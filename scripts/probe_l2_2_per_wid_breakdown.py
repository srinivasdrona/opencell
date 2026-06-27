"""Identify which WIDs dominate the L2.2 substrate W1 gap.

If a small number of WIDs (LIPASE family, etc.) carry most of the W1,
we have a targeted fix path.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture, apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

TRACE_DIR = REPO / "data/m1_sources/karr_native"


def load_seed(seed):
    path = TRACE_DIR / f"per_process_traces_v2_s{seed:03d}" / "Metabolism_100ticks.mat"
    with h5py.File(path, "r") as h:
        before_refs = h["states_before/substrates"][:].reshape(-1)
        after_refs = h["states_after/substrates"][:].reshape(-1)
        enz_refs = h["states_before/enzymes"][:].reshape(-1)
        T = len(before_refs)
        before = np.zeros((T, 585, 3), dtype=np.float64)
        after = np.zeros((T, 585, 3), dtype=np.float64)
        enz = np.zeros((T, 104), dtype=np.float64)
        for t in range(T):
            b = np.asarray(h[before_refs[t]][:], dtype=np.float64)
            a = np.asarray(h[after_refs[t]][:], dtype=np.float64)
            e = np.asarray(h[enz_refs[t]][:], dtype=np.float64).reshape(-1)
            if b.shape == (3, 585):
                b = b.T
            if a.shape == (3, 585):
                a = a.T
            before[t] = b
            after[t] = a
            enz[t] = e
    return before, after, enz


model = km.load_default()
dyn = cfb.load_default_dynamics()
fbr = np.column_stack([model.lb, model.ub]).astype(float)
fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))
SUB_IDS = model.raw["ids"]["substrate_wcm_585"]

# Accumulate per-WID writeback errors across all 500 audit samples
N_SEEDS = 50
N_TICKS = 10
per_wid_err = np.zeros((N_SEEDS, N_TICKS, 585), dtype=np.float64)
per_wid_karr_mass = np.zeros((N_SEEDS, N_TICKS, 585), dtype=np.float64)

for seed in range(N_SEEDS):
    before, after, enz = load_seed(seed)
    for t in range(N_TICKS):
        pre = before[t]
        karr_delta = (after[t] - before[t]).astype(np.float64)
        # Per-WID Karr mass (sum across compartments)
        karr_delta_flat = karr_delta.sum(axis=1)
        per_wid_karr_mass[seed, t] = np.abs(karr_delta_flat)
        # OC GLPK solve + writeback
        lb_oc = cfb.compute_bounds(
            substrates=pre, enzymes=enz[t],
            cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis, enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fbr, dyn=dyn, apply_protein_bounds=False,
        )
        v, info = km.solve_fba(
            model, use_full_objective=True, sense="max", big=1e6,
            lb_override=lb_oc[:,0], ub_override=lb_oc[:,1], solver="glpk",
        )
        oc_delta = apply_karr_substrate_writeback(
            pre_state_585x3=pre, v_504=v,
            growth_per_s=info["biomass_flux_per_s"],
            fixture=fbf, rng=_Mcg16807(seed=12345+seed), step_size_sec=1.0,
        )
        oc_delta_flat = oc_delta.sum(axis=1).astype(np.float64)
        per_wid_err[seed, t] = np.abs(oc_delta_flat - karr_delta_flat)
    if seed % 10 == 0:
        print(f"  seed {seed}: done")

# Aggregate per-WID across all 500 samples
mean_err_per_wid = per_wid_err.mean(axis=(0, 1))  # (585,)
mean_karr_per_wid = per_wid_karr_mass.mean(axis=(0, 1))  # (585,)
total_err = mean_err_per_wid.sum()
print()
print(f"Total mean per-sample writeback L1: {total_err:.0f}")
print()
print("Top 30 WIDs by mean writeback error:")
print(f"{'rank':>4s}  {'WID':16s}  {'err':>10s}  {'%total':>7s}  {'cum%':>6s}  {'karr_mass':>10s}")
order = np.argsort(-mean_err_per_wid)
cum = 0.0
for r, idx in enumerate(order[:30]):
    err = mean_err_per_wid[idx]
    pct = err / total_err * 100
    cum += pct
    print(f"{r+1:4d}  {SUB_IDS[idx]:16s}  {err:10.0f}  {pct:7.2f}  {cum:6.2f}  {mean_karr_per_wid[idx]:10.0f}")

# How many WIDs carry 90% of the error?
sorted_err = mean_err_per_wid[order]
cumsum_pct = sorted_err.cumsum() / total_err * 100
n_90 = int(np.searchsorted(cumsum_pct, 90)) + 1
n_99 = int(np.searchsorted(cumsum_pct, 99)) + 1
print()
print(f"Concentration: top {n_90} WIDs carry 90% of error, top {n_99} carry 99%")
