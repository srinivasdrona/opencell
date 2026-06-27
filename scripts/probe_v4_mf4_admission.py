#!/usr/bin/env python3
"""Empirical probe for V4 MF4 admission at sample (seed=0, tick=1).

This script is investigation-only. It does not modify any implementation code
or fixtures. It produces one JSON report at ``tmp/v4_probe_results.json`` and
exits 0 when all probe sections ran, even if the measured LP / mutation results
do not pass their respective criteria. It exits 1 only on hard errors such as a
missing required file or a solver/runtime failure that prevents the probe from
running.
"""

from __future__ import annotations

import json
import math
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

from opencell.m1.karr_metabolism import KarrMetabolismModel, solve_fba
from opencell.m1.karr_metabolism_writeback import (
    ATP_HYDROLYSIS_SIGNS,
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
GROUND_TRUTH_PATH = (
    ROOT
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
TRACE_PATH = (
    ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_s000"
    / "Metabolism_100ticks.mat"
)
REPORT_PATH = ROOT / "tmp" / "v4_probe_results.json"

TOP17_WIDS = [
    "OCDCEA",
    "H2O2",
    "O2",
    "TRP",
    "TRIOLEIN",
    "TYR",
    "GL",
    "AC",
    "PHE",
    "TrpTrp",
    "H2O",
    "TyrTyr",
    "GLC",
    "ACAL",
    "AEPP",
    "CAP",
    "PhePhe",
]
ALPHAS = [1.0, 0.75, 0.5, 0.25, 0.10, 0.05, 0.01]
TAU_FORMULAS = {
    "tau_A": lambda x: max(1.0, 3e-4 * abs(x)),
    "tau_B": lambda x: max(40.0, 0.03 * abs(x)),
    "tau_C": lambda x: max(100.0, 0.10 * abs(x)),
}
WRITEBACK_SEED = 12345
MUTATION_SHUFFLE_SEED = 99
TOP27_COUNT = 27
I4_SPEARMAN_THRESHOLD = 0.95
I4_SIGN_THRESHOLD = 15
I6_SIGN_SHARE_THRESHOLD = 0.80
SOLVER_BIG = 1e3


class HardProbeError(RuntimeError):
    """Raised for hard probe failures that should exit with status 1."""


@dataclass
class ProbeContext:
    fixture: Any
    ground_truth: dict[str, np.ndarray]
    model: KarrMetabolismModel
    writeback_fixture: KarrWritebackFixture
    substrate_ids: list[str]
    substrate_index: dict[str, int]
    fba_col_names: list[str]
    top17_indices: list[int]
    karr_delta_flat: np.ndarray
    bounds_lb: np.ndarray
    bounds_ub: np.ndarray
    solver_bounds_lb: np.ndarray
    solver_bounds_ub: np.ndarray


def _require_file(path: Path) -> Path:
    if not path.exists():
        raise HardProbeError(f"required file missing: {path}")
    return path


def make_writeback_rng(seed: int) -> Any:
    from opencell.vivarium.karr_protein_decay_light import _Mcg16807  # noqa: PLC0415

    return _Mcg16807(seed)


def load_fixture_mat(path: Path) -> Any:
    _require_file(path)
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def load_ground_truth(path: Path) -> dict[str, np.ndarray]:
    _require_file(path)
    with h5py.File(path, "r") as handle:
        return {
            "flux": np.asarray(handle["flux"], dtype=np.float64).reshape(-1),
            "bounds": np.asarray(handle["bounds"], dtype=np.float64),
            "delta": np.asarray(handle["delta"], dtype=np.float64).T,
            "growth": np.asarray(handle["growth"], dtype=np.float64).reshape(-1)[0],
            "pre_sub": np.asarray(handle["pre_sub"], dtype=np.float64).T,
            "post_sub": np.asarray(handle["post_sub"], dtype=np.float64).T,
        }


def to_builtin(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(v) for v in value]
    return value


def build_report_shell() -> dict[str, Any]:
    return {
        "sample": {"seed": 0, "tick": 1},
        "paths": {
            "fixture_mat": str(FIXTURE_PATH),
            "ground_truth_mat": str(GROUND_TRUTH_PATH),
            "trace_mat": str(TRACE_PATH),
            "report_json": str(REPORT_PATH),
        },
        "constants": {
            "top17_wids": TOP17_WIDS,
            "alphas": ALPHAS,
            "writeback_seed": WRITEBACK_SEED,
            "tau_formulas": {
                "tau_A": "max(1, 3e-4 * |karr_delta_j|)",
                "tau_B": "max(40, 0.03 * |karr_delta_j|)",
                "tau_C": "max(100, 0.10 * |karr_delta_j|)",
            },
        },
        "sections": {
            "precheck": {},
            "karr_feasibility": {},
            "joint_lp": {},
            "line_search": {},
            "surrogate_accuracy": {},
            "mutation_matrix": {},
        },
        "assumptions": [],
        "errors": [],
    }


def _mat_strings(values: Any) -> list[str]:
    return [str(v) for v in np.asarray(values).tolist()]


def build_fba_col_names(fixture: Any, substrate_ids: list[str], reaction_ids: list[str]) -> list[str]:
    n_cols = int(np.asarray(fixture.fbaObjective).shape[0])
    names = [f"FBA_COL_{i}" for i in range(n_cols)]

    reaction_indexs_fba = np.asarray(fixture.reactionIndexs_fba, dtype=np.int64).reshape(-1) - 1
    metabolic_cols = np.asarray(
        fixture.fbaReactionIndexs_metabolicConversion, dtype=np.int64
    ).reshape(-1) - 1
    for col, rxn_idx in zip(metabolic_cols, reaction_indexs_fba, strict=False):
        if 0 <= col < n_cols and 0 <= rxn_idx < len(reaction_ids):
            names[int(col)] = reaction_ids[int(rxn_idx)]

    ext_cols = np.asarray(
        fixture.fbaReactionIndexs_metaboliteExternalExchange, dtype=np.int64
    ).reshape(-1) - 1
    ext_rows = np.asarray(
        fixture.substrateIndexs_externalExchangedMetabolites, dtype=np.int64
    ).reshape(-1) - 1
    for col, row in zip(ext_cols, ext_rows, strict=False):
        if 0 <= col < n_cols and 0 <= row < len(substrate_ids):
            names[int(col)] = f"EXT_{substrate_ids[int(row)]}"

    int_cols = np.asarray(
        fixture.fbaReactionIndexs_metaboliteInternalExchange, dtype=np.int64
    ).reshape(-1) - 1
    int_rows = np.asarray(
        fixture.substrateIndexs_internalExchangedMetabolites, dtype=np.int64
    ).reshape(-1) - 1
    for col, row in zip(int_cols, int_rows, strict=False):
        if 0 <= col < n_cols and 0 <= row < len(substrate_ids):
            names[int(col)] = f"INT_{substrate_ids[int(row)]}"

    biomass_prod = int(np.asarray(fixture.fbaReactionIndexs_biomassProduction).item()) - 1
    biomass_exch = int(np.asarray(fixture.fbaReactionIndexs_biomassExchange).item()) - 1
    if 0 <= biomass_prod < n_cols:
        names[biomass_prod] = "BIOMASS_PRODUCTION"
    if 0 <= biomass_exch < n_cols:
        names[biomass_exch] = "BIOMASS_EXCHANGE"
    return names


def build_probe_context() -> ProbeContext:
    fixture = load_fixture_mat(FIXTURE_PATH)
    ground_truth = load_ground_truth(GROUND_TRUTH_PATH)
    substrate_ids = _mat_strings(fixture.substrateWholeCellModelIDs)
    substrate_index = {wid: idx for idx, wid in enumerate(substrate_ids)}
    top17_indices = [substrate_index[wid] for wid in TOP17_WIDS]

    fba_bounds = np.asarray(fixture.fbaReactionBounds, dtype=np.float64)
    model = KarrMetabolismModel(
        S=np.asarray(fixture.fbaReactionStoichiometryMatrix, dtype=np.float64),
        RHS=np.asarray(fixture.fbaRightHandSide, dtype=np.float64).reshape(-1),
        lb=fba_bounds[:, 0].copy(),
        ub=fba_bounds[:, 1].copy(),
        obj=np.asarray(fixture.fbaObjective, dtype=np.float64).reshape(-1),
        enz_bounds=np.zeros((fba_bounds.shape[0], 2), dtype=np.float64),
        catalysis=np.zeros((0, 0), dtype=np.float64),
        fluxs_stored=np.zeros(fba_bounds.shape[0], dtype=np.float64),
        rxn_wcm_ids_645=_mat_strings(fixture.reactionWholeCellModelIDs),
        fba_col_rxn_wcm=[None] * fba_bounds.shape[0],
        biomass_col=int(np.asarray(fixture.fbaReactionIndexs_biomassProduction).item()) - 1,
        stored_runtime={},
        counts={},
        raw={},
    )
    writeback_fixture = KarrWritebackFixture.from_mat(FIXTURE_PATH)
    bounds_lb = ground_truth["bounds"][0].reshape(-1).astype(np.float64)
    bounds_ub = ground_truth["bounds"][1].reshape(-1).astype(np.float64)
    solver_bounds_lb = np.clip(
        np.where(np.isfinite(bounds_lb), bounds_lb, -SOLVER_BIG),
        -SOLVER_BIG,
        SOLVER_BIG,
    )
    solver_bounds_ub = np.clip(
        np.where(np.isfinite(bounds_ub), bounds_ub, SOLVER_BIG),
        -SOLVER_BIG,
        SOLVER_BIG,
    )
    return ProbeContext(
        fixture=fixture,
        ground_truth=ground_truth,
        model=model,
        writeback_fixture=writeback_fixture,
        substrate_ids=substrate_ids,
        substrate_index=substrate_index,
        fba_col_names=build_fba_col_names(
            fixture=fixture,
            substrate_ids=substrate_ids,
            reaction_ids=_mat_strings(fixture.reactionWholeCellModelIDs),
        ),
        top17_indices=top17_indices,
        karr_delta_flat=ground_truth["delta"].sum(axis=1),
        bounds_lb=bounds_lb,
        bounds_ub=bounds_ub,
        solver_bounds_lb=solver_bounds_lb,
        solver_bounds_ub=solver_bounds_ub,
    )


def check_flux_feasibility(
    model: KarrMetabolismModel,
    flux: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    tol: float = 1e-6,
) -> dict[str, Any]:
    mass_balance = model.S @ flux - model.RHS
    lower_violation = np.maximum(lb - flux, 0.0)
    upper_violation = np.maximum(flux - ub, 0.0)
    return {
        "feasible": bool(
            np.max(np.abs(mass_balance)) <= tol
            and np.max(lower_violation) <= tol
            and np.max(upper_violation) <= tol
        ),
        "tol": tol,
        "mass_balance_max_abs": float(np.max(np.abs(mass_balance))),
        "lower_bound_max_violation": float(np.max(lower_violation)),
        "upper_bound_max_violation": float(np.max(upper_violation)),
    }


def run_d4_precheck(context: ProbeContext) -> tuple[np.ndarray, dict[str, Any]]:
    oc_flux, oc_meta = solve_fba(
        context.model,
        lb_override=context.bounds_lb,
        ub_override=context.bounds_ub,
        solver="glpk",
    )
    karr_flux = context.ground_truth["flux"]
    oc_obj = float(np.dot(context.model.obj, oc_flux))
    karr_obj = float(np.dot(context.model.obj, karr_flux))
    rel_gap = abs(oc_obj - karr_obj) / max(abs(karr_obj), 1.0)
    feasibility = check_flux_feasibility(
        context.model,
        karr_flux,
        context.bounds_lb,
        context.bounds_ub,
    )
    return oc_flux, {
        "solver": "glpk",
        "solver_metadata": oc_meta,
        "objective_value_oc": oc_obj,
        "objective_value_karr": karr_obj,
        "relative_full_objective_gap": rel_gap,
        "karr_flux_feasibility": feasibility,
    }


def build_pre_round_surrogate(
    context: ProbeContext, fixed_growth_per_s: float
) -> tuple[np.ndarray, np.ndarray]:
    n_sub = len(context.substrate_ids)
    n_rxn = context.model.n_reactions
    linear = np.zeros((n_sub, n_rxn), dtype=np.float64)
    wb = context.writeback_fixture

    linear[wb.sub_idx_external, wb.fba_idx_external] -= wb.step_size_sec
    linear[wb.sub_idx_internal, wb.fba_idx_internal] += 1.0

    constant_matrix = wb.metabolism_new_production * fixed_growth_per_s * wb.step_size_sec
    constant_flat = constant_matrix.sum(axis=1)
    unaccounted_qty = wb.unaccounted_energy_consumption * fixed_growth_per_s * wb.step_size_sec
    constant_flat = constant_flat.astype(np.float64, copy=True)
    constant_flat[wb.sub_idx_atp_hydrolysis] += ATP_HYDROLYSIS_SIGNS * unaccounted_qty
    return linear, constant_flat


def linearized_flat_delta(
    linear_operator: np.ndarray, constant_flat: np.ndarray, flux: np.ndarray
) -> np.ndarray:
    return constant_flat + linear_operator @ flux


def actual_writeback_flat(context: ProbeContext, flux: np.ndarray) -> np.ndarray:
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=context.ground_truth["pre_sub"],
        v_504=flux,
        growth_per_s=float(flux[context.model.biomass_col]),
        fixture=context.writeback_fixture,
        rng=make_writeback_rng(WRITEBACK_SEED),
    )
    return delta.sum(axis=1).astype(np.float64)


def tau_vector_for(name: str, target_values: np.ndarray) -> np.ndarray:
    return np.asarray([TAU_FORMULAS[name](float(v)) for v in target_values], dtype=np.float64)


def glpk_status_name(status: int) -> str:
    import swiglpk as glp  # noqa: PLC0415

    names = {
        glp.GLP_UNDEF: "GLP_UNDEF",
        glp.GLP_FEAS: "GLP_FEAS",
        glp.GLP_INFEAS: "GLP_INFEAS",
        glp.GLP_NOFEAS: "GLP_NOFEAS",
        glp.GLP_OPT: "GLP_OPT",
        glp.GLP_UNBND: "GLP_UNBND",
    }
    return names.get(status, f"STATUS_{status}")


def active_bound_report(
    baseline_flux: np.ndarray,
    k: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    col_names: list[str],
    tol: float = 1e-6,
) -> list[dict[str, Any]]:
    candidate = baseline_flux + k
    active: list[dict[str, Any]] = []
    for idx, value in enumerate(candidate):
        if abs(value - lb[idx]) <= tol:
            active.append(
                {
                    "fba_col": idx,
                    "name": col_names[idx],
                    "bound": "lb",
                    "value": float(value),
                    "bound_value": float(lb[idx]),
                }
            )
        if abs(value - ub[idx]) <= tol:
            active.append(
                {
                    "fba_col": idx,
                    "name": col_names[idx],
                    "bound": "ub",
                    "value": float(value),
                    "bound_value": float(ub[idx]),
                }
            )
    return active


def solve_joint_lp(
    *,
    context: ProbeContext,
    baseline_flux: np.ndarray,
    linear_operator: np.ndarray,
    constant_flat: np.ndarray,
    tau_name: str,
) -> dict[str, Any]:
    try:
        import swiglpk as glp  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - dependency failure
        raise HardProbeError(f"swiglpk import failed: {exc}") from exc

    n_rxn = context.model.n_reactions
    n_top = len(context.top17_indices)
    target = context.karr_delta_flat[context.top17_indices]
    tau = tau_vector_for(tau_name, target)
    base_linear = linearized_flat_delta(linear_operator, constant_flat, baseline_flux)
    a = base_linear[context.top17_indices]
    J = linear_operator[context.top17_indices, :]

    row_count = context.model.S.shape[0] + 2 + 2 * n_top
    col_count = n_rxn + n_top
    lp = glp.glp_create_prob()
    glp.glp_term_out(glp.GLP_OFF)
    try:
        glp.glp_set_obj_dir(lp, glp.GLP_MIN)
        glp.glp_add_rows(lp, row_count)

        row = 1
        for _ in range(context.model.S.shape[0]):
            glp.glp_set_row_bnds(lp, row, glp.GLP_FX, 0.0, 0.0)
            row += 1
        glp.glp_set_row_bnds(lp, row, glp.GLP_FX, 0.0, 0.0)
        row += 1
        glp.glp_set_row_bnds(lp, row, glp.GLP_FX, 0.0, 0.0)
        row += 1
        for j in range(n_top):
            upper_rhs = float(target[j] - a[j] + tau[j])
            lower_rhs = float(a[j] - target[j] + tau[j])
            glp.glp_set_row_bnds(lp, row, glp.GLP_UP, 0.0, upper_rhs)
            row += 1
            glp.glp_set_row_bnds(lp, row, glp.GLP_UP, 0.0, lower_rhs)
            row += 1

        glp.glp_add_cols(lp, col_count)
        for j in range(n_rxn):
            lo = float(context.solver_bounds_lb[j] - baseline_flux[j])
            hi = float(context.solver_bounds_ub[j] - baseline_flux[j])
            if abs(lo - hi) <= 1e-12:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_FX, lo, hi)
            else:
                glp.glp_set_col_bnds(lp, j + 1, glp.GLP_DB, lo, hi)
            glp.glp_set_obj_coef(lp, j + 1, 0.0)
        for j in range(n_top):
            col = n_rxn + j + 1
            glp.glp_set_col_bnds(lp, col, glp.GLP_LO, 0.0, 0.0)
            glp.glp_set_obj_coef(lp, col, float(1.0 / tau[j]))

        rows: list[int] = []
        cols: list[int] = []
        vals: list[float] = []

        S = np.asarray(context.model.S, dtype=np.float64)
        s_rows, s_cols = np.nonzero(S)
        for r_idx, c_idx in zip(s_rows, s_cols, strict=False):
            rows.append(int(r_idx) + 1)
            cols.append(int(c_idx) + 1)
            vals.append(float(S[r_idx, c_idx]))

        biomass_row = context.model.S.shape[0] + 1
        rows.append(biomass_row)
        cols.append(context.model.biomass_col + 1)
        vals.append(1.0)

        objective_row = context.model.S.shape[0] + 2
        for c_idx, coef in enumerate(context.model.obj):
            if coef != 0:
                rows.append(objective_row)
                cols.append(c_idx + 1)
                vals.append(float(coef))

        row = context.model.S.shape[0] + 3
        for j in range(n_top):
            nz = np.nonzero(J[j])[0]
            for c_idx in nz:
                rows.append(row)
                cols.append(int(c_idx) + 1)
                vals.append(float(J[j, c_idx]))
            rows.append(row)
            cols.append(n_rxn + j + 1)
            vals.append(-1.0)
            row += 1

            for c_idx in nz:
                rows.append(row)
                cols.append(int(c_idx) + 1)
                vals.append(float(-J[j, c_idx]))
            rows.append(row)
            cols.append(n_rxn + j + 1)
            vals.append(-1.0)
            row += 1

        ia = glp.intArray(len(rows) + 1)
        ja = glp.intArray(len(rows) + 1)
        ar = glp.doubleArray(len(rows) + 1)
        for idx, (r_idx, c_idx, val) in enumerate(zip(rows, cols, vals, strict=True), start=1):
            ia[idx] = r_idx
            ja[idx] = c_idx
            ar[idx] = val
        glp.glp_load_matrix(lp, len(rows), ia, ja, ar)

        glp.glp_scale_prob(lp, glp.GLP_SF_AUTO)
        glp.glp_adv_basis(lp, 0)
        params = glp.glp_smcp()
        glp.glp_init_smcp(params)
        params.msg_lev = glp.GLP_MSG_OFF
        params.presolve = glp.GLP_OFF
        params.meth = glp.GLP_PRIMAL
        params.tol_bnd = 1e-6
        simplex_status = glp.glp_simplex(lp, params)
        if simplex_status != 0:
            raise HardProbeError(f"GLPK simplex returned status {simplex_status} for {tau_name}")

        solution_status = glp.glp_get_status(lp)
        result: dict[str, Any] = {
            "solver_family": "swiglpk",
            "solver_settings": {
                "presolve": "OFF",
                "scale": "AUTO",
                "tol_bnd": 1e-6,
                "simplex": "primal",
            },
            "simplex_status": simplex_status,
            "solution_status": glpk_status_name(solution_status),
            "tau_by_wid": {wid: float(val) for wid, val in zip(TOP17_WIDS, tau, strict=True)},
            "objective_value": None,
            "near_zero_objective": False,
            "infeasible": solution_status != glp.GLP_OPT,
            "per_wid_slack": {},
            "per_wid_linearized_error": {},
            "active_bounds": [],
            "candidate_k_l1": None,
            "candidate_k_linf": None,
        }
        if solution_status != glp.GLP_OPT:
            return result

        k = np.array([glp.glp_get_col_prim(lp, i + 1) for i in range(n_rxn)], dtype=np.float64)
        s = np.array(
            [glp.glp_get_col_prim(lp, n_rxn + i + 1) for i in range(n_top)],
            dtype=np.float64,
        )
        objective_value = float(glp.glp_get_obj_val(lp))
        candidate_linear = a + J @ k
        per_wid_error = np.abs(candidate_linear - target)
        result.update(
            {
                "objective_value": objective_value,
                "near_zero_objective": bool(objective_value <= 1e-9),
                "infeasible": False,
                "candidate_k_l1": float(np.sum(np.abs(k))),
                "candidate_k_linf": float(np.max(np.abs(k))),
                "per_wid_slack": {
                    wid: float(val) for wid, val in zip(TOP17_WIDS, s, strict=True)
                },
                "per_wid_linearized_error": {
                    wid: float(val) for wid, val in zip(TOP17_WIDS, per_wid_error, strict=True)
                },
                "active_bounds": active_bound_report(
                    baseline_flux=baseline_flux,
                    k=k,
                    lb=context.solver_bounds_lb,
                    ub=context.solver_bounds_ub,
                    col_names=context.fba_col_names,
                ),
                "candidate_k": k,
            }
        )
        return result
    finally:
        glp.glp_delete_prob(lp)


