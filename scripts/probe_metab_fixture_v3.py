"""Show raw keys."""
import scipy.io as sio
d = sio.loadmat("data/karr_fixtures/per_process/Metabolism_flat.mat")
print("RAW KEYS:", list(d.keys()))
for k, v in d.items():
    if k.startswith("_"):
        continue
    print(f"  {k}: type={type(v).__name__}", end="")
    if hasattr(v, "shape"):
        print(f" shape={v.shape} dtype={getattr(v, 'dtype', '?')}")
    else:
        print()
