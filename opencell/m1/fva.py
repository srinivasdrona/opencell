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


def _configure_simplex_params(glp: Any) -> Any:
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_OFF
    parm.meth = glp.GLP_PRIMAL
    parm.tol_bnd = 1e-6
    parm.pricing = glp.GLP_PT_STD
    return parm


def _solve_checked(glp: Any, lp: Any, parm: Any, *, label: str) -> None:
    simplex_exit = int(glp.glp_simplex(lp, parm))
    sol_status = int(glp.glp_get_status(lp))
    if simplex_exit != 0 or sol_status != glp.GLP_OPT:
        raise RuntimeError(
            f"{label} failed: simplex_exit={simplex_exit}, sol_status={sol_status}, "
            f"expected simplex_exit=0 and GLP_OPT({glp.GLP_OPT})"
        )


def fva_range(
    S: np.ndarray,
    rhs: np.ndarray,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    biomass_value_star: float,
    epsilon_obj: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Run reaction-wise FVA on the biomass-optimal face."""
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
        eps = float(max(0.0, epsilon_obj))
        if eps == 0.0:
            glp.glp_set_row_bnds(
                lp,
                biomass_row,
                glp.GLP_FX,
                float(biomass_value_star),
                float(biomass_value_star),
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

        v_min = np.empty(n_rxn, dtype=np.float64)
        v_max = np.empty(n_rxn, dtype=np.float64)
        for j in range(n_rxn):
            glp.glp_set_obj_coef(lp, j + 1, 1.0)

            glp.glp_set_obj_dir(lp, glp.GLP_MAX)
            _solve_checked(glp, lp, parm, label=f"FVA max j={j}")
            v_max[j] = float(glp.glp_get_col_prim(lp, j + 1))

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
