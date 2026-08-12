"""Focused tests for the opt-in active-window-aware L2.1 strict rubric.

Run via:
    bin\\oc-pytest tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py -v
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
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import l21_active_window_audit as active_windows  # noqa: E402
import probe_l2_1_strict_rubric as probe  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "L21_ACTIVE_WINDOWS_MANIFEST.json"

EXPECTED_ACTIVE_WINDOW_VERDICTS = {
    "DNARepair": "GENUINE",
    "Metabolism": "GENUINE",
    "ProteinDecay": "GENUINE",
    "Replication": "GENUINE",
    "RNAModification": "GENUINE",
    "RibosomeAssembly": "GENUINE",
    "TranscriptionalRegulation": active_windows.CLASS_MISSING_ACTIVE_EXTRACTION,
    "ChromosomeSegregation": active_windows.CLASS_MISSING_ACTIVE_EXTRACTION,
    "Cytokinesis": active_windows.CLASS_MISSING_ACTIVE_EXTRACTION,
    "DNADamage": active_windows.CLASS_MISSING_ACTIVE_EXTRACTION,
    "HostInteraction": active_windows.CLASS_MISSING_ACTIVE_EXTRACTION,
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
    else:
        assert result["verdict"] == active_windows.CLASS_MISSING_ACTIVE_EXTRACTION
        assert (
            manifest_detail["verification_status"]
            == active_windows.MANIFEST_VERIFY_MISSING_ACTIVE_EXTRACTION
        )
