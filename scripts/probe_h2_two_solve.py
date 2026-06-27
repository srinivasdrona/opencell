from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import swiglpk as glp
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MAT = (
    ROOT
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
FLAT_MAT = ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
NPZ_PATH = ROOT / "data" / "karr_fixtures" / "karr_native_m1.npz"
OUT_JSON = ROOT / "tmp" / "h2_two_solve.json"
OUT_STATUS = ROOT / "STATUS_h2.md"

TOL = 1e-6
BIOMASS_TOL = 1e-9


def _finite_or_none(value: float) -> float | None:
    if np.isfinite(value):
        return float(value)
    return None


def load_sample() -> dict:
    with h5py.File(SAMPLE_MAT, "r") as f:
        flux = np.array(f["flux"], dtype=np.float64).reshape(-1)
        bounds = np.array(f["bounds"], dtype=np.float64)
        growth = float(np.array(f["growth"], dtype=np.float64)[0, 0])
    return {
        "flux": flux,
        "lb": bounds[0].reshape(-1),
        "ub": bounds[1].reshape(-1),
        "growth": growth,
    }


def load_flat_glpk_options() -> dict:
    fixture = loadmat(FLAT_MAT, squeeze_me=True, struct_as_record=False)["data"].fixture
    opts = fixture.linearProgrammingOptions.solverOptions.glpk
    return {
        "solver": str(fixture.linearProgrammingOptions.solver),
        "lpsolver": int(opts.lpsolver),
        "msglev": int(opts.msglev),
        "presol": int(opts.presol),
        "scale": int(opts.scale),
        "tolbnd": float(opts.tolbnd),
    }


def load_npz() -> dict:
    with np.load(NPZ_PATH) as data:
        return {
            "S": np.array(data["S"], dtype=np.float64),
            "RHS": np.array(data["RHS"], dtype=np.float64).reshape(-1),
            "obj": np.array(data["obj"], dtype=np.float64).reshape(-1),
            "lb": np.array(data["lb"], dtype=np.float64).reshape(-1),
            "ub": np.array(data["ub"], dtype=np.float64).reshape(-1),
        }


def biomass_col_from_obj(obj: np.ndarray) -> int:
    return int(np.argmax(obj))


def solve_glpk(
    *,
    S: np.ndarray,
    rhs: np.ndarray,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    sense: str,
    fixed_cols: dict[int, float] | None = None,
) -> dict:
    rows_count, cols_count = S.shape
    fixed_cols = fixed_cols or {}

    lp = glp.glp_create_prob()
    try:
        glp.glp_set_obj_dir(lp, glp.GLP_MAX if sense == "max" else glp.GLP_MIN)
        glp.glp_add_rows(lp, rows_count)
        for i in range(rows_count):
            glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))

        glp.glp_add_cols(lp, cols_count)
        for j in range(cols_count):
            if j in fixed_cols:
                val = float(fixed_cols[j])
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, val, val)
            else:
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

        glp.glp_scale_prob(lp, glp.GLP_SF_AUTO)
        glp.glp_adv_basis(lp, 0)

        params = glp.glp_smcp()
        glp.glp_init_smcp(params)
        params.msg_lev = glp.GLP_MSG_OFF
        params.presolve = glp.GLP_OFF
        params.meth = glp.GLP_PRIMAL
        params.tol_bnd = 1e-6
        params.pricing = glp.GLP_PT_STD

        status_code = glp.glp_simplex(lp, params)
        if status_code != 0:
            raise RuntimeError(f"GLPK simplex returned status {status_code}")
        sol_status = glp.glp_get_status(lp)
        if sol_status != glp.GLP_OPT:
            raise RuntimeError(f"GLPK did not reach optimum (status {sol_status})")

        flux = np.array(
            [glp.glp_get_col_prim(lp, j + 1) for j in range(cols_count)], dtype=np.float64
        )
        clip_lb = lb.copy()
        clip_ub = ub.copy()
        for idx, value in fixed_cols.items():
            clip_lb[idx] = value
            clip_ub[idx] = value
        flux = np.clip(flux, clip_lb, clip_ub)
        return {
            "flux": flux,
            "objective": float(glp.glp_get_obj_val(lp)),
            "glpk_status": int(sol_status),
            "simplex_status": int(status_code),
        }
    finally:
        glp.glp_delete_prob(lp)


