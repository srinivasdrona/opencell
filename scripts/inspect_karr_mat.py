"""Quick: inspect Karr per-process .mat structure."""
import sys
from pathlib import Path
import h5py
import numpy as np

def _walk(g, prefix="", depth=0, max_depth=4):
    for k in g.keys():
        node = g[k]
        path = f"{prefix}/{k}"
        if isinstance(node, h5py.Group):
            print("  " * depth + f"[G] {path}")
            if depth < max_depth:
                _walk(node, path, depth + 1, max_depth)
        else:
            try:
                arr = node[()]
                shape = getattr(arr, "shape", None)
                dtype = getattr(arr, "dtype", type(arr).__name__)
                samp = ""
                if isinstance(arr, np.ndarray) and arr.dtype.kind in "fiub" and arr.size:
                    samp = f" sample={arr.ravel()[:3].tolist()}"
                print("  " * depth + f"[D] {path}: shape={shape} dtype={dtype}{samp}")
            except Exception as e:
                print("  " * depth + f"[D] {path}: !read fail: {e}")

def inspect(p):
    print(f"\n=== {Path(p).name} ===")
    with h5py.File(p, "r") as f:
        _walk(f)

if __name__ == "__main__":
    base = Path("/mnt/e/opencell/data/m1_sources/karr_native/per_process_traces")
    targets = sys.argv[1:] or [
        "Metabolism_100ticks.mat",
        "ProteinTranslocation_100ticks.mat",
        "tRNAAminoacylation_100ticks.mat",
        "DNARepair_100ticks.mat",
        "FtsZPolymerization_100ticks.mat",
    ]
    for t in targets:
        inspect(base / t)
