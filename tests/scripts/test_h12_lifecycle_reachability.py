"""Tests for scripts/l22_evidence/h12_lifecycle_reachability.py -- the
NON-GATING full-natural-cycle reachability probe evidence module for
MacromolecularComplexation/network_ge2_fires.

Two independent test surfaces:

  - **Synthetic-fixture tests** (`_write_raw`, `synthetic_artifact`): build
    tiny, fully self-contained CSV/summary pairs under `tmp_path` and
    exercise `build_lifecycle_reachability_artifact`/
    `validate_lifecycle_reachability_artifact` directly against them.
    These never touch the real, long-running MATLAB probe output and
    cover the anti-cheat tamper battery (classification/gating
    escalation, stop-reason/tick consistency, E1-vs-network2
    stoichiometric impossibility, hash staleness, CSV-vs-summary
    mismatch, single-seed scope disclosure).
  - **Committed-artifact tests** (`artifact` fixture): once the real probe
    completes and `python scripts/l22_evidence/h12_lifecycle_reachability.py
    generate` has been run, these assert the tracked artifact
    (docs/phase_f/l2_2_design_a/h12/lifecycle_reachability/
    MacromolecularComplexation_h12_lifecycle_reachability.json) exists,
    validates, and is internally consistent with the raw probe output
    committed alongside it.

Run via `bin/oc-pytest tests/scripts/test_h12_lifecycle_reachability.py -v`.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12_lifecycle_reachability as hlr  # noqa: E402

VERDICT_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "verdict.py"
GENERATOR_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "generator.py"
EVIDENCE_INDEX_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "h12_evidence_index.json"
PROCESS_CATALOG_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
CONDITION_GATED_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "condition_gated"
    / "MacromolecularComplexation_h12_condition_gated.json"
)


def _mutate(payload: dict, **overrides) -> dict:
    out = copy.deepcopy(payload)
    for path, value in overrides.items():
        keys = path.split(".")
        node = out
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return out


def _write_raw(tmp_path: Path, rows: list, summary_overrides: dict = None):
    """Write a synthetic raw CSV + summary JSON pair under tmp_path and
    return (csv_path, summary_path). `rows` is a list of
    (tick, e1_value, complex1_delta, complex2_delta, pinched) -- per-complex,
    not summed, matching the corrected (post-review) schema. The
    any_complex_changed column is computed as a cancellation-safe OR
    (nonzero c1_delta OR nonzero c2_delta), never as a signed sum -- see
    _recompute_from_csv's docstring for why a signed-sum gate can silently
    drop a real event when two complexes change by opposite amounts in
    the same tick."""
    csv_path = tmp_path / "MacromolecularComplexation_e1_lifecycle_seed000.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(
            "tick,e1_monomer_count_direct_state_read,"
            "complex1_delta_MG_041_062_429_PENTAMER,complex2_delta_MG_041_069_429_PENTAMER,"
            "any_complex_delta_total,any_complex_changed,pinched\n"
        )
        for tick, e1_value, c1_delta, c2_delta, pinched in rows:
            any_delta = c1_delta + c2_delta
            any_changed = 1 if (c1_delta != 0 or c2_delta != 0) else 0
            fh.write(
                f"{tick},{e1_value},{c1_delta},{c2_delta},{any_delta},{any_changed},"
                f"{1 if pinched else 0}\n"
            )

    recomputed = hlr._recompute_from_csv(csv_path)
    n_ticks_ran = recomputed["last_logged_tick"] if recomputed["pinched_at_tick"] < 0 else recomputed["pinched_at_tick"]
    summary = {
        "process": "MacromolecularComplexation",
        "seed": 0,
        "n_ticks_ran": n_ticks_ran,
        "e1_local_substrate_index_1based": 193,
        "net2_complex_indices_1based": [23, 24],
        "max_e1_value": recomputed["max_e1_value"],
        "first_e1_nonzero_tick": recomputed["first_e1_nonzero_tick"],
        "n_any_complex_events": recomputed["n_any_complex_events"],
        "n_net2_events_by_complex": recomputed["n_net2_events_by_complex"],
        "first_net2_event_tick_by_complex": recomputed["first_net2_event_tick_by_complex"],
        "max_net2_delta_by_complex": recomputed["max_net2_delta_by_complex"],
        "natural_cycle_stop_tick": n_ticks_ran,
        "timestamp": "2026-08-05 00:00:00",
    }
    if summary_overrides:
        summary.update(summary_overrides)
    summary_path = tmp_path / "MacromolecularComplexation_e1_lifecycle_seed000_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return csv_path, summary_path


# ---------------------------------------------------------------------------
# Synthetic build/validate round trips
# ---------------------------------------------------------------------------


def test_build_from_synthetic_e1_never_leaves_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 150)] + [(150, 0, 0, 0, True)]
    csv_path, summary_path = _write_raw(tmp_path, rows)
    artifact = hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)
    assert artifact["outcome"] == "e1_remained_zero_throughout_scanned_window"
    assert artifact["e1_ever_nonzero"] is False
    assert artifact["network2_ever_fired_naturally"] is False
    assert artifact["probe"]["stop_reason"] == hlr.STOP_REASON_NATURAL_PINCH
    assert artifact["seed_count"] == 1
    assert hlr.validate_lifecycle_reachability_artifact(artifact) is None


def test_build_from_synthetic_e1_becomes_nonzero_but_no_network2(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 100)] + [(t, 5, 0, 0, False) for t in range(100, 150)] + [
        (150, 5, 0, 0, True)
    ]
    csv_path, summary_path = _write_raw(tmp_path, rows)
    artifact = hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)
    assert artifact["outcome"] == "e1_became_nonzero_but_network2_did_not_fire"
    assert artifact["e1_ever_nonzero"] is True
    assert artifact["network2_ever_fired_naturally"] is False
    assert hlr.validate_lifecycle_reachability_artifact(artifact) is None


def test_recompute_uses_any_complex_changed_not_cancelling_sum(tmp_path):
    """Regression test for the discovered any_complex_delta_total
    cancellation bug: a tick where complex1 gains +1 and complex2 loses -1
    sums to a signed total of 0, but any_complex_changed correctly records
    that something DID change. n_any_complex_events must be derived from
    the cancellation-safe column, not from re-deriving "sum != 0" itself
    (which would silently miss this tick, exactly as the pre-fix MATLAB
    probe's CSV-write gate once did)."""
    csv_path = tmp_path / "MacromolecularComplexation_e1_lifecycle_seed000.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(
            "tick,e1_monomer_count_direct_state_read,"
            "complex1_delta_MG_041_062_429_PENTAMER,complex2_delta_MG_041_069_429_PENTAMER,"
            "any_complex_delta_total,any_complex_changed,pinched\n"
        )
        # tick 100: +1/-1 cancel to a signed sum of 0, but DID change.
        fh.write("100,5,1,-1,0,1,0\n")
        fh.write("101,5,0,0,0,0,1\n")
    recomputed = hlr._recompute_from_csv(csv_path)
    assert recomputed["n_any_complex_events"] == 1
    assert recomputed["n_net2_events_by_complex"] == [1, 1]
    assert recomputed["n_net2_formation_events_by_complex"] == [1, 0]


