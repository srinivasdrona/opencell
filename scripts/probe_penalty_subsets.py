"""Targeted penalty subsets — test kinases-only vs transports-only vs both."""
import sys
import dataclasses
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

# Get baseline OC flux (current GLPK config)
v_oc, info_oc = km.solve_fba(
    model, use_full_objective=True, sense="max", big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
    solver="glpk",
)


def writeback_L1(v, growth, seed=12345):
    A = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub, v_504=v, growth_per_s=growth,
        fixture=fbf, rng=_Mcg16807(seed=seed), step_size_sec=1.0,
    )
    return float(np.abs(A.sum(axis=1).astype(np.float64) - C_flat).sum())


baseline_wb = writeback_L1(v_oc, info_oc["biomass_flux_per_s"])
print(f"Baseline WB L1: {baseline_wb:.0f}  (current GLPK with presolve=OFF)")

# Subsets to test (by FBA col index)
KINASES_PYRUVATE = [194, 198, 199, 200]      # Pyk variants other than _ADP
KINASES_ADENYLATE = [6, 7]                    # Adk2, Adk3 (Adk1 at col 5 is primary)
KINASES_PHOSPHOFRUCTO = [158, 159, 161]      # PfkA2/3/5 (PfkA1 is primary?)
KINASES_GUANYLATE = [83, 84]                  # Gmk3, Gmk4 (Gmk1/2 are primary)
TRANSPORTS_OPP = [28, 297, 449, 450]          # Apts/OppB Trp/Phe
KINASES_ALL = KINASES_PYRUVATE + KINASES_ADENYLATE + KINASES_PHOSPHOFRUCTO + KINASES_GUANYLATE
ALL_17 = KINASES_ALL + TRANSPORTS_OPP + [81, 82]  # Add Gmk1, Gmk2 too

subsets = {
    "Pyk only":      KINASES_PYRUVATE,
    "Adk only":      KINASES_ADENYLATE,
    "PfkA only":     KINASES_PHOSPHOFRUCTO,
    "Gmk only":      KINASES_GUANYLATE,
    "Kinases all":   KINASES_ALL,
    "Transports":    TRANSPORTS_OPP,
    "All 17 candidates": ALL_17,
}

print()
print(f"{'subset':30s}  {'alpha':>8s}  {'growth':>14s}  {'flux L1':>11s}  {'WB L1':>8s}  {'delta':>8s}")
print("-" * 100)

for name, idx_list in subsets.items():
    for alpha in [1e-9, 1e-7, 1e-5]:
        obj_modified = model.obj.copy()
        for r in idx_list:
            sgn = np.sign(v_oc[r])
            obj_modified[r] = obj_modified[r] - alpha * sgn
        model_mod = dataclasses.replace(model, obj=obj_modified)
        try:
            v, info = km.solve_fba(
                model_mod, use_full_objective=True, sense="max", big=1e6,
                lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
                solver="glpk",
            )
            growth = info["biomass_flux_per_s"]
            d_flux = float(np.abs(v - flux_karr).sum())
            wb = writeback_L1(v, growth)
            delta = wb - baseline_wb
            mark = " <-- BETTER" if delta < -100 else ""
            print(f"{name:30s}  {alpha:8.0e}  {growth:14.6e}  {d_flux:11.4e}  {wb:8.0f}  {delta:+8.0f}{mark}")
        except Exception as e:
            print(f"{name:30s}  {alpha:8.0e}  FAILED: {e}")
    print()
