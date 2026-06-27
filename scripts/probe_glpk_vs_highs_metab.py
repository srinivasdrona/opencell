"""Probe: does swiglpk (GLPK 5.0) match Karr's recorded flux better than HiGHS?

At the allocated pre-state from per_process_traces_v2_s000/Metabolism_100ticks.mat
tick 1, we have:
  - Karr's recorded flux (MATLAB GLPK MEX 4.x output)
  - OC HiGHS flux (currently ~99.97% of W1 gap)

If GLPK 5.0 via swiglpk matches Karr to within FP noise (<100 cells differ),
we route opencell.m1.karr_metabolism.solve_fba through GLPK for Metabolism path.

Run:
  bin/oc-py scripts/probe_glpk_vs_highs_metab.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

import swiglpk as glp

GT_PATH = (
    REPO
    / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"
)


def solve_fba_glpk(
    model: km.KarrMetabolismModel,
    lb_override: np.ndarray,
    ub_override: np.ndarray,
    big: float = 1e6,
    use_full_objective: bool = True,
    sense: str = "max",
) -> tuple[np.ndarray, dict]:
    """Solve Karr FBA using swiglpk (GLPK 5.0), Karr's actual solver family.

    Mirrors solve_fba's bound handling: clip infs to ±big, build same LP.
    Uses primal simplex (Karr's MATLAB GLPK MEX default).
    """
    R = model.n_reactions
    M = model.S.shape[0]

    lb = np.where(np.isfinite(lb_override), lb_override, -big).copy()
    ub = np.where(np.isfinite(ub_override), ub_override, big).copy()
    lb = np.clip(lb, -big, big)
    ub = np.clip(ub, -big, big)

    if use_full_objective:
        c = model.obj.copy().astype(np.float64)
    else:
        c = np.zeros(R, dtype=np.float64)
        c[model.biomass_col] = 1.0

    # Build GLPK LP
    lp = glp.glp_create_prob()
    glp.glp_set_prob_name(lp, "karr_fba")
    # Direction: maximize biomass when sense='max' (c is positive on biomass already)
    glp.glp_set_obj_dir(lp, glp.GLP_MAX if sense == "max" else glp.GLP_MIN)

    # Rows (constraints): S*v = RHS, M equality rows
    glp.glp_add_rows(lp, M)
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)
    for i in range(M):
        glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))

    # Cols (variables): R reactions with bounds and objective coefficients
    glp.glp_add_cols(lp, R)
    for j in range(R):
        lj, uj = float(lb[j]), float(ub[j])
        if lj == uj:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lj, uj)
        else:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lj, uj)
        glp.glp_set_obj_coef(lp, j + 1, float(c[j]))

    # Load constraint matrix S (sparse triplet)
    S = np.asarray(model.S, dtype=np.float64)
    rows, cols = np.nonzero(S)
    nnz = len(rows)
    ia = glp.intArray(nnz + 1)
    ja = glp.intArray(nnz + 1)
    ar = glp.doubleArray(nnz + 1)
    for k in range(nnz):
        ia[k + 1] = int(rows[k]) + 1
        ja[k + 1] = int(cols[k]) + 1
        ar[k + 1] = float(S[rows[k], cols[k]])
    glp.glp_load_matrix(lp, nnz, ia, ja, ar)

    # Solve with primal simplex (Karr's MATLAB GLPK MEX default)
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_ERR
    parm.presolve = glp.GLP_ON
    parm.meth = glp.GLP_PRIMAL

    status = glp.glp_simplex(lp, parm)
    if status != 0:
        raise RuntimeError(f"GLPK simplex returned status {status}")

    sol_status = glp.glp_get_status(lp)
    if sol_status != glp.GLP_OPT:
        raise RuntimeError(f"GLPK did not reach optimum, status {sol_status}")

    v = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64)
    obj_val = float(glp.glp_get_obj_val(lp))

    glp.glp_delete_prob(lp)

    biomass_flux = float(v[model.biomass_col])
    return v, {
        "status": "ok",
        "objective_value": obj_val,
        "biomass_flux_per_s": biomass_flux,
        "n_nonzero": int((np.abs(v) > 1e-9).sum()),
    }


def main():
    # Load ground truth at allocated state
    with h5py.File(GT_PATH, "r") as h:
        flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
        growth_karr = float(np.asarray(h["growth"][()]).reshape(-1)[0])
        bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
        pre_sub_alloc = np.asarray(h["pre_sub"][()], dtype=np.float64)
        delta_karr = np.asarray(h["delta"][()], dtype=np.float64)

    if bounds_karr.shape == (2, 504):
        bounds_karr = bounds_karr.T
    if pre_sub_alloc.shape == (3, 585):
        pre_sub_alloc = pre_sub_alloc.T
    if delta_karr.shape == (3, 585):
        delta_karr = delta_karr.T

    print("=" * 70)
    print("Ground truth at allocated state (s=000, tick=1)")
    print("=" * 70)
    print(f"  Karr growth_per_s = {growth_karr:.6e}")
    print(f"  Karr flux sum_abs = {np.abs(flux_karr).sum():.4e}")
    print(f"  Karr flux nonzero = {(flux_karr != 0).sum()}/504")
    print(f"  Karr delta sum_abs= {np.abs(delta_karr).sum():.0f}")

    model = km.load_default()
    lb = bounds_karr[:, 0]
    ub = bounds_karr[:, 1]

    # --- Solve via HiGHS (current OC stack) ---
    v_highs, info_highs = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=1e6,
        lb_override=lb,
        ub_override=ub,
    )

    # --- Solve via swiglpk GLPK 5.0 ---
    v_glpk, info_glpk = solve_fba_glpk(
        model,
        lb_override=lb,
        ub_override=ub,
        big=1e6,
        use_full_objective=True,
        sense="max",
    )

    print()
    print("=" * 70)
    print("Solver outputs (same model, same bounds, same allocated state)")
    print("=" * 70)
    print(
        f"  HiGHS  growth={info_highs['biomass_flux_per_s']:.6e}  "
        f"sum_abs={np.abs(v_highs).sum():.4e}  "
        f"nnz={int((np.abs(v_highs) > 1e-9).sum())}/504"
    )
    print(
        f"  GLPK   growth={info_glpk['biomass_flux_per_s']:.6e}  "
        f"sum_abs={np.abs(v_glpk).sum():.4e}  "
        f"nnz={int((np.abs(v_glpk) > 1e-9).sum())}/504"
    )
    print(
        f"  Karr   growth={growth_karr:.6e}  "
        f"sum_abs={np.abs(flux_karr).sum():.4e}  "
        f"nnz={int((flux_karr != 0).sum())}/504"
    )

    print()
    print("=" * 70)
    print("Flux-vector L1 distances")
    print("=" * 70)
    for name, v in [("HiGHS", v_highs), ("GLPK", v_glpk)]:
        d = v - flux_karr
        L1 = float(np.abs(d).sum())
        gt100 = int((np.abs(d) > 100).sum())
        gt1e4 = int((np.abs(d) > 1e4).sum())
        max_d = float(np.abs(d).max())
        print(
            f"  |{name} - Karr|: L1={L1:.4e}  max_cell={max_d:.4e}  "
            f"cells>100={gt100}  cells>1e4={gt1e4}"
        )

    # --- Writeback comparison ---
    print()
    print("=" * 70)
    print("Writeback L1 (vs Karr recorded delta)")
    print("=" * 70)

    fbf = KarrWritebackFixture.from_mat(
        str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat")
    )

    A_highs = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub_alloc,
        v_504=v_highs,
        growth_per_s=info_highs["biomass_flux_per_s"],
        fixture=fbf,
        rng=_Mcg16807(seed=12345),
        step_size_sec=1.0,
    )
    A_glpk = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub_alloc,
        v_504=v_glpk,
        growth_per_s=info_glpk["biomass_flux_per_s"],
        fixture=fbf,
        rng=_Mcg16807(seed=12345),
        step_size_sec=1.0,
    )
    B_karr = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub_alloc,
        v_504=flux_karr,
        growth_per_s=growth_karr,
        fixture=fbf,
        rng=_Mcg16807(seed=12345),
        step_size_sec=1.0,
    )
    C_recorded = delta_karr.astype(np.int64)

    for name, A in [("HiGHS-WB", A_highs), ("GLPK-WB", A_glpk), ("Karr-flux WB", B_karr)]:
        A_flat = A.sum(axis=1).astype(np.float64)
        C_flat = C_recorded.sum(axis=1).astype(np.float64)
        d_AC = float(np.abs(A_flat - C_flat).sum())
        print(f"  |{name} - Karr recorded|: L1={d_AC:.0f}")

    # The killer comparison
    print()
    print("=" * 70)
    print("GLPK fidelity verdict")
    print("=" * 70)
    d_glpk_karr = float(np.abs(v_glpk - flux_karr).sum())
    d_highs_karr = float(np.abs(v_highs - flux_karr).sum())
    if d_glpk_karr < 100:
        print(f"  ✅ GLPK matches Karr to within FP noise (L1={d_glpk_karr:.4e}).")
        print(f"     HiGHS was off by L1={d_highs_karr:.4e}.")
        print(f"     ACTION: wire swiglpk into solve_fba via solver='glpk' flag.")
    elif d_glpk_karr < d_highs_karr * 0.1:
        print(f"  ✅ GLPK much closer than HiGHS ({d_glpk_karr:.4e} vs {d_highs_karr:.4e}).")
        print(f"     ACTION: wire it in; remaining gap may be GLPK 5.0 vs 4.x basis tweaks.")
    elif d_glpk_karr < d_highs_karr:
        print(f"  ⚠️  GLPK better than HiGHS but not by much "
              f"({d_glpk_karr:.4e} vs {d_highs_karr:.4e}).")
        print(f"     LP is genuinely degenerate; consider pFBA.")
    else:
        print(f"  ❌ GLPK NOT better ({d_glpk_karr:.4e} vs HiGHS {d_highs_karr:.4e}).")
        print(f"     Karr's recorded flux may itself be from a different LP setup.")


if __name__ == "__main__":
    main()