def test_build_from_synthetic_network2_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 100)] + [(100, 5, 1, 1, False)] + [
        (t, 5, 0, 0, False) for t in range(101, 150)
    ] + [(150, 5, 0, 0, True)]
    csv_path, summary_path = _write_raw(tmp_path, rows)
    artifact = hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)
    assert artifact["outcome"] == "network2_fired_naturally"
    assert artifact["e1_ever_nonzero"] is True
    assert artifact["network2_ever_fired_naturally"] is True
    assert artifact["network2_competition_status"] == "both_complexes_fired"
    assert artifact["probe"]["n_net2_formation_events_by_complex"] == [1, 1]
    assert hlr.validate_lifecycle_reachability_artifact(artifact) is None


def test_build_from_synthetic_degradation_only_does_not_count_as_fired(tmp_path, monkeypatch):
    """A complex that is already nonzero at cell birth (per
    MacromolecularComplexation.m's own Initialization semantics) can show a
    real, later DEGRADATION event (delta < 0) with no formation event ever
    observed. That must NOT be counted as "fired" -- only complex2's genuine
    formation event should drive network2_ever_fired_naturally/outcome, and
    competition_status must reflect single-complex, not both-complex,
    evidence."""
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = (
        [(t, 0, 0, 0, False) for t in range(1, 100)]
        # complex1: pure degradation, no preceding formation ever observed
        # in this window (simulates a birth-nonzero complex turning over).
        + [(100, 5, -1, 0, False)]
        # complex2: a genuine formation event.
        + [(110, 5, 0, 1, False)]
        + [(t, 5, 0, 0, False) for t in range(111, 150)]
        + [(150, 5, 0, 0, True)]
    )
    csv_path, summary_path = _write_raw(tmp_path, rows)
    artifact = hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)
    probe = artifact["probe"]
    # Sign-agnostic counts see both complexes as "changed".
    assert probe["n_net2_events_by_complex"] == [1, 1]
    # Formation-only counts correctly attribute the fire to complex2 only.
    assert probe["n_net2_formation_events_by_complex"] == [0, 1]
    assert artifact["outcome"] == "network2_fired_naturally"
    assert artifact["network2_ever_fired_naturally"] is True
    assert artifact["network2_competition_status"] == "single_complex_only_fired"
    assert hlr.validate_lifecycle_reachability_artifact(artifact) is None


