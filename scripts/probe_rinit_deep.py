"""Deeper RI inspection: where do complexs live in the trace?

Catalog says primary_channel=complexs, but trace top-level only has
[substrates, enzymes, boundEnzymes, chromosome]. Looking for where
DnaA complex counts live.
"""
import h5py
import numpy as np
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/ReplicationInitiation_100ticks.mat"

with h5py.File(path, "r") as h:
    # Look at chromosome - maybe complexs live there as a custom field
    chrom_ds = h["states_before/chromosome"]
    ref = chrom_ds[0, 0]
    chrom_group = h[ref]
    print(f"Chromosome group keys: {sorted(chrom_group.keys())}")
    
    # Check if there's a 'dnaa_complex_count' or similar
    for k in chrom_group.keys():
        try:
            v = chrom_group[k]
            if hasattr(v, "shape"):
                print(f"  {k}: shape={v.shape} dtype={v.dtype}")
            else:
                # Group
                print(f"  {k}: group, keys={list(v.keys())[:5]}")
        except Exception as e:
            print(f"  {k}: error {e}")
    
    # Check enzymes evolution - does boundEnzymes change much over ticks?
    print("\n--- boundEnzymes evolution (seed 0) ---")
    boundE_ds = h["states_before/boundEnzymes"]
    for t in [0, 25, 50, 75, 99]:
        ref = boundE_ds[0, t]
        arr = np.asarray(h[ref][()], dtype=np.float64).ravel()
        print(f"  tick {t}: shape={arr.shape}, sum={arr.sum():.0f}, nz={int(np.count_nonzero(arr))}, values={arr[arr > 0]}")
    
    # Check enzymes evolution too
    print("\n--- enzymes evolution (seed 0) ---")
    enz_ds = h["states_before/enzymes"]
    for t in [0, 25, 50, 75, 99]:
        ref = enz_ds[0, t]
        arr = np.asarray(h[ref][()], dtype=np.float64).ravel()
        print(f"  tick {t}: shape={arr.shape}, sum={arr.sum():.0f}, nz={int(np.count_nonzero(arr))}, values={arr[arr > 0]}")
