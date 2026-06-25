"""Test the critical hypothesis: do the OC-vs-Karr flux discrepancies cancel out
at the substrate-effect level (S @ v)?

If S @ v_oc == S @ v_karr (within tolerance), the LP basis differences are
biologically equivalent — both produce the same substrate net change.
If S @ v_oc != S @ v_karr, the differences are real biology divergence.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metabolism_matlab_flux_growth.mat"
with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["fba_flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr = np.asarray(h["bounds_dynamic"][()], dtype=np.float64)
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T

model = km.load_default()
dyn = cfb.load_default_dynamics()
oc_bounds = np.column_stack([model.lb, model.ub]).astype(float)
oc_dyn_bounds = cfb.compute_bounds(
    substrates=dyn.substrates_snapshot, enzymes=dyn.enzymes_snapshot,
    cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
    catalysis=model.catalysis, enz_bounds=model.enz_bounds,
    fba_reaction_bounds=oc_bounds, dyn=dyn, apply_protein_bounds=False,
)
v_oc, info_oc = km.solve_fba(
    model, use_full_objective=True, sense="max",
    big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
)

# S @ v: net flux on each substrate row (376 substrates in FBA space)
S = model.S
print(f"S shape: {S.shape}, dtype: {S.dtype}")

sv_oc = S @ v_oc
sv_karr = S @ flux_karr
print(f"\nS @ v_oc shape: {sv_oc.shape}")
print(f"S @ v_oc sum_abs: {np.abs(sv_oc).sum():.4e}")
print(f"S @ v_karr sum_abs: {np.abs(sv_karr).sum():.4e}")

diff = sv_oc - sv_karr
print(f"\n=== S @ v_oc - S @ v_karr (substrate net flux diff) ===")
print(f"Max abs diff: {np.abs(diff).max():.4e}")
print(f"Mean abs diff: {np.abs(diff).mean():.4e}")
print(f"Median abs diff: {np.median(np.abs(diff)):.4e}")
print(f"Number of rows |diff| > 1: {int((np.abs(diff) > 1).sum())} / {len(diff)}")
print(f"Number of rows |diff| > 100: {int((np.abs(diff) > 100).sum())}")
print(f"Number of rows |diff| > 1e4: {int((np.abs(diff) > 1e4).sum())}")

if int((np.abs(diff) > 1).sum()) > 0:
    print(f"\nTop 10 rows with biggest S @ v diff:")
    worst = np.argsort(-np.abs(diff))[:10]
    for r in worst:
        print(f"  row {r:3d}: OC={sv_oc[r]:+.4e}, Karr={sv_karr[r]:+.4e}, diff={diff[r]:+.4e}")

# Critical: are the WRITEBACK-RELEVANT flux indices equal?
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture
fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))

print(f"\n=== Writeback-relevant flux comparison ===")
print(f"External exchange ({len(fbf.fba_idx_external)} cols):")
ext_diff = v_oc[fbf.fba_idx_external] - flux_karr[fbf.fba_idx_external]
print(f"  sum_abs OC: {np.abs(v_oc[fbf.fba_idx_external]).sum():.4e}")
print(f"  sum_abs Karr: {np.abs(flux_karr[fbf.fba_idx_external]).sum():.4e}")
print(f"  diff sum_abs: {np.abs(ext_diff).sum():.4e}")
print(f"  diff max_abs: {np.abs(ext_diff).max():.4e}")
print(f"  cells with |diff| > 1: {int((np.abs(ext_diff) > 1).sum())} / {len(ext_diff)}")

print(f"\nInternal exchange ({len(fbf.fba_idx_internal)} cols):")
int_diff = v_oc[fbf.fba_idx_internal] - flux_karr[fbf.fba_idx_internal]
print(f"  sum_abs OC: {np.abs(v_oc[fbf.fba_idx_internal]).sum():.4e}")
print(f"  sum_abs Karr: {np.abs(flux_karr[fbf.fba_idx_internal]).sum():.4e}")
print(f"  diff sum_abs: {np.abs(int_diff).sum():.4e}")
print(f"  diff max_abs: {np.abs(int_diff).max():.4e}")
print(f"  cells with |diff| > 1: {int((np.abs(int_diff) > 1).sum())} / {len(int_diff)}")
