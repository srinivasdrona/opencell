"""H1b/H1a refined: does OC model.lb/ub match Karr fixture fbaReactionBounds?

Rule 3 (directionality) clips to these bounds. If they differ from Karr's,
Rule 3 over-constrains and growth drops 4x.
"""
import sys
from pathlib import Path
import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km

model = km.load_default()
mat = loadmat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"),
              squeeze_me=True, struct_as_record=False)
fix = mat["data"].fixture

karr_bounds = np.asarray(fix.fbaReactionBounds, dtype=np.float64)  # (504, 2)
print(f"Karr fixture fbaReactionBounds: shape={karr_bounds.shape}")
print(f"OC model.lb shape: {model.lb.shape}, model.ub shape: {model.ub.shape}")

# Element-wise compare
lb_diff = np.where(np.isfinite(karr_bounds[:, 0]) & np.isfinite(model.lb),
                    np.abs(model.lb - karr_bounds[:, 0]), 0)
ub_diff = np.where(np.isfinite(karr_bounds[:, 1]) & np.isfinite(model.ub),
                    np.abs(model.ub - karr_bounds[:, 1]), 0)
print(f"\nFinite-element diffs:")
print(f"  lb: nnz>1e-6 = {(lb_diff > 1e-6).sum()} / 504, max_abs={lb_diff.max():.6e}")
print(f"  ub: nnz>1e-6 = {(ub_diff > 1e-6).sum()} / 504, max_abs={ub_diff.max():.6e}")

# Inf mismatch
lb_inf_mismatch = (np.isinf(model.lb) != np.isinf(karr_bounds[:, 0]))
ub_inf_mismatch = (np.isinf(model.ub) != np.isinf(karr_bounds[:, 1]))
print(f"  lb inf mismatch (one inf, other not): {lb_inf_mismatch.sum()}")
print(f"  ub inf mismatch: {ub_inf_mismatch.sum()}")

# Sign-of-inf mismatch
lb_sign_diff = np.isinf(model.lb) & np.isinf(karr_bounds[:, 0]) & (np.sign(model.lb) != np.sign(karr_bounds[:, 0]))
ub_sign_diff = np.isinf(model.ub) & np.isinf(karr_bounds[:, 1]) & (np.sign(model.ub) != np.sign(karr_bounds[:, 1]))
print(f"  lb both-inf-different-sign: {lb_sign_diff.sum()}")
print(f"  ub both-inf-different-sign: {ub_sign_diff.sum()}")

# Show first 10 disagreements (any)
print(f"\nTop 10 lb mismatches (where they differ):")
disagree = np.where((lb_diff > 1e-6) | lb_inf_mismatch | lb_sign_diff)[0]
for i in disagree[:10]:
    print(f"  col {i}: OC.lb={model.lb[i]:+.4e}, Karr.lb={karr_bounds[i, 0]:+.4e}")
print(f"\nTop 10 ub mismatches:")
disagree = np.where((ub_diff > 1e-6) | ub_inf_mismatch | ub_sign_diff)[0]
for i in disagree[:10]:
    print(f"  col {i}: OC.ub={model.ub[i]:+.4e}, Karr.ub={karr_bounds[i, 1]:+.4e}")

# Important context: which columns are in which subset (metab_conv, int_exch, biomass_*)
def to0(arr): return np.asarray(arr, dtype=np.int64) - 1
idx_metabolic = to0(fix.fbaReactionIndexs_metabolicConversion)  # 336
idx_int_ex   = to0(fix.fbaReactionIndexs_metaboliteInternalExchange)  # 42
idx_biomass  = int(fix.fbaReactionIndexs_biomassExchange) - 1
idx_biomass_prod = int(fix.fbaReactionIndexs_biomassProduction) - 1
idx_ext_ex   = to0(fix.fbaReactionIndexs_metaboliteExternalExchange)  # 124

print(f"\nColumns subject to Rule 3 (directionality):")
print(f"  metabolic_conversion: {len(idx_metabolic)} cols (cols 0..335)")
print(f"  internal_exchange:    {len(idx_int_ex)} cols (cols 460..501)")
print(f"  biomass_exchange:     1 col ({idx_biomass})")
print(f"  biomass_production:   1 col ({idx_biomass_prod})")
print(f"  TOTAL: {len(idx_metabolic) + len(idx_int_ex) + 2}")
print(f"\nColumns subject to Rule 4 (external_metabolite, NOT in rule 3):")
print(f"  external_exchange: {len(idx_ext_ex)} cols (cols 336..459)")

# Check rule-3 columns specifically
print(f"\n=== Per-subset bound diffs ===")
for name, idx in [("metabolic_conversion", idx_metabolic),
                   ("internal_exchange", idx_int_ex),
                   ("biomass_exchange", np.array([idx_biomass])),
                   ("biomass_production", np.array([idx_biomass_prod]))]:
    lb_d = (np.abs(model.lb[idx] - karr_bounds[idx, 0]) > 1e-6).sum()
    ub_d = (np.abs(model.ub[idx] - karr_bounds[idx, 1]) > 1e-6).sum()
    lb_im = (np.isinf(model.lb[idx]) != np.isinf(karr_bounds[idx, 0])).sum()
    ub_im = (np.isinf(model.ub[idx]) != np.isinf(karr_bounds[idx, 1])).sum()
    print(f"  {name}: lb diffs={lb_d}+{lb_im}inf, ub diffs={ub_d}+{ub_im}inf")
