"""Smoke tests for the Karr-native M2 vivarium chassis."""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m2 import transcription as tx
from opencell.vivarium.karr_m2 import (
    KarrTranscriptionProcess,
    build_karr_m2_engine,
)


@pytest.fixture(scope="module")
def model() -> tx.KarrTranscriptionModel:
    return tx.load_default()


def test_process_builds(model: tx.KarrTranscriptionModel) -> None:
    proc = KarrTranscriptionProcess({"model": model})
    schema = proc.ports_schema()
    assert len(schema["rna"]["counts"]) == 525
    assert set(schema["substrates"]) == {"ATP", "CTP", "GTP", "UTP"}


def test_engine_runs_100_steps_without_drift(
    model: tx.KarrTranscriptionModel,
) -> None:
    engine = build_karr_m2_engine(model=model, time_step_s=1.0)
    engine.update(100.0)
    ts = engine.emitter.get_timeseries()

    # All 525 RNA series are finite and stable (started at steady state).
    for gid, series in ts["rna"]["counts"].items():
        a = np.asarray(series, dtype=float)
        assert np.all(np.isfinite(a)), f"RNA {gid} non-finite"
        spread = float(np.max(a[1:]) - np.min(a[1:]))
        assert spread < 1e-6, f"RNA {gid} drifted: spread={spread}"

    # Substrate accumulators must be strictly negative (consumption).
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        a = np.asarray(ts["substrates"][ntp], dtype=float)
        # last sample = sum of -ntp_per_s over 100s
        assert a[-1] < 0, f"{ntp} not consumed: {a[-1]}"
        # roughly: last ~= - 100s * ntp_per_s
        expected = -100.0 * tx.ntp_consumption_per_s(model)[ntp]
        rel = abs(a[-1] - expected) / abs(expected)
        assert rel < 0.05, f"{ntp} consumption off: {a[-1]} vs {expected}"


def test_engine_starting_from_zero_approaches_steady_state(
    model: tx.KarrTranscriptionModel,
) -> None:
    """1800s integration from zero counts: fast genes within 5% of expr."""
    init = np.zeros(model.n_genes)
    engine = build_karr_m2_engine(
        model=model, time_step_s=1.0, initial_rna_counts=init
    )
    engine.update(1800.0)
    ts = engine.emitter.get_timeseries()

    expr = model.expression[:, 1]
    fast = (model.half_life_min > 0) & (model.half_life_min <= 5.0)
    final = np.array([
        float(ts["rna"]["counts"][gid][-1]) for gid in model.gene_wcm_ids
    ])
    rel = np.abs(final[fast] - expr[fast]) / np.maximum(expr[fast], 1e-12)
    assert float(np.max(rel)) < 0.05, (
        f"fast genes not at steady state: max rel = {rel.max():.4f}"
    )