def run_line_search(
    *,
    context: ProbeContext,
    baseline_flux: np.ndarray,
    candidate_k: np.ndarray,
    tau_name: str,
) -> dict[str, Any]:
    target = context.karr_delta_flat[context.top17_indices]
    tau = tau_vector_for(tau_name, target)
    alphas_report: dict[str, Any] = {}
    verified_alphas: list[float] = []
    best_alpha = None
    best_pass_count = -1
    best_total_error = math.inf

    for alpha in ALPHAS:
        candidate_flux = baseline_flux + alpha * candidate_k
        actual_flat = actual_writeback_flat(context, candidate_flux)
        errors = np.abs(actual_flat[context.top17_indices] - target)
        pass_mask = errors <= tau + 1e-9
        pass_count = int(np.sum(pass_mask))
        total_error = float(np.sum(errors))
        if pass_count == len(TOP17_WIDS):
            verified_alphas.append(alpha)
        if pass_count > best_pass_count or (
            pass_count == best_pass_count and total_error < best_total_error
        ):
            best_alpha = alpha
            best_pass_count = pass_count
            best_total_error = total_error
        alphas_report[str(alpha)] = {
            "pass_count": pass_count,
            "all_17_within_tau": bool(pass_count == len(TOP17_WIDS)),
            "per_wid_abs_error": {
                wid: float(err) for wid, err in zip(TOP17_WIDS, errors, strict=True)
            },
        }

    return {
        "verified_alphas": verified_alphas,
        "best_verified_alpha": max(verified_alphas) if verified_alphas else None,
        "minimum_alpha_all17": min(verified_alphas) if verified_alphas else None,
        "best_alpha_by_pass_count": best_alpha,
        "alphas": alphas_report,
    }


