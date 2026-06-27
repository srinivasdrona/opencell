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
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

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


def _require_file(path: Path) -> Path:
    if not path.exists():
        raise HardProbeError(f"required file missing: {path}")
    return path


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
