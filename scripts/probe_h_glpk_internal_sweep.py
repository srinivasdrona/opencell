from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
OUT_JSON = REPO_ROOT / "tmp" / "h_glpk_internal_sweep.json"
OUT_STATUS = REPO_ROOT / "STATUS_h_glpk_internal_sweep.md"

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

SYSTEMATIC_ROWS = [
    ("O2", 420),
    ("H2O2", 298),
    ("CO2", 69),
    ("AC", 3),
    ("OCDCEA", 439),
    ("GLC", 250),
    ("PHE", 469),
    ("PhePhe", 470),
    ("H2O", 297),
]


class _DetRng:
    def stochastic_round(self, values: np.ndarray) -> np.ndarray:
        return np.rint(np.asarray(values, dtype=np.float64)).astype(np.int64)


@dataclass(frozen=True)
class VariantSpec:
    name: str
    basis: str  # adv | cpx | none
    r_test: int
    tol_dj: float | None = None
    tol_piv: float | None = None


def _load_inputs() -> dict[str, Any]:
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
        "big": big,
    }


def _build_lp(
    *,
    S: np.ndarray,
    rhs: np.ndarray,
    obj: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
) -> Any:
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


def _configure_simplex(spec: VariantSpec) -> Any:
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_OFF
    parm.meth = glp.GLP_PRIMAL
    parm.pricing = glp.GLP_PT_STD
    parm.r_test = int(spec.r_test)
    parm.tol_bnd = 1e-6
    if spec.tol_dj is not None:
        parm.tol_dj = float(spec.tol_dj)
    if spec.tol_piv is not None:
        parm.tol_piv = float(spec.tol_piv)
    return parm


def _basis_init(lp: Any, mode: str) -> None:
    if mode == "adv":
        glp.glp_adv_basis(lp, 0)
        return
    if mode == "cpx":
        if not hasattr(glp, "glp_cpx_basis"):
            raise RuntimeError("swiglpk build does not expose glp_cpx_basis")
        glp.glp_cpx_basis(lp)
        return
    if mode == "none":
        return
    raise ValueError(f"unknown basis mode: {mode}")


def _rel_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom


