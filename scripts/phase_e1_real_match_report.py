"""Generate Phase E.1 real-match report from v6 + Karr trajectory fixtures."""

from __future__ import annotations

import argparse
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from opencell.validation.karr_trajectory import load_karr_trajectory
from opencell.validation.trajectory_compare import (
    SCAFFOLD_OBSERVABLES,
    compare_full_trajectory,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V6_PICKLE = ROOT / "data" / "phase_e" / "v6_trajectory_32400s.pkl"
DEFAULT_KARR_PICKLE = ROOT / "data" / "phase_e" / "karr_trajectory_full.pkl"
DEFAULT_REPORT = ROOT / "docs" / "phase_e" / "E1_real_match.md"


def _fmt(value: float) -> str:
    if not np.isfinite(value):
        return "NaN"
    mag = abs(value)
    if mag == 0.0:
        return "0"
    if mag >= 1e4 or mag < 1e-3:
        return f"{value:.4e}"
    return f"{value:.6f}"


def _load_pickle(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return pickle.load(f)


def _load_or_cache_karr_pickle(path: Path) -> dict[str, Any]:
    if path.exists():
        return _load_pickle(path)
    traj = load_karr_trajectory()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(traj, f)
    return traj


def _v6_observables(v6_fixture: dict[str, Any]) -> dict[str, np.ndarray]:
    out: dict[str, list[float]] = {obs: [] for obs in SCAFFOLD_OBSERVABLES}
    for snap in v6_fixture.get("snapshots", []):
        state = snap.get("state", {})
        if not isinstance(state, dict):
            continue
        for obs in SCAFFOLD_OBSERVABLES:
            out[obs].append(float(state.get(obs, np.nan)))
    return {obs: np.asarray(vals, dtype=np.float64) for obs, vals in out.items()}


def _worst_rows_for_observable(
    observable: str,
    *,
    op_values: np.ndarray,
    karr_values: np.ndarray,
    op_ticks: np.ndarray,
    karr_ticks: np.ndarray,
    n_top: int = 10,
) -> list[dict[str, float]]:
    n = min(op_values.size, karr_values.size, op_ticks.size, karr_ticks.size)
    if n <= 0:
        return []

    op = op_values[:n]
    kr = karr_values[:n]
    valid = np.isfinite(op) & np.isfinite(kr)
    if not np.any(valid):
        return []

    idx = np.arange(n)[valid]
    abs_err = np.abs(op[valid] - kr[valid])
    rel_err = abs_err / np.maximum(np.abs(kr[valid]), 1e-12)
    order = np.argsort(-rel_err)

    rows: list[dict[str, float]] = []
    for rank_idx in order[:n_top]:
        i = int(idx[rank_idx])
        rows.append(
            {
                "observable": observable,
                "snapshot_index": float(i),
                "op_tick": float(op_ticks[i]),
                "karr_tick": float(karr_ticks[i]),
                "op_value": float(op[i]),
                "karr_value": float(kr[i]),
                "abs_err": float(abs_err[rank_idx]),
                "rel_err": float(rel_err[rank_idx]),
            }
        )
    return rows


def build_report(
    *,
    v6_fixture: dict[str, Any],
    karr_trajectory: dict[str, Any],
    compare_result: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = []
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    passing = sum(1 for metrics in compare_result.values() if metrics["status"] == "PASS")

    lines.append("# Phase E.1 Real-Match — chassis_v6 vs Karr full trajectory")
    lines.append("")
    lines.append(f"- Generated: `{now}`")
    lines.append(f"- Chassis: `{v6_fixture.get('chassis', 'unknown')}`")
    lines.append(f"- Schema version: `{v6_fixture.get('schema_version', 'unknown')}`")
    lines.append(f"- Wall time (s): `{_fmt(float(v6_fixture.get('wall_time_s', np.nan)))}`")
    lines.append(f"- Ticks completed: `{int(v6_fixture.get('ticks_completed', 0))}`")
    lines.append(f"- Division detected: `{bool(v6_fixture.get('division_detected', False))}`")
    lines.append(f"- Passing observables: `{passing}/{len(SCAFFOLD_OBSERVABLES)}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| observable | L_inf_rel | L2_rel | n_snapshots | status |")
    lines.append("|---|---:|---:|---:|---|")
    for observable in SCAFFOLD_OBSERVABLES:
        metrics = compare_result.get(observable, {})
        lines.append(
            f"| `{observable}` | {_fmt(float(metrics.get('L_inf_rel', np.nan)))}"
            f" | {_fmt(float(metrics.get('L2_rel', np.nan)))}"
            f" | {int(metrics.get('n_snapshots_compared', 0))}"
            f" | {metrics.get('status', 'UNKNOWN')} |"
        )

    v6_obs = _v6_observables(v6_fixture)
    karr_obs = {k: np.asarray(v, dtype=np.float64) for k, v in karr_trajectory.get("observables", {}).items()}
    op_ticks = np.asarray([float(s.get("tick", np.nan)) for s in v6_fixture.get("snapshots", [])], dtype=np.float64)
    karr_ticks = np.asarray(karr_trajectory.get("tick", []), dtype=np.float64)

    lines.append("")
    lines.append("## Top 10 Worst Snapshots Per Observable")
    lines.append("")

    for observable in SCAFFOLD_OBSERVABLES:
        lines.append(f"### `{observable}`")
        status = compare_result.get(observable, {}).get("status", "UNKNOWN")
        if status in {"MISSING_KARR", "MISSING_OPENCELL"}:
            lines.append("")
            lines.append(f"No comparison rows (`{status}`).")
            lines.append("")
            continue

        rows = _worst_rows_for_observable(
            observable,
            op_values=v6_obs.get(observable, np.asarray([], dtype=np.float64)),
            karr_values=karr_obs.get(observable, np.asarray([], dtype=np.float64)),
            op_ticks=op_ticks,
            karr_ticks=karr_ticks,
            n_top=10,
        )
        lines.append("")
        lines.append("| rank | snapshot_index | op_tick | karr_tick | opencell | karr | abs_err | rel_err |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
        if not rows:
            lines.append("| 1 | NaN | NaN | NaN | NaN | NaN | NaN | NaN |")
            lines.append("")
            continue
        for rank, row in enumerate(rows, start=1):
            lines.append(
                f"| {rank}"
                f" | {_fmt(row['snapshot_index'])}"
                f" | {_fmt(row['op_tick'])}"
                f" | {_fmt(row['karr_tick'])}"
                f" | {_fmt(row['op_value'])}"
                f" | {_fmt(row['karr_value'])}"
                f" | {_fmt(row['abs_err'])}"
                f" | {_fmt(row['rel_err'])} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v6-pickle", type=Path, default=DEFAULT_V6_PICKLE)
    parser.add_argument("--karr-pickle", type=Path, default=DEFAULT_KARR_PICKLE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    v6_fixture = _load_pickle(args.v6_pickle)
    karr_trajectory = _load_or_cache_karr_pickle(args.karr_pickle)
    compare_result = compare_full_trajectory(v6_fixture, karr_trajectory)

    report = build_report(
        v6_fixture=v6_fixture,
        karr_trajectory=karr_trajectory,
        compare_result=compare_result,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    passing = sum(1 for metrics in compare_result.values() if metrics["status"] == "PASS")
    print(
        "phase_e1_real_match_report:"
        f" passing={passing}/{len(SCAFFOLD_OBSERVABLES)}"
        f" report={args.report}"
    )


if __name__ == "__main__":
    main()
