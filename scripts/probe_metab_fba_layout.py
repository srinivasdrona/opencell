"""Check FBA model column layout vs fixture indexs."""
from opencell.m1 import karr_metabolism as km
import scipy.io as sio
import numpy as np

m = km.load_default()
print(f"OC FBA S shape: {m.S.shape}")
print(f"OC lb len: {len(m.lb)}, ub len: {len(m.ub)}")
print(f"OC fba_col_rxn_wcm len: {len(m.fba_col_rxn_wcm)}")

d = sio.loadmat("data/karr_fixtures/per_process/Metabolism_flat.mat", squeeze_me=True, struct_as_record=False)
fix = d["data"].fixture
print(f"\nKarr fbaReactionStoichiometryMatrix shape: {fix.fbaReactionStoichiometryMatrix.shape}")
print(f"Karr fbaReactionIndexs_metaboliteExternalExchange: min={fix.fbaReactionIndexs_metaboliteExternalExchange.min()}, max={fix.fbaReactionIndexs_metaboliteExternalExchange.max()}, count={len(fix.fbaReactionIndexs_metaboliteExternalExchange)}")
print(f"Karr fbaReactionIndexs_metaboliteInternalExchange: min={fix.fbaReactionIndexs_metaboliteInternalExchange.min()}, max={fix.fbaReactionIndexs_metaboliteInternalExchange.max()}, count={len(fix.fbaReactionIndexs_metaboliteInternalExchange)}")
print(f"Karr fbaReactionIndexs_metabolicConversion: count={len(fix.fbaReactionIndexs_metabolicConversion)}, min={fix.fbaReactionIndexs_metabolicConversion.min()}, max={fix.fbaReactionIndexs_metabolicConversion.max()}")
print(f"Karr fbaReactionIndexs_biomassProduction: {fix.fbaReactionIndexs_biomassProduction}")
print(f"Karr fbaReactionIndexs_biomassExchange: {fix.fbaReactionIndexs_biomassExchange}")
