"""Diagnose the seed=0,tick=0 reaction j=392 MIN GLP_ETMLIM failure hit during
the real full N50xM20 sweep (root cause not covered by
bench_fva_full_pipeline.py's 13-sample random selection, which happened not
to include (seed=0, tick=0)). Calls the REAL fva_range (with all three
current fixes: PSE pricing, per-solve basis reset, DB objective-face
epsilon), reaction_subset=[392] only, so runtime is a single column, and
prints exact iteration/time/status. Then tries variant simplex parameter
configurations (STD pricing, GLP_DUAL method, presolve=ON) via monkeypatched
_configure_simplex_params to see whether any resolves it, without touching
the shipped fva.py during the diagnostic itself.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import numpy as np  # noqa: E402

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from opencell.m1 import calc_flux_bounds as cfb  # noqa: E402
from opencell.m1 import fva as fva_mod  # noqa: E402
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture  # noqa: E402

_METABOLISM_FVA_BIG = 1e6
SEED, TICK, J = 0, 0, 392

model = runner_helpers._metabolism_model()
dyn = runner_helpers._metabolism_dynamics()
fixture = KarrWritebackFixture.from_mat(
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
)

oracle = runner_helpers.load_karr_oracle("Metabolism")
before_sub = np.asarray(oracle["before_substrates_cube"], dtype=np.float64)
before_enz = np.asarray(oracle["before_enzymes"], dtype=np.float64)
pre_sub = before_sub[SEED, TICK]
pre_enz = before_enz[SEED, TICK]

fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
bounds = cfb.compute_bounds(
    substrates=pre_sub, enzymes=pre_enz, cell_dry_mass=dyn.cell_dry_mass,
    step_size_sec=dyn.step_size_sec, catalysis=model.catalysis, enz_bounds=model.enz_bounds,
    fba_reaction_bounds=fba_reaction_bounds, dyn=dyn, apply_protein_bounds=False,
)
lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -_METABOLISM_FVA_BIG)
ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], _METABOLISM_FVA_BIG)
lb = np.clip(lb, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
ub = np.clip(ub, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
infeasible = lb > ub
if np.any(infeasible):
    mid = 0.5 * (lb[infeasible] + ub[infeasible])
    lb[infeasible] = mid
    ub[infeasible] = mid

_v_star, info = runner_helpers.m1_karr_metabolism.solve_fba(
    model, use_full_objective=True, sense="max", big=_METABOLISM_FVA_BIG,
    lb_override=lb, ub_override=ub, solver="glpk",
)
biomass_value_star = float(info["objective_value"])
print(f"biomass_value_star={biomass_value_star!r}")

S = np.asarray(model.S, dtype=np.float64)
rhs = np.asarray(model.RHS, dtype=np.float64)
c = np.asarray(model.obj, dtype=np.float64)

print("--- current shipped fva_range config (PSE, primal, basis-reset, DB-eps-face), j=392 only ---")
t0 = time.time()
try:
    v_min, v_max = fva_mod.fva_range(
        S, rhs, c, lb, ub, biomass_value_star=biomass_value_star, reaction_subset=np.array([J]),
    )
    print(f"OK v_min={v_min[J]!r} v_max={v_max[J]!r} time={time.time()-t0:.3f}s")
except RuntimeError as exc:
    print(f"FAILED time={time.time()-t0:.3f}s: {exc}")

print()
print("--- variant: STD pricing (monkeypatched _configure_simplex_params) ---")
_orig_configure = fva_mod._configure_simplex_params


def _configure_std(glp):
    parm = _orig_configure(glp)
    parm.pricing = glp.GLP_PT_STD
    return parm


fva_mod._configure_simplex_params = _configure_std
t0 = time.time()
try:
    v_min, v_max = fva_mod.fva_range(
        S, rhs, c, lb, ub, biomass_value_star=biomass_value_star, reaction_subset=np.array([J]),
    )
    print(f"OK v_min={v_min[J]!r} v_max={v_max[J]!r} time={time.time()-t0:.3f}s")
except RuntimeError as exc:
    print(f"FAILED time={time.time()-t0:.3f}s: {exc}")
fva_mod._configure_simplex_params = _orig_configure

print()
print("--- variant: presolve=ON (PSE) ---")


def _configure_presolve(glp):
    parm = _orig_configure(glp)
    parm.presolve = glp.GLP_ON
    return parm


fva_mod._configure_simplex_params = _configure_presolve
t0 = time.time()
try:
    v_min, v_max = fva_mod.fva_range(
        S, rhs, c, lb, ub, biomass_value_star=biomass_value_star, reaction_subset=np.array([J]),
    )
    print(f"OK v_min={v_min[J]!r} v_max={v_max[J]!r} time={time.time()-t0:.3f}s")
except RuntimeError as exc:
    print(f"FAILED time={time.time()-t0:.3f}s: {exc}")
fva_mod._configure_simplex_params = _orig_configure

print()
print("--- variant: GLP_DUAL method (PSE pricing) ---")


def _configure_dual(glp):
    parm = _orig_configure(glp)
    parm.meth = glp.GLP_DUAL
    return parm


fva_mod._configure_simplex_params = _configure_dual
t0 = time.time()
try:
    v_min, v_max = fva_mod.fva_range(
        S, rhs, c, lb, ub, biomass_value_star=biomass_value_star, reaction_subset=np.array([J]),
    )
    print(f"OK v_min={v_min[J]!r} v_max={v_max[J]!r} time={time.time()-t0:.3f}s")
except RuntimeError as exc:
    print(f"FAILED time={time.time()-t0:.3f}s: {exc}")
fva_mod._configure_simplex_params = _orig_configure
