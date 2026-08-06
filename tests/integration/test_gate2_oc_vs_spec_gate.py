"""Integration tests for the Gate 2 OC-vs-spec structural gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "gate2_verify_oc_vs_spec.py"

_spec = importlib.util.spec_from_file_location("_gate2_oc_vs_spec", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)

_PROCESS_SPECS = gate._load_process_specs()


def _make_process(process_name: str):
    return _PROCESS_SPECS[process_name].process_cls({"rng_seed": 0})


def test_gate_runs_and_reports_current_tree_without_crashing() -> None:
    code, message = gate._gate_result()

    assert code in {0, 1}
    assert isinstance(message, str)
    assert message.startswith("GATE 2 (OC vs spec): ")
    assert "processes=28" in message
    assert "StateUsage" in message
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


def test_state_usage_is_descoped_to_a_cross_process_pointer() -> None:
    # State-usage (which shared Karr state objects a process couples to) is a
    # CROSS-PROCESS concern, not per-process input fidelity. It is deliberately
    # out of scope for Gate 2: metabolite producer/consumer deps are validated by
    # L1b Half B (dependency_symmetry), and state-object hand-off is deferred to L3.
    # The class returns a uniform N/A pointer for every process and never fails the gate.
    for process_name in ("DNADamage", "Transcription", "Metabolism"):
        result = gate._evaluate_state_usage_class(process_name)
        assert result.status == gate._STATUS_NA
        assert len(result.details) == 1
        assert result.details[0].startswith("OUT OF SCOPE for Gate 2")
        assert "L1b Half B" in result.details[0]
        assert "L3" in result.details[0]


def test_compare_vocab_sets_reports_missing_and_extra_members() -> None:
    missing, extra = gate._compare_vocab_sets(
        expected=["ATP", "CTP", "GTP"],
        actual=["ATP", "GTP", "UTP"],
    )

    assert missing == ["CTP"]
    assert extra == ["UTP"]


def test_shape_comparison_treats_ragged_values_as_not_comparable() -> None:
    ragged = (np.array([1.0]), np.array([2.0, 3.0]))

    assert gate._values_match({"shape": [2]}, ragged) is None
