"""Smoke-check that Metabolism trace is not vacuous."""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np


def _read_cell_vector(h5f: h5py.File, ref_ds: h5py.Dataset, tick: int) -> np.ndarray:
    if ref_ds.shape[0] == 1:
        ref = ref_ds[0, tick]
    else:
        ref = ref_ds[tick, 0]
    return np.asarray(h5f[ref]).reshape(-1)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    trace = repo_root / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / "Metabolism_100ticks.mat"
    if not trace.exists():
        print(f"ERROR: trace not found: {trace}")
        return 1

    with h5py.File(trace, "r") as h5f:
        before = h5f["states_before"]["substrates"]
        after = h5f["states_after"]["substrates"]
        if before.shape != after.shape:
            print(f"ERROR: shape mismatch: before={before.shape} after={after.shape}")
            return 1

        n_ticks = max(before.shape[0], before.shape[1])
        per_tick_abs = []
        for tick in range(n_ticks):
            b = _read_cell_vector(h5f, before, tick)
            a = _read_cell_vector(h5f, after, tick)
            if a.shape != b.shape:
                print(f"ERROR: tick {tick} shape mismatch: before={b.shape} after={a.shape}")
                return 1
            per_tick_abs.append(float(np.abs(a - b).sum()))

    nonzero_ticks = sum(val > 0 for val in per_tick_abs)
    for tick, val in enumerate(per_tick_abs):
        print(f"tick {tick:03d}: |delta|={val:.0f}")
    print(f"nonzero ticks: {nonzero_ticks}/{len(per_tick_abs)}")

    if nonzero_ticks < 10:
        print("FAIL: fewer than 10 ticks have nonzero substrate delta.")
        return 1

    print("PASS: metabolism substrate activity check satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
