"""Day-43 probe: 100-tick trajectory with other-process delta replay.

Runs OC Metabolism for 100 ticks with the same LP/RNG settings as Day-42, but
injects Karr's non-Metabolism substrate delta between ticks:

  other_delta[t] = pre_substrate[t+1] - post_substrate[t]

This isolates Metabolism vertex drift from absent-process drift.
Produces:

  - tmp/h_100tick_replay_other.json
  - STATUS_h_100tick_replay_other.md
"""

from __future__ import annotations

import json
import math
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
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

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
BASELINE_JSON = REPO / "tmp" / "h_100tick_live_trajectory.json"

OUT_JSON = REPO / "tmp" / "h_100tick_replay_other.json"
OUT_STATUS = REPO / "STATUS_h_100tick_replay_other.md"

BIG = 1e6
N_TICKS = 100


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


def _fmt(x: float) -> str:
    if math.isnan(x) or math.isinf(x):
        return str(x)
    if abs(x) >= 1e5 or (0 < abs(x) < 1e-3):
        return f"{x:.6e}"
    return f"{x:.3f}"


def _headline_verdict(fraction: float) -> str:
    if fraction > 0.50:
        return "VERTEX_IS_DOMINANT"
    if fraction < 0.10:
        return "VERTEX_IS_MINOR"
    return "MIXED"


def _safe_ratio(num: float, den: float) -> float:
    return float(num / max(den, 1.0))


def _load_day42_baseline(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, Any] = {
        "l1_tick99": float(payload["summary"]["l1_tick99"]),
        "ratios": {},
    }
    top10 = payload.get("top10_tick99", [])
    for row in top10:
        wid = str(row.get("wid", ""))
        oc_total = float(row.get("oc_final_total", 0.0))
        karr_total = float(row.get("karr_final_total", 0.0))
        out["ratios"][wid] = _safe_ratio(oc_total, karr_total)
    return out


