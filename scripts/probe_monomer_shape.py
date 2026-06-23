"""Probe Translation vs ProteinTranslocation oracle monomer shapes."""
from __future__ import annotations
import sys
from pathlib import Path

import h5py
import numpy as np

_REPO = Path(__file__).resolve().parent.parent

for proc in ("Translation", "ProteinTranslocation"):
    trace_path = _REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / f"{proc}_100ticks.mat"
    if not trace_path.exists():
        trace_path = _REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / f"{proc}_100ticks.mat"
    print(f"\n=== {proc}: {trace_path.exists()} ===")
    if not trace_path.exists():
        continue
    with h5py.File(trace_path, "r") as handle:
        sb = handle["states_before"]
        print(f"  states_before keys: {list(sb.keys())}")
        if "monomers" in sb:
            ds = sb["monomers"]
            print(f"  monomers dataset shape: {ds.shape}, dtype: {ds.dtype}")
            # First tick reference
            ref = ds[0, 0] if ds.shape[0] == 1 else ds[0, 0]
            data = np.asarray(handle[ref][()], dtype=np.float64)
            print(f"  monomers[0, 0] shape: {data.shape}")
            print(f"  flat size: {data.size}, sum: {data.sum()}")
