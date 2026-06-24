"""Compare OC bounds to Karr's expected bounds at ALL 504 reactions.

Hypothesis: if OC and Karr have IDENTICAL bounds + IDENTICAL objective + IDENTICAL S,
but different fluxes, then it's degeneracy. Otherwise the bound difference is the bug.

Reconstruct Karr's expected bounds at tick-0 by replicating calcFluxBounds.m line by line
from the fixture data, and compare to what OC produces.
"""
import sys
from pathlib import Path
import numpy as np
import h5py
from scipy.io import loadmat

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

# Load all the pieces
model = km.load_default()
dyn = cfb.load_default_dynamics()
mat = loadmat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"),
              squeeze_me=True, struct_as_record=False)
fix = mat["data"].fixture

# Karr fixture indices (1-based -> 0-based)
def to0(arr): return np.asarray(arr, dtype=np.int64) - 1

idx_metabolic = to0(fix.fbaReactionIndexs_metabolicConversion)
idx_int_ex   = to0(fix.fbaReactionIndexs_metaboliteInternalExchange)
idx_int_lim  = to0(fix.fbaReactionIndexs_metaboliteInternalLimitedExchange)
idx_ext_ex   = to0(fix.fbaReactionIndexs_metaboliteExternalExchange)
idx_biomass  = int(fix.fbaReactionIndexs_biomassExchange) - 1
idx_biomass_prod = int(fix.fbaReactionIndexs_biomassProduction) - 1
sub_idx_int_lim = to0(fix.substrateIndexs_internalExchangedLimitedMetabolites)
sub_idx_ext   = to0(fix.substrateIndexs_externalExchangedMetabolites)
fba_rxn_bounds = np.asarray(fix.fbaReactionBounds, dtype=np.float64)
fba_enz_bounds = np.asarray(fix.fbaEnzymeBounds, dtype=np.float64)
catalysis_matrix = np.asarray(fix.fbaReactionCatalysisMatrix, dtype=np.float64)

# Load Karr tick-0
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T
    karr_enz = get3d("states_before/enzymes", 0).ravel()

# Karr cell_dry_mass (sum) — fixture mass is opaque, use OC's value (3.94e-15 g)
cell_dry_mass_karr = float(dyn.cell_dry_mass)
step_size = float(fix.stepSizeSec)
print(f"OC dyn.cell_dry_mass: {dyn.cell_dry_mass:.6e}")
print(f"stepSizeSec: {step_size}")

# IMPLEMENT Karr calcFluxBounds.m line by line
def karr_calc_bounds(substrates_585x3, enzymes_104, cell_dry_mass):
    n = 504
    lb = -np.inf * np.ones(n)
    ub =  np.inf * np.ones(n)
    rxn_enz = catalysis_matrix @ enzymes_104  # (504,)
    # Rule 1: enzyme kinetic
    lb = np.maximum(lb, fba_enz_bounds[:, 0] * rxn_enz)
    ub = np.minimum(ub, fba_enz_bounds[:, 1] * rxn_enz)
    # Rule 2: enzyme presence
    catalyzed_mask = np.any(catalysis_matrix, axis=1)
    zero_mask = catalyzed_mask & (rxn_enz <= 0)
    lb[zero_mask] = 0
    ub[zero_mask] = 0
    # Rule 3: directionality (metabolic, internal exchange, biomass prod, biomass exchange)
    for idx in [idx_metabolic, idx_int_ex, np.array([idx_biomass]), np.array([idx_biomass_prod])]:
        lb[idx] = np.maximum(lb[idx], fba_rxn_bounds[idx, 0])
        ub[idx] = np.minimum(ub[idx], fba_rxn_bounds[idx, 1])
    # Rule 4: external metabolite availability
    ub[idx_ext_ex] = np.minimum(
        ub[idx_ext_ex],
        substrates_585x3[sub_idx_ext, 1] / step_size  # compartmentIndexs_extracellular=1 (0-based)
    )
    lb[idx_ext_ex] = np.maximum(lb[idx_ext_ex], fba_rxn_bounds[idx_ext_ex, 0] * cell_dry_mass)
    ub[idx_ext_ex] = np.minimum(ub[idx_ext_ex], fba_rxn_bounds[idx_ext_ex, 1] * cell_dry_mass)
    # Rule 5: internal metabolite availability
    lb[idx_int_lim] = np.maximum(
        lb[idx_int_lim],
        -substrates_585x3[sub_idx_int_lim, 0] / step_size  # cytosol col 0
    )
    return lb, ub

karr_lb, karr_ub = karr_calc_bounds(karr_pre, karr_enz, cell_dry_mass_karr)
print(f"\nKarr-emulated bounds: lb sum_abs={np.abs(karr_lb[np.isfinite(karr_lb)]).sum():.0f}, "
      f"ub sum_abs={np.abs(karr_ub[np.isfinite(karr_ub)]).sum():.0f}")

