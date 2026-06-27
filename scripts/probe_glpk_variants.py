"""Probe: try GLPK solver-option variants + locate the residual difference.

Variants to try:
  A. presolve=on,  meth=primal  (current baseline)
  B. presolve=off, meth=primal
  C. presolve=on,  meth=dual
  D. presolve=off, meth=dual
  E. presolve=on,  meth=primal, pricing=STD (textbook)
  F. presolve=on,  meth=primal, ratio_test=STD

Also: print WHICH 12 reactions still differ by >1e4 from Karr to see if it's
the LIPASE family (degenerate) or something else.
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


def _build_lp(model, lb, ub, big, sense="max"):
    R = model.n_reactions
    M = model.S.shape[0]

    lb = np.where(np.isfinite(lb), lb, -big).copy()
    ub = np.where(np.isfinite(ub), ub, big).copy()
    lb = np.clip(lb, -big, big)
    ub = np.clip(ub, -big, big)

    c = model.obj.copy().astype(np.float64)
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)

    lp = glp.glp_create_prob()
    glp.glp_set_prob_name(lp, "karr_fba")
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
    nnz = len(rows)
    ia = glp.intArray(nnz + 1)
    ja = glp.intArray(nnz + 1)
    ar = glp.doubleArray(nnz + 1)
    for k in range(nnz):
        ia[k + 1] = int(rows[k]) + 1
        ja[k + 1] = int(cols[k]) + 1
        ar[k + 1] = float(S[rows[k], cols[k]])
    glp.glp_load_matrix(lp, nnz, ia, ja, ar)
    return lp, R


def _solve_with(lp, R, presolve, meth, pricing=None, r_test=None):
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_ERR
    parm.presolve = glp.GLP_ON if presolve else glp.GLP_OFF
    parm.meth = meth
    if pricing is not None:
        parm.pricing = pricing
    if r_test is not None:
        parm.r_test = r_test

    status = glp.glp_simplex(lp, parm)
    if status != 0:
        return None, f"simplex={status}"
    sol_status = glp.glp_get_status(lp)
    if sol_status != glp.GLP_OPT:
        return None, f"sol={sol_status}"
    v = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64)
    return v, "ok"


def main():
    with h5py.File(GT_PATH, "r") as h:
        flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
        bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
    if bounds_karr.shape == (2, 504):
        bounds_karr = bounds_karr.T

    model = km.load_default()
    lb, ub = bounds_karr[:, 0], bounds_karr[:, 1]

    variants = [
        ("A presolve=on,  primal",   True,  glp.GLP_PRIMAL, None, None),
        ("B presolve=off, primal",   False, glp.GLP_PRIMAL, None, None),
        ("C presolve=on,  dual",     True,  glp.GLP_DUAL,   None, None),
        ("D presolve=off, dual",     False, glp.GLP_DUAL,   None, None),
        ("E primal+STD-pricing",     True,  glp.GLP_PRIMAL, glp.GLP_PT_STD, None),
        ("F primal+STD-ratio-test",  True,  glp.GLP_PRIMAL, None, glp.GLP_RT_STD),
        ("G primal+STD pricing+rt",  True,  glp.GLP_PRIMAL, glp.GLP_PT_STD, glp.GLP_RT_STD),
        ("H presolve=off, dual_p",   False, glp.GLP_DUALP,  None, None),
    ]

    print(f"Karr reference: sum_abs={np.abs(flux_karr).sum():.4e}, nnz={(flux_karr != 0).sum()}/504")
    print()
    print(f"{'variant':28s}  {'L1 vs Karr':>14s}  {'max_cell':>12s}  {'>100':>5s}  {'>1e4':>5s}")
    print("-" * 80)

    best_name = None
    best_L1 = float("inf")
    best_v = None

    for name, presolve, meth, pricing, rtest in variants:
        lp, R = _build_lp(model, lb, ub, big=1e6)
        v, status = _solve_with(lp, R, presolve, meth, pricing, rtest)
        glp.glp_delete_prob(lp)
        if v is None:
            print(f"{name:28s}  FAILED: {status}")
            continue
        d = np.abs(v - flux_karr)
        L1 = float(d.sum())
        max_d = float(d.max())
        gt100 = int((d > 100).sum())
        gt1e4 = int((d > 1e4).sum())
        print(f"{name:28s}  {L1:14.4e}  {max_d:12.4e}  {gt100:5d}  {gt1e4:5d}")
        if L1 < best_L1:
            best_L1 = L1
            best_name = name
            best_v = v

    print()
    print(f"Best variant: {best_name}  L1={best_L1:.4e}")

    # Where are the residual differences for the best variant?
    if best_v is not None:
        d = best_v - flux_karr
        big_idx = np.argsort(-np.abs(d))[:20]
        print()
        print("Top-20 worst reactions for the best variant:")
        print(f"{'rxn_idx':>8s}  {'|diff|':>14s}  {'GLPK':>14s}  {'Karr':>14s}")
        print("-" * 60)
        for idx in big_idx:
            print(f"{idx:8d}  {abs(d[idx]):14.4e}  {best_v[idx]:14.4e}  {flux_karr[idx]:14.4e}")

        # Are the worst diffs paired (forward+reverse pattern)?
        big_d_idx = np.where(np.abs(d) > 1e3)[0]
        print()
        print(f"Reactions with |diff|>1e3: {len(big_d_idx)} of 504")
        # Look for paired ±1e6 LIPASE-family pattern
        for i, idx in enumerate(big_d_idx[:30]):
            if i % 2 == 0:
                print(f"  idx {idx:4d}  diff={d[idx]:+.4e}")


if __name__ == "__main__":
    main()
