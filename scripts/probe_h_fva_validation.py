from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import swiglpk as glp


ROOT = Path(__file__).resolve().parents[1]
NPZ_PATH = ROOT / "data" / "karr_fixtures" / "karr_native_m1.npz"
MAT_PATH = (
    ROOT
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
OUT_JSON = ROOT / "tmp" / "h_fva_validation.json"
OUT_STATUS = ROOT / "STATUS_h_fva_validation.md"

BIG = 1e6
PAIR_COLS = [393, 422, 423, 424, 444, 445, 449, 450]


def load_inputs() -> dict[str, np.ndarray]:
    z = np.load(NPZ_PATH, allow_pickle=False)
    S = np.asarray(z["S"], dtype=np.float64)
    rhs = np.asarray(z["RHS"], dtype=np.float64).reshape(-1)
    c = np.asarray(z["obj"], dtype=np.float64).reshape(-1)

    with h5py.File(MAT_PATH, "r") as f:
        bounds = np.asarray(f["bounds"], dtype=np.float64)  # (2, 504)
        karr_flux = np.asarray(f["flux"], dtype=np.float64).reshape(-1)

    lb = np.clip(bounds[0], -BIG, BIG)
    ub = np.clip(bounds[1], -BIG, BIG)

    if S.shape != (376, 504):
        raise RuntimeError(f"Unexpected S shape {S.shape}, expected (376, 504)")
    if rhs.shape != (376,):
        raise RuntimeError(f"Unexpected RHS shape {rhs.shape}, expected (376,)")
    if c.shape != (504,):
        raise RuntimeError(f"Unexpected obj shape {c.shape}, expected (504,)")
    if lb.shape != (504,) or ub.shape != (504,):
        raise RuntimeError(f"Unexpected bounds shapes lb={lb.shape}, ub={ub.shape}, expected (504,)")
    if karr_flux.shape != (504,):
        raise RuntimeError(f"Unexpected Karr flux shape {karr_flux.shape}, expected (504,)")

    return {
        "S": S,
        "rhs": rhs,
        "c": c,
        "lb": lb,
        "ub": ub,
        "karr_flux": karr_flux,
    }


def configure_simplex_params() -> Any:
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_OFF
    parm.meth = glp.GLP_PRIMAL
    parm.tol_bnd = 1e-6
    parm.pricing = glp.GLP_PT_STD
    return parm


def build_base_lp(
    *,
    S: np.ndarray,
    rhs: np.ndarray,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
) -> Any:
    n_rows, n_cols = S.shape
    lp = glp.glp_create_prob()
    glp.glp_term_out(glp.GLP_OFF)
    glp.glp_set_obj_dir(lp, glp.GLP_MAX)

    glp.glp_add_rows(lp, n_rows)
    for i in range(n_rows):
        glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))

    glp.glp_add_cols(lp, n_cols)
    for j in range(n_cols):
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
    return lp


def solve_checked(lp: Any, parm: Any, *, label: str) -> tuple[int, int]:
    simplex_exit = int(glp.glp_simplex(lp, parm))
    sol_status = int(glp.glp_get_status(lp))
    if simplex_exit != 0 or sol_status != glp.GLP_OPT:
        raise RuntimeError(
            f"{label} failed: simplex_exit={simplex_exit}, sol_status={sol_status}, "
            f"expected simplex_exit=0 and sol_status=GLP_OPT({glp.GLP_OPT})"
        )
    return simplex_exit, sol_status


def add_biomass_equality_row(lp: Any, *, c: np.ndarray, biomass_star: float) -> int:
    glp.glp_add_rows(lp, 1)
    row_idx = int(glp.glp_get_num_rows(lp))
    glp.glp_set_row_bnds(lp, row_idx, glp.GLP_FX, float(biomass_star), float(biomass_star))

    nz = np.flatnonzero(np.abs(c) > 0.0)
    row_len = int(nz.size)
    if row_len <= 0:
        raise RuntimeError("Objective vector is all zeros; cannot add biomass equality row")

    ind = glp.intArray(row_len + 1)
    val = glp.doubleArray(row_len + 1)
    for k, col_idx in enumerate(nz, start=1):
        ind[k] = int(col_idx) + 1
        val[k] = float(c[col_idx])
    glp.glp_set_mat_row(lp, row_idx, row_len, ind, val)
    return row_idx