def test_build_from_synthetic_max_ticks_reached_without_division(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 201)]
    csv_path, summary_path = _write_raw(tmp_path, rows)
    artifact = hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)
    assert artifact["probe"]["stop_reason"] == hlr.STOP_REASON_MAX_TICKS
    assert artifact["probe"]["n_ticks_ran"] == 200
    assert hlr.validate_lifecycle_reachability_artifact(artifact) is None


def test_build_rejects_incomplete_unexplained_run(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 50)]
    csv_path, summary_path = _write_raw(tmp_path, rows, summary_overrides={"n_ticks_ran": 49})
    with pytest.raises(ValueError, match="unrecognized reason"):
        hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)


def test_build_rejects_summary_max_e1_value_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 200)] + [(200, 0, 0, 0, True)]
    csv_path, summary_path = _write_raw(tmp_path, rows, summary_overrides={"max_e1_value": 999})
    with pytest.raises(ValueError, match="max_e1_value"):
        hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)


def test_build_rejects_summary_n_net2_events_by_complex_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 200)] + [(200, 0, 0, 0, True)]
    csv_path, summary_path = _write_raw(tmp_path, rows, summary_overrides={"n_net2_events_by_complex": [5, 0]})
    with pytest.raises(ValueError, match="n_net2_events_by_complex"):
        hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)


def test_build_rejects_structurally_impossible_network2_without_e1(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    # Self-inconsistent raw data: a net2 complex delta is logged at tick 150
    # while e1_monomer_count_direct_state_read is 0 at every tick, including
    # tick 150 -- this cannot come from a real run (network 2 needs E1 > 0
    # by stoichiometry), so
    # the summary is built to match the (also self-inconsistent) CSV
    # recomputation and the structural check must catch it downstream.
    rows = [(t, 0, 0, 0, False) for t in range(1, 150)] + [(150, 0, 1, 1, True)]
    csv_path, summary_path = _write_raw(tmp_path, rows)
    with pytest.raises(ValueError, match="structurally impossible"):
        hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)


def _write_raw_no_summary(tmp_path: Path, rows: list, e1_idx: int = 193, net2_idx: tuple = (23, 24)):
    """Write a synthetic raw CSV + stdout log pair (NO summary.json) under
    tmp_path, simulating an operator-stopped run where the MATLAB loop was
    killed before it could break out and write its own summary. `rows` is
    a list of (tick, e1_value, complex1_delta, complex2_delta, pinched) --
    per-complex, not summed. Returns (csv_path, log_path)."""
    csv_path = tmp_path / "MacromolecularComplexation_e1_lifecycle_seed000.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(
            "tick,e1_monomer_count_direct_state_read,"
            "complex1_delta_MG_041_062_429_PENTAMER,complex2_delta_MG_041_069_429_PENTAMER,"
            "any_complex_delta_total,any_complex_changed,pinched\n"
        )
        for tick, e1_value, c1_delta, c2_delta, pinched in rows:
            any_delta = c1_delta + c2_delta
            any_changed = 1 if (c1_delta != 0 or c2_delta != 0) else 0
            fh.write(
                f"{tick},{e1_value},{c1_delta},{c2_delta},{any_delta},{any_changed},"
                f"{1 if pinched else 0}\n"
            )

    log_path = tmp_path / "MacromolecularComplexation_e1_lifecycle_seed000_stdout.log"
    log_path.write_text(
        "[macromol-scan] === MacromolecularComplexation (seed=0, up to 33000 ticks, natural cycle, "
        "pinch-stop) ===\n"
        f"[macromol-scan] E1 local substrate index = {e1_idx}; "
        f"network-2 complex indices = [{' '.join(str(i) for i in net2_idx)}]\n"
        "[macromol-scan] tick 21000/33000 (164.4 min) max_e1=2 net2_events=[13 13]\n",
        encoding="utf-8",
    )
    return csv_path, log_path


