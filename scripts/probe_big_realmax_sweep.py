"""Test: does OC growth match Karr-expected when big=1e6 (Karr's realmax)?

Karr's Metabolism.m line 192: realmax = 1e6 (used to substitute for ±inf bounds before LP)
OC's karr_metabolism.py line 39: DEFAULT_BIG = 1e3 — 1000x more restrictive

If this is the bug, running OC with big=1e6 should produce growth close to 2.12e-5
(the "rule 3 off" value) AND substrate delta closer to Karr's 148K.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

model = km.load_default()
dyn = cfb.load_default_dynamics()
fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))

trace_path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T
    karr_enz = get3d("states_before/enzymes", 0).ravel()
    karr_after = get3d("states_after/substrates", 0).T

karr_delta = karr_after - karr_pre
karr_sum = float(np.abs(karr_delta).sum())
print(f"Karr substrate delta sum_abs: {karr_sum:.0f}")
print(f"Karr per-WID flat sum_abs: {float(np.abs(karr_delta.sum(axis=1)).sum()):.0f}")
print()

fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)
bounds = cfb.compute_bounds(
    substrates=karr_pre, enzymes=karr_enz,
    cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
    catalysis=model.catalysis, enz_bounds=model.enz_bounds,
    fba_reaction_bounds=fba_reaction_bounds, dyn=dyn,
    apply_protein_bounds=False,
)

print(f"{'big setting':>14} {'growth':>14}  ext at_lb/at_ub/interior")
print("-" * 70)
for big in [1e3, 1e4, 1e5, 1e6, 1e9, 1e12, 1e18]:
    v, info = km.solve_fba(
        model, use_full_objective=True, sense="max",
        big=big,
        lb_override=bounds[:, 0], ub_override=bounds[:, 1],
    )
    growth = info["biomass_flux_per_s"]
    ext_cols = fbf.fba_idx_external
    at_ub = (np.abs(v[ext_cols] - bounds[ext_cols, 1]) < 1e-3).sum()
    at_lb = (np.abs(v[ext_cols] - bounds[ext_cols, 0]) < 1e-3).sum()
    # Also compute writeback delta to compare to Karr's 148K
    from opencell.m1.karr_metabolism_writeback import apply_karr_substrate_writeback
    from opencell.vivarium.karr_protein_decay_light import _Mcg16807
    delta_585x3 = apply_karr_substrate_writeback(
        pre_state_585x3=karr_pre.copy(), v_504=v, growth_per_s=growth,
        fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
    )
    delta_sum = float(np.abs(delta_585x3).sum())
    per_wid_sum = float(np.abs(delta_585x3.sum(axis=1)).sum())
    print(f"{big:>14.0e} {growth:>14.4e}  {at_lb}/{at_ub}/{124-at_lb-at_ub}   "
          f"writeback sum_abs={delta_sum:.0f} (per-WID={per_wid_sum:.0f})")

print(f"\nKarr per-WID target: {float(np.abs(karr_delta.sum(axis=1)).sum()):.0f}")
print(f"Karr per-compartment target: {karr_sum:.0f}")
