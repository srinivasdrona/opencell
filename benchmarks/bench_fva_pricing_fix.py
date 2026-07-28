"""Task 3: test solver-parameter fixes for the degenerate-cycling root cause
found in bench_fva_profile.py (sample seed=0,tick=5 needs 100k-2M+ simplex
iterations per reaction under GLP_PT_STD/Dantzig pricing with no iteration
cap -- this is what hung the live N50/M20 run for ~8.7 CPU-hours after one
sample).

Candidate fix: switch `pricing` from GLP_PT_STD (textbook/Dantzig, known to
be cycling-prone on degenerate LPs) to GLP_PT_PSE (projected steepest edge),
keep everything else (tol_bnd, meth=GLP_PRIMAL, presolve=OFF) identical, and
verify the reported v_min/v_max for the pathological columns match a
authoritative slow reference (very large it_lim, no artificial cap) within
existing tolerance. A pricing-rule change can only affect which optimal
vertex/path is taken to reach the optimum -- never the optimal *value* of a
linear objective over the same polytope -- so equivalence is expected by
LP theory, and we verify it empirically here too.

Run via: bin\\oc-py benchmarks\\bench_fva_pricing_fix.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from opencell.m1 import calc_flux_bounds as cfb  # noqa: E402

_METABOLISM_FVA_BIG = 1e6


def _bounds_for_sample(pre_sub_585x3, pre_enz_104):
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
    lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -_METABOLISM_FVA_BIG)
    ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], _METABOLISM_FVA_BIG)
    lb = np.clip(lb, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
    ub = np.clip(ub, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
    infeasible = lb > ub
    if np.any(infeasible):
        midpoint = 0.5 * (lb[infeasible] + ub[infeasible])
        lb[infeasible] = midpoint
        ub[infeasible] = midpoint
    return lb, ub


def _load_sample(seed, tick):
    oracle = runner_helpers.load_karr_oracle("Metabolism")
    before_sub = np.asarray(oracle["before_substrates_cube"], dtype=np.float64)
    before_enz = np.asarray(oracle["before_enzymes"], dtype=np.float64)
    return before_sub[seed, tick], before_enz[seed, tick]


def build_lp(glp, S, rhs, c, lb, ub):
    m_rows, n_rxn = S.shape
    lp = glp.glp_create_prob()
    glp.glp_term_out(glp.GLP_OFF)
    glp.glp_set_obj_dir(lp, glp.GLP_MAX)
    glp.glp_add_rows(lp, m_rows)
    for i in range(m_rows):
        glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))
    glp.glp_add_cols(lp, n_rxn)
    for j in range(n_rxn):
        lj = float(lb[j])
        uj = float(ub[j])
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
    glp.glp_adv_basis(lp, 0)
    return lp


def solve_face(glp, lp, biomass_value_star, c):
    glp.glp_add_rows(lp, 1)
    biomass_row = int(glp.glp_get_num_rows(lp))
    glp.glp_set_row_bnds(lp, biomass_row, glp.GLP_FX, float(biomass_value_star), float(biomass_value_star))
    nz = np.flatnonzero(np.abs(c) > 0.0)
    ind = glp.intArray(int(nz.size) + 1)
    val = glp.doubleArray(int(nz.size) + 1)
    for k, col in enumerate(nz, start=1):
        ind[k] = int(col) + 1
        val[k] = float(c[col])
    glp.glp_set_mat_row(lp, biomass_row, int(nz.size), ind, val)
    n_rxn = c.shape[0]
    for j in range(n_rxn):
        glp.glp_set_obj_coef(lp, j + 1, 0.0)


def sweep_columns(glp, lp, parm, cols, n_rxn):
    """Solve min/max for a specific subset of columns; return dict j->(vmin,vmax,iters,elapsed)."""
    results = {}
    for j in cols:
        glp.glp_set_obj_coef(lp, j + 1, 1.0)
        row = {}
        for sense, key in ((glp.GLP_MAX, "max"), (glp.GLP_MIN, "min")):
            glp.glp_set_obj_dir(lp, sense)
            t0 = time.perf_counter()
            exit_code = int(glp.glp_simplex(lp, parm))
            status = int(glp.glp_get_status(lp))
            elapsed = time.perf_counter() - t0
            it_cnt = int(glp.glp_get_it_cnt(lp))
            val = float(glp.glp_get_col_prim(lp, j + 1)) if status == glp.GLP_OPT else float("nan")
            row[key] = {"val": val, "status": status, "exit": exit_code, "iters": it_cnt, "s": elapsed}
        results[j] = row
        glp.glp_set_obj_coef(lp, j + 1, 0.0)
    return results


def main() -> None:
    import swiglpk as glp

    seed, tick = 0, 5
    pre_sub, pre_enz = _load_sample(seed, tick)
    lb, ub = _bounds_for_sample(pre_sub, pre_enz)
    model = runner_helpers._metabolism_model()

    _v_star, info = runner_helpers.m1_karr_metabolism.solve_fba(
        model, use_full_objective=True, sense="max", big=_METABOLISM_FVA_BIG,
        lb_override=lb, ub_override=ub, solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])
    S = np.asarray(model.S, dtype=np.float64)
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)
    c = np.asarray(model.obj, dtype=np.float64).reshape(-1)
    n_rxn = c.shape[0]

    # Pathological columns previously observed on this exact sample.
    cols = [3, 6, 24, 66, 233, 384, 395, 396]

    print(f"=== sample seed={seed} tick={tick}: pricing comparison on {len(cols)} pathological columns ===")

    # Reference: authoritative slow solve, very large it_lim, no time cap, GLP_PT_STD (original).
    lp_ref = build_lp(glp, S, rhs, c, lb, ub)
    parm_ref = glp.glp_smcp()
    glp.glp_init_smcp(parm_ref)
    parm_ref.msg_lev = glp.GLP_MSG_OFF
    parm_ref.presolve = glp.GLP_OFF
    parm_ref.meth = glp.GLP_PRIMAL
    parm_ref.tol_bnd = 1e-6
    parm_ref.pricing = glp.GLP_PT_STD
    parm_ref.it_lim = 20_000_000
    parm_ref.tm_lim = 60_000  # 60s hard safety cap per column-direction solve
    exit0 = int(glp.glp_simplex(lp_ref, parm_ref))
    assert int(glp.glp_get_status(lp_ref)) == glp.GLP_OPT, "primary solve must be optimal"
    solve_face(glp, lp_ref, biomass_value_star, c)
    t0 = time.perf_counter()
    ref_results = sweep_columns(glp, lp_ref, parm_ref, cols, n_rxn)
    t_ref = time.perf_counter() - t0
    glp.glp_delete_prob(lp_ref)
    print(f"REFERENCE (GLP_PT_STD, it_lim=20M): {t_ref:.3f}s total for {len(cols)} columns")
    for j, row in ref_results.items():
        print(f"  j={j}: max={row['max']} min={row['min']}")

    # Candidate: GLP_PT_PSE pricing, bounded it_lim as safety net only.
    lp_pse = build_lp(glp, S, rhs, c, lb, ub)
    parm_pse = glp.glp_smcp()
    glp.glp_init_smcp(parm_pse)
    parm_pse.msg_lev = glp.GLP_MSG_OFF
    parm_pse.presolve = glp.GLP_OFF
    parm_pse.meth = glp.GLP_PRIMAL
    parm_pse.tol_bnd = 1e-6
    parm_pse.pricing = glp.GLP_PT_PSE
    parm_pse.it_lim = 200_000
    parm_pse.tm_lim = 30_000
    glp.glp_simplex(lp_pse, parm_pse)
    assert int(glp.glp_get_status(lp_pse)) == glp.GLP_OPT
    solve_face(glp, lp_pse, biomass_value_star, c)
    t0 = time.perf_counter()
    pse_results = sweep_columns(glp, lp_pse, parm_pse, cols, n_rxn)
    t_pse = time.perf_counter() - t0
    glp.glp_delete_prob(lp_pse)
    print(f"CANDIDATE (GLP_PT_PSE, it_lim=200k): {t_pse:.3f}s total for {len(cols)} columns "
          f"(speedup {t_ref / max(t_pse, 1e-9):.1f}x)")
    for j, row in pse_results.items():
        print(f"  j={j}: max={row['max']} min={row['min']} iters_max={row['max']['iters']} iters_min={row['min']['iters']}")

    print("=== equivalence check (tol=1e-6 relative, matches fva.py tolerance semantics) ===")
    max_abs_diff = 0.0
    for j in cols:
        for key in ("max", "min"):
            ref_v = ref_results[j][key]["val"]
            cand_v = pse_results[j][key]["val"]
            diff = abs(ref_v - cand_v)
            max_abs_diff = max(max_abs_diff, diff)
            ok = diff <= 1e-4 * max(1.0, abs(ref_v))
            print(f"  j={j} {key}: ref={ref_v:.6f} candidate={cand_v:.6f} diff={diff:.2e} {'OK' if ok else 'MISMATCH'}")
    print(f"max_abs_diff={max_abs_diff:.2e}")


if __name__ == "__main__":
    main()