# ---------------------------------------------------------------------------
# Operator-stopped-early path (no MATLAB-written summary.json exists)
# ---------------------------------------------------------------------------


def test_build_from_operator_stopped_network2_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 33000)
    rows = [(t, 0, 0, 0, False) for t in range(1, 100)] + [(100, 5, 1, 1, False)] + [
        (t, 5, 0, 0, False) for t in range(101, 150)
    ]
    csv_path, log_path = _write_raw_no_summary(tmp_path, rows)
    missing_summary_path = tmp_path / "does_not_exist_summary.json"
    artifact = hlr.build_lifecycle_reachability_artifact(
        csv_path=csv_path, summary_path=missing_summary_path, stdout_log_path=log_path
    )
    assert artifact["outcome"] == "network2_fired_naturally"
    assert artifact["probe"]["stop_reason"] == hlr.STOP_REASON_OPERATOR_STOPPED
    assert artifact["probe"]["n_ticks_ran"] == 149
    assert artifact["probe"]["e1_local_substrate_index_1based"] == 193
    assert artifact["probe"]["net2_complex_indices_1based"] == [23, 24]
    assert artifact["partial_coverage"] is True
    assert artifact["partial_coverage_note"] and "NOT" in artifact["partial_coverage_note"]
    assert artifact["raw_summary_path"] is None
    assert artifact["raw_summary_sha256"] is None
    assert artifact["raw_log_path"] is not None
    assert hlr.validate_lifecycle_reachability_artifact(artifact) is None


def test_build_operator_stopped_rejects_natural_pinch_without_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 33000)
    rows = [(t, 0, 0, 0, False) for t in range(1, 150)] + [(150, 0, 0, 0, True)]
    csv_path, log_path = _write_raw_no_summary(tmp_path, rows)
    missing_summary_path = tmp_path / "does_not_exist_summary.json"
    with pytest.raises(ValueError, match="natural pinch event but no summary"):
        hlr.build_lifecycle_reachability_artifact(
            csv_path=csv_path, summary_path=missing_summary_path, stdout_log_path=log_path
        )


def test_build_operator_stopped_rejects_at_max_ticks_without_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 150)
    rows = [(t, 0, 0, 0, False) for t in range(1, 151)]
    csv_path, log_path = _write_raw_no_summary(tmp_path, rows)
    missing_summary_path = tmp_path / "does_not_exist_summary.json"
    with pytest.raises(ValueError, match="completed max-ticks run"):
        hlr.build_lifecycle_reachability_artifact(
            csv_path=csv_path, summary_path=missing_summary_path, stdout_log_path=log_path
        )


def test_build_operator_stopped_rejects_missing_log(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 33000)
    rows = [(t, 0, 0, 0, False) for t in range(1, 150)]
    csv_path, log_path = _write_raw_no_summary(tmp_path, rows)
    missing_summary_path = tmp_path / "does_not_exist_summary.json"
    missing_log_path = tmp_path / "does_not_exist.log"
    with pytest.raises(FileNotFoundError, match="stdout log"):
        hlr.build_lifecycle_reachability_artifact(
            csv_path=csv_path, summary_path=missing_summary_path, stdout_log_path=missing_log_path
        )


@pytest.fixture
def synthetic_operator_stopped_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 33000)
    rows = [(t, 0, 0, 0, False) for t in range(1, 100)] + [(100, 5, 1, 1, False)] + [
        (t, 5, 0, 0, False) for t in range(101, 150)
    ]
    csv_path, log_path = _write_raw_no_summary(tmp_path, rows)
    missing_summary_path = tmp_path / "does_not_exist_summary.json"
    return hlr.build_lifecycle_reachability_artifact(
        csv_path=csv_path, summary_path=missing_summary_path, stdout_log_path=log_path
    )


