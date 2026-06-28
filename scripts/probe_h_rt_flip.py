from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import h5py
import numpy as np
import swiglpk as glp

from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = (
    REPO_ROOT
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
FIXTURE_PATH = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
NPZ_PATH = REPO_ROOT / "data" / "karr_fixtures" / "karr_native_m1.npz"
OUT_JSON = REPO_ROOT / "tmp" / "h_rt_flip.json"
OUT_STATUS = REPO_ROOT / "STATUS_h_rt_flip.md"

PAIR_COLS = [
    ("HDCA", 393),
    ("OCDCEA", 422),
    ("PHE", 423),
    ("PhePhe", 424),
    ("TRIOLEIN", 444),
    ("TRIPALMITIN", 445),
    ("TRP", 449),
    ("TrpTrp", 450),
]


class _DetRng:
    def stochastic_round(self, values: np.ndarray) -> np.ndarray:
        return np.rint(np.asarray(values, dtype=np.float64)).astype(np.int64)


def _load_inputs() -> dict[str, np.ndarray | float | KarrWritebackFixture]:
    with h5py.File(SAMPLE_PATH, "r") as f:
        karr_flux = np.asarray(f["flux"], dtype=np.float64).reshape(-1)
        karr_growth = float(np.asarray(f["growth"], dtype=np.float64).reshape(-1)[0])
        pre_sub = np.asarray(f["pre_sub"], dtype=np.float64).T
        karr_delta = np.asarray(f["delta"], dtype=np.float64).T
        bounds = np.asarray(f["bounds"], dtype=np.float64).T

    z = np.load(NPZ_PATH, allow_pickle=False)
    S = np.asarray(z["S"], dtype=np.float64)
    rhs = np.asarray(z["RHS"], dtype=np.float64).reshape(-1)
    obj = np.asarray(z["obj"], dtype=np.float64).reshape(-1)

    # Match prior probes and production clipping behavior around infinities.
    big = 1e6
    lb = np.clip(bounds[:, 0], -big, big)
    ub = np.clip(bounds[:, 1], -big, big)

    fixture = KarrWritebackFixture.from_mat(FIXTURE_PATH)
    return {
        "S": S,
        "rhs": rhs,
        "obj": obj,
        "lb": lb,
        "ub": ub,
        "karr_flux": karr_flux,
        "karr_growth": karr_growth,
        "pre_sub": pre_sub,
        "karr_delta": karr_delta,
        "fixture": fixture,
    }


def _build_lp(
    *,
    S: np.ndarray,
    rhs: np.ndarray,
    obj: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
) -> glp.glp_prob:
    n_rows, n_cols = S.shape
    lp = glp.glp_create_prob()
    glp.glp_set_obj_dir(lp, glp.GLP_MAX)
    glp.glp_add_rows(lp, n_rows)
    for i in range(n_rows):
        glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))

    glp.glp_add_cols(lp, n_cols)
    for j in range(n_cols):
        lo = float(lb[j])
        hi = float(ub[j])
        if lo == hi:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lo, hi)
        else:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lo, hi)
        glp.glp_set_obj_coef(lp, j + 1, float(obj[j]))

    rows, cols = np.nonzero(S)
    nnz = int(rows.size)
    ia = glp.intArray(nnz + 1)
    ja = glp.intArray(nnz + 1)
    ar = glp.doubleArray(nnz + 1)
    for k in range(nnz):
        ia[k + 1] = int(rows[k]) + 1
        ja[k + 1] = int(cols[k]) + 1
        ar[k + 1] = float(S[rows[k], cols[k]])
    glp.glp_load_matrix(lp, nnz, ia, ja, ar)
    return lp


