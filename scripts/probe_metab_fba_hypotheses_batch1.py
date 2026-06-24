"""Batch-probe the cheap, high-info FBA hypotheses (H2a, H3a, H5a, H5b, H6a, H1c).

H2a: OC objective vector differs from Karr
H3a: Some reactions sign-flipped in S matrix
H5a: Enzyme overlay shape mismatch
H5b: boundEnzymes not fed to compute_bounds
H6a: dynamics_inputs.substrates_snapshot stale vs Karr tick-0
H1c: cell_dry_mass wrong scale
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from scipy.io import loadmat

# Load OC model + dyn
model = km.load_default()
dyn = cfb.load_default_dynamics()

# Load Karr fixture
mat = loadmat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"),
              squeeze_me=True, struct_as_record=False)
fix = mat["data"].fixture

# Load Karr tick-0 pre-state
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre_sub = get3d("states_before/substrates", 0).T   # (585, 3)
    karr_pre_enz = get3d("states_before/enzymes", 0).ravel()
    karr_pre_bnd = get3d("states_before/boundEnzymes", 0).ravel()

print("="*70)
print("H2a: Compare OC objective to Karr fixture fbaObjective")
print("="*70)
print(f"OC model attributes: {[a for a in dir(model) if not a.startswith('_') and not callable(getattr(model, a))][:20]}")
karr_obj = np.asarray(fix.fbaObjective, dtype=np.float64).ravel()
print(f"Karr fbaObjective: shape={karr_obj.shape}, nonzero={np.count_nonzero(karr_obj)}, "
      f"max={karr_obj.max():.4e}, min={karr_obj.min():.4e}")
print(f"  nonzero positions: {np.where(karr_obj != 0)[0]}")
print(f"  nonzero values:    {karr_obj[karr_obj != 0]}")
# OC objective: look at .c attribute on the model
for a in ['c', 'objective', 'fba_objective', 'obj', 'fba_c']:
    if hasattr(model, a):
        v = getattr(model, a)
        if isinstance(v, np.ndarray):
            print(f"OC model.{a}: shape={v.shape}, nonzero={np.count_nonzero(v)}, "
                  f"max={v.max():.4e}, min={v.min():.4e}")
            print(f"  nonzero positions: {np.where(v != 0)[0]}")
            print(f"  nonzero values:    {v[v != 0]}")
            break
else:
    print("  OC has no .c/.objective/.fba_objective/.obj/.fba_c attribute — must be inside solve_fba?")

print()
print("="*70)
print("H3a: Compare OC S to Karr fixture fbaReactionStoichiometryMatrix")
print("="*70)
karr_S = np.asarray(fix.fbaReactionStoichiometryMatrix, dtype=np.float64)
print(f"Karr S shape: {karr_S.shape}, nnz: {np.count_nonzero(karr_S)}")
print(f"OC   S shape: {model.S.shape}, nnz: {np.count_nonzero(model.S)}")
if karr_S.shape == model.S.shape:
    diff = model.S - karr_S
    n_diff = int((np.abs(diff) > 1e-9).sum())
    print(f"OC.S - Karr.S: diff_count={n_diff}, max_abs={np.abs(diff).max():.4e}")
    if n_diff:
        # Show first 5 disagreements
        rows, cols = np.where(np.abs(diff) > 1e-9)
        print(f"  First 5 (row, col, OC, Karr):")
        for i in range(min(5, len(rows))):
            r, c = rows[i], cols[i]
            print(f"    [{r},{c}]: OC={model.S[r,c]:.4f}, Karr={karr_S[r,c]:.4f}")
else:
    print("  SHAPE MISMATCH — possibly transposed?")
    if karr_S.shape == (model.S.shape[1], model.S.shape[0]):
        print("  TRANSPOSED. Trying transpose comparison...")
        diff = model.S - karr_S.T
        print(f"  OC.S - Karr.S.T diff: {(np.abs(diff) > 1e-9).sum()}")

print()
print("="*70)
print("H5a: Enzyme overlay shape vs dynamics_inputs.enzymes_snapshot")
print("="*70)
print(f"Karr tick-0 enzymes: shape={karr_pre_enz.shape}")
print(f"dyn.enzymes_snapshot: shape={dyn.enzymes_snapshot.shape}")
print(f"  Length match: {karr_pre_enz.shape == dyn.enzymes_snapshot.shape}")
# Are the values comparable?
if karr_pre_enz.shape == dyn.enzymes_snapshot.shape:
    diff = np.abs(karr_pre_enz - dyn.enzymes_snapshot.ravel())
    print(f"  Per-element abs diff: max={diff.max():.2f}, sum={diff.sum():.1f}")
    print(f"  Karr-fixture enz value summary: min={karr_pre_enz.min()}, "
          f"max={karr_pre_enz.max()}, sum={karr_pre_enz.sum():.0f}")
    print(f"  dyn.enzymes_snapshot summary:   min={dyn.enzymes_snapshot.min()}, "
          f"max={dyn.enzymes_snapshot.max()}, sum={dyn.enzymes_snapshot.sum():.0f}")

print()
print("="*70)
print("H5b: Does cfb.compute_bounds receive boundEnzymes?")
print("="*70)
import inspect
sig = inspect.signature(cfb.compute_bounds)
print(f"compute_bounds signature: {sig}")
params = list(sig.parameters)
print(f"  Parameter names: {params}")
has_bound = any('bound' in p.lower() for p in params)
print(f"  Has any 'bound[Enzyme]' parameter: {has_bound}")

print()
print("="*70)
print("H6a: dynamics_inputs.substrates_snapshot vs Karr tick-0 pre")
print("="*70)
print(f"Karr pre shape: {karr_pre_sub.shape}, sum_abs: {np.abs(karr_pre_sub).sum():.0f}")
print(f"dyn.substrates_snapshot shape: {dyn.substrates_snapshot.shape}, "
      f"sum_abs: {np.abs(dyn.substrates_snapshot).sum():.0f}")
if karr_pre_sub.shape == dyn.substrates_snapshot.shape:
    diff = np.abs(karr_pre_sub - dyn.substrates_snapshot)
    print(f"  diff: max={diff.max():.0f}, sum={diff.sum():.0f}")
    print(f"  -> dyn fixture {'MATCHES' if diff.max() < 1 else 'DIFFERS FROM'} Karr tick-0")
else:
    print(f"  SHAPE MISMATCH!")
print()
print(f"Karr fixture.substrates (initial state from MetabolismFLAT): shape={np.asarray(fix.substrates).shape}, "
      f"sum_abs={np.abs(np.asarray(fix.substrates)).sum():.0f}")

print()
print("="*70)
print("H1c: cell_dry_mass scale check")
print("="*70)
print(f"OC dyn.cell_dry_mass: {dyn.cell_dry_mass}")
# Karr fixture has mass struct, look for it
mass = fix.mass
if hasattr(mass, 'cellDry'):
    cd = np.asarray(mass.cellDry).ravel()
    print(f"Karr fixture mass.cellDry: shape={cd.shape}, value={cd}, sum={cd.sum():.6e}")
if hasattr(mass, 'cellInitialDryWeight'):
    print(f"Karr fixture mass.cellInitialDryWeight: {mass.cellInitialDryWeight}")

# H2a continued — check what objective solve_fba uses
print()
print("="*70)
print("H2a (followup): solve_fba 'use_full_objective' — what does that mean?")
print("="*70)
import opencell.m1.karr_metabolism as km_mod
src = inspect.getsource(km_mod.solve_fba)
# Show first 30 lines
for i, line in enumerate(src.split('\n')[:50]):
    print(f"  {i+1}: {line}")
