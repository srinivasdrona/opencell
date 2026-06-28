from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import swiglpk as glp

from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = (
    ROOT
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
NPZ_PATH = ROOT / "data" / "karr_fixtures" / "karr_native_m1.npz"
WRITEBACK_FIXTURE_PATH = ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
OUT_JSON = ROOT / "tmp" / "h_bound_semantics.json"
OUT_STATUS = ROOT / "STATUS_h_bound_semantics.md"

BIG = 1e6

BOUND_TYPES = ("GLP_FR", "GLP_LO", "GLP_UP", "GLP_DB", "GLP_FX")
PAIR_COLS = {
    "HDCA": 393,
    "OCDCEA": 422,
    "PHE": 423,
    "PhePhe": 424,
    "TRIOLEIN": 444,
    "TRIPALMITIN": 445,
    "TRP": 449,
    "TrpTrp": 450,
}


class _DetRng:
    def stochastic_round(self, values):
        return np.rint(np.asarray(values, dtype=np.float64)).astype(np.int64)


def classify_bounds(bounds_raw: np.ndarray) -> tuple[list[str], dict[str, int]]:
    labels: list[str] = []
    counts = {k: 0 for k in BOUND_TYPES}

    for j in range(bounds_raw.shape[0]):
        lb = float(bounds_raw[j, 0])
        ub = float(bounds_raw[j, 1])

        lb_finite = np.isfinite(lb)
        ub_finite = np.isfinite(ub)

        if lb_finite and ub_finite:
            if lb < ub:
                label = "GLP_DB"
            elif lb == ub:
                label = "GLP_FX"
            else:
                raise ValueError(f"Invalid finite bounds at col {j}: lb={lb}, ub={ub}")
        elif lb_finite and np.isposinf(ub):
            label = "GLP_LO"
        elif np.isneginf(lb) and ub_finite:
            label = "GLP_UP"
        elif np.isneginf(lb) and np.isposinf(ub):
            label = "GLP_FR"
        else:
            raise ValueError(f"Unsupported bounds at col {j}: lb={lb}, ub={ub}")

        labels.append(label)
        counts[label] += 1

    return labels, counts


def clipped_bounds(bounds_raw: np.ndarray, big: float = BIG) -> tuple[np.ndarray, np.ndarray]:
    lb = np.where(np.isfinite(bounds_raw[:, 0]), bounds_raw[:, 0], -big)
    ub = np.where(np.isfinite(bounds_raw[:, 1]), bounds_raw[:, 1], +big)
    lb = np.clip(lb, -big, +big).astype(np.float64)
    ub = np.clip(ub, -big, +big).astype(np.float64)
    return lb, ub


def solve_variant(
    *,
    variant_id: str,
    S: np.ndarray,
    rhs: np.ndarray,
    c: np.ndarray,
    bounds_raw: np.ndarray,
    bound_labels: list[str],
) -> dict:
    n_rows, n_cols = S.shape
    lb_clip, ub_clip = clipped_bounds(bounds_raw)

    lp = glp.glp_create_prob()
    try:
        glp.glp_set_obj_dir(lp, glp.GLP_MAX)
        glp.glp_add_rows(lp, n_rows)
        for i in range(n_rows):
            glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))

        glp.glp_add_cols(lp, n_cols)
        for j in range(n_cols):
            lb_raw = float(bounds_raw[j, 0])
            ub_raw = float(bounds_raw[j, 1])
            label = bound_labels[j]

            if variant_id == "V_clip":
                lo = float(lb_clip[j])
                hi = float(ub_clip[j])
                if lo == hi:
                    glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lo, hi)
                else:
                    glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lo, hi)
            elif variant_id == "V_faithful":
                if label == "GLP_FX":
                    glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lb_raw, ub_raw)
                elif label == "GLP_DB":
                    glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lb_raw, ub_raw)
                elif label == "GLP_LO":
                    glp.glp_set_col_bnds(lp, j + 1, glp.GLP_LO, lb_raw, 0.0)
                elif label == "GLP_UP":
                    glp.glp_set_col_bnds(lp, j + 1, glp.GLP_UP, 0.0, ub_raw)
                elif label == "GLP_FR":
                    glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FR, 0.0, 0.0)
                else:
                    raise ValueError(f"Unknown bound label at col {j}: {label}")
            else:
                raise ValueError(f"Unknown variant_id: {variant_id}")

            glp.glp_set_obj_coef(lp, j + 1, float(c[j]))

        nz_rows, nz_cols = np.nonzero(S)
        nnz = int(nz_rows.size)
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

        simplex_status = int(glp.glp_simplex(lp, params))
        solution_status = int(glp.glp_get_status(lp))
        objective = float(glp.glp_get_obj_val(lp))

        flux = np.array([glp.glp_get_col_prim(lp, j + 1) for j in range(n_cols)], dtype=np.float64)
        if variant_id == "V_clip":
            flux = np.clip(flux, lb_clip, ub_clip)
        else:
            flux = np.clip(flux, bounds_raw[:, 0], bounds_raw[:, 1])

        return {
            "variant": variant_id,
            "simplex_status": simplex_status,
            "solution_status": solution_status,
            "objective": objective,
            "flux": flux,
        }
    finally:
        glp.glp_delete_prob(lp)


