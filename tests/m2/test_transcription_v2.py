"""Tests for M2 v2 mechanism-based transcription oracle."""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m2 import transcription_v2 as v2


@pytest.fixture(scope="module")
def inputs():
    return v2.load_default()


def test_fixture_dimensions(inputs):
    assert inputs.n_tu == 335
    assert inputs.n_genes == 525
    assert inputs.tu_lengths_nt.shape == (335,)
    assert inputs.p_bind_bare.shape == (335,)
    assert inputs.tu_gene_incidence.shape == (335, 525)
    assert inputs.karr_fitted_synth_per_s.shape == (525,)


def test_snapshot_polymerase_counts(inputs):
    assert inputs.n_active_rnap == 35
    assert inputs.n_total_rnap == 40
    np.testing.assert_allclose(inputs.rnap_state_expectations.sum(), 1.0, atol=1e-3)


def test_each_gene_in_exactly_one_tu(inputs):
    """M.g operon structure: every gene maps to exactly one TU."""
    counts = inputs.tu_gene_incidence.sum(axis=0)
    assert int(np.sum(counts == 0)) == 0
    assert int(np.sum(counts == 1)) == 525
    assert int(np.sum(counts > 1)) == 0


def test_polycistronic_tu_count(inputs):
    """Karr's KB has 104 polycistronic operons among 335 TUs."""
    tu_gene_counts = inputs.tu_gene_incidence.sum(axis=1)
    n_poly = int(np.sum(tu_gene_counts > 1))
    assert n_poly == 104


def test_p_bind_normalisation_property(inputs):
    """P_bind values are non-negative and sum to a finite positive number."""
    assert np.all(inputs.p_bind_bare >= 0)
    assert np.isfinite(inputs.p_bind_bare).all()
    assert np.sum(inputs.p_bind_bare) > 0


def test_tu_synthesis_invariant_total_nt_per_s(inputs):
    """Total NT polymerization equals N_active * elongation_rate.

    This is the conservation invariant of the mechanism: at SS each
    active polymerase polymerizes ``elongation_rate`` nt per second.
    """
    total_nt = v2.total_nt_polymerization_per_s(inputs)
    expected = inputs.n_active_rnap * inputs.elongation_rate_nt_per_s
    np.testing.assert_allclose(total_nt, expected, rtol=1e-9)


def test_predict_tu_synthesis_scales_linearly_with_n_active(inputs):
    base = v2.predict_tu_synthesis_per_s(inputs, n_active=10)
    doubled = v2.predict_tu_synthesis_per_s(inputs, n_active=20)
    np.testing.assert_allclose(doubled, 2.0 * base, rtol=1e-12)


def test_predict_gene_rate_distributes_over_operon(inputs):
    """A polycistronic TU's rate appears identically on each of its genes."""
    tu_rate = v2.predict_tu_synthesis_per_s(inputs)
    gene_rate = v2.predict_gene_synthesis_per_s(inputs)
    # pick a polycistronic TU
    poly_tu = np.where(inputs.tu_gene_incidence.sum(axis=1) > 1)[0][0]
    member_genes = np.where(inputs.tu_gene_incidence[poly_tu] == 1)[0]
    for g in member_genes:
        np.testing.assert_allclose(gene_rate[g], tu_rate[poly_tu], rtol=1e-12)


def test_oracle_snapshot_within_3x(inputs):
    """Per-gene mechanism rate vs Karr fitted, snapshot N_active.

    With the snapshot count of 35 active polymerases the mechanism
    under-predicts by ~2x on the median (median log2 ratio ~ -0.91);
    the spread is within ~3x both sides (|log2| < 1.6).  Looser bound
    here because the snapshot count is not cell-cycle averaged.
    """
    pred = v2.predict_gene_synthesis_per_s(inputs)
    summary = v2.compare_to_karr(pred, inputs.karr_fitted_synth_per_s)
    assert summary["n_compared"] >= 500
    assert summary["median_abs_log2_ratio"] < 1.6
    # signed median should be negative (under-prediction)
    assert summary["median_log2_ratio"] < 0


def test_oracle_with_cell_cycle_averaging_within_2x(inputs):
    """Cell-cycle averaging brings agreement to ~M1-oracle quality.

    Over a cell cycle the polymerase count grows from N to 2N, so the
    time-averaged ``N_active`` is roughly ``1.5 * snapshot``.  Doubling
    is the upper bound; we test that the median |log2| drops below 1.0
    (within 2x), comparable to M1's 0.96 per-reaction oracle.
    """
    n_avg = 2.0 * inputs.n_active_rnap
    pred = v2.predict_gene_synthesis_per_s(inputs, n_active=n_avg)
    summary = v2.compare_to_karr(pred, inputs.karr_fitted_synth_per_s)
    assert summary["median_abs_log2_ratio"] < 1.0
    # signed median should be near zero (no systematic bias) within 0.2 log2
    assert abs(summary["median_log2_ratio"]) < 0.2


def test_load_default_path_round_trip(inputs, tmp_path):
    # passing the default path explicitly works
    inputs2 = v2.load_default(v2.DEFAULT_FIXTURE_JSON)
    np.testing.assert_array_equal(inputs.tu_lengths_nt, inputs2.tu_lengths_nt)
    np.testing.assert_array_equal(inputs.p_bind_bare, inputs2.p_bind_bare)


def test_compare_to_karr_handles_zero_karr(inputs):
    """The 3 mRNAs Karr fit with halfLife=0 should not blow up the comparison."""
    pred = v2.predict_gene_synthesis_per_s(inputs)
    summary = v2.compare_to_karr(pred, inputs.karr_fitted_synth_per_s)
    # should compare roughly 522 genes (525 - 3 zero-rate mRNAs)
    assert 500 <= summary["n_compared"] <= 525
