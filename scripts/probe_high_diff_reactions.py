"""Identify which reactions OC's GLPK is using that Karr's GLPK isn't.

Compares per-reaction flux at sample (s=0, t=1):
  - Reactions where |OC flux - Karr flux| > 1e3
  - Highlights TrpTrp/TyrTyr/PhePhe-producing reactions specifically
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
v_oc, info = km.solve_fba(
    model, use_full_objective=True, sense="max", big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
    solver="glpk",
)

S = model.S
sub_ids = model.raw["ids"]["substrate_wcm_585"]

# Get FBA substrate row indices for the substrate WIDs we care about
target_wids = ["TrpTrp", "TyrTyr", "PhePhe", "TRP", "TYR", "PHE",
               "OCDCEA", "TRIOLEIN", "HDCA"]
target_idx = {w: sub_ids.index(w) for w in target_wids if w in sub_ids}
print(f"Target WIDs: {list(target_idx.keys())}")
print(f"S matrix shape: {S.shape}")  # (M, R) = (376, 504)

# But S is the FBA stoich, indexed on FBA substrate rows, not 585.
# Check what fba substrate index maps to. Probably:
print(f"\nfba_substrate_to_wcm 585 mapping: check m.raw['ids']")
keys = list(model.raw["ids"].keys())
print(f"  raw ids keys: {keys}")

# We probably need m.fba_subst_to_substrate_wcm or similar
# Inspect each:
for k in keys:
    v = model.raw["ids"][k]
    if hasattr(v, "__len__"):
        print(f"  {k}: len={len(v)} first={v[0] if v else None}")

# Print top reactions where OC and Karr differ
print()
print("=" * 75)
print("Reactions with largest |OC - Karr| flux at sample (0,1)")
print("=" * 75)
d = v_oc - flux_karr
order = np.argsort(-np.abs(d))
print(f"{'rxn':>4s}  {'|diff|':>10s}  {'OC':>11s}  {'Karr':>11s}  {'lb':>10s}  {'ub':>10s}  stoich-signature")
for r in order[:25]:
    stoich_col = S[:, r]
    nz_rows = np.nonzero(stoich_col)[0]
    sig = ", ".join(f"{'+' if stoich_col[i] > 0 else '-'}fba_{i}" for i in nz_rows[:5])
    if len(nz_rows) > 5:
        sig += f", +{len(nz_rows)-5} more"
    print(f"{r:4d}  {abs(d[r]):10.2e}  {v_oc[r]:+11.2e}  {flux_karr[r]:+11.2e}  "
          f"{bounds_karr[r,0]:+10.2e}  {bounds_karr[r,1]:+10.2e}  {sig}")
