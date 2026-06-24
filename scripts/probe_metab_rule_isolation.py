"""H1a refined: isolate which OC rule(s) over-constrain growth.

Toggle each rule off in turn, measure growth + count exchange fluxes.
The rule whose removal moves growth toward Karr's expected value is the
offending rule.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

model = km.load_default()
dyn = cfb.load_default_dynamics()
fbf = KarrWritebackFixture.from_mat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"))

trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T
    karr_enz = get3d("states_before/enzymes", 0).ravel()

fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)

def run_with_flags(**flags):
    b = cfb.compute_bounds(
        substrates=karr_pre, enzymes=karr_enz,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=model.catalysis, enz_bounds=model.enz_bounds,
        fba_reaction_bounds=fba_reaction_bounds, dyn=dyn,
        apply_protein_bounds=False,
        **flags,
    )
    v, info = km.solve_fba(
        model, use_full_objective=True, sense="max",
        lb_override=b[:, 0], ub_override=b[:, 1],
    )
    growth = info["biomass_flux_per_s"]
    ext_cols = fbf.fba_idx_external
    at_ub = (np.abs(v[ext_cols] - b[ext_cols, 1]) < 1e-3).sum()
    at_lb = (np.abs(v[ext_cols] - b[ext_cols, 0]) < 1e-3).sum()
    return growth, at_lb, at_ub, b, v

print("Karr's expected tick-0 growth ~ 1.5e-5 to 2e-5 (per Day-38 design doc)")
print()
print(f"{'flags':<55} {'growth':>14}  ext at_lb/at_ub/interior")
print("-" * 100)

# Baseline: all on
g, a_lb, a_ub, b_base, _ = run_with_flags()
print(f"{'BASELINE (all rules on)':<55} {g:>14.4e}  {a_lb}/{a_ub}/{124-a_lb-a_ub}")

# Each rule turned off individually
flag_names = [
    "apply_enzyme_kinetic",
    "apply_enzyme_presence",
    "apply_directionality",
    "apply_external_metabolite",
    "apply_internal_metabolite",
]
for f in flag_names:
    g, a_lb, a_ub, _, _ = run_with_flags(**{f: False})
    diff = g - 5.582e-6  # baseline growth
    pct = (g / 5.582e-6 - 1) * 100
    print(f"  off:{f:<48} {g:>14.4e}  {a_lb}/{a_ub}/{124-a_lb-a_ub}   ({pct:+.1f}%)")

# Combined toggles to see additive effects
print()
print(f"--- Combined (off multiple at once) ---")
combos = [
    ("apply_enzyme_kinetic", "apply_enzyme_presence"),
    ("apply_directionality", "apply_external_metabolite"),
    ("apply_external_metabolite", "apply_internal_metabolite"),
]
for combo in combos:
    flags = {f: False for f in combo}
    g, a_lb, a_ub, _, _ = run_with_flags(**flags)
    print(f"  off:{'+'.join(combo):<60} {g:>14.4e}  {a_lb}/{a_ub}/{124-a_lb-a_ub}")

# What if we ONLY apply directionality + external? (no enzyme rules)
print()
g, a_lb, a_ub, _, _ = run_with_flags(
    apply_enzyme_kinetic=False, apply_enzyme_presence=False, apply_internal_metabolite=False,
)
print(f"ONLY external + directionality on: growth={g:.4e}  ext {a_lb}/{a_ub}/{124-a_lb-a_ub}")

# What if we ONLY apply external?
g, a_lb, a_ub, _, _ = run_with_flags(
    apply_enzyme_kinetic=False, apply_enzyme_presence=False,
    apply_directionality=False, apply_internal_metabolite=False,
)
print(f"ONLY external on: growth={g:.4e}  ext {a_lb}/{a_ub}/{124-a_lb-a_ub}")
