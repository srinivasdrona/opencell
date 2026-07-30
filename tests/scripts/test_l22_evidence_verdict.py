"""Unit tests for scripts/l22_evidence/verdict.py mechanical re-derivation.

Constructs synthetic channel/result payloads directly (no real runner
invocation, no MATLAB, no scipy) to prove the re-derivation logic ignores
stored verdict strings and recomputes from raw numbers only.

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_verdict.py -v`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402
from scripts.l22_evidence.catalog import ProcessEntry  # noqa: E402


def _entry(**overrides) -> ProcessEntry:
    base = dict(
        name="FakeProcess",
        bucket="ALGORITHMIC_SHALLOW",
        harness_type="design_a_per_tick",
        m_ticks=100,
        n_seeds=50,
        primary_channel="substrates",
        closed_form_dominant="false",
        event_channels=(),
        output_channels=("substrates",),
        primary_distance="per_tick_vector_w1_mean",
    )
    base.update(overrides)
    return ProcessEntry(**base)


def _channel(**overrides) -> dict:
    base = dict(
        verdict="PASS",
        w1_oc_vs_karr=0.1,
        threshold=1.0,
        q95_null=0.05,
        n_nonzero_oc=100,
        n_nonzero_karr=100,
        is_primary=True,
        is_event_channel=False,
        aggregation="per_tick_vector_w1_mean",
    )
    base.update(overrides)
    return base


def _result(*, channels: dict, seeds=None, ticks=100, warnings=None, **extra) -> dict:
    payload = {
        "process": "FakeProcess",
        "verdict": "PASS",
        "seeds": list(range(50)) if seeds is None else seeds,
        "ticks": ticks,
        "channels": channels,
        "warnings": warnings or [],
    }
    payload.update(extra)
    return payload


# --- Channel-level ------------------------------------------------------------


def test_channel_seed_noise_below_null():
    verdict, reasons = vd.rederive_channel("substrates", _channel(w1_oc_vs_karr=0.01), is_primary=True)
    assert verdict == "SEED_NOISE"
    assert reasons == []


def test_channel_pass_between_null_and_threshold():
    verdict, reasons = vd.rederive_channel("substrates", _channel(w1_oc_vs_karr=0.5), is_primary=True)
    assert verdict == "PASS"
    assert reasons == []


def test_channel_fail_above_threshold_even_if_stored_verdict_says_pass():
    """Tampered stored PASS cannot override a failing raw metric."""
    payload = _channel(verdict="PASS", w1_oc_vs_karr=5.0, threshold=1.0)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("exceeds threshold" in reason for reason in reasons)


def test_channel_missing_evaluator_for_unknown_aggregation():
    payload = _channel(aggregation="some_future_metric_type")
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("some_future_metric_type" in reason for reason in reasons)


def test_channel_missing_evaluator_for_projection_aggregation_without_per_component_block():
    """aggregation says per_component_scaled but the raw per_component block is absent."""
    payload = _channel(aggregation="per_component_scaled")
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("per_component" in reason for reason in reasons)


def test_channel_missing_evaluator_for_hurdle_aggregation_without_hurdle_block():
    """aggregation says hurdle_* but the raw hurdle block is absent."""
    payload = _channel(aggregation="hurdle_event_rate_plus_conditional_scaled_distance")
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_channel_missing_evaluator_for_missing_raw_fields():
    payload = {"verdict": "PASS", "is_primary": True, "is_event_channel": False}
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_channel_primary_vacuous_when_both_sides_zero_nonzero():
    payload = _channel(n_nonzero_oc=0, n_nonzero_karr=0)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_VACUOUS


def test_channel_primary_activity_missing_when_oc_zero_karr_nonzero():
    """P2 zero-activity guard: OC never fired at all while Karr shows real
    activity -- this is NOT the symmetric both-zero VACUOUS case, and must
    not be laundered into INSUFFICIENT_SAMPLES (non-gating) either."""
    payload = _channel(n_nonzero_oc=0, n_nonzero_karr=500)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_ACTIVITY_MISSING
    assert any("substrates" in reason and "500" in reason for reason in reasons)


def test_channel_activity_missing_check_skipped_for_non_primary():
    """The same OC-zero/Karr-nonzero asymmetry on a non-primary channel is
    not gated by this guard -- it still falls through to the ordinary
    MIN_NONZERO_EVENTS/w1 logic (INSUFFICIENT_SAMPLES here, since 0 < 30)."""
    payload = _channel(n_nonzero_oc=0, n_nonzero_karr=500)
    verdict, reasons = vd.rederive_channel("secondary", payload, is_primary=False)
    assert verdict == "INSUFFICIENT_SAMPLES"
    assert reasons == []


@pytest.mark.parametrize("n_nonzero_oc", [-1, -100])
def test_channel_negative_nonzero_count_is_missing_evaluator(n_nonzero_oc):
    """`_is_nonnegative_count` validation (mirrors the pre-existing
    per_component-level check): a negative n_nonzero_oc/karr is impossible
    raw evidence and must not be silently coerced into any real verdict."""
    payload = _channel(n_nonzero_oc=n_nonzero_oc, n_nonzero_karr=100)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("n_nonzero_oc" in reason for reason in reasons)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_channel_non_finite_nonzero_count_is_missing_evaluator(bad_value):
    payload = _channel(n_nonzero_karr=bad_value)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("n_nonzero_karr" in reason for reason in reasons)


def test_channel_negative_nonzero_count_check_applies_to_non_primary_too():
    payload = _channel(n_nonzero_oc=-1, n_nonzero_karr=100)
    verdict, reasons = vd.rederive_channel("secondary", payload, is_primary=False)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


@pytest.mark.parametrize("low_count", list(range(1, 30)))
def test_channel_primary_insufficient_samples_low_oc_count(low_count):
    """Primary low-sample false-green fix: OC below MIN_NONZERO_EVENTS=30
    (Karr healthy) must gate, for every count from 1 through 29."""
    payload = _channel(n_nonzero_oc=low_count, n_nonzero_karr=100)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES
    assert any(str(low_count) in reason for reason in reasons)


@pytest.mark.parametrize("low_count", list(range(1, 30)))
def test_channel_primary_insufficient_samples_low_karr_count(low_count):
    """Same as above, mirrored on the Karr side (OC healthy)."""
    payload = _channel(n_nonzero_oc=100, n_nonzero_karr=low_count)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES
    assert any(str(low_count) in reason for reason in reasons)


@pytest.mark.parametrize("low_count", list(range(1, 30)))
def test_channel_primary_insufficient_samples_both_sides_low(low_count):
    """Both sides equally low (and nonzero) must also gate, not just the
    asymmetric single-side cases above."""
    payload = _channel(n_nonzero_oc=low_count, n_nonzero_karr=low_count)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES


def test_channel_primary_insufficient_samples_exactly_min_nonzero_events_passes_through():
    """Exactly MIN_NONZERO_EVENTS=30 on both sides is NOT insufficient (the
    comparison is strict `<`, matching the pre-existing non-primary
    INSUFFICIENT_SAMPLES boundary convention) -- falls through to the real
    w1-vs-threshold computation."""
    payload = _channel(n_nonzero_oc=schema.MIN_NONZERO_EVENTS, n_nonzero_karr=schema.MIN_NONZERO_EVENTS)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == "PASS"
    assert reasons == []


def test_channel_primary_insufficient_samples_skipped_for_non_primary():
    """A non-primary channel with the exact same low counts falls through to
    the pre-existing, non-gating generic INSUFFICIENT_SAMPLES fallback
    instead -- PRIMARY_INSUFFICIENT_SAMPLES only ever applies to is_primary
    channels."""
    payload = _channel(n_nonzero_oc=5, n_nonzero_karr=5)
    verdict, reasons = vd.rederive_channel("secondary", payload, is_primary=False)
    assert verdict == "INSUFFICIENT_SAMPLES"
    assert reasons == []


def test_channel_primary_insufficient_samples_checked_after_vacuous_and_activity_missing():
    """Ordering: both-zero must still resolve to PRIMARY_VACUOUS (not
    PRIMARY_INSUFFICIENT_SAMPLES), and OC-zero/Karr-nonzero must still
    resolve to PRIMARY_ACTIVITY_MISSING -- PRIMARY_INSUFFICIENT_SAMPLES only
    fires once both of those more specific cases are ruled out."""
    both_zero = _channel(n_nonzero_oc=0, n_nonzero_karr=0)
    verdict, _ = vd.rederive_channel("substrates", both_zero, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_VACUOUS

    activity_missing = _channel(n_nonzero_oc=0, n_nonzero_karr=5)
    verdict, _ = vd.rederive_channel("substrates", activity_missing, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_ACTIVITY_MISSING


def test_channel_insufficient_samples_below_min_nonzero():
    payload = _channel(n_nonzero_oc=5, n_nonzero_karr=5, is_primary=False)
    verdict, reasons = vd.rederive_channel("secondary", payload, is_primary=False)
    assert verdict == "INSUFFICIENT_SAMPLES"


def test_channel_event_channel_is_deferred_regardless_of_metrics():
    payload = _channel(is_event_channel=True, w1_oc_vs_karr=999.0)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "EVENT_CHANNEL_DEFERRED"
    assert reasons == []


# --- per_component_scaled ---------------------------------------------------------


def _per_component_payload(**component_overrides) -> dict:
    """A clean, passing 2-component per_component_scaled payload."""
    payload = {
        "verdict": "PASS",
        "aggregation": "per_component_scaled",
        "is_primary": True,
        "is_event_channel": False,
        "per_component": {
            "component_raw_w1": {"comp_a": 1.0, "comp_b": 0.5},
            "component_scales": {"comp_a": 5.0, "comp_b": 5.0},
            "scaled_distance_threshold": 1.0,
            "component_n_nonzero_oc": {"comp_a": 100, "comp_b": 100},
            "component_n_nonzero_karr": {"comp_a": 100, "comp_b": 100},
            "component_verdicts": {"comp_a": "PASS", "comp_b": "PASS"},
            "joint_verdict": "PASS",
        },
    }
    payload["per_component"].update(component_overrides)
    return payload


def test_per_component_pass_when_all_components_within_threshold():
    verdict, reasons = vd.rederive_channel("chromosome", _per_component_payload(), is_primary=True)
    assert verdict == "PASS"
    assert reasons == []


def test_per_component_fail_ignores_tampered_stored_pass():
    """Stored component_verdicts/joint_verdict say PASS; raw numbers say FAIL."""
    payload = _per_component_payload(
        component_raw_w1={"comp_a": 50.0, "comp_b": 0.5},
        component_verdicts={"comp_a": "PASS", "comp_b": "PASS"},
        joint_verdict="PASS",
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("comp_a" in reason for reason in reasons)


def test_per_component_pass_ignores_tampered_stored_fail():
    """Stored component_verdicts/joint_verdict say FAIL; raw numbers actually PASS."""
    payload = _per_component_payload(
        component_verdicts={"comp_a": "FAIL", "comp_b": "FAIL"},
        joint_verdict="FAIL",
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"
    assert reasons == []


def test_per_component_joint_fails_if_only_one_component_fails():
    payload = _per_component_payload(component_raw_w1={"comp_a": 1.0, "comp_b": 500.0})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("comp_b" in reason for reason in reasons)
    assert not any("comp_a" in reason for reason in reasons)


def test_per_component_boundary_equality_is_pass():
    """scaled_w1 exactly equal to the threshold is PASS (<=, not <)."""
    payload = _per_component_payload(component_raw_w1={"comp_a": 5.0, "comp_b": 5.0})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


def test_per_component_missing_raw_field_is_missing_evaluator():
    payload = _per_component_payload()
    del payload["per_component"]["component_scales"]
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("component_scales" in reason for reason in reasons)


def test_per_component_mismatched_component_name_sets_is_missing_evaluator():
    payload = _per_component_payload(component_scales={"comp_a": 5.0, "comp_other": 5.0})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_per_component_nan_raw_w1_is_missing_evaluator():
    payload = _per_component_payload(component_raw_w1={"comp_a": float("nan"), "comp_b": 0.5})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_per_component_inf_raw_w1_is_missing_evaluator():
    payload = _per_component_payload(component_raw_w1={"comp_a": float("inf"), "comp_b": 0.5})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_per_component_negative_nonzero_count_is_missing_evaluator():
    payload = _per_component_payload(component_n_nonzero_oc={"comp_a": -1, "comp_b": 100})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_per_component_zero_scale_is_missing_evaluator():
    payload = _per_component_payload(component_scales={"comp_a": 0.0, "comp_b": 5.0})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_per_component_primary_vacuous_when_all_components_zero_nonzero_both_sides():
    payload = _per_component_payload(
        component_raw_w1={"comp_a": 0.0, "comp_b": 0.0},
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 0},
        component_n_nonzero_karr={"comp_a": 0, "comp_b": 0},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_VACUOUS


def test_per_component_not_vacuous_when_only_one_component_is_zero_nonzero():
    """One trivial (always-zero) component alongside a real one is a genuine PASS, not vacuous."""
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 0, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


def test_per_component_activity_missing_when_one_component_oc_zero_karr_nonzero():
    """P2 zero-activity guard: comp_a's OC side never fired while Karr's did
    -- must be non-green (PRIMARY_ACTIVITY_MISSING), not silently passed
    through a large `component_scales` divisor, and distinct from the
    both-zero-on-both-sides PRIMARY_CHANNEL_VACUOUS case."""
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 4000, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_ACTIVITY_MISSING
    assert any("comp_a" in reason and "4000" in reason for reason in reasons)


def test_per_component_activity_missing_does_not_penalize_both_zero_component():
    """A component where BOTH sides are genuinely zero must never trip the
    asymmetric activity-missing guard, only the symmetric vacuous one (and
    only when ALL components are both-zero, which is not the case here)."""
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 0, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"
    assert not any(schema.STATUS_PRIMARY_ACTIVITY_MISSING in reason for reason in reasons)


def test_per_component_activity_missing_check_skipped_for_non_primary():
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 4000, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "PASS"


def test_per_component_vacuous_check_skipped_for_non_primary():
    payload = _per_component_payload(
        component_raw_w1={"comp_a": 0.0, "comp_b": 0.0},
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 0},
        component_n_nonzero_karr={"comp_a": 0, "comp_b": 0},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "PASS"


@pytest.mark.parametrize("low_count", list(range(1, 30)))
def test_per_component_primary_insufficient_samples_low_oc_count(low_count):
    """Primary low-sample false-green fix, per_component flavor -- this is
    the real DNASupercoiling bug case (n_oc=17, n_karr=24 on component
    'linkingNumbers.delta_nnz'): a single primary component below
    MIN_NONZERO_EVENTS=30 on either side must gate the WHOLE channel
    (joint semantics), even though comp_b is healthy."""
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": low_count, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 100, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES
    assert any("comp_a" in reason for reason in reasons)


@pytest.mark.parametrize("low_count", list(range(1, 30)))
def test_per_component_primary_insufficient_samples_low_karr_count(low_count):
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 100, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": low_count, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES
    assert any("comp_a" in reason for reason in reasons)


def test_per_component_primary_insufficient_samples_exactly_min_nonzero_events_passes_through():
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": schema.MIN_NONZERO_EVENTS, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": schema.MIN_NONZERO_EVENTS, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


def test_per_component_primary_insufficient_samples_trivial_zero_component_exempt():
    """A component where BOTH sides are genuinely zero (the pre-existing
    trivial-always-zero exemption -- see
    test_per_component_not_vacuous_when_only_one_component_is_zero_nonzero)
    must NOT be treated as insufficient-samples either: 0 < 30 is
    technically true, but this is the documented "always inactive, not
    under-sampled" case, distinct from a component that fired a FEW times."""
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 0, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"
    assert not any(schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES in reason for reason in reasons)


