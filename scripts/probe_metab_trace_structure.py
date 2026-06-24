"""Inspect the Metabolism trace structure to find the right keys."""
import h5py
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
if not trace_path.exists():
    trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / "Metabolism_100ticks.mat"
print(f"Path: {trace_path}")

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

with h5py.File(trace_path, "r") as h:
    print("\nTop-level keys:", list(h.keys()))
    for top in h.keys():
        if isinstance(h[top], h5py.Group):
            print(f"\n=== {top} ===")
            walk(h[top])