def comparison_summary(lhs: np.ndarray, rhs: np.ndarray, *, tol: float = TOL) -> dict:
    abs_diff = np.abs(lhs - rhs)
    order = np.argsort(abs_diff)[::-1]
    top = []
    for idx in order[:10]:
        top.append(
            {
                "col": int(idx),
                "abs_diff": float(abs_diff[idx]),
                "lhs": _finite_or_none(lhs[idx]),
                "rhs": _finite_or_none(rhs[idx]),
            }
        )
    return {
        "l1": float(abs_diff.sum()),
        "l2": float(np.linalg.norm(abs_diff)),
        "linf": float(abs_diff.max()),
        "count_abs_gt_tol": int(np.sum(abs_diff > tol)),
        "sum_abs_diff": float(abs_diff.sum()),
        "max_abs_diff": float(abs_diff.max()),
        "top10": top,
    }


def protocol_vs_karr_summary(
    protocol_flux: np.ndarray, karr_flux: np.ndarray, *, tol: float = TOL
) -> dict:
    abs_diff = np.abs(protocol_flux - karr_flux)
    order = np.argsort(abs_diff)[::-1]
    return {
        "l1": float(abs_diff.sum()),
        "l2": float(np.linalg.norm(abs_diff)),
        "linf": float(abs_diff.max()),
        "count_abs_gt_tol": int(np.sum(abs_diff > tol)),
        "top10": [
            {
                "col": int(idx),
                "abs_diff": float(abs_diff[idx]),
                "protocol": _finite_or_none(protocol_flux[idx]),
                "karr": _finite_or_none(karr_flux[idx]),
            }
            for idx in order[:10]
        ],
    }


def better_match_breakdown(
    flux_a: np.ndarray, flux_b: np.ndarray, karr_flux: np.ndarray, *, tol: float = TOL
) -> dict:
    err_a = np.abs(flux_a - karr_flux)
    err_b = np.abs(flux_b - karr_flux)
    delta = err_a - err_b
    a_better = np.where(delta < -tol)[0]
    b_better = np.where(delta > tol)[0]
    ties = np.where(np.abs(delta) <= tol)[0]
    order = np.argsort(np.abs(delta))[::-1]
    return {
        "a_better_count": int(a_better.size),
        "b_better_count": int(b_better.size),
        "tie_count": int(ties.size),
        "winner_by_l1": "A" if err_a.sum() < err_b.sum() else "B" if err_b.sum() < err_a.sum() else "tie",
        "winner_by_linf": "A"
        if err_a.max() < err_b.max()
        else "B"
        if err_b.max() < err_a.max()
        else "tie",
        "top10_delta": [
            {
                "col": int(idx),
                "abs_error_A": float(err_a[idx]),
                "abs_error_B": float(err_b[idx]),
                "delta_A_minus_B": float(delta[idx]),
                "closer_protocol": "B" if delta[idx] > tol else "A" if delta[idx] < -tol else "tie",
            }
            for idx in order[:10]
        ],
    }


def describe_protocol(
    *,
    label: str,
    flux: np.ndarray,
    full_objective: np.ndarray,
    stage2_objective: np.ndarray,
    biomass_col: int,
    sample_growth: float,
    extra: dict | None = None,
) -> dict:
    data = {
        "label": label,
        "flux": flux.tolist(),
        "combined_objective": float(np.dot(full_objective, flux)),
        "stage2_objective": float(np.dot(stage2_objective, flux)),
        "biomass_value": float(flux[biomass_col]),
        "biomass_matches_sample_growth": bool(
            abs(float(flux[biomass_col]) - sample_growth) <= BIOMASS_TOL
        ),
        "n_nonzero_abs_gt_1e-9": int(np.sum(np.abs(flux) > 1e-9)),
    }
    if extra:
        data.update(extra)
    return data


