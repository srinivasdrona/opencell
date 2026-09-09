from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_dnas_rare_event import two_sided_sparse_gate as gate  # noqa: E402


def test_exact_two_sided_pvalue_rejects_followup8_pooled_overactivity():
    # FOLLOWUP8 frozen pooled counts: OC 1486 vs Karr 65. The one-sided
    # "less" test used by sparse_gate.py cannot reject this (OC is not
    # underactive); the two-sided test must reject it as overactive.
    p = gate.exact_two_sided_pvalue(1486, 65)
    assert p < gate.DEFAULT_CONFIG.alpha_family / 3.0


def test_exact_two_sided_pvalue_still_rejects_zero_oc_underactivity():
    # Two-sided halves the one-sided tail, so the (0, 6) example from the
    # one-sided rule's own test suite no longer clears the same alpha budget
    # (2 * 0.5**6 = 0.03125 > 0.05/3); (0, 7) does (2 * 0.5**7 = 0.015625).
    p = gate.exact_two_sided_pvalue(0, 7)
    assert p < gate.DEFAULT_CONFIG.alpha_family / 3.0


def test_exact_two_sided_pvalue_symmetric_in_direction():
    assert gate.exact_two_sided_pvalue(90, 10) == gate.exact_two_sided_pvalue(10, 90)


def test_preregistration_examples_reject_the_frozen_followup8_pass():
    examples = gate.preregistration_examples()
    bound = examples["holm_alpha_per_test_upper_bound"]
    assert examples["followup8_pooled_1486_vs_65_two_sided_pvalue"] < bound
    assert examples["followup8_active_200_vs_58_two_sided_pvalue"] < bound
    assert examples["followup8_clustered_200_vs_7_two_sided_pvalue"] < bound


def test_sparse_component_rejects_extreme_overactivity_with_direction_label():
    karr = np.zeros((200, 100))
    oc = np.zeros_like(karr)
    # Reproduce the FOLLOWUP8 shape of the problem: Karr sparse (58 active
    # seeds, 7 clustered, 65 pooled hits total). 7 seeds get 2 nonzero ticks
    # each (clustered) and the other 51 active seeds get exactly 1
    # (7*2 + 51*1 = 65 pooled, 7 + 51 = 58 active). OC has hits everywhere.
    oc[:, :] = 1.0
    karr[:7, 0] = 1.0
    karr[:7, 1] = 1.0
    karr[7:58, 0] = 1.0
    result = gate.evaluate_sparse_component(oc, karr, scale=2.0)
    assert result["karr_support"]["pooled_nonzero_ticks"] == 65
    assert result["karr_support"]["active_seeds"] == 58
    assert result["karr_support"]["clustered_seeds"] == 7
    assert result["verdict"] == "PRIMARY_OVERACTIVE"
    directions = {axis["axis"]: axis["direction"] for axis in result["axes"] if axis["rejected"]}
    assert directions.get("pooled_nonzero_ticks") == "OVERACTIVE"
    assert directions.get("active_seeds") == "OVERACTIVE"
    assert directions.get("clustered_seeds") == "OVERACTIVE"


def test_sparse_component_rejects_zero_oc_underactivity_when_karr_is_active():
    karr = np.zeros((31, 2))
    oc = np.zeros_like(karr)
    karr[:, 0] = 1.0
    karr[:6, 1] = 1.0
    result = gate.evaluate_sparse_component(oc, karr, scale=2.0)
    assert result["verdict"] == "PRIMARY_UNDERACTIVE"
    directions = {axis["axis"]: axis["direction"] for axis in result["axes"] if axis["rejected"]}
    assert directions.get("clustered_seeds") == "UNDERACTIVE"


def test_sparse_component_passes_when_matched():
    karr = np.zeros((31, 2))
    oc = np.zeros_like(karr)
    karr[:, 0] = 1.0
    oc[:, 0] = 1.0
    karr[:6, 1] = 1.0
    oc[:6, 1] = 1.0
    result = gate.evaluate_sparse_component(oc, karr, scale=2.0)
    assert result["verdict"] == "PASS"


def test_sparse_component_insufficient_samples_when_pooled_total_is_zero():
    karr = np.zeros((5, 2))
    oc = np.zeros_like(karr)
    result = gate.evaluate_sparse_component(oc, karr, scale=1.0)
    assert result["verdict"] == "PRIMARY_INSUFFICIENT_SAMPLES"


def test_process_fails_on_overactivity_even_though_value_metric_passes():
    oc = np.zeros((200, 100, 2))
    karr = np.zeros((200, 100, 2))
    oc[:, 0, 0] = 10.0
    karr[:, 0, 0] = 10.0
    oc[:, :, 1] = 1.0
    karr[:58, 0, 1] = 1.0
    karr[:7, 1, 1] = 1.0
    result = gate.evaluate_process(
        oc,
        karr,
        {gate.VALUE_COMPONENT: 10.0, gate.SPARSE_COMPONENT: 2.0},
    )
    assert result["delta_value_sum_metric"]["verdict"] == "PASS"
    assert result["process_verdict"] == "PRIMARY_OVERACTIVE"