def evaluate_variant(
    *,
    solve_result: dict,
    karr_flux: np.ndarray,
    karr_delta: np.ndarray,
    pre_sub: np.ndarray,
    fixture: KarrWritebackFixture,
    c: np.ndarray,
) -> dict:
    flux = solve_result["flux"]
    variant_id = solve_result["variant"]
    biomass_col = int(np.argmax(np.abs(c)))
    growth = float(flux[biomass_col])

    rng = _DetRng()
    wb_delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(),
        v_504=flux,
        growth_per_s=growth,
        fixture=fixture,
        rng=rng,
        step_size_sec=fixture.step_size_sec,
    )

    ext_idx = fixture.fba_idx_external
    full_l1 = float(np.abs(flux - karr_flux).sum())
    ext_l1 = float(np.abs(flux[ext_idx] - karr_flux[ext_idx]).sum())
    wb_l1 = int(np.abs(wb_delta.astype(np.int64) - karr_delta.astype(np.int64)).sum())

    pair_flux = {name: float(flux[col]) for name, col in PAIR_COLS.items()}

    return {
        "variant": variant_id,
        "simplex_status": int(solve_result["simplex_status"]),
        "solution_status": int(solve_result["solution_status"]),
        "objective": float(solve_result["objective"]),
        "biomass_col": biomass_col,
        "growth_per_s": growth,
        "full_flux_l1_vs_karr": full_l1,
        "ext_flux_l1_vs_karr": ext_l1,
        "writeback_delta_l1_vs_karr": wb_l1,
        "pair_flux": pair_flux,
        "flux": flux.tolist(),
    }


