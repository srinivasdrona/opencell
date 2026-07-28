from __future__ import annotations

from typing import Any

import numpy as np

from opencell.m1.karr_metabolism_writeback import (
    ATP_HYDROLYSIS_SIGNS,
    CYTOSOL,
    EXTRACELLULAR,
    KarrWritebackFixture,
)


_N_SUBSTRATES = 585
_N_COMPARTMENTS = 3

# Defensive iteration/time caps applied to every individual min/max solve.
# Root cause (see benchmarks/bench_fva_profile.py + bench_fva_pricing_fix.py,
# 2026-07-29): GLP_PT_STD (Dantzig/textbook) pricing on this degenerate,
# ill-scaled network (A-matrix ratio ~3.6e8) can force primal simplex into
# hundreds of thousands to millions of degenerate pivots for specific
# (sample, reaction) pairs -- observed up to ~8.5M cumulative iterations on
# one sample before a 60s/call cap was hit, which is exactly what stalled the
# live N50/M20 run for ~8.7 CPU-hours after a single sample. Switching to
# GLP_PT_PSE (projected steepest-edge) pricing resolves this: verified
# identical optimal values (max abs diff ~3.5e-10) on every column where the
# old STD pricing still converged, and independently-verified-feasible optima
# (mass-balance residual ~2.6e-8, biomass-face residual ~3.5e-18) on the
# columns where STD previously never converged. A pricing rule can only
# change which optimal vertex/path is explored, never the true optimal value
# of a linear objective over a fixed polytope, so this is a solver-equivalent
# fix, not a behavior change. `_FVA_IT_LIM`/`_FVA_TM_LIM_MS` are a pure safety
# net (per-call bounds far above anything observed under PSE pricing, where
# the worst pathological column needed <500 iterations): if some future
# sample is still pathological even under PSE, the solve now fails loudly
# with a RuntimeError instead of hanging indefinitely.
# SECOND root cause (see benchmarks/bench_fva_j390_diag.py +
# bench_fva_j390_sequence_diag.py + bench_fva_basis_reset_fix.py,
# 2026-07-29): even under PSE pricing, WARM-STARTING each column's min/max
# solve from the basis left behind by the PREVIOUS column's solve can itself
# induce catastrophic degenerate cycling independent of the pricing rule.
# Example: sample (seed=0, tick=2) column j=390 (MIN) converges in 30
# iterations when solved from a fresh advanced basis, but had still not
# converged after 186,954 iterations / 15s when warm-started from whatever
# basis the prior column's solve ended on. Resetting to a fresh
# `glp_adv_basis` before every individual min/max solve eliminates this:
# every solve in a representative full sweep (143 relevant columns of sample
# (0,2)) completed within 260 iterations, ~4-5ms/solve overhead included.
# The LP's feasible region and objective are identical regardless of
# starting basis, so this cannot change the true optimal value -- only which
# path simplex takes -- making it a solver-equivalent robustness fix like
# the pricing change, not a behavior change.
# NOTE on GLPK semantics (empirically verified, benchmarks/bench_fva_*):
# `it_lim` is compared against `glp_get_it_cnt`, which is CUMULATIVE over the
# LP object's whole lifetime (every glp_simplex() call on it), not per call --
# so it must be sized for the entire sweep's total iteration budget, not one
# column. `tm_lim` DOES reset per glp_simplex() call (confirmed empirically:
# three independent columns each independently consumed their own full
# tm_lim window), so it is the reliable per-call safety net.
_FVA_IT_LIM = 5_000_000
_FVA_TM_LIM_MS = 10_000

# Numerical (not scientific) floor for the objective-face window; see the
# detailed rationale at the `glp_set_row_bnds(lp, biomass_row, ...)` call
# site in `fva_range` below.
_FVA_OBJ_FACE_NUMERIC_EPS_REL = 1e-9


def _configure_simplex_params(glp: Any) -> Any:
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_OFF
    parm.meth = glp.GLP_PRIMAL
    parm.tol_bnd = 1e-6
    parm.pricing = glp.GLP_PT_PSE
    parm.it_lim = _FVA_IT_LIM
    parm.tm_lim = _FVA_TM_LIM_MS
    return parm


