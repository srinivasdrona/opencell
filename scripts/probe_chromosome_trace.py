"""Probe: are chromosome sparse triples loadable from the DNASupercoiling trace?

This is the cheap test before building runner infrastructure. If the traces have
real chromosome sparse data, the wiring effort is justified. If they're
placeholder strings, we have a different problem first.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet, CHROMOSOME_FIELDS

trace_path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/DNASupercoiling_100ticks.mat"
print(f"Trace: {trace_path.name}")
print(f"  Exists: {trace_path.exists()}, size: {trace_path.stat().st_size / 1024:.0f} KB")

with h5py.File(trace_path, "r") as h:
    print(f"  Top keys: {list(h.keys())}")
    print(f"  states_before keys: {list(h['states_before'].keys())}")
    
    # Try loading tick-0 chromosome state via ChromosomeStore
    chrom_ds = h["states_before/chromosome"]
    print(f"  states_before/chromosome dataset shape: {chrom_ds.shape}, dtype: {chrom_ds.dtype}")
    ref = chrom_ds[0, 0] if chrom_ds.shape[0] == 1 else chrom_ds[0, 0]
    chrom_group = h[ref]
    print(f"  Tick 0 chromosome group keys: {list(chrom_group.keys())}")
    
    # Load via ChromosomeStore
    store_before = ChromosomeStore.from_hdf5_group(chrom_group)
    print(f"\n  Store fields loaded: {sorted(store_before._fields.keys())}")
    print(f"  Store shape: {store_before.shape}")
    
    for field_name in CHROMOSOME_FIELDS:
        if field_name in store_before._fields:
            triplet = store_before.get_field(field_name)
            n = len(triplet.positions)
            sum_val = float(np.sum(np.abs(triplet.values))) if n > 0 else 0.0
            print(f"    {field_name}: nnz={n}, sum_abs={sum_val:.1f}, shape={triplet.shape}")

    # Load tick-0 AFTER
    chrom_ds_after = h["states_after/chromosome"]
    ref_after = chrom_ds_after[0, 0] if chrom_ds_after.shape[0] == 1 else chrom_ds_after[0, 0]
    store_after = ChromosomeStore.from_hdf5_group(h[ref_after])
    
    # Compute linkingNumbers delta
    lb = store_before.get_field("linkingNumbers")
    la = store_after.get_field("linkingNumbers")
    print(f"\n  linkingNumbers BEFORE: nnz={len(lb.positions)}, sum_val={lb.values.sum():.1f}")
    print(f"  linkingNumbers AFTER:  nnz={len(la.positions)}, sum_val={la.values.sum():.1f}")
    print(f"  linkingNumbers delta_value_sum: {(la.values.sum() - lb.values.sum()):.1f}")
    print(f"  linkingNumbers delta_nnz:       {len(la.positions) - len(lb.positions)}")
    
    # Spot-check tick 50 too
    ref50 = chrom_ds[0, 50] if chrom_ds.shape[0] == 1 else chrom_ds[50, 0]
    store50 = ChromosomeStore.from_hdf5_group(h[ref50])
    ln50 = store50.get_field("linkingNumbers")
    print(f"\n  Tick 50 linkingNumbers BEFORE: nnz={len(ln50.positions)}, sum_val={ln50.values.sum():.1f}")
