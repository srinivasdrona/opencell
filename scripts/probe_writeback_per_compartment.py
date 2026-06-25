"""Direct flux check: what does Karr's GLPK put at PHE's external exchange column?"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture, apply_karr_substrate_writeback, EXTRACELLULAR, CYTOSOL,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metabolism_matlab_flux_growth.mat"
with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["fba_flux"][()], dtype=np.float64).reshape(-1)
    growth_karr = float(np.asarray(h["growth_per_s"][()]).reshape(-1)[0])

fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))
model = km.load_default()
sub_ids = list(model.raw["ids"]["substrate_wcm_585"])

print(f"Karr growth_per_s: {growth_karr:.6e}")
print()

# Find PHE position in the index arrays
for wid in ["PHE", "TYR", "TRIOLEIN", "PhePhe"]:
    if wid not in sub_ids:
        continue
    row = sub_ids.index(wid)
    k_arr = np.where(fbf.sub_idx_external == row)[0]
    if len(k_arr) == 0:
        print(f"{wid}: row {row}, NOT in sub_idx_external")
        continue
    k = int(k_arr[0])
    fba_col = int(fbf.fba_idx_external[k])
    flux_at_col = flux_karr[fba_col]
    mnp_row = fbf.metabolism_new_production[row, :]

    # Predict per-WID flat for this WID using the 4 steps
    step1_contrib_extracellular = -flux_at_col * 1.0  # stochRound omitted for clarity
    step3_contrib_cyto = mnp_row[CYTOSOL] * growth_karr
    step3_contrib_ext = mnp_row[EXTRACELLULAR] * growth_karr
    step3_contrib_mem = mnp_row[2] * growth_karr
    expected_flat = step1_contrib_extracellular + step3_contrib_cyto + step3_contrib_ext + step3_contrib_mem

    print(f"{wid:18s} (row={row:3d}, sub_idx_external position k={k}, fba_col={fba_col})")
    print(f"  Karr flux at fba_col={fba_col}: {flux_at_col:+.4e}")
    print(f"  Step 1 extracellular contribution: -flux*step = {step1_contrib_extracellular:+.2f}")
    print(f"  Step 3 cytosol contribution: mnp[cyto]*growth = {step3_contrib_cyto:+.2f}")
    print(f"  Step 3 extracellular contribution: {step3_contrib_ext:+.2f}")
    print(f"  Step 3 membrane contribution: {step3_contrib_mem:+.2f}")
    print(f"  PREDICTED per-WID flat (pre-stochRound): {expected_flat:+.2f}")
    print()

# Now actually run the writeback with Karr's flux and dump per-compartment for these WIDs
print("=" * 70)
print("Actual writeback delta breakdown per compartment (with Karr's flux)")
print("=" * 70)

# Load Karr pre-state
trace_path = REPO / "data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T
    karr_after = get3d("states_after/substrates", 0).T
karr_recorded_delta = karr_after - karr_pre

B_delta = apply_karr_substrate_writeback(
    pre_state_585x3=karr_pre, v_504=flux_karr, growth_per_s=growth_karr,
    fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
)

print(f"{'WID':18s} {'Cytosol':>10s} {'Extracellular':>15s} {'Membrane':>10s} {'Total':>10s}  vs  Karr_total")
for wid in ["PHE", "TYR", "TRIOLEIN", "PhePhe", "H", "H2O"]:
    if wid not in sub_ids:
        continue
    row = sub_ids.index(wid)
    my_cyto = B_delta[row, CYTOSOL]
    my_ext = B_delta[row, EXTRACELLULAR]
    my_mem = B_delta[row, 2]
    my_tot = my_cyto + my_ext + my_mem
    karr_cyto = karr_recorded_delta[row, CYTOSOL]
    karr_ext = karr_recorded_delta[row, EXTRACELLULAR]
    karr_mem = karr_recorded_delta[row, 2]
    karr_tot = karr_cyto + karr_ext + karr_mem
    print(f"{wid:18s} my:{my_cyto:>+7d} {my_ext:>+13d} {my_mem:>+7d} {my_tot:>+7d}  "
          f"karr:{int(karr_tot):>+5d} (cyto={int(karr_cyto):+d}, ext={int(karr_ext):+d}, mem={int(karr_mem):+d})")
