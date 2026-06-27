"""Sanity check: solver still runs after pricing=STD edit; flux matches H3 V3."""
import json
import numpy as np
import h5py

from opencell.m1 import karr_metabolism as km

npz = np.load("data/karr_fixtures/karr_native_m1.npz", allow_pickle=False)
S = npz["S"].astype(np.float64)
rhs = npz["RHS"].astype(np.float64)
c = npz["obj"].astype(np.float64)

# Pull sample (s=0, t=1) ground truth (v7.3 MAT file -> HDF5).
with h5py.File("data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat", "r") as f:
    bounds = np.array(f["bounds"]).T  # MATLAB stores transposed; (504, 2)
    karr_flux = np.array(f["flux"]).ravel()

sample_lb = bounds[:, 0].astype(np.float64)
sample_ub = bounds[:, 1].astype(np.float64)

BIG = 1e6
lb = np.clip(sample_lb, -BIG, BIG)
ub = np.clip(sample_ub, -BIG, BIG)

from types import SimpleNamespace
model = SimpleNamespace(S=S, RHS=rhs)

v, obj, status = km._solve_fba_glpk(model, c=c, lb=lb, ub=ub, sense="max")

l1_vs_karr = float(np.abs(v - karr_flux).sum())
print(f"status={status}, obj={obj:.6e}")
print(f"L1 vs Karr flux: {l1_vs_karr:.3e}")
print(f"Expected (H3 V3): 3.54e+5 (was 8.18e+6 before fix)")
print(f"Reduction: {8.18e6 / l1_vs_karr:.1f}x" if l1_vs_karr > 0 else "exact match")

