"""Verify: is the trace's tick-0 pre-state the SAME as the fitted snapshot?

If they differ significantly, my 'ground truth' flux extraction was at the
wrong state, and the 74% 'solver basis' breakdown is conflated.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent

# Fitted snapshot from my MATLAB extraction
GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metabolism_matlab_flux_growth.mat"
with h5py.File(GT_PATH, "r") as h:
    snapshot_substrates = np.asarray(h["snapshot_substrates"][()], dtype=np.float64)

# Trace's tick-0 pre-state
trace_path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    ds = h["states_before/substrates"]
    ref = ds[0, 0]
    trace_before = np.asarray(h[ref][()], dtype=np.float64)

print(f"Fitted snapshot substrates shape: {snapshot_substrates.shape}")
print(f"Trace tick-0 pre-state shape:    {trace_before.shape}")

# Always transpose to (585, 3)
if snapshot_substrates.shape == (3, 585):
    snapshot_substrates = snapshot_substrates.T
if trace_before.shape == (3, 585):
    trace_before_585x3 = trace_before.T
else:
    trace_before_585x3 = trace_before

print(f"After align: snapshot={snapshot_substrates.shape}, trace={trace_before_585x3.shape}")

# Sum-abs comparison
print(f"\nFitted snapshot sum_abs: {np.abs(snapshot_substrates).sum():.4e}")
print(f"Trace tick-0 pre  sum_abs: {np.abs(trace_before_585x3).sum():.4e}")

# Try to align by checking if shapes match after row-wise comparison
if snapshot_substrates.shape == trace_before_585x3.shape:
    diff = snapshot_substrates - trace_before_585x3
    print(f"\nDiff (snapshot - trace_before):")
    print(f"  Max abs diff: {np.abs(diff).max():.4e}")
    print(f"  Mean abs diff: {np.abs(diff).mean():.4e}")
    print(f"  Cells with |diff| > 1: {int((np.abs(diff) > 1).sum())} / {diff.size}")
    print(f"  Cells with |diff| > 100: {int((np.abs(diff) > 100).sum())}")
    print(f"  Cells with |diff| > 10000: {int((np.abs(diff) > 10000).sum())}")
    
    if np.abs(diff).max() > 100:
        # Find top divergences
        from opencell.m1 import karr_metabolism as km
        sys.path.insert(0, str(REPO))
        model = km.load_default()
        sub_ids = list(model.raw["ids"]["substrate_wcm_585"])
        
        print(f"\nTop 15 row-substrate diffs (across all compartments):")
        per_wid_diff = np.abs(diff).sum(axis=1)
        worst = np.argsort(-per_wid_diff)[:15]
        for r in worst:
            print(f"  {sub_ids[r]:18s}: snapshot={snapshot_substrates[r,:].sum():.0f}, "
                  f"trace_before={trace_before_585x3[r,:].sum():.0f}, "
                  f"diff={diff[r,:].sum():.0f}")

# Also check enzymes
GT_PATH_DIR = REPO / "data/karr_fixtures/matlab_ground_truth"
with h5py.File(GT_PATH, "r") as h:
    snapshot_enzymes = np.asarray(h["snapshot_enzymes"][()], dtype=np.float64).ravel()

with h5py.File(trace_path, "r") as h:
    enz_ds = h["states_before/enzymes"]
    enz_ref = enz_ds[0, 0]
    trace_enz_before = np.asarray(h[enz_ref][()], dtype=np.float64).ravel()

print(f"\n=== Enzymes comparison ===")
print(f"Fitted snapshot enzymes shape: {snapshot_enzymes.shape}, sum: {snapshot_enzymes.sum():.0f}, nonzero: {int(np.count_nonzero(snapshot_enzymes))}")
print(f"Trace tick-0 enzymes shape:   {trace_enz_before.shape}, sum: {trace_enz_before.sum():.0f}, nonzero: {int(np.count_nonzero(trace_enz_before))}")
if snapshot_enzymes.shape == trace_enz_before.shape:
    enz_diff = snapshot_enzymes - trace_enz_before
    print(f"Diff: max abs = {np.abs(enz_diff).max():.4e}, cells > 1: {int((np.abs(enz_diff) > 1).sum())}")