def measure_surrogate_accuracy(
    *,
    context: ProbeContext,
    baseline_flux: np.ndarray,
    candidate_k: np.ndarray,
    linear_operator: np.ndarray,
    constant_flat: np.ndarray,
    selected_alpha: float,
) -> dict[str, Any]:
    candidate_flux = baseline_flux + selected_alpha * candidate_k
    actual_flat = actual_writeback_flat(context, candidate_flux)
    linearized_flat = linearized_flat_delta(linear_operator, constant_flat, candidate_flux)
    per_wid_gap = np.abs(
        linearized_flat[context.top17_indices] - actual_flat[context.top17_indices]
    )
    max_idx = int(np.argmax(per_wid_gap))
    return {
        "alpha": float(selected_alpha),
        "per_wid_abs_gap": {
            wid: float(val) for wid, val in zip(TOP17_WIDS, per_wid_gap, strict=True)
        },
        "max_abs_gap": float(per_wid_gap[max_idx]),
        "max_gap_wid": TOP17_WIDS[max_idx],
    }


def main() -> int:
    try:
        report = build_report_shell()
        context = build_probe_context()
        oc_flux, precheck = run_d4_precheck(context)

        report["fixture_shapes"] = {
            "S": list(np.asarray(context.fixture.fbaReactionStoichiometryMatrix).shape),
            "bounds": list(np.asarray(context.fixture.fbaReactionBounds).shape),
            "objective": list(np.asarray(context.fixture.fbaObjective).shape),
            "delta": list(context.ground_truth["delta"].shape),
            "pre_sub": list(context.ground_truth["pre_sub"].shape),
            "post_sub": list(context.ground_truth["post_sub"].shape),
        }
        report["sections"]["precheck"] = {
            "relative_full_objective_gap": precheck["relative_full_objective_gap"],
            "objective_value_oc": precheck["objective_value_oc"],
            "objective_value_karr": precheck["objective_value_karr"],
            "baseline_solver": precheck["solver"],
            "baseline_biomass_flux_per_s": precheck["solver_metadata"]["biomass_flux_per_s"],
            "baseline_nonzero_fluxes": precheck["solver_metadata"]["n_nonzero"],
        }
        report["sections"]["karr_feasibility"] = precheck["karr_flux_feasibility"]
        report["baseline"] = {
            "oc_flux_l1": float(np.sum(np.abs(oc_flux))),
            "oc_flux_linf": float(np.max(np.abs(oc_flux))),
        }
        linear_operator, constant_flat = build_pre_round_surrogate(
            context, fixed_growth_per_s=precheck["solver_metadata"]["biomass_flux_per_s"]
        )
        report["surrogate"] = {
            "linear_operator_shape": list(linear_operator.shape),
            "constant_shape": list(constant_flat.shape),
            "fixed_growth_per_s": precheck["solver_metadata"]["biomass_flux_per_s"],
        }
        joint_lp_results: dict[str, dict[str, Any]] = {}
        joint_lp_candidates: dict[str, np.ndarray] = {}
        for tau_name in TAU_FORMULAS:
            lp_result = solve_joint_lp(
                context=context,
                baseline_flux=oc_flux,
                linear_operator=linear_operator,
                constant_flat=constant_flat,
                tau_name=tau_name,
            )
            if "candidate_k" in lp_result:
                candidate_k = lp_result["candidate_k"]
                joint_lp_candidates[tau_name] = candidate_k
                lp_result = dict(lp_result)
                lp_result.pop("candidate_k")
                lp_result["active_bounds_count"] = len(lp_result["active_bounds"])
                lp_result["candidate_flux_biomass_per_s"] = float(
                    oc_flux[context.model.biomass_col] + candidate_k[context.model.biomass_col]
                )
            joint_lp_results[tau_name] = lp_result
        report["sections"]["joint_lp"] = joint_lp_results
        line_search_results = {
            tau_name: (
                run_line_search(
                    context=context,
                    baseline_flux=oc_flux,
                    candidate_k=joint_lp_candidates[tau_name],
                    tau_name=tau_name,
                )
                if tau_name in joint_lp_candidates
                else {"verified_alphas": [], "best_verified_alpha": None, "alphas": {}}
            )
            for tau_name in TAU_FORMULAS
        }
        report["sections"]["line_search"] = line_search_results
        surrogate_accuracy: dict[str, Any] = {}
        for tau_name in TAU_FORMULAS:
            if tau_name not in joint_lp_candidates:
                surrogate_accuracy[tau_name] = {"alpha": None, "per_wid_abs_gap": {}}
                continue
            line_search = line_search_results[tau_name]
            selected_alpha = line_search["best_verified_alpha"]
            selection_policy = "best_verified_alpha"
            if selected_alpha is None:
                selected_alpha = line_search["best_alpha_by_pass_count"]
                selection_policy = "best_alpha_by_pass_count"
            surrogate_accuracy[tau_name] = measure_surrogate_accuracy(
                context=context,
                baseline_flux=oc_flux,
                candidate_k=joint_lp_candidates[tau_name],
                linear_operator=linear_operator,
                constant_flat=constant_flat,
                selected_alpha=float(selected_alpha),
            )
            surrogate_accuracy[tau_name]["selection_policy"] = selection_policy
        report["sections"]["surrogate_accuracy"] = surrogate_accuracy

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(to_builtin(report), indent=2, sort_keys=True))
        return 0
    except HardProbeError as exc:
        sys.stderr.write(f"HARD ERROR: {exc}\n")
        return 1
    except Exception as exc:  # pragma: no cover - investigation hard-stop path
        sys.stderr.write(f"HARD ERROR: {exc}\n")
        sys.stderr.write(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
