"""Inspect ReplicationInitiation trace structure and complexs shape."""
import h5py
import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/ReplicationInitiation_100ticks.mat"
print(f"Path: {path.name}, exists: {path.exists()}, size: {path.stat().st_size / 1024:.0f} KB")

with h5py.File(path, "r") as h:
    print(f"Top keys: {list(h.keys())}")
    print(f"states_before keys: {list(h['states_before'].keys())}")
    print(f"states_after keys: {list(h['states_after'].keys())}")
    n_ticks = int(np.asarray(h["metadata/n_ticks"][()]).reshape(-1)[0])
    print(f"n_ticks: {n_ticks}")
    
    for ch in h["states_before"].keys():
        ds = h[f"states_before/{ch}"]
        print(f"\n  states_before/{ch}: shape={ds.shape} dtype={ds.dtype}")
        # Sample tick 0
        ref = ds[0, 0] if ds.shape[0] == 1 else ds[0, 0]
        item = h[ref]
        if hasattr(item, "shape"):
            print(f"    tick 0 item: shape={item.shape} dtype={item.dtype}, sum_abs={np.abs(np.asarray(item)).sum():.0f}, nz={int(np.count_nonzero(np.asarray(item)))}")
        else:
            # It's a group (e.g. chromosome)
            print(f"    tick 0 item: group with keys={list(item.keys())[:10]}")
