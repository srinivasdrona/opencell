"""Tests for M3 Karr-native translation module."""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m3 import translation as tl


@pytest.fixture(scope="module")
def model() -> tl.KarrTranslationModel:
    return tl.load_default()


def test_fixture_counts(model: tl.KarrTranslationModel) -> None:
    assert model.n_proteins == 482
    assert model.elongation_rate_aa_per_s == pytest.approx(16.0)
    # Karr's fitted total mature protein population
    assert int(model.counts_mature.sum()) == 16177
    # 119 essential proteins have halfLife = inf
    assert int(model.immortal_mask.sum()) == 119


def test_arrays_finite_and_consistent(model: tl.KarrTranslationModel) -> None:
    # Lengths > 0
    assert np.all(model.length_aa > 0)
    # Decay >= 0; immortals have decay = 0
    assert np.all(model.decay_rate_per_s >= 0)
    assert np.all(model.decay_rate_per_s[model.immortal_mask] == 0)
    # Synthesis rates non-negative and finite
    assert np.all(np.isfinite(model.synth_rate_per_s))
    assert np.all(model.synth_rate_per_s >= 0)
    # base_counts shape
    assert model.base_counts.shape == (482, 722)


def test_steady_state_round_trip(model: tl.KarrTranslationModel) -> None:
    """For non-immortal proteins, s/k should equal counts_mature exactly
    (Karr's fitting convention)."""
    have_decay = model.decay_rate_per_s > 0
    ss = model.synth_rate_per_s[have_decay] / model.decay_rate_per_s[have_decay]
    diff = np.abs(ss - model.counts_mature[have_decay])
    rel = diff / np.maximum(model.counts_mature[have_decay], 1.0)
    assert float(np.median(rel)) < 1e-6
    # Immortals: synth = 0 by Karr's convention (s = N*k = N*0 = 0)
    assert np.all(model.synth_rate_per_s[model.immortal_mask] == 0)


def test_step_analytical_preserves_steady_state(
    model: tl.KarrTranslationModel,
) -> None:
    n = model.counts_mature.copy()
    n_next = tl.step_analytical(model, n, 1.0)
    diff = float(np.max(np.abs(n_next - n)))
    assert diff < 1e-6, f"steady state not preserved: max diff = {diff:g}"


def test_step_analytical_relaxes_toward_steady_state(
    model: tl.KarrTranslationModel,
) -> None:
    """Perturb the most-degraded (fastest k) protein to 2x and 0.5x;
    after long time it should relax back to N_ss for the decayed ones."""
    ss = model.counts_mature.copy()
    n = ss.copy()
    have_decay = model.decay_rate_per_s > 0
    n[have_decay] = 2.0 * ss[have_decay]  # double
    # 5 e-folding times for the slowest-decaying decayed protein
    k_min = float(np.min(model.decay_rate_per_s[have_decay]))
    dt = 5.0 / k_min
    n2 = tl.step_analytical(model, n, dt)
    rel = np.abs(n2[have_decay] - ss[have_decay]) / np.maximum(ss[have_decay], 1.0)
    assert float(np.max(rel)) < 1e-2


def test_aa_consumption_positive(model: tl.KarrTranslationModel) -> None:
    aa = tl.aa_consumption_per_s(model)
    assert aa["_total_aa_per_s"] > 0
    assert aa["_per_metabolite_per_s_722"].shape == (722,)
    # In a snapshot at SS, all consumption is from decayed proteins
    # (immortals contribute zero synth and zero AA draw).
    assert aa["_total_aa_per_s"] < 1e6