def _solve_checked(glp: Any, lp: Any, parm: Any, *, label: str) -> None:
    simplex_exit = int(glp.glp_simplex(lp, parm))
    sol_status = int(glp.glp_get_status(lp))
    if simplex_exit != 0 or sol_status != glp.GLP_OPT:
        raise RuntimeError(
            f"{label} failed: simplex_exit={simplex_exit}, sol_status={sol_status}, "
            f"expected simplex_exit=0 and GLP_OPT({glp.GLP_OPT}). "
            f"iterations={int(glp.glp_get_it_cnt(lp))} (it_lim={_FVA_IT_LIM}, tm_lim_ms={_FVA_TM_LIM_MS})"
        )


def fva_range(
    S: np.ndarray,
    rhs: np.ndarray,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    biomass_value_star: float,
    epsilon_obj: float = 0.0,
    reaction_subset: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Run reaction-wise FVA on the biomass-optimal face.

    Parameters
    ----------
    reaction_subset : optional array of reaction column indices (0-based).
        When given, only these reactions are min/max-solved; all other
        v_min/v_max entries are left as NaN. This is a pure performance
        optimization for callers (e.g. the L2.2 substrate-delta feasibility
        gate) that only ever read a known-fixed subset of the 504 reactions
        downstream (see `substrate_delta_range_from_fva`, which only ever
        indexes `fixture.fba_idx_external`/`fba_idx_internal`); solving the
        remaining, unread columns has zero effect on any consumer and is
        skipped mechanically. When omitted (default), every reaction is
        solved, exactly reproducing prior behavior/API.

        Regardless of `reaction_subset`, any reaction with `lb[j] == ub[j]`
        is never solved via LP: its value is pinned to that single feasible
        point by construction (the column has a fixed GLP_FX bound), so
        `v_min[j] = v_max[j] = lb[j]` is set directly. This is an exact
        algebraic simplification (not an approximation) and applies whether
        or not the caller passed `reaction_subset`.
    """
    import swiglpk as glp  # noqa: PLC0415

    S = np.asarray(S, dtype=np.float64)
    rhs = np.asarray(rhs, dtype=np.float64).reshape(-1)
    c = np.asarray(c, dtype=np.float64).reshape(-1)
    lb = np.asarray(lb, dtype=np.float64).reshape(-1)
    ub = np.asarray(ub, dtype=np.float64).reshape(-1)

    if S.ndim != 2:
        raise ValueError(f"S must be 2D, got shape {S.shape}")
    m_rows, n_rxn = S.shape
    if rhs.shape != (m_rows,):
        raise ValueError(f"rhs shape mismatch: expected {(m_rows,)}, got {rhs.shape}")
    if c.shape != (n_rxn,):
        raise ValueError(f"c shape mismatch: expected {(n_rxn,)}, got {c.shape}")
    if lb.shape != (n_rxn,) or ub.shape != (n_rxn,):
        raise ValueError(
            f"bounds shape mismatch: expected {(n_rxn,)}, got lb={lb.shape}, ub={ub.shape}"
        )
    if np.any(lb > ub):
        raise ValueError("invalid bounds: lb > ub for one or more reactions")

    if reaction_subset is None:
        target_cols = np.arange(n_rxn, dtype=np.int64)
    else:
        target_cols = np.unique(np.asarray(reaction_subset, dtype=np.int64).reshape(-1))
        if target_cols.size and (target_cols.min() < 0 or target_cols.max() >= n_rxn):
            raise ValueError(
                f"reaction_subset entries must be within [0, {n_rxn}); "
                f"got min={target_cols.min() if target_cols.size else None}, "
                f"max={target_cols.max() if target_cols.size else None}"
            )

    v_min = np.full(n_rxn, np.nan, dtype=np.float64)
    v_max = np.full(n_rxn, np.nan, dtype=np.float64)

    # Trivial fast path: fixed-bound reactions never need an LP solve, on
    # `target_cols` or otherwise -- fill them directly and remove from the
    # solve list.
    fixed_mask = lb[target_cols] == ub[target_cols]
    fixed_cols = target_cols[fixed_mask]
    v_min[fixed_cols] = lb[fixed_cols]
    v_max[fixed_cols] = lb[fixed_cols]
    solve_cols = target_cols[~fixed_mask]

    lp = glp.glp_create_prob()
    try:
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
        _solve_checked(glp, lp, parm, label="FVA primary")

        # Add objective-face constraint: c'v == biomass_value_star (or ±epsilon window).
        glp.glp_add_rows(lp, 1)
        biomass_row = int(glp.glp_get_num_rows(lp))
        # Always use GLP_DB (double-bounded) with at least a tiny numeric
        # floor, never an exact GLP_FX equality, even when epsilon_obj == 0.
        # Root cause (see benchmarks/bench_fva_j417_nofeas_diag.py +
        # bench_fva_objval_mismatch_diag.py, 2026-07-29): on this ill-scaled
        # network (A-matrix ratio ~3.6e8), a hard GLP_FX row can make primal
        # simplex's phase-1 spuriously report GLP_NOFEAS from a fresh crash
        # basis -- e.g. sample (seed=20, tick=16) column j=417 -- even though
        # the row's own optimum (found by the "FVA primary" solve one line
        # above) trivially satisfies it exactly, so the face is provably
        # non-empty. Relaxing to a minuscule GLP_DB window of
        # `_FVA_OBJ_FACE_NUMERIC_EPS_REL` (1e-9, relative to the objective
        # magnitude) resolves this while changing nothing scientifically:
        # it is 3-9 orders of magnitude below every existing feasibility
        # tolerance in this pipeline (test tolerances of 1e-4/1e-6/2.0;
        # `_METABOLISM_FVA_TOL = 2.0` in the L2.2 gate), and is purely an
        # IEEE-754 floating-point equality-constraint engineering fix, not a
        # change to the caller-supplied `epsilon_obj` mathematical range
        # parameter (which continues to widen the face beyond this floor
        # exactly as before whenever epsilon_obj > the floor).
        eps = float(max(0.0, epsilon_obj))
        eps = max(eps, _FVA_OBJ_FACE_NUMERIC_EPS_REL * max(1.0, abs(float(biomass_value_star))))
        glp.glp_set_row_bnds(
            lp,
            biomass_row,
            glp.GLP_DB,
            float(biomass_value_star - eps),
            float(biomass_value_star + eps),
        )

        nz = np.flatnonzero(np.abs(c) > 0.0)
        if nz.size == 0:
            raise ValueError("objective vector c is all zeros; cannot define biomass-optimal face")
        ind = glp.intArray(int(nz.size) + 1)
        val = glp.doubleArray(int(nz.size) + 1)
        for k, col in enumerate(nz, start=1):
            ind[k] = int(col) + 1
            val[k] = float(c[col])
        glp.glp_set_mat_row(lp, biomass_row, int(nz.size), ind, val)

        # Clear objective coefficients and solve each reaction min/max.
        for j in range(n_rxn):
            glp.glp_set_obj_coef(lp, j + 1, 0.0)

        for j in solve_cols.tolist():
            glp.glp_set_obj_coef(lp, j + 1, 1.0)

            # Reset to a fresh advanced (crash) basis before every individual
            # min/max solve. Root cause (see benchmarks/bench_fva_j390_*.py,
            # bench_fva_basis_reset_fix.py, 2026-07-29): warm-starting each
            # solve from whatever basis the PREVIOUS column's solve ended on
            # can itself induce catastrophic degenerate cycling -- e.g.
            # sample (seed=0, tick=2) column j=390 MIN converges in 30
            # iterations from a fresh basis but still had not converged after
            # 186,954 iterations / 15s when warm-started from the prior
            # column's basis. This is independent of the STD-vs-PSE pricing
            # fix above (both can be pathological under warm starts). Since
            # the LP's feasible region and objective are identical regardless
            # of starting basis, resetting cannot change the true optimal
            # value -- only which path simplex takes to reach it -- so this
            # is a solver-equivalent robustness fix, not a behavior change.
            # Cost is small: rebuilding the crash basis for all 143 relevant
            # columns of a representative sample added ~4-5ms/solve and kept
            # every individual solve under 260 iterations.
            glp.glp_adv_basis(lp, 0)
            glp.glp_set_obj_dir(lp, glp.GLP_MAX)
            _solve_checked(glp, lp, parm, label=f"FVA max j={j}")
            v_max[j] = float(glp.glp_get_col_prim(lp, j + 1))

            glp.glp_adv_basis(lp, 0)
            glp.glp_set_obj_dir(lp, glp.GLP_MIN)
            _solve_checked(glp, lp, parm, label=f"FVA min j={j}")
            v_min[j] = float(glp.glp_get_col_prim(lp, j + 1))

            glp.glp_set_obj_coef(lp, j + 1, 0.0)

        return v_min, v_max
    finally:
        glp.glp_delete_prob(lp)


def substrate_delta_range_from_fva(
    v_min: np.ndarray,
    v_max: np.ndarray,
    fixture: KarrWritebackFixture,
    growth_per_s: float,
    step_size_sec: float,
    pre_state_585x3: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project flux-range bounds through Karr writeback Step1+2 + deterministic Step3+4."""
    v_min = np.asarray(v_min, dtype=np.float64).reshape(-1)
    v_max = np.asarray(v_max, dtype=np.float64).reshape(-1)
    pre_state_585x3 = np.asarray(pre_state_585x3, dtype=np.float64)

    if v_min.shape != v_max.shape:
        raise ValueError(f"v_min/v_max shape mismatch: {v_min.shape} vs {v_max.shape}")
    if pre_state_585x3.shape != (_N_SUBSTRATES, _N_COMPARTMENTS):
        raise ValueError(
            "pre_state_585x3 shape mismatch: "
            f"expected {(_N_SUBSTRATES, _N_COMPARTMENTS)}, got {pre_state_585x3.shape}"
        )

    # Step1+Step2 linear projection from per-reaction intervals.
    step12_min = np.zeros((_N_SUBSTRATES, _N_COMPARTMENTS), dtype=np.float64)
    step12_max = np.zeros((_N_SUBSTRATES, _N_COMPARTMENTS), dtype=np.float64)
    step = float(step_size_sec)

    for sub_idx, rxn_idx in zip(fixture.sub_idx_external, fixture.fba_idx_external, strict=True):
        coeff = -step
        j = int(rxn_idx)
        lo = coeff * (v_max[j] if coeff < 0.0 else v_min[j])
        hi = coeff * (v_min[j] if coeff < 0.0 else v_max[j])
        step12_min[int(sub_idx), EXTRACELLULAR] += float(lo)
        step12_max[int(sub_idx), EXTRACELLULAR] += float(hi)

    for sub_idx, rxn_idx in zip(fixture.sub_idx_internal, fixture.fba_idx_internal, strict=True):
        coeff = 1.0
        j = int(rxn_idx)
        lo = coeff * (v_max[j] if coeff < 0.0 else v_min[j])
        hi = coeff * (v_min[j] if coeff < 0.0 else v_max[j])
        step12_min[int(sub_idx), CYTOSOL] += float(lo)
        step12_max[int(sub_idx), CYTOSOL] += float(hi)

    # Step3+Step4 deterministic contribution on the biomass-optimal face.
    deterministic = np.zeros((_N_SUBSTRATES, _N_COMPARTMENTS), dtype=np.float64)
    deterministic += fixture.metabolism_new_production * float(growth_per_s) * step
    unaccounted = fixture.unaccounted_energy_consumption * float(growth_per_s) * step
    deterministic[fixture.sub_idx_atp_hydrolysis, CYTOSOL] += (
        ATP_HYDROLYSIS_SIGNS.astype(np.float64) * unaccounted
    )

    d_min = step12_min + deterministic
    d_max = step12_max + deterministic

    # Step5 clipping as interval transform: metabolite deltas are floored at -pre_state.
    met_rows = np.asarray(fixture.metabolite_row_idx, dtype=np.int64)
    floors = -pre_state_585x3[met_rows, :]
    d_min[met_rows, :] = np.maximum(d_min[met_rows, :], floors)
    d_max[met_rows, :] = np.maximum(d_max[met_rows, :], floors)
    return d_min, d_max


__all__ = ["fva_range", "substrate_delta_range_from_fva"]
