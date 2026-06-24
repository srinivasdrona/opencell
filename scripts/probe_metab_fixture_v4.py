"""Unwrap the nested fixture struct."""
import scipy.io as sio
import numpy as np

d = sio.loadmat("data/karr_fixtures/per_process/Metabolism_flat.mat", squeeze_me=True, struct_as_record=False)
print("RAW KEYS:", [k for k in d.keys() if not k.startswith("_")])
fixture = d["data"].fixture
print("FIXTURE TYPE:", type(fixture).__name__)
print("FIXTURE FIELDS:", sorted(fixture._fieldnames))

print("\n=== substrate-related fields ===")
for k in sorted(fixture._fieldnames):
    if "substrate" in k.lower() or "compartment" in k.lower():
        v = getattr(fixture, k)
        if hasattr(v, "shape"):
            print(f"  {k}: shape={v.shape} dtype={v.dtype}")
        else:
            print(f"  {k}: type={type(v).__name__}")

print("\n=== required for Karr 4-step writeback ===")
for k in [
    "substrateIndexs_externalExchangedMetabolites",
    "substrateIndexs_internalExchangedMetabolites",
    "substrateIndexs_atpHydrolysis",
    "fbaReactionIndexs_metaboliteExternalExchange",
    "fbaReactionIndexs_metaboliteInternalExchange",
    "metabolismNewProduction",
    "unaccountedEnergyConsumption",
]:
    if k in fixture._fieldnames:
        v = getattr(fixture, k)
        if hasattr(v, "shape"):
            preview = v.flatten()[:5] if v.size > 0 else "EMPTY"
            print(f"  {k}: shape={v.shape} dtype={v.dtype} preview={preview}")
        else:
            print(f"  {k}: type={type(v).__name__} value={v}")
    else:
        # fuzzy search
        cands = [kk for kk in fixture._fieldnames if k.lower().replace("_", "").replace("idx", "").replace("indexs", "") in kk.lower().replace("_", "").replace("idx", "").replace("indexs", "")]
        print(f"  {k}: NOT FOUND; candidates: {cands}")

print("\n=== all 'Indexs' fields (Karr naming) ===")
for k in sorted(fixture._fieldnames):
    if "Indexs" in k or "indexs" in k:
        v = getattr(fixture, k)
        sh = getattr(v, "shape", "scalar")
        print(f"  {k}: shape={sh}")

print("\n=== all 'metabolism' / 'unaccounted' / 'production' fields ===")
for k in sorted(fixture._fieldnames):
    if any(s in k.lower() for s in ["metabolism", "unaccounted", "production", "biomass"]):
        v = getattr(fixture, k)
        sh = getattr(v, "shape", "scalar")
        print(f"  {k}: shape={sh}")
