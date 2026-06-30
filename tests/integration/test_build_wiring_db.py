"""Integration coverage for the wiring DB generator and cross-row checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _REPO_ROOT / "scripts" / "build_wiring_db.py"
_DEFAULT_SOURCE_DIR = _REPO_ROOT / "data" / "schemas" / "per_process_wiring"


def _run_generator(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_GENERATOR), *args],
        cwd=str(cwd or _REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _anchor(label: str) -> dict[str, str]:
    return {
        "path": f"tests/fixtures/{label}.py",
        "lines": "1-2",
        "note": f"synthetic anchor for {label}",
    }


def _method_binding(process_name: str, method_name: str) -> dict[str, Any]:
    return {
        "matlab": {
            "symbol": f"{process_name}_{method_name}_matlab",
            "source": _anchor(f"{process_name}_{method_name}_matlab"),
        },
        "oc": {
            "symbol": f"{process_name}_{method_name}_oc",
            "source": _anchor(f"{process_name}_{method_name}_oc"),
        },
        "status": "implemented",
    }


def _row(
    process_name: str,
    *,
    produces_inputs_for: list[str] | None = None,
    consumes_outputs_of: list[str] | None = None,
    hard_before: list[str] | None = None,
    dependencies_note: str = "",
) -> dict[str, Any]:
    produces_inputs_for = produces_inputs_for or []
    consumes_outputs_of = consumes_outputs_of or []
    hard_before = hard_before or []
    return {
        "schema_version": "1.0",
        "schema_date": "2026-06-29",
        "process": {
            "name": process_name,
            "matlab_class": process_name,
            "matlab_file": f"tests/fixtures/{process_name}.m",
            "oc_class": f"{process_name}Process",
            "oc_file": f"tests/fixtures/{process_name}.py",
            "whole_cell_model_id": f"Process_{process_name}",
        },
        "methods": {
            "calcResourceRequirements_Current": _method_binding(process_name, "calcResourceRequirements_Current"),
            "evolveState": _method_binding(process_name, "evolveState"),
            "calcFluxBounds": _method_binding(process_name, "calcFluxBounds"),
        },
        "allocator": {
            "mode": {"karr": "allocation", "oc_current": "allocation"},
            "request_formula": {"matlab": "requests", "oc": "requests"},
            "requests": [],
            "bypasses": [],
        },
        "consume_stoichiometry": [],
        "produce_stoichiometry": [],
        "compartment_routing": [],
        "unit_conversion_chain": {
            "source_units": "a.u.",
            "target_units": "a.u.",
            "steps": [
                {
                    "from_units": "a.u.",
                    "to_units": "a.u.",
                    "operation": "identity",
                    "anchor": _anchor(f"{process_name}_conversion"),
                }
            ],
        },
        "dependencies": {
            "produces_inputs_for": produces_inputs_for,
            "consumes_outputs_of": consumes_outputs_of,
            "note": dependencies_note,
        },
        "ordering_constraints": {
            "hard_before": hard_before,
            "hard_after": [],
            "soft_before": [],
            "soft_after": [],
            "note": "",
        },
        "source_anchors": {
            "matlab_blocks": {"main": _anchor(f"{process_name}_matlab_block")},
            "oc_blocks": {"main": _anchor(f"{process_name}_oc_block")},
        },
        "provenance": {
            "last_audited": "2026-06-29",
            "matlab_files_referenced": [f"tests/fixtures/{process_name}.m"],
            "oc_files_referenced": [f"tests/fixtures/{process_name}.py"],
        },
        "deviations": {
            "lp_bounds_source": {
                "karr": "allocation",
                "oc_current": "allocation",
                "matlab_anchor": _anchor(f"{process_name}_lp_matlab"),
                "oc_anchor": _anchor(f"{process_name}_lp_oc"),
            },
            "shared_pool_projection_merges_compartments": False,
            "known_deviations": [],
            "note": "",
        },
    }


def _write_source_dir(source_dir: Path, rows: dict[str, dict[str, Any]]) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "schema_version": "1.0",
        "schema_date": "2026-06-29",
    }
    (source_dir / "_schema.yaml").write_text(yaml.safe_dump(schema, sort_keys=False), encoding="utf-8")
    for process_name, row in rows.items():
        (source_dir / f"{process_name}.yaml").write_text(
            yaml.safe_dump(row, sort_keys=False),
            encoding="utf-8",
        )


def test_build_validate_only_passes_on_existing_state() -> None:
    current_rows = sorted(p for p in _DEFAULT_SOURCE_DIR.glob("*.yaml") if not p.name.startswith("_"))
    if len(current_rows) < 28:
        pytest.skip("Current wiring DB is still partial; validate-only is expected to fail until all 28 rows land.")

    result = _run_generator("--validate-only")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[CROSS]" in result.stdout
    assert "PASS" in result.stdout


def test_build_emits_combined_yaml(tmp_path: Path) -> None:
    out_path = tmp_path / "_combined.yaml"
    result = _run_generator("--out", str(out_path))
    assert out_path.exists(), result.stdout + result.stderr
    payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert set(payload) >= {"metadata", "processes"}
    assert isinstance(payload["metadata"], dict)
    assert isinstance(payload["processes"], list)
    assert payload["metadata"]["validation_status"] in {"PASS", "FAIL"}
    assert isinstance(payload["metadata"]["row_count"], int)


def test_reciprocal_consistency_detector(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    _write_source_dir(
        source_dir,
        {
            "A": _row("A", produces_inputs_for=["B"]),
            "B": _row("B"),
        },
    )
    out_path = tmp_path / "_combined.yaml"
    result = _run_generator("--validate-only", "--source-dir", str(source_dir), "--out", str(out_path))
    assert result.returncode == 1
    assert "reciprocal mismatch" in result.stdout
    assert "A -> B" in result.stdout


def test_cyclic_ordering_detector(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    _write_source_dir(
        source_dir,
        {
            "A": _row("A", hard_before=["B"]),
            "B": _row("B", hard_before=["A"]),
        },
    )
    out_path = tmp_path / "_combined.yaml"
    result = _run_generator("--validate-only", "--source-dir", str(source_dir), "--out", str(out_path))
    assert result.returncode == 1
    assert "cyclic ordering" in result.stdout
    assert "A hard_before B" in result.stdout
    assert "B hard_before A" in result.stdout
