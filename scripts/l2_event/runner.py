"""Runner + refusal gauntlet for L2.event (requirement 4, surfaces S8/S9).

This module deliberately separates three concerns that a monolithic
"just run it" script would blur together:

1. :func:`check_ensemble_size`, :func:`check_adapter`,
   :func:`load_and_check_window` -- the refusal gauntlet. Each raises
   :class:`RunnerRefusal` with a stable ``reason`` code
   (:data:`scripts.l2_event.schema.RefusalReason`) rather than returning a
   silent default.
2. :func:`evaluate_gate` -- pure statistical orchestration over
   already-built :class:`~scripts.l2_event.schema.EventTimeline` objects.
   It has no idea how those timelines were produced (real MAT trace +
   real OC port, or synthetic test fixtures) -- that decoupling is what
   lets this module's tests run without any process-specific wiring.
3. :func:`main` -- the CLI entrypoint, which is the only place all of the
   above are wired together for a real invocation. Because no process in
   this task has ``adapter_status: gating_ready`` (see
   ``docs/phase_f/l2_event/event_registry.yaml``), invoking this CLI in
   ``--mode gate`` against any of the four real processes today always
   ends in a documented refusal -- that is the correct, honest behavior
   for a foundation task that ships no process wiring.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.l2_event import evidence, metrics
from scripts.l2_event.adapters.base import EventAdapter
from scripts.l2_event.registry import (
    EventRegistryEntry,
    RegistryError,
    load_registry,
    registry_sha256,
    resolve_process_entry,
    validate_against_catalog,
)
from scripts.l2_event.schema import (
    SCHEMA_VERSION,
    EventTimeline,
    GateChannelResult,
    InputManifest,
    InputManifestEntry,
    NullCalibrationDoc,
    ProvenanceDoc,
    RefusalReason,
    ResultDoc,
)
from scripts.l2_event.window_loader import (
    EventWindowRefused,
    WindowGrid,
    classify_trace_dir,
    load_event_window,
)

EXIT_OK = 0
EXIT_GATE_FAIL = 1
EXIT_REFUSED = 2


class RunnerRefusal(Exception):
    """A precondition/input failure the runner refuses to proceed past.
    Distinct from a computed FAIL: this means no verdict was attempted at
    all (requirement 4's "no zero==zero PASS" and friends)."""

    def __init__(self, reason: RefusalReason, message: str) -> None:
        super().__init__(message)
        self.reason: RefusalReason = reason


# ---------------------------------------------------------------------------
# Refusal gauntlet
# ---------------------------------------------------------------------------


def check_ensemble_size(n_seeds_provided: int, required_n_seeds: int) -> None:
    """Refuse a single-seed (or otherwise under-sized) run when the
    registry/catalog declares an ensemble requirement > 1."""
    if required_n_seeds > 1 and n_seeds_provided < required_n_seeds:
        raise RunnerRefusal(
            "SINGLE_SEED_ENSEMBLE_REQUIRED",
            f"{n_seeds_provided} seed(s) provided but this process requires an "
            f"ensemble of {required_n_seeds} seeds; refusing to compute a gate "
            "verdict from an under-powered cohort.",
        )


def check_adapter(adapter: EventAdapter, process: str, registry_entry: EventRegistryEntry) -> None:
    """Refuse an adapter/process mismatch, an adapter not declared in the
    registry for this process, or an adapter not cleared for gating."""
    if adapter.process_name != process:
        raise RunnerRefusal(
            "ADAPTER_PROCESS_MISMATCH",
            f"Adapter '{adapter.adapter_id}' is registered for process "
            f"'{adapter.process_name}', not '{process}'.",
        )
    if registry_entry.adapter_id != adapter.adapter_id:
        raise RunnerRefusal(
            "ADAPTER_NOT_REGISTERED",
            f"Adapter '{adapter.adapter_id}' is not the registry's declared "
            f"adapter_id ('{registry_entry.adapter_id}') for process '{process}'.",
        )
    if registry_entry.adapter_status != "gating_ready":
        raise RunnerRefusal(
            "ADAPTER_NOT_GATING_READY",
            f"Process '{process}' adapter_status="
            f"'{registry_entry.adapter_status}' (not 'gating_ready'); this "
            "foundation ships no process-specific gating wiring, only the "
            "generic runner/metrics/evidence machinery plus an optional "
            "read-only structural smoke.",
        )


def load_and_check_window(
    trace_path: Path, required_observables: tuple[str, ...], *, require_stride_contract: bool = True
) -> WindowGrid:
    """Thin wrapper mapping :class:`EventWindowRefused` to
    :class:`RunnerRefusal` so the CLI has one exception type to catch."""
    try:
        return load_event_window(
            trace_path,
            required_observables=required_observables,
            require_stride_contract=require_stride_contract,
        )
    except EventWindowRefused as exc:
        raise RunnerRefusal(exc.reason, str(exc)) from exc


def check_empty_support(karr_timelines: list[EventTimeline], oc_timelines: list[EventTimeline]) -> None:
    """Refuse (rather than silently PASS) when Karr has zero event support
    across the entire cohort AND OC also has zero support -- this is not a
    refusal in the metrics layer (which correctly reports
    ``NO_KARR_SUPPORT`` per channel) but a whole-run-level early refusal
    for callers that want to short-circuit before spending bootstrap
    compute on a vacuous cohort."""
    karr_total = sum(t.total_fire_count for t in karr_timelines)
    if karr_total == 0:
        oc_total = sum(t.total_fire_count for t in oc_timelines)
        if oc_total == 0:
            raise RunnerRefusal(
                "EMPTY_EVENT_SUPPORT",
                "Karr has zero event support across the entire cohort; "
                "refusing a vacuous zero==zero run rather than reporting PASS.",
            )
        # OC fired despite Karr having none: this is a hard FAIL, not a
        # refusal -- let evaluate_gate's count/timing gates report it.


def check_timeline_cohort_consistency(
    karr_timelines: list[EventTimeline], oc_timelines: list[EventTimeline]
) -> None:
    """M2 (Opus5 review) "window metadata/stride" gauntlet item, as applied
    inside ``evaluate_gate`` itself (which only ever sees already-built
    :class:`EventTimeline` objects, never the raw ``WindowGrid``/HDF5
    metadata that ``window_loader.load_event_window`` validates at ingest).

    This is a second, cohort-level layer: every timeline in the cohort
    (both Karr and OC sides) must share the same ``n_ticks``. A caller that
    hand-assembled timelines from mismatched-length windows (e.g. one seed
    loaded with a truncated/differently-strided grid) is refused here even
    though each individual timeline may look internally well-formed. The
    per-file stride=1/tick_start/tick_end contract itself is enforced by
    ``window_loader`` at load time (M4); this check cannot see stride
    directly, only its consequence (inconsistent tick counts across the
    cohort actually fed to the evaluator).
    """
    all_timelines = list(karr_timelines) + list(oc_timelines)
    if not all_timelines:
        return
    n_ticks_values = {t.n_ticks for t in all_timelines}
    if len(n_ticks_values) > 1:
        raise RunnerRefusal(
            "INCOMPLETE_WINDOW",
            f"Timeline cohort has inconsistent n_ticks across seeds/sides: "
            f"{sorted(n_ticks_values)}; refusing rather than comparing "
            "windows of different lengths (M2 window-consistency check).",
        )


# ---------------------------------------------------------------------------
# Pure metrics orchestration
# ---------------------------------------------------------------------------


def evaluate_gate(
    *,
    process: str,
    registry_entry: EventRegistryEntry,
    adapter: EventAdapter,
    karr_timelines: list[EventTimeline],
    oc_timelines: list[EventTimeline],
    karr_payloads_by_seed: list[list[dict[str, float]]] | None = None,
    oc_payloads_by_seed: list[list[dict[str, float]]] | None = None,
    karr_single_fire_offsets: np.ndarray | None = None,
    oc_single_fire_offsets: np.ndarray | None = None,
    rng: np.random.Generator,
    k_eng: float = metrics.DEFAULT_K_ENG,
    b_resamples: int = metrics.DEFAULT_B_RESAMPLES,
) -> ResultDoc:
    """Compute the count + timing (+ optional payload) gates and aggregate
    a process-level verdict, plus the C6 spurious-firing diagnostic.

    M2 (Opus5 review): this function runs the SAME refusal gauntlet the CLI
    (`main`) runs -- ``check_adapter``, ``check_ensemble_size``,
    ``check_empty_support``, ``check_timeline_cohort_consistency`` -- before
    computing anything. Before this fix, those checks lived only in
    ``main()``'s CLI path; any direct caller of ``evaluate_gate`` (a future
    automation script, a test, a notebook) could bypass every one of them.
    ``registry_entry``/``adapter`` (rather than bare ``adapter_id``/
    ``event_timing_model``/``magnitude_gateable`` strings a caller could
    pass inconsistently) are now the single source of truth for what this
    process's gate is allowed to look like -- there is no parameter
    combination that lets a caller assert an adapter_id/timing model the
    registry does not itself declare.
    """
    check_adapter(adapter, process, registry_entry)
    check_ensemble_size(len(karr_timelines), registry_entry.required_n_seeds)
    if len(karr_timelines) != len(oc_timelines):
        raise ValueError("karr_timelines and oc_timelines must be paired 1:1 per seed.")
    check_empty_support(karr_timelines, oc_timelines)
    check_timeline_cohort_consistency(karr_timelines, oc_timelines)

    adapter_id = registry_entry.adapter_id
    event_timing_model = registry_entry.event_timing_model
    magnitude_gateable = registry_entry.magnitude_gateable
    n_seeds_total = len(karr_timelines)

    # Opus5 review round 3, item #3: the pooled-fire-tick floor for a
    # repeated_firing process and the fired-seed-fraction floor for a
    # single_firing process are DIFFERENT adapter-specific support
    # semantics ("the generic pooled50 conflict") -- always compute the
    # correct one from the registry's declared timing model rather than
    # relying on `count_gate`'s bare repeated_firing-shaped default.
    min_karr_support = metrics.count_support_floor(event_timing_model, n_seeds_total)
    count_result = metrics.count_gate(
        karr_timelines, oc_timelines, rng=rng, b_resamples=b_resamples, k_eng=k_eng, min_karr_support=min_karr_support
    )

    if event_timing_model == "repeated_firing":
        timing_result = metrics.timing_gate_repeated_firing(
            karr_timelines, oc_timelines, rng=rng, b_resamples=b_resamples, k_eng=k_eng
        )
    elif event_timing_model == "single_firing":
        if karr_single_fire_offsets is None or oc_single_fire_offsets is None:
            raise ValueError("single_firing model requires karr/oc_single_fire_offsets.")
        timing_result = metrics.timing_gate_single_firing(
            karr_single_fire_offsets,
            oc_single_fire_offsets,
            rng=rng,
            b_resamples=b_resamples,
            k_eng=k_eng,
            n_seeds_total=n_seeds_total,
        )
    else:
        raise ValueError(f"Unknown event_timing_model: {event_timing_model!r}")

    if magnitude_gateable:
        if karr_payloads_by_seed is None or oc_payloads_by_seed is None:
            raise ValueError("magnitude_gateable=True requires karr/oc_payloads_by_seed.")
        # Opus5 review round 3, item #2: an adapter may declare its exact
        # required payload component keyspace (e.g. RA's 2 real WIDs) so
        # `payload_gate` can refuse BEFORE computing anything if the
        # observed keyspace doesn't match -- `getattr(..., None)` keeps
        # this optional for adapters (e.g. test fakes) that don't declare
        # one, in which case only the generic union/NO_OC_COMPONENT/
        # SPURIOUS_OC_COMPONENT checks apply.
        required_components = getattr(adapter, "required_payload_components", None)
        # Opus5 review round 4, item #2: pass `expected_n_seeds` so
        # `payload_gate` refuses hard (SEED_CARDINALITY_MISMATCH) rather
        # than silently accepting a flattened/mis-clustered payload cohort
        # whose total element count happens to look plausible but whose
        # per-seed grouping doesn't match this ensemble's actual seed
        # count (the same `n_seeds_total` already used for the count/
        # timing gates and `check_ensemble_size` above).
        payload_result = metrics.payload_gate(
            karr_payloads_by_seed,
            oc_payloads_by_seed,
            rng=rng,
            b_resamples=b_resamples,
            k_eng=k_eng,
            required_components=required_components,
            expected_n_seeds=n_seeds_total,
        )
    else:
        payload_result = GateChannelResult(
            channel="payload",
            verdict="NOT_GATEABLE_REDUNDANT",
            statistic_name="n/a",
            statistic_value=None,
            q95_null=None,
            k_eng=None,
            threshold=None,
            n_nonzero_oc=0,
            n_nonzero_karr=0,
            reasons=["magnitude_gateable=False for this process (D6): no non-redundant payload channel exists."],
        )

    oc_only: dict[str, list[int]] = {}
    for karr_tl, oc_tl in zip(karr_timelines, oc_timelines):
        ticks = metrics.oc_only_fire_ticks(karr_tl, oc_tl)
        if ticks:
            oc_only[str(karr_tl.seed)] = ticks

    channels = [count_result, timing_result, payload_result]
    gating_channels = [c for c in channels if c.verdict not in ("NOT_GATEABLE_REDUNDANT",)]

    # M1 (Opus5 review): a channel that could not compute a real statistic
    # at all (zero/insufficient Karr support, or a degenerate null) must
    # REFUSE the whole process verdict, not silently fall through to FAIL
    # or -- worse -- PASS. A channel where OC produced nothing despite Karr
    # support (or the symmetric Karr-silent-but-OC-fires case) is a real,
    # computed calibration failure, so it rolls into FAIL instead.
    NON_COMPUTABLE = {"NO_KARR_SUPPORT", "INSUFFICIENT_KARR_SUPPORT", "DEGENERATE_NULL"}
    # Opus5 review round 3, item #2: the payload gate's two component-
    # keyspace verdicts are FAIL-class (an adapter mapping gap/spurious
    # component is a real defect, not a numeric divergence) and must roll
    # into the process verdict the same way FAIL/NO_OC_SUPPORT already do.
    # Opus5 review round 4, item #2: `SEED_CARDINALITY_MISMATCH` (a
    # caller/adapter passed a payload cohort whose per-seed shape doesn't
    # match the ensemble) is likewise a real defect, not a refusal-for-
    # under-power -- it rolls into FAIL_LIKE, not NON_COMPUTABLE.
    FAIL_LIKE = {"FAIL", "NO_OC_SUPPORT", "NO_OC_COMPONENT", "SPURIOUS_OC_COMPONENT", "SEED_CARDINALITY_MISMATCH"}

    reasons: list[str] = []
    if oc_only:
        reasons.append(
            f"OC fired on {sum(len(v) for v in oc_only.values())} tick(s) where Karr did not "
            f"(seeds: {sorted(oc_only)}) -- spurious OC-only firing (C6)."
        )
        verdict = "FAIL"
    elif any(c.verdict in FAIL_LIKE for c in gating_channels):
        verdict = "FAIL"
        reasons.append(
            "At least one gating channel is FAIL or NO_OC_SUPPORT (OC "
            "produced nothing despite Karr support)."
        )
    elif any(c.verdict in NON_COMPUTABLE for c in gating_channels):
        verdict = "REFUSED"
        non_computable_channels = sorted({c.channel for c in gating_channels if c.verdict in NON_COMPUTABLE})
        reasons.append(
            f"Gating channel(s) {non_computable_channels} could not compute a "
            "calibrated statistic (zero/insufficient Karr support or a "
            "degenerate null); refusing rather than reporting a verdict "
            "derived from an uncalibrated channel (M1)."
        )
    elif all(c.verdict in ("PASS", "SEED_NOISE") for c in gating_channels):
        verdict = "PASS"
    else:
        verdict = "FAIL"
        reasons.append("At least one gating channel is in an unexpected state; not a clean PASS.")

    return ResultDoc(
        schema_version=SCHEMA_VERSION,
        process=process,
        adapter_id=adapter_id,
        event_timing_model=event_timing_model,
        mode="gate",
        verdict=verdict,
        channels=channels,
        oc_only_fire_ticks=oc_only,
        n_seeds_karr=len(karr_timelines),
        n_seeds_oc=len(oc_timelines),
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="l2-event-runner", description=__doc__)
    parser.add_argument("--process", required=True)
    parser.add_argument("--mode", choices=["gate", "smoke"], default="smoke")
    parser.add_argument("--registry-path", default=None)
    parser.add_argument("--karr-source", default=None, help="Directory containing per_process_traces_v2_event_s{seed:03d}/ subdirectories.")
    parser.add_argument("--seeds", default="0", help="Comma-separated seed list, e.g. '0,1,2'.")
    parser.add_argument("--out-dir", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    registry_path = Path(args.registry_path) if args.registry_path else None
    try:
        registry = load_registry(registry_path) if registry_path else load_registry()
    except RegistryError as exc:
        print(f"REFUSED (registry error): {exc}", file=sys.stderr)
        return EXIT_REFUSED

    problems = validate_against_catalog(registry)
    if problems:
        print("REFUSED (registry/catalog inconsistency):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return EXIT_REFUSED

    if args.process not in registry:
        print(f"REFUSED (REGISTRY_PROCESS_UNKNOWN): '{args.process}' not in registry.", file=sys.stderr)
        return EXIT_REFUSED

    entry = registry[args.process]
    if not entry.in_scope_v4:
        print(
            f"REFUSED (REGISTRY_OUT_OF_V4_SCOPE): '{args.process}' is out of "
            f"v4 scope: {entry.deferred_reason}",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    seeds = [int(s) for s in args.seeds.split(",") if s.strip() != ""]

    if args.mode == "gate":
        # M2 (Opus5 review): these are the same checks `evaluate_gate` now
        # runs internally (`check_ensemble_size`, and `check_adapter`'s
        # gating_ready clause). They are duplicated here only as a fast,
        # friendly pre-flight message -- there is no gating-ready adapter
        # in this repo to construct real karr/oc timelines from, so this
        # CLI path can never actually reach a call to `evaluate_gate`
        # today. Once a future process branch adds a gating_ready adapter,
        # this block's job is solely to build that adapter + timelines and
        # call `evaluate_gate(process=..., registry_entry=entry,
        # adapter=..., ...)` -- the SAME function whose internal gauntlet
        # `test_l2_event_runner.py` verifies cannot be bypassed by a direct
        # caller. No parallel/duplicate gating logic is meant to grow here.
        try:
            check_ensemble_size(len(seeds), entry.required_n_seeds)
            if entry.adapter_status != "gating_ready":
                raise RunnerRefusal(
                    "ADAPTER_NOT_GATING_READY",
                    f"Process '{args.process}' has adapter_status="
                    f"'{entry.adapter_status}'; gate mode requires 'gating_ready'. "
                    "This foundation intentionally ships no gating-ready process "
                    "adapters -- see docs/phase_f/l2_event/L2_EVENT_FOUNDATION_STATUS.md.",
                )
        except RunnerRefusal as refusal:
            print(f"REFUSED ({refusal.reason}): {refusal}", file=sys.stderr)
            return EXIT_REFUSED
        print(
            f"REFUSED: gate mode for '{args.process}' has no further path in this "
            "foundation build (no gating-ready adapter exists).",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    # --mode smoke: only RibosomeAssembly has a registered smoke adapter.
    if args.process != "RibosomeAssembly" or entry.adapter_status != "structural_smoke_only":
        print(
            f"REFUSED (ADAPTER_NOT_REGISTERED): '{args.process}' has no "
            f"structural smoke adapter (adapter_status={entry.adapter_status!r}).",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    karr_source = Path(args.karr_source) if args.karr_source else Path("data/m1_sources/karr_native")
    all_ok = True
    for seed in seeds:
        trace_path = karr_source / f"per_process_traces_v2_event_s{seed:03d}" / "RibosomeAssembly_100ticks.mat"
        try:
            result = run_structural_smoke(
                process="RibosomeAssembly",
                seed=seed,
                trace_path=trace_path,
                registry_entry=entry,
                registry=registry,
            )
        except RunnerRefusal as refusal:
            print(f"REFUSED ({refusal.reason}) seed={seed}: {refusal}", file=sys.stderr)
            all_ok = False
            continue
        print(
            f"STRUCTURAL SMOKE OK: process=RibosomeAssembly seed={seed} "
            f"n_ticks={result['n_ticks']} tick_offset={result['tick_offset']} "
            f"karr_fires={result['karr_total_fires']} oc_fires={result['oc_total_fires']} "
            "(mode=structural_smoke, no gate verdict computed)"
        )
        run_dir = _write_smoke_evidence(
            process="RibosomeAssembly",
            seed=seed,
            trace_path=trace_path,
            result=result,
            registry_path=registry_path,
        )
        evidence.bundle_run(run_dir, "RibosomeAssembly")
        evidence.write_index(list(registry.keys()))
        print(f"  evidence written: {evidence.relative_to_repo(run_dir)}")
    return EXIT_OK if all_ok else EXIT_REFUSED


def run_structural_smoke(
    *,
    process: str,
    seed: int,
    trace_path: Path,
    registry_entry: EventRegistryEntry,
    registry: dict[str, EventRegistryEntry],
) -> dict:
    """Run the RibosomeAssembly seed-N structural smoke end to end: load
    the window, replay every tick through the real OC port using only
    Karr's ``states_before`` (never ``states_after``), and compare Karr's
    vs OC's per-tick fire counts. Returns a plain dict summary -- this is
    intentionally NOT a :class:`~scripts.l2_event.schema.ResultDoc` gate
    verdict; callers must not treat ``karr_total_fires == oc_total_fires``
    as a PASS. See module + adapter docstrings."""
    del registry, registry_entry  # not needed here; validated by the caller before dispatch.
    from scripts.l2_event.adapters import ribosome_assembly_smoke as ra_smoke

    # M4: the real seed-0 event MAT predates the stride/tick_start/tick_end
    # (or window_anchor) metadata contract -- see
    # docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md. The
    # structural smoke is explicitly a read-only loader/adapter/OC-port
    # round-trip proof, not a gate verdict, so it tolerates an incomplete
    # contract instead of hard-refusing; the resulting problems are
    # surfaced (never hidden) in the smoke's evidence reasons below.
    window = load_and_check_window(trace_path, ra_smoke._RA_OBSERVABLES, require_stride_contract=False)

    l2 = ra_smoke._import_l2_replay_common()
    from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess  # noqa: PLC0415

    process_obj = KarrRibosomeAssemblyProcess({"rng_seed": int(seed)})

    karr_fires = 0
    oc_fires = 0
    per_tick: list[dict] = []
    adapter: ra_smoke.RibosomeAssemblySmokeAdapter | None = None
    for tick in range(window.n_ticks):
        state, wids_by_observable = ra_smoke.build_karr_conditioned_state(process_obj, window, tick)
        if adapter is None:
            # M3 (Opus5 review): build the adapter's Karr-index -> OC-wid
            # payload mapping once, from the wids the loader/overlay
            # already infers for the `complexs` channel -- this is the
            # SAME wid ordering `build_karr_conditioned_state` uses to
            # overlay Karr's state into the OC template, so Karr's payload
            # keys now line up exactly with `update["complex"]["counts"]`'s
            # real keys instead of meaningless positional placeholders.
            complex_index_by_wid = dict(enumerate(wids_by_observable["complexs"]))
            adapter = ra_smoke.RibosomeAssemblySmokeAdapter(complex_index_by_wid=complex_index_by_wid)
        karr_obs = adapter.karr_observation(window, tick)
        update = ra_smoke.run_ribosome_assembly_oc_tick(process_obj, state)
        oc_obs = adapter.oc_observation(tick, state, update)
        karr_fires += karr_obs.fire_count
        oc_fires += oc_obs.fire_count
        if karr_obs.fired or oc_obs.fired:
            per_tick.append({"tick": tick, "karr_fired": karr_obs.fired, "oc_fired": oc_obs.fired})
    del l2

    return {
        "n_ticks": window.n_ticks,
        "tick_offset": window.tick_offset,
        "karr_total_fires": karr_fires,
        "oc_total_fires": oc_fires,
        "per_tick_fires": per_tick,
        "trace_kind": classify_trace_dir(trace_path),
        "stride_contract_ok": window.stride_contract_ok,
        "stride_contract_problems": list(window.stride_contract_problems),
    }


def _write_smoke_evidence(
    *,
    process: str,
    seed: int,
    trace_path: Path,
    result: dict,
    registry_path: Path | None,
) -> Path:
    """Write the mandatory 5-file artifact set for one structural-smoke
    run, using ``verdict='NOT_APPLICABLE'`` throughout so nothing here can
    be mistaken for a computed gate PASS/FAIL (requirement 5 + D6-style
    escape hatch, applied to the smoke mode rather than the payload
    channel)."""
    run_id = f"seed{seed:03d}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    generated_at = datetime.now(timezone.utc).isoformat()

    result_doc = ResultDoc(
        schema_version=SCHEMA_VERSION,
        process=process,
        adapter_id="ribosome_assembly.smoke.v1",
        event_timing_model="repeated_firing",
        mode="structural_smoke",
        verdict="NOT_APPLICABLE",
        channels=[],
        oc_only_fire_ticks={},
        n_seeds_karr=1,
        n_seeds_oc=1,
        reasons=[
            "structural_smoke_only: proves the loader/adapter/OC-port round-trip works "
            "on one real seed; this is NOT a calibrated ensemble gate verdict.",
            f"karr_total_fires={result['karr_total_fires']} oc_total_fires={result['oc_total_fires']}",
            *(
                ["stride_contract_ok=True: window carries a complete "
                 "stride/tick_start/tick_end(or window_anchor) contract."]
                if result["stride_contract_ok"]
                else [
                    "stride_contract_ok=False (M4, non-fatal for structural_smoke): "
                    + "; ".join(result["stride_contract_problems"])
                ]
            ),
        ],
    )

    input_manifest = InputManifest(
        schema_version=SCHEMA_VERSION,
        process=process,
        inputs=[
            InputManifestEntry(
                path=str(trace_path.resolve()),
                sha256=evidence.sha256_file(trace_path),
                seed=seed,
                n_ticks=result["n_ticks"],
                tick_offset=result["tick_offset"],
                trace_kind=result["trace_kind"],
            )
        ],
    )

    null_calibration = NullCalibrationDoc(
        schema_version=SCHEMA_VERSION,
        process=process,
        channel="n/a",
        statistic_name="n/a",
        b_resamples=0,
        q95_null=0.0,
    )

    provenance = ProvenanceDoc(
        schema_version=SCHEMA_VERSION,
        process=process,
        adapter_id="ribosome_assembly.smoke.v1",
        adapter_module="scripts.l2_event.adapters.ribosome_assembly_smoke",
        karr_source=str(trace_path.parent.resolve()),
        git_sha=evidence.current_git_sha(),
        registry_sha256=registry_sha256(registry_path) if registry_path else registry_sha256(),
        generated_at=generated_at,
        # Opus5 review round 3, item #6/#7: k_eng_provenance is now a real
        # schema field (previously only ever lived inside a
        # GateChannelResult.extra dict, and this structural smoke doesn't
        # even run a gate channel) -- record it here too so every
        # ProvenanceDoc this codebase emits is self-describing about which
        # k_eng constant, if any, was in force.
        k_eng_provenance=metrics.K_ENG_PROVENANCE,
    )

    summary = {
        "process": process,
        "seed": seed,
        "mode": "structural_smoke",
        "verdict": "NOT_APPLICABLE",
        "karr_total_fires": result["karr_total_fires"],
        "oc_total_fires": result["oc_total_fires"],
        "generated_at": generated_at,
    }

    run_dir = evidence.write_run_artifacts(
        process,
        run_id,
        {
            "result.json": result_doc.to_json(),
            "input_manifest.json": input_manifest.to_json(),
            "null_calibration.json": null_calibration.to_json(),
            "provenance.json": provenance.to_json(),
            "SUMMARY.json": summary,
        },
    )
    return run_dir


if __name__ == "__main__":
    raise SystemExit(main())
