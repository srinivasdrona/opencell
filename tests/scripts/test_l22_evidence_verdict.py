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


def test_channel_missing_evaluator_for_projection_aggregation():
    payload = _channel(aggregation="per_component_scaled")
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=True)
    assert verdict == schema.STATUS_MISSING_EVALUATOR
    assert any("per_component_scaled" in reason for reason in reasons)


def test_channel_missing_evaluator_for_hurdle_aggregation():
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


def test_channel_insufficient_samples_below_min_nonzero():
    payload = _channel(n_nonzero_oc=5, n_nonzero_karr=5, is_primary=False)
    verdict, reasons = vd.rederive_channel("secondary", payload, is_primary=False)
    assert verdict == "INSUFFICIENT_SAMPLES"


def test_channel_event_channel_is_deferred_regardless_of_metrics():
    payload = _channel(is_event_channel=True, w1_oc_vs_karr=999.0)
    verdict, reasons = vd.rederive_channel("chromosome", payload, is_primary=False)
    assert verdict == "EVENT_CHANNEL_DEFERRED"
    assert reasons == []


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


def test_process_deterministic_convergence_with_valid_h12_support_is_clean(tmp_path):
    h12_path = tmp_path / "h12_evidence.json"
    h12_path.write_text(json.dumps({"nontrivial_sample_count": 7}), encoding="utf-8")
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
    h12_path.write_text(json.dumps({"nontrivial_sample_count": 0}), encoding="utf-8")
    entry = _entry(closed_form_dominant="confirmed_biology_validated")
    result = _result(
        channels={"substrates": _channel()},
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched Karr exactly"],
        h12_evidence_ref=str(h12_path),
    )
    outcome = vd.rederive_process("FakeProcess", entry, result)
    assert outcome.mechanical_verdict == schema.STATUS_FAIL


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
