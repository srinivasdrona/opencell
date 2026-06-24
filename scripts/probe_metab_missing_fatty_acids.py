"""Why are HDCEA, HDCA missing and OCDCEA sign-flipped in OC's writeback?

Karr at tick 0:
  HDCEA: -7919 (extracellular nutrient uptake)
  HDCA:  -7918
  OCDCEA: -6741

OC after Day-38 writeback:
  HDCEA: 0
  HDCA:  0
  OCDCEA: +1000  (wrong sign!)

Hypotheses to check:
  H1: These substrates aren't in sub_idx_external (mapping bug)
  H2: They are in sub_idx_external but FBA flux for the corresponding exchange reaction is zero/wrong
  H3: They're being applied but Step 5 clip eats the delta because pre-state is near zero
  H4: OCDCEA: applied correctly to extracellular, but step 3 biomass adds +N to membrane row, cancelling
       OR sub_idx_external for OCDCEA points to a different substrate row
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture, CYTOSOL, EXTRACELLULAR, MEMBRANE
from opencell.m1 import karr_metabolism as km

fix = KarrWritebackFixture.from_mat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"))
model = km.load_default()
sub_ids = list(model.raw["ids"]["substrate_wcm_585"])

target_wids = ["HDCEA", "HDCA", "OCDCEA"]
print(f"=== H1: Are HDCEA/HDCA/OCDCEA in sub_idx_external? ===")
for wid in target_wids:
    try:
        row = sub_ids.index(wid)
    except ValueError:
        print(f"  {wid}: NOT in OC's 585-substrate list at all!")
        continue
    in_ext = row in fix.sub_idx_external
    in_int = row in fix.sub_idx_internal
    in_atp = row in fix.sub_idx_atp_hydrolysis
    in_met = row in fix.metabolite_row_idx
    print(f"  {wid}: row={row}, in_external={in_ext}, in_internal={in_int}, "
          f"in_atp_hydro={in_atp}, in_metabolite_rows={in_met}")

print(f"\n=== H4 / Step 3 contribution at these rows ===")
print(f"metabolism_new_production has shape {fix.metabolism_new_production.shape}")
for wid in target_wids:
    try:
        row = sub_ids.index(wid)
    except ValueError:
        continue
    cyto = fix.metabolism_new_production[row, CYTOSOL]
    extr = fix.metabolism_new_production[row, EXTRACELLULAR]
    memb = fix.metabolism_new_production[row, MEMBRANE]
    print(f"  {wid}[row={row}]: biomass per unit growth — cytosol={cyto:.2e}, "
          f"extracellular={extr:.2e}, membrane={memb:.2e}")

print(f"\n=== H2: External exchange FBA flux at these rows ===")
# Run OC's dynamic-bounds FBA at karr tick-0 pre-state to see the actual flux
import scipy.io as sio
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T   # (585, 3)
    enz_before = get3d("states_before/enzymes", 0).ravel()

# Need to run FBA via the dynamic_bounds path; easiest is via _metabolism_process
from _l2_2_design_a_runner_helpers import _metabolism_process
proc = _metabolism_process(0)
proc._sub_state = karr_pre.copy()
if len(enz_before) == len(proc._enz_state):
    proc._enz_state = enz_before.copy()
states = {
    "substrates": {sid: float(karr_pre[i, 0]) for i, sid in enumerate(sub_ids)},
    "enzymes": {ew: float(enz_before[i]) if i < len(enz_before) else 0.0 for i, ew in enumerate(proc.enzyme_wids)},
    "boundEnzymes": {ew: 0.0 for ew in proc.enzyme_wids},
    "metabolic_reaction": {},
    "m1_pools": {},
    "trace_hint": {},
}

# Disable writeback temporarily so we can inspect raw FBA fluxes
proc.enable_karr_substrate_writeback = False
update = proc.next_update(1.0, states)
proc.enable_karr_substrate_writeback = True

flux_dict = update.get("metabolic_reaction", {}).get("fluxs", {})
growth = update.get("metabolic_reaction", {}).get("growth_per_s", 0.0)
print(f"OC growth_per_s: {growth:.4e}")

# Find external exchange flux for each target wid
# fba_idx_external is the (124,) array of FBA column indices for external exchange
# sub_idx_external[k] is the substrate row that fba_idx_external[k] exchanges
for wid in target_wids:
    try:
        row = sub_ids.index(wid)
    except ValueError:
        continue
    # find index in sub_idx_external where row matches
    k_arr = np.where(fix.sub_idx_external == row)[0]
    if len(k_arr) == 0:
        print(f"  {wid}: row {row} not in sub_idx_external (already showed in H1)")
        continue
    k = int(k_arr[0])
    fba_col = int(fix.fba_idx_external[k])
    # Map FBA col index to rxn_wid
    fba_col_rxn = model.fba_col_rxn_wcm
    rxn_wid = fba_col_rxn[fba_col] if fba_col < len(fba_col_rxn) else None
    rxn_flux = flux_dict.get(rxn_wid, "not_in_flux_dict") if rxn_wid else "no_wid_mapping"
    # Also the v_504 raw value (we don't have direct access but flux_dict is v_504 reformatted)
    print(f"  {wid}: fba_col={fba_col}, rxn_wid={rxn_wid}, flux_per_s={rxn_flux}")
    # What does Karr have for the same wid at extracellular?
    karr_ext_delta = -7919 if wid == "HDCEA" else (-7918 if wid == "HDCA" else -6741)
    expected_flux = -karr_ext_delta / 1.0  # delta = -stochRound(flux * step), so flux = -delta/step
    print(f"     Expected flux from Karr delta: {expected_flux:+.0f} mol/sec")

print(f"\n=== H3: pre_state at these (row, extracellular) cells ===")
for wid in target_wids:
    try:
        row = sub_ids.index(wid)
    except ValueError:
        continue
    pre_cyt = karr_pre[row, CYTOSOL]
    pre_ext = karr_pre[row, EXTRACELLULAR]
    pre_mem = karr_pre[row, MEMBRANE]
    print(f"  {wid}[row={row}] Karr pre: cytosol={pre_cyt:.0f}, "
          f"extracellular={pre_ext:.0f}, membrane={pre_mem:.0f}")

# Check fba_reaction bounds for the exchange reactions of these target wids
print(f"\n=== FBA bounds for target external exchange reactions ===")
for wid in target_wids:
    try:
        row = sub_ids.index(wid)
    except ValueError:
        continue
    k_arr = np.where(fix.sub_idx_external == row)[0]
    if len(k_arr) == 0:
        continue
    k = int(k_arr[0])
    fba_col = int(fix.fba_idx_external[k])
    static_lb = model.lb[fba_col]
    static_ub = model.ub[fba_col]
    print(f"  {wid} fba_col={fba_col}: STATIC lb={static_lb}, ub={static_ub}")
