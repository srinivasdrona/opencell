"""Trace dipeptide & lipid pathways: which reactions OC uses that Karr doesn't.

For each problem-WID cluster, identify:
  1. FBA substrate row index in the 376-row S matrix
  2. Reactions where this WID is a product (S[wid_row, rxn] > 0) or reactant (< 0)
  3. OC flux vs Karr flux on those reactions at sample (0,1)
  4. Reaction bounds (lb, ub)

Goal: find specific reactions where OC has |flux| > 1e3 and Karr has |flux| ~ 0,
or vice versa. These are the "alternative pathway" picks.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"

with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T

model = km.load_default()
v_oc, _info = km.solve_fba(
    model, use_full_objective=True, sense="max", big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
    solver="glpk",
)

S = model.S  # (376, 504)
print(f"S matrix shape: {S.shape}")

# Find the FBA substrate row map. The 376 rows index into a subset of 585 substrates.
# Let me dig into raw to find it
raw = model.raw
print(f"\nModel.raw keys: {list(raw.keys())}")
print(f"Substrate count: {raw['counts']}")

# Inspect the npz directly
npz_path = REPO / raw["matrix_npz"]
print(f"NPZ path: {npz_path}")
with np.load(npz_path) as data:
    print(f"NPZ keys: {list(data.keys())}")
    if "fba_substrate_idx_to_substrate_wcm" in data.keys():
        m = data["fba_substrate_idx_to_substrate_wcm"]
        print(f"fba_substrate_idx_to_substrate_wcm: shape {m.shape}")
    if "fba_row_substrate_idx" in data.keys():
        m = data["fba_row_substrate_idx"]
        print(f"fba_row_substrate_idx: shape {m.shape}, first 10: {m[:10]}")
