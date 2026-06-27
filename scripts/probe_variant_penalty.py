"""Identify all variant-family pickaround reactions and apply targeted parsimony.

Criteria for "alternate variant" needing penalty:
  - OC |flux| > 1e3 AND Karr |flux| < OC|flux| / 100 (OC over-uses)
  - OR Karr |flux| > 1e3 AND OC |flux| < Karr|flux| / 100 (OC under-uses)
  - OR sign disagreement with |OC|, |Karr| both > 1e2

Add parsimony = -alpha (per |v|) on the OC-over-using reactions only.
Magnitude chosen to bias the LP without overpowering biomass:
  alpha = 1e-9 → at v=1e6, contribution = -1e-3 (vs biomass = +0.02)
  alpha = 1e-7 → at v=1e6, contribution = -1e-1 (5x biomass — risky)
Test multiple alpha values.
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

# Baseline OC solve (current GLPK config)
v_oc, info_oc = km.solve_fba(
    model, use_full_objective=True, sense="max", big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
    solver="glpk",
)

# Identify alternate-variant candidates
n_R = 504
candidates = []
for r in range(n_R):
    oc_v = v_oc[r]
    karr_v = flux_karr[r]
    if abs(oc_v) > 1e3 and abs(karr_v) < abs(oc_v) / 100:
        candidates.append((r, oc_v, karr_v, "OC overuses"))
    elif abs(karr_v) > 1e3 and abs(oc_v) < abs(karr_v) / 100:
        # If we PENALIZE OC's near-zero, that doesn't help; opposite case.
        # Skip these — they're cases where Karr uses something OC doesn't.
        pass
    elif np.sign(oc_v) != np.sign(karr_v) and abs(oc_v) > 100 and abs(karr_v) > 100:
        candidates.append((r, oc_v, karr_v, "sign-disagree"))

print(f"Found {len(candidates)} alternate-variant candidates to penalize:")
for r, oc_v, karr_v, why in candidates[:20]:
    print(f"  col {r:4d}  OC={oc_v:+.3e}  Karr={karr_v:+.3e}  ({why})")

penalty_indices = [r for r, _, _, _ in candidates]
print(f"\nWill penalize {len(penalty_indices)} reactions.")

# Compute baseline writeback L1 for reference
def writeback_L1(v, growth, seed=12345):
    A = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub, v_504=v, growth_per_s=growth,
        fixture=fbf, rng=_Mcg16807(seed=seed), step_size_sec=1.0,
    )
    return float(np.abs(A.sum(axis=1).astype(np.float64) - C_flat).sum())

baseline_wb = writeback_L1(v_oc, info_oc["biomass_flux_per_s"])
print(f"\nBaseline WB L1 (no extra penalty): {baseline_wb:.0f}")

# Sweep alpha
print()
print(f"{'alpha':>10s}  {'growth':>14s}  {'flux L1':>11s}  {'nnz':>4s}  {'WB L1':>8s}  {'delta WB':>9s}")
print("-" * 80)

# Save original objective
obj_orig = model.obj.copy()

for alpha in [0, 1e-12, 1e-9, 1e-7, 1e-5, 1e-3]:
    # Build modified objective
    obj_modified = obj_orig.copy()
    # Penalty on signed v: subtract alpha if OC's flux is positive at this reaction,
    # add alpha if negative. This biases LP to suppress THIS direction.
    # But for symmetric tie-breaking, easier: penalize |v|, which needs abs vars.
    # Simpler: subtract alpha * sign(oc_v) from objective. The LP will prefer
    # opposite-sign flux, which suppresses OC's chosen direction.
    for r in penalty_indices:
        sgn = np.sign(v_oc[r])
        obj_modified[r] = obj_orig[r] - alpha * sgn
    
    # Inject into model temporarily — clone all fields
    import dataclasses
    model_mod = dataclasses.replace(model, obj=obj_modified)
    v, info = km.solve_fba(
        model_mod, use_full_objective=True, sense="max", big=1e6,
        lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
        solver="glpk",
    )
    growth = info["biomass_flux_per_s"]
    d_flux = np.abs(v - flux_karr).sum()
    nnz = int((np.abs(v) > 1e-9).sum())
    wb = writeback_L1(v, growth)
    delta_wb = wb - baseline_wb
    print(f"  {alpha:8.0e}  {growth:14.6e}  {d_flux:11.4e}  {nnz:4d}  {wb:8.0f}  {delta_wb:+9.0f}")
