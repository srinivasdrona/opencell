"""Day-41 follow-up probe: presolve ON vs OFF, now that pricing=STD.

Karr's Metabolism.m:176 uses presolve=1 (ON). Day-40 found presolve=OFF
helps OC under PSE pricing, but that was the wrong-vertex regime.
Re-test under the now-correct STD pricing.

Sample: (s=0, t=1). Output: tmp/h5_presolve_under_std.json + console.
"""
import json
import numpy as np
import h5py
import swiglpk as glp


def build_and_solve(S, rhs, c, lb, ub, *, presolve, scale_type, tol_bnd, pricing, sense="max"):
    R = c.shape[0]
    M = S.shape[0]

    lp = glp.glp_create_prob()
    try:
        glp.glp_set_obj_dir(lp, glp.GLP_MAX if sense == "max" else glp.GLP_MIN)
        glp.glp_add_rows(lp, M)
        for i in range(M):
            glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))

        glp.glp_add_cols(lp, R)
        for j in range(R):
            lo = float(lb[j])
            hi = float(ub[j])
            if lo == hi:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lo, hi)
            else:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lo, hi)
            glp.glp_set_obj_coef(lp, j + 1, float(c[j]))

        nz_rows, nz_cols = np.nonzero(S)
        nnz = int(len(nz_rows))
        ia = glp.intArray(nnz + 1)
        ja = glp.intArray(nnz + 1)
        ar = glp.doubleArray(nnz + 1)
        for k in range(nnz):
            ia[k + 1] = int(nz_rows[k]) + 1
            ja[k + 1] = int(nz_cols[k]) + 1
            ar[k + 1] = float(S[nz_rows[k], nz_cols[k]])
        glp.glp_load_matrix(lp, nnz, ia, ja, ar)

        glp.glp_scale_prob(lp, scale_type)
        glp.glp_adv_basis(lp, 0)

        parm = glp.glp_smcp()
        glp.glp_init_smcp(parm)
        parm.msg_lev = glp.GLP_MSG_OFF
        parm.presolve = presolve
        parm.meth = glp.GLP_PRIMAL
        parm.tol_bnd = tol_bnd
        parm.pricing = pricing

        status_code = glp.glp_simplex(lp, parm)
        sol_status = glp.glp_get_status(lp)
        obj = float(glp.glp_get_obj_val(lp))

        v = np.array(
            [glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64
        )
        v_clipped = np.clip(v, lb, ub)
        return {
            "status_code": status_code,
            "sol_status": sol_status,
            "objective": obj,
            "flux": v,
            "flux_clipped": v_clipped,
        }
    finally:
        glp.glp_delete_prob(lp)


def main():
    npz = np.load("data/karr_fixtures/karr_native_m1.npz", allow_pickle=False)
    S = npz["S"].astype(np.float64)
    rhs = npz["RHS"].astype(np.float64)
    c = npz["obj"].astype(np.float64)

    with h5py.File("data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat", "r") as f:
        bounds = np.array(f["bounds"]).T  # (504, 2)
        karr_flux = np.array(f["flux"]).ravel()

    sample_lb = bounds[:, 0].astype(np.float64)
    sample_ub = bounds[:, 1].astype(np.float64)

    BIG = 1e6
    lb = np.clip(sample_lb, -BIG, BIG)
    ub = np.clip(sample_ub, -BIG, BIG)

    # Variants. Each row = (id, description, presolve, scale, tol, pricing)
    variants = [
        # Production-current (our shipped fix from 1735729): presolve=OFF, pricing=STD
        ("V_prod", "presolve=OFF + STD (current production)",
         glp.GLP_OFF, glp.GLP_SF_AUTO, 1e-6, glp.GLP_PT_STD),
        # Karr's literal Metabolism.m:176 config: presolve=ON, scale=AUTO, tolbnd=1e-6, pricing default (STD on GLPK 4.x)
        ("V_karr", "presolve=ON + STD (Karr Metabolism.m:176 literal)",
         glp.GLP_ON, glp.GLP_SF_AUTO, 1e-6, glp.GLP_PT_STD),
        # Stress: what if glpkmex's scale=1 actually means equilibration only? (GLP_SF_EQ)
        ("V_eq", "presolve=ON + STD + scale=EQ",
         glp.GLP_ON, glp.GLP_SF_EQ, 1e-6, glp.GLP_PT_STD),
        # Stress: what if scale=1 means geometric mean only? (GLP_SF_GM)
        ("V_gm", "presolve=ON + STD + scale=GM",
         glp.GLP_ON, glp.GLP_SF_GM, 1e-6, glp.GLP_PT_STD),
        # Stress: tolbnd=1e-7 (glpkmex defaults to 1e-7, not 1e-6)
        ("V_tol1e7", "presolve=ON + STD + tol_bnd=1e-7",
         glp.GLP_ON, glp.GLP_SF_AUTO, 1e-7, glp.GLP_PT_STD),
    ]

    results = []
    for vid, desc, ps, sc, tol, pr in variants:
        try:
            r = build_and_solve(S, rhs, c, lb, ub,
                                presolve=ps, scale_type=sc, tol_bnd=tol, pricing=pr)
            l1_vs_karr = float(np.abs(r["flux_clipped"] - karr_flux).sum())
            linf_vs_karr = float(np.abs(r["flux_clipped"] - karr_flux).max())
            nnz_diff = int(np.sum(np.abs(r["flux_clipped"] - karr_flux) > 1e-9))
            print(f"{vid:>10s}  obj={r['objective']:.6e}  L1_vs_Karr={l1_vs_karr:.3e}  Linf={linf_vs_karr:.3e}  nnz_diff={nnz_diff:>3d}  status={r['sol_status']}  | {desc}")
            results.append({
                "id": vid, "desc": desc,
                "presolve": int(ps), "scale": int(sc), "tol_bnd": tol, "pricing": int(pr),
                "objective": r["objective"],
                "sol_status": int(r["sol_status"]),
                "l1_vs_karr": l1_vs_karr,
                "linf_vs_karr": linf_vs_karr,
                "nnz_diff_gt_1e9": nnz_diff,
            })
        except Exception as e:
            print(f"{vid:>10s}  FAILED: {e}")
            results.append({"id": vid, "desc": desc, "error": str(e)})

    # Pairwise L1 between fluxes of V_prod and V_karr
    flux_prod = None
    flux_karr = None
    for vid, desc, ps, sc, tol, pr in variants[:2]:
        r = build_and_solve(S, rhs, c, lb, ub,
                            presolve=ps, scale_type=sc, tol_bnd=tol, pricing=pr)
        if vid == "V_prod":
            flux_prod = r["flux_clipped"]
        elif vid == "V_karr":
            flux_karr = r["flux_clipped"]
    if flux_prod is not None and flux_karr is not None:
        pairwise = float(np.abs(flux_prod - flux_karr).sum())
        print(f"\nPairwise L1(V_prod, V_karr) = {pairwise:.3e}")

    out_path = "tmp/h5_presolve_under_std.json"
    with open(out_path, "w") as f:
        json.dump({"variants": results, "karr_recorded_l1_baseline_pre_fix": 8.18e+6}, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
