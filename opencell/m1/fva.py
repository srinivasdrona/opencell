from __future__ import annotations

import time
from dataclasses import dataclass
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

# GLP_EITLIM (7) / GLP_ETMLIM (9): the simplex call consumed its ENTIRE
# it_lim/tm_lim budget without resolving to GLP_OPT or a certified
# infeasible/unbounded status. This is the "genuinely slow/cycling" failure
# mode. By contrast, simplex_exit == 0 with sol_status == GLP_NOFEAS is a
# FAST, cheap failure (phase-1 terminates almost immediately once it
# certifies the current basis's face is empty) -- see the fallback-cascade
# reordering rationale below (`_solve_direction_with_fallback`).
_FVA_TIMEOUT_EXIT_CODES = frozenset({7, 9})

# Absolute (NOT relative) numerical floor for the objective-face window; see
# the detailed rationale at the `glp_set_row_bnds(lp, biomass_row, ...)` call
# site in `fva_range` below. The name says "ABS" because the code that
# consumes this constant is `eps = max(eps, _FVA_OBJ_FACE_NUMERIC_EPS_ABS *
# max(1.0, abs(biomass_value_star)))`: since the realistic biomass magnitude
# (~0.021) is always below the `max(1.0, ...)` floor, that floor -- not
# biomass_value_star -- always wins, so this constant is, in practice, an
# absolute additive tolerance on the objective value in flux units, not a
# tolerance relative to biomass_value_star. An earlier version of this
# comment incorrectly called it "relative"; it is not (see full correction
# below at the `glp_set_row_bnds` call site).
_FVA_OBJ_FACE_NUMERIC_EPS_ABS = 1e-9


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


@dataclass
class _SimplexAttempt:
    """Outcome of one `glp_simplex` call, used both to decide success/failure
    and to drive fallback-cascade telemetry (C4) and NOFEAS/timeout-aware
    reordering (C3)."""

    ok: bool
    simplex_exit: int
    sol_status: int
    iterations: int
    wall_time_s: float


def _run_simplex_attempt(glp: Any, lp: Any, parm: Any) -> _SimplexAttempt:
    t0 = time.perf_counter()
    simplex_exit = int(glp.glp_simplex(lp, parm))
    wall_time_s = time.perf_counter() - t0
    sol_status = int(glp.glp_get_status(lp))
    iterations = int(glp.glp_get_it_cnt(lp))
    ok = simplex_exit == 0 and sol_status == glp.GLP_OPT
    return _SimplexAttempt(
        ok=ok,
        simplex_exit=simplex_exit,
        sol_status=sol_status,
        iterations=iterations,
        wall_time_s=wall_time_s,
    )


def _solve_checked(glp: Any, lp: Any, parm: Any, *, label: str) -> None:
    attempt = _run_simplex_attempt(glp, lp, parm)
    if not attempt.ok:
        raise RuntimeError(
            f"{label} failed: simplex_exit={attempt.simplex_exit}, sol_status={attempt.sol_status}, "
            f"expected simplex_exit=0 and GLP_OPT({glp.GLP_OPT}). "
            f"iterations={attempt.iterations} (it_lim={_FVA_IT_LIM}, tm_lim_ms={_FVA_TM_LIM_MS})"
        )


def new_fva_solver_telemetry() -> dict[str, Any]:
    """Return a fresh, empty telemetry accumulator for `fva_range(...,
    telemetry=...)`. Purely a diagnostic record of solver-strategy attempts
    (attempts/successes/failures/wall time/iterations per fallback
    strategy) -- it carries NO authority over the returned v_min/v_max or
    any downstream PASS/FAIL verdict; it exists only so operators can see
    which fallback strategies are actually doing work in a given sweep."""
    return {
        "total_solves": 0,
        "solves_needing_fallback": 0,
        "max_attempts_single_solve": 0,
        "total_wall_time_s": 0.0,
        "strategies": {},
    }


