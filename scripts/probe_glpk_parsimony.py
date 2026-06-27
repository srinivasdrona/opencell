"""Test if tiny L2 regularization breaks the LIPASE-family LP degeneracy.

Objective becomes: max c'v  s.t. (S v = b, lb <= v <= ub)
                  -> max c'v - ε * sum(v_i^2)  (quadratic — needs QP)
OR simpler L1-style with auxiliary vars (pFBA-light):
                  -> max c'v  with c containing tiny -ε on every reaction
                     so unused +/- pairs don't get arbitrary ±1e6 mass.

We test:
  G1: GLPK baseline (no regularization)
  G2: GLPK with -1e-9 on every non-objective reaction (suppresses spurious flux)
  G3: GLPK with -1e-6
  G4: GLPK with -1e-4
  G5: GLPK with -1e-9 ONLY on the 12 known LIPASE-family pairs
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km

import swiglpk as glp

GT_PATH = (
    REPO
    / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"
)


def _solve(model, lb, ub, obj_vec, big=1e6):
    R = model.n_reactions
    M = model.S.shape[0]
    lb = np.clip(np.where(np.isfinite(lb), lb, -big), -big, big)
    ub = np.clip(np.where(np.isfinite(ub), ub, big), -big, big)
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)

    lp = glp.glp_create_prob()
    glp.glp_set_obj_dir(lp, glp.GLP_MAX)
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
        glp.glp_set_obj_coef(lp, j + 1, float(obj_vec[j]))
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

    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_ON
    parm.meth = glp.GLP_PRIMAL

    glp.glp_simplex(lp, parm)
    v = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64)
    growth = float(v[model.biomass_col])
    glp.glp_delete_prob(lp)
    return v, growth


def main():
    with h5py.File(GT_PATH, "r") as h:
        flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
        bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
        growth_karr = float(np.asarray(h["growth"][()]).reshape(-1)[0])
    if bounds_karr.shape == (2, 504):
        bounds_karr = bounds_karr.T

    model = km.load_default()
    lb, ub = bounds_karr[:, 0], bounds_karr[:, 1]

    obj_base = model.obj.copy().astype(np.float64)
    biomass = model.biomass_col

    print(f"Karr: growth={growth_karr:.6e}  flux sum_abs={np.abs(flux_karr).sum():.4e}  nnz={(flux_karr != 0).sum()}/504")
    print()
    print(f"{'variant':40s}  {'growth':>12s}  {'L1 vs Karr':>14s}  {'>1e4':>5s}  {'>1e5':>5s}  {'>5e5':>5s}")
    print("-" * 100)

    # Identify spurious-flux candidates from previous probe: reactions with
    # near-zero Karr flux but where GLPK puts ±1e6
    spurious_idx = [6, 7, 159, 194, 198, 199, 200, 161]

    eps_values = [0.0, 1e-12, 1e-9, 1e-6, 1e-4, 1e-3]
    for eps in eps_values:
        # Subtract eps from every reaction (penalize all non-zero flux),
        # but DON'T touch the biomass column — preserve growth optimum
        obj = obj_base.copy()
        obj -= eps  # all entries reduced
        obj[biomass] = obj_base[biomass]  # restore biomass coef
        v, growth = _solve(model, lb, ub, obj)
        d = v - flux_karr
        L1 = float(np.abs(d).sum())
        gt1e4 = int((np.abs(d) > 1e4).sum())
        gt1e5 = int((np.abs(d) > 1e5).sum())
        gt5e5 = int((np.abs(d) > 5e5).sum())
        growth_match = "MATCH" if abs(growth - growth_karr) < 1e-10 else f"DIFF {growth-growth_karr:+.2e}"
        eps_str = f"{eps:.0e}"
        print(f"  uniform parsim eps={eps_str:8s}            {growth:12.6e}  {L1:14.4e}  {gt1e4:5d}  {gt1e5:5d}  {gt5e5:5d}  [{growth_match}]")

    # Targeted: only penalize the 8 known spurious LIPASE indices
    for eps in [1e-9, 1e-6, 1e-3]:
        obj = obj_base.copy()
        for k in spurious_idx:
            obj[k] -= eps
        v, growth = _solve(model, lb, ub, obj)
        d = v - flux_karr
        L1 = float(np.abs(d).sum())
        gt1e4 = int((np.abs(d) > 1e4).sum())
        gt1e5 = int((np.abs(d) > 1e5).sum())
        gt5e5 = int((np.abs(d) > 5e5).sum())
        growth_match = "MATCH" if abs(growth - growth_karr) < 1e-10 else f"DIFF {growth-growth_karr:+.2e}"
        eps_str = f"{eps:.0e}"
        print(f"  targeted-8 eps={eps_str:8s}                 {growth:12.6e}  {L1:14.4e}  {gt1e4:5d}  {gt1e5:5d}  {gt5e5:5d}  [{growth_match}]")


if __name__ == "__main__":
    main()