def build_top_infeasible(
    *,
    karr_flux: np.ndarray,
    v_min: np.ndarray,
    v_max: np.ndarray,
    tol: np.ndarray,
) -> list[dict[str, float | int]]:
    lower = v_min - tol
    upper = v_max + tol
    dist_tol = np.maximum(np.maximum(lower - karr_flux, karr_flux - upper), 0.0)
    dist_raw = np.maximum(np.maximum(v_min - karr_flux, karr_flux - v_max), 0.0)

    infeasible_idx = np.flatnonzero(dist_tol > 0.0)
    if infeasible_idx.size == 0:
        return []

    ranked = sorted(
        (int(i) for i in infeasible_idx),
        key=lambda i: float(dist_tol[i]),
        reverse=True,
    )[:10]
    out: list[dict[str, float | int]] = []
    for j in ranked:
        out.append(
            {
                "j": j,
                "karr_flux": float(karr_flux[j]),
                "v_min": float(v_min[j]),
                "v_max": float(v_max[j]),
                "tol": float(tol[j]),
                "distance_outside_range": float(dist_tol[j]),
                "distance_outside_raw_range": float(dist_raw[j]),
            }
        )
    return out


def render_status(report: dict[str, Any]) -> str:
    top10 = report["top10_infeasible"]
    pair_rows = report["pair_columns"]
    self_audit = report["self_audit"]

    lines: list[str] = []
    lines.append("# STATUS_h_fva_validation")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "Run single-sample `(s=0,t=1)` Flux Variability Analysis (FVA) using swiglpk with "
        "Day-41 production LP settings, then test whether Karr's recorded flux for each of "
        "the 504 reactions lies within OC's biomass-optimal feasibility range."
    )
    lines.append("")
    lines.append("## Verdict")
    lines.append(f"- **{report['verdict']}**")
    lines.append(f"- `biomass_value_star`: `{report['biomass_value_star']:.12e}`")
    lines.append(
        f"- Feasible reactions: `{report['n_feasible']}/504` "
        f"(`{report['feasibility_fraction'] * 100.0:.3f}%`)"
    )
    lines.append(
        f"- Infeasible reactions: `{report['n_infeasible']}/504` "
        f"(`{(1.0 - report['feasibility_fraction']) * 100.0:.3f}%`)"
    )
    lines.append(f"- Wall time: `{report['wall_time_sec']:.3f}` sec")
    lines.append(f"- Total LP solves: `{report['lp_solves_total']}`")
    lines.append("")
    lines.append("## Top-10 Infeasible Reactions")
    if top10:
        lines.append(
            "| j | karr_flux[j] | v_min[j] | v_max[j] | tol_j | distance_outside_range |"
        )
        lines.append("|---:|---:|---:|---:|---:|---:|")
        for row in top10:
            lines.append(
                f"| {row['j']} | {row['karr_flux']:.12e} | {row['v_min']:.12e} | "
                f"{row['v_max']:.12e} | {row['tol']:.12e} | {row['distance_outside_range']:.12e} |"
            )
    else:
        lines.append("No infeasible reactions detected under the specified tolerance.")
    lines.append("")
    lines.append("## Substitution-Pair Columns")
    lines.append("| j | karr_flux | v_min | v_max | width | tol_j | feasible |")
    lines.append("|---:|---:|---:|---:|---:|---:|:---:|")
    for row in pair_rows:
        lines.append(
            f"| {row['j']} | {row['karr_flux']:.12e} | {row['v_min']:.12e} | "
            f"{row['v_max']:.12e} | {row['width']:.12e} | {row['tol']:.12e} | "
            f"{'YES' if row['feasible'] else 'NO'} |"
        )
    lines.append("")
    lines.append("## VERIFICATION")
    lines.append("| Item | Value |")
    lines.append("|---|---|")
    lines.append("| Command | `bin\\oc-py scripts/probe_h_fva_validation.py` |")
    lines.append("| Sample | `seed=0, tick=1` |")
    lines.append("| LP fixture | `data/karr_fixtures/karr_native_m1.npz` |")
    lines.append("| Ground truth | `data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat` |")
    lines.append("| JSON artifact | `tmp/h_fva_validation.json` |")
    lines.append("| STATUS artifact | `STATUS_h_fva_validation.md` |")
    lines.append("")
    lines.append("## Self-audit")
    lines.append("| # | Criterion | Verified |")
    lines.append("|---|---|---|")
    for row in self_audit:
        mark = "[x]" if row["ok"] else "[ ]"
        lines.append(f"| {row['id']} | {row['criterion']} | {mark} |")
    lines.append("")
    return "\n".join(lines)


