"""Smoke tests for the Karr-native M3 vivarium chassis."""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m3 import translation as tl
from opencell.vivarium.karr_m3 import (
    KarrTranslationProcess,
    build_karr_m3_engine,
)


@pytest.fixture(scope="module")
def model() -> tl.KarrTranslationModel:
    return tl.load_default()


def test_process_builds(model: tl.KarrTranslationModel) -> None:
    proc = KarrTranslationProcess({"model": model})
    schema = proc.ports_schema()
    assert len(schema["protein"]["counts"]) == 482
    assert "AA_total" in schema["substrates"]


def test_engine_runs_without_drift_at_ss(
    model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_m3_engine(model=model, time_step_s=1.0)
    engine.update(20.0)
    ts = engine.emitter.get_timeseries()
    for pid, series in ts["protein"]["counts"].items():
        a = np.asarray(series, dtype=float)
        assert np.all(np.isfinite(a)), f"protein {pid} non-finite"
        spread = float(np.max(a[1:]) - np.min(a[1:]))
        assert spread < 1e-3, f"protein {pid} drifted: spread={spread}"
    aa = np.asarray(ts["substrates"]["AA_total"], dtype=float)
    assert aa[-1] < 0
    expected = -20.0 * tl.aa_consumption_per_s(model)["_total_aa_per_s"]
    rel = abs(aa[-1] - expected) / abs(expected)
    assert rel < 0.05


def test_engine_starting_perturbed_relaxes(
    model: tl.KarrTranslationModel,
) -> None:
    """Start at 1.5x mature counts; after 5 e-foldings of the slowest
    decayed protein, decayed species should be back near steady state."""
    init = 1.5 * model.counts_mature
    engine = build_karr_m3_engine(
        model=model, time_step_s=10.0, initial_protein_counts=init
    )
    have_decay = model.decay_rate_per_s > 0
    k_min = float(np.min(model.decay_rate_per_s[have_decay]))
    duration = 5.0 / k_min
    engine.update(duration)
    ts = engine.emitter.get_timeseries()
    # Sample final
    final = np.array([
        float(ts["protein"]["counts"][p][-1]) for p in model.protein_wcm_ids
    ])
    rel = np.abs(final[have_decay] - model.counts_mature[have_decay]) / np.maximum(
        model.counts_mature[have_decay], 1.0
    )
    assert float(np.max(rel)) < 1e-2
