"""L2.1 trace mutated-tick auditor.

For each Karr `<Process>_100ticks.mat` trace, count per-observable how many
of the 100 ticks have a nonzero `states_after - states_before` delta. Surfaces
the "1 real tick + 99 no-ops" pattern that inflated tRNAAA's L2.1 confidence.

Usage:
    python scripts/audit_l2_trace_mutation.py \\
        --trace data/m1_sources/karr_native/per_process_traces/tRNAAminoacylation_100ticks.mat

Or, default sweep across the 3-pilot set:
    python scripts/audit_l2_trace_mutation.py --pilot-sweep

No process construction; no test execution; static .mat read only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import h5py
import numpy as np


def _read_tick_vector(h5f: h5py.File, ref_dataset: h5py.Dataset, tick: int) -> np.ndarray:
    ref = ref_dataset[tick, 0]
    arr = np.asarray(h5f[ref])
    return arr.reshape(-1)


def audit_trace(trace_path: Path) -> dict:
    """Return a mutated-tick report for one trace."""
    report: dict = {
        "trace": str(trace_path),
        "observables": {},
    }
    with h5py.File(trace_path, "r") as h5f:
        if "states_before" not in h5f or "states_after" not in h5f:
            report["error"] = "missing states_before/states_after groups"
            return report
        before_group = h5f["states_before"]
        after_group = h5f["states_after"]
        obs_names = sorted(set(before_group.keys()) & set(after_group.keys()))
        n_ticks_attr = None
        for name in obs_names:
            before_ref = before_group[name]
            after_ref = after_group[name]
            if before_ref.shape != after_ref.shape:
                report["observables"][name] = {"error": "shape mismatch"}
                continue
            n_ticks = before_ref.shape[0]
            n_ticks_attr = n_ticks
            nonzero_ticks: list[int] = []
            total_abs_delta = 0.0
            max_abs_delta = 0.0
            sample_tick = None
            sample_diff = None
            for tick in range(n_ticks):
                before = _read_tick_vector(h5f, before_ref, tick)
                after = _read_tick_vector(h5f, after_ref, tick)
                if before.shape != after.shape:
                    nonzero_ticks.append(tick)
                    continue
                delta = after - before
                abs_delta = float(np.abs(delta).sum())
                if abs_delta > 0:
                    nonzero_ticks.append(tick)
                    total_abs_delta += abs_delta
                    tick_max = float(np.abs(delta).max())
                    if tick_max > max_abs_delta:
                        max_abs_delta = tick_max
                        sample_tick = tick
                        nz_idx = int(np.argmax(np.abs(delta)))
                        sample_diff = {
                            "tick": tick,
                            "idx": nz_idx,
                            "before": float(before[nz_idx]),
                            "after": float(after[nz_idx]),
                            "delta": float(delta[nz_idx]),
                        }
            report["observables"][name] = {
                "n_ticks": n_ticks,
                "nonzero_delta_ticks": len(nonzero_ticks),
                "first_5_nonzero_ticks": nonzero_ticks[:5],
                "total_abs_delta": total_abs_delta,
                "max_abs_delta": max_abs_delta,
                "largest_delta_sample": sample_diff,
            }
        report["n_ticks"] = n_ticks_attr
    return report


def _pilot_sweep_traces(repo_root: Path) -> list[Path]:
    base = repo_root / "data" / "m1_sources" / "karr_native" / "per_process_traces"
    return [
        base / "tRNAAminoacylation_100ticks.mat",
        base / "MacromolecularComplexation_100ticks.mat",
        base / "RNAModification_100ticks.mat",
    ]


def _all_traces(repo_root: Path) -> list[Path]:
    base = repo_root / "data" / "m1_sources" / "karr_native" / "per_process_traces"
    return sorted(base.glob("*_100ticks.mat"))


def _format_summary(report: dict) -> str:
    lines = []
    name = Path(report["trace"]).stem.replace("_100ticks", "")
    lines.append(f"\n=== {name} ===")
    if "error" in report:
        lines.append(f"ERROR: {report['error']}")
        return "\n".join(lines)
    n_ticks = report.get("n_ticks") or 0
    lines.append(f"observable                  nz_ticks  total_|delta|       max_|delta|   sample_diff")
    for obs, info in report["observables"].items():
        if "error" in info:
            lines.append(f"  {obs:25s}  ERROR: {info['error']}")
            continue
        nz = info["nonzero_delta_ticks"]
        total = info["total_abs_delta"]
        mx = info["max_abs_delta"]
        sample = info.get("largest_delta_sample")
        sample_str = (
            f"t={sample['tick']} idx={sample['idx']} {sample['before']:.0f}->{sample['after']:.0f} (Δ={sample['delta']:+g})"
            if sample else "none"
        )
        lines.append(f"  {obs:25s}  {nz:4d}/{n_ticks:<3d}  {total:14.0f}    {mx:12.0f}   {sample_str}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, help="Single .mat trace path")
    parser.add_argument("--pilot-sweep", action="store_true", help="Run all 3 pilot traces")
    parser.add_argument("--all", action="store_true", help="Run every *_100ticks.mat in the standard dir")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root for --pilot-sweep (default: parent of scripts/)",
    )
    args = parser.parse_args()

    if not args.trace and not args.pilot_sweep and not args.all:
        parser.error("--trace or --pilot-sweep or --all required")

    if args.trace:
        traces = [args.trace]
    elif args.all:
        traces = _all_traces(args.repo_root)
    else:
        traces = _pilot_sweep_traces(args.repo_root)
    reports = []
    for t in traces:
        if not t.exists():
            reports.append({"trace": str(t), "error": "trace not found"})
            continue
        reports.append(audit_trace(t))

    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for r in reports:
            print(_format_summary(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