# OC compute_bounds
fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)
oc_bounds = cfb.compute_bounds(
    substrates=karr_pre, enzymes=karr_enz,
    cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
    catalysis=model.catalysis, enz_bounds=model.enz_bounds,
    fba_reaction_bounds=fba_reaction_bounds, dyn=dyn,
    apply_protein_bounds=False,
)
oc_lb = oc_bounds[:, 0]
oc_ub = oc_bounds[:, 1]

# Compare row by row
print(f"\nOC bounds: lb sum_abs={np.abs(oc_lb[np.isfinite(oc_lb)]).sum():.0f}, "
      f"ub sum_abs={np.abs(oc_ub[np.isfinite(oc_ub)]).sum():.0f}")

# Diff (handling inf)
def safe_diff(a, b):
    both_inf_same = (np.isinf(a) & np.isinf(b) & (np.sign(a) == np.sign(b)))
    finite = np.isfinite(a) & np.isfinite(b)
    diff = np.where(finite, np.abs(a - b), 0)
    return diff, both_inf_same, finite

lb_diff, lb_inf_same, lb_finite = safe_diff(oc_lb, karr_lb)
ub_diff, ub_inf_same, ub_finite = safe_diff(oc_ub, karr_ub)
print(f"\nFinite-element diffs:")
print(f"  lb: nnz_diff>1e-3 = {(lb_diff > 1e-3).sum()} / {lb_finite.sum()} finite")
print(f"  ub: nnz_diff>1e-3 = {(ub_diff > 1e-3).sum()} / {ub_finite.sum()} finite")
print(f"Inf mismatch (one inf, other finite or different sign):")
lb_inf_mismatch = (np.isinf(oc_lb) != np.isinf(karr_lb)) | (np.isinf(oc_lb) & np.isinf(karr_lb) & (np.sign(oc_lb) != np.sign(karr_lb)))
ub_inf_mismatch = (np.isinf(oc_ub) != np.isinf(karr_ub)) | (np.isinf(oc_ub) & np.isinf(karr_ub) & (np.sign(oc_ub) != np.sign(karr_ub)))
print(f"  lb inf mismatch: {lb_inf_mismatch.sum()}")
print(f"  ub inf mismatch: {ub_inf_mismatch.sum()}")

# Top 10 disagreements
print(f"\nTop 10 ub differences (OC - Karr):")
worst = np.argsort(-(ub_diff + ub_inf_mismatch.astype(float) * 1e20))[:10]
for i in worst:
    print(f"  col {i}: OC.ub={oc_ub[i]:+.4e}, Karr.ub={karr_ub[i]:+.4e}, diff={oc_ub[i]-karr_ub[i] if np.isfinite(oc_ub[i]) and np.isfinite(karr_ub[i]) else 'inf':}")
print(f"\nTop 10 lb differences:")
worst = np.argsort(-(lb_diff + lb_inf_mismatch.astype(float) * 1e20))[:10]
for i in worst:
    print(f"  col {i}: OC.lb={oc_lb[i]:+.4e}, Karr.lb={karr_lb[i]:+.4e}")

# Now solve with KARR bounds and see if HDCA flux moves
print()
print("="*70)
print("SOLVE FBA WITH KARR-RECONSTRUCTED BOUNDS (vs OC's bounds)")
print("="*70)
big = 1e18
for label, lb_use, ub_use in [("OC bounds", oc_lb, oc_ub), ("Karr-emulated bounds", karr_lb, karr_ub)]:
    lb_clipped = np.where(np.isfinite(lb_use), lb_use, -big)
    ub_clipped = np.where(np.isfinite(ub_use), ub_use, big)
    v, info = km.solve_fba(
        model, use_full_objective=True, sense="max",
        lb_override=lb_clipped, ub_override=ub_clipped,
    )
    print(f"\n--- {label} ---")
    print(f"  growth_per_s: {info['biomass_flux_per_s']:.6e}")
    fbf = KarrWritebackFixture.from_mat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"))
    targets = [("HDCA", 300), ("HDCEA", 301), ("OCDCEA", 439)]
    for wid, row in targets:
        k_arr = np.where(fbf.sub_idx_external == row)[0]
        if len(k_arr) == 0: continue
        k = int(k_arr[0])
        col = int(fbf.fba_idx_external[k])
        print(f"  {wid} col={col}: flux={v[col]:+.2f}, lb={lb_use[col]:+.2f}, ub={ub_use[col]:+.2f}")
    at_ub = (np.abs(v[idx_ext_ex] - ub_use[idx_ext_ex]) < 1e-3).sum()
    at_lb = (np.abs(v[idx_ext_ex] - lb_use[idx_ext_ex]) < 1e-3).sum()
    print(f"  External: at_lb={at_lb}, at_ub={at_ub}, interior={124-at_lb-at_ub}")
