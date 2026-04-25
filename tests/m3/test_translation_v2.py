"""Tests for M3 v2 ribosome-mechanics translation oracle.

See module docstring of `opencell.m3.translation_v2` for the
finding that v1's ``synth_rate_per_s`` is decay-balance only and
underrates the true polymerization by ~23x; tests here therefore
validate the mechanism's *invariants* and *physiological scale*
rather than per-protein agreement with v1.
"""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m3 import translation_v2 as v2


@pytest.fixture(scope="module")
def inputs():
    return v2.load_default()


def test_fixture_dimensions(inputs):
    assert inputs.n_proteins == 482
    assert inputs.length_aa.shape == (482,)
    assert inputs.mrna_counts.shape == (482,)
    assert inputs.karr_v1_synth_per_s.shape == (482,)
    assert inputs.n_ribosomes_bound_per_mrna.shape == (482,)


def test_snapshot_ribosome_counts(inputs):
    assert inputs.n_active_ribosomes == 56
    assert inputs.n_total_ribosomes == 136
    np.testing.assert_allclose(inputs.ribosome_state_occupancies.sum(), 1.0, atol=1e-3)
    # snapshot active fraction
    assert 0.3 < v2.fraction_active_from_occupancies(inputs) < 0.6


def test_snapshot_ribosomes_bound_matches_active(inputs):
    """Sanity: every active ribosome is bound to exactly one mRNA."""
    n_bound = int(inputs.n_ribosomes_bound_per_mrna.sum())
    assert n_bound == inputs.n_active_ribosomes


def test_mrna_counts_are_sparse(inputs):
    """Snapshot mRNA pool is sparse (start of cell cycle)."""
    nz = int(np.sum(inputs.mrna_counts > 0))
    total = float(inputs.mrna_counts.sum())
    assert nz == 98
    assert total == 143


def test_total_aa_polymerization_invariant(inputs):
    """Conservation: total aa/s == N_active * elongation_rate."""
    total_aa = v2.total_aa_polymerization_per_s(inputs)
    expected = inputs.n_active_ribosomes * inputs.elongation_rate_aa_per_s
    np.testing.assert_allclose(total_aa, expected, rtol=1e-9)
    assert total_aa == pytest.approx(896.0, rel=1e-9)


def test_predict_scales_linearly_with_n_active(inputs):
    base = v2.predict_synthesis_per_s(inputs, n_active=10)
    doubled = v2.predict_synthesis_per_s(inputs, n_active=20)
    np.testing.assert_allclose(doubled, 2.0 * base, rtol=1e-12)


def test_predict_only_for_present_mrnas(inputs):
    """Proteins with zero mRNA in the snapshot get zero predicted rate."""
    pred = v2.predict_synthesis_per_s(inputs)
    no_mrna = inputs.mrna_counts == 0
    np.testing.assert_array_equal(pred[no_mrna], np.zeros(int(no_mrna.sum())))


def test_predict_handles_empty_mrna_pool(inputs):
    """If mRNA pool is empty (degenerate input), prediction is all zeros."""
    pred = v2.predict_synthesis_per_s(inputs, mrna_counts=np.zeros(inputs.n_proteins))
    np.testing.assert_array_equal(pred, np.zeros(inputs.n_proteins))


def test_mechanism_total_exceeds_v1_decay_balance(inputs):
    """Mechanism polymerizes ~23x more aa/s than v1's decay-balance.

    Documented finding: v1 ``synth_rate_per_s = counts_mature * decay``
    omits cell-growth dilution and the 119 immortal proteins, so it is
    a strict lower bound on production.  At the snapshot the gap is ~23x.
    """
    total_aa_mech = v2.total_aa_polymerization_per_s(inputs)
    total_aa_v1 = float(np.sum(inputs.karr_v1_synth_per_s * inputs.length_aa))
    ratio = total_aa_mech / total_aa_v1
    assert 15.0 < ratio < 50.0  # measured 23x


def test_mechanism_predicts_above_doubling_requirement(inputs):
    """Mechanism rate is comfortably above the bare doubling requirement.

    M.g cell cycle is ~9 hr; total protein content ~ sum(counts*length_aa).
    Doubling that in 9hr requires ~ ln(2)*content/cycle aa/s.  Mechanism
    should be at least 3x this (polymerization also services turnover).
    """
    total_aa_mech = v2.total_aa_polymerization_per_s(inputs)
    # use M3 v1 fixture's snapshot to compute total content
    from opencell.m3 import load_default as load_v1
    v1 = load_v1()
    total_content_aa = float(np.sum(v1.counts_mature * v1.length_aa))
    cycle_s = 9.0 * 3600.0
    doubling_req_aa_per_s = np.log(2) * total_content_aa / cycle_s
    assert total_aa_mech >= 3.0 * doubling_req_aa_per_s


def test_predict_distributes_across_present_mrnas(inputs):
    """Per-protein rate is proportional to mRNA copy count.

    The formula ``synth_i = N*k*mRNA_i / sum(m*L)`` has length cancel
    only inside the bound-fraction term, not in the per-protein rate;
    the rate per mRNA copy is therefore the SAME constant across all
    proteins regardless of length.
    """
    pred = v2.predict_synthesis_per_s(inputs)
    has_mrna = inputs.mrna_counts > 0
    rate_per_copy = pred[has_mrna] / inputs.mrna_counts[has_mrna]
    np.testing.assert_allclose(rate_per_copy, rate_per_copy[0], rtol=1e-12)
    # cross-check with the closed form
    denom = float(np.sum(inputs.mrna_counts * inputs.length_aa))
    expected = (inputs.n_active_ribosomes
                * inputs.elongation_rate_aa_per_s / denom)
    np.testing.assert_allclose(rate_per_copy[0], expected, rtol=1e-12)


def test_load_default_path_round_trip(inputs):
    inputs2 = v2.load_default(v2.DEFAULT_FIXTURE_JSON)
    np.testing.assert_array_equal(inputs.mrna_counts, inputs2.mrna_counts)
    np.testing.assert_array_equal(inputs.length_aa, inputs2.length_aa)
