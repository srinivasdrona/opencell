"""Day-42 probe (h): pFBA / global secondary objective disambiguation.

Sample fixed at (seed=0, tick=1). Compare three LP configurations:
  - V_prod:     current production single-solve GLPK
  - V_pfba:     existing km._solve_fba_glpk_pfba two-stage solve
  - V_loopless: two-stage solve with biomass fixed, then minimize sum |v|
                over non-exchange columns only (probe-local implementation)

For each successful variant:
  - objective value
  - full-flux L1 vs Karr
  - external-exchange flux L1 vs Karr
  - deterministic writeback delta L1 vs Karr
  - substitution-pair column flux values (8 columns)

Writes:
  - tmp/h_pfba.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)


class _DetRng:
    def stochastic_round(self, values):
        return np.rint(np.asarray(values, dtype=np.float64)).astype(np.int64)


# Substitution-pair columns from Day-42 probes.
PAIR_COLS: dict[str, int] = {
    "HDCA": 393,
    "OCDCEA": 422,
    "PHE": 423,
    "PhePhe": 424,
    "TRIOLEIN": 444,
    "TRIPALMITIN": 445,
    "TRP": 449,
    "TrpTrp": 450,
}


def _load_inputs():
    sample_path = (
        REPO
        / "data"
        / "karr_fixtures"
        / "matlab_ground_truth"
        / "metab_flux_allocated_state_s000_tick1.mat"
    )
    fixture_path = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    lp_path = REPO / "data" / "karr_fixtures" / "karr_native_m1.npz"

    with h5py.File(sample_path, "r") as h:
        karr_flux = np.asarray(h["flux"], dtype=np.float64).reshape(-1)
        karr_growth = float(np.asarray(h["growth"], dtype=np.float64).reshape(-1)[0])
        pre_sub = np.asarray(h["pre_sub"], dtype=np.float64).T
        karr_delta = np.asarray(h["delta"], dtype=np.float64).T
        bounds = np.asarray(h["bounds"], dtype=np.float64).T

    npz = np.load(lp_path, allow_pickle=False)
    S = np.asarray(npz["S"], dtype=np.float64)
    rhs = np.asarray(npz["RHS"], dtype=np.float64).reshape(-1)
    c = np.asarray(npz["obj"], dtype=np.float64).reshape(-1)

    big = 1e6
    lb = np.clip(bounds[:, 0], -big, big)
    ub = np.clip(bounds[:, 1], -big, big)

    fixture = KarrWritebackFixture.from_mat(fixture_path)
    model = SimpleNamespace(S=S, RHS=rhs)
    biomass_col = int(np.argmax(np.abs(c)))
    return model, c, lb, ub, fixture, karr_flux, karr_growth, pre_sub, karr_delta, biomass_col


def _solve_glpk_loopless_internal(
    model: SimpleNamespace,
    *,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    sense: str,
    biomass_col: int,
    penalty_mask: np.ndarray,
) -> tuple[np.ndarray, float, str]:
    """Probe-local loopless-style solve: biomass-fixed + minimize internal |v|."""
    import swiglpk as glp  # noqa: PLC0415

    if sense != "max":
        raise ValueError("loopless probe expects sense='max'")
    R = c.shape[0]
    M = model.S.shape[0]
    rhs = np.asarray(model.RHS, dtype=np.float64).reshape(-1)
    if penalty_mask.shape != (R,):
        raise ValueError(f"penalty_mask shape mismatch: {penalty_mask.shape}, expected {(R,)}")

    # Stage 1: production objective optimum.
    v_stage1, _obj_stage1, _status_stage1 = km._solve_fba_glpk(
        model,
        c=c,
        lb=lb,
        ub=ub,
        sense=sense,
    )
    biomass_flux = float(v_stage1[biomass_col])

    # Stage 2: fix biomass and minimize selected |v|.
    lp = glp.glp_create_prob()
    try:
        glp.glp_set_obj_dir(lp, glp.GLP_MIN)

        n_rows = M + 2 * R
        glp.glp_add_rows(lp, n_rows)
        for i in range(M):
            glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))
        for i in range(R):
            glp.glp_set_row_bnds(lp, M + 1 + i, glp.GLP_LO, 0.0, 0.0)  # w_i - v_i >= 0
            glp.glp_set_row_bnds(lp, M + R + 1 + i, glp.GLP_LO, 0.0, 0.0)  # w_i + v_i >= 0

        glp.glp_add_cols(lp, 2 * R)
        for j in range(R):
            lj, uj = float(lb[j]), float(ub[j])
            if j == biomass_col:
                bio_tol = max(1e-9, 1e-6 * abs(biomass_flux))
                lo = max(lj, biomass_flux - bio_tol)
                hi = min(uj, biomass_flux + bio_tol)
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lo, hi)
            elif lj == uj:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lj, uj)
            else:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lj, uj)
            glp.glp_set_obj_coef(lp, j + 1, 0.0)

        big_w = max(
            1.0,
            float(np.max(np.abs(lb))),
            float(np.max(np.abs(ub))),
        ) * 2.0
        for j in range(R):
            glp.glp_set_col_bnds(lp, R + j + 1, glp.GLP_DB, 0.0, big_w)
            glp.glp_set_obj_coef(lp, R + j + 1, 1.0 if penalty_mask[j] else 0.0)

        S = np.asarray(model.S, dtype=np.float64)
        S_rows, S_cols = np.nonzero(S)
        n_s = int(len(S_rows))
        nnz_total = n_s + 4 * R
        ia = glp.intArray(nnz_total + 1)
        ja = glp.intArray(nnz_total + 1)
        ar = glp.doubleArray(nnz_total + 1)
        k = 0
        for idx in range(n_s):
            k += 1
            ia[k] = int(S_rows[idx]) + 1
            ja[k] = int(S_cols[idx]) + 1
            ar[k] = float(S[S_rows[idx], S_cols[idx]])
        for i in range(R):
            k += 1
            ia[k] = M + 1 + i
            ja[k] = R + i + 1
            ar[k] = 1.0
            k += 1
            ia[k] = M + 1 + i
            ja[k] = i + 1
            ar[k] = -1.0
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
        parm.pricing = glp.GLP_PT_STD

        status = glp.glp_simplex(lp, parm)
        if status != 0:
            raise RuntimeError(f"GLPK loopless stage-2 simplex returned status {status}")
        sol_status = glp.glp_get_status(lp)
        if sol_status != glp.GLP_OPT:
            raise RuntimeError(
                f"GLPK loopless stage-2 did not reach optimum (status {sol_status})"
            )

        v = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(R)], dtype=np.float64)
        sum_abs_penalized = float(glp.glp_get_obj_val(lp))
        original_obj = float(np.dot(c, v))
        status_msg = (
            f"loopless_ok sum_abs_penalized={sum_abs_penalized:.4e} "
            f"n_penalized={int(penalty_mask.sum())}"
        )
        return v, original_obj, status_msg
    finally:
        glp.glp_delete_prob(lp)


def _variant_metrics(
    *,
    label: str,
    flux: np.ndarray,
    obj: float,
    status: str,
    fixture: KarrWritebackFixture,
    biomass_col: int,
    pre_sub: np.ndarray,
    karr_flux: np.ndarray,
    karr_delta: np.ndarray,
) -> dict:
    growth = float(flux[biomass_col])
    rng = _DetRng()
    oc_delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(),
        v_504=flux,
        growth_per_s=growth,
        fixture=fixture,
        rng=rng,
        step_size_sec=fixture.step_size_sec,
    )
    full_l1 = float(np.abs(flux - karr_flux).sum())
    ext_l1 = float(np.abs(flux[fixture.fba_idx_external] - karr_flux[fixture.fba_idx_external]).sum())
    wb_l1 = int(np.abs(oc_delta.astype(np.int64) - karr_delta.astype(np.int64)).sum())
    pair_flux = {name: float(flux[col]) for name, col in PAIR_COLS.items()}
    return {
        "label": label,
        "lp_status": status,
        "lp_obj": float(obj),
        "biomass_growth": growth,
        "full_flux_l1_vs_karr": full_l1,
        "ext_exchange_flux_l1_vs_karr": ext_l1,
        "writeback_delta_l1_vs_karr": wb_l1,
        "pair_flux": pair_flux,
    }


def _attach_preservation(result: dict, baseline: dict):
    obj_den = max(1e-12, abs(float(baseline["lp_obj"])))
    obj_rel = abs(float(result["lp_obj"]) - float(baseline["lp_obj"])) / obj_den
    bio_den = max(1e-12, abs(float(baseline["biomass_growth"])))
    bio_rel = abs(float(result["biomass_growth"]) - float(baseline["biomass_growth"])) / bio_den
    result["objective_rel_diff_vs_v_prod"] = float(obj_rel)
    result["biomass_rel_diff_vs_v_prod"] = float(bio_rel)
    result["objective_preserved_1e_5"] = bool(obj_rel <= 1e-5)
    result["biomass_preserved_1e_5"] = bool(bio_rel <= 1e-5)


def main():
    (
        model,
        c,
        lb,
        ub,
        fixture,
        karr_flux,
        karr_growth,
        pre_sub,
        karr_delta,
        biomass_col,
    ) = _load_inputs()

    # Deterministic writeback floor when feeding Karr's own flux/growth.
    floor_delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(),
        v_504=karr_flux,
        growth_per_s=karr_growth,
        fixture=fixture,
        rng=_DetRng(),
        step_size_sec=fixture.step_size_sec,
    )
    wb_floor_l1 = int(np.abs(floor_delta.astype(np.int64) - karr_delta.astype(np.int64)).sum())

    pair_flux_karr = {name: float(karr_flux[col]) for name, col in PAIR_COLS.items()}

    # V_prod: production baseline.
    v_prod, obj_prod, status_prod = km._solve_fba_glpk(
        model, c=c, lb=lb, ub=ub, sense="max",
    )
    r_prod = _variant_metrics(
        label="V_prod",
        flux=v_prod,
        obj=obj_prod,
        status=status_prod,
        fixture=fixture,
        biomass_col=biomass_col,
        pre_sub=pre_sub,
        karr_flux=karr_flux,
        karr_delta=karr_delta,
    )

    # V_pfba: existing production function (must remain unmodified).
    r_pfba = None
    pfba_error = None
    try:
        v_pfba, obj_pfba, status_pfba = km._solve_fba_glpk_pfba(
            model,
            c=c,
            lb=lb,
            ub=ub,
            sense="max",
            biomass_col=biomass_col,
        )
        r_pfba = _variant_metrics(
            label="V_pfba",
            flux=v_pfba,
            obj=obj_pfba,
            status=status_pfba,
            fixture=fixture,
            biomass_col=biomass_col,
            pre_sub=pre_sub,
            karr_flux=karr_flux,
            karr_delta=karr_delta,
        )
        _attach_preservation(r_pfba, r_prod)
    except Exception as exc:  # noqa: BLE001
        pfba_error = {"type": type(exc).__name__, "message": str(exc)}

    # V_loopless: stage-2 parsimony excluding exchange columns from penalty.
    exchange_cols = np.unique(
        np.concatenate([fixture.fba_idx_external, fixture.fba_idx_internal]).astype(np.int64)
    )
    penalty_mask = np.ones(c.shape[0], dtype=bool)
    penalty_mask[exchange_cols] = False
    penalty_mask[biomass_col] = False

    r_loopless = None
    loopless_error = None
    try:
        v_loop, obj_loop, status_loop = _solve_glpk_loopless_internal(
            model,
            c=c,
            lb=lb,
            ub=ub,
            sense="max",
            biomass_col=biomass_col,
            penalty_mask=penalty_mask,
        )
        r_loopless = _variant_metrics(
            label="V_loopless",
            flux=v_loop,
            obj=obj_loop,
            status=status_loop,
            fixture=fixture,
            biomass_col=biomass_col,
            pre_sub=pre_sub,
            karr_flux=karr_flux,
            karr_delta=karr_delta,
        )
        _attach_preservation(r_loopless, r_prod)
    except Exception as exc:  # noqa: BLE001
        loopless_error = {"type": type(exc).__name__, "message": str(exc)}

    # Derived comparisons.
    baseline_wb = int(r_prod["writeback_delta_l1_vs_karr"])
    denom_to_floor = max(1, baseline_wb - wb_floor_l1)

    def summarize_closure(variant_result):
        if variant_result is None:
            return None
        wb = int(variant_result["writeback_delta_l1_vs_karr"])
        improved = baseline_wb - wb
        frac = improved / denom_to_floor
        return {
            "writeback_l1": wb,
            "improvement_vs_v_prod": int(improved),
            "fraction_of_gap_to_floor_closed_vs_v_prod": float(frac),
        }

    closure_pfba = summarize_closure(r_pfba)
    closure_loopless = summarize_closure(r_loopless)

    # Console report.
    print("Day-42 Probe H: pFBA / global secondary objective")
    print("sample=(seed=0, tick=1)")
    print(f"biomass_col={biomass_col}")
    print(
        f"writeback deterministic floor (Karr-flux -> Karr-delta L1): {wb_floor_l1}"
    )
    print()
    print(
        f"{'variant':<12s} {'status':<44s} {'obj':>12s} {'growth':>12s} "
        f"{'full_L1':>12s} {'ext_L1':>12s} {'WB_L1':>10s}"
    )
    print("-" * 120)

    def row_from_result(r):
        return (
            f"{r['label']:<12s} {str(r['lp_status'])[:44]:<44s} "
            f"{r['lp_obj']:>12.6e} {r['biomass_growth']:>12.6e} "
            f"{r['full_flux_l1_vs_karr']:>12.3e} {r['ext_exchange_flux_l1_vs_karr']:>12.3e} "
            f"{int(r['writeback_delta_l1_vs_karr']):>10d}"
        )

    print(row_from_result(r_prod))
    if r_pfba is not None:
        print(row_from_result(r_pfba))
    else:
        print(
            f"{'V_pfba':<12s} {('ERROR: ' + pfba_error['message'])[:44]:<44s} "
            f"{'-':>12s} {'-':>12s} {'-':>12s} {'-':>12s} {'-':>10s}"
        )
    if r_loopless is not None:
        print(row_from_result(r_loopless))
    else:
        print(
            f"{'V_loopless':<12s} {('ERROR: ' + loopless_error['message'])[:44]:<44s} "
            f"{'-':>12s} {'-':>12s} {'-':>12s} {'-':>12s} {'-':>10s}"
        )

    print()
    print("Pair-column flux comparison:")
    print(
        f"{'name':>12s} {'Karr':>12s} {'V_prod':>12s} {'V_pfba':>12s} {'V_loopless':>12s}"
    )
    for name in PAIR_COLS:
        k = pair_flux_karr[name]
        p = r_prod["pair_flux"][name]
        pf = r_pfba["pair_flux"][name] if r_pfba is not None else None
        lo = r_loopless["pair_flux"][name] if r_loopless is not None else None
        pf_s = f"{pf:+12.3e}" if pf is not None else f"{'ERR':>12s}"
        lo_s = f"{lo:+12.3e}" if lo is not None else f"{'ERR':>12s}"
        print(f"{name:>12s} {k:+12.3e} {p:+12.3e} {pf_s} {lo_s}")

    if r_pfba is not None:
        print()
        print(
            "V_pfba preservation vs V_prod: "
            f"objective_rel_diff={r_pfba['objective_rel_diff_vs_v_prod']:.3e}, "
            f"biomass_rel_diff={r_pfba['biomass_rel_diff_vs_v_prod']:.3e}, "
            f"pass_obj={r_pfba['objective_preserved_1e_5']}, "
            f"pass_biomass={r_pfba['biomass_preserved_1e_5']}"
        )
    if r_loopless is not None:
        print(
            "V_loopless preservation vs V_prod: "
            f"objective_rel_diff={r_loopless['objective_rel_diff_vs_v_prod']:.3e}, "
            f"biomass_rel_diff={r_loopless['biomass_rel_diff_vs_v_prod']:.3e}, "
            f"pass_obj={r_loopless['objective_preserved_1e_5']}, "
            f"pass_biomass={r_loopless['biomass_preserved_1e_5']}"
        )

    if closure_pfba is not None:
        print(
            "V_pfba writeback-gap closure: "
            f"{closure_pfba['improvement_vs_v_prod']} "
            f"(fraction to floor={closure_pfba['fraction_of_gap_to_floor_closed_vs_v_prod']:.3%})"
        )
    if closure_loopless is not None:
        print(
            "V_loopless writeback-gap closure: "
            f"{closure_loopless['improvement_vs_v_prod']} "
            f"(fraction to floor={closure_loopless['fraction_of_gap_to_floor_closed_vs_v_prod']:.3%})"
        )

    out = {
        "probe": "Day-42 Probe H: pFBA / global secondary objective",
        "sample": {"seed": 0, "tick": 1},
        "constants": {
            "biomass_col": biomass_col,
            "pair_cols": PAIR_COLS,
            "wb_floor_l1_deterministic": wb_floor_l1,
            "exchange_cols_count": int(exchange_cols.size),
            "loopless_penalized_cols_count": int(penalty_mask.sum()),
        },
        "karr": {
            "growth": karr_growth,
            "pair_flux": pair_flux_karr,
        },
        "variants": {
            "V_prod": r_prod,
            "V_pfba": r_pfba,
            "V_loopless": r_loopless,
        },
        "errors": {
            "V_pfba": pfba_error,
            "V_loopless": loopless_error,
        },
        "closure": {
            "V_pfba": closure_pfba,
            "V_loopless": closure_loopless,
        },
    }

    out_path = REPO / "tmp" / "h_pfba.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