def _telemetry_record_attempt(
    telemetry: dict[str, Any] | None,
    strategy_name: str,
    attempt_iterations_delta: int,
    attempt: _SimplexAttempt,
) -> None:
    if telemetry is None:
        return
    stats = telemetry["strategies"].setdefault(
        strategy_name,
        {"attempts": 0, "successes": 0, "failures": 0, "wall_time_s": 0.0, "iterations": 0},
    )
    stats["attempts"] += 1
    stats["successes" if attempt.ok else "failures"] += 1
    stats["wall_time_s"] += attempt.wall_time_s
    stats["iterations"] += attempt_iterations_delta
    telemetry["total_wall_time_s"] += attempt.wall_time_s


def _telemetry_record_solve_complete(telemetry: dict[str, Any] | None, n_attempts: int) -> None:
    if telemetry is None:
        return
    telemetry["total_solves"] += 1
    if n_attempts > 1:
        telemetry["solves_needing_fallback"] += 1
    telemetry["max_attempts_single_solve"] = max(telemetry["max_attempts_single_solve"], n_attempts)


# THIRD root cause (see benchmarks/bench_fva_seed0_tick0_j392_diag.py +
# bench_fva_seed0_tick0_full_subset_repro.py, 2026-07-29): the real full
# N50xM20 sweep hit a column (sample seed=0/tick=0, j=392, MIN) that timed
# out (GLP_ETMLIM, 877,903 iterations in 10s) under the shipped PSE-pricing
# + per-solve `glp_adv_basis` reset -- yet re-solving the IDENTICAL LP data
# (byte-for-byte same S/rhs/c/lb/ub/biomass_value_star) for this exact
# sample+column in isolation, and also as part of the full 166-column
# sequence run standalone, both converged instantly (<0.03s). This was not
# reproducible on demand, consistent with floating-point-level sensitivity
# of a near-degenerate LP (e.g. from run-to-run BLAS/thread-scheduling
# nondeterminism feeding `compute_bounds`/`solve_fba`) rather than a fixed
# bug: the same solver, given the same inputs, is deterministic, so a
# transient failure like this can only mean the actual floating-point inputs
# differed at the ULP level between runs, which for a genuinely
# near-degenerate face can swing simplex onto a catastrophically long
# pivot path in one run and not another. Because this class of failure is
# fundamentally non-reproducible-on-demand, it cannot be eliminated by
# fixing "the one bad case" -- instead every individual min/max solve now
# retries, on failure, through a short cascade of alternative
# algorithmically-independent strategies (different pricing rule and/or
# different crash-basis constructor) before giving up. Every strategy solves
# the mathematically IDENTICAL LP (same rows/cols/bounds/objective/
# objective-face window) -- by LP strong duality, any solve that terminates
# with GLP_OPT status carries an implicit optimality certificate (its
# reduced costs/dual values satisfy complementary slackness), so accepting
# the first strategy to reach GLP_OPT cannot change the mathematical answer,
# only which deterministic pivot path was used to certify it.
#
# CASCADE ORDERING (C3 correction, 2026-07-29, see
# benchmarks/bench_fva_fallback_cascade_telemetry.py): a failure's EXIT CODE
# tells us how expensive it was and whether retrying the SAME basis with
# only a different pricing rule is likely to help quickly:
#   - simplex_exit == 0, sol_status == GLP_NOFEAS: phase-1 CERTIFIED
#     infeasibility of the current basis's face -- this is typically fast
#     (does not consume the tm_lim budget) and, per the second root cause
#     above, is frequently a basis/pricing artifact rather than a genuine
#     empty face (the face is non-empty by construction: the "FVA primary"
#     solve already exhibited a feasible point on it). Retrying immediately
#     with a different pricing rule under the SAME basis is cheap and often
#     resolves it.
#   - simplex_exit in {GLP_EITLIM(7), GLP_ETMLIM(9)}: the attempt consumed
#     its ENTIRE it_lim/tm_lim budget (up to the full 10s tm_lim) without
#     resolving -- this is the expensive case. Immediately retrying the same
#     basis with only a different pricing rule risks paying a SECOND full
#     ~10s timeout before reaching a strategy that changes the basis
#     structurally. Since the whole point of `_FVA_FALLBACK_STRATEGIES` is
#     that different BASIS constructors (not just pricing rules) are the
#     more likely lever to escape a genuine cycle, a slow (timeout) failure
#     skips the immediately-following same-basis/different-pricing entry and
#     jumps straight to the next DIFFERENT-basis strategy. This changes
#     nothing about which strategies are eventually tried (every strategy in
#     the list can still be reached), only the ORDER/whether a same-basis
#     retry is attempted after a genuine timeout -- so it cannot change the
#     mathematical answer (see the strong-duality argument above), only wall
#     time. Measured effect: see
#     benchmarks/bench_fva_fallback_cascade_telemetry.py for real before/after
#     wall-time numbers on known-hard samples.
_FVA_FALLBACK_STRATEGIES: tuple[tuple[str, str, int], ...] = (
    # (strategy_name, basis_kind, pricing_variant)
    # pricing_variant: 0 = GLP_PT_PSE, 1 = GLP_PT_STD, 2 = GLP_PT_PSE + presolve ON
    ("adv_pse", "adv", 0),  # primary: fresh advanced/crash basis, PSE pricing (already tried)
    ("adv_std", "adv", 1),  # SAME crash basis, STD (Dantzig) pricing -- cheap immediate retry
    ("std_pse", "std", 0),  # DIFFERENT (trivial all-slack) basis, PSE pricing
    ("std_std", "std", 1),  # different basis, STD pricing
    ("adv_pse_presolve", "adv", 2),  # last resort: fresh crash basis, PSE pricing, presolve ON
)