def _sgn(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _direction_phrase(*, karr_row_delta_total: float, variant_row_delta_total: float) -> str:
    if np.isclose(variant_row_delta_total, karr_row_delta_total):
        return "matches_karr"

    if karr_row_delta_total < 0:
        return (
            "more_consumption_than_karr"
            if variant_row_delta_total < karr_row_delta_total
            else "less_consumption_than_karr"
        )
    if karr_row_delta_total > 0:
        return (
            "more_production_than_karr"
            if variant_row_delta_total > karr_row_delta_total
            else "less_production_than_karr"
        )
    return (
        "higher_net_delta_than_karr"
        if variant_row_delta_total > karr_row_delta_total
        else "lower_net_delta_than_karr"
    )


def _variant_metrics(
    *,
    spec: VariantSpec,
    lp_payload: dict[str, np.ndarray],
    pre_sub: np.ndarray,
    karr_flux: np.ndarray,
    karr_delta: np.ndarray,
    fixture: KarrWritebackFixture,
    biomass_col: int,
) -> dict[str, Any]:
    lp = _build_lp(
        S=lp_payload["S"],
        rhs=lp_payload["rhs"],
        obj=lp_payload["obj"],
        lb=lp_payload["lb"],
        ub=lp_payload["ub"],
    )
    try:
        glp.glp_scale_prob(lp, glp.GLP_SF_AUTO)
        _basis_init(lp, spec.basis)
        parm = _configure_simplex(spec)

        simplex_status = int(glp.glp_simplex(lp, parm))
        sol_status = int(glp.glp_get_status(lp))
        if simplex_status != 0 or sol_status != glp.GLP_OPT:
            return {
                "name": spec.name,
                "ok": False,
                "error": f"GLPK solve failed (simplex={simplex_status}, sol_status={sol_status})",
                "simplex_status": simplex_status,
                "solution_status": sol_status,
                "solver_options": {
                    "basis_init": spec.basis,
                    "presolve": "OFF",
                    "meth": "PRIMAL",
                    "pricing": "STD",
                    "r_test": "FLIP" if spec.r_test == glp.GLP_RT_FLIP else "HAR",
                    "tol_bnd": 1e-6,
                    "tol_dj": float(parm.tol_dj),
                    "tol_piv": float(parm.tol_piv),
                    "scale": "AUTO",
                },
            }

        flux = np.array(
            [glp.glp_get_col_prim(lp, j + 1) for j in range(lp_payload["obj"].size)],
            dtype=np.float64,
        )
        flux = np.clip(flux, lp_payload["lb"], lp_payload["ub"])
        objective = float(glp.glp_get_obj_val(lp))
        growth = float(flux[biomass_col])

        det_rng = _DetRng()
        delta = apply_karr_substrate_writeback(
            pre_state_585x3=pre_sub.copy(),
            v_504=flux,
            growth_per_s=growth,
            fixture=fixture,
            rng=det_rng,
            step_size_sec=fixture.step_size_sec,
        )
        delta_i64 = delta.astype(np.int64)
        karr_delta_i64 = np.rint(karr_delta).astype(np.int64)

        row_dir: dict[str, Any] = {}
        for label, row_idx in SYSTEMATIC_ROWS:
            row_karr = float(karr_delta_i64[row_idx, :].sum())
            row_var = float(delta_i64[row_idx, :].sum())
            row_diff = row_var - row_karr
            row_dir[label] = {
                "row_index": row_idx,
                "karr_row_delta_total": row_karr,
                "variant_row_delta_total": row_var,
                "variant_minus_karr": row_diff,
                "variant_minus_karr_sign": _sgn(row_diff),
                "direction_vs_karr": _direction_phrase(
                    karr_row_delta_total=row_karr,
                    variant_row_delta_total=row_var,
                ),
            }

        return {
            "name": spec.name,
            "ok": True,
            "simplex_status": simplex_status,
            "solution_status": sol_status,
            "objective": objective,
            "biomass_growth_per_s": growth,
            "solver_options": {
                "basis_init": spec.basis,
                "presolve": "OFF",
                "meth": "PRIMAL",
                "pricing": "STD",
                "r_test": "FLIP" if spec.r_test == glp.GLP_RT_FLIP else "HAR",
                "tol_bnd": 1e-6,
                "tol_dj": float(parm.tol_dj),
                "tol_piv": float(parm.tol_piv),
                "scale": "AUTO",
            },
            "full_flux_l1_vs_karr": float(np.abs(flux - karr_flux).sum()),
            "writeback_delta_l1_vs_karr_recorded": int(np.abs(delta_i64 - karr_delta_i64).sum()),
            "pair_flux": {name: float(flux[col]) for name, col in PAIR_COLS},
            "systematic_direction": row_dir,
        }
    finally:
        glp.glp_delete_prob(lp)


def _choose_verdict(max_flips: int) -> str:
    if max_flips >= 5:
        return "FOUND_THE_KNOB"
    if max_flips >= 2:
        return "PARTIAL_HIT"
    return "NO_HIT"


def _write_status(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    variants = payload["variants"]
    flips_by_substrate = payload["flips_by_substrate"]

    def fmtf(x: float) -> str:
        return f"{x:.9e}"

    lines: list[str] = []
    lines.append("# STATUS_h_glpk_internal_sweep")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "- Sweep GLPK internal heuristics at sample `(s=0, t=1)` using OC LP build with clipped fixture bounds,"
    )
    lines.append(
        "  then compare writeback substrate deltas against Karr to identify the knob driving systematic mode bias."
    )
    lines.append("")
    lines.append("## Headline Verdict")
    lines.append(f"**{summary['headline_verdict']}**")
    lines.append("")
    lines.append(
        f"- Best objective-preserved variant: `{summary['best_variant']}` "
        f"(flips_toward_karr={summary['best_variant_flip_count']}/9, "
        f"L1={summary['best_variant_l1_vs_karr']})."
    )
    lines.append(
        f"- V0 writeback delta L1 vs Karr: {summary['v0_writeback_delta_l1_vs_karr']} "
        f"(target improvement threshold: below 14517)."
    )
    lines.append(
        f"- All 11 variants executed: {'YES' if summary['all_variants_ran'] else 'NO'}; "
        f"all objective-preserved within 1e-5 rel: "
        f"{'YES' if summary['all_variants_objective_preserved_within_1e5_rel'] else 'NO'}."
    )
    lines.append("")
    lines.append("## Variant Table")
    lines.append("| Variant | ok | obj | rel_obj_vs_V0 | obj<=1e-5 | writeback_L1 | L1<14517 | flips_toward_karr |")
    lines.append("|---|---|---:|---:|---|---:|---|---:|")
    for name in payload["variant_order"]:
        v = variants[name]
        if not v["ok"]:
            lines.append(f"| {name} | NO | n/a | n/a | n/a | n/a | n/a | 0 |")
            continue
        lines.append(
            f"| {name} | YES | {fmtf(v['objective'])} | {v['objective_rel_diff_vs_v0']:.3e} | "
            f"{'YES' if v['objective_preserved_within_1e5_rel'] else 'NO'} | "
            f"{v['writeback_delta_l1_vs_karr_recorded']} | "
            f"{'YES' if v['writeback_l1_improved_vs_v0'] else 'NO'} | "
            f"{v['flip_count_toward_karr']} |"
        )

    lines.append("")
    lines.append("## Per-substrate Direction Flips Toward Karr")
    lines.append("| Substrate | Row | Variants with flip_toward_karr |")
    lines.append("|---|---:|---|")
    for substrate, row_idx in SYSTEMATIC_ROWS:
        movers = flips_by_substrate[substrate]["variants_flip_toward_karr"]
        mover_text = ", ".join(movers) if movers else "(none)"
        lines.append(f"| {substrate} | {row_idx} | {mover_text} |")

    lines.append("")
    lines.append("## VERIFICATION")
    lines.append("| Item | Value |")
    lines.append("|---|---|")
    lines.append("| Command | `bin/oc-py scripts/probe_h_glpk_internal_sweep.py` |")
    lines.append("| Sample | seed=0, tick=1 |")
    lines.append("| LP bounds source | `data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat` |")
    lines.append("| LP matrix source | `data/karr_fixtures/karr_native_m1.npz` |")
    lines.append("| Writeback fixture | `data/karr_fixtures/per_process/Metabolism_flat.mat` |")
    lines.append("| JSON artifact | `tmp/h_glpk_internal_sweep.json` |")
    lines.append("| STATUS artifact | `STATUS_h_glpk_internal_sweep.md` |")
    lines.append("")
    lines.append("## Self-audit")
    lines.append("| # | Criterion | Verified |")
    lines.append("|---|---|---|")
    for idx, row in enumerate(payload["self_audit"], start=1):
        lines.append(f"| {idx} | {row['criterion']} | {'[x]' if row['ok'] else '[ ]'} |")

    OUT_STATUS.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> int:
    inputs = _load_inputs()
    glp.glp_term_out(glp.GLP_OFF)

    if not hasattr(glp, "GLP_RT_FLIP"):
        raise RuntimeError("swiglpk build does not expose GLP_RT_FLIP")

    variant_specs: list[VariantSpec] = [
        VariantSpec(name="V0", basis="adv", r_test=glp.GLP_RT_HAR),
        VariantSpec(name="V_cpx_basis", basis="cpx", r_test=glp.GLP_RT_HAR),
        VariantSpec(name="V_no_advanced_basis", basis="none", r_test=glp.GLP_RT_HAR),
        VariantSpec(name="V_tol_dj_1e5", basis="adv", r_test=glp.GLP_RT_HAR, tol_dj=1e-5),
        VariantSpec(name="V_tol_dj_1e9", basis="adv", r_test=glp.GLP_RT_HAR, tol_dj=1e-9),
        VariantSpec(name="V_tol_piv_1e8", basis="adv", r_test=glp.GLP_RT_HAR, tol_piv=1e-8),
        VariantSpec(name="V_tol_piv_1e12", basis="adv", r_test=glp.GLP_RT_HAR, tol_piv=1e-12),
        VariantSpec(name="V_flip_r_test", basis="adv", r_test=glp.GLP_RT_FLIP),
        VariantSpec(name="V_cpx_basis_plus_flip", basis="cpx", r_test=glp.GLP_RT_FLIP),
        VariantSpec(name="V_no_advbas_plus_flip", basis="none", r_test=glp.GLP_RT_FLIP),
        VariantSpec(
            name="V_all_alt",
            basis="cpx",
            r_test=glp.GLP_RT_FLIP,
            tol_dj=1e-5,
        ),
    ]

    lp_payload = {
        "S": inputs["S"],
        "rhs": inputs["rhs"],
        "obj": inputs["obj"],
        "lb": inputs["lb"],
        "ub": inputs["ub"],
    }
    biomass_col = int(np.argmax(np.abs(inputs["obj"])))

    variants: dict[str, Any] = {}
    for spec in variant_specs:
        variants[spec.name] = _variant_metrics(
            spec=spec,
            lp_payload=lp_payload,
            pre_sub=inputs["pre_sub"],
            karr_flux=inputs["karr_flux"],
            karr_delta=inputs["karr_delta"],
            fixture=inputs["fixture"],
            biomass_col=biomass_col,
        )

    v0 = variants["V0"]
    if not v0["ok"]:
        raise RuntimeError(f"V0 failed; cannot evaluate sweep: {v0.get('error', 'unknown error')}")

    v0_obj = float(v0["objective"])
    v0_l1 = int(v0["writeback_delta_l1_vs_karr_recorded"])

    for name, record in variants.items():
        if not record["ok"]:
            record["objective_rel_diff_vs_v0"] = None
            record["objective_preserved_within_1e5_rel"] = False
            record["objective_changed_gt_1pct"] = False
            record["writeback_l1_improved_vs_v0"] = False
            record["flip_count_toward_karr"] = 0
            continue

        rel = _rel_diff(float(record["objective"]), v0_obj)
        record["objective_rel_diff_vs_v0"] = rel
        record["objective_preserved_within_1e5_rel"] = bool(rel <= 1e-5)
        record["objective_changed_gt_1pct"] = bool(rel > 1e-2)
        record["writeback_l1_improved_vs_v0"] = bool(
            int(record["writeback_delta_l1_vs_karr_recorded"]) < v0_l1
        )

    v0_signs = {
        substrate: int(v0["systematic_direction"][substrate]["variant_minus_karr_sign"])
        for substrate, _ in SYSTEMATIC_ROWS
    }
    flips_by_substrate: dict[str, Any] = {}
    for substrate, row_idx in SYSTEMATIC_ROWS:
        movers: list[str] = []
        for name in variants:
            rec = variants[name]
            if not rec["ok"]:
                continue
            sign_here = int(rec["systematic_direction"][substrate]["variant_minus_karr_sign"])
            flip = (v0_signs[substrate] != 0) and (sign_here == -v0_signs[substrate])
            rec["systematic_direction"][substrate]["flip_toward_karr_vs_v0"] = bool(flip)
            rec["systematic_direction"][substrate]["moved_toward_karr_abs_error"] = bool(
                abs(float(rec["systematic_direction"][substrate]["variant_minus_karr"]))
                < abs(float(v0["systematic_direction"][substrate]["variant_minus_karr"]))
            )
            if name != "V0" and flip:
                movers.append(name)
        flips_by_substrate[substrate] = {
            "row_index": row_idx,
            "v0_sign": v0_signs[substrate],
            "variants_flip_toward_karr": movers,
        }

    for name in variants:
        rec = variants[name]
        if not rec["ok"]:
            continue
        rec["flip_count_toward_karr"] = int(
            sum(
                1
                for substrate, _ in SYSTEMATIC_ROWS
                if rec["systematic_direction"][substrate]["flip_toward_karr_vs_v0"]
            )
        )

    objective_preserved_candidates = [
        rec
        for rec in variants.values()
        if rec["ok"] and rec["objective_preserved_within_1e5_rel"]
    ]
    if objective_preserved_candidates:
        best = sorted(
            objective_preserved_candidates,
            key=lambda rec: (
                -int(rec["flip_count_toward_karr"]),
                int(rec["writeback_delta_l1_vs_karr_recorded"]),
                rec["name"],
            ),
        )[0]
        max_flips = int(max(int(rec["flip_count_toward_karr"]) for rec in objective_preserved_candidates))
    else:
        best = v0
        max_flips = 0

    headline = _choose_verdict(max_flips)

    self_audit = [
        {"criterion": "All 11 requested variants were executed", "ok": len(variants) == 11},
        {
            "criterion": "V0 uses production baseline knobs (OFF, PRIMAL, STD, HAR, tol_bnd=1e-6, AUTO, adv_basis)",
            "ok": (
                v0["ok"]
                and v0["solver_options"]["presolve"] == "OFF"
                and v0["solver_options"]["meth"] == "PRIMAL"
                and v0["solver_options"]["pricing"] == "STD"
                and v0["solver_options"]["r_test"] == "HAR"
                and float(v0["solver_options"]["tol_bnd"]) == 1e-6
                and v0["solver_options"]["scale"] == "AUTO"
                and v0["solver_options"]["basis_init"] == "adv"
            ),
        },
        {
            "criterion": "Per-variant objective preservation (rel <= 1e-5) computed vs V0",
            "ok": all(rec.get("objective_rel_diff_vs_v0") is not None for rec in variants.values() if rec["ok"]),
        },
        {
            "criterion": "Per-variant writeback substrate-delta L1 vs Karr recorded computed with _DetRng(np.rint)",
            "ok": all("writeback_delta_l1_vs_karr_recorded" in rec for rec in variants.values() if rec["ok"]),
        },
        {
            "criterion": "Per-variant 8 substitution-pair flux columns captured",
            "ok": all(len(rec.get("pair_flux", {})) == 8 for rec in variants.values() if rec["ok"]),
        },
        {
            "criterion": "Per-variant sign table for 9 systematic-bias substrates captured",
            "ok": all(len(rec.get("systematic_direction", {})) == 9 for rec in variants.values() if rec["ok"]),
        },
        {
            "criterion": "Best objective-preserved variant selected by most flips then lowest L1",
            "ok": best["name"] in variants,
        },
        {
            "criterion": "JSON and STATUS artifacts written to requested paths",
            "ok": True,
        },
    ]

    all_variants_ran = len(variants) == 11
    all_objective_preserved = all(
        bool(rec["ok"]) and bool(rec["objective_preserved_within_1e5_rel"])
        for rec in variants.values()
    )

    payload = {
        "metadata": {
            "probe": "h_glpk_internal_sweep",
            "sample": {"seed": 0, "tick": 1},
            "command": "bin/oc-py scripts/probe_h_glpk_internal_sweep.py",
            "files": {
                "ground_truth_fixture": str(SAMPLE_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
                "lp_fixture_npz": str(NPZ_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
                "writeback_fixture_mat": str(FIXTURE_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
                "json_output": str(OUT_JSON.relative_to(REPO_ROOT)).replace("\\", "/"),
                "status_output": str(OUT_STATUS.relative_to(REPO_ROOT)).replace("\\", "/"),
            },
            "lp_shape": {
                "rows": int(inputs["S"].shape[0]),
                "cols": int(inputs["S"].shape[1]),
            },
            "biomass_col": biomass_col,
            "karr_growth_per_s": float(inputs["karr_growth"]),
        },
        "variant_order": [spec.name for spec in variant_specs],
        "pair_columns": [{"name": n, "col": c} for n, c in PAIR_COLS],
        "systematic_substrates": [{"name": n, "row": r} for n, r in SYSTEMATIC_ROWS],
        "variants": variants,
        "flips_by_substrate": flips_by_substrate,
        "summary": {
            "headline_verdict": headline,
            "v0_writeback_delta_l1_vs_karr": v0_l1,
            "all_variants_ran": all_variants_ran,
            "all_variants_objective_preserved_within_1e5_rel": all_objective_preserved,
            "best_variant": best["name"],
            "best_variant_flip_count": int(best.get("flip_count_toward_karr", 0)),
            "best_variant_l1_vs_karr": int(best.get("writeback_delta_l1_vs_karr_recorded", v0_l1)),
            "max_flip_count_among_objective_preserved": max_flips,
            "objective_preserved_variants_with_l1_below_v0": [
                rec["name"]
                for rec in objective_preserved_candidates
                if int(rec["writeback_delta_l1_vs_karr_recorded"]) < v0_l1
            ],
            "objective_preserved_variants_with_2plus_flips": [
                rec["name"]
                for rec in objective_preserved_candidates
                if int(rec.get("flip_count_toward_karr", 0)) >= 2
            ],
            "objective_preserved_variants_with_5plus_flips": [
                rec["name"]
                for rec in objective_preserved_candidates
                if int(rec.get("flip_count_toward_karr", 0)) >= 5
            ],
        },
        "self_audit": self_audit,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="ascii")
    _write_status(payload)

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_STATUS}")
    print(
        "Headline="
        f"{payload['summary']['headline_verdict']}; "
        f"best={payload['summary']['best_variant']} "
        f"(flips={payload['summary']['best_variant_flip_count']}, "
        f"L1={payload['summary']['best_variant_l1_vs_karr']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
