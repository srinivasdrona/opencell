from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import swiglpk as glp


REPO_ROOT = Path(__file__).resolve().parents[1]
MAT_PATH = (
    REPO_ROOT
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
NPZ_PATH = REPO_ROOT / "data" / "karr_fixtures" / "karr_native_m1.npz"
OUT_PATH = REPO_ROOT / "tmp" / "h3_options_sweep.json"
STATUS_PATH = REPO_ROOT / "STATUS_h3.md"


METH_NAMES = {
    glp.GLP_PRIMAL: "PRIMAL",
    glp.GLP_DUAL: "DUAL",
    glp.GLP_DUALP: "DUALP",
}
PRESOLVE_NAMES = {
    glp.GLP_ON: "ON",
    glp.GLP_OFF: "OFF",
}
PRICING_NAMES = {
    glp.GLP_PT_STD: "STD",
    glp.GLP_PT_PSE: "PSE",
}
RTEST_NAMES = {
    glp.GLP_RT_STD: "STD",
    glp.GLP_RT_HAR: "HAR",
}
SCALE_FLAGS = {
    "NONE": None,
    "AUTO": glp.GLP_SF_AUTO,
    "GM": glp.GLP_SF_GM,
    "EQ": glp.GLP_SF_EQ,
    "2N": glp.GLP_SF_2N,
    "SKIP": glp.GLP_SF_SKIP,
}
SOLUTION_STATUS_NAMES = {
    glp.GLP_UNDEF: "UNDEF",
    glp.GLP_FEAS: "FEAS",
    glp.GLP_INFEAS: "INFEAS",
    glp.GLP_NOFEAS: "NOFEAS",
    glp.GLP_OPT: "OPT",
    glp.GLP_UNBND: "UNBND",
}

VARIANTS = [
    {
        "id": "V0",
        "label": "current V4 baseline",
        "presolve": glp.GLP_OFF,
        "meth": glp.GLP_PRIMAL,
        "pricing": None,
        "r_test": None,
        "tol_bnd": 1e-6,
        "scale": "AUTO",
    },
    {
        "id": "V1",
        "label": "presolve on tighter tol",
        "presolve": glp.GLP_ON,
        "meth": glp.GLP_PRIMAL,
        "pricing": None,
        "r_test": None,
        "tol_bnd": 1e-7,
        "scale": "AUTO",
    },
    {
        "id": "V2",
        "label": "dual simplex",
        "presolve": glp.GLP_OFF,
        "meth": glp.GLP_DUAL,
        "pricing": None,
        "r_test": None,
        "tol_bnd": 1e-6,
        "scale": "AUTO",
    },
    {
        "id": "V3",
        "label": "std pricing",
        "presolve": glp.GLP_OFF,
        "meth": glp.GLP_PRIMAL,
        "pricing": glp.GLP_PT_STD,
        "r_test": None,
        "tol_bnd": 1e-6,
        "scale": "AUTO",
    },
    {
        "id": "V4",
        "label": "std ratio test",
        "presolve": glp.GLP_OFF,
        "meth": glp.GLP_PRIMAL,
        "pricing": None,
        "r_test": glp.GLP_RT_STD,
        "tol_bnd": 1e-6,
        "scale": "AUTO",
    },
    {
        "id": "V5",
        "label": "looser tol",
        "presolve": glp.GLP_OFF,
        "meth": glp.GLP_PRIMAL,
        "pricing": None,
        "r_test": None,
        "tol_bnd": 1e-5,
        "scale": "AUTO",
    },
    {
        "id": "V6",
        "label": "no scaling",
        "presolve": glp.GLP_OFF,
        "meth": glp.GLP_PRIMAL,
        "pricing": None,
        "r_test": None,
        "tol_bnd": 1e-6,
        "scale": "NONE",
    },
    {
        "id": "V7",
        "label": "geometric mean scaling",
        "presolve": glp.GLP_OFF,
        "meth": glp.GLP_PRIMAL,
        "pricing": None,
        "r_test": None,
        "tol_bnd": 1e-6,
        "scale": "GM",
    },
]


def load_inputs() -> dict:
    with h5py.File(MAT_PATH, "r") as f:
        bounds = np.asarray(f["bounds"], dtype=np.float64)
        karr_flux = np.asarray(f["flux"], dtype=np.float64).reshape(-1)

    z = np.load(NPZ_PATH)
    S = np.asarray(z["S"], dtype=np.float64)
    rhs = np.asarray(z["RHS"], dtype=np.float64).reshape(-1)
    obj = np.asarray(z["obj"], dtype=np.float64).reshape(-1)

    finite_bounds = bounds[np.isfinite(bounds)]
    finite_karr = karr_flux[np.isfinite(karr_flux)]
    big = float(
        max(
            1e6,
            np.max(np.abs(finite_bounds)) if finite_bounds.size else 0.0,
            np.max(np.abs(finite_karr)) if finite_karr.size else 0.0,
        )
    )
    lb = np.where(np.isfinite(bounds[0]), bounds[0], -big)
    ub = np.where(np.isfinite(bounds[1]), bounds[1], big)

    return {
        "S": S,
        "rhs": rhs,
        "obj": obj,
        "lb": lb,
        "ub": ub,
        "karr_flux": karr_flux,
        "big": big,
    }


def build_lp(S: np.ndarray, rhs: np.ndarray, obj: np.ndarray, lb: np.ndarray, ub: np.ndarray):
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
        glp.glp_set_obj_coef(lp, j + 1, float(obj[j]))

    rows, cols = np.nonzero(S)
    nnz = int(rows.size)
    ia = glp.intArray(nnz + 1)
    ja = glp.intArray(nnz + 1)
    ar = glp.doubleArray(nnz + 1)
    for k, (row, col) in enumerate(zip(rows, cols, strict=True), start=1):
        ia[k] = int(row) + 1
        ja[k] = int(col) + 1
        ar[k] = float(S[row, col])
    glp.glp_load_matrix(lp, nnz, ia, ja, ar)
    return lp


def format_top_fluxes(v: np.ndarray, limit: int = 5) -> list[dict]:
    order = np.argsort(np.abs(v))[::-1][:limit]
    return [
        {
            "index": int(idx),
            "value": float(v[idx]),
            "abs": float(abs(v[idx])),
        }
        for idx in order
    ]


def solve_variant(lp, variant: dict, lb: np.ndarray, ub: np.ndarray, karr_flux: np.ndarray) -> tuple[dict, np.ndarray | None]:
    glp.glp_unscale_prob(lp)
    scale_flag = SCALE_FLAGS[variant["scale"]]
    if scale_flag is not None:
        glp.glp_scale_prob(lp, scale_flag)

    # Reset the basis each time so the sweep isolates options, not leftover state.
    glp.glp_adv_basis(lp, 0)
    glp.glp_set_it_cnt(lp, 0)

    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = variant["presolve"]
    parm.meth = variant["meth"]
    parm.tol_bnd = float(variant["tol_bnd"])
    if variant["pricing"] is not None:
        parm.pricing = variant["pricing"]
    if variant["r_test"] is not None:
        parm.r_test = variant["r_test"]

    simplex_exit = int(glp.glp_simplex(lp, parm))
    solution_status = int(glp.glp_get_status(lp))
    iter_count = int(glp.glp_get_it_cnt(lp))

    solve_status = (
        "OPT"
        if simplex_exit == 0 and solution_status == glp.GLP_OPT
        else f"FAILED: simplex={simplex_exit}, solution={SOLUTION_STATUS_NAMES.get(solution_status, str(solution_status))}"
    )

    record = {
        "variant": variant["id"],
        "label": variant["label"],
        "options": {
            "presolve": PRESOLVE_NAMES[variant["presolve"]],
            "meth": METH_NAMES[variant["meth"]],
            "pricing": PRICING_NAMES[parm.pricing],
            "r_test": RTEST_NAMES[parm.r_test],
            "tol_bnd": float(variant["tol_bnd"]),
            "scale": variant["scale"],
        },
        "simplex_exit_code": simplex_exit,
        "solution_status_code": solution_status,
        "solution_status": solve_status,
        "iteration_count": iter_count,
        "scaling_reset_applied": True,
        "basis_reset_applied": True,
    }

    if simplex_exit != 0 or solution_status != glp.GLP_OPT:
        record.update(
            {
                "objective": None,
                "flux": None,
                "flux_summary": None,
                "l1_vs_v0": None,
                "l1_vs_karr": None,
            }
        )
        return record, None

    v = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(lb.size)], dtype=np.float64)
    v = np.clip(v, lb, ub)
    objective = float(glp.glp_get_obj_val(lp))
    l1_vs_karr = float(np.abs(v - karr_flux).sum())
    record.update(
        {
            "objective": objective,
            "flux": [float(x) for x in v],
            "flux_summary": {
                "sum_abs": float(np.abs(v).sum()),
                "nnz": int((np.abs(v) > 1e-9).sum()),
                "top5_largest_abs": format_top_fluxes(v),
            },
            "l1_vs_v0": None,
            "l1_vs_karr": l1_vs_karr,
        }
    )
    return record, v


