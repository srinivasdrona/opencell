"""Unit tests for `scripts/l2_event/division_window_spec.py` -- the single
machine-loadable source of truth for Cytokinesis/FtsZPolymerization
division-window M_ticks values introduced by the 2026-09-04 Cytokinesis
window preregistration fix.

These tests exercise the loader in isolation (missing file, malformed
JSON, missing process entry, agreement with the real repo spec) --
end-to-end agreement with the MATLAB extractor/driver and
PROCESS_CATALOG.yaml is covered by
tests/scripts/test_extract_dual_division_window_static.py's
test_catalog_and_spec_agree_on_cytokinesis_m_ticks, and agreement with the
Python cohort-prep/validator modules is covered by
tests/scripts/test_validate_dual_division_canary.py's
test_prepare_cytokinesis_cohort_and_canary_validator_agree_with_the_shared_spec.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.division_window_spec import (  # noqa: E402
    CYTOKINESIS_M_TICKS,
    FTSZ_M_TICKS,
    SPEC_PATH,
    DivisionWindowSpecError,
    ProvisionalMarginOverrunError,
    SelectionContractError,
    attempt_record_filename,
    attempt_status_values,
    candidate_seed_start,
    check_inclusive_span_margin,
    load_spec,
    m_ticks_for,
    process_spec,
    required_completed_windows,
    selection_contract,
    selection_contract_applies_to,
    selection_horizon_max_search_ticks,
    selection_order,
    tick_range_from_division_for,
)


def test_real_repo_spec_file_has_the_preregistered_2026_09_04_values():
    """Locks in the actual preregistered values this task's evidence
    justifies -- a regression here means someone changed the number
    without going through a fresh preregistration commit."""
    assert m_ticks_for("Cytokinesis") == 5000
    assert tick_range_from_division_for("Cytokinesis") == (-4999, 0)
    assert m_ticks_for("FtsZPolymerization") == 200
    assert tick_range_from_division_for("FtsZPolymerization") == (-200, 0)


def test_module_constants_match_the_loader_functions():
    assert m_ticks_for("Cytokinesis") == CYTOKINESIS_M_TICKS
    assert m_ticks_for("FtsZPolymerization") == FTSZ_M_TICKS


def test_real_spec_file_exists_at_the_documented_path():
    assert SPEC_PATH.exists()
    assert SPEC_PATH == REPO_ROOT / "docs" / "phase_f" / "l2_event" / "division_window_spec.json"


def test_evidence_block_records_the_margin_over_the_real_overrun():
    doc = load_spec()
    evidence = doc["processes"]["Cytokinesis"]["evidence"]
    assert evidence["max_observed_span_ticks"] == 4076
    assert evidence["max_observed_span_seed"] == 36
    m_ticks = doc["processes"]["Cytokinesis"]["m_ticks"]
    assert m_ticks - evidence["max_observed_span_ticks"] == evidence["margin_ticks"]
    assert evidence["margin_ticks"] > 0, "the preregistered M_ticks must exceed the max observed span"


def test_supersedes_block_records_the_prior_non_authoritative_value():
    doc = load_spec()
    supersedes = doc["processes"]["Cytokinesis"]["supersedes"]
    assert supersedes["m_ticks"] == 4000
    assert supersedes["tick_range_from_division"] == [-3999, 0]


def test_missing_spec_file_raises_never_silently_defaults(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"
    with pytest.raises(DivisionWindowSpecError):
        load_spec(missing_path)
    with pytest.raises(DivisionWindowSpecError):
        m_ticks_for("Cytokinesis", spec_path=missing_path)


def test_malformed_json_raises_never_silently_defaults(tmp_path):
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(DivisionWindowSpecError):
        load_spec(bad_path)


def test_spec_missing_processes_key_raises(tmp_path):
    bad_path = tmp_path / "no_processes.json"
    bad_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    with pytest.raises(DivisionWindowSpecError):
        load_spec(bad_path)


def test_unknown_process_raises_never_falls_back_to_a_guessed_value(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({"processes": {"Cytokinesis": {"m_ticks": 5000, "tick_range_from_division": [-4999, 0]}}}),
        encoding="utf-8",
    )
    with pytest.raises(DivisionWindowSpecError):
        process_spec("FtsZPolymerization", spec_path=spec_path)
    with pytest.raises(DivisionWindowSpecError):
        m_ticks_for("SomeOtherProcess", spec_path=spec_path)


def test_process_entry_missing_m_ticks_key_raises(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({"processes": {"Cytokinesis": {"tick_range_from_division": [-4999, 0]}}}),
        encoding="utf-8",
    )
    with pytest.raises(DivisionWindowSpecError):
        m_ticks_for("Cytokinesis", spec_path=spec_path)


def test_process_entry_missing_tick_range_key_raises(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({"processes": {"Cytokinesis": {"m_ticks": 5000}}}),
        encoding="utf-8",
    )
    with pytest.raises(DivisionWindowSpecError):
        tick_range_from_division_for("Cytokinesis", spec_path=spec_path)


def test_custom_spec_path_is_isolated_from_the_real_repo_spec(tmp_path):
    """A caller-supplied spec_path must be read fresh, never fall back to
    (or leak into) the real repo spec file / cached module constants."""
    custom_path = tmp_path / "custom_spec.json"
    custom_path.write_text(
        json.dumps({"processes": {"Cytokinesis": {"m_ticks": 6000, "tick_range_from_division": [-5999, 0]}}}),
        encoding="utf-8",
    )
    assert m_ticks_for("Cytokinesis", spec_path=custom_path) == 6000
    # Module-level constant, read once at import time from the real repo
    # spec, must be unaffected by a later call using a different spec_path.
    assert CYTOKINESIS_M_TICKS == 5000


# ---------------------------------------------------------------------------
# Provisional-margin gate (Opus final review, 2026-09-04): boundary tests.
# `check_inclusive_span_margin(onset_tick, completion_tick, m_ticks)` must
# accept a span that leaves exactly 1 tick of margin (inclusive_span ==
# m_ticks - 1), and reject both an exactly-zero-margin span
# (inclusive_span == m_ticks) and a genuine overrun (inclusive_span ==
# m_ticks + 1). This is a stricter, additional application-level gate on
# top of (never a replacement for) the MATLAB extractor's own capture
# invariant, which is left unchanged.
# ---------------------------------------------------------------------------


def test_margin_gate_accepts_span_one_tick_below_m_ticks(): # M-1 margin
    """inclusive_span = m_ticks - 1 leaves exactly 1 tick of margin --
    must be accepted (never rejected for merely being close to the
    boundary)."""
    m_ticks = 5000
    completion_tick = 31993
    onset_tick = completion_tick - (m_ticks - 1) + 1  # inclusive_span == m_ticks - 1
    inclusive_span = completion_tick - onset_tick + 1
    assert inclusive_span == m_ticks - 1
    check_inclusive_span_margin(onset_tick, completion_tick, m_ticks)  # must not raise


def test_margin_gate_rejects_span_exactly_equal_to_m_ticks():
    """inclusive_span == m_ticks (zero margin) must be REJECTED even
    though the MATLAB extractor's own capture invariant would have
    allowed it -- this is the whole point of the provisional-margin gate:
    a zero-margin observation is itself evidence the PROVISIONAL m_ticks
    was not generous enough, and must trigger the escalation policy just
    like a true overrun."""
    m_ticks = 5000
    completion_tick = 31993
    onset_tick = completion_tick - m_ticks + 1  # inclusive_span == m_ticks exactly
    inclusive_span = completion_tick - onset_tick + 1
    assert inclusive_span == m_ticks
    with pytest.raises(ProvisionalMarginOverrunError):
        check_inclusive_span_margin(onset_tick, completion_tick, m_ticks)


def test_margin_gate_rejects_span_one_tick_above_m_ticks(): # M+1 overrun
    """inclusive_span == m_ticks + 1 is a genuine overrun -- must be
    rejected (this case would ALSO fail the MATLAB extractor's own
    capture invariant and never produce a file at all, but this test
    exercises the Python-side gate directly and independently)."""
    m_ticks = 5000
    completion_tick = 31993
    onset_tick = completion_tick - (m_ticks + 1) + 1  # inclusive_span == m_ticks + 1
    inclusive_span = completion_tick - onset_tick + 1
    assert inclusive_span == m_ticks + 1
    with pytest.raises(ProvisionalMarginOverrunError):
        check_inclusive_span_margin(onset_tick, completion_tick, m_ticks)


def test_margin_gate_error_message_reports_the_escalation_formula():
    with pytest.raises(ProvisionalMarginOverrunError, match=r"1\.227"):
        check_inclusive_span_margin(onset_tick=1, completion_tick=5000, m_ticks=5000)


# ---------------------------------------------------------------------------
# Selection contract (division-censor-contract, 2026-09-08 preregistration):
# candidate_seed_start / required_completed_windows / max_search_ticks /
# selection_order / attempt_record_filename. Fail-closed, no defaults --
# mirrors the per-process m_ticks accessors' discipline exactly.
# ---------------------------------------------------------------------------


def test_real_repo_spec_has_the_preregistered_selection_contract_values():
    assert candidate_seed_start() == 0
    assert required_completed_windows() == 50
    assert selection_horizon_max_search_ticks() == 100000
    assert selection_order() == "ascending_seed"
    assert attempt_record_filename() == "division_window_attempt.json"
    assert set(attempt_status_values()) == {"COMPLETED", "RIGHT_CENSORED"}


def test_selection_contract_applies_to_both_dual_tap_processes():
    assert selection_contract_applies_to("Cytokinesis")
    assert selection_contract_applies_to("FtsZPolymerization")
    assert not selection_contract_applies_to("SomeUnrelatedProcess")


def test_selection_contract_schema_version_bumped_to_3():
    doc = load_spec()
    assert doc["schema_version"] == 3


def test_missing_selection_contract_block_raises(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({"processes": {"Cytokinesis": {"m_ticks": 5000, "tick_range_from_division": [-4999, 0]}}}),
        encoding="utf-8",
    )
    with pytest.raises(SelectionContractError):
        selection_contract(spec_path=spec_path)
    with pytest.raises(SelectionContractError):
        candidate_seed_start(spec_path=spec_path)


def test_selection_contract_missing_required_key_raises(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "processes": {"Cytokinesis": {"m_ticks": 5000, "tick_range_from_division": [-4999, 0]}},
                "selection_contract": {
                    "applies_to": ["Cytokinesis"],
                    "candidate_seed_start": 0,
                    # required_completed_windows deliberately omitted
                    "max_search_ticks": 100000,
                    "selection_order": "ascending_seed",
                    "attempt_record_filename": "division_window_attempt.json",
                    "attempt_status_values": ["COMPLETED", "RIGHT_CENSORED"],
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SelectionContractError):
        required_completed_windows(spec_path=spec_path)


def test_selection_contract_not_a_dict_raises(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "processes": {"Cytokinesis": {"m_ticks": 5000, "tick_range_from_division": [-4999, 0]}},
                "selection_contract": "not-a-dict",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SelectionContractError):
        selection_contract(spec_path=spec_path)


def test_selection_contract_is_isolated_from_a_custom_spec_path(tmp_path):
    custom_path = tmp_path / "custom_spec.json"
    custom_path.write_text(
        json.dumps(
            {
                "processes": {"Cytokinesis": {"m_ticks": 6000, "tick_range_from_division": [-5999, 0]}},
                "selection_contract": {
                    "applies_to": ["Cytokinesis"],
                    "candidate_seed_start": 3,
                    "required_completed_windows": 10,
                    "max_search_ticks": 200000,
                    "selection_order": "ascending_seed",
                    "attempt_record_filename": "attempt.json",
                    "attempt_status_values": ["COMPLETED", "RIGHT_CENSORED"],
                },
            }
        ),
        encoding="utf-8",
    )
    assert candidate_seed_start(spec_path=custom_path) == 3
    assert required_completed_windows(spec_path=custom_path) == 10
    assert selection_horizon_max_search_ticks(spec_path=custom_path) == 200000
    # The real repo spec's values must be unaffected.
    assert candidate_seed_start() == 0
    assert required_completed_windows() == 50
    assert selection_horizon_max_search_ticks() == 100000
