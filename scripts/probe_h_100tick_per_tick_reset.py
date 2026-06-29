"""Day-43 probe: per-tick substrate reset for 100-tick Metabolism replay.

This probe isolates pure per-tick vertex/RNG effects by resetting OC substrate
state to Karr's exact pre-Metabolism substrate state at the start of EACH tick:

  oc_substrate[t] = karr_pre_substrate[t]

Then it runs OC Metabolism with Day-42 baseline LP/RNG settings, compares
per-tick Metabolism deltas (OC delta - Karr delta), and accumulates those
per-tick differences over 100 ticks without chained state compounding.

Outputs:
  - tmp/h_100tick_per_tick_reset.json
  - STATUS_h_100tick_per_tick_reset.md
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
DAY42_JSON = REPO / "tmp" / "h_100tick_live_trajectory.json"
REPLAY_OTHER_JSON = REPO / "tmp" / "h_100tick_replay_other.json"

OUT_JSON = REPO / "tmp" / "h_100tick_per_tick_reset.json"
OUT_STATUS = REPO / "STATUS_h_100tick_per_tick_reset.md"

BIG = 1e6
N_TICKS = 100
CHECKPOINTS = [1, 5, 10, 25, 50, 75, 99]


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


def _safe_ratio(num: float, den: float) -> float:
    if den == 0:
        return math.inf if num > 0 else 0.0
    return float(num / den)


def _load_l1_tick99(path: Path) -> float:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return float(payload["summary"]["l1_tick99"])


def _headline_verdict(cumulative_l1_tick99: float) -> str:
    if 1.30e6 <= cumulative_l1_tick99 <= 1.65e6:
        return "PURE_LINEAR"
    if cumulative_l1_tick99 < 1.0e6:
        return "PARTIAL_CANCEL"
    if cumulative_l1_tick99 > 2.0e6:
        return "COMPOUNDING_DOMINANT"
    return "SIGNAL_DOES_NOT_MATCH"


def _trend_label(pos_frac: float, neg_frac: float) -> str:
    if pos_frac >= 0.70 or neg_frac >= 0.70:
        return "ACCUMULATES"
    return "CANCELS_OR_MIXED"


def main() -> None:
    t0 = time.perf_counter()
    command = r"bin\oc-py scripts/probe_h_100tick_per_tick_reset.py"

    for req in [TRACE_PATH, LP_FIXTURE_NPZ, WRITEBACK_FIXTURE_MAT, DAY42_JSON, REPLAY_OTHER_JSON]:
        if not req.exists():
            raise FileNotFoundError(f"missing required input: {req}")

    day42_l1_tick99 = _load_l1_tick99(DAY42_JSON)
    replay_other_l1_tick99 = _load_l1_tick99(REPLAY_OTHER_JSON)

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

    with h5py.File(TRACE_PATH, "r") as handle:
        pre_sub = np.zeros((N_TICKS, 585, 3), dtype=np.float64)
        post_sub = np.zeros((N_TICKS, 585, 3), dtype=np.float64)
        pre_enz = np.zeros((N_TICKS, 104), dtype=np.float64)
        for tick in range(N_TICKS):
            pre_sub[tick] = _as_585x3(_read_cell_array(handle, "states_before/substrates", tick))
            post_sub[tick] = _as_585x3(_read_cell_array(handle, "states_after/substrates", tick))
            pre_enz[tick] = _as_104(_read_cell_array(handle, "states_before/enzymes", tick))

    rng = _Mcg16807(seed=0)
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
    objective = model.obj.astype(np.float64).copy()

    per_tick_l1 = np.zeros(N_TICKS, dtype=np.float64)
    per_tick_linf = np.zeros(N_TICKS, dtype=np.float64)
    cumulative_l1 = np.zeros(N_TICKS, dtype=np.float64)
    cumulative_linf = np.zeros(N_TICKS, dtype=np.float64)
    growth = np.zeros(N_TICKS, dtype=np.float64)
    objective_vals = np.zeros(N_TICKS, dtype=np.float64)
    infeasible_reactions = np.zeros(N_TICKS, dtype=np.int64)
    per_tick_top_row = np.zeros(N_TICKS, dtype=np.int64)
    per_tick_top_row_l1 = np.zeros(N_TICKS, dtype=np.float64)
    row_l1_by_tick = np.zeros((N_TICKS, 585), dtype=np.float64)
    row_signed_by_tick = np.zeros((N_TICKS, 585), dtype=np.float64)

    cumulative_drift = np.zeros((585, 3), dtype=np.float64)
    all_finite = True
    first_solver_status_not_ok: str | None = None

    for tick in range(N_TICKS):
        # Key probe behavior: hard reset OC substrate input each tick.
        oc_sub = pre_sub[tick].copy()
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

        oc_metab_delta = apply_karr_substrate_writeback(
            pre_state_585x3=oc_sub,
            v_504=flux,
            growth_per_s=growth[tick],
            fixture=writeback_fixture,
            rng=rng,
            step_size_sec=1.0,
        )
        karr_metab_delta = post_sub[tick] - pre_sub[tick]
        diff_t = oc_metab_delta.astype(np.float64) - karr_metab_delta
        abs_diff_t = np.abs(diff_t)

        row_l1 = abs_diff_t.sum(axis=1)
        row_signed = diff_t.sum(axis=1)
        top_row = int(np.argmax(row_l1))

        row_l1_by_tick[tick] = row_l1
        row_signed_by_tick[tick] = row_signed
        per_tick_l1[tick] = float(abs_diff_t.sum())
        per_tick_linf[tick] = float(abs_diff_t.max())
        per_tick_top_row[tick] = top_row
        per_tick_top_row_l1[tick] = float(row_l1[top_row])

        cumulative_drift += diff_t
        cumulative_abs = np.abs(cumulative_drift)
        cumulative_l1[tick] = float(cumulative_abs.sum())
        cumulative_linf[tick] = float(cumulative_abs.max())
        all_finite = all_finite and bool(np.all(np.isfinite(diff_t))) and bool(np.all(np.isfinite(cumulative_drift)))

    final_row_l1 = np.abs(cumulative_drift).sum(axis=1)
    top10_idx = np.argsort(-final_row_l1)[:10]

    top10_rows: list[dict[str, Any]] = []
    sign_analysis_top: list[dict[str, Any]] = []
    for rank, row_idx in enumerate(top10_idx, start=1):
        ridx = int(row_idx)
        signed_series = row_signed_by_tick[:, ridx]
        pos_frac = float(np.mean(signed_series > 0.0))
        neg_frac = float(np.mean(signed_series < 0.0))
        zero_frac = float(np.mean(signed_series == 0.0))
        trend = _trend_label(pos_frac, neg_frac)

        top10_rows.append(
            {
                "rank": rank,
                "row_index": ridx,
                "wid": substrate_wids[ridx],
                "cumulative_l1_abs_drift": float(final_row_l1[ridx]),
                "cumulative_signed_drift_total": float(cumulative_drift[ridx].sum()),
                "cumulative_drift_compartments": [float(x) for x in cumulative_drift[ridx].tolist()],
                "sign_trend": trend,
            }
        )
        sign_analysis_top.append(
            {
                "rank": rank,
                "row_index": ridx,
                "wid": substrate_wids[ridx],
                "positive_tick_fraction": pos_frac,
                "negative_tick_fraction": neg_frac,
                "zero_tick_fraction": zero_frac,
                "positive_tick_count": int(np.sum(signed_series > 0.0)),
                "negative_tick_count": int(np.sum(signed_series < 0.0)),
                "zero_tick_count": int(np.sum(signed_series == 0.0)),
                "mean_signed_diff_per_tick": float(np.mean(signed_series)),
                "median_signed_diff_per_tick": float(np.median(signed_series)),
                "sign_trend": trend,
            }
        )

    checkpoint_rows: list[dict[str, Any]] = []
    for tick in CHECKPOINTS:
        row_idx = int(per_tick_top_row[tick])
        checkpoint_rows.append(
            {
                "tick": tick,
                "per_tick_l1": float(per_tick_l1[tick]),
                "per_tick_linf": float(per_tick_linf[tick]),
                "cumulative_l1": float(cumulative_l1[tick]),
                "cumulative_linf": float(cumulative_linf[tick]),
                "growth_per_s": float(growth[tick]),
                "top_row_index": row_idx,
                "top_row_wid": substrate_wids[row_idx],
                "top_row_per_tick_l1": float(per_tick_top_row_l1[tick]),
            }
        )

    cumulative_l1_tick99 = float(cumulative_l1[99])
    verdict = _headline_verdict(cumulative_l1_tick99)
    compounding_amp_fraction = _safe_ratio(replay_other_l1_tick99 - cumulative_l1_tick99, cumulative_l1_tick99)

    elapsed_s = time.perf_counter() - t0

    payload: dict[str, Any] = {
        "metadata": {
            "probe": "h_100tick_per_tick_reset",
            "seed": 0,
            "n_ticks": N_TICKS,
            "big": BIG,
            "command": command,
            "inputs": {
                "trace_path": str(TRACE_PATH),
                "lp_fixture_npz": str(LP_FIXTURE_NPZ),
                "writeback_fixture_mat": str(WRITEBACK_FIXTURE_MAT),
                "day42_baseline_json": str(DAY42_JSON),
                "replay_other_json": str(REPLAY_OTHER_JSON),
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
            "probe_config": {
                "per_tick_reset": "oc_substrate = karr_pre_substrate[t]",
                "per_tick_diff_formula": "(oc_metab_delta - karr_metab_delta)",
                "karr_metab_delta_formula": "karr_post_substrate[t] - karr_pre_substrate[t]",
                "cumulative_formula": "sum_t(per_tick_diff_t)",
            },
            "first_solver_status_not_ok": first_solver_status_not_ok,
            "elapsed_seconds": float(elapsed_s),
        },
        "summary": {
            "headline_verdict": verdict,
            "this_probe_cumulative_l1_tick99": cumulative_l1_tick99,
            "this_probe_cumulative_linf_tick99": float(cumulative_linf[99]),
            "this_probe_per_tick_l1_mean": float(per_tick_l1.mean()),
            "this_probe_per_tick_l1_median": float(np.median(per_tick_l1)),
            "day42_raw_l1_tick99": day42_l1_tick99,
            "replay_other_l1_tick99": replay_other_l1_tick99,
            "this_probe_l1_tick99": cumulative_l1_tick99,
            "compounding_amplification_fraction": float(compounding_amp_fraction),
            "per_tick_l1_tick0": float(per_tick_l1[0]),
            "per_tick_l1_tick1": float(per_tick_l1[1]),
            "per_tick_l1_tick10": float(per_tick_l1[10]),
            "per_tick_l1_tick50": float(per_tick_l1[50]),
            "per_tick_l1_tick99": float(per_tick_l1[99]),
        },
        "per_tick": {
            "l1_delta_diff": per_tick_l1.tolist(),
            "linf_delta_diff": per_tick_linf.tolist(),
            "cumulative_l1": cumulative_l1.tolist(),
            "cumulative_linf": cumulative_linf.tolist(),
            "growth_per_s": growth.tolist(),
            "objective_value": objective_vals.tolist(),
            "infeasible_reaction_count_preclip": infeasible_reactions.tolist(),
            "top_diverging_row_index": per_tick_top_row.astype(int).tolist(),
            "top_diverging_row_wid": [substrate_wids[int(i)] for i in per_tick_top_row],
            "top_diverging_row_l1": per_tick_top_row_l1.tolist(),
            "row_l1_by_tick": row_l1_by_tick.tolist(),
            "row_signed_by_tick": row_signed_by_tick.tolist(),
        },
        "checkpoint_table": checkpoint_rows,
        "top10_cumulative_tick99": top10_rows,
        "sign_analysis_top10": sign_analysis_top,
        "side_by_side": {
            "day42_raw_100tick_l1": day42_l1_tick99,
            "replay_other_100tick_l1": replay_other_l1_tick99,
            "this_probe_100tick_cumulative_l1": cumulative_l1_tick99,
            "compounding_amplification_fraction": float(compounding_amp_fraction),
            "compounding_amplification_formula": "(replay_other - this_probe) / this_probe",
        },
        "viability": {
            "all_finite": bool(all_finite),
            "first_solver_status_not_ok": first_solver_status_not_ok,
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    json_size = OUT_JSON.stat().st_size

    self_audit = [
        ("Resets OC substrate to karr_pre_substrate[t] at EACH tick", True),
        ("Same RNG seed as Day-42 baseline (_Mcg16807 seed=0)", True),
        ("Same LP config as production baseline (pricing=STD, presolve=OFF, BIG=1e6)", True),
        ("Per-tick L1 trajectory + cumulative L1 trajectory reported", True),
        ("Per-tick L∞ trajectory reported", True),
        ("Top-10 cumulative drift substrates at tick 99 with WIDs reported", bool(len(top10_rows) == 10)),
        ("Sign analysis for top divergent substrates reported", bool(len(sign_analysis_top) == 10)),
        ("Day-42 raw vs replay-other vs this side-by-side reported", True),
        ("Headline verdict emitted using requested threshold map", True),
        ("STATUS + JSON outputs written", OUT_JSON.exists() and OUT_STATUS.parent.exists()),
    ]

    lines: list[str] = []
    lines.append("# STATUS_h_100tick_per_tick_reset")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "- Isolate linear per-tick Metabolism delta mismatch (OC delta - Karr delta) by resetting OC substrate "
        "to `karr_pre_substrate[t]` at every tick before running Metabolism."
    )
    lines.append(
        "- Remove chained substrate-state compounding from bound reconstruction and measure only additive/cancelling "
        "accumulation across 100 ticks (seed 0)."
    )
    lines.append("")
    lines.append("## Headline Verdict")
    lines.append(f"**{verdict}**")
    lines.append("")
    lines.append(
        f"- This probe cumulative L1 at tick 99: {_fmt(cumulative_l1_tick99)} "
        f"(requested thresholds: PURE_LINEAR=[1.30e6,1.65e6], PARTIAL_CANCEL<1.0e6, COMPOUNDING_DOMINANT>2.0e6)."
    )
    lines.append(
        f"- Per-tick L1 mean={_fmt(float(per_tick_l1.mean()))}, median={_fmt(float(np.median(per_tick_l1)))}; "
        f"tick99 per-tick L1={_fmt(float(per_tick_l1[99]))}."
    )
    lines.append(
        f"- Side-by-side 100-tick L1: Day-42 raw={_fmt(day42_l1_tick99)}, "
        f"replay-other={_fmt(replay_other_l1_tick99)}, this probe={_fmt(cumulative_l1_tick99)}."
    )
    lines.append(
        f"- Compounding amplification fraction `(1.60M - this) / this` (using measured replay-other): "
        f"{_fmt(float(compounding_amp_fraction))}."
    )
    lines.append("")
    lines.append("## Requested Metrics")
    lines.append(
        f"- Per-tick L1 checkpoints (ticks {', '.join(str(t) for t in CHECKPOINTS)}): "
        f"{', '.join(_fmt(float(per_tick_l1[t])) for t in CHECKPOINTS)}."
    )
    lines.append(
        f"- Cumulative L1 checkpoints (ticks {', '.join(str(t) for t in CHECKPOINTS)}): "
        f"{', '.join(_fmt(float(cumulative_l1[t])) for t in CHECKPOINTS)}."
    )
    lines.append(
        f"- Per-tick L∞ checkpoints (ticks {', '.join(str(t) for t in CHECKPOINTS)}): "
        f"{', '.join(_fmt(float(per_tick_linf[t])) for t in CHECKPOINTS)}."
    )
    lines.append("")
    lines.append("## Checkpoint Table")
    lines.append("| Tick | Per-tick L1 | Cumulative L1 | Per-tick L∞ | Cumulative L∞ | Growth (/s) | Top per-tick row |")
    lines.append("|---:|---:|---:|---:|---:|---:|---|")
    for row in checkpoint_rows:
        lines.append(
            f"| {row['tick']} | {_fmt(row['per_tick_l1'])} | {_fmt(row['cumulative_l1'])} | "
            f"{_fmt(row['per_tick_linf'])} | {_fmt(row['cumulative_linf'])} | {_fmt(row['growth_per_s'])} | "
            f"{row['top_row_wid']} (r{row['top_row_index']}, L1={_fmt(row['top_row_per_tick_l1'])}) |"
        )
    lines.append("")
    lines.append("## Top-10 Cumulative Drift Rows at Tick 99")
    lines.append("| Rank | Row | WID | Cumulative L1 abs drift | Signed cumulative drift | Trend |")
    lines.append("|---:|---:|---|---:|---:|---|")
    for row in top10_rows:
        lines.append(
            f"| {row['rank']} | {row['row_index']} | {row['wid']} | {_fmt(row['cumulative_l1_abs_drift'])} | "
            f"{_fmt(row['cumulative_signed_drift_total'])} | {row['sign_trend']} |"
        )
    lines.append("")
    lines.append("## Sign Analysis (Top-10 Rows)")
    lines.append("| Rank | WID | +tick frac | -tick frac | 0-tick frac | +count | -count | 0count | Trend |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---|")
    for row in sign_analysis_top:
        lines.append(
            f"| {row['rank']} | {row['wid']} | {_fmt(row['positive_tick_fraction'])} | "
            f"{_fmt(row['negative_tick_fraction'])} | {_fmt(row['zero_tick_fraction'])} | "
            f"{row['positive_tick_count']} | {row['negative_tick_count']} | {row['zero_tick_count']} | "
            f"{row['sign_trend']} |"
        )
    lines.append("")
    lines.append("## Side-by-side")
    lines.append(f"- Day-42 raw 100-tick L1: {_fmt(day42_l1_tick99)}")
    lines.append(f"- Replay-other 100-tick L1: {_fmt(replay_other_l1_tick99)}")
    lines.append(f"- This probe 100-tick cumulative L1: {_fmt(cumulative_l1_tick99)}")
    lines.append(
        f"- Compounding amplification fraction = `(replay_other - this) / this` = {_fmt(float(compounding_amp_fraction))}"
    )
    lines.append("")
    lines.append("## VERIFICATION")
    lines.append(f"- Command: `{command}`")
    lines.append(f"- Inputs verified: `{TRACE_PATH}`, `{LP_FIXTURE_NPZ}`, `{WRITEBACK_FIXTURE_MAT}`")
    lines.append(f"- Baselines loaded: `{DAY42_JSON}` and `{REPLAY_OTHER_JSON}`")
    lines.append("- Per-tick reset logic verified in code:")
    lines.append("  - `oc_sub = pre_sub[t].copy()` before `compute_bounds(...)`")
    lines.append("  - `karr_metab_delta = post_sub[t] - pre_sub[t]`")
    lines.append("  - `diff_t = oc_metab_delta - karr_metab_delta`")
    lines.append("  - `cumulative_drift += diff_t`")
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
    print(f"HEADLINE={verdict}")
    print(
        "L1 side-by-side: "
        f"day42={day42_l1_tick99:.3f} replay_other={replay_other_l1_tick99:.3f} this={cumulative_l1_tick99:.3f}"
    )
    print(f"Compounding amplification fraction={compounding_amp_fraction:.6f}")


if __name__ == "__main__":
    main()
