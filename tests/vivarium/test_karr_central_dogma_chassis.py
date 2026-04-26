"""Chassis-composition smoke tests: M1 + M2 + M3 ticking together."""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine


@pytest.fixture(scope="module")
def m1_model() -> km.KarrMetabolismModel:
    return km.load_default()


@pytest.fixture(scope="module")
def m2_model() -> tx.KarrTranscriptionModel:
    return tx.load_default()


@pytest.fixture(scope="module")
def m3_model() -> tl.KarrTranslationModel:
    return tl.load_default()


def test_engine_builds_and_runs(m1_model, m2_model, m3_model) -> None:
    eng = build_karr_m1_m2_m3_engine(
        m1_model=m1_model, m2_model=m2_model, m3_model=m3_model,
        time_step_s=1.0,
    )
    eng.update(10.0)
    ts = eng.emitter.get_timeseries()
    for k in ("metabolic_reaction", "rna", "protein", "substrates"):
        assert k in ts


def test_central_dogma_states_stable_at_ss(m1_model, m2_model, m3_model) -> None:
    """M1 growth flat; M2 RNAs flat; M3 proteins flat - all start at SS."""
    eng = build_karr_m1_m2_m3_engine(
        m1_model=m1_model, m2_model=m2_model, m3_model=m3_model,
        time_step_s=1.0,
    )
    eng.update(20.0)
    ts = eng.emitter.get_timeseries()

    g = np.asarray(ts["metabolic_reaction"]["growth_per_h"], dtype=float)
    assert np.all(np.isfinite(g))
    assert float(np.max(g[1:]) - np.min(g[1:])) < 1e-9

    for gid, series in ts["rna"]["counts"].items():
        a = np.asarray(series, dtype=float)
        assert np.all(np.isfinite(a))
        assert float(np.max(a[1:]) - np.min(a[1:])) < 1e-6

    for pid, series in ts["protein"]["counts"].items():
        a = np.asarray(series, dtype=float)
        assert np.all(np.isfinite(a))
        assert float(np.max(a[1:]) - np.min(a[1:])) < 1e-3


def test_shared_substrates_carry_m2_and_m3_consumption(
    m1_model, m2_model, m3_model,
) -> None:
    """NTP keys (from M2) and per-AA keys (from M3) accumulate
    negative deltas in the SHARED substrates store."""
    eng = build_karr_m1_m2_m3_engine(
        m1_model=m1_model, m2_model=m2_model, m3_model=m3_model,
        time_step_s=1.0,
    )
    eng.update(20.0)
    ts = eng.emitter.get_timeseries()

    # NTP keys from M2
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        a = np.asarray(ts["substrates"][ntp], dtype=float)
        assert a[-1] < a[0]
        expected = -20.0 * tx.ntp_consumption_per_s(
            tx.calibrated_chassis_model(m2_model)
        )[ntp]
        rel = abs((a[-1] - a[0]) - expected) / abs(expected)
        assert rel < 0.05, f"{ntp} delta off"

    # 20 per-AA keys from M3
    aa_consum = tl.aa_consumption_per_s(m3_model)
    for aa in tl.AA_WCM_IDS:
        series = np.asarray(ts["substrates"][aa], dtype=float)
        # M2 does not write to AA keys, so any movement is from M3.
        assert series[-1] < series[0], f"{aa} did not decrement"
        expected = -20.0 * aa_consum[aa]
        if abs(expected) > 1e-12:
            rel = abs((series[-1] - series[0]) - expected) / abs(expected)
            assert rel < 0.05, f"{aa} delta {series[-1]-series[0]} vs {expected}"


def test_dimensionality(m1_model, m2_model, m3_model) -> None:
    """Sanity: 645 reactions + 525 RNAs + 482 proteins emitted."""
    eng = build_karr_m1_m2_m3_engine(
        m1_model=m1_model, m2_model=m2_model, m3_model=m3_model,
        time_step_s=1.0,
    )
    eng.update(2.0)
    ts = eng.emitter.get_timeseries()
    assert len(ts["metabolic_reaction"]["fluxs"]) == 645
    assert len(ts["rna"]["counts"]) == 525
    assert len(ts["protein"]["counts"]) == 482
