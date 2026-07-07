"""Integration tests for scripts/l1b_verify_wiring.py."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "l1b_verify_wiring.py"
_SCHEMA = _REPO_ROOT / "data" / "schemas" / "per_process_wiring" / "_schema.yaml"


def _run_l1b(
    *args: str,
    env_overrides: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=str(cwd or _REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _make_matlab_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "classdef SynthProcess",
                "methods",
                "function out = calcResourceRequirements_Current(obj)",
                "out = 0;",
                "end",
                "function out = evolveState(obj)",
                "out = 0;",
                "end",
                "function out = calcFluxBounds(obj)",
                "out = 0;",
                "end",
                "function out = initializeConstants(obj)",
                "out = 0;",
                "end",
                "end",
                "end",
            ]
        ),
        encoding="utf-8",
    )


def _make_latin1_matlab_file(path: Path) -> None:
    lines = [
        "classdef SynthProcess",
        "methods",
        "function out = calcResourceRequirements_Current(obj)",
        "out = 0;",
        "end",
        "function out = evolveState(obj)",
        "out = 0;",
        "end",
        "function out = calcFluxBounds(obj)",
        "out = 0;",
        "end",
        "function out = initializeConstants(obj)",
        "out = 0;",
        "end",
        "end",
        "end",
        "% caf\xe9",
    ]
    path.write_bytes("\n".join(lines).encode("latin-1"))


def _make_python_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "class SynthProcess:",
                "    def calc_resource_requirements(self) -> int:",
                "        return 0",
                "",
                "    def evolve_state(self) -> int:",
                "        return 0",
                "",
                "def compute_bounds() -> int:",
                "    return 0",
                "",
                "class RequestCalculatorSynth:",
                "    def next_update(self) -> int:",
                "        return 0",
                "",
                "class KarrAllocationStep:",
                "    def next_update(self) -> int:",
                "        return 0",
            ]
        ),
        encoding="utf-8",
    )


def _make_extract_doc_file(path: Path, *, symbols: list[str]) -> None:
    prose = "\n".join(f"- Derived summary mentions `{symbol}` in prose." for symbol in symbols)
    path.write_text(
        "\n".join(
            [
                "# Synthetic extracted process doc",
                "",
                prose,
            ]
        ),
        encoding="utf-8",
    )


def _anchor(path: Path, symbol: str, lines: str = "1-200") -> dict[str, str]:
    return {
        "path": str(path),
        "symbol": symbol,
        "lines": lines,
        "note": "synthetic anchor",
    }


def _stub_method_map(
    *,
    process_name: str,
    request_symbol: str = "calc_resource_requirements",
    evolve_symbol: str = "evolve_state",
    bounds_symbol: str = "compute_bounds",
) -> dict[str, Any]:
    return {
        "schema": "oc_method_map/1.0",
        "processes": {
            process_name: {
                "runtime_methods": {
                    "calcResourceRequirements_Current": {
                        "oc": f"synthetic.py:{request_symbol}:1",
                    },
                    "evolveState": {
                        "oc": f"synthetic.py:{evolve_symbol}:1",
                    },
                    "calcFluxBounds": {
                        "oc": f"synthetic.py:{bounds_symbol}:1",
                    },
                }
            }
        },
    }


def _stub_method_map_many(*process_names: str) -> dict[str, Any]:
    payload = {"schema": "oc_method_map/1.0", "processes": {}}
    for process_name in process_names:
        payload["processes"][process_name] = _stub_method_map(process_name=process_name)["processes"][process_name]
    return payload


def _synthetic_row(
    *,
    process_name: str,
    matlab_path: Path,
    python_path: Path,
    consume_wid: str = "GLC",
    produce_wid: str = "ATP",
    request_wid: str = "GLC",
    bypass_wid: str = "ATP",
    coherent_units: bool = True,
) -> dict[str, Any]:
    first_to_units = "molecules/s"
    second_from_units = "molecules/s" if coherent_units else "wrong_units"
    return {
        "schema_version": "2.0",
        "schema_date": "2026-07-07",
        "process": {
            "name": process_name,
            "matlab_class": process_name,
            "matlab_file": str(matlab_path),
            "oc_class": f"{process_name}Process",
            "oc_file": str(python_path),
            "whole_cell_model_id": f"Process_{process_name}",
        },
        "integration_touchpoints": {
            "calcResourceRequirements_Current": {
                "matlab": {
                    "symbol": "calcResourceRequirements_Current",
                    "source": _anchor(matlab_path, "calcResourceRequirements_Current"),
                },
                "oc": {
                    "symbol": "calc_resource_requirements",
                    "source": _anchor(python_path, "calc_resource_requirements"),
                },
                "status": "implemented",
            },
            "evolveState": {
                "matlab": {"symbol": "evolveState", "source": _anchor(matlab_path, "evolveState")},
                "oc": {
                    "symbol": "evolve_state",
                    "source": _anchor(python_path, "evolve_state"),
                    "supporting": [
                        _anchor(python_path, "compute_bounds", lines="1-50"),
                    ],
                },
                "status": "implemented",
            },
            "calcFluxBounds": {
                "matlab": {"symbol": "calcFluxBounds", "source": _anchor(matlab_path, "calcFluxBounds")},
                "oc": {"symbol": "compute_bounds", "source": _anchor(python_path, "compute_bounds")},
                "status": "implemented",
            },
        },
        "allocator": {
            "mode": {"karr": "allocation", "oc_current": "allocation"},
            "request_formula": {"matlab": "req", "oc": "req"},
            "requests": [{"wid": request_wid, "compartment": "cytosol", "source": "karr", "note": "synthetic"}],
            "bypasses": [{"wid": bypass_wid, "compartment": "cytosol", "source": "oc", "note": "synthetic"}],
        },
        "consume_stoichiometry": [
            {
                "wid": consume_wid,
                "compartment": "cytosol",
                "kind": "constant",
                "formula_or_constant": "1",
                "matlab_anchor": _anchor(matlab_path, "evolveState"),
                "oc_anchor": _anchor(python_path, "evolve_state"),
            }
        ],
        "produce_stoichiometry": [
            {
                "wid": produce_wid,
                "compartment": "cytosol",
                "kind": "constant",
                "formula_or_constant": "1",
                "matlab_anchor": _anchor(matlab_path, "evolveState"),
                "oc_anchor": _anchor(python_path, "evolve_state"),
            }
        ],
        "stoichiometry_oracle": {
            "class": "matrix",
            "record_path": "__AUTO_ORACLE__",
            "substrate_count": 2,
            "note": "synthetic oracle",
        },
        "compartment_routing": [],
        "unit_conversion_chain": {
            "source_units": "mmol",
            "target_units": "molecules/tick",
            "steps": [
                {
                    "from_units": "mmol",
                    "to_units": first_to_units,
                    "operation": "x",
                    "anchor": _anchor(matlab_path, "initializeConstants"),
                },
                {
                    "from_units": second_from_units,
                    "to_units": "molecules/tick",
                    "operation": "x",
                    "anchor": _anchor(matlab_path, "initializeConstants"),
                },
            ],
        },
        "dependencies": {"produces_inputs_for": [], "consumes_outputs_of": []},
        "ordering_constraints": {"hard_before": [], "hard_after": [], "soft_before": [], "soft_after": []},
        "source_anchors": {
            "matlab_blocks": {"main": _anchor(matlab_path, "evolveState")},
            "oc_blocks": {"main": _anchor(python_path, "evolve_state")},
        },
        "provenance": {
            "last_audited": "2026-07-07",
            "audited_by": "test",
            "oc_commit_sha": "deadbeef",
            "matlab_files_referenced": [str(matlab_path)],
            "oc_files_referenced": [str(python_path)],
        },
        "deviations": {
            "lp_bounds_source": {
                "karr": "allocation",
                "oc_current": "allocation",
                "matlab_anchor": _anchor(matlab_path, "calcFluxBounds"),
                "oc_anchor": _anchor(python_path, "compute_bounds"),
            },
            "shared_pool_projection_merges_compartments": False,
            "known_deviations": [],
        },
    }


def _write_synthetic_env(
    tmp_path: Path,
    *,
    row_payload: dict[str, Any],
    process_name: str,
    state_groups: dict[str, list[str]],
    method_map_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    wiring_dir = tmp_path / "wiring"
    schema_dir = tmp_path / "per_process"
    wiring_dir.mkdir(parents=True, exist_ok=True)
    schema_dir.mkdir(parents=True, exist_ok=True)

    (wiring_dir / "_schema.yaml").write_text(_SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
    row_copy = copy.deepcopy(row_payload)
    oracle_path = tmp_path / "oracle.json"
    oracle_block = row_copy.get("stoichiometry_oracle")
    oracle_class = oracle_block.get("class") if isinstance(oracle_block, dict) else "matrix"
    if oracle_class == "none":
        oracle_substrates: list[dict[str, str]] = []
    else:
        oracle_substrates = []
        seen_pairs: set[tuple[str, str]] = set()
        for entry in [*row_copy.get("consume_stoichiometry", []), *row_copy.get("produce_stoichiometry", [])]:
            if not isinstance(entry, dict):
                continue
            wid = entry.get("wid")
            compartment = entry.get("compartment")
            if not isinstance(wid, str) or not isinstance(compartment, str):
                continue
            pair = (wid, compartment)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            oracle_substrates.append({"wid": wid, "compartment": compartment})
        if not oracle_substrates:
            oracle_substrates = [
                {"wid": "GLC", "compartment": "cytosol"},
                {"wid": "ATP", "compartment": "cytosol"},
            ]
    if isinstance(row_copy.get("stoichiometry_oracle"), dict):
        row_copy["stoichiometry_oracle"].setdefault("substrate_count", len(oracle_substrates))
    oracle_path.write_text(
        json.dumps(
            {
                "process": process_name,
                "class": oracle_class,
                "n_substrates": len(oracle_substrates),
                "substrates": oracle_substrates,
            }
        ),
        encoding="utf-8",
    )
    row_copy["stoichiometry_oracle"]["record_path"] = str(oracle_path)
    _write_yaml(wiring_dir / f"{process_name}.yaml", row_copy)

    stem = "synthetic_process"
    (schema_dir / f"{stem}.toml").write_text(
        "\n".join(
            [
                "[process]",
                f'name = "{process_name}"',
                "",
                "[state_groups]",
                f'substrates = {state_groups.get("substrates", [])!r}'.replace("'", '"'),
                f'enzymes = {state_groups.get("enzymes", [])!r}'.replace("'", '"'),
                f'monomers = {state_groups.get("monomers", [])!r}'.replace("'", '"'),
                f'complexs = {state_groups.get("complexs", [])!r}'.replace("'", '"'),
                f'rnas = {state_groups.get("rnas", [])!r}'.replace("'", '"'),
            ]
        ),
        encoding="utf-8",
    )

    env = {
        "OC_L1B_WIRING_DIR": str(wiring_dir),
        "OC_L1B_PROCESS_SCHEMA_DIR": str(schema_dir),
    }
    if method_map_payload is not None:
        method_map_path = tmp_path / "oc_method_map.yaml"
        _write_yaml(method_map_path, method_map_payload)
        env["OC_L1B_OC_METHOD_MAP"] = str(method_map_path)
    return env


def _write_synthetic_corpus_env(
    tmp_path: Path,
    *,
    row_payloads: list[dict[str, Any]],
    state_groups_by_process: dict[str, dict[str, list[str]]],
    method_map_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    wiring_dir = tmp_path / "wiring"
    schema_dir = tmp_path / "per_process"
    wiring_dir.mkdir(parents=True, exist_ok=True)
    schema_dir.mkdir(parents=True, exist_ok=True)

    (wiring_dir / "_schema.yaml").write_text(_SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")

    for row_payload in row_payloads:
        row_copy = copy.deepcopy(row_payload)
        process_name = row_copy["process"]["name"]

        oracle_block = row_copy.get("stoichiometry_oracle")
        oracle_class = oracle_block.get("class") if isinstance(oracle_block, dict) else "matrix"
        if oracle_class == "none":
            oracle_substrates = []
        else:
            oracle_substrates = []
            seen_pairs: set[tuple[str, str]] = set()
            for entry in [*row_copy.get("consume_stoichiometry", []), *row_copy.get("produce_stoichiometry", [])]:
                if not isinstance(entry, dict):
                    continue
                wid = entry.get("wid")
                compartment = entry.get("compartment")
                if not isinstance(wid, str) or not isinstance(compartment, str):
                    continue
                pair = (wid, compartment)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                oracle_substrates.append({"wid": wid, "compartment": compartment})

            if not oracle_substrates:
                oracle_substrates = [
                    {"wid": "GLC", "compartment": "cytosol"},
                    {"wid": "ATP", "compartment": "cytosol"},
                ]

        if isinstance(row_copy.get("stoichiometry_oracle"), dict):
            row_copy["stoichiometry_oracle"].setdefault("substrate_count", len(oracle_substrates))
        oracle_path = tmp_path / f"{process_name}_oracle.json"
        oracle_path.write_text(
            json.dumps(
                {
                    "process": process_name,
                    "class": oracle_class,
                    "n_substrates": len(oracle_substrates),
                    "substrates": oracle_substrates,
                }
            ),
            encoding="utf-8",
        )
        row_copy["stoichiometry_oracle"]["record_path"] = str(oracle_path)
        _write_yaml(wiring_dir / f"{process_name}.yaml", row_copy)

    for process_name, state_groups in state_groups_by_process.items():
        (schema_dir / f"{process_name.lower()}.toml").write_text(
            "\n".join(
                [
                    "[process]",
                    f'name = "{process_name}"',
                    "",
                    "[state_groups]",
                    f'substrates = {state_groups.get("substrates", [])!r}'.replace("'", '"'),
                    f'enzymes = {state_groups.get("enzymes", [])!r}'.replace("'", '"'),
                    f'monomers = {state_groups.get("monomers", [])!r}'.replace("'", '"'),
                    f'complexs = {state_groups.get("complexs", [])!r}'.replace("'", '"'),
                    f'rnas = {state_groups.get("rnas", [])!r}'.replace("'", '"'),
                ]
            ),
            encoding="utf-8",
        )

    env = {
        "OC_L1B_WIRING_DIR": str(wiring_dir),
        "OC_L1B_PROCESS_SCHEMA_DIR": str(schema_dir),
    }
    if method_map_payload is not None:
        method_map_path = tmp_path / "oc_method_map.yaml"
        _write_yaml(method_map_path, method_map_payload)
        env["OC_L1B_OC_METHOD_MAP"] = str(method_map_path)
    return env


def _json_report(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(result.stdout)


def _row_by_name(report: dict[str, Any], process_name: str) -> dict[str, Any]:
    matches = [row for row in report["rows"] if row["process"] == process_name]
    assert matches, f"missing row {process_name} in report"
    return matches[0]


def test_all_28_rows_run_without_exception() -> None:
    result = _run_l1b("--format", "plain")
    assert result.returncode in {0, 1}
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined


def test_metabolism_row_passes_checks_1_and_2() -> None:
    result = _run_l1b("--process", "Metabolism", "--format", "json")
    assert result.returncode in {0, 1}
    report = _json_report(result)
    row = _row_by_name(report, "Metabolism")
    assert row["checks"]["check_matlab_anchors_resolve"]["verdict"] == "PASS"
    assert row["checks"]["check_oc_anchors_resolve"]["verdict"] == "PASS"


def test_synthetic_row_with_missing_matlab_file_fails_check_1(tmp_path: Path) -> None:
    matlab_path = tmp_path / "missing.m"
    python_path = tmp_path / "synthetic.py"
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 1
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert row_report["checks"]["check_matlab_anchors_resolve"]["verdict"] == "FAIL"


def test_synthetic_row_with_wid_not_in_schema_toml_fails_check_3(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
        consume_wid="NONEXISTENT_WID",
    )
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 1
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert row_report["checks"]["check_consume_produce_wids_in_schema_toml"]["verdict"] == "FAIL"


def test_unit_conversion_chain_incoherence_fails_check_5(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
        coherent_units=False,
    )
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 1
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert row_report["checks"]["check_unit_conversion_chain_coherent"]["verdict"] == "FAIL"


def test_cyclic_ordering_partner_valid_process_passes_check_6() -> None:
    result = _run_l1b("--process", "Translation", "--format", "json")
    assert result.returncode in {0, 1}
    report = _json_report(result)
    row = _row_by_name(report, "Translation")
    assert row["checks"]["check_ordering_constraints_reference_valid_processes"]["verdict"] == "PASS"


def test_check1_latin1_matlab_file_decodes(tmp_path: Path) -> None:
    matlab_path = tmp_path / "latin1_synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_latin1_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 0
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert row_report["checks"]["check_matlab_anchors_resolve"]["verdict"] == "PASS"


def test_check1_mirror_path_rewrite(tmp_path: Path) -> None:
    mirror_relative = Path("tmp") / "test_check1_mirror_path_rewrite.m"
    rewritten_matlab_path = _REPO_ROOT / mirror_relative
    mirror_matlab_path = Path(f"E:/opencell-mirrors/opencell/{mirror_relative.as_posix()}")
    python_path = tmp_path / "synthetic.py"

    rewritten_matlab_path.parent.mkdir(parents=True, exist_ok=True)
    _make_matlab_file(rewritten_matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=mirror_matlab_path,
        python_path=python_path,
    )
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
    )

    try:
        result = _run_l1b("--format", "json", env_overrides=env)
    finally:
        rewritten_matlab_path.unlink(missing_ok=True)

    assert result.returncode == 0
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    check_1 = row_report["checks"]["check_matlab_anchors_resolve"]
    assert check_1["verdict"] == "PASS"
    assert any("mirror anchor path rewritten" in detail for detail in check_1["details"])


def test_check1_md_extract_doc_permissive(tmp_path: Path) -> None:
    python_path = tmp_path / "synthetic.py"
    _make_python_file(python_path)

    md_with_symbols = tmp_path / "extract_with_symbols.md"
    _make_extract_doc_file(
        md_with_symbols,
        symbols=[
            "calcResourceRequirements_Current",
            "evolveState",
            "calcFluxBounds",
            "initializeConstants",
        ],
    )
    row_pass = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=md_with_symbols,
        python_path=python_path,
    )
    env_pass = _write_synthetic_env(
        tmp_path / "pass_case",
        row_payload=row_pass,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
    )
    result_pass = _run_l1b("--format", "json", env_overrides=env_pass)
    assert result_pass.returncode == 0
    report_pass = _json_report(result_pass)
    row_report_pass = _row_by_name(report_pass, "SyntheticProcess")
    check_1_pass = row_report_pass["checks"]["check_matlab_anchors_resolve"]
    assert check_1_pass["verdict"] == "PASS"
    assert any("derived-doc .md anchor" in detail for detail in check_1_pass["details"])

    md_without_symbols = tmp_path / "extract_without_symbols.md"
    md_without_symbols.write_text(
        "# Synthetic extracted process doc\n\nNo MATLAB symbol names are present here.\n",
        encoding="utf-8",
    )
    row_fail = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=md_without_symbols,
        python_path=python_path,
    )
    env_fail = _write_synthetic_env(
        tmp_path / "fail_case",
        row_payload=row_fail,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
    )
    result_fail = _run_l1b("--format", "json", env_overrides=env_fail)
    assert result_fail.returncode == 1
    report_fail = _json_report(result_fail)
    row_report_fail = _row_by_name(report_fail, "SyntheticProcess")
    check_1_fail = row_report_fail["checks"]["check_matlab_anchors_resolve"]
    assert check_1_fail["verdict"] == "FAIL"
    assert any("not found in derived-doc file" in detail for detail in check_1_fail["details"])


def test_synthetic_v2_row_passes_new_row_local_checks(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        method_map_payload=_stub_method_map(process_name="SyntheticProcess"),
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 0
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert report["aggregate"]["overall_verdict"] == "PASS"
    assert row_report["checks"]["check_schema_conformance"]["verdict"] == "PASS"
    assert row_report["checks"]["check_stoichiometry_oracle_matches"]["verdict"] == "PASS"
    assert row_report["checks"]["check_half_a_b_consistency"]["verdict"] == "PASS"
    assert row_report["checks"]["check_a_invariants"]["verdict"] == "PASS"


def test_synthetic_v2_row_missing_source_anchor_symbol_fails_schema_conformance(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )
    del row["integration_touchpoints"]["evolveState"]["oc"]["source"]["symbol"]
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        method_map_payload=_stub_method_map(process_name="SyntheticProcess"),
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 1
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert report["aggregate"]["overall_verdict"] == "FAIL"
    assert row_report["checks"]["check_schema_conformance"]["verdict"] == "FAIL"
    assert any("integration_touchpoints/evolveState/oc/source" in detail for detail in row_report["checks"]["check_schema_conformance"]["details"])


def test_synthetic_v2_row_wrong_oracle_count_fails_stoichiometry_check(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )
    row["stoichiometry_oracle"]["substrate_count"] = 99
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        method_map_payload=_stub_method_map(process_name="SyntheticProcess"),
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 1
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert report["aggregate"]["overall_verdict"] == "FAIL"
    assert row_report["checks"]["check_stoichiometry_oracle_matches"]["verdict"] == "FAIL"
    assert any("substrate_count mismatch" in detail for detail in row_report["checks"]["check_stoichiometry_oracle_matches"]["details"])


def test_synthetic_v2_row_drifted_oc_symbol_fails_half_a_b_consistency(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )
    row["integration_touchpoints"]["evolveState"]["oc"]["symbol"] = "drifted_symbol"
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        method_map_payload=_stub_method_map(process_name="SyntheticProcess"),
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 1
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert report["aggregate"]["overall_verdict"] == "FAIL"
    assert row_report["checks"]["check_half_a_b_consistency"]["verdict"] == "FAIL"
    assert any("Half A/B drift for evolveState" in detail for detail in row_report["checks"]["check_half_a_b_consistency"]["details"])


def test_synthetic_v2_row_a1_violation_fails_a_invariants(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )
    row["integration_touchpoints"]["calcResourceRequirements_Current"]["status"] = "not_implemented"
    row["allocator"]["request_formula"]["oc"] = "NOT_IMPLEMENTED"
    env = _write_synthetic_env(
        tmp_path,
        row_payload=row,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        method_map_payload=_stub_method_map(process_name="SyntheticProcess"),
    )

    result = _run_l1b("--format", "json", env_overrides=env)
    assert result.returncode == 1
    report = _json_report(result)
    row_report = _row_by_name(report, "SyntheticProcess")
    assert report["aggregate"]["overall_verdict"] == "FAIL"
    assert row_report["checks"]["check_a_invariants"]["verdict"] == "FAIL"
    assert any(detail.startswith("A1:") for detail in row_report["checks"]["check_a_invariants"]["details"])


def test_synthetic_v2_row_a1_noop_escape_is_scoped_to_oracle_none(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)
    base_row = _synthetic_row(
        process_name="SyntheticProcess",
        matlab_path=matlab_path,
        python_path=python_path,
    )

    row_none = copy.deepcopy(base_row)
    row_none["integration_touchpoints"]["calcResourceRequirements_Current"]["status"] = "not_implemented"
    row_none["stoichiometry_oracle"]["class"] = "none"
    row_none["stoichiometry_oracle"]["substrate_count"] = 0
    row_none["consume_stoichiometry"] = []
    row_none["produce_stoichiometry"] = []
    row_none["allocator"]["requests"] = []
    env_none = _write_synthetic_env(
        tmp_path / "oracle_none",
        row_payload=row_none,
        process_name="SyntheticProcess",
        state_groups={"substrates": [], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        method_map_payload=_stub_method_map(process_name="SyntheticProcess"),
    )

    result_none = _run_l1b("--format", "json", env_overrides=env_none)
    report_none = _json_report(result_none)
    row_report_none = _row_by_name(report_none, "SyntheticProcess")
    assert row_report_none["checks"]["check_a_invariants"]["verdict"] == "PASS"

    row_inline = copy.deepcopy(base_row)
    row_inline["integration_touchpoints"]["calcResourceRequirements_Current"]["status"] = "not_implemented"
    row_inline["stoichiometry_oracle"]["class"] = "inline"
    env_inline = _write_synthetic_env(
        tmp_path / "oracle_inline",
        row_payload=row_inline,
        process_name="SyntheticProcess",
        state_groups={"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        method_map_payload=_stub_method_map(process_name="SyntheticProcess"),
    )

    result_inline = _run_l1b("--format", "json", env_overrides=env_inline)
    report_inline = _json_report(result_inline)
    row_report_inline = _row_by_name(report_inline, "SyntheticProcess")
    assert row_report_inline["checks"]["check_a_invariants"]["verdict"] == "FAIL"
    assert any(detail.startswith("A1:") for detail in row_report_inline["checks"]["check_a_invariants"]["details"])


def test_dependency_symmetry_passes_then_fails(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)

    row_a = _synthetic_row(
        process_name="ProcessA",
        matlab_path=matlab_path,
        python_path=python_path,
        consume_wid="GLC",
        produce_wid="ATP",
        request_wid="GLC",
    )
    row_b = _synthetic_row(
        process_name="ProcessB",
        matlab_path=matlab_path,
        python_path=python_path,
        consume_wid="ATP",
        produce_wid="GLC",
        request_wid="ATP",
    )
    row_a["dependencies"]["produces_inputs_for"] = ["ProcessB"]
    row_b["dependencies"]["consumes_outputs_of"] = ["ProcessA"]

    env_pass = _write_synthetic_corpus_env(
        tmp_path / "pass_case",
        row_payloads=[row_a, row_b],
        state_groups_by_process={
            "ProcessA": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
            "ProcessB": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        },
        method_map_payload=_stub_method_map_many("ProcessA", "ProcessB"),
    )
    result_pass = _run_l1b("--format", "json", env_overrides=env_pass)
    assert result_pass.returncode == 0
    report_pass = _json_report(result_pass)
    assert _row_by_name(report_pass, "ProcessA")["checks"]["check_dependency_symmetry"]["verdict"] == "PASS"
    assert _row_by_name(report_pass, "ProcessB")["checks"]["check_dependency_symmetry"]["verdict"] == "PASS"

    row_b_fail = copy.deepcopy(row_b)
    row_b_fail["dependencies"]["consumes_outputs_of"] = []
    env_fail = _write_synthetic_corpus_env(
        tmp_path / "fail_case",
        row_payloads=[row_a, row_b_fail],
        state_groups_by_process={
            "ProcessA": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
            "ProcessB": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        },
        method_map_payload=_stub_method_map_many("ProcessA", "ProcessB"),
    )
    result_fail = _run_l1b("--format", "json", env_overrides=env_fail)
    assert result_fail.returncode == 1
    report_fail = _json_report(result_fail)
    row_a_fail = _row_by_name(report_fail, "ProcessA")
    assert row_a_fail["checks"]["check_dependency_symmetry"]["verdict"] == "FAIL"
    assert any(
        "ProcessA.produces_inputs_for -> ProcessB" in detail
        for detail in row_a_fail["checks"]["check_dependency_symmetry"]["details"]
    )


def test_orphan_consume_wids_fail_then_clear(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)

    row_a = _synthetic_row(
        process_name="ProcessA",
        matlab_path=matlab_path,
        python_path=python_path,
        consume_wid="X_orphan",
        produce_wid="ATP",
        request_wid="X_orphan",
    )
    row_b = _synthetic_row(
        process_name="ProcessB",
        matlab_path=matlab_path,
        python_path=python_path,
        consume_wid="ATP",
        produce_wid="GLC",
        request_wid="ATP",
    )

    env_fail = _write_synthetic_corpus_env(
        tmp_path / "fail_case",
        row_payloads=[row_a, row_b],
        state_groups_by_process={
            "ProcessA": {"substrates": ["X_orphan", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
            "ProcessB": {"substrates": ["GLC", "ATP", "X_orphan"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        },
        method_map_payload=_stub_method_map_many("ProcessA", "ProcessB"),
    )
    result_fail = _run_l1b("--format", "json", env_overrides=env_fail)
    assert result_fail.returncode == 1
    report_fail = _json_report(result_fail)
    row_a_fail = _row_by_name(report_fail, "ProcessA")
    assert row_a_fail["checks"]["check_orphan_consume_wids"]["verdict"] == "FAIL"
    assert any("X_orphan" in detail for detail in row_a_fail["checks"]["check_orphan_consume_wids"]["details"])

    row_b_clear = copy.deepcopy(row_b)
    row_b_clear["produce_stoichiometry"][0]["wid"] = "X_orphan"
    env_pass = _write_synthetic_corpus_env(
        tmp_path / "pass_case",
        row_payloads=[row_a, row_b_clear],
        state_groups_by_process={
            "ProcessA": {"substrates": ["X_orphan", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
            "ProcessB": {"substrates": ["GLC", "ATP", "X_orphan"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        },
        method_map_payload=_stub_method_map_many("ProcessA", "ProcessB"),
    )
    result_pass = _run_l1b("--format", "json", env_overrides=env_pass)
    assert result_pass.returncode == 0
    report_pass = _json_report(result_pass)
    row_a_pass = _row_by_name(report_pass, "ProcessA")
    assert row_a_pass["checks"]["check_orphan_consume_wids"]["verdict"] == "PASS"


def test_dependency_cycle_fails_then_passes(tmp_path: Path) -> None:
    matlab_path = tmp_path / "synthetic.m"
    python_path = tmp_path / "synthetic.py"
    _make_matlab_file(matlab_path)
    _make_python_file(python_path)

    row_a = _synthetic_row(
        process_name="ProcessA",
        matlab_path=matlab_path,
        python_path=python_path,
        consume_wid="GLC",
        produce_wid="ATP",
        request_wid="GLC",
    )
    row_b = _synthetic_row(
        process_name="ProcessB",
        matlab_path=matlab_path,
        python_path=python_path,
        consume_wid="ATP",
        produce_wid="GLC",
        request_wid="ATP",
    )
    row_a["dependencies"] = {
        "produces_inputs_for": ["ProcessB"],
        "consumes_outputs_of": ["ProcessB"],
    }
    row_b["dependencies"] = {
        "produces_inputs_for": ["ProcessA"],
        "consumes_outputs_of": ["ProcessA"],
    }

    env_fail = _write_synthetic_corpus_env(
        tmp_path / "fail_case",
        row_payloads=[row_a, row_b],
        state_groups_by_process={
            "ProcessA": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
            "ProcessB": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        },
        method_map_payload=_stub_method_map_many("ProcessA", "ProcessB"),
    )
    result_fail = _run_l1b("--format", "json", env_overrides=env_fail)
    assert result_fail.returncode == 1
    report_fail = _json_report(result_fail)
    graph_fail = report_fail["aggregate"]["graph_checks"]["no_dependency_cycles"]
    assert graph_fail["verdict"] == "FAIL"
    assert ["ProcessA", "ProcessB", "ProcessA"] in graph_fail["cycles"]

    row_b_pass = copy.deepcopy(row_b)
    row_b_pass["dependencies"] = {
        "produces_inputs_for": [],
        "consumes_outputs_of": ["ProcessA"],
    }
    row_a_pass = copy.deepcopy(row_a)
    row_a_pass["dependencies"] = {
        "produces_inputs_for": ["ProcessB"],
        "consumes_outputs_of": [],
    }
    env_pass = _write_synthetic_corpus_env(
        tmp_path / "pass_case",
        row_payloads=[row_a_pass, row_b_pass],
        state_groups_by_process={
            "ProcessA": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
            "ProcessB": {"substrates": ["GLC", "ATP"], "enzymes": [], "monomers": [], "complexs": [], "rnas": []},
        },
        method_map_payload=_stub_method_map_many("ProcessA", "ProcessB"),
    )
    result_pass = _run_l1b("--format", "json", env_overrides=env_pass)
    assert result_pass.returncode == 0
    report_pass = _json_report(result_pass)
    graph_pass = report_pass["aggregate"]["graph_checks"]["no_dependency_cycles"]
    assert graph_pass["verdict"] == "PASS"
    assert graph_pass["cycles"] == []
