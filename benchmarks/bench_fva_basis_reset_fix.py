"""Test hypothesis: warm-started basis carryover across successive column
min/max solves is what causes catastrophic degenerate cycling (not the
per-column LP itself, which converges in ~30 iterations cold). Compare:
(a) current approach: basis carried forward across all solves in solve_cols
(b) candidate fix: reset to a fresh advanced basis before every individual
    min/max solve.
Confirms whether (b) avoids the blowup and whether optimal values match.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import swiglpk as glp

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from opencell.m1 import calc_flux_bounds as cfb  # noqa: E402
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture  # noqa: E402


def bounds_for_sample(pre_sub_585x3, pre_enz_104):
    model = runner_helpers._metabolism_model()
    dyn = runner_helpers._metabolism_dynamics()
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
    bounds = cfb.compute_bounds(
        substrates=np.asarray(pre_sub_585x3, dtype=np.float64),
        enzymes=np.asarray(pre_enz_104, dtype=np.float64),
        cell_dry_mass=dyn.cell_dry_mass,
        step_size_sec=dyn.step_size_sec,
        catalysis=model.catalysis,
        enz_bounds=model.enz_bounds,
        fba_reaction_bounds=fba_reaction_bounds,
        dyn=dyn,
        apply_protein_bounds=False,
    )
    big = 1e6
    lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -big)
    ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], big)
    lb = np.clip(lb, -big, big).astype(np.float64)
    ub = np.clip(ub, -big, big).astype(np.float64)
    infeasible = lb > ub
    if np.any(infeasible):
        midpoint = 0.5 * (lb[infeasible] + ub[infeasible])
        lb[infeasible] = midpoint
        ub[infeasible] = midpoint
    return lb, ub


def build_lp(S, rhs, c, lb, ub, m_rows, n_rxn):
    lp = glp.glp_create_prob()
    glp.glp_term_out(glp.GLP_OFF)
    glp.glp_set_obj_dir(lp, glp.GLP_MAX)
    glp.glp_add_rows(lp, m_rows)
    for i in range(m_rows):
        glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))
    glp.glp_add_cols(lp, n_rxn)
    for j in range(n_rxn):
        lj, uj = float(lb[j]), float(ub[j])
        if lj == uj:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lj, uj)
        else:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lj, uj)
        glp.glp_set_obj_coef(lp, j + 1, float(c[j]))
    s_rows, s_cols = np.nonzero(S)
    nnz = int(s_rows.size)
    ia = glp.intArray(nnz + 1)
    ja = glp.intArray(nnz + 1)
    ar = glp.doubleArray(nnz + 1)
    for k in range(nnz):
        ia[k + 1] = int(s_rows[k]) + 1
        ja[k + 1] = int(s_cols[k]) + 1
        ar[k + 1] = float(S[s_rows[k], s_cols[k]])
    glp.glp_load_matrix(lp, nnz, ia, ja, ar)
    glp.glp_scale_prob(lp, glp.GLP_SF_AUTO)
    return lp


def make_parm(tm_lim_ms):
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_OFF
    parm.meth = glp.GLP_PRIMAL
    parm.tol_bnd = 1e-6
    parm.pricing = glp.GLP_PT_PSE
    parm.it_lim = 50_000_000
    parm.tm_lim = tm_lim_ms
    return parm


def main():
    seed, tick = 0, 2
    oracle = runner_helpers.load_karr_oracle("Metabolism")
    before_sub = np.asarray(oracle["before_substrates_cube"], dtype=np.float64)
    before_enz = np.asarray(oracle["before_enzymes"], dtype=np.float64)
    pre_sub = before_sub[seed, tick]
    pre_enz = before_enz[seed, tick]

    model = runner_helpers._metabolism_model()
    lb, ub = bounds_for_sample(pre_sub, pre_enz)
    _v_star, info = runner_helpers.m1_karr_metabolism.solve_fba(
        model, use_full_objective=True, sense="max", big=1e6,
        lb_override=lb, ub_override=ub, solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])

    fixture = KarrWritebackFixture.from_mat(
        _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    )
    reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )

    S = np.asarray(model.S, dtype=np.float64)
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)
    c = np.asarray(model.obj, dtype=np.float64).reshape(-1)
    m_rows, n_rxn = S.shape

    target_cols = np.unique(reaction_subset)
    fixed_mask = lb[target_cols] == ub[target_cols]
    solve_cols = target_cols[~fixed_mask]

    lp = build_lp(S, rhs, c, lb, ub, m_rows, n_rxn)
    glp.glp_adv_basis(lp, 0)
    parm = make_parm(10_000)
    exit_code = glp.glp_simplex(lp, parm)
    print(f"primary solve: exit={exit_code} status={glp.glp_get_status(lp)} it_cnt={glp.glp_get_it_cnt(lp)}")

    glp.glp_add_rows(lp, 1)
    biomass_row = glp.glp_get_num_rows(lp)
    glp.glp_set_row_bnds(lp, biomass_row, glp.GLP_FX, biomass_value_star, biomass_value_star)
    nz = np.flatnonzero(np.abs(c) > 0.0)
    ind = glp.intArray(int(nz.size) + 1)
    val = glp.doubleArray(int(nz.size) + 1)
    for k, col in enumerate(nz, start=1):
        ind[k] = int(col) + 1
        val[k] = float(c[col])
    glp.glp_set_mat_row(lp, biomass_row, int(nz.size), ind, val)
    for j in range(n_rxn):
        glp.glp_set_obj_coef(lp, j + 1, 0.0)

    v_min = {}
    v_max = {}
    t_start = time.perf_counter()
    max_iters_seen = 0
    for j in solve_cols.tolist():
        glp.glp_set_obj_coef(lp, j + 1, 1.0)

        # CANDIDATE FIX: reset to a fresh advanced basis before each solve to
        # eliminate warm-start degeneracy carryover.
        glp.glp_adv_basis(lp, 0)
        glp.glp_set_obj_dir(lp, glp.GLP_MAX)
        it0 = glp.glp_get_it_cnt(lp)
        exit_code = glp.glp_simplex(lp, parm)
        status = glp.glp_get_status(lp)
        it1 = glp.glp_get_it_cnt(lp)
        max_iters_seen = max(max_iters_seen, it1 - it0)
        if status != glp.GLP_OPT:
            print(f"  MAX j={j} FAILED: exit={exit_code} status={status} iters={it1-it0}")
            break
        v_max[j] = glp.glp_get_col_prim(lp, j + 1)

        glp.glp_adv_basis(lp, 0)
        glp.glp_set_obj_dir(lp, glp.GLP_MIN)
        it0 = glp.glp_get_it_cnt(lp)
        exit_code = glp.glp_simplex(lp, parm)
        status = glp.glp_get_status(lp)
        it1 = glp.glp_get_it_cnt(lp)
        max_iters_seen = max(max_iters_seen, it1 - it0)
        if status != glp.GLP_OPT:
            print(f"  MIN j={j} FAILED: exit={exit_code} status={status} iters={it1-it0}")
            break
        v_min[j] = glp.glp_get_col_prim(lp, j + 1)

        glp.glp_set_obj_coef(lp, j + 1, 0.0)

    elapsed = time.perf_counter() - t_start
    print(f"Solved {len(v_min)}/{solve_cols.size} columns in {elapsed:.4f}s "
          f"(max iters in any single solve: {max_iters_seen})")
    if 390 in v_min:
        print(f"j=390 MIN value with basis reset: {v_min[390]!r} (expect ~-13197.325864087215)")
    glp.glp_delete_prob(lp)


if __name__ == "__main__":
    main()
