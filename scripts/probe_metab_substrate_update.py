"""Probe Karr substrate-update algorithm against recorded states_after at tick 0.

Validates the 4 Karr substrate updates (evolveState lines 1213-1231):
  1. Nutrient uptake: external -= round(flux_external × stepSize)
  2. Recycled metabolites: internal += round(flux_internal)
  3. New biomass: all += round(metabolismNewProduction × growth × stepSize)
  4. Unaccounted energy: ATP/ADP/Pi/H2O/H deltas

If our algorithm matches Karr's recorded substrate delta at tick 0, we can wire
it into Metabolism.next_update with confidence.
"""
from __future__ import annotations
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.compartmented import load_default as load_compartmented

# Load fixture data
fix_path = _REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
mat = loadmat(str(fix_path), squeeze_me=True, struct_as_record=False)
fixture = mat["data"].fixture

# 1-based → 0-based MATLAB index conversion
def matlab_idx(arr):
    return np.asarray(arr, dtype=np.int64) - 1

sub_idx_external = matlab_idx(fixture.substrateIndexs_externalExchangedMetabolites)  # (124,)
sub_idx_internal = matlab_idx(fixture.substrateIndexs_internalExchangedMetabolites)  # (42,)
sub_idx_atp_hydrolysis = matlab_idx(fixture.substrateIndexs_atpHydrolysis)  # (5,)
fba_idx_external = matlab_idx(fixture.fbaReactionIndexs_metaboliteExternalExchange)  # (124,)
fba_idx_internal = matlab_idx(fixture.fbaReactionIndexs_metaboliteInternalExchange)  # (42,)
metab_new_production = np.asarray(fixture.metabolismNewProduction, dtype=np.float64)  # (585, 3)
unaccounted_energy = float(fixture.unaccountedEnergyConsumption)
step_size_sec = float(fixture.stepSizeSec)
sub_wids_585 = list(fixture.substrateWholeCellModelIDs)
extracellular_idx = 2  # MATLAB compartmentIndexs_extracellular - 1 (1-based to 0-based)
# Per Metabolism.m: compartmentIndexs_cytosol=1, compartmentIndexs_extracellular=2, compartmentIndexs_membrane=3
# In MATLAB indices, so 0-based: cytosol=0, extracellular=1, membrane=2
extracellular_idx = 1
cytosol_idx = 0

print(f"Loaded Metabolism fixture: 585 substrates × 3 compartments × 645 reactions")
print(f"  External exchange substrates: {len(sub_idx_external)}")
print(f"  Internal exchange substrates: {len(sub_idx_internal)}")
print(f"  ATP hydrolysis substrates: {len(sub_idx_atp_hydrolysis)}")
print(f"  unaccountedEnergyConsumption: {unaccounted_energy}")
print(f"  stepSizeSec: {step_size_sec}")

# Load Karr's per-tick trace
trace_path = _REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
if not trace_path.exists():
    trace_path = _REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / "Metabolism_100ticks.mat"
print(f"\nLoading trace: {trace_path}")

with h5py.File(trace_path, "r") as handle:
    # Look for states_before / states_after at tick 0 with full 585x3 substrate matrix
    def get_3d(group_path: str, tick: int) -> np.ndarray:
        ds = handle[group_path]
        rows, cols = int(ds.shape[0]), int(ds.shape[1])
        if rows == 1 and cols >= (tick + 1):
            ref = ds[0, tick]
        elif cols == 1 and rows >= (tick + 1):
            ref = ds[tick, 0]
        else:
            ref = ds[tick, 0] if rows >= (tick + 1) else ds[0, tick]
        return np.asarray(handle[ref][()], dtype=np.float64)

    # substrates field: 585 × 3 (full compartmented)
    karr_sub_before = get_3d("states_before/substrates", 0)
    karr_sub_after = get_3d("states_after/substrates", 0)
    print(f"\nKarr substrate matrix shape (before): {karr_sub_before.shape}")
    print(f"Karr substrate matrix shape (after): {karr_sub_after.shape}")

    # Check what other keys exist
    sb = handle["states_before"]
    print(f"\nstates_before keys: {list(sb.keys())}")
    sa = handle["states_after"]
    print(f"states_after keys: {list(sa.keys())}")

    if "metabolicReaction" in sa:
        mr = sa["metabolicReaction"]
        print(f"\nmetabolicReaction keys: {list(mr.keys())}")
        if "growth" in mr:
            growth_after = get_3d("states_after/metabolicReaction/growth", 0)
            print(f"growth at tick 0 (after): shape={growth_after.shape}, value={growth_after.ravel()[0] if growth_after.size else None}")
        if "fluxs" in mr:
            fluxs_after = get_3d("states_after/metabolicReaction/fluxs", 0)
            print(f"fluxs at tick 0 (after): shape={fluxs_after.shape}, nonzero={np.count_nonzero(fluxs_after)}, max_abs={np.abs(fluxs_after).max():.4f}")