def write_status(
    *,
    bound_counts: dict[str, int],
    v_clip: dict,
    v_faithful: dict,
    karr_pair_flux: dict[str, float],
    pair_l1_between_variants: float,
    objective_rel_gap: float,
) -> None:
    same_obj = objective_rel_gap <= 1e-5
    clip_wb_ok = abs(v_clip["writeback_delta_l1_vs_karr"] - 14517) <= 500
    faithful_opt = v_faithful["solution_status"] == int(glp.GLP_OPT) and v_faithful["simplex_status"] == 0
    clip_opt = v_clip["solution_status"] == int(glp.GLP_OPT) and v_clip["simplex_status"] == 0

    lines = [
        "# STATUS_h_bound_semantics",
        "",
        "## INTENT",
        "- Probe whether GLPK bound-type semantics (FR/LO/UP/DB/FX) at LP construction alter the selected optimal vertex and downstream writeback at sample (s=0, t=1).",
        "- Keep all non-bound solver options fixed to H3+H5 production parameters (pricing=STD, presolve=OFF, scale=AUTO, tol_bnd=1e-6, primal).",
        "",
        "## Headline",
        "| Variant | Objective | Full flux L1 vs Karr | Ext flux L1 vs Karr | Writeback delta L1 vs Karr |",
        "|---|---:|---:|---:|---:|",
        f"| V_clip | {v_clip['objective']:.9e} | {v_clip['full_flux_l1_vs_karr']:.6e} | {v_clip['ext_flux_l1_vs_karr']:.6e} | {v_clip['writeback_delta_l1_vs_karr']} |",
        f"| V_faithful | {v_faithful['objective']:.9e} | {v_faithful['full_flux_l1_vs_karr']:.6e} | {v_faithful['ext_flux_l1_vs_karr']:.6e} | {v_faithful['writeback_delta_l1_vs_karr']} |",
        "",
        "## Bound-Type Distribution",
        "| Type | Count |",
        "|---|---:|",
        f"| GLP_FR | {bound_counts['GLP_FR']} |",
        f"| GLP_LO | {bound_counts['GLP_LO']} |",
        f"| GLP_UP | {bound_counts['GLP_UP']} |",
        f"| GLP_DB | {bound_counts['GLP_DB']} |",
        f"| GLP_FX | {bound_counts['GLP_FX']} |",
        "",
        "## Pair-Column Flux",
        "| Column | Karr | V_clip | V_faithful |",
        "|---|---:|---:|---:|",
    ]
    for name in PAIR_COLS:
        lines.append(
            f"| {name} | {karr_pair_flux[name]:+.6e} | {v_clip['pair_flux'][name]:+.6e} | {v_faithful['pair_flux'][name]:+.6e} |"
        )

    lines.extend(
        [
            "",
            "## Verdict",
            f"- Objective relative gap `|obj_clip-obj_faithful|/max(|obj|,1)` = `{objective_rel_gap:.6e}` ({'PASS' if same_obj else 'FAIL'} vs 1e-5 criterion).",
            f"- V_clip writeback sanity (`~14517`) observed `{v_clip['writeback_delta_l1_vs_karr']}` ({'PASS' if clip_wb_ok else 'CHECK'}).",
            f"- Pair-column L1 between V_clip and V_faithful = `{pair_l1_between_variants:.6e}`.",
            "- Interpretation: if pair-column and writeback metrics move under V_faithful while objective is unchanged, bound semantics affect vertex selection on a degenerate optimal face.",
            "",
            "## VERIFICATION",
            "- Executed with `bin\\oc-py scripts/probe_h_bound_semantics.py`.",
            f"- JSON artifact written: `{OUT_JSON.relative_to(ROOT)}`.",
            f"- Status artifact written: `{OUT_STATUS.relative_to(ROOT)}`.",
            f"- Optimality checks: V_clip={clip_opt}, V_faithful={faithful_opt}.",
            "",
            "## Self-audit",
            "| # | Criterion | Verified |",
            "|---|---|---|",
            "| 1 | Raw bounds loaded from `.mat` without clipping before classification | [x] |",
            "| 2 | All 504 columns classified into GLP_FR/LO/UP/DB/FX | [x] |",
            "| 3 | V_clip encoded non-FX columns as GLP_DB after +/-1e6 clipping | [x] |",
            "| 4 | V_faithful used GLPK bound API by class (FR/LO/UP/DB/FX) | [x] |",
            f"| 5 | V_clip writeback L1 near 14517 sanity value | {'[x]' if clip_wb_ok else '[ ]'} |",
            f"| 6 | Objective equality within 1e-5 relative | {'[x]' if same_obj else '[ ]'} |",
            "| 7 | Headline + bound distribution + pair-column tables emitted | [x] |",
            "| 8 | INTENT + VERIFICATION sections present | [x] |",
        ]
    )

    OUT_STATUS.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    with h5py.File(SAMPLE_PATH, "r") as f:
        bounds_raw = np.asarray(f["bounds"], dtype=np.float64).T
        karr_flux = np.asarray(f["flux"], dtype=np.float64).reshape(-1)
        pre_sub = np.asarray(f["pre_sub"], dtype=np.float64).T
        karr_delta = np.asarray(f["delta"], dtype=np.float64).T

    npz = np.load(NPZ_PATH, allow_pickle=False)
    S = np.asarray(npz["S"], dtype=np.float64)
    rhs = np.asarray(npz["RHS"], dtype=np.float64).reshape(-1)
    c = np.asarray(npz["obj"], dtype=np.float64).reshape(-1)

    bound_labels, bound_counts = classify_bounds(bounds_raw)

    fixture = KarrWritebackFixture.from_mat(WRITEBACK_FIXTURE_PATH)

    solve_clip = solve_variant(
        variant_id="V_clip",
        S=S,
        rhs=rhs,
        c=c,
        bounds_raw=bounds_raw,
        bound_labels=bound_labels,
    )
    solve_faithful = solve_variant(
        variant_id="V_faithful",
        S=S,
        rhs=rhs,
        c=c,
        bounds_raw=bounds_raw,
        bound_labels=bound_labels,
    )

    eval_clip = evaluate_variant(
        solve_result=solve_clip,
        karr_flux=karr_flux,
        karr_delta=karr_delta,
        pre_sub=pre_sub,
        fixture=fixture,
        c=c,
    )
    eval_faithful = evaluate_variant(
        solve_result=solve_faithful,
        karr_flux=karr_flux,
        karr_delta=karr_delta,
        pre_sub=pre_sub,
        fixture=fixture,
        c=c,
    )

    karr_pair_flux = {name: float(karr_flux[col]) for name, col in PAIR_COLS.items()}
    pair_l1_between_variants = float(
        sum(abs(eval_clip["pair_flux"][name] - eval_faithful["pair_flux"][name]) for name in PAIR_COLS)
    )
    objective_rel_gap = abs(eval_clip["objective"] - eval_faithful["objective"]) / max(
        abs(eval_clip["objective"]),
        abs(eval_faithful["objective"]),
        1.0,
    )

    headline = [eval_clip, eval_faithful]

    print("Bound-type distribution (504 columns):")
    for t in BOUND_TYPES:
        print(f"  {t:>6s}: {bound_counts[t]:>4d}")

    print()
    print(f"{'variant':<12s} {'obj':>14s} {'full_L1':>12s} {'ext_L1':>12s} {'writeback_L1':>13s}")
    print("-" * 70)
    for row in headline:
        print(
            f"{row['variant']:<12s} {row['objective']:>14.6e} {row['full_flux_l1_vs_karr']:>12.3e} "
            f"{row['ext_flux_l1_vs_karr']:>12.3e} {row['writeback_delta_l1_vs_karr']:>13d}"
        )

    print()
    print("Pair-column flux:")
    print(f"{'name':>12s} {'Karr':>13s} {'V_clip':>13s} {'V_faithful':>13s}")
    for name in PAIR_COLS:
        print(
            f"{name:>12s} {karr_pair_flux[name]:>+13.6e} {eval_clip['pair_flux'][name]:>+13.6e} "
            f"{eval_faithful['pair_flux'][name]:>+13.6e}"
        )
    print(f"\nPair-column L1(V_clip, V_faithful): {pair_l1_between_variants:.6e}")
    print(f"Objective relative gap: {objective_rel_gap:.6e}")

    payload = {
        "probe": "Day-42 Probe 2: faithful bound semantics",
        "sample": {"seed": 0, "tick": 1},
        "paths": {
            "sample_mat": str(SAMPLE_PATH.relative_to(ROOT)),
            "lp_npz": str(NPZ_PATH.relative_to(ROOT)),
            "writeback_fixture_mat": str(WRITEBACK_FIXTURE_PATH.relative_to(ROOT)),
        },
        "solver_options": {
            "presolve": "GLP_OFF",
            "meth": "GLP_PRIMAL",
            "pricing": "GLP_PT_STD",
            "scale": "GLP_SF_AUTO",
            "tol_bnd": 1e-6,
            "sense": "GLP_MAX",
        },
        "bound_type_distribution": bound_counts,
        "bound_type_by_col_0based": bound_labels,
        "variants": {
            "V_clip": eval_clip,
            "V_faithful": eval_faithful,
        },
        "pair_columns": {
            "definitions_0based": PAIR_COLS,
            "karr_pair_flux": karr_pair_flux,
            "pair_l1_between_variants": pair_l1_between_variants,
        },
        "objective_relative_gap": objective_rel_gap,
        "acceptance_checks": {
            "v_clip_writeback_l1_near_14517": bool(abs(eval_clip["writeback_delta_l1_vs_karr"] - 14517) <= 500),
            "both_same_optimal_objective_rel_1e_5": bool(objective_rel_gap <= 1e-5),
            "v_clip_optimal": bool(eval_clip["simplex_status"] == 0 and eval_clip["solution_status"] == int(glp.GLP_OPT)),
            "v_faithful_optimal": bool(
                eval_faithful["simplex_status"] == 0 and eval_faithful["solution_status"] == int(glp.GLP_OPT)
            ),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2))

    write_status(
        bound_counts=bound_counts,
        v_clip=eval_clip,
        v_faithful=eval_faithful,
        karr_pair_flux=karr_pair_flux,
        pair_l1_between_variants=pair_l1_between_variants,
        objective_rel_gap=objective_rel_gap,
    )

    print(f"\nWrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_STATUS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
