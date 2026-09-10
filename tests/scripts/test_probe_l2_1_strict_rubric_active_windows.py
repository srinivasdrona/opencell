"""Focused tests for the opt-in active-window-aware L2.1 strict rubric.

Run via:
    bin\\oc-pytest tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py -v
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import l21_active_window_audit as active_windows  # noqa: E402
import probe_l2_1_strict_rubric as probe  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_1" / "L21_ACTIVE_WINDOWS_MANIFEST.json"

EXPECTED_ACTIVE_WINDOW_VERDICTS = {
    "DNARepair": "GENUINE",
    "Metabolism": "GENUINE",
    "ProteinDecay": "GENUINE",
    "Replication": "GENUINE",
    "RNAModification": "GENUINE",
    "RibosomeAssembly": "GENUINE",
    "ChromosomeSegregation": "GENUINE",
    "TranscriptionalRegulation": "GENUINE",
    "Cytokinesis": "GENUINE",
    "DNADamage": "GENUINE",
    "HostInteraction": "GENUINE",
}


def _load_manifest_payload() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _write_single_row_manifest(tmp_path: Path, process_name: str) -> Path:
    payload = _load_manifest_payload()
    row = next(copy.deepcopy(item) for item in payload["rows"] if item["process"] == process_name)
    payload["rows"] = [row]
    payload["counts"] = {
        active_windows.CLASS_EXISTING_WINDOW_PASS: int(
            row["classification"] == active_windows.CLASS_EXISTING_WINDOW_PASS
        ),
        active_windows.CLASS_CODE_GAP: int(row["classification"] == active_windows.CLASS_CODE_GAP),
        active_windows.CLASS_MISSING_ACTIVE_EXTRACTION: int(
            row["classification"] == active_windows.CLASS_MISSING_ACTIVE_EXTRACTION
        ),
    }
    manifest_path = tmp_path / "single_row_active_window_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def test_current_manifest_summary_matches_rows() -> None:
    payload = _load_manifest_payload()
    actual_counts = Counter(row["classification"] for row in payload["rows"])
    expected_counts = {
        classification: actual_counts.get(classification, 0)
        for classification in (
            active_windows.CLASS_EXISTING_WINDOW_PASS,
            active_windows.CLASS_CODE_GAP,
            active_windows.CLASS_MISSING_ACTIVE_EXTRACTION,
        )
    }
    assert payload["counts"] == expected_counts

    expected_nodeids = [
        row["replay_evidence"]["nodeid"]
        for row in payload["rows"]
        if row["classification"] == active_windows.CLASS_EXISTING_WINDOW_PASS
    ]
    assert payload["pytest_replay_command"] == (
        "bin\\\\oc-pytest.cmd -q " + " ".join(expected_nodeids)
    )


def test_no_manifest_path_matches_the_original_default_logic():
    assert probe.audit_one_process("Metabolism") == probe._audit_one_process_default("Metabolism")


def test_active_window_manifest_sha_tamper_fails_closed(tmp_path: Path):
    manifest_path = _write_single_row_manifest(tmp_path, "Metabolism")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["rows"][0]["source"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    verification = active_windows.verify_active_window_manifest_row(manifest_path, "Metabolism")
    assert verification["verification_status"] == active_windows.MANIFEST_VERIFY_INVALID
    assert "sha256 mismatch" in verification["failure_reason"]

    result = probe.audit_one_process("Metabolism", active_window_manifest=manifest_path)
    assert result["verdict"] == active_windows.MANIFEST_VERIFY_INVALID
    assert "sha256 mismatch" in result["active_window_manifest_error"]


def test_active_window_manifest_stale_classification_fails_closed(tmp_path: Path):
    manifest_path = _write_single_row_manifest(tmp_path, "Metabolism")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["rows"][0]["classification"] = active_windows.CLASS_MISSING_ACTIVE_EXTRACTION
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    verification = active_windows.verify_active_window_manifest_row(manifest_path, "Metabolism")
    assert verification["verification_status"] == active_windows.MANIFEST_VERIFY_INVALID
    assert "replay_evidence" in verification["failure_reason"]

    result = probe.audit_one_process("Metabolism", active_window_manifest=manifest_path)
    assert result["verdict"] == active_windows.MANIFEST_VERIFY_INVALID
    assert "replay_evidence" in result["active_window_manifest_error"]


def test_active_window_manifest_code_gap_row_verifies_via_synthetic_row(tmp_path: Path):
    """Regression coverage for `verify_active_window_manifest_row`'s
    CLASS_CODE_GAP re-verification branch (the final fall-through in that
    function, reached when `recorded_classification` is neither
    EXISTING_WINDOW_PASS nor MISSING_ACTIVE_EXTRACTION), using an entirely
    SYNTHETIC manifest row built around a dummy on-disk file -- never
    depending on any row in the REAL manifest actually being CODE_GAP.

    Before the TranscriptionalRegulation promotion (2026-09-09), this
    branch was incidentally exercised by
    `test_current_tree_active_window_manifest_checkpoint
    [TranscriptionalRegulation]` because that was the manifest's one
    real CODE_GAP row. Now that the real manifest is a literal
    11 EXISTING_WINDOW_PASS / 0 CODE_GAP / 0 MISSING_ACTIVE_EXTRACTION (see
    `test_current_manifest_summary_matches_rows`), that incidental
    coverage is gone -- this test closes the gap directly and
    permanently, independent of any future manifest composition.

    Uses HostInteraction's `process_name` (an arbitrary, real
    `TARGET_PROCESSES` member -- the specific choice does not matter here,
    since `_summarize_trace_candidate`/`_classify_live_trace_candidate`
    are both monkeypatched below rather than reading any real trace
    content) with a tiny, self-contained dummy trace file created in
    `tmp_path` so the source-existence/sha256 checks
    (`verify_active_window_manifest_row`'s first real gate) pass against
    a genuine file this test fully controls, never a real gitignored
    trace this worktree may or may not have locally.
    """
    process_name = "HostInteraction"
    dummy_trace_path = tmp_path / "synthetic_dummy_trace.mat"
    dummy_trace_path.write_bytes(b"not a real .mat file, only its sha256 is ever read by this test")
    dummy_sha256 = hashlib.sha256(dummy_trace_path.read_bytes()).hexdigest()

    manifest_path = _write_single_row_manifest(tmp_path, process_name)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = payload["rows"][0]
    row["classification"] = active_windows.CLASS_CODE_GAP
    row["source"] = {
        "path": str(dummy_trace_path),
        "repo_relative_hint": str(dummy_trace_path),
        "sha256": dummy_sha256,
        "trace_family": "event_window",
        "source_manifest": None,
    }
    synthetic_trace_window = {
        "n_ticks": 100,
        "tick_offset": 0.0,
        "first_active_local_tick": 4,
        "first_active_absolute_tick": 4.0,
        "active_tick_count": 1,
        "first_active_detail": None,
    }
    row["trace_window"] = synthetic_trace_window
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    dummy_candidate = active_windows.TraceCandidate(
        path=str(dummy_trace_path),
        repo_relative_hint=str(dummy_trace_path),
        sha256=dummy_sha256,
        trace_family="event_window",
        n_ticks=100,
        rng_seed=0,
        tick_offset=0.0,
        states_after_keys=["substrates"],
        first_active_tick=synthetic_trace_window["first_active_local_tick"],
        first_active_absolute_tick=synthetic_trace_window["first_active_absolute_tick"],
        active_tick_count=synthetic_trace_window["active_tick_count"],
        first_active_detail=None,
        source_manifest=None,
    )

    def fake_summarize_trace_candidate(process, path, *, known_sha, source_manifest):
        assert process == process_name
        assert Path(path) == dummy_trace_path
        assert known_sha == dummy_sha256
        return dummy_candidate

    def fake_classify_live_trace_candidate(process, candidate, *, progress=False):
        assert process == process_name
        assert candidate is dummy_candidate
        return None, None, active_windows.CLASS_CODE_GAP, None

    original_summarize = active_windows._summarize_trace_candidate
    original_classify = active_windows._classify_live_trace_candidate
    active_windows._summarize_trace_candidate = fake_summarize_trace_candidate
    active_windows._classify_live_trace_candidate = fake_classify_live_trace_candidate
    try:
        verification = active_windows.verify_active_window_manifest_row(manifest_path, process_name)
    finally:
        active_windows._summarize_trace_candidate = original_summarize
        active_windows._classify_live_trace_candidate = original_classify

    assert verification["verified"] is True
    assert verification["verification_status"] == active_windows.MANIFEST_VERIFY_CODE_GAP
    assert verification["fresh_classification"] == active_windows.CLASS_CODE_GAP
    assert verification["recorded_classification"] == active_windows.CLASS_CODE_GAP
    assert verification["failure_reason"] is None


@pytest.mark.parametrize("process_name", sorted(EXPECTED_ACTIVE_WINDOW_VERDICTS))
def test_current_tree_active_window_manifest_checkpoint(process_name: str):
    result = probe.audit_one_process(process_name, active_window_manifest=MANIFEST_PATH)
    assert result["verdict"] == EXPECTED_ACTIVE_WINDOW_VERDICTS[process_name]

    manifest_detail = result["active_window_manifest"]
    assert manifest_detail["manifest_sha256"] is not None
    assert len(manifest_detail["manifest_sha256"]) == 64
    assert manifest_detail["source_actual_sha256"] == manifest_detail["source_recorded_sha256"]

    if result["verdict"] == "GENUINE":
        assert manifest_detail["verification_status"] == active_windows.MANIFEST_VERIFY_EXISTING_WINDOW_PASS
        assert result["bit_identity_pass"] is True
        assert result["karr_active_ticks"] > 0
        assert result["fire_rate_when_karr_active"] is not None
    elif result["verdict"] == active_windows.CLASS_CODE_GAP:
        # CODE_GAP rows are re-verified by fully re-running the live bit-identity
        # replay against the recorded source trace; the manifest classification is
        # only trusted if the fresh replay independently reproduces a genuine,
        # Karr-active divergence (not merely an unchanged/stale label).
        assert manifest_detail["verification_status"] == active_windows.MANIFEST_VERIFY_CODE_GAP
        assert manifest_detail["fresh_classification"] == active_windows.CLASS_CODE_GAP
        assert result["bit_identity_pass"] is False
        assert result["karr_active_ticks"] > 0
    else:
        assert result["verdict"] == active_windows.CLASS_MISSING_ACTIVE_EXTRACTION
        assert (
            manifest_detail["verification_status"]
            == active_windows.MANIFEST_VERIFY_MISSING_ACTIVE_EXTRACTION
        )
