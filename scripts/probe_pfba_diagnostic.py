"""Diagnose pFBA stage 2: dump problem stats + verify LP construction."""
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

with h5py.File(GT_PATH, "r") as h:
    bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T

model = km.load_default()
lb_arr = bounds_karr[:, 0]
ub_arr = bounds_karr[:, 1]
big = 1e6
lb_arr = np.clip(np.where(np.isfinite(lb_arr), lb_arr, -big), -big, big)
ub_arr = np.clip(np.where(np.isfinite(ub_arr), ub_arr, big), -big, big)

# Stage 1 manual call
c_natural = model.obj.copy().astype(np.float64)
v_stage1, obj1, _ = km._solve_fba_glpk(
    model, c=c_natural, lb=lb_arr, ub=ub_arr, sense="max",
)
print(f"Stage 1: growth={v_stage1[model.biomass_col]:.6e}  obj={obj1:.6e}")
print(f"         biomass_col={model.biomass_col}")
print(f"         sum_abs(v)={np.abs(v_stage1).sum():.4e}")

biomass_flux = float(v_stage1[model.biomass_col])
print(f"         biomass_flux={biomass_flux:.6e}")

# Manually re-build stage 2 with diagnostics
R = 504
M = model.S.shape[0]
print(f"Model dims: M={M} rows, R={R} cols")

bio_tol = max(1e-7, 1e-6 * abs(biomass_flux))
print(f"bio_tol = {bio_tol:.4e}  bounds [{biomass_flux - bio_tol:.4e}, {biomass_flux + bio_tol:.4e}]")

n_rows = M + 1 + 2 * R
print(f"n_rows = {n_rows}")
print(f"biomass-fix row index: {M+1}")
print(f"w-v rows: {M+2}..{M+1+R}")
print(f"w+v rows: {M+R+2}..{M+1+2*R}")

# Now actually build + solve and inspect
lp = glp.glp_create_prob()
glp.glp_set_obj_dir(lp, glp.GLP_MIN)
glp.glp_add_rows(lp, n_rows)
rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)
for i in range(M):
    glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))
glp.glp_set_row_bnds(lp, M + 1, glp.GLP_DB, biomass_flux - bio_tol, biomass_flux + bio_tol)
for i in range(R):
    glp.glp_set_row_bnds(lp, M + 1 + 1 + i, glp.GLP_LO, 0.0, 0.0)
for i in range(R):
    glp.glp_set_row_bnds(lp, M + 1 + R + 1 + i, glp.GLP_LO, 0.0, 0.0)

glp.glp_add_cols(lp, 2 * R)
for j in range(R):
    lj, uj = float(lb_arr[j]), float(ub_arr[j])
    if lj == uj:
        glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lj, uj)
    else:
        glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lj, uj)
    glp.glp_set_obj_coef(lp, j + 1, 0.0)

big_w = max(max(abs(float(lb_arr[j])) for j in range(R)),
            max(abs(float(ub_arr[j])) for j in range(R))) * 2.0
for j in range(R):
    glp.glp_set_col_bnds(lp, R + j + 1, glp.GLP_DB, 0.0, big_w)
    glp.glp_set_obj_coef(lp, R + j + 1, 0.0 if j == model.biomass_col else 1.0)

# Build matrix
S = np.asarray(model.S, dtype=np.float64)
S_rows, S_cols = np.nonzero(S)
n_S = int(len(S_rows))
nnz_total = n_S + 1 + 4 * R
print(f"nnz_total = {nnz_total}  (S nnz = {n_S}, +1 biomass, +{4*R} w-v/w+v)")

ia = glp.intArray(nnz_total + 1)
ja = glp.intArray(nnz_total + 1)
ar = glp.doubleArray(nnz_total + 1)
k = 0
for idx in range(n_S):
    k += 1
    ia[k] = int(S_rows[idx]) + 1
    ja[k] = int(S_cols[idx]) + 1
    ar[k] = float(S[S_rows[idx], S_cols[idx]])
k += 1
ia[k] = M + 1
ja[k] = model.biomass_col + 1
ar[k] = 1.0
for i in range(R):
    k += 1
    ia[k] = M + 1 + 1 + i
    ja[k] = R + i + 1
    ar[k] = 1.0
    k += 1
    ia[k] = M + 1 + 1 + i
    ja[k] = i + 1
    ar[k] = -1.0
for i in range(R):
    k += 1
    ia[k] = M + 1 + R + 1 + i
    ja[k] = R + i + 1
    ar[k] = 1.0
    k += 1
    ia[k] = M + 1 + R + 1 + i
    ja[k] = i + 1
    ar[k] = 1.0
print(f"Triplets written: k={k}")
glp.glp_load_matrix(lp, k, ia, ja, ar)

parm = glp.glp_smcp()
glp.glp_init_smcp(parm)
parm.msg_lev = glp.GLP_MSG_ON  # verbose
parm.presolve = glp.GLP_ON
parm.meth = glp.GLP_PRIMAL

print()
print("--- GLPK simplex ---")
status = glp.glp_simplex(lp, parm)
sol_status = glp.glp_get_status(lp)
print(f"status_code={status}, sol_status={sol_status} (OPT={glp.GLP_OPT}, FEAS={glp.GLP_FEAS}, INFEAS={glp.GLP_INFEAS}, NOFEAS={glp.GLP_NOFEAS})")

v_out = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64)
w_out = np.array([glp.glp_get_col_prim(lp, R + j + 1) for j in range(R)], dtype=np.float64)
print(f"v: growth={v_out[model.biomass_col]:.6e}  sum_abs={np.abs(v_out).sum():.4e}  nnz={(np.abs(v_out)>1e-9).sum()}")
print(f"w: sum={w_out.sum():.4e}  max={w_out.max():.4e}")

# Inspect biomass row
biomass_row_val = glp.glp_get_row_prim(lp, M + 1)
print(f"Biomass row primal: {biomass_row_val:.6e}  (should be in [{biomass_flux - bio_tol:.4e}, {biomass_flux + bio_tol:.4e}])")

glp.glp_delete_prob(lp)