def test_rejects_operator_stopped_partial_coverage_flipped_false(synthetic_operator_stopped_artifact):
    payload = _mutate(synthetic_operator_stopped_artifact, partial_coverage=False)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "partial_coverage" in err


def test_rejects_operator_stopped_missing_partial_coverage_note(synthetic_operator_stopped_artifact):
    payload = _mutate(synthetic_operator_stopped_artifact, partial_coverage_note=None)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "partial_coverage_note" in err


def test_rejects_operator_stopped_tampered_log_hash(synthetic_operator_stopped_artifact):
    payload = _mutate(synthetic_operator_stopped_artifact, raw_log_sha256="0" * 64)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "raw_log_sha256" in err


def test_rejects_operator_stopped_stop_reason_at_max_ticks(synthetic_operator_stopped_artifact):
    payload = _mutate(
        synthetic_operator_stopped_artifact,
        **{"probe.n_ticks_ran": synthetic_operator_stopped_artifact["probe"]["n_ticks_max"]},
    )
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "operator-stopped but n_ticks_ran" in err


def test_natural_completion_artifact_never_carries_raw_log(synthetic_artifact):
    assert synthetic_artifact["raw_log_path"] is None
    assert synthetic_artifact["raw_log_sha256"] is None
    assert synthetic_artifact["partial_coverage"] is False
    assert synthetic_artifact["partial_coverage_note"] is None


# ---------------------------------------------------------------------------
# Tamper battery against validate_lifecycle_reachability_artifact
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 150)] + [(150, 0, 0, 0, True)]
    csv_path, summary_path = _write_raw(tmp_path, rows)
    return hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)


@pytest.mark.parametrize(
    "bad_classification",
    ["PASS", "H12_CONFIRMED", "H12_OBSERVED_REGIME", "CONDITION_GATED", "CONDITION_GATED_CANDIDATE"],
)
def test_rejects_classification_escalation(synthetic_artifact, bad_classification):
    payload = _mutate(synthetic_artifact, classification=bad_classification)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "classification" in err


def test_rejects_gating_relabeled(synthetic_artifact):
    payload = _mutate(synthetic_artifact, gating="GATING -- blocks the row")
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "NON_GATING" in err


def test_rejects_missing_consumer_entry(synthetic_artifact):
    payload = _mutate(synthetic_artifact, not_consumed_by=hlr.EXPECTED_NOT_CONSUMED_BY[:-1])
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "not_consumed_by" in err


def test_rejects_unblocks_current_row_flipped_true(synthetic_artifact):
    payload = _mutate(synthetic_artifact, unblocks_current_row=True)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "unblocks_current_row" in err


def test_rejects_unblocks_l2_5_flipped_true(synthetic_artifact):
    payload = _mutate(synthetic_artifact, unblocks_l2_5=True)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "unblocks_l2_5" in err


def test_rejects_maintainer_decision_made_flipped_true(synthetic_artifact):
    payload = _mutate(synthetic_artifact, maintainer_decision_made=True)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "maintainer_decision_made" in err


def test_rejects_seed_count_widened_without_evidence(synthetic_artifact):
    payload = _mutate(synthetic_artifact, seed_count=50)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "seed_count" in err


def test_rejects_scope_note_hiding_single_seed_scope(synthetic_artifact):
    payload = _mutate(synthetic_artifact, scope_note="Generalizes across the full natural population.")
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "scope_note" in err


def test_rejects_bad_stop_reason(synthetic_artifact):
    payload = _mutate(synthetic_artifact, **{"probe.stop_reason": "operator_stopped_it"})
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "stop_reason" in err


def test_rejects_natural_pinch_at_or_after_max_ticks(synthetic_artifact):
    # Claiming natural pinch but with n_ticks_ran >= n_ticks_max is a
    # truncation being relabeled as a natural stop.
    payload = _mutate(synthetic_artifact, **{"probe.n_ticks_ran": 200})
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "natural pinch" in err


def test_rejects_formation_count_exceeding_event_count(synthetic_artifact):
    payload = _mutate(synthetic_artifact, **{"probe.n_net2_formation_events_by_complex": [1, 0]})
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "exceeds" in err and "n_net2_formation_events_by_complex" in err


