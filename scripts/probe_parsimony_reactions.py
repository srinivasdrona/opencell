from opencell.m1 import karr_metabolism as km
import numpy as np

m = km.load_default()
rxn_ids = m.rxn_wcm_ids_645  # may have None for non-FBA columns
fba_rxns = m.fba_col_rxn_wcm if hasattr(m, 'fba_col_rxn_wcm') else None

print(f"Model has {len(rxn_ids)} reactions total")
# Find names for the 35 parsimony-penalized cols (idx 460-500)
print()
print("Penalized columns 460-500 (parsimony reactions):")
nz = np.nonzero(m.obj)[0]
for idx in sorted(nz):
    if idx == m.biomass_col:
        continue
    # rxn_ids is what? Let me check shape
    if fba_rxns is not None and idx < len(fba_rxns):
        name = fba_rxns[idx]
    else:
        name = f"col_{idx}"
    print(f"  col {idx}: {name}")

# Also try .raw structure
print()
print("Model raw keys:", list(m.raw.keys())[:20])
if 'ids' in m.raw:
    print("ids keys:", list(m.raw['ids'].keys()))
    # Look for fba reaction ids
    for k in m.raw['ids']:
        v = m.raw['ids'][k]
        if hasattr(v, '__len__') and len(v) == 504:
            print(f"  {k} has 504 entries")
            for idx in sorted(nz)[:10]:
                print(f"    col {idx}: {v[idx]}")
            break