def _solve_variant(
    *,
    name: str,
    r_test: int,
    S: np.ndarray,
    rhs: np.ndarray,
    obj: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
) -> tuple[dict[str, object], np.ndarray]:
    lp = _build_lp(S=S, rhs=rhs, obj=obj, lb=lb, ub=ub)
    try:
        glp.glp_scale_prob(lp, glp.GLP_SF_AUTO)
        glp.glp_adv_basis(lp, 0)

        parm = glp.glp_smcp()
        glp.glp_init_smcp(parm)
        parm.msg_lev = glp.GLP_MSG_OFF
        parm.presolve = glp.GLP_OFF
        parm.meth = glp.GLP_PRIMAL
        parm.pricing = glp.GLP_PT_STD
        parm.r_test = int(r_test)
        parm.tol_bnd = 1e-6

        simplex_status = int(glp.glp_simplex(lp, parm))
        sol_status = int(glp.glp_get_status(lp))
        if simplex_status != 0 or sol_status != glp.GLP_OPT:
            raise RuntimeError(
                f"{name}: GLPK solve failed (simplex={simplex_status}, sol_status={sol_status})"
            )

        flux = np.array(
            [glp.glp_get_col_prim(lp, j + 1) for j in range(obj.size)], dtype=np.float64
        )
        flux = np.clip(flux, lb, ub)
        record = {
            "name": name,
            "solver_options": {
                "presolve": "GLP_OFF",
                "meth": "GLP_PRIMAL",
                "pricing": "GLP_PT_STD",
                "r_test": "GLP_RT_FLIP" if r_test == glp.GLP_RT_FLIP else "GLP_RT_HAR",
                "tol_bnd": 1e-6,
                "scale": "GLP_SF_AUTO",
            },
            "simplex_status": simplex_status,
            "solution_status": sol_status,
            "objective": float(glp.glp_get_obj_val(lp)),
        }
        return record, flux
    finally:
        glp.glp_delete_prob(lp)


def _rel_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom


def _variant_metrics(
    *,
    record: dict[str, object],
    flux: np.ndarray,
    karr_flux: np.ndarray,
    karr_delta: np.ndarray,
    pre_sub: np.ndarray,
    fixture: KarrWritebackFixture,
    biomass_col: int,
) -> dict[str, object]:
    growth = float(flux[biomass_col])
    rng = _DetRng()
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(),
        v_504=flux,
        growth_per_s=growth,
        fixture=fixture,
        rng=rng,
        step_size_sec=fixture.step_size_sec,
    )
    delta_i64 = delta.astype(np.int64)
    karr_delta_i64 = np.rint(karr_delta).astype(np.int64)

    ext_idx = fixture.fba_idx_external
    return {
        **record,
        "biomass_growth_per_s": growth,
        "full_flux_l1_vs_karr": float(np.abs(flux - karr_flux).sum()),
        "external_exchange_flux_l1_vs_karr": float(
            np.abs(flux[ext_idx] - karr_flux[ext_idx]).sum()
        ),
        "writeback_delta_l1_vs_karr_recorded": int(np.abs(delta_i64 - karr_delta_i64).sum()),
        "pair_flux": {name: float(flux[col]) for name, col in PAIR_COLS},
    }


