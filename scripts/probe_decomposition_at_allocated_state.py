"""REDO the OC-vs-Karr decomposition with flux extracted at the correct
allocated state (not fitted snapshot).
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture, apply_karr_substrate_writeback, CYTOSOL, EXTRACELLULAR,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

# NEW ground truth: flux at the trace's allocated state
GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"

with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
    growth_karr = float(np.asarray(h["growth"][()]).reshape(-1)[0])
    bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
    pre_sub_alloc = np.asarray(h["pre_sub"][()], dtype=np.float64)  # (3, 585) or (585, 3)
    pre_enz_alloc = np.asarray(h["pre_enz"][()], dtype=np.float64).reshape(-1)
    post_sub_alloc = np.asarray(h["post_sub"][()], dtype=np.float64)
    delta_karr_alloc = np.asarray(h["delta"][()], dtype=np.float64)

# Normalize shapes to (585, 3)
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T
if pre_sub_alloc.shape == (3, 585):
    pre_sub_alloc = pre_sub_alloc.T
if post_sub_alloc.shape == (3, 585):
    post_sub_alloc = post_sub_alloc.T
if delta_karr_alloc.shape == (3, 585):
    delta_karr_alloc = delta_karr_alloc.T

print(f"Karr at allocated state:")
print(f"  growth_per_s = {growth_karr:.6e}")
print(f"  flux sum_abs = {np.abs(flux_karr).sum():.4e}")
print(f"  flux nonzero = {(flux_karr != 0).sum()}/504")
print(f"  pre_sub sum_abs = {np.abs(pre_sub_alloc).sum():.4e}")
print(f"  delta sum_abs = {np.abs(delta_karr_alloc).sum():.0f}")

# Run OC HiGHS at the SAME allocated state
model = km.load_default()
dyn = cfb.load_default_dynamics()

# Use Karr's bounds (already at the allocated state)
v_oc, info_oc = km.solve_fba(
    model, use_full_objective=True, sense="max",
    big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
)
growth_oc = info_oc["biomass_flux_per_s"]
print(f"\nOC HiGHS at allocated state (using Karr's bounds):")
print(f"  growth_per_s = {growth_oc:.6e}")
print(f"  flux sum_abs = {np.abs(v_oc).sum():.4e}")

# Flux-vector L1 distance OC HiGHS vs Karr GLPK
flux_diff = v_oc - flux_karr
print(f"\n=== Flux comparison (OC HiGHS vs Karr GLPK, same bounds, same state) ===")
print(f"|OC flux - Karr flux| L1: {np.abs(flux_diff).sum():.4e}")
print(f"Max abs diff per cell: {np.abs(flux_diff).max():.4e}")
print(f"Cells |diff| > 1: {(np.abs(flux_diff) > 1).sum()}/504")
print(f"Cells |diff| > 100: {(np.abs(flux_diff) > 100).sum()}/504")
print(f"Cells |diff| > 1e4: {(np.abs(flux_diff) > 1e4).sum()}/504")

# Apply writeback with both fluxes at the allocated pre-state
fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))

A = apply_karr_substrate_writeback(
    pre_state_585x3=pre_sub_alloc, v_504=v_oc, growth_per_s=growth_oc,
    fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
)
B = apply_karr_substrate_writeback(
    pre_state_585x3=pre_sub_alloc, v_504=flux_karr, growth_per_s=growth_karr,
    fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
)
C = delta_karr_alloc.astype(np.int64)

# Per-WID flat
A_flat = A.sum(axis=1).astype(np.float64)
B_flat = B.sum(axis=1).astype(np.float64)
C_flat = C.sum(axis=1).astype(np.float64)

d_AB = float(np.abs(A_flat - B_flat).sum())
d_BC = float(np.abs(B_flat - C_flat).sum())
d_AC = float(np.abs(A_flat - C_flat).sum())

print("\n" + "=" * 70)
print("PROPER DECOMPOSITION AT THE CORRECT (ALLOCATED) STATE")
print("=" * 70)
print(f"A = OC-flux WB sum_abs:   {np.abs(A_flat).sum():.0f}")
print(f"B = Karr-flux WB sum_abs: {np.abs(B_flat).sum():.0f}")
print(f"C = Karr recorded sum_abs:{np.abs(C_flat).sum():.0f}")
print()
print(f"|A - B| (solver basis):     {d_AB:.0f}")
print(f"|B - C| (RNG + algorithm):  {d_BC:.0f}")
print(f"|A - C| (TOTAL gap):        {d_AC:.0f}")
print()
print(f"Solver-basis %: {d_AB/d_AC*100:.1f}%")
print(f"RNG+fidelity %: {d_BC/d_AC*100:.1f}%")
print(f"Sum: {(d_AB+d_BC)/d_AC*100:.1f}%")
