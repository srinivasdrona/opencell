"""Probe Karr's index semantics for substrate writeback.

Critical question: are substrateIndexs_internalExchangedMetabolites (42,) and
substrateIndexs_atpHydrolysis (5,) row indices (into cytosol col 1) or LINEAR
indices into the (585, 3) matrix?

MATLAB linear-index formula for (row, col) in (585, 3) is:
  linidx_1based = row + (col-1)*585
  -> row in [1,585]: cytosol col 1
  -> row in [586,1170]: extracellular col 2
  -> row in [1171,1755]: membrane col 3

So if max(values) <= 585, they're cytosol-only row indices.
"""
import scipy.io as sio
import numpy as np

d = sio.loadmat("data/karr_fixtures/per_process/Metabolism_flat.mat", squeeze_me=True, struct_as_record=False)
fix = d["data"].fixture

# Compartment indexs (1-based)
print("compartmentIndexs_cytosol:", fix.compartmentIndexs_cytosol)
print("compartmentIndexs_extracellular:", fix.compartmentIndexs_extracellular)
print("compartmentIndexs_membrane:", fix.compartmentIndexs_membrane)
print()

for name in [
    "substrateIndexs_externalExchangedMetabolites",
    "substrateIndexs_internalExchangedMetabolites",
    "substrateIndexs_atpHydrolysis",
]:
    v = getattr(fix, name)
    print(f"{name}:")
    print(f"  shape={v.shape} dtype={v.dtype}")
    print(f"  min={v.min()} max={v.max()}")
    print(f"  values: {v}")
    # Decode linear indexing
    if v.max() <= 585:
        print(f"  -> all <= 585, so these are substrate-row indices (1-based)")
        print(f"     when used in single-arg form, they target cytosol (col 1)")
    else:
        # decode as linear indices
        v0 = v - 1  # 0-based linear
        rows = v0 % 585
        cols = v0 // 585
        print(f"  -> LINEAR indices into (585, 3)")
        print(f"     rows (0-based): {rows}")
        print(f"     cols (0-based): {cols}  (0=cyt, 1=ext, 2=mem)")
        from collections import Counter
        print(f"     col distribution: {dict(Counter(cols.tolist()))}")
    print()

# Also check the FBA reaction indexs sizes vs substrate idxs
for name in ["fbaReactionIndexs_metaboliteExternalExchange", "fbaReactionIndexs_metaboliteInternalExchange"]:
    v = getattr(fix, name)
    print(f"{name}: shape={v.shape} min={v.min()} max={v.max()}")

# Check metabolismNewProduction shape
print(f"\nmetabolismNewProduction: shape={fix.metabolismNewProduction.shape}")
print(f"  type={type(fix.metabolismNewProduction).__name__} dtype={fix.metabolismNewProduction.dtype}")
mnp = fix.metabolismNewProduction
print(f"  nonzero entries: {int((mnp != 0).sum())} / {mnp.size}")
# Per compartment
for c in range(mnp.shape[1]):
    print(f"  compartment col {c}: nonzero={int((mnp[:, c] != 0).sum())}, sum={mnp[:, c].sum():.3f}")

print(f"\nunaccountedEnergyConsumption: type={type(fix.unaccountedEnergyConsumption).__name__}")
print(f"  value: {fix.unaccountedEnergyConsumption}")

print(f"\nstepSizeSec: {fix.stepSizeSec}")
print(f"growthAssociatedMaintenance: {fix.growthAssociatedMaintenance}")
print(f"nonGrowthAssociatedMaintenance: {fix.nonGrowthAssociatedMaintenance}")