def _pair_rows(
    *,
    karr_flux: np.ndarray,
    prod_pair_flux: Mapping[str, float],
    flip_pair_flux: Mapping[str, float],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for name, col in PAIR_COLS:
        karr_v = float(karr_flux[col])
        prod_v = float(prod_pair_flux[name])
        flip_v = float(flip_pair_flux[name])
        rows.append(
            {
                "name": name,
                "col": col,
                "karr": karr_v,
                "v_prod": prod_v,
                "v_flip": flip_v,
                "abs_diff_prod_vs_karr": abs(prod_v - karr_v),
                "abs_diff_flip_vs_karr": abs(flip_v - karr_v),
            }
        )
    return rows


def _write_status(results: dict[str, object]) -> None:
    v_prod = results["variants"]["V_prod"]
    v_flip = results["variants"]["V_flip"]
    checks = results["acceptance_checks"]
    pair_rows = results["pair_columns"]

    def fmt_f(x: float) -> str:
        return f"{x:.9e}"

    def fmt_i(x: int) -> str:
        return f"{x:d}"

    lines = [
        "# STATUS_h_rt_flip",
        "",
        "## INTENT",
        "Run a focused two-variant GLPK probe at sample (s=0, t=1) with LP",
        "construction matching `opencell/m1/karr_metabolism.py::_solve_fba_glpk`,",
        "isolating only `parm.r_test` (`HAR` vs `FLIP`), then compare flux and",
        "writeback deltas against Karr ground truth.",
        "",
        "## Headline",
        "",
        "| Variant | objective | full_flux_L1_vs_Karr | ext_flux_L1_vs_Karr | writeback_delta_L1_vs_Karr |",
        "|---|---:|---:|---:|---:|",
        (
            f"| V_prod (r_test=GLP_RT_HAR) | {fmt_f(v_prod['objective'])} | "
            f"{fmt_f(v_prod['full_flux_l1_vs_karr'])} | "
            f"{fmt_f(v_prod['external_exchange_flux_l1_vs_karr'])} | "
            f"{fmt_i(v_prod['writeback_delta_l1_vs_karr_recorded'])} |"
        ),
        (
            f"| V_flip (r_test=GLP_RT_FLIP) | {fmt_f(v_flip['objective'])} | "
            f"{fmt_f(v_flip['full_flux_l1_vs_karr'])} | "
            f"{fmt_f(v_flip['external_exchange_flux_l1_vs_karr'])} | "
            f"{fmt_i(v_flip['writeback_delta_l1_vs_karr_recorded'])} |"
        ),
        "",
        "## Pair Columns (Karr vs V_prod vs V_flip)",
        "",
        "| name | col | Karr | V_prod | V_flip |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in pair_rows:
        lines.append(
            f"| {row['name']} | {row['col']} | {fmt_f(row['karr'])} | "
            f"{fmt_f(row['v_prod'])} | {fmt_f(row['v_flip'])} |"
        )

    lines.extend(
        [
            "",
            "## Conclusion",
            (
                "V_flip closed the writeback gap below 1000 L1: "
                f"{'YES' if checks['v_flip_writeback_below_1000'] else 'NO'} "
                f"(V_flip={v_flip['writeback_delta_l1_vs_karr_recorded']})."
            ),
            (
                "Objective agreement V_prod vs V_flip (relative diff <= 1e-5): "
                f"{'YES' if checks['objectives_match_within_1e_5_rel'] else 'NO'} "
                f"(rel_diff={results['objective_relative_diff']:.3e})."
            ),
            "",
            "## VERIFICATION",
            "| Item | Value |",
            "|---|---|",
            "| Command | `bin/oc-py scripts/probe_h_rt_flip.py` |",
            "| Sample | seed=0, tick=1 |",
            "| LP fixture | `data/karr_fixtures/karr_native_m1.npz` |",
            "| Ground truth | `data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat` |",
            "| Writeback fixture | `data/karr_fixtures/per_process/Metabolism_flat.mat` |",
            "| JSON artifact | `tmp/h_rt_flip.json` |",
            "| STATUS artifact | `STATUS_h_rt_flip.md` |",
            "",
            "## Self-audit",
            "| # | Criterion | Verified |",
            "|---|---|---|",
            "| 1 | Only two variants run (HAR baseline and FLIP test) | "
            f"{'[x]' if checks['only_two_variants'] else '[ ]'} |",
            "| 2 | V_prod writeback delta near expected ~14517 sanity point | "
            f"{'[x]' if checks['v_prod_writeback_near_14517'] else '[ ]'} |",
            "| 3 | V_flip explicitly sets `parm.r_test = GLP_RT_FLIP` | "
            f"{'[x]' if checks['v_flip_uses_glp_rt_flip'] else '[ ]'} |",
            "| 4 | Objectives match within 1e-5 relative | "
            f"{'[x]' if checks['objectives_match_within_1e_5_rel'] else '[ ]'} |",
            "| 5 | Deterministic writeback RNG uses `np.rint` | "
            f"{'[x]' if checks['deterministic_rng_is_rint'] else '[ ]'} |",
            "| 6 | Pair-column table includes all 8 requested columns | "
            f"{'[x]' if checks['pair_columns_complete'] else '[ ]'} |",
            "| 7 | JSON artifact written to `tmp/h_rt_flip.json` | "
            f"{'[x]' if checks['json_written'] else '[ ]'} |",
            "| 8 | INTENT + VERIFICATION blocks present in this status file | [x] |",
        ]
    )
    OUT_STATUS.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> int:
    inputs = _load_inputs()
    S = inputs["S"]
    rhs = inputs["rhs"]
    obj = inputs["obj"]
    lb = inputs["lb"]
    ub = inputs["ub"]
    karr_flux = inputs["karr_flux"]
    karr_growth = float(inputs["karr_growth"])
    pre_sub = inputs["pre_sub"]
    karr_delta = inputs["karr_delta"]
    fixture = inputs["fixture"]

    biomass_col = int(np.argmax(np.abs(obj)))
    if not hasattr(glp, "GLP_RT_FLIP"):
        raise RuntimeError("swiglpk build does not expose GLP_RT_FLIP")

    rec_prod, flux_prod = _solve_variant(
        name="V_prod",
        r_test=glp.GLP_RT_HAR,
        S=S,
        rhs=rhs,
        obj=obj,
        lb=lb,
        ub=ub,
    )
    rec_flip, flux_flip = _solve_variant(
        name="V_flip",
        r_test=glp.GLP_RT_FLIP,
        S=S,
        rhs=rhs,
        obj=obj,
        lb=lb,
        ub=ub,
    )

    met_prod = _variant_metrics(
        record=rec_prod,
        flux=flux_prod,
        karr_flux=karr_flux,
        karr_delta=karr_delta,
        pre_sub=pre_sub,
        fixture=fixture,
        biomass_col=biomass_col,
    )
    met_flip = _variant_metrics(
        record=rec_flip,
        flux=flux_flip,
        karr_flux=karr_flux,
        karr_delta=karr_delta,
        pre_sub=pre_sub,
        fixture=fixture,
        biomass_col=biomass_col,
    )

    pair_rows = _pair_rows(
        karr_flux=karr_flux,
        prod_pair_flux=met_prod["pair_flux"],
        flip_pair_flux=met_flip["pair_flux"],
    )

    obj_rel_diff = _rel_diff(float(met_prod["objective"]), float(met_flip["objective"]))
    checks = {
        "only_two_variants": True,
        "v_prod_writeback_near_14517": abs(
            int(met_prod["writeback_delta_l1_vs_karr_recorded"]) - 14517
        )
        <= 250,
        "v_flip_uses_glp_rt_flip": (
            met_flip["solver_options"]["r_test"] == "GLP_RT_FLIP"
        ),
        "objectives_match_within_1e_5_rel": obj_rel_diff <= 1e-5,
        "v_flip_writeback_below_1000": (
            int(met_flip["writeback_delta_l1_vs_karr_recorded"]) < 1000
        ),
        "deterministic_rng_is_rint": True,
        "pair_columns_complete": len(pair_rows) == 8,
        "json_written": True,
    }

    out = {
        "sample": {
            "seed": 0,
            "tick": 1,
            "biomass_col": biomass_col,
            "karr_growth_per_s": karr_growth,
            "files": {
                "lp_fixture": str(NPZ_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
                "ground_truth": str(SAMPLE_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
                "writeback_fixture": str(FIXTURE_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            },
        },
        "variants": {
            "V_prod": met_prod,
            "V_flip": met_flip,
        },
        "objective_relative_diff": obj_rel_diff,
        "pair_columns": pair_rows,
        "acceptance_checks": checks,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n", encoding="ascii")
    _write_status(out)

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_STATUS}")
    print(
        "writeback_delta_L1: "
        f"V_prod={met_prod['writeback_delta_l1_vs_karr_recorded']}, "
        f"V_flip={met_flip['writeback_delta_l1_vs_karr_recorded']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
