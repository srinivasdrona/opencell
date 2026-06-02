"""Inspect per_process_replay npz fixtures + flat .mat per-process refs."""
import numpy as np
from pathlib import Path
import json

base = Path("data/karr_fixtures/per_process_replay")
print("=== per_process_replay (decoded fixtures) ===")
for npz in sorted(base.glob("*.npz")):
    arr = np.load(npz, allow_pickle=True)
    print(f"\n--- {npz.name} ---")
    for k in arr.files:
        v = arr[k]
        try:
            print(f"  {k}: shape={v.shape} dtype={v.dtype}")
        except Exception:
            print(f"  {k}: {type(v).__name__}")
    js = npz.with_suffix(".json")
    if js.exists():
        print("  meta:", json.dumps(json.loads(js.read_text()), indent=2)[:400])

print("\n\n=== per_process flat.mat (v7, scipy-loadable) ===")
from scipy.io import loadmat
flat_dir = Path("data/karr_fixtures/per_process")
samples = ["Metabolism_flat.mat", "Transcription_flat.mat", "Translation_flat.mat"]
for s in samples:
    p = flat_dir / s
    if not p.exists():
        continue
    try:
        m = loadmat(p, squeeze_me=True, struct_as_record=False)
        print(f"\n--- {s} ---")
        for k, v in m.items():
            if k.startswith("__"):
                continue
            if hasattr(v, "shape") and getattr(v, "dtype", None) is not None:
                print(f"  {k}: shape={v.shape} dtype={v.dtype}")
            else:
                print(f"  {k}: {type(v).__name__}")
    except Exception as e:
        print(f"  {s}: load fail: {e}")