def test_rejects_competition_status_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = [(t, 0, 0, 0, False) for t in range(1, 100)] + [(100, 5, 1, 1, False)] + [
        (t, 5, 0, 0, False) for t in range(101, 150)
    ] + [(150, 5, 0, 0, True)]
    csv_path, summary_path = _write_raw(tmp_path, rows)
    artifact = hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)
    payload = _mutate(artifact, network2_competition_status="neither_fired")
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "network2_competition_status" in err


def test_rejects_csv_recompute_mismatch_on_formation_counts(tmp_path, monkeypatch):
    """The final independent CSV-recompute cross-check must catch a tampered
    probe.n_net2_formation_events_by_complex even when every other
    in-memory consistency check (subset invariant, e1 consistency,
    network2_ever_fired_naturally, competition_status, outcome) has been
    made to agree with the lie -- only re-reading the raw CSV catches it."""
    monkeypatch.setattr(hlr, "N_TICKS_MAX", 200)
    rows = (
        [(t, 0, 0, 0, False) for t in range(1, 100)]
        + [(100, 5, -1, 0, False)]  # complex1: degradation only, no formation
        + [(110, 5, 0, 1, False)]  # complex2: genuine formation
        + [(t, 5, 0, 0, False) for t in range(111, 150)]
        + [(150, 5, 0, 0, True)]
    )
    csv_path, summary_path = _write_raw(tmp_path, rows)
    artifact = hlr.build_lifecycle_reachability_artifact(csv_path=csv_path, summary_path=summary_path)
    assert artifact["probe"]["n_net2_formation_events_by_complex"] == [0, 1]
    assert artifact["network2_competition_status"] == "single_complex_only_fired"
    payload = _mutate(
        artifact,
        **{
            "probe.n_net2_formation_events_by_complex": [1, 1],
            "network2_competition_status": "both_complexes_fired",
        },
    )
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "CSV-recomputed n_net2_formation_events_by_complex" in err


def test_rejects_network2_fired_without_e1_nonzero(synthetic_artifact):
    payload = _mutate(
        synthetic_artifact,
        **{
            "probe.n_net2_events_by_complex": [1, 0],
            "probe.n_net2_formation_events_by_complex": [1, 0],
            "network2_ever_fired_naturally": True,
            "outcome": "network2_fired_naturally",
        },
    )
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "structurally impossible" in err


def test_rejects_outcome_drift_from_derived_value(synthetic_artifact):
    payload = _mutate(synthetic_artifact, outcome="network2_fired_naturally")
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "outcome" in err


def test_rejects_e1_ever_nonzero_inconsistent_with_probe(synthetic_artifact):
    payload = _mutate(synthetic_artifact, e1_ever_nonzero=True)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "e1_ever_nonzero" in err


def test_rejects_stale_matlab_script_hash(synthetic_artifact):
    payload = _mutate(synthetic_artifact, matlab_script_sha256_lf_normalized="0" * 64)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "matlab_script" in err


def test_rejects_stale_generator_hash(synthetic_artifact):
    payload = _mutate(synthetic_artifact, generator_source_sha256_lf_normalized="0" * 64)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "generator_source" in err


def test_rejects_stale_e1_provenance_hash(synthetic_artifact):
    payload = _mutate(synthetic_artifact, e1_provenance_ref_sha256_lf_normalized="0" * 64)
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "e1_provenance_ref" in err


def test_rejects_missing_raw_csv_on_disk(synthetic_artifact):
    payload = _mutate(synthetic_artifact, raw_csv_path="data/does_not_exist_lifecycle.csv")
    err = hlr.validate_lifecycle_reachability_artifact(payload)
    assert err is not None and "raw_csv_path" in err


def test_recompute_from_csv_never_reads_summary_json():
    import inspect

    source = inspect.getsource(hlr._recompute_from_csv)
    # anti-laundering: recomputation reads the raw CSV directly, never opens
    # or parses the summary JSON it is meant to independently cross-check.
    assert "_load_json" not in source
    assert "json.load" not in source


# ---------------------------------------------------------------------------
# Non-gating boundary: this module/artifact must not be wired into the
# central verdict/generator/catalog machinery, nor mutate the accepted
# condition-gated artifact's own lifecycle_reachability_status.
# ---------------------------------------------------------------------------


def test_verdict_module_never_references_this_module():
    source = VERDICT_PATH.read_text(encoding="utf-8")
    assert "h12_lifecycle_reachability" not in source