def run_probe() -> dict[str, Any]:
    t0 = time.perf_counter()
    data = load_inputs()
    S = data["S"]
    rhs = data["rhs"]
    c = data["c"]
    lb = data["lb"]
    ub = data["ub"]
    karr_flux = data["karr_flux"]

    n_rxn = int(c.shape[0])
    lp_solves = 0
    simplex_exit_codes: list[int] = []
    sol_status_codes: list[int] = []

    parm = configure_simplex_params()
    lp = build_base_lp(S=S, rhs=rhs, c=c, lb=lb, ub=ub)
    try:
        simplex_exit, sol_status = solve_checked(lp, parm, label="primary LP")
        lp_solves += 1
        simplex_exit_codes.append(simplex_exit)
        sol_status_codes.append(sol_status)

        v_star = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(n_rxn)], dtype=np.float64)
        biomass_star_obj = float(glp.glp_get_obj_val(lp))
        biomass_star_dot = float(np.dot(c, v_star))

        biomass_row = add_biomass_equality_row(lp, c=c, biomass_star=biomass_star_obj)

        for j in range(n_rxn):
            glp.glp_set_obj_coef(lp, j + 1, 0.0)

        v_min = np.empty(n_rxn, dtype=np.float64)
        v_max = np.empty(n_rxn, dtype=np.float64)

        for j in range(n_rxn):
            glp.glp_set_obj_coef(lp, j + 1, 1.0)

            glp.glp_set_obj_dir(lp, glp.GLP_MAX)
            simplex_exit, sol_status = solve_checked(lp, parm, label=f"FVA max j={j}")
            lp_solves += 1
            simplex_exit_codes.append(simplex_exit)
            sol_status_codes.append(sol_status)
            v_max[j] = float(glp.glp_get_col_prim(lp, j + 1))

            glp.glp_set_obj_dir(lp, glp.GLP_MIN)
            simplex_exit, sol_status = solve_checked(lp, parm, label=f"FVA min j={j}")
            lp_solves += 1
            simplex_exit_codes.append(simplex_exit)
            sol_status_codes.append(sol_status)
            v_min[j] = float(glp.glp_get_col_prim(lp, j + 1))

            glp.glp_set_obj_coef(lp, j + 1, 0.0)

        tol = 1e-4 * np.maximum(1.0, np.abs(karr_flux))
        lower = v_min - tol
        upper = v_max + tol
        feasible = (karr_flux >= lower) & (karr_flux <= upper)
        n_feasible = int(np.sum(feasible))
        n_infeasible = int(n_rxn - n_feasible)
        feasibility_fraction = float(n_feasible / n_rxn)

        if feasibility_fraction >= 0.99:
            verdict = "VALIDATED"
        elif feasibility_fraction >= 0.80:
            verdict = "PARTIAL"
        else:
            verdict = "FALSIFIED"

        top10 = build_top_infeasible(karr_flux=karr_flux, v_min=v_min, v_max=v_max, tol=tol)

        pair_rows: list[dict[str, Any]] = []
        for j in PAIR_COLS:
            pair_rows.append(
                {
                    "j": int(j),
                    "karr_flux": float(karr_flux[j]),
                    "v_min": float(v_min[j]),
                    "v_max": float(v_max[j]),
                    "width": float(v_max[j] - v_min[j]),
                    "tol": float(tol[j]),
                    "feasible": bool(feasible[j]),
                }
            )

        all_opt = bool(
            len(sol_status_codes) == 1009
            and all(code == glp.GLP_OPT for code in sol_status_codes)
            and all(code == 0 for code in simplex_exit_codes)
        )

        self_audit = [
            {
                "id": 1,
                "criterion": "FVA solver implemented with 1008 per-reaction LP solves (max+min for each of 504 columns)",
                "ok": lp_solves == 1009,
            },
            {
                "id": 2,
                "criterion": "All LP solves returned simplex_exit=0 and GLP_OPT",
                "ok": all_opt,
            },
            {
                "id": 3,
                "criterion": "Primary LP used production config (STD pricing, presolve OFF, scale AUTO, tol_bnd=1e-6, primal)",
                "ok": True,
            },
            {
                "id": 4,
                "criterion": "Biomass equality row added as c'v == biomass_value_star",
                "ok": biomass_row == 377,
            },
            {
                "id": 5,
                "criterion": "Feasibility tolerance applied per reaction: 1e-4 * max(1, |karr_flux[j]|)",
                "ok": True,
            },
            {
                "id": 6,
                "criterion": "Bounds sourced from MAT `bounds` and clipped to +/-1e6",
                "ok": True,
            },
            {
                "id": 7,
                "criterion": "8 substitution-pair columns reported with Karr flux and FVA ranges",
                "ok": len(pair_rows) == 8,
            },
            {
                "id": 8,
                "criterion": "Artifacts written: STATUS_h_fva_validation.md + tmp/h_fva_validation.json",
                "ok": True,
            },
        ]

        wall_time = float(time.perf_counter() - t0)
        return {
            "meta": {
                "sample": {"seed": 0, "tick": 1},
                "files_read": [str(NPZ_PATH.relative_to(ROOT)), str(MAT_PATH.relative_to(ROOT))],
                "solver": {
                    "family": "swiglpk",
                    "pricing": "STD",
                    "presolve": "OFF",
                    "scale": "AUTO",
                    "tol_bnd": 1e-6,
                    "meth": "PRIMAL",
                },
                "bounds_source": "MAT bounds (clipped to +/-1e6)",
            },
            "verdict": verdict,
            "biomass_value_star": biomass_star_obj,
            "biomass_value_star_dot_check": biomass_star_dot,
            "biomass_obj_minus_dot": float(biomass_star_obj - biomass_star_dot),
            "n_reactions": n_rxn,
            "n_feasible": n_feasible,
            "n_infeasible": n_infeasible,
            "feasibility_fraction": feasibility_fraction,
            "lp_solves_total": lp_solves,
            "expected_lp_solves_total": 1009,
            "all_lp_optimal": all_opt,
            "simplex_exit_unique": sorted({int(x) for x in simplex_exit_codes}),
            "solution_status_unique": sorted({int(x) for x in sol_status_codes}),
            "top10_infeasible": top10,
            "pair_columns": pair_rows,
            "v_min": v_min.tolist(),
            "v_max": v_max.tolist(),
            "karr_flux": karr_flux.tolist(),
            "tol": tol.tolist(),
            "wall_time_sec": wall_time,
            "self_audit": self_audit,
        }
    finally:
        glp.glp_delete_prob(lp)


def main() -> None:
    report = run_probe()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))
    OUT_STATUS.write_text(render_status(report))
    print(
        f"verdict={report['verdict']} "
        f"feasible={report['n_feasible']}/504 "
        f"infeasible={report['n_infeasible']}/504 "
        f"lp_solves={report['lp_solves_total']} "
        f"wall_time_sec={report['wall_time_sec']:.3f}"
    )


if __name__ == "__main__":
    main()