def build_pairwise_matrix(order: list[str], fluxes: dict[str, np.ndarray | None]) -> list[list[float | None]]:
    matrix: list[list[float | None]] = []
    for left in order:
        row: list[float | None] = []
        for right in order:
            if fluxes[left] is None or fluxes[right] is None:
                row.append(None)
            else:
                row.append(float(np.abs(fluxes[left] - fluxes[right]).sum()))
        matrix.append(row)
    return matrix


def write_status_md(data: dict) -> None:
    summary = data["summary"]
    lines = [
        "# H3 Options Sweep",
        "",
        "## Outcome",
        f"- Hypothesis check: {summary['hypothesis_outcome']}",
        f"- Max pairwise vertex L1: {summary['max_pairwise_l1']:.6g}" if summary["max_pairwise_l1"] is not None else "- Max pairwise vertex L1: n/a",
        f"- Max vertex-vs-V0 L1: {summary['max_vertex_vs_v0_l1']:.6g}" if summary["max_vertex_vs_v0_l1"] is not None else "- Max vertex-vs-V0 L1: n/a",
        f"- V0 vs Karr L1: {summary['v0_l1_vs_karr']:.6g}" if summary["v0_l1_vs_karr"] is not None else "- V0 vs Karr L1: n/a",
        f"- Best variant vs Karr: {summary['best_variant_vs_karr']['variant']} ({summary['best_variant_vs_karr']['l1']:.6g})" if summary["best_variant_vs_karr"] is not None else "- Best variant vs Karr: n/a",
        f"- Variants beating V0 on Karr distance: {', '.join(summary['variants_beating_v0']) if summary['variants_beating_v0'] else 'none'}",
        "",
        "## Self-audit",
        "| # | Criterion | Verified |",
        "|---|---|---|",
        f"| 1 | All 8 variants attempted | {'[x]' if summary['all_variants_attempted'] else '[ ]'} |",
        f"| 2 | Each variant's solution_status checked | {'[x]' if summary['solution_status_checked'] else '[ ]'} |",
        f"| 3 | Scaling reset between variants (glp_unscale_prob or fresh LP) | {'[x]' if summary['scaling_reset_verified'] else '[ ]'} |",
        f"| 4 | Pairwise 8x8 distance matrix present | {'[x]' if summary['pairwise_matrix_present'] else '[ ]'} |",
        "| 5 | INTENT + VERIFICATION emitted | [ ] |",
        "",
        "## Files",
        f"- JSON artifact: `{OUT_PATH.relative_to(REPO_ROOT)}`",
        f"- Probe script: `scripts/probe_h3_options_sweep.py`",
    ]
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> int:
    inputs = load_inputs()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lp = build_lp(inputs["S"], inputs["rhs"], inputs["obj"], inputs["lb"], inputs["ub"])
    try:
        records: list[dict] = []
        fluxes: dict[str, np.ndarray | None] = {}
        for variant in VARIANTS:
            record, flux = solve_variant(
                lp,
                variant=variant,
                lb=inputs["lb"],
                ub=inputs["ub"],
                karr_flux=inputs["karr_flux"],
            )
            fluxes[variant["id"]] = flux
            records.append(record)

        v0_flux = fluxes["V0"]
        if v0_flux is not None:
            for record in records:
                flux = fluxes[record["variant"]]
                record["l1_vs_v0"] = float(np.abs(flux - v0_flux).sum()) if flux is not None else None

        order = [variant["id"] for variant in VARIANTS]
        pairwise_matrix = build_pairwise_matrix(order, fluxes)
        pairwise_values = [
            cell
            for i, row in enumerate(pairwise_matrix)
            for j, cell in enumerate(row)
            if i != j and cell is not None
        ]
        valid_karr = [
            {"variant": record["variant"], "l1": record["l1_vs_karr"]}
            for record in records
            if record["l1_vs_karr"] is not None
        ]
        best_variant_vs_karr = min(valid_karr, key=lambda item: item["l1"]) if valid_karr else None
        v0_record = next(record for record in records if record["variant"] == "V0")
        variants_beating_v0 = [
            record["variant"]
            for record in records
            if record["variant"] != "V0"
            and record["l1_vs_karr"] is not None
            and v0_record["l1_vs_karr"] is not None
            and record["l1_vs_karr"] < v0_record["l1_vs_karr"]
        ]

        max_pairwise_l1 = max(pairwise_values) if pairwise_values else None
        if best_variant_vs_karr is not None and best_variant_vs_karr["l1"] < 1e3:
            hypothesis_outcome = "one variant reached Karr within 1e3"
        elif max_pairwise_l1 is not None and max_pairwise_l1 < 1e3:
            hypothesis_outcome = "all variants stayed within 1e3 pairwise; H3 falsified"
        elif max_pairwise_l1 is not None and max_pairwise_l1 >= 1e6:
            hypothesis_outcome = "variants spread across 1e6-scale vertices; options are a major driver"
        else:
            hypothesis_outcome = "variants moved, but not enough to hit the 1e3 or 1e6 thresholds"

        data = {
            "sample": {
                "seed": 0,
                "tick": 1,
                "mat_path": str(MAT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
                "npz_path": str(NPZ_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
                "infinity_substitute_big": inputs["big"],
            },
            "variants": records,
            "pairwise_l1_matrix": {
                "order": order,
                "matrix": pairwise_matrix,
            },
            "summary": {
                "max_pairwise_l1": max_pairwise_l1,
                "max_vertex_vs_v0_l1": max(
                    (record["l1_vs_v0"] for record in records if record["l1_vs_v0"] is not None),
                    default=None,
                ),
                "max_vertex_vs_karr_l1": max(
                    (record["l1_vs_karr"] for record in records if record["l1_vs_karr"] is not None),
                    default=None,
                ),
                "v0_l1_vs_karr": v0_record["l1_vs_karr"],
                "best_variant_vs_karr": best_variant_vs_karr,
                "variants_beating_v0": variants_beating_v0,
                "any_variant_beats_v0": bool(variants_beating_v0),
                "all_variants_attempted": len(records) == 8,
                "solution_status_checked": all(record["solution_status"] is not None for record in records),
                "scaling_reset_verified": all(record["scaling_reset_applied"] for record in records),
                "pairwise_matrix_present": len(pairwise_matrix) == 8 and all(len(row) == 8 for row in pairwise_matrix),
                "hypothesis_outcome": hypothesis_outcome,
            },
        }
        OUT_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="ascii")
        write_status_md(data)

        print(f"Wrote {OUT_PATH}")
        print(f"Outcome: {hypothesis_outcome}")
        if best_variant_vs_karr is not None:
            print(
                "Best variant vs Karr: "
                f"{best_variant_vs_karr['variant']} L1={best_variant_vs_karr['l1']:.6g}"
            )
        return 0
    finally:
        glp.glp_delete_prob(lp)


if __name__ == "__main__":
    raise SystemExit(main())
