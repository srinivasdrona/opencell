"""Batch-2 probes:

H5b: Does Karr's calcFluxBounds use boundEnzymes? Compare to compute_bounds.
H1a/H1b: Diff cfb.compute_bounds rules against calcFluxBounds.m, rule by rule.
H2a-exact: Exact-value diff OC obj vs Karr fbaObjective.
H7: For each at-UB external exchange, isolate which rule produced that bound.
H1c: cell_dry_mass scale check (femtograms vs grams).
"""
import sys
import inspect
from pathlib import Path
import numpy as np
import h5py
from scipy.io import loadmat

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

print("="*70)
print("H2a-exact: OC.obj vs Karr.fbaObjective")
print("="*70)
model = km.load_default()
mat = loadmat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"),
              squeeze_me=True, struct_as_record=False)
fix = mat["data"].fixture
karr_obj = np.asarray(fix.fbaObjective, dtype=np.float64).ravel()
oc_obj = model.obj.ravel()
print(f"OC.obj   shape={oc_obj.shape}, nnz={(oc_obj != 0).sum()}, sum_abs={np.abs(oc_obj).sum():.6e}")
print(f"Karr.obj shape={karr_obj.shape}, nnz={(karr_obj != 0).sum()}, sum_abs={np.abs(karr_obj).sum():.6e}")
if karr_obj.shape == oc_obj.shape:
    diff = oc_obj - karr_obj
    n_diff = (np.abs(diff) > 1e-12).sum()
    print(f"Element-wise diff: nnz={n_diff}, max_abs={np.abs(diff).max():.6e}")
    if n_diff:
        for i in np.where(np.abs(diff) > 1e-12)[0][:5]:
            print(f"  [{i}]: OC={oc_obj[i]:.6e}, Karr={karr_obj[i]:.6e}")
else:
    print(f"SHAPE MISMATCH: OC {oc_obj.shape} vs Karr {karr_obj.shape}")

print()
print("="*70)
print("H5b: Inspect Karr calcFluxBounds.m signature + look at compute_bounds rules")
print("="*70)
# Find Karr's calcFluxBounds.m file
candidates = list(REPO.glob("data/m1_sources/**/calcFluxBounds*"))
print(f"calcFluxBounds.m candidates: {[str(c.relative_to(REPO)) for c in candidates]}")
karr_calc = None
for c in candidates:
    if c.suffix == ".m":
        karr_calc = c
        break
if karr_calc:
    txt = karr_calc.read_text(errors='ignore')
    # Show the function signature + first few lines
    lines = txt.split("\n")
    in_func = False
    shown = 0
    for line in lines:
        if "function" in line and "calcFluxBounds" in line:
            in_func = True
        if in_func:
            print(f"  {line}")
            shown += 1
            if shown > 30:
                break
    # Check if 'boundEnzymes' appears in the file
    print(f"\n'boundEnzymes' mentioned in {karr_calc.name}: {txt.lower().count('boundenzymes')} times")
    print(f"'this.enzymes' references: {txt.count('this.enzymes')}")

print()
print("="*70)
print("H1a/H1b: cfb.compute_bounds rule structure")
print("="*70)
src = inspect.getsource(cfb.compute_bounds)
# Find rule sections (look for # Rule N: or apply_X branches)
import re
print("Rule branches in compute_bounds:")
for m in re.finditer(r'(if apply_\w+:|# Rule \d+:|# .{1,80}rule)', src):
    print(f"  {m.group()}")

print()
print("="*70)
print("H7: For UB-hit external exchanges, which apply_* flag flipped them?")
print("="*70)
# Repeatedly call compute_bounds with each rule toggled OFF, measure delta in
# bounds at the UB-hit columns
fbf = KarrWritebackFixture.from_mat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"))
dyn = cfb.load_default_dynamics()
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T
    karr_enz = get3d("states_before/enzymes", 0).ravel()

fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)
ext_cols = fbf.fba_idx_external

# Baseline: all rules on
def get_bounds(**flags):
    return cfb.compute_bounds(
        substrates=karr_pre, enzymes=karr_enz,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=model.catalysis, enz_bounds=model.enz_bounds,
        fba_reaction_bounds=fba_reaction_bounds, dyn=dyn,
        apply_protein_bounds=False,
        **flags,
    )

baseline = get_bounds()
print(f"Baseline (all rules on): ext_lb sum_abs={np.abs(baseline[ext_cols, 0]).sum():.0f}, "
      f"ext_ub sum_abs={np.abs(baseline[ext_cols, 1]).sum():.0f}")

flags_to_test = [
    "apply_enzyme_kinetic",
    "apply_enzyme_presence",
    "apply_directionality",
    "apply_external_metabolite",
    "apply_internal_metabolite",
]
for flag in flags_to_test:
    b = get_bounds(**{flag: False})
    lb_diff = np.abs(b[ext_cols, 0] - baseline[ext_cols, 0]).sum()
    ub_diff = np.abs(b[ext_cols, 1] - baseline[ext_cols, 1]).sum()
    print(f"  WITHOUT {flag}: ext_lb sum_abs diff={lb_diff:.0f}, ext_ub sum_abs diff={ub_diff:.0f}")

# Now identify WHICH rule is producing the ±7918 bound at fatty acid columns
print()
print("Per-rule contributions at HDCA (col 393) ub:")
for flag in flags_to_test:
    b = get_bounds(**{flag: False})
    print(f"  Without {flag}: lb={b[393, 0]:+.2f}, ub={b[393, 1]:+.2f} "
          f"(baseline lb={baseline[393, 0]:+.2f}, ub={baseline[393, 1]:+.2f})")

print()
print("="*70)
print("H1c: cell_dry_mass scale")
print("="*70)
print(f"OC dyn.cell_dry_mass: {dyn.cell_dry_mass} (femtograms? grams?)")
# Karr: mass.cellInitialDryWeight is in pg? g? Read directly
mass = fix.mass
if hasattr(mass, "cellInitialDryWeight"):
    print(f"Karr fix.mass.cellInitialDryWeight: {mass.cellInitialDryWeight}")
if hasattr(mass, "cellDry"):
    cd = np.asarray(mass.cellDry).ravel()
    print(f"Karr fix.mass.cellDry: {cd}")
# Karr's calcFluxBounds.m uses mass.cellDry. Check.
if karr_calc:
    txt = karr_calc.read_text(errors='ignore')
    for line in txt.split("\n"):
        if "mass" in line.lower() and ("cellDry" in line or "dryWeight" in line or "molarVolume" in line):
            print(f"  Karr mass reference: {line.strip()[:120]}")