def classify_hypothesis(a_vs_b_max: float, winner_by_l1: str) -> str:
    if a_vs_b_max <= TOL:
        return "H2 falsified: protocol A and B match within 1e-6."
    if winner_by_l1 == "B":
        return "H2 supported: protocol B differs from A and is closer to Karr by L1."
    if winner_by_l1 == "A":
        return "H2 not supported: protocol B differs from A but moves away from Karr by L1."
    return "H2 mixed: protocol B differs from A, but neither protocol wins cleanly against Karr."


def main() -> None:
    sample = load_sample()
    fixture_glpk = load_flat_glpk_options()
    matrices = load_npz()

    S = matrices["S"]
    rhs = matrices["RHS"]
    full_objective = matrices["obj"]
    biomass_col = biomass_col_from_obj(full_objective)

    sample_lb = sample["lb"].copy()
    sample_ub = sample["ub"].copy()
    BIG = 1e6
    sample_lb = np.clip(sample_lb, -BIG, BIG)
    sample_ub = np.clip(sample_ub, -BIG, BIG)
    karr_flux = sample["flux"]
    sample_growth = sample["growth"]

    biomass_only = np.zeros_like(full_objective)
    biomass_only[biomass_col] = 1.0
    parsimony_only = full_objective.copy()
    parsimony_only[biomass_col] = 0.0

    a = solve_glpk(
        S=S,
        rhs=rhs,
        c=full_objective,
        lb=sample_lb,
        ub=sample_ub,
        sense="max",
    )
    b_stage1 = solve_glpk(
        S=S,
        rhs=rhs,
        c=biomass_only,
        lb=sample_lb,
        ub=sample_ub,
        sense="max",
    )
    growth0 = float(b_stage1["flux"][biomass_col])
    b = solve_glpk(
        S=S,
        rhs=rhs,
        c=parsimony_only,
        lb=sample_lb,
        ub=sample_ub,
        sense="max",
        fixed_cols={biomass_col: growth0},
    )

    a_vs_b = comparison_summary(a["flux"], b["flux"])
    a_vs_karr = protocol_vs_karr_summary(a["flux"], karr_flux)
    b_vs_karr = protocol_vs_karr_summary(b["flux"], karr_flux)
    closer = better_match_breakdown(a["flux"], b["flux"], karr_flux)

    out = {
        "metadata": {
            "hypothesis": "H2 two-solve protocol hypothesis",
            "sample": {"seed": 0, "tick": 1},
            "tolerance_abs": TOL,
            "biomass_tolerance_abs": BIOMASS_TOL,
            "inputs": {
                "sample_mat": str(SAMPLE_MAT.relative_to(ROOT)),
                "flat_mat": str(FLAT_MAT.relative_to(ROOT)),
                "npz": str(NPZ_PATH.relative_to(ROOT)),
                "sample_growth": sample_growth,
                "biomass_col": biomass_col,
            },
            "fixture_glpk_options": fixture_glpk,
            "used_glpk_options": {
                "solver": "swiglpk",
                "scale": "GLP_SF_AUTO",
                "advanced_basis": True,
                "presolve": "GLP_OFF",
                "method": "GLP_PRIMAL",
                "tol_bnd": 1e-6,
                "msg_lev": "GLP_MSG_OFF",
            },
            "sample_bounds_vs_npz_defaults": {
                "lb_finite_diff_count": int(
                    np.sum(
                        np.isfinite(sample_lb)
                        & np.isfinite(matrices["lb"])
                        & (sample_lb != matrices["lb"])
                    )
                ),
                "ub_finite_diff_count": int(
                    np.sum(
                        np.isfinite(sample_ub)
                        & np.isfinite(matrices["ub"])
                        & (sample_ub != matrices["ub"])
                    )
                ),
                "lb_inf_mismatch_count": int(np.sum(np.isinf(sample_lb) != np.isinf(matrices["lb"]))),
                "ub_inf_mismatch_count": int(np.sum(np.isinf(sample_ub) != np.isinf(matrices["ub"]))),
            },
        },
        "protocol_A_combined_objective": describe_protocol(
            label="A",
            flux=a["flux"],
            full_objective=full_objective,
            stage2_objective=parsimony_only,
            biomass_col=biomass_col,
            sample_growth=sample_growth,
            extra={
                "solve_objective_value": float(a["objective"]),
                "glpk_status": a["glpk_status"],
                "simplex_status": a["simplex_status"],
            },
        ),
        "protocol_B_two_step": describe_protocol(
            label="B",
            flux=b["flux"],
            full_objective=full_objective,
            stage2_objective=parsimony_only,
            biomass_col=biomass_col,
            sample_growth=sample_growth,
            extra={
                "growth0_from_stage1": growth0,
                "stage1_biomass_objective": float(b_stage1["objective"]),
                "stage2_parsimony_objective": float(b["objective"]),
                "stage1_glpk_status": b_stage1["glpk_status"],
                "stage2_glpk_status": b["glpk_status"],
                "stage1_simplex_status": b_stage1["simplex_status"],
                "stage2_simplex_status": b["simplex_status"],
                "biomass_fixed_with": "GLP_FX",
            },
        ),
        "karr_recorded_flux": describe_protocol(
            label="Karr",
            flux=karr_flux,
            full_objective=full_objective,
            stage2_objective=parsimony_only,
            biomass_col=biomass_col,
            sample_growth=sample_growth,
            extra={
                "growth_dataset_value": sample_growth,
                "flux_biomass_minus_growth_dataset": float(karr_flux[biomass_col] - sample_growth),
            },
        ),
        "comparisons": {
            "a_vs_b": a_vs_b,
            "a_vs_karr": a_vs_karr,
            "b_vs_karr": b_vs_karr,
            "protocol_match_to_karr": closer,
            "objective_values": {
                "c_dot_v_A": float(np.dot(full_objective, a["flux"])),
                "c_dot_v_B": float(np.dot(full_objective, b["flux"])),
                "c_dot_v_Karr": float(np.dot(full_objective, karr_flux)),
                "parsimony_only_dot_v_A": float(np.dot(parsimony_only, a["flux"])),
                "parsimony_only_dot_v_B": float(np.dot(parsimony_only, b["flux"])),
                "parsimony_only_dot_v_Karr": float(np.dot(parsimony_only, karr_flux)),
            },
            "biomass_values": {
                "A": float(a["flux"][biomass_col]),
                "B": float(b["flux"][biomass_col]),
                "Karr": float(karr_flux[biomass_col]),
                "growth_dataset": sample_growth,
                "all_match_sample_growth_within_tol": bool(
                    all(
                        abs(val - sample_growth) <= BIOMASS_TOL
                        for val in (
                            float(a["flux"][biomass_col]),
                            float(b["flux"][biomass_col]),
                            float(karr_flux[biomass_col]),
                        )
                    )
                ),
            },
            "verdict": classify_hypothesis(a_vs_b["max_abs_diff"], closer["winner_by_l1"]),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2))

    status_lines = [
        "# H2 Two-Solve Probe",
        "",
        f"- Verdict: {out['comparisons']['verdict']}",
        f"- Command: `bin/oc-py scripts/probe_h2_two_solve.py`",
        f"- Biomass values: A={out['comparisons']['biomass_values']['A']:.15g}, B={out['comparisons']['biomass_values']['B']:.15g}, Karr={out['comparisons']['biomass_values']['Karr']:.15g}, growth={sample_growth:.15g}",
        f"- A vs B max abs diff: {out['comparisons']['a_vs_b']['max_abs_diff']:.15g}",
        f"- A vs Karr L1: {out['comparisons']['a_vs_karr']['l1']:.15g}",
        f"- B vs Karr L1: {out['comparisons']['b_vs_karr']['l1']:.15g}",
        f"- Better match to Karr by L1: {out['comparisons']['protocol_match_to_karr']['winner_by_l1']}",
        "",
        "## Self-audit",
        "",
        "| # | Criterion | Verified |",
        "|---|---|---|",
        "| 1 | Two-step protocol implemented (separate biomass-max then parsimony-max on biomass-fixed face) | [x] |",
        "| 2 | Both LP solves use swiglpk + V4-aligned options | [x] |",
        "| 3 | Biomass column bounds set to GLP_FX in second solve | [x] |",
        "| 4 | JSON includes A flux, B flux, Karr flux, all 3 comparisons | [x] |",
        "| 5 | INTENT + VERIFICATION blocks emitted | [ ] |",
    ]
    OUT_STATUS.write_text("\n".join(status_lines) + "\n")


if __name__ == "__main__":
    main()
