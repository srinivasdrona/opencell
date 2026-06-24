"""Inspect Metabolism_init.mat — it may have growth recorded at init."""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent

with h5py.File(REPO / "data/m1_sources/karr_native/initial_states/Metabolism_init.mat", "r") as h:
    print("Top:", list(h.keys()))

    def walk(g, depth=0):
        for k in g.keys():
            v = g[k]
            prefix = "  " * depth + k
            if hasattr(v, "keys"):
                print(f"{prefix}/")
                walk(v, depth + 1)
            else:
                try:
                    print(f"{prefix}: shape={v.shape} dtype={v.dtype}")
                except Exception as e:
                    print(f"{prefix}: ? {e}")

    if "init_state" in h:
        print("\n=== init_state ===")
        walk(h["init_state"])
    if "metadata" in h:
        print("\n=== metadata ===")
        walk(h["metadata"])
