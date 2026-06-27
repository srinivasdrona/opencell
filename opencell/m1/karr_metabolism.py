"""Karr-native M1 metabolism module.

Loads Karr's fitted FBA snapshot directly:
  - S: 376 x 504 (fbaReactionStoichiometryMatrix)
  - lb, ub: from fbaReactionBounds (504, 2)
  - obj: fbaObjective (504,) -- biomass at col 502 with coefficient +1000
  - RHS: fbaRightHandSide (376,)
  - reaction WCM IDs (645) and per-FBA-column WCM IDs (504, sparse)
  - Karr's stored runtime fluxs[645] (Mode E oracle)

Replaces the iPS189-based opencell.m1.central_carbon for whole-cell
work.  Same ID space as Karr's other 27 processes, so M1 plugs into
the dynamic loop (vivarium chassis) without translation.

Important: snapshot fbaEnzymeBounds are NOT applied by default.  They
are post-step values (free-enzyme count after substrate binding) and
were proven inconsistent with Karr's own stored fluxs (34/504 cols
violate them by up to 100x).  See Session N+8 / commit c5244f2.
The bounds are exposed for inspection but excluded from the LP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "karr_native_m1.json"
)

# Default flux ceiling used when relaxing infinities for HiGHS.  Set to
# Karr's natural per-cell-per-second range (stored fluxs span [-1e6, 1e6]
# but conversion fluxes typically <= 1e3).  Documented in
# `artifacts/M1_validation.json` (schema_v4 Mode D).
DEFAULT_BIG = 1e3


@dataclass
class KarrMetabolismModel:
    S: np.ndarray
    RHS: np.ndarray
    lb: np.ndarray
    ub: np.ndarray
    obj: np.ndarray
    enz_bounds: np.ndarray
    catalysis: np.ndarray
    fluxs_stored: np.ndarray
    rxn_wcm_ids_645: list[str]
    fba_col_rxn_wcm: list[str | None]
    biomass_col: int
    stored_runtime: dict
    counts: dict
    raw: dict = field(repr=False)

    @property
    def n_reactions(self) -> int:
        return self.S.shape[1]

    @property
    def n_substrates(self) -> int:
        return self.S.shape[0]

    def reaction_wcm_id_to_645_index(self, wcm_id: str) -> int:
        return self.rxn_wcm_ids_645.index(wcm_id)

    def fba_col_for_wcm_id(self, wcm_id: str) -> int | None:
        """Return the 504-space FBA column for a Karr WCM reaction ID, or None
        if that reaction is not in the metabolicConversion subset."""
        for col, name in enumerate(self.fba_col_rxn_wcm):
            if name == wcm_id:
                return col
        return None


def load_default(path: str | Path | None = None) -> KarrMetabolismModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    meta = json.loads(p.read_text())
    npz_path = p.parent / Path(meta["matrix_npz"]).name
    z = np.load(npz_path)
    return KarrMetabolismModel(
        S=z["S"],
        RHS=z["RHS"],
        lb=z["lb"],
        ub=z["ub"],
        obj=z["obj"],
        enz_bounds=z["enz_bounds"],
        catalysis=z["catalysis"],
        fluxs_stored=z["fluxs_stored"],
        rxn_wcm_ids_645=list(meta["ids"]["reaction_wcm_645"]),
        fba_col_rxn_wcm=list(meta["ids"]["fba_col_to_reaction_wcm"]),
        biomass_col=int(meta["biomass_col"]),
        stored_runtime=dict(meta["stored_runtime"]),
        counts=dict(meta["counts"]),
        raw=meta,
    )


def _solve_fba_glpk(
    model: "KarrMetabolismModel",
    *,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    sense: str,
) -> tuple[np.ndarray, float, str]:
    """GLPK 5.0 (swiglpk) backend for solve_fba.

    ``c`` is the natural-sense objective vector (positive coefficient on
    biomass for the "max" sense). Caller MUST NOT pre-apply the
    linprog-minimization sign flip; this helper drives GLPK's GLP_MAX /
    GLP_MIN directly.

    Matches Karr 2012's solver family (GLPK MEX). Used for L2.2 fidelity:
    on a degenerate LP (cond ~ 6.7e+12 on the metabolism allocated state)
    HiGHS and GLPK pick different vertices and produce ~50M difference in
    flux L1 norm; GLPK is ~6.7x closer to Karr's recorded MATLAB GLPK flux.

    Lazy import: swiglpk is an optional dependency.
    """
    import swiglpk as glp  # noqa: PLC0415 — optional dep, only loaded on demand

    R = c.shape[0]
    M = model.S.shape[0]
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)

    lp = glp.glp_create_prob()
    try:
        glp.glp_set_obj_dir(lp, glp.GLP_MAX if sense == "max" else glp.GLP_MIN)
        glp.glp_add_rows(lp, M)
        for i in range(M):
            glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))
        glp.glp_add_cols(lp, R)
        for j in range(R):
            lj, uj = float(lb[j]), float(ub[j])
            if lj == uj:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lj, uj)
            else:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lj, uj)
            glp.glp_set_obj_coef(lp, j + 1, float(c[j]))

        S = np.asarray(model.S, dtype=np.float64)
        rows, cols = np.nonzero(S)
        nnz = int(len(rows))
        ia = glp.intArray(nnz + 1)
        ja = glp.intArray(nnz + 1)
        ar = glp.doubleArray(nnz + 1)
        for k in range(nnz):
            ia[k + 1] = int(rows[k]) + 1
            ja[k + 1] = int(cols[k]) + 1
            ar[k + 1] = float(S[rows[k], cols[k]])
        glp.glp_load_matrix(lp, nnz, ia, ja, ar)

        # Karr 2012 GLPK option `scale=1`: enable automatic problem scaling
        # before the simplex. On the cond=6.7e+12 metabolism LP this changes
        # pivot selection and brings the OC basis closer to Karr's.
        glp.glp_scale_prob(lp, glp.GLP_SF_AUTO)

        # Construct an advanced initial basis (triangular). Required when
        # presolve is OFF; harmless otherwise.
        glp.glp_adv_basis(lp, 0)

        parm = glp.glp_smcp()
        glp.glp_init_smcp(parm)
        parm.msg_lev = glp.GLP_MSG_OFF
        # Day-40 finding: with presolve OFF, GLPK reaches a basis that is
        # ~7x closer to Karr's recorded flux at the metabolism allocated
        # state (writeback L1 81K -> 11K at sample (0,1)). Presolve was
        # aggressively zeroing variables that Karr's GLPK 4.x kept basic.
        # See scripts/probe_glpk_presolve_variants.py.
        parm.presolve = glp.GLP_OFF
        parm.meth = glp.GLP_PRIMAL
        # Karr's `tolbnd = 10e-7 = 1e-6` — looser than GLPK's default 1e-7.
        parm.tol_bnd = 1e-6

        status = glp.glp_simplex(lp, parm)
        if status != 0:
            raise RuntimeError(f"GLPK simplex returned status {status}")
        sol_status = glp.glp_get_status(lp)
        if sol_status != glp.GLP_OPT:
            raise RuntimeError(f"GLPK did not reach optimum (status {sol_status})")

        v = np.array(
            [glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64
        )
        # Karr post-solve clip (Metabolism.m:1296):
        #   fbaReactionFluxs = max(min(fbaReactionFluxs, upFluxBounds), loFluxBounds)
        # The LP solver returns values up to tol_bnd outside the strict bounds;
        # clipping enforces bound feasibility for downstream writeback math.
        v = np.clip(v, lb, ub)
        obj_val = float(glp.glp_get_obj_val(lp))
        return v, obj_val, "ok"
    finally:
        glp.glp_delete_prob(lp)


def _solve_fba_glpk_pfba(
    model: "KarrMetabolismModel",
    *,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    sense: str,
    biomass_col: int,
) -> tuple[np.ndarray, float, str]:
    """Parsimonious FBA (pFBA) via two-stage GLPK solve.

    Stage 1: solve standard FBA (max c'v) -> read v_biomass*.
    Stage 2: fix biomass at v_biomass*, add auxiliary variables w_i = |v_i|,
             minimize Sum(w_i) over the non-biomass reactions.

    This is the COBRA-standard fix for LP degeneracy: it picks the unique
    flux distribution that achieves the optimal biomass with minimum total
    flux mass. Removes the LIPASE-family +/-1e6 paired-swap degeneracy that
    plagues the raw FBA on the metabolism allocated state.

    Variables (2R total):
      - v_0...v_{R-1}: original reaction fluxes (signed, with original bounds)
      - w_0...w_{R-1}: auxiliary "abs of v" variables (>= 0)
    Constraints (M + 1 + 2R total):
      - S v = b               (M equality rows, original stoichiometry)
      - v[biomass_col] = v_b* (1 equality row, biomass fixed)
      - w_i - v_i >= 0        (R rows)
      - w_i + v_i >= 0        (R rows)
    Objective: min Sum_{i != biomass_col} w_i
    """
    import swiglpk as glp  # noqa: PLC0415

    R = c.shape[0]
    M = model.S.shape[0]
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)

    # Stage 1: get biomass optimum
    v_stage1, obj1, _ = _solve_fba_glpk(model, c=c, lb=lb, ub=ub, sense=sense)
    biomass_flux = float(v_stage1[biomass_col])

    # Stage 2: parsimonious LP
    #
    # Architecture note: rather than adding an extra "biomass = v_biomass*"
    # constraint row, we fix the biomass COLUMN's bounds directly. This
    # avoids GLPK scaling problems on tiny biomass values (~1e-5) mixed
    # with mass-balance equality rows (~1e+6 magnitudes), which previously
    # caused GLPK to silently return v_biomass ~ 0 with no infeasibility
    # warning.
    lp = glp.glp_create_prob()
    try:
        glp.glp_set_obj_dir(lp, glp.GLP_MIN)

        # Rows: M (Sv=b) + R (w >= v) + R (w >= -v)
        n_rows = M + 2 * R
        glp.glp_add_rows(lp, n_rows)
        for i in range(M):
            glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))
        # w_i - v_i >= 0
        for i in range(R):
            glp.glp_set_row_bnds(lp, M + 1 + i, glp.GLP_LO, 0.0, 0.0)
        # w_i + v_i >= 0
        for i in range(R):
            glp.glp_set_row_bnds(lp, M + R + 1 + i, glp.GLP_LO, 0.0, 0.0)

        # Cols: R for v + R for w
        glp.glp_add_cols(lp, 2 * R)
        for j in range(R):
            lj, uj = float(lb[j]), float(ub[j])
            if j == biomass_col:
                # Fix biomass at stage-1 optimum with a tiny relative tolerance
                # window. GLP_FX is brittle when the fixed value is at the
                # feasibility tolerance threshold; GLP_DB with bio_tol works
                # robustly across magnitudes.
                bio_tol = max(1e-9, 1e-6 * abs(biomass_flux))
                lo = max(lj, biomass_flux - bio_tol)
                hi = min(uj, biomass_flux + bio_tol)
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lo, hi)
            elif lj == uj:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lj, uj)
            else:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lj, uj)
            glp.glp_set_obj_coef(lp, j + 1, 0.0)  # no direct cost on v
        # w columns: lower bound 0, no upper (will get |v| which is <= big)
        big_w = max(abs(float(lb[j])) for j in range(R))
        big_w = max(big_w, max(abs(float(ub[j])) for j in range(R)))
        big_w = max(big_w, 1.0) * 2.0
        for j in range(R):
            glp.glp_set_col_bnds(lp, R + j + 1, glp.GLP_DB, 0.0, big_w)
            # Minimize sum of w_i for non-biomass columns
            glp.glp_set_obj_coef(lp, R + j + 1, 0.0 if j == biomass_col else 1.0)

        # Build constraint matrix triplets
        S = np.asarray(model.S, dtype=np.float64)
        S_rows, S_cols = np.nonzero(S)
        n_S = int(len(S_rows))
        # Plus: w-v rows (2R entries), w+v rows (2R entries)
        nnz_total = n_S + 4 * R
        ia = glp.intArray(nnz_total + 1)
        ja = glp.intArray(nnz_total + 1)
        ar = glp.doubleArray(nnz_total + 1)
        k = 0
        # S matrix entries on the v columns
        for idx in range(n_S):
            k += 1
            ia[k] = int(S_rows[idx]) + 1
            ja[k] = int(S_cols[idx]) + 1
            ar[k] = float(S[S_rows[idx], S_cols[idx]])
        # w_i - v_i >= 0  rows  M+1 .. M+R
        for i in range(R):
            k += 1
            ia[k] = M + 1 + i
            ja[k] = R + i + 1   # w_i column
            ar[k] = 1.0
            k += 1
            ia[k] = M + 1 + i
            ja[k] = i + 1       # v_i column
            ar[k] = -1.0
        # w_i + v_i >= 0  rows  M+R+1 .. M+2R
        for i in range(R):
            k += 1
            ia[k] = M + R + 1 + i
            ja[k] = R + i + 1
            ar[k] = 1.0
            k += 1
            ia[k] = M + R + 1 + i
            ja[k] = i + 1
            ar[k] = 1.0
        glp.glp_load_matrix(lp, k, ia, ja, ar)

        parm = glp.glp_smcp()
        glp.glp_init_smcp(parm)
        parm.msg_lev = glp.GLP_MSG_OFF
        parm.presolve = glp.GLP_ON
        parm.meth = glp.GLP_PRIMAL

        status = glp.glp_simplex(lp, parm)
        if status != 0:
            raise RuntimeError(f"GLPK pFBA stage-2 simplex returned status {status}")
        sol_status = glp.glp_get_status(lp)
        if sol_status != glp.GLP_OPT:
            raise RuntimeError(f"GLPK pFBA stage-2 did not reach optimum (status {sol_status})")

        v = np.array(
            [glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64
        )
        # obj_val is sum of |v| over non-biomass — diagnostic only.
        sum_abs_flux = float(glp.glp_get_obj_val(lp))
        # Return the original objective value (recomputed) so caller's status
        # dict reports the biological optimum, not the parsimony sum.
        original_obj = float(np.dot(c, v))
        return v, original_obj, f"pfba_ok sum_abs={sum_abs_flux:.4e}"
    finally:
        glp.glp_delete_prob(lp)


def solve_fba(
    model: KarrMetabolismModel,
    objective_col: int | None = None,
    sense: str = "max",
    big: float = DEFAULT_BIG,
    use_full_objective: bool = True,
    lb_override: np.ndarray | None = None,
    ub_override: np.ndarray | None = None,
    solver: str = "highs",
    pfba: bool = False,
) -> tuple[np.ndarray, dict]:
    """Solve Karr's fitted FBA exactly.

    Default is `use_full_objective=True` (Karr's published 36-nonzero
    objective: +1000 on biomass + 35 small parsimony penalties).
    Set `objective_col` to override and maximise / minimise a single
    column instead.  `big` substitutes for +/-inf in bounds.

    ``lb_override`` / ``ub_override`` (each shape ``(R,)``) replace
    ``model.lb`` / ``model.ub`` for this solve only; the model itself
    is never mutated.  Used by the dynamic-bounds chassis loop.

    ``solver`` selects the LP backend:
      * ``"highs"`` (default) — scipy.optimize.linprog method='highs'.
      * ``"glpk"``  — GLPK 5.0 via swiglpk (Karr 2012's solver family).
        Required for L2.2 Metabolism fidelity (the FBA is degenerate;
        HiGHS and GLPK pick different vertices). swiglpk is an optional
        dependency; install with ``pip install swiglpk``.

    ``pfba`` (default False) enables parsimonious FBA: a two-stage solve
    that first maximizes the biological objective, then minimizes total
    flux mass (Sum|v_i|) subject to biomass-fixed-at-optimum. Resolves the
    LIPASE-family LP degeneracy that produces +/-1e6 paired-swap noise on
    the metabolism allocated state. COBRA-standard fix; required for full
    L2.2 substrate W1 convergence. Currently implemented for solver="glpk"
    only.
    """
    R = model.n_reactions
    src_lb = model.lb if lb_override is None else lb_override
    src_ub = model.ub if ub_override is None else ub_override
    if src_lb.shape != (R,) or src_ub.shape != (R,):
        raise ValueError(
            f"bound override shape mismatch: lb {src_lb.shape}, ub {src_ub.shape}, R={R}"
        )
    lb = np.where(np.isfinite(src_lb), src_lb, -big).copy()
    ub = np.where(np.isfinite(src_ub), src_ub, big).copy()
    lb = np.clip(lb, -big, big)
    ub = np.clip(ub, -big, big)

    sign = -1.0 if sense == "max" else 1.0
    if objective_col is None and use_full_objective:
        c = sign * model.obj.copy()
    else:
        c = np.zeros(R)
        col = model.biomass_col if objective_col is None else int(objective_col)
        c[col] = sign

    if pfba and solver != "glpk":
        raise ValueError("pfba=True is currently only supported with solver='glpk'")

    if solver == "glpk":
        # Build the NATURAL-sense objective vector for GLPK (no scipy
        # min-flip): for "max" sense GLPK gets +obj on the biomass row.
        if objective_col is None and use_full_objective:
            c_natural = model.obj.copy().astype(np.float64)
        else:
            c_natural = np.zeros(R, dtype=np.float64)
            col = model.biomass_col if objective_col is None else int(objective_col)
            c_natural[col] = 1.0
        if pfba:
            v, obj_val, status = _solve_fba_glpk_pfba(
                model,
                c=c_natural,
                lb=lb,
                ub=ub,
                sense=sense,
                biomass_col=model.biomass_col,
            )
            solver_tag = "glpk+pfba"
        else:
            v, obj_val, status = _solve_fba_glpk(
                model, c=c_natural, lb=lb, ub=ub, sense=sense,
            )
            solver_tag = "glpk"
        biomass_flux = float(v[model.biomass_col])
        return v, {
            "status": status,
            "message": f"{solver_tag} ok",
            "objective_value": obj_val,
            "biomass_flux_per_s": biomass_flux,
            "biomass_flux_per_h": biomass_flux * 3600.0,
            "big": big,
            "use_full_objective": use_full_objective,
            "n_nonzero": int((np.abs(v) > 1e-9).sum()),
            "solver": solver_tag,
        }

    if solver != "highs":
        raise ValueError(f"unknown solver={solver!r}; expected 'highs' or 'glpk'")

    bounds = list(zip(lb.tolist(), ub.tolist(), strict=False))

    res = linprog(
        c=c,
        A_eq=model.S,
        b_eq=model.RHS,
        bounds=bounds,
        method="highs",
        options={"presolve": True},
    )
    if not res.success:
        raise RuntimeError(f"Karr FBA infeasible: {res.message}")

    v = np.asarray(res.x, dtype=float)
    biomass_flux = float(v[model.biomass_col])
    return v, {
        "status": "ok",
        "message": res.message,
        "objective_value": -float(res.fun) if sense == "max" else float(res.fun),
        "biomass_flux_per_s": biomass_flux,
        "biomass_flux_per_h": biomass_flux * 3600.0,
        "big": big,
        "use_full_objective": use_full_objective,
        "n_nonzero": int((np.abs(v) > 1e-9).sum()),
        "solver": "highs",
    }


def per_reaction_comparison(
    model: KarrMetabolismModel,
    v: np.ndarray,
    nonzero_only: bool = True,
    tol: float = 1e-9,
) -> list[dict]:
    """Compare predicted FBA fluxes (504-space) against Karr's stored
    runtime fluxs (645-space), for every metabolicConversion FBA col
    that has a WCM ID."""
    out = []
    for col, wcm in enumerate(model.fba_col_rxn_wcm):
        if wcm is None:
            continue
        pred = float(v[col])
        idx_645 = model.rxn_wcm_ids_645.index(wcm)
        karr = float(model.fluxs_stored[idx_645])
        if nonzero_only and abs(pred) < tol and abs(karr) < tol:
            continue
        out.append(
            {
                "fba_col": col,
                "wcm_id": wcm,
                "predicted": pred,
                "karr_stored": karr,
            }
        )
    return out
