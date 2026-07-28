"""Task 1: profile ONE current Metabolism FVA sample (wall/CPU, solver call counts).

Reproduces the exact per-sample computation used by
`_metabolism_fva_sample_feasibility` in
`tests/vivarium/l2_2_design_a_runner.py`, but with instrumentation:
  - wall-clock + CPU-clock time for solve_fba (biomass LP) and fva_range
    (2*504 min/max LPs).
  - per-call histogram of simplex iteration counts (glp_get_it_cnt) to
    detect degeneracy/cycling as a root cause of slow solves.

Run via: bin\\oc-py benchmarks\\bench_fva_profile.py
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
from opencell.m1.fva import _configure_simplex_params, _solve_checked  # noqa: E402

_METABOLISM_FVA_BIG = 1e6


def _bounds_for_sample(pre_sub_585x3: np.ndarray, pre_enz_104: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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


def _load_sample(seed: int, tick: int) -> tuple[np.ndarray, np.ndarray]:
    oracle = runner_helpers.load_karr_oracle("Metabolism")
    before_sub = np.asarray(oracle["before_substrates_cube"], dtype=np.float64)
    before_enz = np.asarray(oracle["before_enzymes"], dtype=np.float64)
    pre_sub = before_sub[seed, tick]
    pre_enz = before_enz[seed, tick]
    return pre_sub, pre_enz


def instrumented_fva_range(S, rhs, c, lb, ub, biomass_value_star, epsilon_obj=0.0, it_lim=None, tm_lim_ms=None):
    """Copy of fva_range with per-call iteration-count + timing instrumentation.

    it_lim / tm_lim_ms bound each individual min/max LP so a degenerate/cycling
    solve cannot silently consume unbounded wall time; failures are recorded
    (label, status, iters, elapsed) rather than raising, so a full sweep can
    finish and expose every problematic column.
    """
    import swiglpk as glp

    S = np.asarray(S, dtype=np.float64)
    rhs = np.asarray(rhs, dtype=np.float64).reshape(-1)
    c = np.asarray(c, dtype=np.float64).reshape(-1)
    lb = np.asarray(lb, dtype=np.float64).reshape(-1)
    ub = np.asarray(ub, dtype=np.float64).reshape(-1)
    m_rows, n_rxn = S.shape

    lp = glp.glp_create_prob()
    stats = {
        "setup_s": 0.0,
        "primary_s": 0.0,
        "sweep_s": 0.0,
        "iters": [],
        "per_lp_s": [],
        "n_lps": 0,
        "failures": [],
    }
    try:
        t0 = time.perf_counter()
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
        parm = _configure_simplex_params(glp)
        if it_lim is not None:
            parm.it_lim = int(it_lim)
        if tm_lim_ms is not None:
            parm.tm_lim = int(tm_lim_ms)
        stats["setup_s"] = time.perf_counter() - t0

        t1 = time.perf_counter()
        _solve_checked(glp, lp, parm, label="FVA primary")
        stats["primary_s"] = time.perf_counter() - t1
        stats["iters"].append(int(glp.glp_get_it_cnt(lp)))
        stats["n_lps"] += 1

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
        for j in range(n_rxn):
            glp.glp_set_obj_coef(lp, j + 1, 0.0)

        v_min = np.empty(n_rxn, dtype=np.float64)
        v_max = np.empty(n_rxn, dtype=np.float64)
        t2 = time.perf_counter()
        for j in range(n_rxn):
            glp.glp_set_obj_coef(lp, j + 1, 1.0)

            for sense, dirn, arr in ((glp.GLP_MAX, "max", v_max), (glp.GLP_MIN, "min", v_min)):
                glp.glp_set_obj_dir(lp, sense)
                tlp = time.perf_counter()
                simplex_exit = int(glp.glp_simplex(lp, parm))
                sol_status = int(glp.glp_get_status(lp))
                elapsed = time.perf_counter() - tlp
                it_cnt = int(glp.glp_get_it_cnt(lp))
                stats["iters"].append(it_cnt)
                stats["per_lp_s"].append(elapsed)
                stats["n_lps"] += 1
                if simplex_exit != 0 or sol_status != glp.GLP_OPT:
                    stats["failures"].append(
                        {"j": j, "dir": dirn, "simplex_exit": simplex_exit, "status": sol_status, "iters": it_cnt, "s": elapsed}
                    )
                    arr[j] = float("nan")
                else:
                    arr[j] = float(glp.glp_get_col_prim(lp, j + 1))

            glp.glp_set_obj_coef(lp, j + 1, 0.0)
        stats["sweep_s"] = time.perf_counter() - t2
        return v_min, v_max, stats
    finally:
        glp.glp_delete_prob(lp)


def main() -> None:
    import sys as _sys

    # 24 samples spread across the 50-seed x 20-tick oracle grid, chosen to be
    # diverse (early/late seeds, early/mid/late ticks) rather than cherry-picked.
    rng = np.random.default_rng(12345)
    seeds = sorted(set(int(x) for x in rng.choice(50, size=20, replace=False)) | {0, 1, 49})
    ticks = [0, 1, 5, 10, 19]
    samples = [(s, t) for s in seeds[:8] for t in ticks][:24]

    it_lim = None  # rely on fva.py's own _FVA_IT_LIM/_FVA_TM_LIM_MS safety net now
    tm_lim_ms = None
    grand_totals = {"wall": 0.0, "n_lps": 0, "n_failures": 0}
    worst = []
    for seed, tick in samples:
        pre_sub, pre_enz = _load_sample(seed, tick)
        lb, ub = _bounds_for_sample(pre_sub, pre_enz)
        model = runner_helpers._metabolism_model()

        t0_wall = time.perf_counter()
        _v_star, info = runner_helpers.m1_karr_metabolism.solve_fba(
            model,
            use_full_objective=True,
            sense="max",
            big=_METABOLISM_FVA_BIG,
            lb_override=lb,
            ub_override=ub,
            solver="glpk",
        )
        t_fba_wall = time.perf_counter() - t0_wall
        biomass_value_star = float(info["objective_value"])

        t1_wall = time.perf_counter()
        v_min, v_max, stats = instrumented_fva_range(
            np.asarray(model.S, dtype=np.float64),
            np.asarray(model.RHS, dtype=np.float64),
            np.asarray(model.obj, dtype=np.float64),
            lb,
            ub,
            biomass_value_star=biomass_value_star,
            it_lim=it_lim,
            tm_lim_ms=tm_lim_ms,
        )
        t_fva_wall = time.perf_counter() - t1_wall

        n_lps = stats["n_lps"]
        iters = np.asarray(stats["iters"], dtype=np.int64)
        per_lp = np.asarray(stats["per_lp_s"], dtype=np.float64)
        total_wall = t_fba_wall + t_fva_wall
        grand_totals["wall"] += total_wall
        grand_totals["n_lps"] += n_lps
        grand_totals["n_failures"] += len(stats["failures"])
        worst.append((total_wall, seed, tick, per_lp.max() if per_lp.size else 0.0))

        msg = (
            f"sample(seed={seed},tick={tick}) fba={t_fba_wall:.4f}s fva={t_fva_wall:.4f}s "
            f"total={total_wall:.4f}s n_lps={n_lps} iters[min={iters.min()},max={iters.max()},"
            f"mean={iters.mean():.1f}] per_lp_s[max={per_lp.max() if per_lp.size else 0:.4f}] "
            f"failures={len(stats['failures'])}"
        )
        if stats["failures"]:
            msg += f" FAILURE_DETAIL={stats['failures'][:3]}"
        print(msg)
        _sys.stdout.flush()

    worst.sort(reverse=True)
    print("=== SUMMARY ===")
    print(f"n_samples={len(samples)} total_wall={grand_totals['wall']:.4f}s "
          f"mean_per_sample={grand_totals['wall'] / len(samples):.4f}s "
          f"total_lps={grand_totals['n_lps']} total_failures={grand_totals['n_failures']}")
    print("worst 5 samples by total wall time:")
    for total_wall, seed, tick, worst_lp in worst[:5]:
        print(f"  seed={seed} tick={tick} total={total_wall:.4f}s worst_single_lp={worst_lp:.4f}s")
    projected_n50_m20 = grand_totals["wall"] / len(samples) * 50 * 20
    print(f"Projected N50xM20 runtime at this per-sample rate: {projected_n50_m20:.1f}s "
          f"({projected_n50_m20 / 3600:.3f} hours)")


if __name__ == "__main__":
    main()
