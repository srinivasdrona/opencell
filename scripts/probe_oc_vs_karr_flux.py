"""Compare OC's HiGHS FBA flux to Karr's GLPK ground truth at the snapshot.

Day-39 Path B: now that we have Karr's actual flux vector from MATLAB,
quantify the OC-vs-Karr divergence at the LP-solution level.

Loads MATLAB-extracted ground truth from:
  data/karr_fixtures/matlab_ground_truth/metabolism_matlab_flux_growth.mat

Runs OC's HiGHS at the same bounds.

Reports per-reaction divergence histogram + top discrepancies.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metabolism_matlab_flux_growth.mat"
print(f"Loading ground truth: {GT_PATH.name}")

with h5py.File(GT_PATH, "r") as h:
    print(f"Top keys: {[k for k in h.keys() if not k.startswith('#')]}")
    growth_karr = float(np.asarray(h["growth_per_s"][()]).reshape(-1)[0])
    flux_karr = np.asarray(h["fba_flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr = np.asarray(h["bounds_dynamic"][()], dtype=np.float64)
    realmax = float(np.asarray(h["realmax"][()]).reshape(-1)[0])
    cell_dry_mass = float(np.asarray(h["snapshot_cell_dry_mass"][()]).reshape(-1)[0])
    fba_objective = np.asarray(h["fba_objective"][()], dtype=np.float64).reshape(-1)

# Bounds shape: MATLAB saves as (2, 504), Python sees (2, 504) — but logically
# we want (504, 2) so it matches OC's convention.
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T
print(f"Karr fba_flux shape: {flux_karr.shape}, sum_abs: {np.abs(flux_karr).sum():.4e}")
print(f"Karr growth_per_s: {growth_karr:.6e}")
print(f"Karr realmax: {realmax}")
print(f"Karr bounds shape: {bounds_karr.shape}, finite count: {int(np.isfinite(bounds_karr).sum())} / {bounds_karr.size}")
print(f"Karr fba_objective shape: {fba_objective.shape}, nonzero: {(fba_objective != 0).sum()}")

# Load OC model
model = km.load_default()
print(f"\nOC model.S shape: {model.S.shape}")

# Compare bounds first
oc_bounds = np.column_stack([model.lb, model.ub]).astype(float)
print(f"\n=== Bounds comparison (static OC.lb/ub vs Karr dynamic bounds_dyn) ===")
# Karr's bounds are POST-calcFluxBounds (dynamic), OC.lb/ub is static fixture.
# We need to run cfb.compute_bounds on OC side to get dynamic bounds.
dyn = cfb.load_default_dynamics()
oc_dyn_bounds = cfb.compute_bounds(
    substrates=dyn.substrates_snapshot,
    enzymes=dyn.enzymes_snapshot,
    cell_dry_mass=dyn.cell_dry_mass,
    step_size_sec=dyn.step_size_sec,
    catalysis=model.catalysis,
    enz_bounds=model.enz_bounds,
    fba_reaction_bounds=oc_bounds,
    dyn=dyn,
    apply_protein_bounds=False,
)
# Diff finite cells
both_finite_lb = np.isfinite(oc_dyn_bounds[:, 0]) & np.isfinite(bounds_karr[:, 0])
both_finite_ub = np.isfinite(oc_dyn_bounds[:, 1]) & np.isfinite(bounds_karr[:, 1])
lb_diff = np.abs(oc_dyn_bounds[both_finite_lb, 0] - bounds_karr[both_finite_lb, 0])
ub_diff = np.abs(oc_dyn_bounds[both_finite_ub, 1] - bounds_karr[both_finite_ub, 1])
print(f"  lb finite-cell diff (max, mean): {lb_diff.max():.4e}, {lb_diff.mean():.4e}")
print(f"  ub finite-cell diff (max, mean): {ub_diff.max():.4e}, {ub_diff.mean():.4e}")
print(f"  cells where OC=inf but Karr=finite (lb): {(~np.isfinite(oc_dyn_bounds[:, 0]) & np.isfinite(bounds_karr[:, 0])).sum()}")
print(f"  cells where OC=inf but Karr=finite (ub): {(~np.isfinite(oc_dyn_bounds[:, 1]) & np.isfinite(bounds_karr[:, 1])).sum()}")
print(f"  cells where Karr=inf but OC=finite (lb): {(np.isfinite(oc_dyn_bounds[:, 0]) & ~np.isfinite(bounds_karr[:, 0])).sum()}")
print(f"  cells where Karr=inf but OC=finite (ub): {(np.isfinite(oc_dyn_bounds[:, 1]) & ~np.isfinite(bounds_karr[:, 1])).sum()}")

# Now solve OC's FBA with Karr's bounds + realmax=1e6 (matching Karr exactly)
print(f"\n=== OC HiGHS at Karr-matched conditions ===")
v_oc, info_oc = km.solve_fba(
    model, use_full_objective=True, sense="max",
    big=realmax,  # match Karr realmax
    lb_override=bounds_karr[:, 0],
    ub_override=bounds_karr[:, 1],
)
print(f"OC growth_per_s: {info_oc['biomass_flux_per_s']:.6e}")
print(f"OC fba_flux sum_abs: {np.abs(v_oc).sum():.4e}")
print(f"OC fba_flux nonzero: {(v_oc != 0).sum()} / {len(v_oc)}")

# Per-reaction comparison
diff = v_oc - flux_karr
abs_diff = np.abs(diff)
print(f"\n=== Per-reaction flux diff (OC HiGHS - Karr GLPK) ===")
print(f"Max abs diff: {abs_diff.max():.4e}")
print(f"Mean abs diff: {abs_diff.mean():.4e}")
print(f"Median abs diff: {np.median(abs_diff):.4e}")
print(f"Number of cells with |diff| > 1: {int((abs_diff > 1).sum())} / {len(diff)}")
print(f"Number of cells with |diff| > 100: {int((abs_diff > 100).sum())}")
print(f"Number of cells with |diff| > 1e4: {int((abs_diff > 1e4).sum())}")
print(f"Number of cells with |diff| > 1e5: {int((abs_diff > 1e5).sum())}")

# Sign agreement
sign_agree = ((v_oc > 0) == (flux_karr > 0)) & ((v_oc < 0) == (flux_karr < 0))
print(f"Cells with sign agreement: {sign_agree.sum()} / {len(v_oc)}")

# Top 20 worst discrepancies
print(f"\n=== Top 20 worst per-reaction flux diffs ===")
worst = np.argsort(-abs_diff)[:20]
for i in worst:
    rxn_wid = model.fba_col_rxn_wcm[i] if i < len(model.fba_col_rxn_wcm) else None
    print(f"  col {i:3d} ({rxn_wid}): OC={v_oc[i]:+.4e}, Karr={flux_karr[i]:+.4e}, diff={diff[i]:+.4e}")

# Objective agreement: are we picking the same biomass?
biomass_col = model.biomass_col
print(f"\n=== Biomass column (col {biomass_col}) ===")
print(f"OC v[{biomass_col}] = {v_oc[biomass_col]:.6e}")
print(f"Karr v[{biomass_col}] = {flux_karr[biomass_col]:.6e}")
print(f"OC reports growth_per_s = {info_oc['biomass_flux_per_s']:.6e}")
print(f"Karr growth_per_s = {growth_karr:.6e}")