def test_per_component_primary_insufficient_samples_skipped_for_non_primary():
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 3, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 3, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "PASS"
    assert not any(schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES in reason for reason in reasons)


def test_per_component_primary_insufficient_samples_checked_after_activity_missing():
    """Ordering: the OC-zero/Karr-nonzero asymmetric case on comp_a must
    still resolve to PRIMARY_ACTIVITY_MISSING, not PRIMARY_INSUFFICIENT_SAMPLES,
    even though 0 < MIN_NONZERO_EVENTS is also true."""
    payload = _per_component_payload(
        component_n_nonzero_oc={"comp_a": 0, "comp_b": 100},
        component_n_nonzero_karr={"comp_a": 4000, "comp_b": 100},
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_ACTIVITY_MISSING


# --- hurdle_event_rate_plus_conditional_scaled_distance ---------------------------


def _hurdle_payload(**hurdle_overrides) -> dict:
    """A clean, passing hurdle payload with 2 conditional components."""
    payload = {
        "verdict": "PASS",
        "aggregation": "hurdle_event_rate_plus_conditional_scaled_distance",
        "is_primary": True,
        "is_event_channel": False,
        "hurdle": {
            "event_rate_diff": 0.02,
            "event_rate_threshold": 0.10,
            "conditional_w1_per_component": {"component_1": 1.0, "component_2": 0.5},
            "conditional_scaled_w1_per_component": {"component_1": 0.2, "component_2": 0.1},
            "conditional_component_scales": {"component_1": 5.0, "component_2": 5.0},
            "conditional_scaled_distance_threshold": 1.0,
            "n_events_oc": 40,
            "n_events_karr": 42,
            "component_verdicts": {"component_1": "PASS", "component_2": "PASS"},
            "joint_verdict": "PASS",
        },
    }
    payload["hurdle"].update(hurdle_overrides)
    return payload


def test_hurdle_pass_when_event_rate_and_all_conditionals_within_threshold():
    verdict, reasons = vd.rederive_channel("chromosome", _hurdle_payload(), is_primary=True)
    assert verdict == "PASS"
    assert reasons == []


def test_hurdle_fail_ignores_tampered_stored_pass_on_event_rate():
    payload = _hurdle_payload(event_rate_diff=0.9, joint_verdict="PASS")
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("event_rate_diff" in reason for reason in reasons)


def test_hurdle_fail_ignores_tampered_stored_pass_on_conditional_component():
    payload = _hurdle_payload(
        conditional_w1_per_component={"component_1": 50.0, "component_2": 0.5},
        component_verdicts={"component_1": "PASS", "component_2": "PASS"},
        joint_verdict="PASS",
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("component_1" in reason for reason in reasons)


def test_hurdle_pass_ignores_tampered_stored_fail():
    payload = _hurdle_payload(component_verdicts={"component_1": "FAIL", "component_2": "FAIL"}, joint_verdict="FAIL")
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


def test_hurdle_joint_fails_if_only_one_conditional_component_fails():
    payload = _hurdle_payload(conditional_w1_per_component={"component_1": 1.0, "component_2": 500.0})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("component_2" in reason for reason in reasons)
    assert not any("component_1" in reason for reason in reasons)


def test_hurdle_boundary_equality_on_event_rate_is_pass():
    payload = _hurdle_payload(event_rate_diff=0.10, event_rate_threshold=0.10)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


def test_hurdle_boundary_equality_on_conditional_distance_is_pass():
    payload = _hurdle_payload(conditional_w1_per_component={"component_1": 5.0, "component_2": 0.5})
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


def test_hurdle_missing_raw_field_is_missing_evaluator():
    payload = _hurdle_payload()
    del payload["hurdle"]["conditional_component_scales"]
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("conditional_component_scales" in reason for reason in reasons)


def test_hurdle_nan_event_rate_diff_is_missing_evaluator():
    payload = _hurdle_payload(event_rate_diff=float("nan"))
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_hurdle_negative_event_count_is_missing_evaluator():
    payload = _hurdle_payload(n_events_oc=-5)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_hurdle_zero_events_on_both_sides_is_primary_vacuous_not_pass():
    """The runner's own joint_verdict is trivially PASS when nothing ever fires
    on either side (see test_hurdle_distance_handles_all_zero_event_surface in
    test_l2_2_design_a_projections.py); the mechanical re-derivation must not
    launder that into a green row."""
    payload = _hurdle_payload(
        event_rate_diff=0.0,
        conditional_w1_per_component={"component_1": 0.0, "component_2": 0.0},
        n_events_oc=0,
        n_events_karr=0,
        joint_verdict="PASS",
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_VACUOUS


def test_hurdle_zero_events_vacuity_skipped_for_non_primary():
    payload = _hurdle_payload(
        event_rate_diff=0.0,
        conditional_w1_per_component={"component_1": 0.0, "component_2": 0.0},
        n_events_oc=0,
        n_events_karr=0,
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "PASS"


def test_hurdle_activity_missing_when_oc_zero_events_karr_nonzero():
    """P2 zero-activity guard, hurdle flavor: OC recorded zero events across
    the ensemble while Karr recorded real events -- distinct from the
    symmetric both-zero VACUOUS case, and must not be silently PASSed."""
    payload = _hurdle_payload(n_events_oc=0, n_events_karr=42)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_ACTIVITY_MISSING
    assert any("42" in reason for reason in reasons)


def test_hurdle_activity_missing_check_skipped_for_non_primary():
    payload = _hurdle_payload(n_events_oc=0, n_events_karr=42)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "PASS"


def test_hurdle_activity_missing_preserves_accumulated_reasons():
    """Item 3 fix: the PRIMARY_ACTIVITY_MISSING return branch used to
    REPLACE `reasons` with a fresh single-item list, silently discarding any
    FAIL reasons already accumulated from the event-rate/conditional-
    component checks above it (e.g. a hand-tampered stored PASS on those
    earlier checks). It must now APPEND and preserve them."""
    payload = _hurdle_payload(
        event_rate_diff=0.9,  # accumulates a FAIL reason before the OC/Karr check runs
        conditional_w1_per_component={"component_1": 50.0, "component_2": 0.5},  # accumulates a 2nd
        n_events_oc=0,
        n_events_karr=42,
        joint_verdict="PASS",
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_ACTIVITY_MISSING
    assert any("event_rate_diff" in reason for reason in reasons)
    assert any("component_1" in reason for reason in reasons)
    assert any(schema.STATUS_PRIMARY_ACTIVITY_MISSING in reason for reason in reasons)
    assert len(reasons) == 3


@pytest.mark.parametrize("low_count", list(range(1, 30)))
def test_hurdle_primary_insufficient_samples_low_oc_event_count(low_count):
    """Primary low-sample false-green fix, hurdle flavor: a nonzero-but-low
    OC event count (Karr healthy) must gate."""
    payload = _hurdle_payload(n_events_oc=low_count, n_events_karr=42)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES
    assert any(str(low_count) in reason for reason in reasons)


@pytest.mark.parametrize("low_count", list(range(1, 30)))
def test_hurdle_primary_insufficient_samples_low_karr_event_count(low_count):
    payload = _hurdle_payload(n_events_oc=40, n_events_karr=low_count)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES
    assert any(str(low_count) in reason for reason in reasons)


def test_hurdle_primary_insufficient_samples_exactly_min_nonzero_events_passes_through():
    payload = _hurdle_payload(
        n_events_oc=schema.MIN_NONZERO_EVENTS,
        n_events_karr=schema.MIN_NONZERO_EVENTS,
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


def test_hurdle_primary_insufficient_samples_preserves_accumulated_reasons():
    payload = _hurdle_payload(
        event_rate_diff=0.9,
        n_events_oc=5,
        n_events_karr=42,
        joint_verdict="PASS",
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES
    assert any("event_rate_diff" in reason for reason in reasons)
    assert any(schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES in reason for reason in reasons)
    assert len(reasons) == 2


def test_hurdle_primary_insufficient_samples_skipped_for_non_primary():
    payload = _hurdle_payload(n_events_oc=5, n_events_karr=5)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "PASS"


def test_hurdle_primary_insufficient_samples_checked_after_vacuous_and_activity_missing():
    both_zero = _hurdle_payload(n_events_oc=0, n_events_karr=0, event_rate_diff=0.0,
                                 conditional_w1_per_component={"component_1": 0.0, "component_2": 0.0})
    verdict, _ = vd.rederive_channel("chromosome", both_zero, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_VACUOUS

    activity_missing = _hurdle_payload(n_events_oc=0, n_events_karr=5)
    verdict, _ = vd.rederive_channel("chromosome", activity_missing, is_primary=True)
    assert verdict == schema.STATUS_PRIMARY_ACTIVITY_MISSING


def test_hurdle_no_conditional_components_gates_on_event_rate_alone():
    payload = _hurdle_payload(
        conditional_w1_per_component={},
        conditional_scaled_w1_per_component={},
        conditional_component_scales={},
        component_verdicts={},
        n_events_oc=40,
        n_events_karr=42,
    )
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == "PASS"


# --- fva_feasibility ---------------------------------------------------------------


def _fva_payload(**overrides) -> dict:
    payload = {
        "verdict": "PASS",
        "aggregation": "fva_feasibility",
        "is_primary": True,
        "is_event_channel": False,
        "fva_feasibility_fraction": 1.0,
        "fva_feasible_pairs": 100,
        "fva_pairs_total": 100,
        "fva_tolerance": 2.0,
        "fva_threshold": 0.99,
    }
    payload.update(overrides)
    return payload


def test_fva_pass_when_fraction_meets_threshold():
    verdict, reasons = vd.rederive_channel("substrates", _fva_payload(), is_primary=True)
    assert verdict == "PASS"
    assert reasons == []


def test_fva_fail_ignores_tampered_stored_pass():
    payload = _fva_payload(verdict="PASS", fva_feasible_pairs=10, fva_feasibility_fraction=0.10)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("below fva_threshold" in reason for reason in reasons)


def test_fva_pass_ignores_tampered_stored_fail():
    payload = _fva_payload(verdict="FAIL", fva_feasible_pairs=100, fva_pairs_total=100, fva_feasibility_fraction=1.0)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == "PASS"


def test_fva_boundary_equality_at_threshold_is_pass():
    payload = _fva_payload(fva_feasible_pairs=99, fva_pairs_total=100, fva_feasibility_fraction=0.99, fva_threshold=0.99)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == "PASS"


def test_fva_just_below_threshold_fails():
    payload = _fva_payload(fva_feasible_pairs=98, fva_pairs_total=100, fva_feasibility_fraction=0.98, fva_threshold=0.99)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL


def test_fva_total_pairs_zero_fails_honest_not_vacuous_pass():
    payload = _fva_payload(fva_feasible_pairs=0, fva_pairs_total=0, fva_feasibility_fraction=0.0)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("fva_pairs_total" in reason for reason in reasons)


def test_fva_inconsistent_fraction_fails():
    """Stored fva_feasibility_fraction disagrees with feasible_pairs/total_pairs."""
    payload = _fva_payload(fva_feasible_pairs=50, fva_pairs_total=100, fva_feasibility_fraction=0.99)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL
    assert any("inconsistent" in reason for reason in reasons)


def test_fva_feasible_exceeds_total_fails():
    payload = _fva_payload(fva_feasible_pairs=150, fva_pairs_total=100, fva_feasibility_fraction=1.5)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_FAIL


def test_fva_negative_feasible_pairs_is_missing_evaluator():
    payload = _fva_payload(fva_feasible_pairs=-1)
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_fva_nan_threshold_is_missing_evaluator():
    payload = _fva_payload(fva_threshold=float("nan"))
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR


def test_fva_missing_raw_field_is_missing_evaluator():
    payload = _fva_payload()
    del payload["fva_tolerance"]
    verdict, reasons = vd.rederive_channel("substrates", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("fva_tolerance" in reason for reason in reasons)


# --- Process-level --------------------------------------------------------------


def test_process_pass_when_all_gateable_channels_clean():
    entry = _entry()
    result = _result(channels={"substrates": _channel()})
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_PASS
    assert outcome.reasons == []


def test_process_stored_pass_cannot_override_failing_channel():
    entry = _entry()
    result = _result(channels={"substrates": _channel(verdict="PASS", w1_oc_vs_karr=99.0, threshold=1.0)})
    result["verdict"] = "PASS"
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL


def test_process_nm_mismatch_old_m10_vs_catalog_m100():
    """Old M=10 evidence presented against a catalog that now says M=100."""
    entry = _entry(m_ticks=100, n_seeds=50)
    result = _result(channels={"substrates": _channel()}, ticks=10)
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("NM_MISMATCH" in reason and "100" in reason and "10" in reason for reason in outcome.reasons)


def test_process_n_mismatch_seed_count():
    entry = _entry(n_seeds=50)
    result = _result(channels={"substrates": _channel()}, seeds=list(range(3)))
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("NM_MISMATCH" in reason for reason in outcome.reasons)


@pytest.mark.parametrize(
    "sentinel",
    [
        "KARR_SINGLE_SEED_REUSED: some detail",
        "TRIVIAL_RNG_LEAK: some detail",
        "PRIMARY_CHANNEL_ORACLE_LAUNDERING: some detail",
    ],
)
def test_process_hard_fail_sentinel_warnings_demote_to_non_green(sentinel):
    entry = _entry()
    result = _result(channels={"substrates": _channel()}, warnings=[sentinel])
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("SENTINEL_FAIL" in reason for reason in outcome.reasons)


def test_process_deterministic_convergence_without_h12_support_is_non_green():
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("h12_evidence_ref" in reason for reason in outcome.reasons)


def _write_h12_fixture_files(tmp_path):
    """Retained for API compatibility; no longer used to build valid H12
    payloads (see `_valid_h12_payload` below) now that predictor_source_path
    is hard-pinned to the real `scripts/l22_evidence/h12.py` and the
    fixture/vendored-Karr-source hashes must match REAL on-disk repo files
    -- fake tmp-path files can no longer pass `validate_h12_support`."""
    source_path = tmp_path / "h12_predictor_source.py"
    source_path.write_text("# fake predictor source\n", encoding="utf-8")
    fixture_path = tmp_path / "fixture.mat"
    fixture_path.write_bytes(b"fake fixture bytes")
    import hashlib

    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    return source_path, source_sha, fixture_path, fixture_sha


_H12_REAL_PROCESS = "tRNAAminoacylation"


def _valid_h12_payload(tmp_path=None, *, process: str = _H12_REAL_PROCESS, **overrides) -> dict:
    """Build a fully-valid H12 artifact payload for a REAL catalog process,
    using REAL on-disk hashes (the actual `scripts/l22_evidence/h12.py`,
    the actual process fixture, and the actual vendored Karr source file) --
    `validate_h12_support` now hard-pins `predictor_source_path` to the
    real module and hard-verifies all three referenced file hashes, so a
    synthetic tmp-path fixture can no longer be made to pass. `tmp_path` is
    accepted (but unused) for call-site compatibility.
    """
    from scripts.l22_evidence import h12

    predictor_path_on_disk = REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH
    fixture = h12.load_fixture(process)
    karr_citation = h12.karr_source_citation(process)
    base = dict(
        process=process,
        verdict="H12_CONFIRMED",
        nontrivial_sample_count=7,
        exact_match_rate=1.0,
        trivial_mismatch_count=0,
        branches_confirmed=sorted(h12.REQUIRED_BRANCHES[process]),
        predictor_source_path=h12.EXPECTED_PREDICTOR_SOURCE_PATH,
        predictor_source_sha256_lf_normalized=h12._sha256_lf_normalized(predictor_path_on_disk),
        fixture_path=fixture["__fixture_path__"],
        fixture_sha256=fixture["__fixture_sha256__"],
        karr_source_citation=karr_citation,
    )
    base.update(overrides)
    return base


def test_process_deterministic_convergence_with_valid_h12_support_is_clean(tmp_path):
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(json.dumps(_valid_h12_payload(tmp_path)), encoding="utf-8")
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_PASS
    assert outcome.reasons == []


def test_process_h12_support_rejected_when_nontrivial_sample_count_is_zero(tmp_path):
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(
        json.dumps(_valid_h12_payload(tmp_path, nontrivial_sample_count=0)), encoding="utf-8"
    )
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL


def test_process_h12_support_rejected_when_verdict_is_not_confirmed(tmp_path):
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(json.dumps(_valid_h12_payload(tmp_path, verdict="H12_FAIL")), encoding="utf-8")
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("H12_CONFIRMED" in reason for reason in outcome.reasons)


def test_process_h12_observed_regime_never_clears_gate(tmp_path):
    """H12_OBSERVED_REGIME is honest, non-laundered evidence (100% exact
    match on every sample the predictor COULD evaluate) but explicitly must
    never be accepted as sentinel-clearing support -- only H12_CONFIRMED
    (full required branch coverage) may clear
    PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE."""
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(
        json.dumps(_valid_h12_payload(tmp_path, verdict="H12_OBSERVED_REGIME")), encoding="utf-8"
    )
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("H12_CONFIRMED" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_match_rate_not_exactly_one(tmp_path):
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(json.dumps(_valid_h12_payload(tmp_path, exact_match_rate=0.99)), encoding="utf-8")
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("exact_match_rate" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_trivial_mismatch_count_nonzero(tmp_path):
    """ANY trivial (predicted-no-op) mismatch is a harder failure than a
    nontrivial miss and must hard-fail the gate regardless of a perfect
    nontrivial exact_match_rate."""
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(json.dumps(_valid_h12_payload(tmp_path, trivial_mismatch_count=1)), encoding="utf-8")
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("trivial_mismatch_count" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_required_branch_coverage_incomplete(tmp_path):
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(
        json.dumps(_valid_h12_payload(tmp_path, branches_confirmed=[])), encoding="utf-8"
    )
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("required branch coverage" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_predictor_source_path_is_wrong(tmp_path):
    """A dangling/substituted predictor_source_path must hard-fail, never
    fall back to hash-only trust of an arbitrary file."""
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(
        json.dumps(_valid_h12_payload(tmp_path, predictor_source_path="scripts/l22_evidence/h12_fake.py")),
        encoding="utf-8",
    )
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("pinned path" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_predictor_source_is_stale(tmp_path):
    """If h12.py (the predictor source) is edited after the artifact was
    generated, the recorded predictor_source_sha256_lf_normalized no longer
    matches the current on-disk file -- the artifact must be treated as
    stale, not trusted. Simulated via a deliberately-wrong recorded hash
    (the real production h12.py is never mutated by this test).
    """
    h12_path = tmp_path / "h12_evidence.json"
    payload = _valid_h12_payload(
        tmp_path, predictor_source_sha256_lf_normalized="0" * 64
    )
    h12_path.write_text(json.dumps(payload), encoding="utf-8")

    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("STALE" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_fixture_is_stale(tmp_path):
    """Simulated via a deliberately-wrong recorded fixture hash (the real
    production fixture .mat file is never mutated by this test)."""
    h12_path = tmp_path / "h12_evidence.json"
    payload = _valid_h12_payload(tmp_path, fixture_sha256="0" * 64)
    h12_path.write_text(json.dumps(payload), encoding="utf-8")

    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("STALE" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_karr_source_citation_is_stale(tmp_path):
    """Simulated via a deliberately-wrong recorded vendored-Karr-source
    hash (the real vendored .m file is never mutated by this test)."""
    h12_path = tmp_path / "h12_evidence.json"
    payload = _valid_h12_payload(tmp_path)
    payload["karr_source_citation"]["vendored_sha256_lf_normalized"] = "0" * 64
    h12_path.write_text(json.dumps(payload), encoding="utf-8")

    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("STALE" in reason for reason in outcome.reasons)


def test_process_h12_support_rejected_when_fixture_missing_from_disk(tmp_path):
    """A referenced fixture (a git-tracked file) that does not exist on
    disk at all -- e.g. a substituted/dangling path -- is a hard fail, NOT
    a soft-trust-the-recorded-hash attestation. Fixtures are tracked files;
    per the anti-tamper mandate there is no soft trust for any tracked
    file this artifact references."""
    h12_path = tmp_path / "h12_evidence.json"
    payload = _valid_h12_payload(
        tmp_path,
        fixture_path="data/karr_fixtures/per_process/DoesNotExist_flat.mat",
        fixture_sha256="0" * 64,
    )
    h12_path.write_text(json.dumps(payload), encoding="utf-8")

    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("does not exist on disk" in reason for reason in outcome.reasons)


def test_process_deferred_is_always_non_green_even_with_decision_and_evidence(tmp_path):
    alt_path = tmp_path / "alternate_evidence.json"
    alt_path.write_text(json.dumps({"note": "alternate"}), encoding="utf-8")
    entry = _entry()
    result = _result(
        channels={"substrates": _channel()},
        decision_ref="decisions/2026-07-28-defer-fakeprocess.yaml",
        alternate_evidence_ref=str(alt_path),
    )
    result["verdict"] = "DEFERRED"
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any(reason.startswith(schema.STATUS_DEFERRED) for reason in outcome.reasons)
    assert any("never GREEN" in reason for reason in outcome.reasons)


def test_process_deferred_without_decision_or_evidence_names_both_gaps():
    entry = _entry()
    result = _result(channels={"substrates": _channel()})
    result["verdict"] = "DEFERRED"
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert any("missing decision_ref" in reason for reason in outcome.reasons)
    assert any("missing or unresolved alternate_evidence_ref" in reason for reason in outcome.reasons)


def test_process_no_gateable_channels_when_all_deferred_or_insufficient():
    entry = _entry()
    result = _result(
        channels={
            "chromosome": _channel(is_event_channel=True),
            "secondary": _channel(n_nonzero_oc=1, n_nonzero_karr=1, is_primary=False),
        }
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_NO_GATEABLE_CHANNELS


def test_process_name_mismatch_is_flagged():
    entry = _entry()
    result = _result(channels={"substrates": _channel()})
    result["process"] = "SomeOtherProcess"
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("PROCESS_NAME_MISMATCH" in reason for reason in outcome.reasons)


def test_process_missing_primary_channel_marker_is_schema_invalid():
    entry = _entry()
    result = _result(channels={"substrates": _channel(is_primary=False)})
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any("no channel in result.json marked is_primary" in reason for reason in outcome.reasons)


# --- F3: catalog primary_channel must map to exactly one is_primary=true channel


def test_process_primary_channel_name_mismatch_is_vacuous_substitution():
    """A DIFFERENT channel marked is_primary=true while the catalog's real
    `primary_channel` ("substrates") is present but not primary must be
    treated as a vacuous substitution, not silently accepted as "some
    channel is primary, close enough"."""
    entry = _entry()  # primary_channel="substrates"
    result = _result(
        channels={
            "substrates": _channel(is_primary=False),
            "decoy": _channel(is_primary=True),
        }
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any(
        schema.STATUS_PRIMARY_VACUOUS in reason and "decoy" in reason and "substrates" in reason
        for reason in outcome.reasons
    ), outcome.reasons


def test_process_multiple_channels_marked_is_primary_is_non_green():
    """Two channels both marked is_primary=true is ambiguous -- which one is
    actually authoritative? -- and must be non-green, not silently resolved
    by picking whichever the aggregation loop happens to see first."""
    entry = _entry()
    result = _result(
        channels={
            "substrates": _channel(is_primary=True),
            "other": _channel(is_primary=True),
        }
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any(
        schema.STATUS_PRIMARY_VACUOUS in reason and "2 channels" in reason for reason in outcome.reasons
    ), outcome.reasons


def test_process_primary_channel_matching_catalog_name_exactly_once_is_clean():
    """The correct, non-vacuous case: exactly one channel is_primary=true
    AND its name matches the catalog's declared primary_channel -- no new
    F3 reason should ever fire here."""
    entry = _entry()  # primary_channel="substrates"
    result = _result(
        channels={
            "substrates": _channel(is_primary=True),
            "other": _channel(is_primary=False),
        }
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_PASS
    assert outcome.reasons == []


def test_process_primary_channel_name_alias_is_clean_not_vacuous():
    """P0 fix: the runner normalizes a handful of catalog channel-name
    aliases (e.g. `"rnas"` -> `"RNAs"`) before ever writing result.json, so
    the catalog's raw `primary_channel="rnas"` legitimately shows up as
    result.json key `"RNAs"` with is_primary=true. This is NOT a vacuous
    substitution and must not demote an otherwise-healthy process."""
    entry = _entry(primary_channel="rnas", output_channels=("rnas",))
    result = _result(
        channels={
            "RNAs": _channel(is_primary=True),
        }
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_PASS
    assert outcome.reasons == []


def test_process_primary_channel_mrnas_alias_is_clean_not_vacuous():
    """Same alias-normalization guarantee for the other registered alias
    (`"mrnas"` -> `"mRNAs"`)."""
    entry = _entry(primary_channel="mrnas", output_channels=("mrnas",))
    result = _result(
        channels={
            "mRNAs": _channel(is_primary=True),
        }
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_PASS
    assert outcome.reasons == []


def test_process_primary_channel_genuine_mismatch_still_non_green_after_alias_fix():
    """A genuine (non-alias) name mismatch must still be caught -- the
    alias-normalization fix must not accidentally widen the comparison
    into a fuzzy match."""
    entry = _entry(primary_channel="rnas", output_channels=("rnas", "decoy"))
    result = _result(
        channels={
            "decoy": _channel(is_primary=True),
        }
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any(schema.STATUS_PRIMARY_VACUOUS in reason for reason in outcome.reasons), outcome.reasons


def test_process_empty_catalog_primary_channel_is_non_green_even_with_one_is_primary():
    """F5 hardening: the pre-existing `elif entry.primary_channel and ...`
    guard silently SKIPPED the name-match check whenever the catalog's own
    `primary_channel` field was itself empty/None, meaning ANY single
    is_primary=true channel would pass unchallenged -- exactly the
    vacuous-substitution risk this block exists to prevent, just triggered
    by a missing catalog declaration rather than a name mismatch. An
    empty/None `primary_channel` with channels present must now be
    explicitly non-green, never silently treated as "nothing to check
    against"."""
    entry = _entry(primary_channel="")
    result = _result(channels={"substrates": _channel(is_primary=True)})
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL
    assert any(
        schema.STATUS_PRIMARY_VACUOUS in reason and "empty/missing" in reason for reason in outcome.reasons
    ), outcome.reasons


def test_every_real_in_scope_catalog_entry_has_nonempty_primary_channel():
    """Catalog-level sanity check against the REAL (non-synthetic)
    PROCESS_CATALOG.yaml: every in-scope process must declare a non-empty
    `primary_channel` -- if this ever regressed to empty/None for a real
    process, `test_process_empty_catalog_primary_channel_is_non_green_
    even_with_one_is_primary` above proves that row would (correctly) go
    non-green, but this test catches the catalog regression directly,
    at the source, rather than only downstream via a verdict test."""
    from scripts.l22_evidence import catalog as cat

    for name, entry in cat.in_scope_processes().items():
        assert entry.primary_channel, f"{name}: catalog primary_channel is empty/missing"
