"""Probe Metabolism fixture for what Karr substrate-update needs."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from scipy.io import loadmat

_REPO = Path(__file__).resolve().parent.parent
fix_path = _REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
print(f"Loading {fix_path}")
mat = loadmat(str(fix_path), squeeze_me=True, struct_as_record=False)
print(f"Top keys: {[k for k in mat.keys() if not k.startswith('_')]}")
data = mat.get("data")
if data is not None:
    fixture = getattr(data, "fixture", None)
    if fixture is not None:
        print(f"\nfixture attrs:")
        for attr in dir(fixture):
            if attr.startswith("_"):
                continue
            try:
                v = getattr(fixture, attr)
                if isinstance(v, np.ndarray):
                    print(f"  {attr}: shape={v.shape}, dtype={v.dtype}")
                else:
                    print(f"  {attr}: type={type(v).__name__}")
            except Exception as e:
                print(f"  {attr}: error {e}")
