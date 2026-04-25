"""Inspect metabolism_dynamics.mat contents (v7.3 HDF5)."""
import h5py
import numpy as np

with h5py.File('data/m1_sources/karr_flat/metabolism_dynamics.mat', 'r') as f:
    def walk(name, obj):
        if isinstance(obj, h5py.Dataset):
            print(f"  {name}: shape={obj.shape} dtype={obj.dtype}")
    f.visititems(walk)
    # Top-level
    print("--- top-level keys ---")
    for k in f.keys():
        v = f[k]
        if isinstance(v, h5py.Dataset):
            print(f"  {k}: shape={v.shape} dtype={v.dtype}")
        else:
            print(f"  {k}: group with members {list(v.keys())[:5]}...")