def _solve_direction_with_fallback(
    glp: Any,
    lp: Any,
    base_parm: Any,
    *,
    j: int,
    direction: int,
    label: str,
    telemetry: dict[str, Any] | None = None,
) -> None:
    """Solve one min/max direction for column `j`, retrying with independent
    solver strategies (see `_FVA_FALLBACK_STRATEGIES` above) if earlier
    strategies fail to certify GLP_OPT. Raises RuntimeError only if every
    strategy fails.

    `telemetry`, if given, must be a dict from `new_fva_solver_telemetry()`;
    it is updated in place with per-strategy attempt/success/failure/
    wall-time/iteration counters. Purely a diagnostic side channel -- it
    never affects which strategy is accepted or the returned LP solution.
    """
    glp.glp_set_obj_dir(lp, direction)
    errors: list[str] = []
    n_attempts = 0
    idx = 0
    strategies = _FVA_FALLBACK_STRATEGIES
    prev_cumulative_iters = int(glp.glp_get_it_cnt(lp))
    while idx < len(strategies):
        strategy_name, basis_kind, pricing_variant = strategies[idx]
        if basis_kind == "adv":
            glp.glp_adv_basis(lp, 0)
        else:
            glp.glp_std_basis(lp)

        parm = glp.glp_smcp()
        glp.glp_init_smcp(parm)
        parm.msg_lev = glp.GLP_MSG_OFF
        parm.presolve = glp.GLP_ON if pricing_variant == 2 else glp.GLP_OFF
        parm.meth = glp.GLP_PRIMAL
        parm.tol_bnd = base_parm.tol_bnd
        parm.pricing = glp.GLP_PT_STD if pricing_variant == 1 else glp.GLP_PT_PSE
        parm.it_lim = _FVA_IT_LIM
        parm.tm_lim = _FVA_TM_LIM_MS

        n_attempts += 1
        attempt = _run_simplex_attempt(glp, lp, parm)
        cumulative_iters = int(glp.glp_get_it_cnt(lp))
        _telemetry_record_attempt(
            telemetry, strategy_name, cumulative_iters - prev_cumulative_iters, attempt
        )
        prev_cumulative_iters = cumulative_iters

        if attempt.ok:
            _telemetry_record_solve_complete(telemetry, n_attempts)
            return

        errors.append(
            f"{label} [{strategy_name}] failed: simplex_exit={attempt.simplex_exit}, "
            f"sol_status={attempt.sol_status}, iterations={attempt.iterations}"
        )

        # C3 reordering: after a genuine timeout (not a fast NOFEAS), skip an
        # immediately-following same-basis/different-pricing retry -- see the
        # rationale above `_FVA_FALLBACK_STRATEGIES`.
        if (
            attempt.simplex_exit in _FVA_TIMEOUT_EXIT_CODES
            and idx + 1 < len(strategies)
            and strategies[idx + 1][1] == basis_kind
        ):
            idx += 2
        else:
            idx += 1

    _telemetry_record_solve_complete(telemetry, n_attempts)
    raise RuntimeError(
        f"{label} failed after exhausting all {len(_FVA_FALLBACK_STRATEGIES)} fallback "
        f"strategies: " + " | ".join(errors)
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
    telemetry: dict[str, Any] | None = None,
    _face_mode: str = "db",
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
    telemetry : optional dict from `new_fva_solver_telemetry()`. When given,
        it is updated in place with per-fallback-strategy solver diagnostics
        (attempts/successes/failures/wall-time/iterations), plus a
        `"fva_primary_objective_value"` entry (the internally-recomputed
        primary-solve optimum, for comparison against the caller-supplied
        `biomass_value_star`). Purely informational -- omitting it (default
        `None`) reproduces prior behavior/API exactly, and passing it never
        changes the returned v_min/v_max or which strategy is accepted for
        any solve.
    """
    if _face_mode not in ("db", "fx"):
        raise ValueError(f"_face_mode must be 'db' or 'fx', got {_face_mode!r}")
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
        if telemetry is not None:
            telemetry["fva_primary_objective_value"] = float(glp.glp_get_obj_val(lp))

        # Add objective-face constraint: c'v == biomass_value_star (or ±epsilon window).
        glp.glp_add_rows(lp, 1)
        biomass_row = int(glp.glp_get_num_rows(lp))
        # Always use GLP_DB (double-bounded) with at least a tiny numeric
        # floor, never an exact GLP_FX equality, even when epsilon_obj == 0.
        #
        # WHY THIS ROW EXISTS (corrected 2026-07-29 review pass -- see
        # benchmarks/bench_fva_fx_vs_db_objective_face_equivalence.py for the
        # full reproducible measurement this paragraph summarizes):
        # `biomass_value_star` is computed by a SEPARATE `solve_fba` call on
        # its own independently-scaled LP instance, while the "FVA primary"
        # solve two lines above re-solves the mathematically identical
        # optimization on THIS LP instance (own `glp_scale_prob` scaling,
        # own basis/pricing path). Both should reach the same true optimum,
        # but two independent floating-point LP solves of the same
        # continuous optimum are not guaranteed to agree to the last bit.
        # This row's job is to constrain every subsequent min/max solve to
        # the face {v : c'v == biomass_value_star}, so it must tolerate that
        # cross-solve mismatch -- an EXACT GLP_FX equality against the
        # externally-supplied value does not, and empirically fails: see
        # benchmarks/bench_fva_j417_nofeas_diag.py (sample seed=20/tick=16,
        # column j=417) for the first observed case, where a hard GLP_FX row
        # made primal simplex's phase-1 spuriously report GLP_NOFEAS from a
        # fresh crash basis even though the row's own optimum (the "FVA
        # primary" solve one line above) trivially satisfies it exactly, so
        # the face is provably non-empty.
        #
        # `_FVA_OBJ_FACE_NUMERIC_EPS_ABS` (1e-9) is an ABSOLUTE additive
        # window in objective (flux) units, NOT a value scaled down further
        # by `biomass_value_star`'s own magnitude -- see the constant's
        # definition above for why. Do NOT reason about its safety from "1e-9
        # is obviously tiny": `substrate_delta_range_from_fva` can amplify a
        # flux-unit epsilon into a downstream d_min/d_max shift of up to
        # ~2.6e3 whole-molecule counts (larger than the `_METABOLISM_FVA_TOL
        # = 2.0` count-scale pass tolerance in the L2.2 gate) -- so a window
        # that were merely "small in flux units" would NOT automatically be
        # safe on the count scale a caller ultimately reads. Its actual
        # justification is empirical, not a magnitude argument:
        #   1. It covers the REAL observed cross-solve mismatch between the
        #      internal "FVA primary" objective value and
        #      `biomass_value_star`, which independent measurement across a
        #      pre-registered 100-sample set (50 seeds x ticks {0,1}; see
        #      benchmarks/artifacts/fva_fx_vs_db_objective_face_equivalence.json)
        #      found to have a maximum absolute value of 2.8939350915635487e-13
        #      (mean 1.32650869455464e-13) -- i.e. the 1e-9 window covers the
        #      actual observed mismatch with ~3.54 orders of magnitude of
        #      margin (log10(1e-9 / 2.894e-13) ~= 3.54), it is not an
        #      arbitrary "small" choice.
        #   2. Without ANY window (exact GLP_FX equality, epsilon_obj=0 and
        #      no floor), the *single-attempt* solve (i.e. without the
        #      fallback cascade below) fails to reach GLP_OPT on 1/100
        #      pre-registered samples (seed=12/tick=1) and reproducibly on
        #      the original historically-documented case (seed=20/tick=16,
        #      column j=417: GLP_NOFEAS, 37595 iterations -- see
        #      benchmarks/bench_fva_j417_nofeas_diag.py). At seed=20/tick=16
        #      specifically, exact FX fails EVERY strategy in the full
        #      5-strategy fallback cascade below (all NOFEAS/ENOPFS, 37595-
        #      39098 iterations) -- i.e. no amount of pivoting/basis retrying
        #      recovers that face, which is the strongest evidence the
        #      window is necessary, not merely convenient, for at least this
        #      sample. With the shipped fallback cascade active, measured
        #      exact-FX failure across the full 100-sample set drops to
        #      0/100, but that cascade is an independent robustness fix
        #      (root causes #1-#3 above) that a caller should not rely on in
        #      place of this window: the cascade cannot always recover a
        #      genuinely-infeasible exact-equality face (as seed=20/tick=16
        #      demonstrates), so this window remains the correct fix at the
        #      LP-construction level. NOTE: an earlier (rejected) review
        #      draft of this comment cited a ~15.7% exact-FX failure rate
        #      across 102 samples/150,930 pairs; that figure could not be
        #      reproduced against this 100-sample pre-registered set under
        #      the shipped cascade and is very likely explained by either a
        #      wider tick range (the original bug sample is at tick=16,
        #      outside the {0,1} set measured here) or a baseline that did
        #      not include the already-shipped fallback cascade. This
        #      comment reports what was actually independently measured,
        #      not the earlier unreproduced figure.
        # The same benchmark also sweeps epsilon_obj across several orders
        # of magnitude around this floor and confirms the final feasibility
        # classification (and every d_min/d_max value) is unchanged (0
        # flips) across the swept range, i.e. this window's exact size is
        # not something the pass/fail outcome is sensitive to within that
        # practical bracket -- it is the smallest floor that reliably clears
        # the observed mismatch, not a fitted/tuned value. This is purely an
        # IEEE-754 floating-point equality-constraint engineering fix, not a
        # change to the caller-supplied `epsilon_obj` mathematical range
        # parameter (which continues to widen the face beyond this floor
        # exactly as before whenever epsilon_obj > the floor).
        eps = float(max(0.0, epsilon_obj))
        eps = max(eps, _FVA_OBJ_FACE_NUMERIC_EPS_ABS * max(1.0, abs(float(biomass_value_star))))
        if _face_mode == "fx":
            # Benchmark/test-only escape hatch (see
            # benchmarks/bench_fva_fx_vs_db_objective_face_equivalence.py):
            # forces the EXACT GLP_FX equality this module used to ship with
            # (no window at all), reusing the identical LP construction,
            # reaction_subset, and fallback cascade as production `_face_mode
            # == "db"`, so the two modes are an apples-to-apples comparison.
            # Never used by any production caller (`fva_range`'s public
            # signature has no `_face_mode` parameter to set this).
            glp.glp_set_row_bnds(
                lp, biomass_row, glp.GLP_FX, float(biomass_value_star), float(biomass_value_star)
            )
        else:
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
            # THIRD root cause fix: if the primary (PSE + fresh advanced
            # basis) attempt fails to certify GLP_OPT, retry through a small
            # cascade of algorithmically-independent strategies -- see
            # `_solve_direction_with_fallback` above for the full rationale
            # and why this cannot change the mathematical answer.
            _solve_direction_with_fallback(
                glp, lp, parm, j=j, direction=glp.GLP_MAX,
                label=f"FVA max j={j}", telemetry=telemetry,
            )
            v_max[j] = float(glp.glp_get_col_prim(lp, j + 1))

            _solve_direction_with_fallback(
                glp, lp, parm, j=j, direction=glp.GLP_MIN,
                label=f"FVA min j={j}", telemetry=telemetry,
            )
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
