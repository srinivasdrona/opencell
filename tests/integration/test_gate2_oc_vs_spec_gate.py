"""Integration tests for the Gate 2 OC-vs-spec vocabulary gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "gate2_verify_oc_vs_spec.py"

_spec = importlib.util.spec_from_file_location("_gate2_oc_vs_spec", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_gate_runs_and_reports_current_tree_without_crashing() -> None:
    code, message = gate._gate_result()

    assert code in {0, 1}
    assert isinstance(message, str)
    assert message.startswith("GATE 2 (OC vs spec): ")
    assert "/28 processes" in message
    assert "INFO — order-only differences:" in message
    assert "Transcription: substrates" not in message


def test_compare_vocab_sets_reports_missing_and_extra_members() -> None:
    missing, extra = gate._compare_vocab_sets(
        expected=["ATP", "CTP", "GTP"],
        actual=["ATP", "GTP", "UTP"],
    )

    assert missing == ["CTP"]
    assert extra == ["UTP"]
