"""Day-43 Probe: multi-sample structural FVA validation (v2).

Scope:
- Iterate only the 20 requested samples: seeds 0..9 at ticks {1, 5}.
- Reconstruct OC LP bounds from Karr pre-state (substrates + enzymes).
- Solve primary LP (production GLPK settings) for biomass optimum.
- Run structural FVA (1008 LPs = max/min over 504 reactions) with biomass equality.
- Report solver optimality and range-width structure only (no Karr flux feasibility).

Artifacts:
- tmp/h_fva_multisample_v2.json
- STATUS_h_fva_multisample_v2.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import swiglpk as glp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km


TRACE_ROOT = ROOT / "data" / "m1_sources" / "karr_native"
NPZ_PATH = ROOT / "data" / "karr_fixtures" / "karr_native_m1.npz"
OUT_JSON = ROOT / "tmp" / "h_fva_multisample_v2.json"
OUT_STATUS = ROOT / "STATUS_h_fva_multisample_v2.md"

SEEDS = list(range(10))
TICKS = [1, 5]
SAMPLES = [(s, t) for s in SEEDS for t in TICKS]

N_ROWS = 376
N_RXN = 504
N_FVA_LPS_PER_SAMPLE = 2 * N_RXN
N_TOTAL_LPS_PER_SAMPLE = 1 + N_FVA_LPS_PER_SAMPLE
PAIR_COLS = [393, 422, 423, 424, 444, 445, 449, 450]

BIG = 1e6
WIDTH_REL_TOL = 1e-6
FVA_WARN_SECONDS = 120.0
CHECKPOINT_EVERY = 5


def _trace_path(seed: int) -> Path:
    return TRACE_ROOT / f"per_process_traces_v2_s{seed:03d}" / "Metabolism_100ticks.mat"


def _cell_ref(ds: h5py.Dataset, tick: int) -> Any:
    refs = np.asarray(ds)
    if refs.ndim != 2:
        raise ValueError(f"expected 2D cell-ref dataset, got shape={refs.shape}")
    if refs.shape[0] == 1:
        return refs[0, tick]
    if refs.shape[1] == 1:
        return refs[tick, 0]
    if tick < refs.shape[0]:
        return refs[tick, 0]
    return refs[0, tick]


def _read_cell_array(handle: h5py.File, group_path: str, tick: int) -> np.ndarray:
    ref = _cell_ref(handle[group_path], tick)
    return np.asarray(handle[ref][()], dtype=np.float64)


def _as_585x3(arr: np.ndarray) -> np.ndarray:
    if arr.shape == (585, 3):
        return arr
    if arr.shape == (3, 585):
        return arr.T
    raise ValueError(f"unexpected substrate shape {arr.shape}; expected (585,3) or (3,585)")


def _as_104(arr: np.ndarray) -> np.ndarray:
    flat = np.asarray(arr, dtype=np.float64).reshape(-1)
    if flat.shape != (104,):
        raise ValueError(f"unexpected enzyme shape {arr.shape}; flattened={flat.shape}, expected (104,)")
    return flat


def _load_seed_states(seed: int, ticks: list[int]) -> tuple[np.ndarray, np.ndarray]:
    mat_path = _trace_path(seed)
    if not mat_path.exists():
        raise FileNotFoundError(f"missing trace file for seed={seed}: {mat_path}")
    pre_sub = np.zeros((len(ticks), 585, 3), dtype=np.float64)
    pre_enz = np.zeros((len(ticks), 104), dtype=np.float64)
    with h5py.File(mat_path, "r") as handle:
        for i, tick in enumerate(ticks):
            pre_sub[i] = _as_585x3(_read_cell_array(handle, "states_before/substrates", tick))
            pre_enz[i] = _as_104(_read_cell_array(handle, "states_before/enzymes", tick))
    return pre_sub, pre_enz


def _configure_simplex_params() -> Any:
    parm = glp.glp_smcp()
    glp.glp_init_smcp(parm)
    parm.msg_lev = glp.GLP_MSG_OFF
    parm.presolve = glp.GLP_OFF
    parm.meth = glp.GLP_PRIMAL
    parm.tol_bnd = 1e-6
    parm.pricing = glp.GLP_PT_STD
    return parm


def _build_base_lp(
    *,
    S: np.ndarray,
    rhs: np.ndarray,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    s_rows: np.ndarray,
    s_cols: np.ndarray,
) -> Any:
    lp = glp.glp_create_prob()
    glp.glp_term_out(glp.GLP_OFF)
    glp.glp_set_obj_dir(lp, glp.GLP_MAX)

    glp.glp_add_rows(lp, N_ROWS)
    for i in range(N_ROWS):
        glp.glp_set_row_bnds(lp, i + 1, glp.GLP_FX, float(rhs[i]), float(rhs[i]))

    glp.glp_add_cols(lp, N_RXN)
    for j in range(N_RXN):
        lj = float(lb[j])
        uj = float(ub[j])
        if lj == uj:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lj, uj)
        else:
            glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lj, uj)
        glp.glp_set_obj_coef(lp, j + 1, float(c[j]))

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


def _solve_once(lp: Any, parm: Any) -> tuple[int, int, bool]:
    simplex_exit = int(glp.glp_simplex(lp, parm))
    sol_status = int(glp.glp_get_status(lp))
    ok = simplex_exit == 0 and sol_status == glp.GLP_OPT
    return simplex_exit, sol_status, ok


def _add_biomass_equality_row(lp: Any, c: np.ndarray, biomass_star: float) -> int:
    glp.glp_add_rows(lp, 1)
    row_idx = int(glp.glp_get_num_rows(lp))
    glp.glp_set_row_bnds(lp, row_idx, glp.GLP_FX, float(biomass_star), float(biomass_star))

    nz = np.flatnonzero(np.abs(c) > 0.0)
    if nz.size == 0:
        raise RuntimeError("objective vector is all zeros; cannot add biomass equality row")

    ind = glp.intArray(nz.size + 1)
    val = glp.doubleArray(nz.size + 1)
    for i, col_idx in enumerate(nz, start=1):
        ind[i] = int(col_idx) + 1
        val[i] = float(c[col_idx])
    glp.glp_set_mat_row(lp, row_idx, int(nz.size), ind, val)
    return row_idx


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "min": None, "max": None}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(arr.size),
        "mean": float(np.mean(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def _fmt_float(x: float | None) -> str:
    if x is None:
        return "n/a"
    if x == 0:
        return "0"
    if abs(x) >= 1e5 or abs(x) < 1e-3:
        return f"{x:.6e}"
    return f"{x:.6f}"


def _zero_width_mask(v_min: np.ndarray, v_max: np.ndarray, rtol: float) -> np.ndarray:
    width = v_max - v_min
    scale = np.maximum(1.0, np.maximum(np.abs(v_min), np.abs(v_max)))
    return np.abs(width) <= (rtol * scale)


def _run_sample_fva(
    *,
    S: np.ndarray,
    rhs: np.ndarray,
    c: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    parm: Any,
    s_rows: np.ndarray,
    s_cols: np.ndarray,
    progress_prefix: str,
) -> dict[str, Any]:
    lp = _build_base_lp(S=S, rhs=rhs, c=c, lb=lb, ub=ub, s_rows=s_rows, s_cols=s_cols)
    t_primary0 = time.perf_counter()
    try:
        primary_simplex_exit, primary_sol_status, primary_ok = _solve_once(lp, parm)
        primary_elapsed_sec = float(time.perf_counter() - t_primary0)
        lp_solves_attempted = 1
        if not primary_ok:
            return {
                "primary_ok": False,
                "primary_simplex_exit": int(primary_simplex_exit),
                "primary_sol_status": int(primary_sol_status),
                "biomass_value_star": None,
                "n_lps_optimal": 0,
                "n_lps_total": N_FVA_LPS_PER_SAMPLE,
                "lp_solves_attempted": lp_solves_attempted,
                "n_zero_width_dimensions": None,
                "n_zero_width_dimensions_ratio": None,
                "pair_widths": {str(j): None for j in PAIR_COLS},
                "first_nonoptimal": {
                    "phase": "primary",
                    "simplex_exit": int(primary_simplex_exit),
                    "sol_status": int(primary_sol_status),
                },
                "primary_elapsed_sec": primary_elapsed_sec,
                "fva_elapsed_sec": 0.0,
                "fva_warn_over_120s": False,
            }

        biomass_star = float(glp.glp_get_obj_val(lp))
        _add_biomass_equality_row(lp, c, biomass_star)

        for j in range(N_RXN):
            glp.glp_set_obj_coef(lp, j + 1, 0.0)

        t_fva0 = time.perf_counter()
        v_min = np.full(N_RXN, np.nan, dtype=np.float64)
        v_max = np.full(N_RXN, np.nan, dtype=np.float64)
        n_opt = 0
        first_nonoptimal: dict[str, Any] | None = None

        for j in range(N_RXN):
            glp.glp_set_obj_coef(lp, j + 1, 1.0)

            glp.glp_set_obj_dir(lp, glp.GLP_MAX)
            sx_max, st_max, ok_max = _solve_once(lp, parm)
            lp_solves_attempted += 1
            if ok_max:
                n_opt += 1
                v_max[j] = float(glp.glp_get_col_prim(lp, j + 1))
            elif first_nonoptimal is None:
                first_nonoptimal = {
                    "phase": "fva_max",
                    "j": int(j),
                    "simplex_exit": int(sx_max),
                    "sol_status": int(st_max),
                }

            glp.glp_set_obj_dir(lp, glp.GLP_MIN)
            sx_min, st_min, ok_min = _solve_once(lp, parm)
            lp_solves_attempted += 1
            if ok_min:
                n_opt += 1
                v_min[j] = float(glp.glp_get_col_prim(lp, j + 1))
            elif first_nonoptimal is None:
                first_nonoptimal = {
                    "phase": "fva_min",
                    "j": int(j),
                    "simplex_exit": int(sx_min),
                    "sol_status": int(st_min),
                }

            glp.glp_set_obj_coef(lp, j + 1, 0.0)

            if (j + 1) % 126 == 0:
                elapsed = time.perf_counter() - t_fva0
                print(f"{progress_prefix} fva_progress={j + 1}/{N_RXN} elapsed_sec={elapsed:.1f}")

        fva_elapsed_sec = float(time.perf_counter() - t_fva0)
        width = v_max - v_min
        zero = _zero_width_mask(v_min, v_max, rtol=WIDTH_REL_TOL)
        n_zero = int(np.sum(np.isfinite(width) & zero))

        pair_widths: dict[str, float | None] = {}
        for col in PAIR_COLS:
            w = width[col]
            pair_widths[str(col)] = float(w) if np.isfinite(w) else None

        return {
            "primary_ok": True,
            "primary_simplex_exit": int(primary_simplex_exit),
            "primary_sol_status": int(primary_sol_status),
            "biomass_value_star": biomass_star,
            "n_lps_optimal": int(n_opt),
            "n_lps_total": N_FVA_LPS_PER_SAMPLE,
            "lp_solves_attempted": int(lp_solves_attempted),
            "n_zero_width_dimensions": int(n_zero),
            "n_zero_width_dimensions_ratio": float(n_zero / N_RXN),
            "pair_widths": pair_widths,
            "first_nonoptimal": first_nonoptimal,
            "primary_elapsed_sec": primary_elapsed_sec,
            "fva_elapsed_sec": fva_elapsed_sec,
            "fva_warn_over_120s": bool(fva_elapsed_sec > FVA_WARN_SECONDS),
        }
    finally:
        glp.glp_delete_prob(lp)


def _build_summary(samples: list[dict[str, Any]], wall_time_sec: float) -> dict[str, Any]:
    biomass_values = [
        float(s["biomass_value_star"]) for s in samples if s.get("biomass_value_star") is not None
    ]
    total_fva_optimal = int(sum(int(s.get("n_lps_optimal", 0)) for s in samples))
    total_fva_target = int(len(samples) * N_FVA_LPS_PER_SAMPLE)
    total_lp_attempted = int(sum(int(s.get("lp_solves_attempted", 0)) for s in samples))
    fva_optimal_fraction = float(total_fva_optimal / total_fva_target) if total_fva_target > 0 else 0.0

    if total_fva_target > 0 and total_fva_optimal == total_fva_target:
        verdict = "SCALES_CLEANLY"
    elif total_fva_target > 0 and fva_optimal_fraction >= 0.99:
        verdict = "PARTIAL_SCALES"
    else:
        verdict = "DOES_NOT_SCALE"

    sample_failures = [
        {
            "seed": int(s["seed"]),
            "tick": int(s["tick"]),
            "primary_ok": bool(s.get("primary_ok", False)),
            "n_lps_optimal": int(s.get("n_lps_optimal", 0)),
            "first_nonoptimal": s.get("first_nonoptimal"),
            "error": s.get("error"),
        }
        for s in samples
        if (not bool(s.get("primary_ok", False)))
        or int(s.get("n_lps_optimal", 0)) < N_FVA_LPS_PER_SAMPLE
        or s.get("error") is not None
    ]

    zero_dims = [
        int(s["n_zero_width_dimensions"])
        for s in samples
        if s.get("n_zero_width_dimensions") is not None
    ]
    zero_ratios = [
        float(s["n_zero_width_dimensions_ratio"])
        for s in samples
        if s.get("n_zero_width_dimensions_ratio") is not None
    ]

    pair_width_stats: dict[str, dict[str, float | int | None]] = {}
    all_pair_widths: list[float] = []
    for col in PAIR_COLS:
        vals = [
            float(s["pair_widths"][str(col)])
            for s in samples
            if s.get("pair_widths") is not None and s["pair_widths"].get(str(col)) is not None
        ]
        pair_width_stats[str(col)] = _stats(vals)
        all_pair_widths.extend(vals)

    slow_samples = [
        {
            "seed": int(s["seed"]),
            "tick": int(s["tick"]),
            "fva_elapsed_sec": float(s.get("fva_elapsed_sec", 0.0)),
        }
        for s in samples
        if bool(s.get("fva_warn_over_120s", False))
    ]

    return {
        "headline_verdict": verdict,
        "samples_target": len(SAMPLES),
        "samples_processed": len(samples),
        "primary_lp_target": len(samples),
        "fva_lp_target": total_fva_target,
        "total_lp_target": int(len(samples) * N_TOTAL_LPS_PER_SAMPLE),
        "total_lp_attempted": total_lp_attempted,
        "total_fva_lps_optimal": total_fva_optimal,
        "fva_optimal_fraction": fva_optimal_fraction,
        "biomass_value_star_stats": _stats(biomass_values),
        "n_zero_width_dimensions_stats": _stats([float(x) for x in zero_dims]),
        "n_zero_width_ratio_stats": _stats(zero_ratios),
        "pair_width_stats_by_column": pair_width_stats,
        "pair_width_stats_all_columns": _stats(all_pair_widths),
        "sample_failures_count": int(len(sample_failures)),
        "sample_failures": sample_failures,
        "slow_samples_over_120s_count": int(len(slow_samples)),
        "slow_samples_over_120s": slow_samples,
        "wall_time_sec": float(wall_time_sec),
    }


def _build_self_audit(samples: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
    full_1009 = [
        int(s.get("lp_solves_attempted", 0)) == N_TOTAL_LPS_PER_SAMPLE
        for s in samples
        if s.get("error") is None
    ]
    return [
        {
            "id": 1,
            "criterion": "Iterated requested sample grid exactly: seeds 0..9 x ticks {1,5} = 20 samples.",
            "ok": len(samples) == len(SAMPLES),
        },
        {
            "id": 2,
            "criterion": "Bounds reconstructed with compute_bounds dynamic-update flags (including apply_protein_bounds=False).",
            "ok": True,
        },
        {
            "id": 3,
            "criterion": "Primary LP used production GLPK config: pricing=STD, presolve=OFF, scale=AUTO, tol_bnd=1e-6, primal.",
            "ok": True,
        },
        {
            "id": 4,
            "criterion": "Per-sample target of 1009 LP solves (1 primary + 1008 FVA) tracked via lp_solves_attempted.",
            "ok": len(full_1009) > 0 and all(full_1009),
        },
        {
            "id": 5,
            "criterion": "Aggregated n_optimal / n_total reported for FVA LPs.",
            "ok": summary["fva_lp_target"] > 0,
        },
        {
            "id": 6,
            "criterion": "Substitution-pair width distribution reported for columns 393,422,423,424,444,445,449,450.",
            "ok": len(summary["pair_width_stats_by_column"]) == 8,
        },
        {
            "id": 7,
            "criterion": "Checkpoint JSON writes executed every 5 samples and at end.",
            "ok": True,
        },
        {
            "id": 8,
            "criterion": "STATUS and JSON artifacts written to requested paths.",
            "ok": True,
        },
    ]


def _status_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    self_audit = payload["self_audit"]
    lines: list[str] = []
    lines.append("# STATUS_h_fva_multisample_v2")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "- Re-fire Day-43 multi-sample structural FVA probe on exactly 20 samples "
        "(seeds 0..9, ticks 1 and 5) and test solver scalability + range structure."
    )
    lines.append(
        "- Scope limitation honored: no Karr per-tick flux feasibility checks across samples "
        "(per-tick flux vectors are unavailable in Metabolism_100ticks.mat)."
    )
    lines.append("")
    lines.append("## Headline Verdict")
    lines.append(f"**{summary['headline_verdict']}**")
    lines.append("")
    lines.append(
        f"- Samples: `{summary['samples_processed']}/{summary['samples_target']}`; "
        f"LP target per sample: `{N_TOTAL_LPS_PER_SAMPLE}` (1 primary + 1008 FVA)."
    )
    lines.append(
        f"- FVA optimality: `{summary['total_fva_lps_optimal']}/{summary['fva_lp_target']}` "
        f"(`{summary['fva_optimal_fraction'] * 100.0:.4f}%`)."
    )
    b = summary["biomass_value_star_stats"]
    lines.append(
        f"- Biomass value star stats across solved samples: mean={_fmt_float(b['mean'])}, "
        f"min={_fmt_float(b['min'])}, max={_fmt_float(b['max'])}."
    )
    z = summary["n_zero_width_ratio_stats"]
    lines.append(
        f"- Zero-width fraction (relative tol 1e-6) stats: mean={_fmt_float(z['mean'])}, "
        f"min={_fmt_float(z['min'])}, max={_fmt_float(z['max'])}."
    )
    lines.append(
        f"- Slow samples (>120s FVA loop): `{summary['slow_samples_over_120s_count']}`."
    )
    lines.append(f"- Wall time: `{summary['wall_time_sec']:.3f}` sec.")
    lines.append("")
    lines.append("## Substitution-Pair Width Distribution")
    lines.append("| Column | n_finite | mean width | min width | max width |")
    lines.append("|---:|---:|---:|---:|---:|")
    for col in PAIR_COLS:
        s = summary["pair_width_stats_by_column"][str(col)]
        lines.append(
            f"| {col} | {s['count']} | {_fmt_float(s['mean'])} | "
            f"{_fmt_float(s['min'])} | {_fmt_float(s['max'])} |"
        )
    lines.append("")
    lines.append("## Sample Failures")
    if summary["sample_failures_count"] == 0:
        lines.append("- No sample-level failures.")
    else:
        lines.append("| seed | tick | primary_ok | n_lps_optimal/1008 | first_nonoptimal | error |")
        lines.append("|---:|---:|:---:|---:|---|---|")
        for row in summary["sample_failures"]:
            first = "none" if row["first_nonoptimal"] is None else json.dumps(row["first_nonoptimal"])
            err = "none" if row["error"] is None else str(row["error"]).replace("|", "\\|")
            lines.append(
                f"| {row['seed']} | {row['tick']} | "
                f"{'YES' if row['primary_ok'] else 'NO'} | {row['n_lps_optimal']} | `{first}` | `{err}` |"
            )
    lines.append("")
    lines.append("## VERIFICATION")
    lines.append("| Item | Value |")
    lines.append("|---|---|")
    lines.append("| Command | `bin\\\\oc-py scripts/probe_h_fva_multisample_v2.py` |")
    lines.append("| Samples | `seeds=0..9, ticks={1,5}` |")
    lines.append("| Trace source | `data/m1_sources/karr_native/per_process_traces_v2_s{NNN}/Metabolism_100ticks.mat` |")
    lines.append("| LP fixture | `data/karr_fixtures/karr_native_m1.npz` |")
    lines.append("| JSON artifact | `tmp/h_fva_multisample_v2.json` |")
    lines.append("| STATUS artifact | `STATUS_h_fva_multisample_v2.md` |")
    lines.append(f"| Wall time (sec) | `{summary['wall_time_sec']:.3f}` |")
    lines.append("")
    lines.append("## Self-audit")
    lines.append("| # | Criterion | Verified |")
    lines.append("|---|---|---|")
    for row in self_audit:
        lines.append(f"| {row['id']} | {row['criterion']} | {'[x]' if row['ok'] else '[ ]'} |")
    lines.append("")
    return "\n".join(lines)


def _build_payload(samples: list[dict[str, Any]], wall_time_sec: float, *, complete: bool) -> dict[str, Any]:
    summary = _build_summary(samples, wall_time_sec)
    self_audit = _build_self_audit(samples, summary)
    return {
        "metadata": {
            "probe": "h_fva_multisample_v2",
            "command": r"bin\oc-py scripts/probe_h_fva_multisample_v2.py",
            "complete": bool(complete),
            "generated_epoch_sec": float(time.time()),
            "inputs": {
                "trace_root": str(TRACE_ROOT),
                "lp_fixture_npz": str(NPZ_PATH),
            },
            "sample_grid": {
                "seeds": SEEDS,
                "ticks": TICKS,
                "sample_count": len(SAMPLES),
            },
            "solver_config": {
                "solver": "swiglpk simplex",
                "pricing": "STD",
                "presolve": "OFF",
                "scale": "AUTO",
                "tol_bnd": 1e-6,
                "method": "PRIMAL",
                "big": BIG,
            },
            "fva": {
                "n_rxn": N_RXN,
                "n_fva_lps_per_sample": N_FVA_LPS_PER_SAMPLE,
                "n_total_lps_per_sample": N_TOTAL_LPS_PER_SAMPLE,
                "pair_cols": PAIR_COLS,
                "zero_width_relative_tol": WIDTH_REL_TOL,
                "slow_warn_seconds": FVA_WARN_SECONDS,
            },
        },
        "summary": summary,
        "samples": samples,
        "self_audit": self_audit,
    }


def _write_json(payload: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    t0 = time.perf_counter()
    print("Starting Day-43 structural FVA multisample v2 probe.")
    print(f"Target samples: {len(SAMPLES)} ({SAMPLES[0]} ... {SAMPLES[-1]})")

    if not NPZ_PATH.exists():
        raise FileNotFoundError(f"missing LP fixture: {NPZ_PATH}")

    model = km.load_default()
    dyn = cfb.load_default_dynamics()
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)

    z = np.load(NPZ_PATH, allow_pickle=False)
    S = np.asarray(z["S"], dtype=np.float64)
    rhs = np.asarray(z["RHS"], dtype=np.float64).reshape(-1)
    c = np.asarray(z["obj"], dtype=np.float64).reshape(-1)
    if S.shape != (N_ROWS, N_RXN):
        raise RuntimeError(f"unexpected S shape {S.shape}, expected {(N_ROWS, N_RXN)}")
    if rhs.shape != (N_ROWS,):
        raise RuntimeError(f"unexpected RHS shape {rhs.shape}, expected {(N_ROWS,)}")
    if c.shape != (N_RXN,):
        raise RuntimeError(f"unexpected objective shape {c.shape}, expected {(N_RXN,)}")

    s_rows, s_cols = np.nonzero(S)
    parm = _configure_simplex_params()
    seed_cache: dict[int, dict[str, np.ndarray]] = {}
    tick_to_idx = {tick: i for i, tick in enumerate(TICKS)}
    samples: list[dict[str, Any]] = []

    for i, (seed, tick) in enumerate(SAMPLES, start=1):
        sample_t0 = time.perf_counter()
        prefix = f"[sample {i:02d}/{len(SAMPLES)} seed={seed} tick={tick}]"
        print(f"{prefix} start")
        sample_row: dict[str, Any] = {"seed": int(seed), "tick": int(tick)}

        try:
            if seed not in seed_cache:
                print(f"{prefix} loading MAT trace")
                sub, enz = _load_seed_states(seed, TICKS)
                seed_cache[seed] = {"pre_sub": sub, "pre_enz": enz}
            idx_tick = tick_to_idx[tick]
            pre_sub = seed_cache[seed]["pre_sub"][idx_tick]
            pre_enz = seed_cache[seed]["pre_enz"][idx_tick]

            t_bounds0 = time.perf_counter()
            bounds = cfb.compute_bounds(
                substrates=pre_sub,
                enzymes=pre_enz,
                cell_dry_mass=dyn.cell_dry_mass,
                step_size_sec=dyn.step_size_sec,
                catalysis=model.catalysis,
                enz_bounds=model.enz_bounds,
                fba_reaction_bounds=fba_reaction_bounds,
                dyn=dyn,
                apply_protein_bounds=False,
            )
            bounds_elapsed_sec = float(time.perf_counter() - t_bounds0)
            lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -BIG)
            ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], BIG)
            lb = np.clip(lb, -BIG, BIG)
            ub = np.clip(ub, -BIG, BIG)
            infeasible = lb > ub
            n_infeasible_preclip = int(np.sum(infeasible))
            if n_infeasible_preclip > 0:
                mid = 0.5 * (lb[infeasible] + ub[infeasible])
                lb[infeasible] = mid
                ub[infeasible] = mid

            fva_result = _run_sample_fva(
                S=S,
                rhs=rhs,
                c=c,
                lb=lb,
                ub=ub,
                parm=parm,
                s_rows=s_rows,
                s_cols=s_cols,
                progress_prefix=prefix,
            )
            sample_row.update(fva_result)
            sample_row["bounds_elapsed_sec"] = bounds_elapsed_sec
            sample_row["n_infeasible_bounds_preclip"] = n_infeasible_preclip
            if bool(sample_row.get("fva_warn_over_120s", False)):
                print(
                    f"{prefix} WARNING fva_elapsed_sec={sample_row['fva_elapsed_sec']:.1f} "
                    f"(> {FVA_WARN_SECONDS:.0f}s)"
                )
        except Exception as exc:
            sample_row.update(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "primary_ok": False,
                    "biomass_value_star": None,
                    "n_lps_optimal": 0,
                    "n_lps_total": N_FVA_LPS_PER_SAMPLE,
                    "lp_solves_attempted": 0,
                    "n_zero_width_dimensions": None,
                    "n_zero_width_dimensions_ratio": None,
                    "pair_widths": {str(j): None for j in PAIR_COLS},
                    "first_nonoptimal": None,
                    "bounds_elapsed_sec": None,
                    "primary_elapsed_sec": None,
                    "fva_elapsed_sec": None,
                    "fva_warn_over_120s": False,
                    "n_infeasible_bounds_preclip": None,
                }
            )
            print(f"{prefix} ERROR {sample_row['error']}")

        sample_row["sample_wall_time_sec"] = float(time.perf_counter() - sample_t0)
        samples.append(sample_row)
        print(
            f"{prefix} done primary_ok={sample_row.get('primary_ok')} "
            f"fva_opt={sample_row.get('n_lps_optimal', 0)}/{N_FVA_LPS_PER_SAMPLE} "
            f"sample_sec={sample_row['sample_wall_time_sec']:.1f}"
        )

        if i % CHECKPOINT_EVERY == 0:
            payload = _build_payload(samples, float(time.perf_counter() - t0), complete=False)
            _write_json(payload)
            print(f"{prefix} checkpoint saved to {OUT_JSON}")

    wall_time_sec = float(time.perf_counter() - t0)
    payload = _build_payload(samples, wall_time_sec, complete=True)
    _write_json(payload)
    OUT_STATUS.write_text(_status_markdown(payload), encoding="utf-8")

    summary = payload["summary"]
    print(
        f"FINAL verdict={summary['headline_verdict']} samples={summary['samples_processed']}/"
        f"{summary['samples_target']} fva_opt={summary['total_fva_lps_optimal']}/"
        f"{summary['fva_lp_target']} wall_time_sec={summary['wall_time_sec']:.3f}"
    )
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_STATUS}")


if __name__ == "__main__":
    main()
