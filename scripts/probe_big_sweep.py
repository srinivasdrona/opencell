"""Test if lowering `big` (the +/-inf substitute) closes the cycle-magnitude gap.

Karr's recorded flux on the worst-offender reactions is ±3e4 max.
Our GLPK pushes them to ±1e6 (our big cap).
If we lower big to ~1e4-1e5, our cycles get constrained closer to Karr's natural scale.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture, apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"

with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
    pre_sub = np.asarray(h["pre_sub"][()], dtype=np.float64)
    delta_karr = np.asarray(h["delta"][()], dtype=np.float64).astype(np.int64)
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T
if pre_sub.shape == (3, 585):
    pre_sub = pre_sub.T
if delta_karr.shape == (3, 585):
    delta_karr = delta_karr.T

model = km.load_default()
fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))
C_flat = delta_karr.sum(axis=1).astype(np.float64)

print(f"Karr ref: growth=2.119269e-05, nnz=327, sum_abs={np.abs(flux_karr).sum():.2e}")
print()
print(f"{'big':>8s}  {'growth':>14s}  {'flux L1':>11s}  {'cycle max':>9s}  {'nnz':>4s}  {'WB L1':>8s}")
print("-" * 75)

for big in [1e6, 5e5, 1e5, 5e4, 3e4, 1e4]:
    try:
        v, info = km.solve_fba(
            model, use_full_objective=True, sense="max",
            big=big,
            lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
            solver="glpk",
        )
        growth = info["biomass_flux_per_s"]
        d = v - flux_karr
        L1 = float(np.abs(d).sum())
        nnz = int((np.abs(v) > 1e-9).sum())
        # Cycle reactions (indices identified from prior probe)
        cycle_idx = [6, 7, 81, 83, 159, 161, 194, 198, 199, 200]
        cycle_max = float(max(abs(v[i]) for i in cycle_idx))
        # Writeback
        delta_oc = apply_karr_substrate_writeback(
            pre_state_585x3=pre_sub, v_504=v, growth_per_s=growth,
            fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
        )
        A_flat = delta_oc.sum(axis=1).astype(np.float64)
        wb = float(np.abs(A_flat - C_flat).sum())
        print(f"  {big:>6.0e}  {growth:14.6e}  {L1:11.4e}  {cycle_max:9.2e}  {nnz:4d}  {wb:8.0f}")
    except Exception as e:
        print(f"  {big:>6.0e}: FAILED ({e})")

print()
print(f"  Karr  {2.119269e-5:14.6e}  {0.0:11.4e}  {float(max(abs(flux_karr[i]) for i in [6,7,81,83,159,161,194,198,199,200])):9.2e}  327  {40:8d}")
