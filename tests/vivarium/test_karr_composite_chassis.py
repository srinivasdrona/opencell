"""Chassis-composition smoke tests: M1 + M2 ticking together."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.vivarium.karr_composite import build_karr_m1_m2_engine


@pytest.fixture(scope="module")
def m1_model() -> km.KarrMetabolismModel:
    return km.load_default()


@pytest.fixture(scope="module")
def m2_model() -> tx.KarrTranscriptionModel:
    return tx.load_default()


def test_engine_builds_and_runs(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
) -> None:
    eng = build_karr_m1_m2_engine(
        m1_model=m1_model,
        m2_model=m2_model,
        time_step_s=1.0,
    )
    eng.update(10.0)
    ts = eng.emitter.get_timeseries()
    assert "metabolic_reaction" in ts
    assert "rna" in ts
    assert "substrates" in ts


def test_m1_growth_stable_under_composition(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
) -> None:
    """M1's biomass flux must not drift just because M2 is also ticking
    (M2 writes into substrates, but M1 ignores the placeholder counts
    in this chassis tick, so growth stays at the FBA solve)."""
    eng = build_karr_m1_m2_engine(
        m1_model=m1_model,
        m2_model=m2_model,
        time_step_s=1.0,
    )
    eng.update(20.0)
    ts = eng.emitter.get_timeseries()
    g = np.asarray(ts["metabolic_reaction"]["growth_per_h"], dtype=float)
    # First sample is initial-state default; tighten on arr[1:].
    spread = float(np.max(g[1:]) - np.min(g[1:]))
    assert np.all(np.isfinite(g))
    assert spread < 1e-9, f"M1 growth drifted under composition: {spread}"


def test_m2_rna_stable_at_steady_state_under_composition(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
) -> None:
    """M2 starts at expression steady state; should remain there under
    composition (M1 doesn't perturb M2's stores in this chassis tick)."""
    eng = build_karr_m1_m2_engine(
        m1_model=m1_model,
        m2_model=m2_model,
        time_step_s=1.0,
    )
    eng.update(20.0)
    ts = eng.emitter.get_timeseries()
    for gid, series in ts["rna"]["counts"].items():
        a = np.asarray(series, dtype=float)
        assert np.all(np.isfinite(a)), f"RNA {gid} non-finite"
        spread = float(np.max(a[1:]) - np.min(a[1:]))
        assert spread < 1e-6, f"RNA {gid} drifted: spread={spread}"


def test_shared_substrates_accumulate_m2_consumption(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
) -> None:
    """M2's NTP deltas must land in the SHARED substrates store (where
    M1 also lives), proving the topology wires both processes into the
    same store rather than creating parallel stores."""
    eng = build_karr_m1_m2_engine(
        m1_model=m1_model,
        m2_model=m2_model,
        time_step_s=1.0,
    )
    eng.update(20.0)
    ts = eng.emitter.get_timeseries()
    # Substrates emit only the keys M2 declared with _emit=True (ATP/
    # CTP/GTP/UTP).  M1 declared _emit=False for the other 581 -> they
    # exist in state but don't appear in timeseries.
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        a = np.asarray(ts["substrates"][ntp], dtype=float)
        assert a[0] == pytest.approx(1.0), f"{ntp} initial != M1's default 1.0: {a[0]}"
        # 20 ticks of negative deltas accumulate; final < initial.
        assert a[-1] < a[0], f"{ntp} did not decrease: {a[0]} -> {a[-1]}"
        expected_delta = (
            -20.0 * tx.ntp_consumption_per_s(tx.calibrated_chassis_model(m2_model))[ntp]
        )
        observed_delta = float(a[-1] - a[0])
        rel = abs(observed_delta - expected_delta) / abs(expected_delta)
        assert rel < 0.05, f"{ntp} delta off: {observed_delta} vs {expected_delta}"
