"""Phase E.1 dry run: chassis_v4 trajectory scaffold vs Karr reference.

Runs chassis_v4 for 1000 s, samples every 100 s, extracts scaffold observables,
compares against the first 1000 s of Karr's trajectory snapshots, and prints a
markdown table.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from opencell.analysis.cell_mass import compute_cell_mass
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.validation.karr_trajectory import load_karr_trajectory
from opencell.validation.trajectory_compare import compare_trajectories
from opencell.vivarium.karr_composite import build_karr_chassis_v4

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = ROOT / "docs" / "phase_e" / "E1_scaffold.md"


def _extract_observables_from_state(
    state: dict[str, Any],
    *,
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> dict[str, float]:
    mass = compute_cell_mass(state, m1_model, m2_model, m3_model)
    substrates = state.get("substrates", {})
    rna_counts = state.get("rna", {}).get("counts", {})
    protein_counts = state.get("protein", {}).get("counts", {})
    chromosome = state.get("chromosome", {})

    replication_label = str(chromosome.get("replication_state", "idle"))
    replication_code_map = {"idle": 0.0, "initiating": 1.0, "elongating": 2.0, "complete": 3.0}
    replication_state_code = replication_code_map.get(replication_label, 0.0)

    # Chassis_v4 does not carry explicit fork position yet.
    fork_position_norm = 0.0
    if isinstance(chromosome.get("fork_positions"), (tuple, list)):
        pos = np.asarray(chromosome["fork_positions"], dtype=np.float64).reshape(-1)
        if pos.size > 0:
            scale = max(float(np.max(np.abs(pos))), 1.0)
            fork_position_norm = float(np.clip(np.max(np.abs(pos)) / scale, 0.0, 1.0))

    dntp_pool_total = float(
        substrates.get("DATP", 0.0)
        + substrates.get("DCTP", 0.0)
        + substrates.get("DGTP", 0.0)
        + substrates.get("DTTP", 0.0)
    )

    return {
        "cell_dry_mass_g": float(mass.total_g),
        "replication_state_code": float(replication_state_code),
        "fork_position_norm": float(fork_position_norm),
        "mrna_total_count_estimate": float(sum(float(v) for v in rna_counts.values())),
        "protein_total_count_estimate": float(sum(float(v) for v in protein_counts.values())),
        "atp_pool": float(substrates.get("ATP", np.nan)),
        "gtp_pool": float(substrates.get("GTP", np.nan)),
        "dntp_pool_total": dntp_pool_total,
        "division_event_timestamp_s": float(np.nan),
    }


def run_opencell_trajectory(
    *,
    horizon_s: int,
    snapshot_interval_s: int,
) -> dict[str, Any]:
    m1_model = km.load_default()
    m2_model = tx.load_default()
    m3_model = tl.load_default()

    engine = build_karr_chassis_v4(
        m1_model=m1_model,
        m2_model=m2_model,
        m3_model=m3_model,
        time_step_s=1.0,
        emit_step_s=float(snapshot_interval_s),
    )

    times: list[float] = []
    obs_series: dict[str, list[float]] = {}

    n_steps = int(horizon_s // snapshot_interval_s)
    for i in range(n_steps):
        engine.update(float(snapshot_interval_s))
        t = float((i + 1) * snapshot_interval_s)
        times.append(t)

        state = engine.state.get_value()
        obs = _extract_observables_from_state(
            state,
            m1_model=m1_model,
            m2_model=m2_model,
            m3_model=m3_model,
        )
        for key, value in obs.items():
            obs_series.setdefault(key, []).append(value)

    return {
        "time_s": np.asarray(times, dtype=np.float64),
        "observables": {k: np.asarray(v, dtype=np.float64) for k, v in obs_series.items()},
        "phenotypes": {},
    }


def _fmt(x: float) -> str:
    if not np.isfinite(x):
        return "NaN"
    ax = abs(x)
    if ax == 0.0:
        return "0"
    if ax >= 1e4 or ax < 1e-3:
        return f"{x:.4e}"
    return f"{x:.4f}"


def _build_markdown_report(
    *,
    horizon_s: int,
    snapshot_interval_s: int,
    opencell_trajectory: dict[str, Any],
    karr_trajectory: dict[str, Any],
    compare_result: dict[str, Any],
) -> str:
    lines: list[str] = []
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines.append("# Phase E.1 Scaffold — chassis_v4 vs Karr (first 1000 s)")
    lines.append("")
    lines.append(f"- Generated: `{generated_at}`")
    lines.append(f"- Horizon: `{horizon_s}` s")
    lines.append(f"- Snapshot interval: `{snapshot_interval_s}` s")
    lines.append(
        "- Note: large mismatches are expected in this scaffold stage (chassis_v4 is partial vs full Karr WCM)."
    )
    lines.append("")
    lines.append("| observable | opencell_value | karr_value | rel_err | status |")
    lines.append("|---|---:|---:|---:|---|")

    op_obs = opencell_trajectory["observables"]
    karr_obs = karr_trajectory["observables"]
    for observable in compare_result["shared_observables"]:
        op_val = float(op_obs[observable][-1])
        karr_val = float(karr_obs[observable][-1])
        err = compare_result["observable_errors"].get(observable, {})
        rel_err = float(err.get("l_inf_rel", np.nan))
        rel_tol = float(err.get("rel_tol", np.nan))
        status = "PASS" if np.isfinite(rel_err) and np.isfinite(rel_tol) and rel_err < rel_tol else "FAIL"
        lines.append(
            f"| `{observable}` | {_fmt(op_val)} | {_fmt(karr_val)} | {_fmt(rel_err)} | {status} |"
        )

    lines.append("")
    lines.append("## Diff Summary")
    lines.append("")
    lines.append("```text")
    lines.append(compare_result["summary"])
    lines.append("```")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon-s", type=int, default=1000)
    parser.add_argument("--snapshot-interval-s", type=int, default=100)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    karr_trajectory = load_karr_trajectory(max_time_s=float(args.horizon_s))
    opencell_trajectory = run_opencell_trajectory(
        horizon_s=args.horizon_s,
        snapshot_interval_s=args.snapshot_interval_s,
    )
    compare_result = compare_trajectories(opencell_trajectory, karr_trajectory)

    report = _build_markdown_report(
        horizon_s=args.horizon_s,
        snapshot_interval_s=args.snapshot_interval_s,
        opencell_trajectory=opencell_trajectory,
        karr_trajectory=karr_trajectory,
        compare_result=compare_result,
    )
    print(report)

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
