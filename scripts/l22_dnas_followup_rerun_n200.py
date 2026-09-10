"""Recompute the frozen DNAS N=200 gate after the source-faithful sigma fix.

Streams the frozen sibling seed traces one seed at a time, recomputes the OC
chromosome projection tensor with the current worktree's DNASupercoiling code,
and evaluates the unchanged prereg gate against the same frozen Karr tensor.
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
from scripts.l22_dnas_rare_event.sparse_gate import evaluate_process, sensitivity_evaluations  # noqa: E402

PROCESS = "DNASupercoiling"
DEFAULT_TRACE_ROOT = Path(
    "E:/opencell-worktrees/l22-dnas-closure-20260805/data/m1_sources/karr_native"
)
DEFAULT_BASE_CHECKPOINT = Path(
    "E:/opencell-worktrees/l22-dnas-closure-20260805/"
    "docs/phase_f/l2_2_design_a/evidence_bundle/DNASupercoiling/"
    "diagnostic_n200/raw_captured_tensors_checkpoint.npz"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "evidence_bundle"
    / "DNASupercoiling"
    / "diagnostic_n200_followup"
    / "post_sigma_fix_rerun"
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
        print(f"[l22_dnas_followup_rerun_n200] seed {seed:03d}/{n_seeds - 1:03d} complete")

    checkpoint_path = out_dir / "raw_captured_tensors_checkpoint.npz"
    np.savez(
        checkpoint_path,
        oc_tensor=oc_tensor,
        karr_tensor=karr_tensor,
        component_scales=loaded["component_scales"],
    )

    evaluation = evaluate_process(oc_tensor, karr_tensor, loaded["component_scales"])
    sensitivity = sensitivity_evaluations(oc_tensor, karr_tensor, loaded["component_scales"])
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "process": PROCESS,
        "trace_root": str(trace_root),
        "base_checkpoint_path": str(base_checkpoint_path),
        "checkpoint_path": str(checkpoint_path),
        "shape": list(oc_tensor.shape),
        "component_scales": loaded["component_scales"],
        "primary_evaluation": evaluation,
        "sensitivity": sensitivity,
    }
    result_path = out_dir / "sparse_gate_evaluation.json"
    result_path.write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    print(f"[l22_dnas_followup_rerun_n200] wrote {checkpoint_path}")
    print(f"[l22_dnas_followup_rerun_n200] wrote {result_path}")
    print(
        "[l22_dnas_followup_rerun_n200] final verdict "
        f"{evaluation['process_verdict']} sparse={evaluation['delta_nnz_sparse_gate']['verdict']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
