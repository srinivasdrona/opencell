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


def load_and_check_window(trace_path: Path, required_observables: tuple[str, ...]) -> WindowGrid:
    """Thin wrapper mapping :class:`EventWindowRefused` to
    :class:`RunnerRefusal` so the CLI has one exception type to catch."""
    try:
        return load_event_window(trace_path, required_observables=required_observables)
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


# ---------------------------------------------------------------------------
# Pure metrics orchestration
# ---------------------------------------------------------------------------


def evaluate_gate(
    *,
    process: str,
    adapter_id: str,
    event_timing_model: str,
    magnitude_gateable: bool,
    karr_timelines: list[EventTimeline],
    oc_timelines: list[EventTimeline],
    karr_payloads: list[dict[str, float]] | None = None,
    oc_payloads: list[dict[str, float]] | None = None,
    karr_single_fire_offsets: np.ndarray | None = None,
    oc_single_fire_offsets: np.ndarray | None = None,
    rng: np.random.Generator,
    k_eng: float = metrics.DEFAULT_K_ENG,
    b_resamples: int = metrics.DEFAULT_B_RESAMPLES,
) -> ResultDoc:
    """Compute the count + timing (+ optional payload) gates and aggregate
    a process-level verdict, plus the C6 spurious-firing diagnostic."""
    if len(karr_timelines) != len(oc_timelines):
        raise ValueError("karr_timelines and oc_timelines must be paired 1:1 per seed.")

    check_empty_support(karr_timelines, oc_timelines)

    count_result = metrics.count_gate(karr_timelines, oc_timelines, rng=rng, b_resamples=b_resamples, k_eng=k_eng)

    if event_timing_model == "repeated_firing":
        timing_result = metrics.timing_gate_repeated_firing(
            karr_timelines, oc_timelines, rng=rng, b_resamples=b_resamples, k_eng=k_eng
        )
    elif event_timing_model == "single_firing":
        if karr_single_fire_offsets is None or oc_single_fire_offsets is None:
            raise ValueError("single_firing model requires karr/oc_single_fire_offsets.")
        timing_result = metrics.timing_gate_single_firing(
            karr_single_fire_offsets, oc_single_fire_offsets, rng=rng, b_resamples=b_resamples, k_eng=k_eng
        )
    else:
        raise ValueError(f"Unknown event_timing_model: {event_timing_model!r}")

    if magnitude_gateable:
        if karr_payloads is None or oc_payloads is None:
            raise ValueError("magnitude_gateable=True requires karr/oc_payloads.")
        payload_result = metrics.payload_gate(karr_payloads, oc_payloads, rng=rng, b_resamples=b_resamples, k_eng=k_eng)
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
    reasons: list[str] = []
    if oc_only:
        reasons.append(
            f"OC fired on {sum(len(v) for v in oc_only.values())} tick(s) where Karr did not "
            f"(seeds: {sorted(oc_only)}) -- spurious OC-only firing (C6)."
        )
        verdict = "FAIL"
    elif any(c.verdict == "FAIL" for c in gating_channels):
        verdict = "FAIL"
    elif all(c.verdict == "NO_KARR_SUPPORT" for c in gating_channels):
        verdict = "FAIL"
        reasons.append("Every gating channel reports NO_KARR_SUPPORT.")
    elif all(c.verdict in ("PASS", "SEED_NOISE") for c in gating_channels):
        verdict = "PASS"
    else:
        verdict = "FAIL"
        reasons.append("At least one gating channel is NO_KARR_SUPPORT while others PASS; not a clean PASS.")

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

    window = load_and_check_window(trace_path, ra_smoke._RA_OBSERVABLES)

    l2 = ra_smoke._import_l2_replay_common()
    from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess  # noqa: PLC0415

    process_obj = KarrRibosomeAssemblyProcess({"rng_seed": int(seed)})
    adapter = ra_smoke.RibosomeAssemblySmokeAdapter()

    karr_fires = 0
    oc_fires = 0
    per_tick: list[dict] = []
    for tick in range(window.n_ticks):
        karr_obs = adapter.karr_observation(window, tick)
        state, _wids = ra_smoke.build_karr_conditioned_state(process_obj, window, tick)
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