def test_generator_module_never_references_this_module():
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert "h12_lifecycle_reachability" not in source


def test_evidence_index_never_references_this_module():
    source = EVIDENCE_INDEX_PATH.read_text(encoding="utf-8")
    assert "h12_lifecycle_reachability" not in source


def test_process_catalog_never_references_this_module():
    source = PROCESS_CATALOG_PATH.read_text(encoding="utf-8")
    assert "h12_lifecycle_reachability" not in source


def test_condition_gated_artifact_lifecycle_status_still_literally_unresolved():
    # This module must never have caused the OTHER artifact's own
    # lifecycle_reachability_status to be resolved -- that field is a
    # different, narrower claim (whether a tick_offset>0 RE-EXTRACTION
    # would resolve it) and remains correctly test-locked to "UNRESOLVED"
    # by test_h12_condition_gated.py.
    payload = json.loads(CONDITION_GATED_PATH.read_text(encoding="utf-8"))
    assert payload["lifecycle_reachability_status"] == "UNRESOLVED"


# ---------------------------------------------------------------------------
# Committed real-artifact checks (require `generate` to have been run
# against the real full-cycle MATLAB probe output)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def artifact():
    if not hlr.OUT_PATH.is_file():
        pytest.skip("real lifecycle-reachability artifact not yet generated")
    with open(hlr.OUT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_committed_artifact_exists_and_validates(artifact):
    err = hlr.validate_lifecycle_reachability_artifact(artifact)
    assert err is None, err


def test_committed_artifact_is_single_seed_zero(artifact):
    assert artifact["probe"]["seed"] == 0
    assert artifact["seed_count"] == 1


def test_committed_artifact_scanned_a_substantial_tick_range(artifact):
    # Falsifiability floor: refuse to accept a "probe" that ran a trivially
    # short number of ticks (e.g. a smoke test) as if it were decisive
    # lifecycle-reachability evidence -- must clear RibosomeAssembly's
    # documented ~238-tick activation point with real margin.
    assert artifact["probe"]["n_ticks_ran"] >= 1000


def test_committed_artifact_reports_network2_fired_naturally(artifact):
    # The decisive finding this whole probe exists to establish: E1 leaves
    # zero and network >= 2 actually FORMS a complex (delta > 0, not merely
    # a nonzero delta) under the real scheduler, with no conditioning --
    # directly falsifying the "genuine biological ceiling" hypothesis for
    # the natural lifecycle scanned.
    assert artifact["e1_ever_nonzero"] is True
    assert artifact["network2_ever_fired_naturally"] is True
    assert artifact["outcome"] == "network2_fired_naturally"
    assert any(n > 0 for n in artifact["probe"]["n_net2_formation_events_by_complex"])


def test_committed_artifact_reports_per_complex_identity_evidence(artifact):
    # Per-complex (not summed) reporting is what lets this artifact
    # distinguish genuine 2-way competition from a degenerate
    # single-candidate draw (finding #3); network2_competition_status must
    # be derived, present, and match the per-complex FORMATION-only counts
    # (delta > 0), not the sign-agnostic any-change counts -- a complex
    # already nonzero at cell birth could show a pure degradation event
    # with no formation, which must not be counted as "fired".
    n_net2_events_by_complex = artifact["probe"]["n_net2_events_by_complex"]
    n_net2_formation_events_by_complex = artifact["probe"]["n_net2_formation_events_by_complex"]
    assert len(n_net2_events_by_complex) == 2
    assert len(n_net2_formation_events_by_complex) == 2
    for c in range(2):
        assert n_net2_formation_events_by_complex[c] <= n_net2_events_by_complex[c]
    assert artifact["network2_competition_status"] in (
        "both_complexes_fired",
        "single_complex_only_fired",
        "neither_fired",
    )
    assert artifact["network2_competition_status"] == hlr._competition_status(n_net2_formation_events_by_complex)


def test_committed_artifact_raw_files_are_tracked(artifact):
    assert hlr.RAW_CSV_PATH.is_file()
    if artifact["probe"]["stop_reason"] == hlr.STOP_REASON_OPERATOR_STOPPED:
        assert not hlr.RAW_SUMMARY_PATH.is_file()
        assert hlr.RAW_LOG_PATH.is_file()
    else:
        assert hlr.RAW_SUMMARY_PATH.is_file()
