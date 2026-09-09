from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_dnas_rare_event import sparse_gate  # noqa: E402


def test_support_counts_tracks_pooled_active_and_clustered_seeds():
    values = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
    )
    counts = sparse_gate.support_counts(values)
    assert counts.pooled_nonzero_ticks == 3
    assert counts.active_seeds == 2
    assert counts.clustered_seeds == 1


def test_holm_adjust_is_monotone_and_order_aware():
    adjusted = sparse_gate.holm_adjust([0.01, 0.04, 0.02])
    assert adjusted == [0.03, 0.04, 0.04]


def test_exact_underactivity_pvalue_matches_prereg_floor_examples():
    assert sparse_gate.exact_underactivity_pvalue(15, 31) < sparse_gate.DEFAULT_CONFIG.alpha_family / 3.0
    assert sparse_gate.exact_underactivity_pvalue(0, 6) < sparse_gate.DEFAULT_CONFIG.alpha_family / 3.0


def test_sparse_component_fails_if_karr_support_is_below_floor():
    karr = np.zeros((10, 3))
    oc = np.zeros_like(karr)
    karr[:5, 0] = 1.0
    oc[:5, 0] = 1.0
    result = sparse_gate.evaluate_sparse_component(oc, karr, scale=2.0)
    assert result["verdict"] == "PRIMARY_INSUFFICIENT_SAMPLES"


def test_sparse_component_rejects_zero_oc_when_cluster_support_is_adequate():
    karr = np.zeros((31, 2))
    oc = np.zeros_like(karr)
    karr[:, 0] = 1.0
    karr[:6, 1] = 1.0
    result = sparse_gate.evaluate_sparse_component(oc, karr, scale=2.0)
    assert result["karr_support"]["clustered_seeds"] == 6
    assert result["verdict"] == "PRIMARY_UNDERACTIVE"


def test_sparse_component_rejects_half_rate_underactivity_on_pooled_and_active_axes():
    karr = np.zeros((31, 2))
    oc = np.zeros_like(karr)
    karr[:, 0] = 1.0
    karr[:6, 1] = 1.0
    oc[:15, 0] = 1.0
    result = sparse_gate.evaluate_sparse_component(oc, karr, scale=2.0)
    rejected_axes = {axis["axis"] for axis in result["underactivity_axes"] if axis["rejected_underactivity"]}
    assert "pooled_nonzero_ticks" in rejected_axes
    assert "active_seeds" in rejected_axes
    assert result["verdict"] == "PRIMARY_UNDERACTIVE"


def test_process_passes_when_dense_and_sparse_components_match():
    oc = np.zeros((31, 2, 2))
    karr = np.zeros((31, 2, 2))
    oc[:, 0, 0] = 10.0
    karr[:, 0, 0] = 10.0
    oc[:, :, 1] = 1.0
    karr[:, :, 1] = 1.0
    result = sparse_gate.evaluate_process(
        oc,
        karr,
        {
            sparse_gate.VALUE_COMPONENT: 10.0,
            sparse_gate.SPARSE_COMPONENT: 2.0,
        },
    )
    assert result["delta_value_sum_metric"]["verdict"] == "PASS"
    assert result["delta_nnz_sparse_gate"]["verdict"] == "PASS"
    assert result["process_verdict"] == "PASS"
