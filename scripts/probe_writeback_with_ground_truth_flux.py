"""Apply Karr writeback with BOTH OC's flux and Karr's flux. Compare resulting
substrate deltas.

If OC-flux writeback differs from Karr-flux writeback significantly, the L2.2 W1
gap is the solver-basis difference (HiGHS vs GLPK).
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
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
    project_to_flat_per_wid,
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

# Get OC HiGHS flux at Karr-matched conditions
v_oc, info_oc = km.solve_fba(
    model, use_full_objective=True, sense="max",
    big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
)
growth_oc = info_oc["biomass_flux_per_s"]

# Load Karr tick-0 pre-state for writeback
trace_path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T   # (585, 3)
    karr_after_recorded = get3d("states_after/substrates", 0).T
karr_recorded_delta = karr_after_recorded - karr_pre

fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))

# Apply writeback with OC flux + OC growth
rng_oc = _Mcg16807(seed=12345)
delta_from_oc_flux = apply_karr_substrate_writeback(
    pre_state_585x3=karr_pre,
    v_504=v_oc,
    growth_per_s=growth_oc,
    fixture=fbf, rng=rng_oc, step_size_sec=1.0,
)

# Apply writeback with KARR flux + KARR growth (ground truth)
rng_karr = _Mcg16807(seed=12345)
delta_from_karr_flux = apply_karr_substrate_writeback(
    pre_state_585x3=karr_pre,
    v_504=flux_karr,
    growth_per_s=growth_karr,
    fixture=fbf, rng=rng_karr, step_size_sec=1.0,
)

print(f"=== Substrate delta comparison (with Karr realmax=1e6) ===")
print(f"OC-flux writeback (585, 3) sum_abs: {np.abs(delta_from_oc_flux).sum():.0f}")
print(f"Karr-flux writeback (585, 3) sum_abs: {np.abs(delta_from_karr_flux).sum():.0f}")
print(f"Karr recorded delta sum_abs: {np.abs(karr_recorded_delta).sum():.0f}")

# Per-WID flat projection (sum across compartments)
sub_ids = list(model.raw["ids"]["substrate_wcm_585"])
flat_oc = project_to_flat_per_wid(delta_from_oc_flux, sub_ids)
flat_karr_writeback = project_to_flat_per_wid(delta_from_karr_flux, sub_ids)

flat_karr_recorded = {sub_ids[i]: float(karr_recorded_delta[i, :].sum())
                      for i in range(585) if karr_recorded_delta[i, :].sum() != 0}

print(f"\nPer-WID flat sum_abs:")
print(f"  OC-flux writeback: {sum(abs(v) for v in flat_oc.values()):.0f} (keys: {len(flat_oc)})")
print(f"  Karr-flux writeback: {sum(abs(v) for v in flat_karr_writeback.values()):.0f} (keys: {len(flat_karr_writeback)})")
print(f"  Karr recorded: {sum(abs(v) for v in flat_karr_recorded.values()):.0f} (keys: {len(flat_karr_recorded)})")

# W1-like distance: sum of |oc_writeback[wid] - karr_writeback[wid]|
all_wids = set(flat_oc) | set(flat_karr_writeback)
w1_oc_vs_karr_writeback = sum(
    abs(flat_oc.get(w, 0.0) - flat_karr_writeback.get(w, 0.0))
    for w in all_wids
)
print(f"\nPer-WID L1 diff between OC-flux writeback and Karr-flux writeback: {w1_oc_vs_karr_writeback:.1f}")
print(f"  (this is the solver-basis contribution to the L2.2 W1 metric)")

# Same comparison vs Karr's RECORDED delta (what L2.2 actually compares against)
all_wids_rec = set(flat_oc) | set(flat_karr_recorded)
w1_oc_vs_karr_recorded = sum(
    abs(flat_oc.get(w, 0.0) - flat_karr_recorded.get(w, 0.0))
    for w in all_wids_rec
)
print(f"\nPer-WID L1 diff between OC-flux writeback and Karr RECORDED delta: {w1_oc_vs_karr_recorded:.1f}")
print(f"  (this is the total gap the L2.2 strict-rubric measures)")

# Top divergences between OC-writeback and Karr-recorded
print(f"\n=== Top 15 per-WID divergences (OC-flux writeback vs Karr recorded) ===")
diffs = []
for w in all_wids_rec:
    oc_v = flat_oc.get(w, 0.0)
    karr_v = flat_karr_recorded.get(w, 0.0)
    diffs.append((w, oc_v, karr_v, oc_v - karr_v))
diffs.sort(key=lambda x: -abs(x[3]))
for w, oc_v, karr_v, d in diffs[:15]:
    print(f"  {w:20s}: OC={oc_v:+.0f}, Karr={karr_v:+.0f}, diff={d:+.0f}")
