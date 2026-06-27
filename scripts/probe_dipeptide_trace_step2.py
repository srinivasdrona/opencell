"""Step 2: map FBA substrate rows to 585-WID names, then trace dipeptide reactions."""
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

S = model.S
sub_ids_585 = model.raw["ids"]["substrate_wcm_585"]
sub_names_585 = model.raw["ids"]["substrate_names_585"]
fba_col_to_rxn = model.raw["ids"]["fba_col_to_reaction_wcm"]
rxn_names_645 = model.raw["ids"]["reaction_names_645"]
rxn_ids_645 = model.raw["ids"]["reaction_wcm_645"]

# Find the substrates/compartments mapping for the 376 FBA rows
npz = np.load(REPO / model.raw["matrix_npz"])
fba_sub_idx_substrates = npz["fba_sub_idx_substrates"]  # likely (n_substrates_count,) -> fba_row_index
print(f"fba_sub_idx_substrates shape: {fba_sub_idx_substrates.shape}")
print(f"  sample first 10: {fba_sub_idx_substrates[:10]}")
print(f"  unique count: {len(np.unique(fba_sub_idx_substrates))}")
# Need to look at interpretation for guidance
import json
interp = model.raw.get("interpretation", "")
if isinstance(interp, str) and interp:
    print(f"Interpretation: {interp[:300]}")
elif isinstance(interp, dict):
    print(f"Interpretation keys: {list(interp.keys())}")
    for k, v in interp.items():
        if "substrate" in str(k).lower() or "fba" in str(k).lower():
            print(f"  {k}: {str(v)[:200]}")

# Build the mapping: fba_row_index -> (wcm_substrate_idx, compartment)
# fba_sub_idx_substrates appears to be an array (n_fba_sub_count,) of fba row indices
# Convert: for each WCM substrate idx, what FBA row(s) does it appear in?
# Actually fba_sub_idx_substrates is the OTHER way — likely fba_sub_idx_substrates[fba_row] = wcm_substrate_idx
print()
print("Trying inversion approach")
# Test: if fba_sub_idx_substrates is shape (n_substrates_count,) where its entry is
# an FBA row index, that means it's "for each substrate index in some list, what FBA row"
# We need: for each FBA row, what is the WCM 585 idx + compartment

# Find by matching: try fba_idx_metab_conv too
print(f"fba_idx_metab_conv: shape {npz['fba_idx_metab_conv'].shape}, first 10: {npz['fba_idx_metab_conv'][:10]}")
print(f"fba_idx_ext_exch: shape {npz['fba_idx_ext_exch'].shape}, first 5: {npz['fba_idx_ext_exch'][:5]}")
print(f"fba_idx_int_exch: shape {npz['fba_idx_int_exch'].shape}, first 5: {npz['fba_idx_int_exch'][:5]}")
print(f"fba_idx_int_lim: shape {npz['fba_idx_int_lim'].shape}, first 5: {npz['fba_idx_int_lim'][:5]}")
print(f"fba_idx_int_unlim: shape {npz['fba_idx_int_unlim'].shape}, first 5: {npz['fba_idx_int_unlim'][:5]}")
