from opencell.m1 import karr_metabolism as km
import numpy as np

m = km.load_default()
obj = m.obj
print(f"obj shape: {obj.shape}")
nz = np.nonzero(obj)[0]
print(f"Nonzero coefs: {len(nz)}")
print("Top 10 by abs(coef):")
order = np.argsort(-np.abs(obj))
for i in order[:10]:
    print(f"  idx={i:4d}  coef={obj[i]:+.6e}")
print(f"\nBiomass col: {m.biomass_col}, obj[biomass]={obj[m.biomass_col]:+.6e}")
print(f"Karr expected: 36 nonzero (1 biomass at +1000, 35 small parsimony)")

# All nonzero coefs
print(f"\nAll {len(nz)} nonzero coefficients:")
for i in nz:
    print(f"  idx={i:4d}  coef={obj[i]:+.6e}")
