from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import h5py
import numpy as np
import pytest

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km
from opencell.m1.fva import fva_range, substrate_delta_range_from_fva
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture


_REPO = Path(__file__).resolve().parents[2]
_GT_SAMPLE_PATH = (
    _REPO
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
_WRITEBACK_FIXTURE_MAT = _REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
_FVA_REF_JSON = _REPO / "tmp" / "h_fva_validation.json"
_SUB_DELTA_REF_JSON = _REPO / "tmp" / "h_substrate_delta_fva.json"
_BIG = 1e6


def _as_585x3(arr: np.ndarray) -> np.ndarray:
    if arr.shape == (585, 3):
        return np.asarray(arr, dtype=np.float64)
    if arr.shape == (3, 585):
        return np.asarray(arr.T, dtype=np.float64)
    raise ValueError(f"unexpected substrate shape {arr.shape}; expected (585,3) or (3,585)")


def _as_104(arr: np.ndarray) -> np.ndarray:
    flat = np.asarray(arr, dtype=np.float64).reshape(-1)
    if flat.shape != (104,):
        raise ValueError(f"unexpected enzyme shape {arr.shape}; flattened={flat.shape}, expected (104,)")
    return flat


@lru_cache(maxsize=1)
def _fva_validation_case() -> dict[str, np.ndarray | float]:
    if not _GT_SAMPLE_PATH.exists():
        pytest.skip(f"Missing sample fixture: {_GT_SAMPLE_PATH}")

    model = km.load_default()
    with h5py.File(_GT_SAMPLE_PATH, "r") as handle:
        bounds = np.asarray(handle["bounds"], dtype=np.float64)
        karr_flux = np.asarray(handle["flux"], dtype=np.float64).reshape(-1)

    lb = np.clip(bounds[0], -_BIG, _BIG)
    ub = np.clip(bounds[1], -_BIG, _BIG)
    _v_star, info = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=_BIG,
        lb_override=lb,
        ub_override=ub,
        solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])
    v_min, v_max = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb,
        ub,
        biomass_value_star=biomass_value_star,
    )
    return {
        "v_min": v_min,
        "v_max": v_max,
        "karr_flux": karr_flux,
        "biomass_value_star": biomass_value_star,
    }


@lru_cache(maxsize=1)
def _substrate_delta_case() -> dict[str, np.ndarray]:
    if not _GT_SAMPLE_PATH.exists():
        pytest.skip(f"Missing sample fixture: {_GT_SAMPLE_PATH}")
    if not _WRITEBACK_FIXTURE_MAT.exists():
        pytest.skip(f"Missing writeback fixture: {_WRITEBACK_FIXTURE_MAT}")

    model = km.load_default()
    dyn = cfb.load_default_dynamics()
    fixture = KarrWritebackFixture.from_mat(_WRITEBACK_FIXTURE_MAT)

    with h5py.File(_GT_SAMPLE_PATH, "r") as handle:
        pre_sub = _as_585x3(np.asarray(handle["pre_sub"], dtype=np.float64))
        pre_enz = _as_104(np.asarray(handle["pre_enz"], dtype=np.float64))

    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
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
    lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -_BIG)
    ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], _BIG)
    lb = np.clip(lb, -_BIG, _BIG).astype(np.float64)
    ub = np.clip(ub, -_BIG, _BIG).astype(np.float64)
    infeasible = lb > ub
    if np.any(infeasible):
        midpoint = 0.5 * (lb[infeasible] + ub[infeasible])
        lb[infeasible] = midpoint
        ub[infeasible] = midpoint

    _v_star, info = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=_BIG,
        lb_override=lb,
        ub_override=ub,
        solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])
    v_min, v_max = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb,
        ub,
        biomass_value_star=biomass_value_star,
    )
    d_min, d_max = substrate_delta_range_from_fva(
        v_min=v_min,
        v_max=v_max,
        fixture=fixture,
        growth_per_s=float(info["biomass_flux_per_s"]),
        step_size_sec=float(fixture.step_size_sec),
        pre_state_585x3=pre_sub,
    )
    return {
        "d_min": d_min,
        "d_max": d_max,
    }


def test_fva_range_at_sample_0_1() -> None:
    if not _FVA_REF_JSON.exists():
        pytest.skip(f"Missing reference artifact: {_FVA_REF_JSON}")

    case = _fva_validation_case()
    with _FVA_REF_JSON.open("r", encoding="utf-8") as handle:
        ref = json.load(handle)

    karr_flux = np.asarray(case["karr_flux"], dtype=np.float64)
    v_min = np.asarray(case["v_min"], dtype=np.float64)
    v_max = np.asarray(case["v_max"], dtype=np.float64)
    tol = 1e-4 * np.maximum(1.0, np.abs(karr_flux))
    feasible = (karr_flux >= (v_min - tol)) & (karr_flux <= (v_max + tol))

    assert int(np.count_nonzero(feasible)) == int(ref["n_feasible"]) == 504
    assert float(np.mean(feasible)) == pytest.approx(float(ref["feasibility_fraction"]), abs=1e-12)


def test_substrate_delta_range_at_sample_0_1() -> None:
    if not _SUB_DELTA_REF_JSON.exists():
        pytest.skip(f"Missing reference artifact: {_SUB_DELTA_REF_JSON}")

    case = _substrate_delta_case()
    d_min = np.asarray(case["d_min"], dtype=np.float64)
    d_max = np.asarray(case["d_max"], dtype=np.float64)

    with _SUB_DELTA_REF_JSON.open("r", encoding="utf-8") as handle:
        ref = json.load(handle)
    sample0 = next(sample for sample in ref["samples"] if int(sample["seed"]) == 0 and int(sample["tick_label"]) == 1)

    tol = 2.0
    for row_key, row_payload in sample0["substitution_rows"].items():
        row = int(row_key)
        for comp_payload in row_payload["compartments"]:
            comp = int(comp_payload["comp"])
            expected_min = comp_payload["range_min"]
            expected_max = comp_payload["range_max"]
            karr_delta = float(comp_payload["karr_delta"])
            if expected_min is None or expected_max is None:
                continue
            # Primary regression: Karr's recorded substitution-row deltas remain feasible.
            assert karr_delta >= d_min[row, comp] - tol
            assert karr_delta <= d_max[row, comp] + tol
            # For deterministic cells (probe interval collapses to one value),
            # the projected bounds should still agree numerically.
            if abs(float(expected_max) - float(expected_min)) <= 1e-9:
                assert d_min[row, comp] == pytest.approx(float(expected_min), abs=1e-6)
                assert d_max[row, comp] == pytest.approx(float(expected_max), abs=1e-6)


def test_karr_flux_in_fva_range_sample_0_1() -> None:
    case = _fva_validation_case()
    karr_flux = np.asarray(case["karr_flux"], dtype=np.float64)
    v_min = np.asarray(case["v_min"], dtype=np.float64)
    v_max = np.asarray(case["v_max"], dtype=np.float64)
    tol = 1e-4 * np.maximum(1.0, np.abs(karr_flux))

    assert np.all(karr_flux >= (v_min - tol))
    assert np.all(karr_flux <= (v_max + tol))
