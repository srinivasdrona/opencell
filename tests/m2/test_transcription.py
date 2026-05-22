"""Tests for M2 Karr-native transcription module."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.m2 import transcription as tx


@pytest.fixture(scope="module")
def model() -> tx.KarrTranscriptionModel:
    return tx.load_default()


def test_fixture_counts(model: tx.KarrTranscriptionModel) -> None:
    assert model.n_genes == 525
    assert model.tu_binding_probabilities.shape == (335,)
    types = {t: model.gene_types.count(t) for t in set(model.gene_types)}
    assert types == {"mRNA": 482, "rRNA": 3, "sRNA": 4, "tRNA": 36}
    assert model.elongation_rate_nt_per_s == pytest.approx(50.0)


def test_arrays_finite_and_nonneg(model: tx.KarrTranscriptionModel) -> None:
    for arr in (
        model.half_life_min,
        model.decay_rate_per_min,
        model.decay_rate_per_s,
        model.length_nt,
        model.expression,
        model.synthesis_rate_per_min,
        model.synthesis_rate_per_s,
        model.rna_ss_predicted,
        model.tu_binding_probabilities,
    ):
        a = np.asarray(arr)
        assert np.all(np.isfinite(a)), f"non-finite in {a.shape}"
        assert np.all(a >= 0), "unexpected negative values"


def test_steady_state_round_trip_to_expression(
    model: tx.KarrTranscriptionModel,
) -> None:
    """RNA_ss := synthesisRate / decay should equal expression[:, 1]
    by Karr's fitting convention.  Validates extraction + units only."""
    ss = model.rna_ss_predicted
    expr = model.expression[:, 1]
    decay = model.decay_rate_per_min
    have_decay = decay > 0
    diff = np.abs(ss[have_decay] - expr[have_decay])
    rel = diff / np.maximum(np.abs(expr[have_decay]), 1e-12)
    median_rel = float(np.median(rel))
    assert median_rel < 1e-6, f"steady-state round-trip broken: median rel diff = {median_rel:g}"


def test_step_analytical_reaches_steady_state(
    model: tx.KarrTranscriptionModel,
) -> None:
    """Integrate from zero for 30min; fast genes within 5% of expr[:,1]."""
    rna = np.zeros(model.n_genes)
    dt = 1.0
    t = 0.0
    while t < 1800.0:
        rna = tx.step_analytical(model, rna, dt, condition=1)
        t += dt
    expr = model.expression[:, 1]
    fast = (model.half_life_min > 0) & (model.half_life_min <= 5.0)
    rel = np.abs(rna[fast] - expr[fast]) / np.maximum(expr[fast], 1e-12)
    assert float(np.max(rel)) < 0.05, (
        f"fast genes not at steady state after 30min: max rel = {rel.max():.4f}"
    )


def test_step_analytical_preserves_steady_state(
    model: tx.KarrTranscriptionModel,
) -> None:
    rna = model.expression[:, 1].copy()
    rna_next = tx.step_analytical(model, rna, 1.0, condition=1)
    diff = np.max(np.abs(rna_next - rna))
    assert diff < 1e-9, f"steady state not preserved: max diff = {diff:g}"


def test_ntp_consumption_per_s_positive(
    model: tx.KarrTranscriptionModel,
) -> None:
    ntp = tx.ntp_consumption_per_s(model, condition=1)
    for k in ("ATP", "CTP", "GTP", "UTP"):
        assert ntp[k] > 0
    total = ntp["_total_nt_per_s"]
    assert 1e2 < total < 1e5, f"total NTP/s out of plausible range: {total}"
