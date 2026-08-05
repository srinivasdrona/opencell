"""Real N=50/M=200 event-class gate computation for RibosomeAssembly.

This is the process-specific driver that turns the 50 real,
individually-validated event-window MAT traces
(``data/m1_sources/karr_native/per_process_traces_v2_event_s{000..049}/
RibosomeAssembly_100ticks.mat``) into an honest, computed
``scripts.l2_event.runner.evaluate_gate`` verdict -- replacing the
seed-0-only ``structural_smoke`` / ``NOT_APPLICABLE`` evidence this
process previously carried (see
``docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/``).

It deliberately reuses, rather than re-implements, every real code path a
computed gate verdict must go through:

* :func:`scripts.l2_event.ribosome_assembly_seed_audit.audit_ribosome_assembly_n50_seeds`
  -- refuses (nonzero exit, no evidence written) unless all 50 seeds are
  present, individually valid (hash-bound to the current
  ``scripts/matlab/mnrnd.m`` shim + the M4 stride/tick contract), and
  non-aliased (no duplicated file content across seeds).
* :func:`scripts.l2_event.adapters.ribosome_assembly_smoke.build_karr_conditioned_state`
  / :func:`run_ribosome_assembly_oc_tick` -- the SAME real per-tick OC
  state construction + real OC port invocation the seed-0 structural
  smoke and this adapter's own unit tests already use (never a
  reimplementation, never a synthetic/mocked OC tick).
* :class:`scripts.l2_event.adapters.ribosome_assembly_gate.RibosomeAssemblyGateAdapter`
  -- the existing, unit-tested, gating-ready adapter (``ribosome_assembly.
  gate.v1``); this script never hand-builds ``EventObservation``/
  ``EventTimeline`` objects, only the adapter's own
  ``karr_observation``/``oc_observation`` methods do.
* :func:`scripts.l2_event.runner.evaluate_gate` -- the real statistical
  orchestration function (same refusal gauntlet a CLI invocation would
  run: ``check_adapter``, ``check_ensemble_size``, ``check_empty_support``,
  ``check_timeline_cohort_consistency``).

This module intentionally never calls
:func:`scripts.l2_event.evidence.write_index` -- the shared, tracked
``evidence_index.json`` is out of scope for this task (a future event
integration branch regenerates it). It only writes this ONE process's
live run artifacts (``artifacts/l2_event/RibosomeAssembly/<run_id>/``) and
bundles them into this ONE process's tracked evidence directory
(``docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/``).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import evidence, metrics  # noqa: E402
from scripts.l2_event.adapters import ribosome_assembly_smoke as ra_smoke  # noqa: E402
from scripts.l2_event.adapters.ribosome_assembly_gate import (  # noqa: E402
    RibosomeAssemblyGateAdapter,
)
from scripts.l2_event.launcher import KARR_NATIVE_ROOT, event_window_mat_path  # noqa: E402
from scripts.l2_event.registry import (  # noqa: E402
    REGISTRY_PATH,
    RegistryError,
    registry_sha256,
    resolve_process_entry,
)
from scripts.l2_event.ribosome_assembly_seed_audit import (  # noqa: E402
    DEFAULT_SPECS_PATH,
    REQUIRED_N_SEEDS,
    SeedAuditError,
    audit_ribosome_assembly_n50_seeds,
)
from scripts.l2_event.runner import (  # noqa: E402
    RunnerRefusal,
    evaluate_gate,
    load_and_check_window,
)
from scripts.l2_event.schema import (  # noqa: E402
    SCHEMA_VERSION,
    EventTimeline,
    InputManifest,
    InputManifestEntry,
    ProvenanceDoc,
)
from scripts.l2_event.window_loader import classify_trace_dir  # noqa: E402

PROCESS = "RibosomeAssembly"


class GateRunRefused(Exception):  # noqa: N818
    # Matches this package's established RunnerRefusal/EventWindowRefused
    # naming convention (runner.py, window_loader.py) rather than an
    # "Error"-suffixed name.
    """Raised when this driver refuses to attempt (or finish) a real N=50
    gate computation -- e.g. the seed audit is incomplete. Distinct from
    :class:`scripts.l2_event.runner.RunnerRefusal`, which this module lets
    propagate unchanged when it is ``evaluate_gate`` itself refusing."""


def _build_seed_timelines(
    seed: int, trace_path: Path, adapter: RibosomeAssemblyGateAdapter
) -> tuple[EventTimeline, EventTimeline, list[dict[str, float]], list[dict[str, float]], Any]:
    """Build one seed's real Karr + OC :class:`EventTimeline` (plus fired-
    tick payload lists) by replaying every tick of its event window through
    the real OC port, mirroring
    ``tests/scripts/test_l2_event_ribosome_assembly_gate.py::
    test_gate_adapter_real_seed0_round_trip_reproduces_ticks_9_and_17``
    exactly, generalized to any of the 50 seeds. Returns the loaded
    ``WindowGrid`` too, so the caller can build this seed's
    ``InputManifestEntry`` without re-loading the file."""
    from opencell.vivarium.karr_ribosome_assembly import (
        KarrRibosomeAssemblyProcess,  # noqa: PLC0415
    )

    window = load_and_check_window(trace_path, ra_smoke._RA_OBSERVABLES, require_stride_contract=True)
    process_obj = KarrRibosomeAssemblyProcess({"rng_seed": int(seed)})

    karr_obs_list = []
    oc_obs_list = []
    karr_payloads: list[dict[str, float]] = []
    oc_payloads: list[dict[str, float]] = []
    for tick in range(window.n_ticks):
        state, _ = ra_smoke.build_karr_conditioned_state(process_obj, window, tick)
        karr_obs = adapter.karr_observation(window, tick)
        update = ra_smoke.run_ribosome_assembly_oc_tick(process_obj, state)
        oc_obs = adapter.oc_observation(tick, state, update)
        karr_obs_list.append(karr_obs)
        oc_obs_list.append(oc_obs)
        if karr_obs.fired:
            karr_payloads.append(karr_obs.payload)
        if oc_obs.fired:
            oc_payloads.append(oc_obs.payload)

    karr_timeline = EventTimeline(process=PROCESS, seed=seed, observations=tuple(karr_obs_list))
    oc_timeline = EventTimeline(process=PROCESS, seed=seed, observations=tuple(oc_obs_list))
    return karr_timeline, oc_timeline, karr_payloads, oc_payloads, window


def run_real_n50_gate(
    *,
    specs_path: Path = DEFAULT_SPECS_PATH,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    registry_path: Path = REGISTRY_PATH,
    bootstrap_seed: int = 0,
) -> dict[str, Any]:
    """Audit, then (only if the audit is clean) compute the real 50-seed
    gate verdict end to end. Returns a dict with the audit report, the
    computed :class:`~scripts.l2_event.schema.ResultDoc`, and the per-seed
    input manifest entries -- the exact ingredients the evidence writer
    below needs. Raises :class:`GateRunRefused` if the audit is not clean
    (never partially writes evidence in that case)."""
    audit = audit_ribosome_assembly_n50_seeds(specs_path, karr_native_root=karr_native_root)
    if not audit["all_seeds_valid"]:
        n_missing = REQUIRED_N_SEEDS - audit["n_seeds_valid"]
        raise GateRunRefused(
            f"seed audit is not clean: only {audit['n_seeds_valid']}/{REQUIRED_N_SEEDS} seeds are "
            f"valid ({n_missing} missing/invalid/aliased); refusing to attempt a real gate "
            "computation from an incomplete or laundered cohort. See the audit report's "
            "per_seed[].reason for details."
        )

    try:
        registry_entry = resolve_process_entry(PROCESS, registry_path)
    except RegistryError as exc:
        raise GateRunRefused(f"could not resolve registry entry for {PROCESS!r}: {exc}") from exc

    adapter = RibosomeAssemblyGateAdapter()
    karr_timelines: list[EventTimeline] = []
    oc_timelines: list[EventTimeline] = []
    karr_payloads_by_seed: list[list[dict[str, float]]] = []
    oc_payloads_by_seed: list[list[dict[str, float]]] = []
    input_entries: list[InputManifestEntry] = []

    for seed in range(REQUIRED_N_SEEDS):
        trace_path = event_window_mat_path(PROCESS, seed, n_ticks=100, karr_native_root=karr_native_root)
        karr_tl, oc_tl, karr_pl, oc_pl, window = _build_seed_timelines(seed, trace_path, adapter)
        karr_timelines.append(karr_tl)
        oc_timelines.append(oc_tl)
        karr_payloads_by_seed.append(karr_pl)
        oc_payloads_by_seed.append(oc_pl)
        input_entries.append(
            InputManifestEntry(
                path=str(trace_path.resolve()),
                sha256=evidence.sha256_file(trace_path),
                seed=seed,
                n_ticks=window.n_ticks,
                tick_offset=window.tick_offset,
                trace_kind=classify_trace_dir(trace_path),
            )
        )

    # RunnerRefusal (e.g. ADAPTER_NOT_GATING_READY if the registry has not
    # yet been promoted, or SINGLE_SEED_ENSEMBLE_REQUIRED if somehow fewer
    # than 50 timelines were built) is allowed to propagate unchanged --
    # this is the SAME refusal gauntlet a real CLI gate invocation runs,
    # never bypassed or caught-and-silenced here.
    rng = np.random.default_rng(bootstrap_seed)
    result = evaluate_gate(
        process=PROCESS,
        registry_entry=registry_entry,
        adapter=adapter,
        karr_timelines=karr_timelines,
        oc_timelines=oc_timelines,
        karr_payloads_by_seed=karr_payloads_by_seed,
        oc_payloads_by_seed=oc_payloads_by_seed,
        rng=rng,
    )

    return {
        "audit": audit,
        "result": result,
        "input_entries": input_entries,
        "registry_entry": registry_entry,
    }


def write_n50_gate_evidence(
    outcome: dict[str, Any], *, karr_native_root: Path = KARR_NATIVE_ROOT, registry_path: Path = REGISTRY_PATH
) -> Path:
    """Write the mandatory 5-artifact evidence set for this real N=50 gate
    run, then bundle it into the tracked, portable
    ``docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/`` directory.
    Deliberately never calls ``evidence.write_index`` (shared
    ``evidence_index.json`` is out of this task's scope)."""
    result = outcome["result"]
    input_entries: list[InputManifestEntry] = outcome["input_entries"]
    registry_entry = outcome["registry_entry"]

    run_id = f"n50-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    generated_at = datetime.now(UTC).isoformat()

    input_manifest = InputManifest(schema_version=SCHEMA_VERSION, process=PROCESS, inputs=input_entries)

    null_calibration = {
        "schema_version": SCHEMA_VERSION,
        "process": PROCESS,
        "cluster_unit": "seed",
        "b_resamples": metrics.DEFAULT_B_RESAMPLES,
        "channels": [
            {
                "channel": c.channel,
                "statistic_name": c.statistic_name,
                "statistic_value": c.statistic_value,
                "q95_null": c.q95_null,
                "k_eng": c.k_eng,
                "threshold": c.threshold,
                "verdict": c.verdict,
            }
            for c in result.channels
        ],
    }

    provenance = ProvenanceDoc(
        schema_version=SCHEMA_VERSION,
        process=PROCESS,
        adapter_id=registry_entry.adapter_id or "ribosome_assembly.gate.v1",
        adapter_module="scripts.l2_event.adapters.ribosome_assembly_gate",
        karr_source=str(karr_native_root.resolve()),
        git_sha=evidence.current_git_sha(),
        registry_sha256=registry_sha256(registry_path),
        generated_at=generated_at,
        k_eng_provenance=metrics.K_ENG_PROVENANCE,
    )

    summary = {
        "process": PROCESS,
        "mode": "gate",
        "verdict": result.verdict,
        "n_seeds_karr": result.n_seeds_karr,
        "n_seeds_oc": result.n_seeds_oc,
        "channels": {c.channel: c.verdict for c in result.channels},
        "reasons": result.reasons,
        "generated_at": generated_at,
    }

    run_dir = evidence.write_run_artifacts(
        PROCESS,
        run_id,
        {
            "result.json": result.to_json(),
            "input_manifest.json": input_manifest.to_json(),
            "null_calibration.json": null_calibration,
            "provenance.json": provenance.to_json(),
            "SUMMARY.json": summary,
        },
    )
    bundle_dir = evidence.bundle_run(run_dir, PROCESS)
    return bundle_dir


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", default=str(DEFAULT_SPECS_PATH))
    parser.add_argument("--karr-native-root", default=str(KARR_NATIVE_ROOT))
    parser.add_argument("--registry-path", default=str(REGISTRY_PATH))
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    parser.add_argument(
        "--write-evidence",
        action="store_true",
        help="Write/bundle the tracked evidence artifacts. Without this flag, only prints the verdict (dry run).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        outcome = run_real_n50_gate(
            specs_path=Path(args.specs),
            karr_native_root=Path(args.karr_native_root),
            registry_path=Path(args.registry_path),
            bootstrap_seed=args.bootstrap_seed,
        )
    except (GateRunRefused, SeedAuditError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except RunnerRefusal as exc:
        print(f"REFUSED ({exc.reason}): {exc}", file=sys.stderr)
        return 2

    result = outcome["result"]
    print(f"VERDICT: process={PROCESS} mode=gate verdict={result.verdict}")
    for c in result.channels:
        print(f"  channel={c.channel} verdict={c.verdict} statistic={c.statistic_name}={c.statistic_value} q95_null={c.q95_null}")
    for reason in result.reasons:
        print(f"  reason: {reason}")

    if args.write_evidence:
        bundle_dir = write_n50_gate_evidence(
            outcome, karr_native_root=Path(args.karr_native_root), registry_path=Path(args.registry_path)
        )
        print(f"evidence bundled: {evidence.relative_to_repo(bundle_dir)}")

    return 0 if result.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