karr_delta = karr_sub_after - karr_sub_before
nz = np.count_nonzero(karr_delta)
print(f"\nKarr substrate delta at tick 0: nonzero={nz}, sum_abs={np.abs(karr_delta).sum():.1f}, max_abs={np.abs(karr_delta).max():.0f}")
if nz > 0 and nz <= 20:
    nz_idx = np.argwhere(karr_delta != 0)
    print(f"  First 20 nonzero deltas:")
    for si, ki in nz_idx[:20]:
        print(f"    {sub_wids_585[si]}[{ki}]: {karr_delta[si, ki]:+.0f}")

# Note: karr_sub_before/after are (3, 585) compartments × substrates per the trace.
# Transpose to (585, 3) to match Metabolism.m convention substrates(substrate, compartment).
karr_sub_before_585x3 = karr_sub_before.T  # (585, 3)
karr_sub_after_585x3 = karr_sub_after.T    # (585, 3)
karr_delta_585x3 = karr_sub_after_585x3 - karr_sub_before_585x3

# Now run FBA at tick 0 with default bounds (static path)
print("\n=== Running FBA with Karr's tick-0 pre-state ===")
model = km.load_default()
v_504, info = km.solve_fba(model, use_full_objective=True, sense="max")
print(f"FBA solved: {info['status']}, growth_per_s = {info['biomass_flux_per_s']:.6e}, n_nonzero={info['n_nonzero']}")

# Expand 504-col FBA to 645-col reaction space
rxn_wids_645 = list(model.raw["ids"]["reaction_wcm_645"])
fba_col_rxn = list(model.fba_col_rxn_wcm)
v_645 = np.zeros(645, dtype=np.float64)
for col, wid in enumerate(fba_col_rxn):
    if wid is None:
        continue
    try:
        r_idx = rxn_wids_645.index(wid)
    except ValueError:
        continue
    v_645[r_idx] += v_504[col]

growth = info["biomass_flux_per_s"]

# Apply Karr's 4 substrate updates (no stochastic rounding — use exact float for diagnosis)
# Compartments per Metabolism.m: 1=cytosol, 2=extracellular, 3=membrane (1-based)
# Convert to 0-based: 0=cytosol, 1=extracellular, 2=membrane
# (Karr's trace dim 0 is compartment per loadmat output above.)
karr_extra_cmp = 1   # extracellular
karr_cyto_cmp = 0    # cytosol

oc_delta = np.zeros((585, 3), dtype=np.float64)

# Step 1: nutrient uptake — external compartment loses molecules consumed by external exchange reactions
# substrates[sub_idx_external, extracellular_idx] -= flux[fba_idx_external] * step
oc_delta[sub_idx_external, karr_extra_cmp] -= v_645[fba_idx_external] * step_size_sec

# Step 2: recycled metabolites — internal exchange (substrates only, no compartment in MATLAB index)
# Per Karr code: this.substrates(internalIdxs) += stochasticRound(flux[internal])
# When you index substrates without a compartment, MATLAB returns ALL compartments. But Karr's code does
#   this.substrates(this.substrateIndexs_internalExchangedMetabolites) = + this.substrates(...) + stochRound(...)
# This is linear indexing in MATLAB; the 42 indices map to specific (substrate, compartment) pairs.
# For now use cytosol compartment as default; verify later.
oc_delta[sub_idx_internal, karr_cyto_cmp] += v_645[fba_idx_internal]

# Step 3: new biomass — full 585×3 += metabolismNewProduction × growth × step
oc_delta += metab_new_production * growth * step_size_sec

# Step 4: unaccounted energy on 5 ATP-hydrolysis substrates [-1, -1, +1, +1, +1]
atp_signs = np.array([-1, -1, 1, 1, 1], dtype=np.float64)
unaccounted_quantity = unaccounted_energy * growth * step_size_sec
oc_delta[sub_idx_atp_hydrolysis, karr_cyto_cmp] += atp_signs * unaccounted_quantity

print("\n=== Comparison (computed-without-stochastic-rounding vs Karr-recorded) ===")
diff = oc_delta - karr_delta_585x3
nz_diff = np.count_nonzero(np.abs(diff) > 1.0)
print(f"OC delta nonzero (>1 abs): {np.count_nonzero(np.abs(oc_delta) > 1.0)}")
print(f"Karr delta nonzero: {np.count_nonzero(np.abs(karr_delta_585x3) > 0)}")
print(f"Diff (OC - Karr) max_abs: {np.abs(diff).max():.2f}")
print(f"Diff sum_abs: {np.abs(diff).sum():.2f}")
print(f"Diff nonzero (>1): {nz_diff}")
print(f"Total OC sum_abs: {np.abs(oc_delta).sum():.2f}")
print(f"Total Karr sum_abs: {np.abs(karr_delta_585x3).sum():.2f}")

# Where are the biggest diffs?
if nz_diff > 0:
    print(f"\nTop 10 worst diffs (OC computed vs Karr recorded):")
    worst = np.argsort(-np.abs(diff).ravel())[:10]
    for flat in worst:
        si, ki = np.unravel_index(flat, diff.shape)
        print(f"  {sub_wids_585[si]}[cmp={ki}]: OC={oc_delta[si,ki]:+.1f}, Karr={karr_delta_585x3[si,ki]:+.1f}, diff={diff[si,ki]:+.1f}")