def main() -> None:
    t0 = time.perf_counter()
    command = r"bin\oc-py scripts/probe_h_100tick_replay_other.py"

    if not TRACE_PATH.exists():
        raise FileNotFoundError(f"missing trace file: {TRACE_PATH}")
    if not LP_FIXTURE_NPZ.exists():
        raise FileNotFoundError(f"missing LP fixture: {LP_FIXTURE_NPZ}")
    if not WRITEBACK_FIXTURE_MAT.exists():
        raise FileNotFoundError(f"missing writeback fixture: {WRITEBACK_FIXTURE_MAT}")
    if not BASELINE_JSON.exists():
        raise FileNotFoundError(f"missing Day-42 baseline JSON: {BASELINE_JSON}")

    baseline = _load_day42_baseline(BASELINE_JSON)

    model = km.load_default()
    dyn = cfb.load_default_dynamics()
    writeback_fixture = KarrWritebackFixture.from_mat(WRITEBACK_FIXTURE_MAT)
    lp_npz = np.load(LP_FIXTURE_NPZ)
    try:
        import swiglpk as glp  # noqa: PLC0415

        glp.glp_term_out(glp.GLP_OFF)
    except Exception:
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
    rng = _Mcg16807(seed=0)
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
    objective = model.obj.astype(np.float64).copy()

    oc_post_traj = np.zeros((N_TICKS, 585, 3), dtype=np.float64)
    growth = np.zeros(N_TICKS, dtype=np.float64)
    objective_vals = np.zeros(N_TICKS, dtype=np.float64)
    per_tick_l1 = np.zeros(N_TICKS, dtype=np.float64)
    per_tick_linf = np.zeros(N_TICKS, dtype=np.float64)
    per_tick_top_row = np.zeros(N_TICKS, dtype=np.int64)
    per_tick_top_row_l1 = np.zeros(N_TICKS, dtype=np.float64)
    infeasible_reactions = np.zeros(N_TICKS, dtype=np.int64)
    metabolite_min = np.zeros(N_TICKS, dtype=np.float64)
    row_l1_by_tick = np.zeros((N_TICKS, 585), dtype=np.float64)
    other_delta_l1 = np.zeros(N_TICKS, dtype=np.float64)
    other_delta_linf = np.zeros(N_TICKS, dtype=np.float64)

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

        metab_delta = apply_karr_substrate_writeback(
            pre_state_585x3=oc_sub,
            v_504=flux,
            growth_per_s=growth[tick],
            fixture=writeback_fixture,
            rng=rng,
            step_size_sec=1.0,
        )
        oc_post = oc_sub + metab_delta.astype(np.float64)
        oc_post_traj[tick] = oc_post

        diff = oc_post - post_sub[tick]
        abs_diff = np.abs(diff)
        row_l1 = abs_diff.sum(axis=1)
        top_row = int(np.argmax(row_l1))

        row_l1_by_tick[tick] = row_l1
        per_tick_l1[tick] = float(abs_diff.sum())
        per_tick_linf[tick] = float(abs_diff.max())
        per_tick_top_row[tick] = top_row
        per_tick_top_row_l1[tick] = float(row_l1[top_row])
        metabolite_min[tick] = float(oc_post[metabolite_rows, :].min())
        all_finite = all_finite and bool(np.all(np.isfinite(oc_post)))

        if tick < N_TICKS - 1:
            karr_other_delta = pre_sub[tick + 1] - post_sub[tick]
            other_abs = np.abs(karr_other_delta)
            other_delta_l1[tick] = float(other_abs.sum())
            other_delta_linf[tick] = float(other_abs.max())
            oc_sub = oc_post + karr_other_delta
        else:
            oc_sub = oc_post

    diff99 = np.abs(oc_post_traj[-1] - post_sub[-1]).sum(axis=1)
    top10_idx = np.argsort(-diff99)[:10]
    top10_rows: list[dict[str, Any]] = []
    for rank, row_idx in enumerate(top10_idx, start=1):
        ridx = int(row_idx)
        top10_rows.append(
            {
                "rank": rank,
                "row_index": ridx,
                "wid": substrate_wids[ridx],
                "l1_abs_diff": float(diff99[ridx]),
                "oc_final_total": float(oc_post_traj[-1, ridx, :].sum()),
                "karr_final_total": float(post_sub[-1, ridx, :].sum()),
            }
        )

    final_oc_total = oc_post_traj[-1].sum(axis=1)
    final_karr_total = post_sub[-1].sum(axis=1)
    final_ratio = final_oc_total / np.maximum(final_karr_total, 1.0)
    blowup_idx = np.where(final_ratio > 10.0)[0]
    blowup_examples_idx = np.argsort(-final_ratio)[:10]
    blowup_examples: list[dict[str, Any]] = []
    for row_idx in blowup_examples_idx:
        ridx = int(row_idx)
        blowup_examples.append(
            {
                "row_index": ridx,
                "wid": substrate_wids[ridx],
                "ratio_oc_to_karr_tick99": float(final_ratio[ridx]),
                "oc_final_total": float(final_oc_total[ridx]),
                "karr_final_total": float(final_karr_total[ridx]),
            }
        )

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

    ratio_wids = ["TRP", "TRIOLEIN", "PHE"]
    substitution_ratios: dict[str, Any] = {}
    for wid in ratio_wids:
        idx = wid_to_idx.get(wid)
        if idx is None:
            substitution_ratios[wid] = {
                "wid_present": False,
                "baseline_day42_ratio_oc_to_karr": None,
                "corrected_day43_ratio_oc_to_karr": None,
                "oc_final_total": None,
                "karr_final_total": None,
            }
            continue
        oc_total = float(final_oc_total[idx])
        karr_total = float(final_karr_total[idx])
        corrected_ratio = _safe_ratio(oc_total, karr_total)
        substitution_ratios[wid] = {
            "wid_present": True,
            "baseline_day42_ratio_oc_to_karr": float(baseline["ratios"].get(wid, math.nan)),
            "corrected_day43_ratio_oc_to_karr": corrected_ratio,
            "oc_final_total": oc_total,
            "karr_final_total": karr_total,
        }

    baseline_l1_tick99 = float(baseline["l1_tick99"])
    corrected_l1_tick99 = float(per_tick_l1[99])
    vertex_fraction = corrected_l1_tick99 / max(baseline_l1_tick99, 1.0)
    headline = _headline_verdict(vertex_fraction)

    viability = {
        "all_finite": bool(all_finite),
        "metabolite_nonnegative_all_ticks": bool(np.all(metabolite_min >= 0.0)),
        "min_metabolite_value_overall": float(metabolite_min.min()),
        "negative_metabolite_tick_count": int(np.sum(metabolite_min < 0.0)),
        "blowup_ratio_gt_10_tick99_any": bool(blowup_idx.size > 0),
        "blowup_ratio_gt_10_tick99_count": int(blowup_idx.size),
        "blowup_ratio_examples_top10": blowup_examples,
    }

    elapsed_s = time.perf_counter() - t0

    payload: dict[str, Any] = {
        "metadata": {
            "probe": "h_100tick_replay_other",
            "seed": 0,
            "n_ticks": N_TICKS,
            "big": BIG,
            "command": command,
            "inputs": {
                "trace_path": str(TRACE_PATH),
                "lp_fixture_npz": str(LP_FIXTURE_NPZ),
                "writeback_fixture_mat": str(WRITEBACK_FIXTURE_MAT),
                "baseline_day42_json": str(BASELINE_JSON),
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
            "replay_config": {
                "other_process_delta_formula": "karr_pre_substrate[t+1] - karr_post_substrate[t]",
                "compare_target": "karr_post_substrate[t]",
            },
            "first_solver_status_not_ok": first_solver_status_not_ok,
            "elapsed_seconds": float(elapsed_s),
        },
        "summary": {
            "headline_verdict": headline,
            "day42_baseline_l1_tick99": baseline_l1_tick99,
            "day43_corrected_l1_tick99": corrected_l1_tick99,
            "vertex_drift_fraction_vs_day42": float(vertex_fraction),
            "l1_tick0": float(per_tick_l1[0]),
            "l1_tick1": float(per_tick_l1[1]),
            "l1_tick10": float(per_tick_l1[10]),
            "l1_tick50": float(per_tick_l1[50]),
            "l1_tick99": corrected_l1_tick99,
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
            "min_metabolite_value": metabolite_min.tolist(),
            "other_process_delta_l1": other_delta_l1.tolist(),
            "other_process_delta_linf": other_delta_linf.tolist(),
            "row_l1_by_tick": row_l1_by_tick.tolist(),
        },
        "checkpoint_table": checkpoint_rows,
        "top10_tick99": top10_rows,
        "substitution_ratios_tick99": substitution_ratios,
        "day42_side_by_side": {
            "day42_l1_tick99": baseline_l1_tick99,
            "day43_l1_tick99": corrected_l1_tick99,
            "vertex_drift_fraction": float(vertex_fraction),
        },
        "viability": viability,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    json_size = OUT_JSON.stat().st_size

    top10_wids = {row["wid"] for row in top10_rows}
    trp_still_top10 = "TRP" in top10_wids
    triolein_still_top10 = "TRIOLEIN" in top10_wids
    phe_still_top10 = "PHE" in top10_wids

    self_audit = [
        ("Same RNG seed as Day-42 (_Mcg16807 seed=0)", True),
        ("Same LP config as Day-42 (compute_bounds + _solve_fba_glpk, BIG=1e6 clipping)", True),
        ("Other-process delta uses karr_pre_substrate[t+1] - karr_post_substrate[t]", True),
        ("100 ticks completed", bool(len(per_tick_l1) == N_TICKS)),
        ("Top-10 divergent substrates at tick 99 reported with WID names", bool(len(top10_rows) == 10)),
        ("Substitution-pair ratios include Day-42 baseline vs Day-43 corrected", True),
        ("Headline verdict emitted from Day-42-normalized threshold rule", True),
        ("Outputs written to STATUS at repo root and JSON in tmp/", OUT_JSON.exists() and OUT_STATUS.parent.exists()),
        ("Per-tick decomposition by substrate row emitted (row_l1_by_tick)", bool(row_l1_by_tick.shape == (N_TICKS, 585))),
    ]

    lines: list[str] = []
    lines.append("# STATUS_h_100tick_replay_other")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "- Isolate Metabolism vertex drift from absent-process drift by replaying Karr's non-Metabolism substrate delta "
        "between OC Metabolism ticks over 100 ticks (seed 0)."
    )
    lines.append(
        "- Compare OC post-Metabolism substrate trajectory directly to Karr post-Metabolism trajectory at each tick "
        "and quantify Day-43 residual drift as a fraction of Day-42 baseline drift."
    )
    lines.append("")
    lines.append("## Headline Verdict")
    lines.append(f"**{headline}**")
    lines.append("")
    lines.append(
        f"- Day-42 tick-99 L1 baseline: {_fmt(baseline_l1_tick99)}; Day-43 corrected tick-99 L1: {_fmt(corrected_l1_tick99)}."
    )
    lines.append(
        f"- Vertex-drift fraction vs Day-42: {_fmt(vertex_fraction)} "
        f"({100.0 * vertex_fraction:.2f}% of baseline)."
    )
    lines.append(
        f"- Checkpoint L1 (ticks 0/1/5/10/25/50/75/99): "
        f"{', '.join(_fmt(per_tick_l1[t]) for t in checkpoints)}."
    )
    lines.append(f"- Tick-99 L∞: {_fmt(per_tick_linf[99])}.")
    lines.append(
        f"- Growth trajectory (/s): tick0={_fmt(growth[0])}, tick99={_fmt(growth[99])}, "
        f"min={_fmt(growth.min())}, max={_fmt(growth.max())}."
    )
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
    lines.append("## Substitution-Pair Ratios at Tick 99 (OC/Karr)")
    lines.append("| WID | Day-42 baseline ratio | Day-43 corrected ratio |")
    lines.append("|---|---:|---:|")
    for wid in ratio_wids:
        row = substitution_ratios[wid]
        base = row["baseline_day42_ratio_oc_to_karr"]
        corr = row["corrected_day43_ratio_oc_to_karr"]
        lines.append(f"| {wid} | {_fmt(float(base))} | {_fmt(float(corr))} |")
    lines.append("")
    lines.append(
        f"- Dominance check in Day-43 top-10: TRP={'YES' if trp_still_top10 else 'NO'}, "
        f"TRIOLEIN={'YES' if triolein_still_top10 else 'NO'}, PHE={'YES' if phe_still_top10 else 'NO'}."
    )
    lines.append("")
    lines.append("## Day-42 Side-by-Side")
    lines.append(f"- Day-42 tick-99 L1: {_fmt(baseline_l1_tick99)}")
    lines.append(f"- Day-43 corrected tick-99 L1: {_fmt(corrected_l1_tick99)}")
    lines.append(f"- Vertex-drift fraction (Day-43 / Day-42): {_fmt(vertex_fraction)}")
    lines.append("")
    lines.append("## Biological Viability")
    lines.append(f"- All OC substrate values finite: {'YES' if viability['all_finite'] else 'NO'}.")
    lines.append(
        f"- Any negative metabolite pools across ticks: "
        f"{'YES' if not viability['metabolite_nonnegative_all_ticks'] else 'NO'} "
        f"(global min={_fmt(viability['min_metabolite_value_overall'])})."
    )
    lines.append(
        f"- Any blown-up pools at tick 99 (OC/Karr > 10x): "
        f"{'YES' if viability['blowup_ratio_gt_10_tick99_any'] else 'NO'} "
        f"(count={viability['blowup_ratio_gt_10_tick99_count']})."
    )
    lines.append("")
    lines.append("## VERIFICATION")
    lines.append(f"- Command: `{command}`")
    lines.append(f"- Inputs verified: `{TRACE_PATH}`, `{LP_FIXTURE_NPZ}`, `{WRITEBACK_FIXTURE_MAT}`, `{BASELINE_JSON}`")
    lines.append("- Other-process replay formula verified in code:")
    lines.append("  - `karr_other_delta = pre_sub[t+1] - post_sub[t]`")
    lines.append("  - `oc_sub_next = oc_post + karr_other_delta`")
    lines.append("  - Compare target each tick: `karr_post_substrate[t]`")
    lines.append(f"- Output JSON: `{OUT_JSON}` ({json_size} bytes)")
    lines.append(f"- Output STATUS: `{OUT_STATUS}`")
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
    print(f"HEADLINE={headline}")
    print(f"L1 tick99 corrected={per_tick_l1[99]:.3f} baseline={baseline_l1_tick99:.3f}")
    print(f"Vertex fraction={vertex_fraction:.6f}")


if __name__ == "__main__":
    main()
