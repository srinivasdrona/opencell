"""Re-do the writeback decomposition with PROPER L1 distance arithmetic.

Triangle: A=OC-flux writeback, B=Karr-flux writeback, C=Karr recorded.
  |A - C| <= |A - B| + |B - C|  (always)

If |A - B| + |B - C| > |A - C|, the two contributions overlap.
If = , they are perfectly aligned (rare but possible).
If < , my arithmetic is wrong somewhere.

I previously claimed "74% solver + 18% RNG" by using sum_abs differences
instead of L1 distances. Recomputing properly.
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
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture, apply_karr_substrate_writeback, project_to_flat_per_wid,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metabolism_matlab_flux_growth.mat"
with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["fba_flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr = np.asarray(h["bounds_dynamic"][()], dtype=np.float64)
    growth_karr = float(np.asarray(h["growth_per_s"][()]).reshape(-1)[0])
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T

model = km.load_default()
dyn = cfb.load_default_dynamics()

v_oc, info_oc = km.solve_fba(
    model, use_full_objective=True, sense="max",
    big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
)
growth_oc = info_oc["biomass_flux_per_s"]

trace_path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T
    karr_after_recorded = get3d("states_after/substrates", 0).T
karr_recorded_delta = karr_after_recorded - karr_pre

fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))

# Run writeback with both flux vectors, SAME RNG seed
A = apply_karr_substrate_writeback(
    pre_state_585x3=karr_pre, v_504=v_oc, growth_per_s=growth_oc,
    fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
)
B = apply_karr_substrate_writeback(
    pre_state_585x3=karr_pre, v_504=flux_karr, growth_per_s=growth_karr,
    fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
)
C = karr_recorded_delta.astype(np.int64)

# All three are (585, 3). Project to flat per-WID via row-sum.
sub_ids = list(model.raw["ids"]["substrate_wcm_585"])

def to_flat_array(delta_585x3):
    return delta_585x3.sum(axis=1).astype(np.float64)  # (585,)

A_flat = to_flat_array(A)
B_flat = to_flat_array(B)
C_flat = to_flat_array(C)

# Proper L1 distances
d_AB = float(np.abs(A_flat - B_flat).sum())
d_BC = float(np.abs(B_flat - C_flat).sum())
d_AC = float(np.abs(A_flat - C_flat).sum())

print("=" * 70)
print("PROPER L1 DISTANCE DECOMPOSITION (per-WID flat, summed across compartments)")
print("=" * 70)
print(f"A = OC-flux writeback   sum_abs = {np.abs(A_flat).sum():.0f}")
print(f"B = Karr-flux writeback sum_abs = {np.abs(B_flat).sum():.0f}")
print(f"C = Karr recorded delta sum_abs = {np.abs(C_flat).sum():.0f}")
print()
print(f"|A - B| = {d_AB:.0f}   (solver basis effect: OC HiGHS vs Karr GLPK, SAME RNG)")
print(f"|B - C| = {d_BC:.0f}   (RNG + algorithm fidelity gap: same flux, OC RNG vs Karr RNG)")
print(f"|A - C| = {d_AC:.0f}   (TOTAL gap: what L2.2 measures)")
print()
print(f"|A - B| + |B - C| = {d_AB + d_BC:.0f}   (triangle upper bound)")
print(f"|A - C| - (|A - B| + |B - C|) = {d_AC - (d_AB + d_BC):.0f}")
print(f"  → if positive, my math is WRONG (triangle violation impossible)")
print(f"  → if negative, the two factors OVERLAP (some divergence is shared)")
print(f"  → if zero, perfect orthogonality (rare)")

if d_AC > d_AB + d_BC + 1e-9:
    print()
    print("⚠️ TRIANGLE VIOLATION — arithmetic bug somewhere. Investigating per-WID.")
    # Diagnose: which WIDs contribute to the violation?
    for i in range(585):
        ab = abs(A_flat[i] - B_flat[i])
        bc = abs(B_flat[i] - C_flat[i])
        ac = abs(A_flat[i] - C_flat[i])
        if ac > ab + bc + 1e-9:
            print(f"  WID {sub_ids[i]}: A={A_flat[i]:.1f} B={B_flat[i]:.1f} C={C_flat[i]:.1f} "
                  f"|A-C|={ac:.1f} > |A-B|+|B-C|={ab+bc:.1f}")
            break
else:
    overlap = (d_AB + d_BC) - d_AC
    print()
    print(f"Triangle valid. Overlap fraction: {overlap / d_AC * 100:.1f}%")
    print()
    print("Honest decomposition:")
    print(f"  Solver-basis contribution: {d_AB / d_AC * 100:.1f}% of total gap ({d_AB:.0f} / {d_AC:.0f})")
    print(f"  RNG+fidelity contribution: {d_BC / d_AC * 100:.1f}% of total gap ({d_BC:.0f} / {d_AC:.0f})")
    print(f"  Sum: {(d_AB + d_BC) / d_AC * 100:.1f}% (>= 100% if factors overlap)")

# Per-WID breakdown: which WIDs have largest A-B (solver-basis) vs B-C (RNG)?
print()
print("=" * 70)
print("Per-WID attribution (top 10 each)")
print("=" * 70)

ab_per_wid = np.abs(A_flat - B_flat)
bc_per_wid = np.abs(B_flat - C_flat)
ac_per_wid = np.abs(A_flat - C_flat)

print("\nTop 10 by |A - B| (solver-basis):")
for i in np.argsort(-ab_per_wid)[:10]:
    print(f"  {sub_ids[i]:18s}: A={A_flat[i]:+8.0f} B={B_flat[i]:+8.0f} C={C_flat[i]:+8.0f} "
          f"|A-B|={ab_per_wid[i]:7.0f} |B-C|={bc_per_wid[i]:7.0f} |A-C|={ac_per_wid[i]:7.0f}")

print("\nTop 10 by |B - C| (RNG/fidelity):")
for i in np.argsort(-bc_per_wid)[:10]:
    print(f"  {sub_ids[i]:18s}: A={A_flat[i]:+8.0f} B={B_flat[i]:+8.0f} C={C_flat[i]:+8.0f} "
          f"|A-B|={ab_per_wid[i]:7.0f} |B-C|={bc_per_wid[i]:7.0f} |A-C|={ac_per_wid[i]:7.0f}")

print("\nTop 10 by |A - C| (total gap):")
for i in np.argsort(-ac_per_wid)[:10]:
    print(f"  {sub_ids[i]:18s}: A={A_flat[i]:+8.0f} B={B_flat[i]:+8.0f} C={C_flat[i]:+8.0f} "
          f"|A-B|={ab_per_wid[i]:7.0f} |B-C|={bc_per_wid[i]:7.0f} |A-C|={ac_per_wid[i]:7.0f}")
