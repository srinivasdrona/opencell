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
    # M3 declares one substrate key per standard amino acid (20).
    assert "AA_total" not in schema["substrates"]
    for aa in tl.AA_WCM_IDS:
        assert aa in schema["substrates"], f"missing AA key {aa}"
    assert len(schema["substrates"]) == 20


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

    aa_consum = tl.aa_consumption_per_s(model)
    for aa in tl.AA_WCM_IDS:
        series = np.asarray(ts["substrates"][aa], dtype=float)
        assert series[-1] < 0, f"{aa} delta should be negative"
        expected = -20.0 * aa_consum[aa]
        if abs(expected) > 1e-12:
            rel = abs(series[-1] - expected) / abs(expected)
            assert rel < 0.05, f"{aa} delta {series[-1]} vs expected {expected}"

    # Sum across the 20 per-AA deltas should reconstruct the bulk total.
    total = sum(float(np.asarray(ts["substrates"][aa])[-1]) for aa in tl.AA_WCM_IDS)
    expected_total = -20.0 * aa_consum["_total_aa_per_s"]
    # Bulk total includes FMET (init-Met) and any non-standard residues
    # captured in length_aa.  Per-AA sum covers 20 standard residues, so
    # |sum| <= |total|.  Allow a 5% gap (FMET + small modifications).
    assert abs(total) <= abs(expected_total) * 1.001
    assert abs(total) > abs(expected_total) * 0.85


def test_engine_starting_perturbed_relaxes(
    model: tl.KarrTranslationModel,
) -> None:
    """Start at 1.5x mature counts; after 5 e-foldings of the slowest
    decayed protein, decayed species should be back near steady state."""
    init = 1.5 * model.counts_mature
    engine = build_karr_m3_engine(model=model, time_step_s=10.0, initial_protein_counts=init)
    have_decay = model.decay_rate_per_s > 0
    k_min = float(np.min(model.decay_rate_per_s[have_decay]))
    duration = 5.0 / k_min
    engine.update(duration)
    ts = engine.emitter.get_timeseries()
    # Sample final
    final = np.array([float(ts["protein"]["counts"][p][-1]) for p in model.protein_wcm_ids])
    rel = np.abs(final[have_decay] - model.counts_mature[have_decay]) / np.maximum(
        model.counts_mature[have_decay], 1.0
    )
    assert float(np.max(rel)) < 1e-2
