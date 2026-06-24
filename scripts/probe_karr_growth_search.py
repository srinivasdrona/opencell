"""Find Karr's recorded tick-0 growth_per_s.

Search:
  1. data/m1_sources/karr_native/initial_states/Metabolism_init.mat
  2. data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat (already checked: no growth)
  3. Any other Karr-native artifact that might have metabolicReaction.growth
"""
import sys
from pathlib import Path
import numpy as np
import h5py
from scipy.io import loadmat

REPO = Path(__file__).resolve().parent.parent

candidates = [
    REPO / "data/m1_sources/karr_native/initial_states/Metabolism_init.mat",
    REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat",
]

# Also search for any .mat with 'growth' anywhere
print("=== Scanning .mat files for 'growth' or 'metabolicReaction' ===")
mat_files = list(REPO.glob("data/m1_sources/karr_native/**/*.mat"))[:200]
print(f"Total .mat files: {len(list(REPO.glob('data/m1_sources/karr_native/**/*.mat')))}")

# Quick check each candidate
for p in candidates:
    if not p.exists():
        print(f"{p.name}: NOT FOUND")
        continue
    print(f"\n--- {p.relative_to(REPO)} ---")
    # Try v7.3 first (h5py)
    try:
        with h5py.File(p, "r") as h:
            print(f"  v7.3 HDF5; top-level keys: {list(h.keys())}")
            # Walk for growth
            def walk(g, path=""):
                for k in g.keys():
                    v = g[k]
                    full = f"{path}/{k}"
                    if hasattr(v, "keys"):
                        walk(v, full)
                    else:
                        if "growth" in full.lower() or "metabolicreaction" in full.lower() or "fluxs" in full.lower():
                            try:
                                print(f"  {full}: shape={v.shape} dtype={v.dtype}")
                            except Exception:
                                print(f"  {full}: opaque")
            walk(h)
    except OSError:
        # v5 format
        try:
            m = loadmat(str(p), squeeze_me=True, struct_as_record=False)
            for k, v in m.items():
                if k.startswith("_"):
                    continue
                print(f"  v5 key: {k} type={type(v).__name__}")
                if hasattr(v, "_fieldnames"):
                    for f in v._fieldnames:
                        if "growth" in f.lower() or "metabolicreaction" in f.lower():
                            val = getattr(v, f)
                            print(f"    {f}: {repr(val)[:200]}")
                    # also nested data.fixture
                    if hasattr(v, "fixture"):
                        fix = v.fixture
                        if hasattr(fix, "_fieldnames"):
                            for ff in fix._fieldnames:
                                if "growth" in ff.lower() or "metabolicreaction" in ff.lower() or "biomass" in ff.lower():
                                    val = getattr(fix, ff)
                                    print(f"    fixture.{ff}: {repr(val)[:200]}")
        except Exception as e:
            print(f"  ERROR: {e}")

print("\n=== Search any file with 'metabolicReaction' or growth key ===")
hits = []
for p in mat_files:
    try:
        with h5py.File(p, "r") as h:
            def find(g, path=""):
                for k in g.keys():
                    full = f"{path}/{k}"
                    if "growth" in full.lower() or "metabolicReaction" in full or "metabolic_reaction" in full.lower():
                        hits.append((str(p.relative_to(REPO)), full))
                        return
                    v = g[k]
                    if hasattr(v, "keys"):
                        find(v, full)
            find(h)
    except (OSError, KeyError):
        pass
    if len(hits) >= 10:
        break
print(f"Hits ({len(hits)}):")
for h in hits[:15]:
    print(f"  {h[0]}: {h[1]}")
