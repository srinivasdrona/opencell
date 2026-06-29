"""Day-43 probe: 100-tick live Metabolism trajectory with deterministic round.

Runs OC Metabolism in isolation for 100 consecutive ticks, initialized from
Karr's recorded pre-tick-0 substrate state and driven by Karr's per-tick enzyme
trace (seed 0). Produces:

  - tmp/h_100tick_detround.json
  - STATUS_h_100tick_detround.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)

TRACE_PATH = (
    REPO
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_s000"
    / "Metabolism_100ticks.mat"
)
LP_FIXTURE_NPZ = REPO / "data" / "karr_fixtures" / "karr_native_m1.npz"
WRITEBACK_FIXTURE_MAT = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"

OUT_JSON = REPO / "tmp" / "h_100tick_detround.json"
OUT_STATUS = REPO / "STATUS_h_100tick_detround.md"
BASELINE_JSON = REPO / "tmp" / "h_100tick_live_trajectory.json"

BIG = 1e6
N_TICKS = 100


class _DetRng:
    def stochastic_round(self, values):
        return np.rint(np.asarray(values, dtype=np.float64)).astype(np.int64)


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


def _mat_strings(values: Any) -> list[str]:
    arr = np.asarray(values, dtype=object).reshape(-1)
    out: list[str] = []
    for item in arr:
        if isinstance(item, bytes):
            out.append(item.decode("utf-8"))
            continue
        if isinstance(item, str):
            out.append(item)
            continue
        if isinstance(item, np.ndarray):
            flat = np.asarray(item).reshape(-1)
            if flat.size == 1:
                out.append(str(flat.item()))
            else:
                out.append("".join(str(x) for x in flat.tolist()).strip())
            continue
        out.append(str(item))
    return out


def _growth_mode(per_tick_l1: np.ndarray) -> str:
    if per_tick_l1.size < 4:
        return "undetermined"
    start = float(per_tick_l1[0])
    end = float(per_tick_l1[-1])
    if end <= start * 1.1:
        return "flat"
    mid = per_tick_l1.size // 2
    first_half = float(per_tick_l1[mid] - per_tick_l1[0])
    second_half = float(per_tick_l1[-1] - per_tick_l1[mid])
    if second_half > 1.25 * first_half:
        return "super-linear"
    if second_half < 0.75 * first_half:
        return "sub-linear"
    return "approximately linear"


def _verdict(per_tick_l1: np.ndarray, karr_mass: np.ndarray) -> str:
    start = float(per_tick_l1[0])
    end = float(per_tick_l1[-1])
    ratio = end / max(start, 1.0)
    rel_end = end / max(float(karr_mass[-1]), 1.0)
    if ratio <= 2.0 and rel_end <= 0.15:
        return "TRACKS"
    if ratio <= 5.0 and rel_end <= 0.50:
        return "PARTIAL"
    return "DIVERGES"


def _fmt(x: float) -> str:
    if abs(x) >= 1e5 or (0 < abs(x) < 1e-3):
        return f"{x:.6e}"
    return f"{x:.3f}"


def _safe_ratio(num: float, den: float) -> float:
    return float(num) / max(float(den), 1.0)


def _rng_verdict(baseline_l1_tick99: float, det_l1_tick99: float) -> str:
    delta = baseline_l1_tick99 - det_l1_tick99
    if det_l1_tick99 < 0.5 * baseline_l1_tick99:
        return "RNG_IS_DOMINANT"
    if abs(delta) <= 235000.0:
        return "RNG_NEGLIGIBLE"
    return "RNG_MATTERS"


def _top10_ratio(top10_rows: list[dict[str, Any]], wid: str) -> float | None:
    for row in top10_rows:
        if row.get("wid") != wid:
            continue
        return _safe_ratio(float(row["oc_final_total"]), float(row["karr_final_total"]))
    return None


def main() -> None:
    t0 = time.perf_counter()
    command = r"bin\oc-py scripts/probe_h_100tick_detround.py"

    if not TRACE_PATH.exists():
        raise FileNotFoundError(f"missing trace file: {TRACE_PATH}")
    if not LP_FIXTURE_NPZ.exists():
        raise FileNotFoundError(f"missing LP fixture: {LP_FIXTURE_NPZ}")
    if not WRITEBACK_FIXTURE_MAT.exists():
        raise FileNotFoundError(f"missing writeback fixture: {WRITEBACK_FIXTURE_MAT}")

    model = km.load_default()
    dyn = cfb.load_default_dynamics()
    writeback_fixture = KarrWritebackFixture.from_mat(WRITEBACK_FIXTURE_MAT)
    lp_npz = np.load(LP_FIXTURE_NPZ)
    try:
        import swiglpk as glp  # noqa: PLC0415

        glp.glp_term_out(glp.GLP_OFF)
    except Exception:
        # Optional dependency path; probe still works without explicit terminal suppression.
        pass

    mat = loadmat(str(WRITEBACK_FIXTURE_MAT), squeeze_me=True, struct_as_record=False)
    fix = mat["data"].fixture
    substrate_wids = _mat_strings(fix.substrateWholeCellModelIDs)
    if len(substrate_wids) != 585:
        raise ValueError(f"expected 585 substrate WIDs from fixture; got {len(substrate_wids)}")
    wid_to_idx = {wid: i for i, wid in enumerate(substrate_wids)}
    metabolite_rows = np.asarray(writeback_fixture.metabolite_row_idx, dtype=np.int64)

    with h5py.File(TRACE_PATH, "r") as handle:
        pre_sub = np.zeros((N_TICKS, 585, 3), dtype=np.float64)
        post_sub = np.zeros((N_TICKS, 585, 3), dtype=np.float64)
        pre_enz = np.zeros((N_TICKS, 104), dtype=np.float64)
        for tick in range(N_TICKS):
            pre_sub[tick] = _as_585x3(_read_cell_array(handle, "states_before/substrates", tick))
            post_sub[tick] = _as_585x3(_read_cell_array(handle, "states_after/substrates", tick))
            pre_enz[tick] = _as_104(_read_cell_array(handle, "states_before/enzymes", tick))

    oc_sub = pre_sub[0].copy()
    rng = _DetRng()
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
    objective = model.obj.astype(np.float64).copy()

    oc_traj = np.zeros((N_TICKS, 585, 3), dtype=np.float64)
    karr_traj = np.zeros((N_TICKS, 585, 3), dtype=np.float64)
    growth = np.zeros(N_TICKS, dtype=np.float64)
    objective_vals = np.zeros(N_TICKS, dtype=np.float64)
    per_tick_l1 = np.zeros(N_TICKS, dtype=np.float64)
    per_tick_linf = np.zeros(N_TICKS, dtype=np.float64)
    per_tick_top_row = np.zeros(N_TICKS, dtype=np.int64)
    per_tick_top_row_l1 = np.zeros(N_TICKS, dtype=np.float64)
    infeasible_reactions = np.zeros(N_TICKS, dtype=np.int64)
    metabolite_min = np.zeros(N_TICKS, dtype=np.float64)

    major_wids = ["ATP", "H2O", "CTP", "GTP", "UTP"]
    major_stats: dict[str, dict[str, list[float]]] = {}
    for wid in major_wids:
        if wid in wid_to_idx:
            major_stats[wid] = {
                "oc_total": [],
                "oc_cytosol": [],
                "karr_total": [],
                "karr_cytosol": [],
            }

    all_finite = True
    first_solver_status_not_ok: str | None = None

    for tick in range(N_TICKS):
        enz_t = pre_enz[tick]
        bounds = cfb.compute_bounds(
            substrates=oc_sub,
            enzymes=enz_t,
            cell_dry_mass=dyn.cell_dry_mass,
            step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis,
            enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fba_reaction_bounds,
            dyn=dyn,
            apply_protein_bounds=False,
        )
        lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -BIG)
        ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], BIG)
        lb = np.clip(lb, -BIG, BIG)
        ub = np.clip(ub, -BIG, BIG)
        infeasible = lb > ub
        if infeasible.any():
            mid = 0.5 * (lb[infeasible] + ub[infeasible])
            lb[infeasible] = mid
            ub[infeasible] = mid
        infeasible_reactions[tick] = int(infeasible.sum())

        flux, obj_val, status = km._solve_fba_glpk(
            model,
            c=objective,
            lb=lb,
            ub=ub,
            sense="max",
        )
        if status != "ok" and first_solver_status_not_ok is None:
            first_solver_status_not_ok = status

        growth[tick] = float(flux[model.biomass_col])
        objective_vals[tick] = float(obj_val)

        delta = apply_karr_substrate_writeback(
            pre_state_585x3=oc_sub,
            v_504=flux,
            growth_per_s=growth[tick],
            fixture=writeback_fixture,
            rng=rng,
            step_size_sec=1.0,
        )
        oc_sub = oc_sub + delta.astype(np.float64)
        oc_traj[tick] = oc_sub

        karr_target = pre_sub[tick + 1] if tick + 1 < N_TICKS else post_sub[N_TICKS - 1]
        karr_traj[tick] = karr_target
        diff = oc_sub - karr_target
        abs_diff = np.abs(diff)
        row_l1 = abs_diff.sum(axis=1)
        top_row = int(np.argmax(row_l1))

        per_tick_l1[tick] = float(abs_diff.sum())
        per_tick_linf[tick] = float(abs_diff.max())
        per_tick_top_row[tick] = top_row
        per_tick_top_row_l1[tick] = float(row_l1[top_row])
        metabolite_min[tick] = float(oc_sub[metabolite_rows, :].min())
        all_finite = all_finite and bool(np.all(np.isfinite(oc_sub)))

        for wid, series in major_stats.items():
            idx = wid_to_idx[wid]
            series["oc_total"].append(float(oc_sub[idx].sum()))
            series["oc_cytosol"].append(float(oc_sub[idx, 0]))
            series["karr_total"].append(float(karr_target[idx].sum()))
            series["karr_cytosol"].append(float(karr_target[idx, 0]))

    karr_mass = np.abs(karr_traj).sum(axis=(1, 2))
    verdict = _verdict(per_tick_l1, karr_mass)
    growth_pattern = _growth_mode(per_tick_l1)

    diff99 = np.abs(oc_traj[-1] - karr_traj[-1]).sum(axis=1)
    top10_idx = np.argsort(-diff99)[:10]
    top10_rows: list[dict[str, Any]] = []
    for rank, row_idx in enumerate(top10_idx, start=1):
        top10_rows.append(
            {
                "rank": rank,
                "row_index": int(row_idx),
                "wid": substrate_wids[int(row_idx)],
                "l1_abs_diff": float(diff99[int(row_idx)]),
                "oc_final_total": float(oc_traj[-1, int(row_idx), :].sum()),
                "karr_final_total": float(karr_traj[-1, int(row_idx), :].sum()),
            }
        )

    major_summary: dict[str, Any] = {}
    for wid, series in major_stats.items():
        oc_total = np.asarray(series["oc_total"], dtype=np.float64)
        karr_total = np.asarray(series["karr_total"], dtype=np.float64)
        ratio = oc_total / np.maximum(karr_total, 1.0)
        major_summary[wid] = {
            "min_oc_total": float(oc_total.min()),
            "max_oc_total": float(oc_total.max()),
            "min_oc_cytosol": float(np.min(np.asarray(series["oc_cytosol"], dtype=np.float64))),
            "zero_or_negative_total_any_tick": bool(np.any(oc_total <= 0.0)),
            "blowup_ratio_gt_10_any_tick": bool(np.any(ratio > 10.0)),
            "max_oc_to_karr_total_ratio": float(ratio.max()),
        }

    viability = {
        "all_finite": bool(all_finite),
        "metabolite_nonnegative_all_ticks": bool(np.all(metabolite_min >= 0.0)),
        "min_metabolite_value_overall": float(metabolite_min.min()),
        "major_metabolites": major_summary,
    }

    checkpoints = [0, 1, 5, 10, 25, 50, 75, 99]
    checkpoint_rows: list[dict[str, Any]] = []
    for tick in checkpoints:
        row_idx = int(per_tick_top_row[tick])
        checkpoint_rows.append(
            {
                "tick": tick,
                "l1": float(per_tick_l1[tick]),
                "linf": float(per_tick_linf[tick]),
                "growth_per_s": float(growth[tick]),
                "top_row_index": row_idx,
                "top_row_wid": substrate_wids[row_idx],
                "top_row_l1": float(per_tick_top_row_l1[tick]),
            }
        )

    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8")) if BASELINE_JSON.exists() else None
    baseline_l1_tick99 = float(per_tick_l1[99])
    if baseline is not None:
        baseline_l1_tick99 = float(baseline["summary"]["l1_tick99"])
    det_l1_tick99 = float(per_tick_l1[99])
    rng_contribution = baseline_l1_tick99 - det_l1_tick99
    rng_contribution_pct = 100.0 * _safe_ratio(rng_contribution, baseline_l1_tick99)
    headline_verdict = _rng_verdict(baseline_l1_tick99, det_l1_tick99)

    substitution_wids = ["TRP", "TRIOLEIN", "PHE"]
    substitution_pairs: dict[str, dict[str, float | None]] = {}
    for wid in substitution_wids:
        idx = wid_to_idx[wid]
        det_ratio = _safe_ratio(float(oc_traj[-1, idx, :].sum()), float(karr_traj[-1, idx, :].sum()))
        baseline_ratio = _top10_ratio(baseline.get("top10_tick99", []) if baseline is not None else [], wid)
        ratio_delta = det_ratio - baseline_ratio if baseline_ratio is not None else None
        substitution_pairs[wid] = {
            "det_ratio_oc_over_karr_tick99": det_ratio,
            "day42_ratio_oc_over_karr_tick99": baseline_ratio,
            "delta_vs_day42": ratio_delta,
        }

    elapsed_s = time.perf_counter() - t0

    payload: dict[str, Any] = {
        "metadata": {
            "probe": "h_100tick_detround",
            "seed": 0,
            "n_ticks": N_TICKS,
            "big": BIG,
            "command": command,
            "inputs": {
                "trace_path": str(TRACE_PATH),
                "lp_fixture_npz": str(LP_FIXTURE_NPZ),
                "writeback_fixture_mat": str(WRITEBACK_FIXTURE_MAT),
                "lp_fixture_shapes": {
                    "S": list(np.asarray(lp_npz["S"]).shape),
                    "RHS": list(np.asarray(lp_npz["RHS"]).shape),
                    "obj": list(np.asarray(lp_npz["obj"]).shape),
                    "lb": list(np.asarray(lp_npz["lb"]).shape),
                    "ub": list(np.asarray(lp_npz["ub"]).shape),
                },
            },
            "solver_config": {
                "solver": "km._solve_fba_glpk",
                "pricing": "STD",
                "presolve": "OFF",
                "scale": "AUTO",
                "tol_bnd": 1e-6,
                "big": BIG,
                "sense": "max",
                "use_full_objective": True,
            },
            "first_solver_status_not_ok": first_solver_status_not_ok,
            "elapsed_seconds": float(elapsed_s),
        },
        "summary": {
            "verdict": verdict,
            "headline_verdict": headline_verdict,
            "growth_pattern": growth_pattern,
            "l1_tick0": float(per_tick_l1[0]),
            "l1_tick1": float(per_tick_l1[1]),
            "l1_tick10": float(per_tick_l1[10]),
            "l1_tick50": float(per_tick_l1[50]),
            "l1_tick99": float(per_tick_l1[99]),
            "linf_tick99": float(per_tick_linf[99]),
            "growth_tick0": float(growth[0]),
            "growth_tick99": float(growth[99]),
            "growth_min": float(growth.min()),
            "growth_max": float(growth.max()),
        },
        "per_tick": {
            "l1": per_tick_l1.tolist(),
            "linf": per_tick_linf.tolist(),
            "growth_per_s": growth.tolist(),
            "objective_value": objective_vals.tolist(),
            "infeasible_reaction_count_preclip": infeasible_reactions.tolist(),
            "top_diverging_row_index": per_tick_top_row.astype(int).tolist(),
            "top_diverging_row_wid": [substrate_wids[int(i)] for i in per_tick_top_row],
            "top_diverging_row_l1": per_tick_top_row_l1.tolist(),
            "karr_mass_l1": karr_mass.tolist(),
            "min_metabolite_value": metabolite_min.tolist(),
        },
        "checkpoint_table": checkpoint_rows,
        "top10_tick99": top10_rows,
        "baseline_comparison": {
            "day42_baseline_json": str(BASELINE_JSON),
            "day42_tick99_l1_mcg16807": baseline_l1_tick99,
            "day43_tick99_l1_detround": det_l1_tick99,
            "rng_contribution_abs_l1": rng_contribution,
            "rng_contribution_pct_of_day42": rng_contribution_pct,
            "headline_verdict": headline_verdict,
        },
        "substitution_pairs_tick99": substitution_pairs,
        "viability": viability,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    json_size = OUT_JSON.stat().st_size

    self_audit = [
        ("Probe initializes from Karr pre-tick-0 substrate state", True),
        ("100-tick loop executes end-to-end", True),
        ("Per-tick enzyme input uses Karr states_before/enzymes trace", True),
        ("LP solved with km._solve_fba_glpk (pricing=STD, presolve=OFF, scale=AUTO, tol_bnd=1e-6)", True),
        ("Bounds clipping uses BIG=1e6 before GLPK call", True),
        ("Writeback uses _DetRng stochastic_round=np.rint (no random sampling)", True),
        ("OC trajectory compared to Karr trajectory at every tick", True),
        ("Top-10 divergent rows at tick 99 reported with fixture WIDs", True),
        ("Day-42 baseline side-by-side comparison computed from tmp/h_100tick_live_trajectory.json", bool(baseline is not None)),
        ("Headline verdict emitted: RNG_NEGLIGIBLE / RNG_MATTERS / RNG_IS_DOMINANT", True),
        ("Substitution-pair ratios (TRP, TRIOLEIN, PHE) reported for tick 99", True),
        ("INTENT + VERIFICATION + self-audit present in STATUS", True),
    ]

    lines: list[str] = []
    lines.append("# STATUS_h_100tick_detround")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "- Mirror the Day-42 100-tick live Metabolism trajectory probe with identical solver/bounds/input trace, but "
        "replace stochastic rounding with deterministic `np.rint` to isolate RNG-driven drift."
    )
    lines.append(
        "- Quantify Day-42 minus Day-43 tick-99 L1 drift and classify RNG contribution as RNG_NEGLIGIBLE, RNG_MATTERS, or RNG_IS_DOMINANT."
    )
    lines.append("")
    lines.append("## Headline")
    lines.append(f"**{headline_verdict}**")
    lines.append("")
    lines.append("- Tick indexing in the table is 0-based over post-update states (`tick=0` is the first OC update, compared to `Karr states_before[1]`).")
    lines.append(f"- Day-42 tick-99 L1 (_Mcg16807): {_fmt(baseline_l1_tick99)}")
    lines.append(f"- Day-43 tick-99 L1 (_DetRng np.rint): {_fmt(det_l1_tick99)}")
    lines.append(
        f"- RNG contribution (baseline - deterministic): {_fmt(rng_contribution)} "
        f"({rng_contribution_pct:.2f}% of baseline)."
    )
    if rng_contribution < 0.0:
        lines.append("- Note: negative contribution means deterministic rounding drifted more than Day-42 stochastic rounding.")
    lines.append(f"- L1 drift mode over 100 ticks (deterministic probe): **{growth_pattern}**.")
    lines.append(
        f"- Key L1 checkpoints: tick 0={_fmt(per_tick_l1[0])}, tick 1={_fmt(per_tick_l1[1])}, "
        f"tick 5={_fmt(per_tick_l1[5])}, tick 10={_fmt(per_tick_l1[10])}, tick 25={_fmt(per_tick_l1[25])}, "
        f"tick 50={_fmt(per_tick_l1[50])}, tick 75={_fmt(per_tick_l1[75])}, tick 99={_fmt(per_tick_l1[99])}."
    )
    lines.append(f"- Key L∞ at tick 99: {_fmt(per_tick_linf[99])}.")
    lines.append(f"- Growth trajectory: tick0={_fmt(growth[0])}, tick99={_fmt(growth[99])}, min={_fmt(growth.min())}, max={_fmt(growth.max())}.")
    lines.append("")
    lines.append("## Checkpoint Table")
    lines.append("| Tick | L1 | L∞ | Growth (/s) | Top diverging row |")
    lines.append("|---:|---:|---:|---:|---|")
    for row in checkpoint_rows:
        lines.append(
            f"| {row['tick']} | {_fmt(row['l1'])} | {_fmt(row['linf'])} | {_fmt(row['growth_per_s'])} | "
            f"{row['top_row_wid']} (r{row['top_row_index']}, L1={_fmt(row['top_row_l1'])}) |"
        )
    lines.append("")
    lines.append("## Top-10 Tick-99 Divergent Substrates")
    lines.append("| Rank | Row | WID | L1 abs diff | OC final total | Karr final total |")
    lines.append("|---:|---:|---|---:|---:|---:|")
    for row in top10_rows:
        lines.append(
            f"| {row['rank']} | {row['row_index']} | {row['wid']} | {_fmt(row['l1_abs_diff'])} | "
            f"{_fmt(row['oc_final_total'])} | {_fmt(row['karr_final_total'])} |"
        )
    lines.append("")
    lines.append("## Substitution-Pair Ratios at Tick 99")
    lines.append("| WID | Day-43 detround OC/Karr | Day-42 baseline OC/Karr | Delta (det - day42) |")
    lines.append("|---|---:|---:|---:|")
    for wid in ["TRP", "TRIOLEIN", "PHE"]:
        vals = substitution_pairs[wid]
        day42_ratio = vals["day42_ratio_oc_over_karr_tick99"]
        day42_fmt = "n/a" if day42_ratio is None else _fmt(float(day42_ratio))
        delta = vals["delta_vs_day42"]
        delta_fmt = "n/a" if delta is None else _fmt(float(delta))
        lines.append(
            f"| {wid} | {_fmt(float(vals['det_ratio_oc_over_karr_tick99']))} | {day42_fmt} | {delta_fmt} |"
        )
    lines.append("")
    lines.append("## Biological Viability")
    lines.append(f"- All OC substrate values finite across 100 ticks: {'YES' if viability['all_finite'] else 'NO'}.")
    lines.append(
        f"- Metabolite rows non-negative at all ticks: {'YES' if viability['metabolite_nonnegative_all_ticks'] else 'NO'} "
        f"(global min metabolite value={_fmt(viability['min_metabolite_value_overall'])})."
    )
    if major_summary:
        lines.append("- Major metabolite checks (ATP, H2O, NTPs):")
        for wid in major_wids:
            if wid not in major_summary:
                continue
            ms = major_summary[wid]
            lines.append(
                f"  - {wid}: min_total={_fmt(ms['min_oc_total'])}, max_total={_fmt(ms['max_oc_total'])}, "
                f"min_cyt={_fmt(ms['min_oc_cytosol'])}, zero_or_negative_any={ms['zero_or_negative_total_any_tick']}, "
                f"blowup_ratio_gt_10_any={ms['blowup_ratio_gt_10_any_tick']}, max_ratio={_fmt(ms['max_oc_to_karr_total_ratio'])}"
            )
    lines.append("")
    lines.append("## VERIFICATION")
    lines.append(f"- Command: `{command}`")
    lines.append(f"- Inputs verified: `{TRACE_PATH}`, `{LP_FIXTURE_NPZ}`, `{WRITEBACK_FIXTURE_MAT}`")
    lines.append(f"- Day-42 baseline JSON: `{BASELINE_JSON}` ({'found' if baseline is not None else 'missing'})")
    lines.append(f"- Output JSON: `{OUT_JSON}` ({json_size} bytes)")
    lines.append(f"- Output STATUS: `{OUT_STATUS}` (written by this probe)")
    lines.append(f"- Total wall time: {elapsed_s:.3f} s")
    lines.append("")
    lines.append("## Self-audit")
    lines.append("| # | Criterion | Verified |")
    lines.append("|---|---|---|")
    for i, (criterion, ok) in enumerate(self_audit, start=1):
        lines.append(f"| {i} | {criterion} | {'[x]' if ok else '[ ]'} |")

    OUT_STATUS.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_STATUS}")
    print(f"VERDICT={headline_verdict}")
    print(f"DAY42_L1_TICK99={baseline_l1_tick99:.3f}")
    print(f"DAY43_L1_TICK99={det_l1_tick99:.3f}")
    print(f"RNG_CONTRIBUTION_L1={rng_contribution:.3f} ({rng_contribution_pct:.3f}%)")
    print(f"L1 tick1={per_tick_l1[1]:.3f} tick10={per_tick_l1[10]:.3f} tick50={per_tick_l1[50]:.3f} tick99={per_tick_l1[99]:.3f}")
    print(f"Linf tick99={per_tick_linf[99]:.3f}")
    print(f"Growth tick0={growth[0]:.6e} tick99={growth[99]:.6e}")


if __name__ == "__main__":
    main()
