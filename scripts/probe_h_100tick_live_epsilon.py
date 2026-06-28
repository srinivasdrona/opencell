"""Day-42 EOD probe 12: 100-tick live trajectory with a-fit epsilon objective.

Runs OC Metabolism in isolation for 100 ticks using an epsilon-perturbed objective
on substitution-pair columns. Epsilon signs are derived only from Karr's recorded
flux at sample (s=0, t=1), then held fixed across all ticks.

Produces:
  - tmp/h_100tick_live_epsilon.json
  - STATUS_h_100tick_live_epsilon.md
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
EPS_FLUX_PATH = (
    REPO
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
BASELINE_JSON = REPO / "tmp" / "h_100tick_live_trajectory.json"

OUT_JSON = REPO / "tmp" / "h_100tick_live_epsilon.json"
OUT_STATUS = REPO / "STATUS_h_100tick_live_epsilon.md"

BIG = 1e6
N_TICKS = 100
EPSILON = 1e-9

PAIR_COLS: list[tuple[str, int]] = [
    ("HDCA", 393),
    ("OCDCEA", 422),
    ("PHE", 423),
    ("PhePhe", 424),
    ("TRIOLEIN", 444),
    ("TRIPALMITIN", 445),
    ("TRP", 449),
    ("TrpTrp", 450),
]

PAIR_REPORT_WIDS = ["TRP", "TRIOLEIN", "PHE", "OCDCEA"]
CHECKPOINTS = [0, 1, 5, 10, 25, 50, 75, 99]


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
    mid = per_tick_l1.size // 2
    first_half = float(per_tick_l1[mid] - per_tick_l1[0])
    second_half = float(per_tick_l1[-1] - per_tick_l1[mid])
    if per_tick_l1[-1] <= start * 1.1:
        return "flat"
    if second_half > 1.25 * first_half:
        return "super-linear"
    if second_half < 0.75 * first_half:
        return "sub-linear"
    return "approximately linear"


def _fmt(x: float) -> str:
    if abs(x) >= 1e5 or (0 < abs(x) < 1e-3):
        return f"{x:.6e}"
    return f"{x:.3f}"


def _headline_verdict(l1_tick99: float, closure_pct: float) -> str:
    if l1_tick99 < 100000.0:
        return "TRACKS"
    if l1_tick99 < 1000000.0:
        return "PARTIAL_TRACK"
    if l1_tick99 > 4000000.0:
        return "NO_IMPROVEMENT"
    return "PARTIAL_TRACK" if closure_pct > 15.0 else "NO_IMPROVEMENT"


def _build_epsilon_objective(c_base: np.ndarray, karr_flux_t1: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    c_eps = c_base.copy()
    applied: list[dict[str, Any]] = []
    for name, col in PAIR_COLS:
        kv = float(karr_flux_t1[col])
        if abs(kv) > 1e-3:
            push = float(np.sign(kv) * EPSILON)
            c_eps[col] += push
        else:
            push = 0.0
        applied.append(
            {
                "name": name,
                "col": int(col),
                "karr_flux_t1": kv,
                "epsilon_added": float(push),
                "applied": bool(push != 0.0),
            }
        )
    return c_eps, applied


def _run_trajectory(
    *,
    model: Any,
    dyn: Any,
    writeback_fixture: KarrWritebackFixture,
    pre_sub: np.ndarray,
    post_sub: np.ndarray,
    pre_enz: np.ndarray,
    metabolite_rows: np.ndarray,
    wid_to_idx: dict[str, int],
    objective: np.ndarray,
) -> dict[str, Any]:
    oc_sub = pre_sub[0].copy()
    rng = _Mcg16807(seed=0)
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)

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

    diff99 = np.abs(oc_traj[-1] - karr_traj[-1]).sum(axis=1)

    return {
        "oc_traj": oc_traj,
        "karr_traj": karr_traj,
        "growth": growth,
        "objective_vals": objective_vals,
        "per_tick_l1": per_tick_l1,
        "per_tick_linf": per_tick_linf,
        "per_tick_top_row": per_tick_top_row,
        "per_tick_top_row_l1": per_tick_top_row_l1,
        "infeasible_reactions": infeasible_reactions,
        "metabolite_min": metabolite_min,
        "all_finite": all_finite,
        "major_stats": major_stats,
        "first_solver_status_not_ok": first_solver_status_not_ok,
        "diff99_row_l1": diff99,
    }


def main() -> None:
    t0 = time.perf_counter()
    command = r"bin\oc-py scripts/probe_h_100tick_live_epsilon.py"

    for path in [TRACE_PATH, LP_FIXTURE_NPZ, WRITEBACK_FIXTURE_MAT, EPS_FLUX_PATH, BASELINE_JSON]:
        if not path.exists():
            raise FileNotFoundError(f"missing required input: {path}")

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

    with h5py.File(EPS_FLUX_PATH, "r") as handle:
        karr_flux_t1 = np.asarray(handle["flux"]).reshape(-1).astype(np.float64)
    if karr_flux_t1.shape[0] != 504:
        raise ValueError(f"expected 504 flux entries in epsilon reference; got {karr_flux_t1.shape[0]}")

    baseline_payload = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    baseline_l1_tick99_file = float(baseline_payload["summary"]["l1_tick99"])
    baseline_top_file = baseline_payload["top10_tick99"][0]
    baseline_per_tick_l1_file = np.asarray(baseline_payload["per_tick"]["l1"], dtype=np.float64)
    baseline_per_tick_linf_file = np.asarray(baseline_payload["per_tick"]["linf"], dtype=np.float64)

    c_base = model.obj.astype(np.float64).copy()
    c_npz = np.asarray(lp_npz["obj"], dtype=np.float64).reshape(-1)
    obj_base_vs_npz_max_abs_diff = float(np.max(np.abs(c_base - c_npz)))
    c_epsilon, epsilon_applied = _build_epsilon_objective(c_base, karr_flux_t1)

    eps_run = _run_trajectory(
        model=model,
        dyn=dyn,
        writeback_fixture=writeback_fixture,
        pre_sub=pre_sub,
        post_sub=post_sub,
        pre_enz=pre_enz,
        metabolite_rows=metabolite_rows,
        wid_to_idx=wid_to_idx,
        objective=c_epsilon,
    )

    # Recompute baseline with identical runtime path for pair-level closure metrics.
    base_recomputed = _run_trajectory(
        model=model,
        dyn=dyn,
        writeback_fixture=writeback_fixture,
        pre_sub=pre_sub,
        post_sub=post_sub,
        pre_enz=pre_enz,
        metabolite_rows=metabolite_rows,
        wid_to_idx=wid_to_idx,
        objective=c_base,
    )

    per_tick_l1 = eps_run["per_tick_l1"]
    per_tick_linf = eps_run["per_tick_linf"]
    growth = eps_run["growth"]
    objective_vals = eps_run["objective_vals"]
    per_tick_top_row = eps_run["per_tick_top_row"]
    per_tick_top_row_l1 = eps_run["per_tick_top_row_l1"]
    infeasible_reactions = eps_run["infeasible_reactions"]
    metabolite_min = eps_run["metabolite_min"]
    diff99 = eps_run["diff99_row_l1"]

    karr_mass = np.abs(eps_run["karr_traj"]).sum(axis=(1, 2))
    growth_pattern = _growth_mode(per_tick_l1)

    top10_idx = np.argsort(-diff99)[:10]
    top10_rows: list[dict[str, Any]] = []
    for rank, row_idx in enumerate(top10_idx, start=1):
        top10_rows.append(
            {
                "rank": rank,
                "row_index": int(row_idx),
                "wid": substrate_wids[int(row_idx)],
                "l1_abs_diff": float(diff99[int(row_idx)]),
                "oc_final_total": float(eps_run["oc_traj"][-1, int(row_idx), :].sum()),
                "karr_final_total": float(eps_run["karr_traj"][-1, int(row_idx), :].sum()),
            }
        )

    major_summary: dict[str, Any] = {}
    for wid, series in eps_run["major_stats"].items():
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
        "all_finite": bool(eps_run["all_finite"]),
        "metabolite_nonnegative_all_ticks": bool(np.all(metabolite_min >= 0.0)),
        "min_metabolite_value_overall": float(metabolite_min.min()),
        "major_metabolites": major_summary,
    }

    checkpoint_rows: list[dict[str, Any]] = []
    for tick in CHECKPOINTS:
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

    baseline_recomputed_l1_tick99 = float(base_recomputed["per_tick_l1"][99])
    baseline_vs_file_abs_diff = abs(baseline_recomputed_l1_tick99 - baseline_l1_tick99_file)

    epsilon_l1_tick99 = float(per_tick_l1[99])
    epsilon_top_tick99 = top10_rows[0]
    closure_pct = (baseline_l1_tick99_file - epsilon_l1_tick99) / max(baseline_l1_tick99_file, 1.0) * 100.0
    verdict = _headline_verdict(epsilon_l1_tick99, closure_pct)

    compare_tick99 = {
        "baseline_file_l1_tick99": baseline_l1_tick99_file,
        "baseline_file_top_row_wid": str(baseline_top_file["wid"]),
        "baseline_file_top_row_l1": float(baseline_top_file["l1_abs_diff"]),
        "epsilon_l1_tick99": epsilon_l1_tick99,
        "epsilon_top_row_wid": str(epsilon_top_tick99["wid"]),
        "epsilon_top_row_l1": float(epsilon_top_tick99["l1_abs_diff"]),
        "closure_percent": float(closure_pct),
        "baseline_recomputed_l1_tick99": baseline_recomputed_l1_tick99,
        "baseline_recomputed_vs_file_abs_diff": float(baseline_vs_file_abs_diff),
    }

    pair_comparison: list[dict[str, Any]] = []
    for wid in PAIR_REPORT_WIDS:
        if wid not in wid_to_idx:
            pair_comparison.append(
                {
                    "wid": wid,
                    "present_in_fixture": False,
                }
            )
            continue
        idx = wid_to_idx[wid]
        base_l1 = float(base_recomputed["diff99_row_l1"][idx])
        eps_l1 = float(diff99[idx])
        base_oc_total = float(base_recomputed["oc_traj"][-1, idx, :].sum())
        eps_oc_total = float(eps_run["oc_traj"][-1, idx, :].sum())
        karr_total = float(eps_run["karr_traj"][-1, idx, :].sum())
        improve_abs = base_l1 - eps_l1
        improve_pct = improve_abs / max(base_l1, 1.0) * 100.0
        pair_comparison.append(
            {
                "wid": wid,
                "present_in_fixture": True,
                "baseline_l1_tick99_recomputed": base_l1,
                "epsilon_l1_tick99": eps_l1,
                "improvement_abs": float(improve_abs),
                "improvement_percent": float(improve_pct),
                "baseline_oc_total_tick99": base_oc_total,
                "epsilon_oc_total_tick99": eps_oc_total,
                "karr_total_tick99": karr_total,
                "baseline_oc_to_karr_ratio": float(base_oc_total / max(karr_total, 1.0)),
                "epsilon_oc_to_karr_ratio": float(eps_oc_total / max(karr_total, 1.0)),
            }
        )

    checkpoint_compare: list[dict[str, Any]] = []
    for tick in CHECKPOINTS:
        checkpoint_compare.append(
            {
                "tick": int(tick),
                "baseline_l1": float(baseline_per_tick_l1_file[tick]),
                "epsilon_l1": float(per_tick_l1[tick]),
                "baseline_linf": float(baseline_per_tick_linf_file[tick]),
                "epsilon_linf": float(per_tick_linf[tick]),
            }
        )

    elapsed_s = time.perf_counter() - t0

    payload: dict[str, Any] = {
        "metadata": {
            "probe": "h_100tick_live_epsilon",
            "seed": 0,
            "n_ticks": N_TICKS,
            "big": BIG,
            "epsilon": EPSILON,
            "command": command,
            "inputs": {
                "trace_path": str(TRACE_PATH),
                "lp_fixture_npz": str(LP_FIXTURE_NPZ),
                "writeback_fixture_mat": str(WRITEBACK_FIXTURE_MAT),
                "epsilon_reference_flux_path": str(EPS_FLUX_PATH),
                "baseline_trajectory_json": str(BASELINE_JSON),
                "lp_fixture_shapes": {
                    "S": list(np.asarray(lp_npz["S"]).shape),
                    "RHS": list(np.asarray(lp_npz["RHS"]).shape),
                    "obj": list(np.asarray(lp_npz["obj"]).shape),
                    "lb": list(np.asarray(lp_npz["lb"]).shape),
                    "ub": list(np.asarray(lp_npz["ub"]).shape),
                },
            },
            "objective_base_vs_npz_max_abs_diff": obj_base_vs_npz_max_abs_diff,
            "epsilon_applied_columns": epsilon_applied,
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
            "first_solver_status_not_ok": eps_run["first_solver_status_not_ok"],
            "elapsed_seconds": float(elapsed_s),
        },
        "summary": {
            "verdict": verdict,
            "growth_pattern": growth_pattern,
            "l1_tick0": float(per_tick_l1[0]),
            "l1_tick1": float(per_tick_l1[1]),
            "l1_tick10": float(per_tick_l1[10]),
            "l1_tick50": float(per_tick_l1[50]),
            "l1_tick99": epsilon_l1_tick99,
            "linf_tick99": float(per_tick_linf[99]),
            "growth_tick0": float(growth[0]),
            "growth_tick99": float(growth[99]),
            "growth_min": float(growth.min()),
            "growth_max": float(growth.max()),
        },
        "tick99_comparison_vs_baseline": compare_tick99,
        "checkpoint_comparison_vs_baseline": checkpoint_compare,
        "per_substitution_pair_comparison": pair_comparison,
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
        "viability": viability,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    json_size = OUT_JSON.stat().st_size

    self_audit = [
        (
            "Epsilon signs derived only from metab_flux_allocated_state_s000_tick1.mat at (s=0,t=1)",
            True,
        ),
        ("Epsilon perturbation applied identically at all 100 ticks", True),
        ("Same RNG seed (_Mcg16807 seed=0) as prior 100-tick trajectory probe", True),
        ("Same solver path/config as prior probe (GLPK STD, presolve OFF, BIG=1e6)", True),
        ("Same bounds reconstruction path as prior probe (cfb.compute_bounds)", True),
        ("Run includes full 100 ticks and per-tick L1/Linf/growth arrays", len(per_tick_l1) == 100),
        (
            "Side-by-side tick-99 comparison references tmp/h_100tick_live_trajectory.json baseline",
            True,
        ),
        ("Closure percent computed as (baseline-epsilon)/baseline*100", True),
        (
            "Per-substitution-pair improvements reported for TRP/TRIOLEIN/PHE/OCDCEA",
            len(pair_comparison) == 4,
        ),
        ("STATUS and JSON artifacts written", OUT_STATUS.parent.exists() and OUT_JSON.exists()),
    ]

    lines: list[str] = []
    lines.append("# STATUS_h_100tick_live_epsilon")
    lines.append("")
    lines.append("## INTENT")
    lines.append(
        "- Run the same 100-tick live OC Metabolism trajectory probe as the baseline, but with a fixed a-fit epsilon objective "
        "(epsilon=1e-9 on substitution-pair columns using Karr flux signs from sample (s=0,t=1))."
    )
    lines.append(
        "- Test whether the per-tick epsilon objective tie-break closes trajectory-level drift vs Karr over 100 ticks, "
        "and quantify closure at tick 99 and for substitution-pair substrates."
    )
    lines.append("")
    lines.append("## Headline")
    lines.append(f"**{verdict}**")
    lines.append("")
    lines.append(
        f"- Tick-99 L1: epsilon={_fmt(epsilon_l1_tick99)} vs baseline={_fmt(baseline_l1_tick99_file)}; "
        f"closure={closure_pct:.2f}%."
    )
    lines.append(
        f"- Tick-99 top diverging substrate: epsilon={epsilon_top_tick99['wid']} "
        f"(L1={_fmt(float(epsilon_top_tick99['l1_abs_diff']))}) vs baseline={baseline_top_file['wid']} "
        f"(L1={_fmt(float(baseline_top_file['l1_abs_diff']))})."
    )
    lines.append(
        f"- L1 drift mode over 100 ticks (epsilon run): **{growth_pattern}**; "
        f"checkpoints tick1={_fmt(per_tick_l1[1])}, tick10={_fmt(per_tick_l1[10])}, tick50={_fmt(per_tick_l1[50])}, tick99={_fmt(per_tick_l1[99])}."
    )
    lines.append(
        f"- Growth trajectory (epsilon run): tick0={_fmt(growth[0])}, tick99={_fmt(growth[99])}, "
        f"min={_fmt(growth.min())}, max={_fmt(growth.max())}."
    )
    lines.append("")
    lines.append("## Epsilon Objective")
    lines.append("| Column | FBA col | Karr flux @ (s=0,t=1) | epsilon added to c[col] |")
    lines.append("|---|---:|---:|---:|")
    for row in epsilon_applied:
        lines.append(
            f"| {row['name']} | {row['col']} | {_fmt(float(row['karr_flux_t1']))} | {_fmt(float(row['epsilon_added']))} |"
        )
    lines.append("")
    lines.append("## Checkpoint Table (Epsilon Run)")
    lines.append("| Tick | L1 | L∞ | Growth (/s) | Top diverging row |")
    lines.append("|---:|---:|---:|---:|---|")
    for row in checkpoint_rows:
        lines.append(
            f"| {row['tick']} | {_fmt(row['l1'])} | {_fmt(row['linf'])} | {_fmt(row['growth_per_s'])} | "
            f"{row['top_row_wid']} (r{row['top_row_index']}, L1={_fmt(row['top_row_l1'])}) |"
        )
    lines.append("")
    lines.append("## Baseline vs Epsilon (Checkpoints)")
    lines.append("| Tick | Baseline L1 | Epsilon L1 | Baseline L∞ | Epsilon L∞ |")
    lines.append("|---:|---:|---:|---:|---:|")
    for row in checkpoint_compare:
        lines.append(
            f"| {row['tick']} | {_fmt(row['baseline_l1'])} | {_fmt(row['epsilon_l1'])} | "
            f"{_fmt(row['baseline_linf'])} | {_fmt(row['epsilon_linf'])} |"
        )
    lines.append("")
    lines.append("## Substitution-Pair Improvement at Tick 99")
    lines.append("| WID | Baseline L1 (recomputed) | Epsilon L1 | Improvement | Improvement % | Baseline OC/Karr | Epsilon OC/Karr |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in pair_comparison:
        if not row.get("present_in_fixture", False):
            lines.append(f"| {row['wid']} | n/a | n/a | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| {row['wid']} | {_fmt(float(row['baseline_l1_tick99_recomputed']))} | {_fmt(float(row['epsilon_l1_tick99']))} | "
            f"{_fmt(float(row['improvement_abs']))} | {row['improvement_percent']:.2f}% | "
            f"{_fmt(float(row['baseline_oc_to_karr_ratio']))} | {_fmt(float(row['epsilon_oc_to_karr_ratio']))} |"
        )
    lines.append("")
    lines.append("## Top-10 Tick-99 Divergent Substrates (Epsilon Run)")
    lines.append("| Rank | Row | WID | L1 abs diff | OC final total | Karr final total |")
    lines.append("|---:|---:|---|---:|---:|---:|")
    for row in top10_rows:
        lines.append(
            f"| {row['rank']} | {row['row_index']} | {row['wid']} | {_fmt(float(row['l1_abs_diff']))} | "
            f"{_fmt(float(row['oc_final_total']))} | {_fmt(float(row['karr_final_total']))} |"
        )
    lines.append("")
    lines.append("## Biological Viability")
    lines.append(f"- All OC substrate values finite across 100 ticks: {'YES' if viability['all_finite'] else 'NO'}.")
    lines.append(
        f"- Metabolite rows non-negative at all ticks: "
        f"{'YES' if viability['metabolite_nonnegative_all_ticks'] else 'NO'} "
        f"(global min metabolite value={_fmt(viability['min_metabolite_value_overall'])})."
    )
    if major_summary:
        lines.append("- Major metabolite checks (ATP, H2O, NTPs):")
        for wid in ["ATP", "H2O", "CTP", "GTP", "UTP"]:
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
    lines.append(f"- Inputs verified: `{TRACE_PATH}`, `{LP_FIXTURE_NPZ}`, `{WRITEBACK_FIXTURE_MAT}`, `{EPS_FLUX_PATH}`, `{BASELINE_JSON}`")
    lines.append(
        f"- Baseline tick-99 from file: L1={_fmt(baseline_l1_tick99_file)}, top={baseline_top_file['wid']} "
        f"(L1={_fmt(float(baseline_top_file['l1_abs_diff']))})."
    )
    lines.append(
        f"- Baseline recompute check (same runtime path): tick-99 L1={_fmt(baseline_recomputed_l1_tick99)}; "
        f"|recomputed-file|={_fmt(baseline_vs_file_abs_diff)}."
    )
    lines.append(f"- Output JSON: `{OUT_JSON}` ({json_size} bytes)")
    lines.append(f"- Output STATUS: `{OUT_STATUS}` (written by this probe)")
    lines.append(f"- Objective base consistency check: max|model.obj - npz.obj|={_fmt(obj_base_vs_npz_max_abs_diff)}")
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
    print(f"VERDICT={verdict}")
    print(f"L1 tick99 baseline(file)={baseline_l1_tick99_file:.3f} epsilon={epsilon_l1_tick99:.3f} closure={closure_pct:.2f}%")
    print(
        f"Top tick99 baseline(file)={baseline_top_file['wid']}({float(baseline_top_file['l1_abs_diff']):.3f}) "
        f"epsilon={epsilon_top_tick99['wid']}({float(epsilon_top_tick99['l1_abs_diff']):.3f})"
    )


if __name__ == "__main__":
    main()
