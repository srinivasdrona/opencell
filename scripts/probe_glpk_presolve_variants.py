"""Test if disabling presolve preserves more of Karr's structure."""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture, apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807
import swiglpk as glp

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"

with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
    pre_sub = np.asarray(h["pre_sub"][()], dtype=np.float64)
    delta_karr = np.asarray(h["delta"][()], dtype=np.float64).astype(np.int64)
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T
if pre_sub.shape == (3, 585):
    pre_sub = pre_sub.T
if delta_karr.shape == (3, 585):
    delta_karr = delta_karr.T

model = km.load_default()
lb, ub = bounds_karr[:, 0], bounds_karr[:, 1]


def solve_variant(presolve, scale, tol_bnd, label):
    R = model.n_reactions
    M = model.S.shape[0]
    big = 1e6
    lb_c = np.clip(np.where(np.isfinite(lb), lb, -big), -big, big)
    ub_c = np.clip(np.where(np.isfinite(ub), ub, big), -big, big)

    lp = glp.glp_create_prob()
    glp.glp_set_obj_dir(lp, glp.GLP_MAX)
    glp.glp_add_rows(lp, M)
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)
    for i in range(M):
        glp.glp_set_row_bnds(lp, i+1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))
    glp.glp_add_cols(lp, R)
    for j in range(R):
        lj, uj = float(lb_c[j]), float(ub_c[j])
        if lj == uj:
            glp.glp_set_col_bnds(lp, j+1, glp.GLP_FX, lj, uj)
        else:
            glp.glp_set_col_bnds(lp, j+1, glp.GLP_DB, lj, uj)
        glp.glp_set_obj_coef(lp, j+1, float(model.obj[j]))
    S = np.asarray(model.S, dtype=np.float64)
    rows, cols = np.nonzero(S)
    nnz = len(rows)
    ia = glp.intArray(nnz+1); ja = glp.intArray(nnz+1); ar = glp.doubleArray(nnz+1)
    for k in range(nnz):
        ia[k+1] = int(rows[k])+1; ja[k+1] = int(cols[k])+1; ar[k+1] = float(S[rows[k], cols[k]])
    glp.glp_load_matrix(lp, nnz, ia, ja, ar)
    if scale:
        glp.glp_scale_prob(lp, glp.GLP_SF_AUTO)
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_ON if presolve else glp.GLP_OFF
    parm.meth = glp.GLP_PRIMAL
    parm.tol_bnd = tol_bnd
    # When presolve is OFF and no basis is provided, need to construct one
    if not presolve:
        glp.glp_adv_basis(lp, 0)  # Advanced basis construction
    glp.glp_simplex(lp, parm)
    v = np.array([glp.glp_get_col_prim(lp, j+1) for j in range(R)], dtype=np.float64)
    v = np.clip(v, lb_c, ub_c)
    growth = float(v[model.biomass_col])
    d = v - flux_karr
    L1 = float(np.abs(d).sum())
    nnz_oc = int((np.abs(v) > 1e-9).sum())
    return v, growth, L1, nnz_oc


fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))
C_recorded = delta_karr.sum(axis=1).astype(np.float64)


def writeback_L1(v, growth):
    A = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub, v_504=v, growth_per_s=growth,
        fixture=fbf, rng=_Mcg16807(seed=12345), step_size_sec=1.0,
    )
    A_flat = A.sum(axis=1).astype(np.float64)
    return float(np.abs(A_flat - C_recorded).sum())


print(f"Karr ref: growth=2.119269e-05, nnz=327/504, sum_abs=3.34e+07")
print()
print(f"{'variant':40s}  {'growth':>14s}  {'flux L1':>11s}  {'nnz':>5s}  {'WB L1':>8s}")
print("-" * 90)

for presolve in [True, False]:
    for scale in [True, False]:
        for tol_bnd in [1e-6, 1e-7]:
            label = f"presol={presolve}, scale={scale}, tol={tol_bnd:.0e}"
            try:
                v, growth, L1, nnz = solve_variant(presolve, scale, tol_bnd, label)
                wb = writeback_L1(v, growth)
                print(f"{label:40s}  {growth:14.6e}  {L1:11.4e}  {nnz:5d}  {wb:8.0f}")
            except Exception as e:
                print(f"{label:40s}  FAILED: {e}")
