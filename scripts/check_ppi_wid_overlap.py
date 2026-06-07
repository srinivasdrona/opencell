"""Verify CAUSE_4 hypothesis: PPI unprocessed/processed monomer WID overlap."""
from scipy.io import loadmat

mat = loadmat("data/karr_fixtures/per_process/ProteinProcessingI_flat.mat")
fx = mat["data"]["fixture"][0, 0]


def parse(arr):
    out = []
    a = arr
    if a.shape == (1, 1):
        a = a[0, 0]
    for r in a.ravel():
        v = r
        while hasattr(v, "flat"):
            if v.size == 0:
                v = ""
                break
            v = v.flat[0]
        out.append(str(v))
    return out


u = parse(fx["unprocessedMonomerWholeCellModelIDs"])
p = parse(fx["processedMonomerWholeCellModelIDs"])
print(f"PPI unprocessed n={len(u)}, processed n={len(p)}")
print(f"  identical positional lists? {u == p}")
print(f"  set-overlap count: {len(set(u) & set(p))}")
print(f"  first 5 unprocessed: {u[:5]}")
print(f"  first 5 processed:   {p[:5]}")
print(f"  same at index 0? {u[0] == p[0] if u and p else None}")

mat2 = loadmat("data/karr_fixtures/per_process/ProteinProcessingII_flat.mat")
fx2 = mat2["data"]["fixture"][0, 0]
u2 = parse(fx2["unprocessedMonomerWholeCellModelIDs"])
p2 = parse(fx2["processedMonomerWholeCellModelIDs"])
print(f"PPII unprocessed n={len(u2)}, processed n={len(p2)}")
print(f"  identical positional lists? {u2 == p2}")
print(f"  set-overlap count: {len(set(u2) & set(p2))}")

print("---")
print(f"PPI.unprocessed ∩ PPII.unprocessed (PPI's writes -> PPII's reads): "
      f"{len(set(u) & set(u2))}")
print(f"PPI.processed   ∩ PPII.unprocessed (PPI's processed writes leaking to PPII inputs): "
      f"{len(set(p) & set(u2))}")
