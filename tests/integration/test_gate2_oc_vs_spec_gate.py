"""Integration tests for the Gate 2 OC-vs-spec structural gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "gate2_verify_oc_vs_spec.py"

_spec = importlib.util.spec_from_file_location("_gate2_oc_vs_spec", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)

_PROCESS_SPECS = gate._load_process_specs()
_STATE_USAGE = gate._load_state_usage(gate._STATE_USAGE_PATH)


def _make_process(process_name: str):
    return _PROCESS_SPECS[process_name].process_cls({"rng_seed": 0})


def test_gate_runs_and_reports_current_tree_without_crashing() -> None:
    code, message = gate._gate_result()

    assert code in {0, 1}
    assert isinstance(message, str)
    assert message.startswith("GATE 2 (OC vs spec): ")
    assert "processes=28" in message
    assert "StateUsage" in message
    assert "missing_states=" in message
    assert "Transcription: substrates" not in message


def test_small_molecule_stoich_processes_match_small_molecule_spec_basis() -> None:
    for process_name in ("DNADamage", "DNARepair"):
        process = _make_process(process_name)
        spec_payload = gate._load_spec_payload(gate.DEFAULT_SPEC_DIR / f"{process_name}.yaml")

        result = gate._evaluate_stoichiometry_class(
            process,
            spec_payload,
            fixture_path=gate.DEFAULT_FIXTURE_DIR / f"{process_name}_flat.mat",
        )

        assert result.status == gate._STATUS_CONFORM
        assert result.details == []


def test_state_usage_reports_missing_states_from_karr_usage() -> None:
    dnadamage = gate._evaluate_state_usage_class(
        "DNADamage",
        _make_process("DNADamage"),
        fixture_path=gate.DEFAULT_FIXTURE_DIR / "DNADamage_flat.mat",
        state_usage=_STATE_USAGE,
    )
    transcription = gate._evaluate_state_usage_class(
        "Transcription",
        _make_process("Transcription"),
        fixture_path=gate.DEFAULT_FIXTURE_DIR / "Transcription_flat.mat",
        state_usage=_STATE_USAGE,
    )

    # State-usage is now INFO-only (demoted from a hard gate) because the heuristic
    # has known false-positives/negatives (writes-as-reads, missed MATLAB aliases, OC
    # private fixture-state loads). It reports apparent gaps but does NOT fail the gate.
    assert dnadamage.status == gate._STATUS_CONFORM
    assert transcription.status == gate._STATUS_NOT_EXPOSED
    assert any(
        detail.startswith("apparent missing_states=") and "RNAPolymerase" in detail
        for detail in transcription.details
    )
    assert any("HEURISTIC / INFO-ONLY" in detail for detail in transcription.details)


def test_compare_vocab_sets_reports_missing_and_extra_members() -> None:
    missing, extra = gate._compare_vocab_sets(
        expected=["ATP", "CTP", "GTP"],
        actual=["ATP", "GTP", "UTP"],
    )

    assert missing == ["CTP"]
    assert extra == ["UTP"]
