"""Inspect Karr knowledgeBase.mat — try scipy first, fall back to h5py."""
import sys
import scipy.io as sio

PATH = r"E:\opencell\data\m1_sources\WholeCell\data\knowledgeBase.mat"

try:
    d = sio.loadmat(PATH, squeeze_me=False, struct_as_record=False)
    print("LOADED via scipy.io.loadmat (MAT v5)")
    keys = [k for k in d.keys() if not k.startswith("__")]
    print("top-level keys:", keys)
    none_obj = d["None"]
    print("'None' record:", none_obj.dtype, none_obj.shape)
    rec = none_obj[0]
    print("rec[0]:", type(rec).__name__)
    for fname in ("s0","s1","s2","arr"):
        v = rec[fname] if hasattr(rec, "dtype") else getattr(rec, fname, None)
        print(f"  {fname}: type={type(v).__name__} shape={getattr(v,'shape','-')} dtype={getattr(v,'dtype','-')}")
        # Drill in
        if hasattr(v, "shape") and v.size:
            sample = v.flat[0]
            print(f"    flat[0] type={type(sample).__name__}",
                  repr(sample)[:200] if not hasattr(sample,'shape') else f"shape={sample.shape}")
except NotImplementedError as e:
    print("SCIPY FAILED (MAT v7.3 HDF5):", e)
    try:
        import h5py
    except ImportError:
        print("h5py not installed; pip install h5py")
        sys.exit(1)
    with h5py.File(PATH, "r") as f:
        print("Loaded via h5py — top-level keys:", list(f.keys()))
        def walk(g, depth=0, max_depth=3):
            if depth > max_depth:
                return
            for k in g.keys():
                item = g[k]
                indent = "  " * depth
                if isinstance(item, h5py.Group):
                    print(f"{indent}{k}/ (group, {len(item)} children)")
                    walk(item, depth+1, max_depth)
                else:
                    print(f"{indent}{k}: shape={item.shape} dtype={item.dtype}")
        walk(f)
