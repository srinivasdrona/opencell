"""Reproduce the seed=0,tick=0 j=392 MIN failure using the REAL full
reaction_subset (not an isolated single column) to confirm the hidden-state
hypothesis: does `glp_adv_basis` reset actually depend on what happened to
the LP object during prior columns' solves in this sequence, even though the
LP's structural DATA (bounds/coeffs/matrix) at solve time is byte-identical
to solving j=392 alone? Compares three basis strategies at the moment of
solving j=392: (1) current shipped glp_adv_basis-before-each-solve, (2)
glp_std_basis (the trivial all-slack basis, provably independent of any
prior variable status), (3) a brand-new glp_prob object rebuilt from scratch
for this one column only (byte-for-byte identical structural data, zero
possible hidden-state carryover).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import numpy as np  # noqa: E402
import swiglpk as glp  # noqa: E402

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
fva_reaction_subset = np.union1d(
    np.asarray(fixture.fba_idx_external, dtype=np.int64),
    np.asarray(fixture.fba_idx_internal, dtype=np.int64),
)
print(f"reaction_subset size={fva_reaction_subset.size}, contains 392={392 in fva_reaction_subset.tolist()}")

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

print("--- reproduce with REAL full reaction_subset (should reproduce j=392 failure) ---")
t0 = time.time()
try:
    v_min, v_max = fva_mod.fva_range(
        np.asarray(model.S, dtype=np.float64), np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64), lb, ub,
        biomass_value_star=biomass_value_star, reaction_subset=fva_reaction_subset,
    )
    print(f"OK all columns, time={time.time()-t0:.3f}s")
except RuntimeError as exc:
    print(f"FAILED time={time.time()-t0:.3f}s: {exc}")
