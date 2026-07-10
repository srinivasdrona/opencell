"""Integration tests for the Gate 1 input-spec freeze gate."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "gate1_verify_spec_freeze.py"

_spec = importlib.util.spec_from_file_location("_gate1_freeze", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_gate_passes_on_clean_committed_tree() -> None:
    code, message = gate._gate_result()

    assert code == 0
    assert message.startswith("GATE 1 (spec freeze): PASS")
    assert "28 processes" in message


def test_gate_fails_when_spec_yaml_is_mutated(tmp_path: Path) -> None:
    spec_dir = tmp_path / "karr_input_spec"
    shutil.copytree(gate.DEFAULT_SPEC_DIR, spec_dir)
    process_name = "DNARepair"
    spec_path = spec_dir / f"{process_name}.yaml"
    original = spec_path.read_bytes()
    spec_path.write_bytes(original[:-1] + (b"\r" if original[-1:] != b"\r" else b"\n"))

    code, message = gate._gate_result(
        spec_dir=spec_dir,
        manifest_path=spec_dir / "MANIFEST.json",
    )

    assert code == 1
    assert process_name in message
    assert "spec hash drift" in message or "spec bytes drift" in message


def test_gate_fails_when_manifest_hash_is_mutated(tmp_path: Path) -> None:
    spec_dir = tmp_path / "karr_input_spec"
    shutil.copytree(gate.DEFAULT_SPEC_DIR, spec_dir)
    manifest_path = spec_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    process_name = "DNARepair"
    manifest[process_name]["spec_sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    code, message = gate._gate_result(spec_dir=spec_dir, manifest_path=manifest_path)

    assert code == 1
    assert process_name in message
    assert "spec hash drift" in message or "MANIFEST.json drift" in message


def test_gate_skips_cleanly_when_fixtures_are_absent(tmp_path: Path) -> None:
    empty_fixture_dir = tmp_path / "missing_fixtures"
    empty_fixture_dir.mkdir()

    code, message = gate._gate_result(fixture_dir=empty_fixture_dir)

    assert code == 0
    assert "SKIPPED" in message
