"""Smoke tests for the Karr-native M1 vivarium Process chassis."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.m1 import karr_metabolism as km
from opencell.vivarium.karr_metabolism import (
    KarrMetabolismProcess,
    build_karr_m1_engine,
)


@pytest.fixture(scope="module")
def model() -> km.KarrMetabolismModel:
    return km.load_default()


def test_process_builds(model: km.KarrMetabolismModel) -> None:
    proc = KarrMetabolismProcess({"model": model})
    schema = proc.ports_schema()
    assert "metabolic_reaction" in schema and "substrates" in schema
    assert len(schema["metabolic_reaction"]["fluxs"]) == 645
    assert len(schema["substrates"]) == 585


def test_single_update_matches_standalone_solver(
    model: km.KarrMetabolismModel,
) -> None:
    proc = KarrMetabolismProcess({"model": model, "time_step": 1.0})
    schema = proc.ports_schema()
    initial = {
        "metabolic_reaction": {
            "fluxs": {k: v["_default"] for k, v in schema["metabolic_reaction"]["fluxs"].items()},
            "growth_per_s": schema["metabolic_reaction"]["growth_per_s"]["_default"],
            "growth_per_h": schema["metabolic_reaction"]["growth_per_h"]["_default"],
        },
        "substrates": {k: v["_default"] for k, v in schema["substrates"].items()},
    }
    upd = proc.next_update(1.0, initial)
    standalone_v, standalone_info = km.solve_fba(model, use_full_objective=True, sense="max")
    assert upd["metabolic_reaction"]["growth_per_h"] == pytest.approx(
        standalone_info["biomass_flux_per_h"], rel=1e-9
    )


def test_engine_runs_100_steps_without_drift(
    model: km.KarrMetabolismModel,
) -> None:
    """Chassis acceptance: 100 1-second ticks complete; biomass is stable
    (snapshot-based FBA is time-invariant when state is unchanged) and no
    flux is NaN/inf."""
    engine = build_karr_m1_engine(model=model, time_step_s=1.0)
    engine.update(100.0)
    ts = engine.emitter.get_timeseries()

    growth_series = ts["metabolic_reaction"]["growth_per_h"]
    # at least 100 emitted points (1 per second + initial)
    assert len(growth_series) >= 100

    arr = np.asarray(growth_series, dtype=float)
    assert np.all(np.isfinite(arr)), "growth went non-finite"
    # First emit is the t=0 initial-state default (= Karr stored ~0.0763);
    # subsequent emits are the predicted snapshot value (~0.039).  After
    # the first tick the snapshot-based FBA is time-invariant: spread
    # across ticks 1..N must be ~0.
    spread = float(np.max(arr[1:]) - np.min(arr[1:]))
    assert spread < 1e-9, f"biomass not stable across ticks: spread={spread}"

    # all 645 flux series must be finite for every emitted tick
    for rid, series in ts["metabolic_reaction"]["fluxs"].items():
        a = np.asarray(series, dtype=float)
        assert np.all(np.isfinite(a)), f"flux {rid} went non-finite"


def test_engine_biomass_matches_standalone(
    model: km.KarrMetabolismModel,
) -> None:
    standalone_v, info = km.solve_fba(model)
    engine = build_karr_m1_engine(model=model, time_step_s=1.0)
    engine.update(5.0)
    ts = engine.emitter.get_timeseries()
    g = float(ts["metabolic_reaction"]["growth_per_h"][-1])
    assert g == pytest.approx(info["biomass_flux_per_h"], rel=1e-9)

