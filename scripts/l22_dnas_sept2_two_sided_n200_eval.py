"""Run the frozen DNAS N=200 gate ONCE with the new two-sided sparse rule.

Recomputes the OC chromosome projection tensor with the current worktree's
DNASupercoiling code (both the stochasticRound-early-return fix and the
still-open chromosome-release-RNG gap documented in
STATUS_L22_DNAS_SEPT2.md), streaming the same frozen sibling seed traces and
frozen Karr tensor used by `l22_dnas_followup_rerun_n200.py`, and evaluates
the result with the newly preregistered two-sided rule
(`scripts/l22_dnas_rare_event/two_sided_sparse_gate.py`) instead of the
rejected one-sided `sparse_gate.py` rule.

This script is a new file (mirrors, does not edit,
`l22_dnas_followup_rerun_n200.py`) so the FOLLOWUP7/8 provenance stays intact.
Per PROMPT_SEPT2.md this is run exactly once, after the two-sided rule and its
preregistration document were committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

import _l2_2_design_a_runner_helpers as helpers  # noqa: E402
import _l2_2_dnas_runner_helpers as dnas_helpers  # noqa: E402
from scripts.l22_dnas_rare_event.evaluate_checkpoint import _load_tensor_checkpoint  # noqa: E402
from scripts.l22_dnas_rare_event.two_sided_sparse_gate import (  # noqa: E402
    evaluate_process,
    preregistration_examples,
)

PROCESS = "DNASupercoiling"
DEFAULT_TRACE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native"
DEFAULT_BASE_CHECKPOINT = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "evidence_bundle"
    / "DNASupercoiling"
    / "diagnostic_n200"
    / "raw_captured_tensors_checkpoint.npz"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "evidence_bundle"
    / "DNASupercoiling"
    / "diagnostic_n200_followup"
    / "sept2_two_sided_rerun"
)


def _coerce_cli_path(raw: str | Path) -> Path:
    text = str(raw)
    if len(text) >= 3 and text[1:3] in {":/", ":\\"}:
        win = PureWindowsPath(text)
        drive = str(win.drive).rstrip(":").lower()
        tail = Path(*win.parts[1:])
        return Path("/mnt") / drive / tail
    return Path(text)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", default=str(DEFAULT_TRACE_ROOT))
    parser.add_argument("--base-checkpoint", default=str(DEFAULT_BASE_CHECKPOINT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return parser.parse_args(argv)


def _seed_trace_path(trace_root: Path, seed: int) -> Path:
    if seed == 0:
        return trace_root / "per_process_traces_v2" / f"{PROCESS}_100ticks.mat"
    return trace_root / f"per_process_traces_v2_s{seed:03d}" / f"{PROCESS}_100ticks.mat"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    trace_root = _coerce_cli_path(args.trace_root).resolve()
    base_checkpoint_path = _coerce_cli_path(args.base_checkpoint).resolve()
    out_dir = _coerce_cli_path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    loaded = _load_tensor_checkpoint(base_checkpoint_path)
    karr_tensor = np.asarray(loaded["karr_tensor"], dtype=np.float64)
    n_seeds, m_ticks, n_components = karr_tensor.shape
    if n_components != 2:
        raise ValueError(f"Expected 2 components; got {karr_tensor.shape}")

    sample_process = helpers._dna_supercoiling_process(0)  # noqa: SLF001
    substrate_wids = list(sample_process.substrate_wids)
    enzyme_wids = list(sample_process.enzyme_wids)
    oc_tensor = np.zeros_like(karr_tensor)

    dnas_helpers.reset_dna_supercoiling_persistent_processes()

    # Per-(seed,tick) audit-boundary telemetry: `exceeded_audit_boundary`
    # (opencell/vivarium/dnas_process_rng_ledger.py's ProcessRngReplayRng)
    # was previously computed but never read or aggregated anywhere --
    # Opus's review found 95/5000 ticks across 19 seeds (in a 50-seed
    # production sample) where OC's process-owned-RNG consumption exceeded
    # the independently-recorded real MATLAB draw count for that tick,
    # silently, with no effect on the gate verdict. This aggregation makes
    # any such breach fail the gate closed (see the fail-closed check after
    # the seed loop below) instead of being disclosed-but-ignored.
    audit_boundary_breaches: list[dict[str, Any]] = []
    # Under-consumption tracking (audited, not fail-closed -- see the loop
    # below for rationale).
    audit_boundary_under_consumption: list[dict[str, Any]] = []
    ledger_covered_tick_count = 0

    for seed in range(n_seeds):
        path = _seed_trace_path(trace_root, seed)
        if not path.exists():
            raise FileNotFoundError(f"Missing frozen trace for seed {seed}: {path}")
        with h5py.File(path, "r") as trace:
            before_substrates = helpers._matlab_channel_matrix(trace, trace["states_before/substrates"])  # noqa: SLF001
            before_enzymes = helpers._matlab_channel_matrix(trace, trace["states_before/enzymes"])  # noqa: SLF001
            before_bound = helpers._matlab_channel_matrix(trace, trace["states_before/boundEnzymes"])  # noqa: SLF001
            available_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
            if available_ticks < m_ticks:
                raise ValueError(
                    f"Trace {path} has only {available_ticks} ticks; expected at least {m_ticks}"
                )
            for tick in range(m_ticks):
                before_store = helpers._chromosome_store_at(trace, "states_before", tick)  # noqa: SLF001
                sample_state = {
                    "substrate_wids": substrate_wids,
                    "enzyme_wids": enzyme_wids,
                    "oracle_before_substrates": before_substrates[tick],
                    "oracle_before_enzymes": before_enzymes[tick],
                    "oracle_before_bound_enzymes": before_bound[tick],
                    "oracle_before_chromosome_store": before_store,
                }
                oc_result = dnas_helpers.run_dna_supercoiling_tick(seed, tick, sample_state)
                oc_tensor[seed, tick, 0] = helpers._chromosome_projection_component(  # noqa: SLF001
                    "linkingNumbers.delta_value_sum",
                    before_store,
                    oc_result["chromosome_after_store"],
                )
                oc_tensor[seed, tick, 1] = helpers._chromosome_projection_component(  # noqa: SLF001
                    "linkingNumbers.delta_nnz",
                    before_store,
                    oc_result["chromosome_after_store"],
                )
                process = dnas_helpers._DNA_SUPERCOILING_PERSISTENT_PROCESSES._processes[seed]  # noqa: SLF001
                ledger = process._process_rng_ledger  # noqa: SLF001
                if ledger is not None and ledger.has_tick(tick):
                    ledger_covered_tick_count += 1
                    cache = process._process_rng_replay_cache  # noqa: SLF001
                    if cache is not None and int(cache[0]) == tick:
                        recorded_len = int(ledger.entry_for_tick(tick).recorded_len)
                        consumed = int(cache[1]._pos)  # noqa: SLF001
                        if bool(cache[1].exceeded_audit_boundary):
                            audit_boundary_breaches.append(
                                {
                                    "seed": int(seed),
                                    "tick": int(tick),
                                    "recorded_len": recorded_len,
                                    "consumed": consumed,
                                }
                            )
                        # Under-consumption is not an error (the state-seeded
                        # ledger never "runs out" on a shortfall, unlike the
                        # old finite-list design), but per instruction to
                        # audit both directions where possible, it is still
                        # tracked: it would mean OC computed FEWER
                        # candidate/events than the real historical run
                        # needed for this tick -- a different, not-yet-seen
                        # failure mode were it to occur.
                        elif consumed < recorded_len:
                            audit_boundary_under_consumption.append(
                                {
                                    "seed": int(seed),
                                    "tick": int(tick),
                                    "recorded_len": recorded_len,
                                    "consumed": consumed,
                                }
                            )
        print(f"[l22_dnas_sept2_two_sided_n200_eval] seed {seed:03d}/{n_seeds - 1:03d} complete")

    checkpoint_path = out_dir / "raw_captured_tensors_checkpoint.npz"
    np.savez(
        checkpoint_path,
        oc_tensor=oc_tensor,
        karr_tensor=karr_tensor,
        component_scales=loaded["component_scales"],
    )

    evaluation = evaluate_process(oc_tensor, karr_tensor, loaded["component_scales"])

    # Fail-closed audit-boundary check (mandate: "make any nonzero boundary
    # breach fail closed until root-caused; do not merely disclose it").
    # This is independent of, and checked BEFORE trusting, the two-sided
    # gate's own statistical verdict: a breach means at least one tick's
    # process-owned-RNG consumption exceeded the independently-recorded
    # real MATLAB draw count for that tick -- i.e. OC computed more
    # candidate events than the real historical run needed, a genuine
    # state/candidate divergence that can be statistically invisible in
    # the pooled projection tensor (see STATUS_L22_DNAS_SEPT2.md's
    # "projection-silent" characterization) while still being real.
    audit_boundary_ok = len(audit_boundary_breaches) == 0
    process_verdict = str(evaluation["process_verdict"])
    if not audit_boundary_ok:
        process_verdict = "FAIL_AUDIT_BOUNDARY_BREACH_NOT_ROOT_CAUSED"

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "process": PROCESS,
        "rule": "two_sided_sparse_gate",
        "trace_root": str(trace_root),
        "base_checkpoint_path": str(base_checkpoint_path),
        "checkpoint_path": str(checkpoint_path),
        "shape": list(oc_tensor.shape),
        "component_scales": loaded["component_scales"],
        "preregistration_examples": preregistration_examples(),
        "primary_evaluation": evaluation,
        "process_rng_audit_boundary": {
            "ledger_covered_tick_count": int(ledger_covered_tick_count),
            "breach_count": len(audit_boundary_breaches),
            "audit_boundary_ok": bool(audit_boundary_ok),
            "breaches": audit_boundary_breaches,
            "under_consumption_count": len(audit_boundary_under_consumption),
            "under_consumption": audit_boundary_under_consumption,
        },
        "process_verdict": process_verdict,
    }
    result_path = out_dir / "two_sided_gate_evaluation.json"
    result_path.write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    print(f"[l22_dnas_sept2_two_sided_n200_eval] wrote {checkpoint_path}")
    print(f"[l22_dnas_sept2_two_sided_n200_eval] wrote {result_path}")
    print(
        "[l22_dnas_sept2_two_sided_n200_eval] two-sided-gate verdict "
        f"{evaluation['process_verdict']} sparse={evaluation['delta_nnz_sparse_gate']['verdict']}"
    )
    print(
        "[l22_dnas_sept2_two_sided_n200_eval] process-RNG audit boundary: "
        f"{len(audit_boundary_breaches)} breach(es) across "
        f"{ledger_covered_tick_count} ledger-covered ticks"
    )
    print(
        "[l22_dnas_sept2_two_sided_n200_eval] process-RNG under-consumption "
        f"(audited, non-fatal): {len(audit_boundary_under_consumption)} tick(s)"
    )
    print(f"[l22_dnas_sept2_two_sided_n200_eval] FINAL process_verdict: {process_verdict}")
    if not audit_boundary_ok:
        print(
            "[l22_dnas_sept2_two_sided_n200_eval] FAIL-CLOSED: nonzero audit-boundary "
            "breaches are not disclosed-and-ignored -- this run is NOT a valid PASS "
            "regardless of the two-sided gate's own verdict. Root-cause and close all "
            "breaches, then rerun.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
