"""Quick inspection: Metabolism fixture keys + substrates port shape across consumers."""
import scipy.io as sio
import numpy as np

d = sio.loadmat("data/karr_fixtures/per_process/Metabolism_flat.mat")
keys = sorted(k for k in d if not k.startswith("_"))
print(f"Total keys: {len(keys)}")

print("\n=== substrate-related ===")
for k in keys:
    if "substrate" in k.lower():
        v = d[k]
        if hasattr(v, "shape"):
            print(f"  {k}: shape={v.shape} dtype={v.dtype}")

print("\n=== compartment-related ===")
for k in keys:
    if "compartment" in k.lower():
        v = d[k]
        if hasattr(v, "shape"):
            print(f"  {k}: shape={v.shape} dtype={v.dtype}")

print("\n=== fixture for Karr 4-step writeback ===")
for k in [
    "substrateIndexs_externalExchangedMetabolites",
    "substrateIndexs_internalExchangedMetabolites",
    "substrateIndexs_atpHydrolysis",
    "fbaReactionIndexs_metaboliteExternalExchange",
    "fbaReactionIndexs_metaboliteInternalExchange",
    "metabolismNewProduction",
    "unaccountedEnergyConsumption",
]:
    v = d.get(k)
    if v is None:
        # try fuzzy match
        cands = [kk for kk in keys if k.lower().replace("_", "") in kk.lower().replace("_", "")]
        print(f"  {k}: NOT FOUND directly; candidates: {cands[:3]}")
    else:
        print(f"  {k}: shape={v.shape} dtype={v.dtype}")
