#!/usr/bin/env python3
"""Build the per-process wiring DB and run cross-row consistency checks."""

from __future__ import annotations

import argparse
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
DEFAULT_OUT = DEFAULT_SOURCE_DIR / "_combined.yaml"
CANONICAL_MANIFEST = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "manifest.json"

TOP_LEVEL_REQUIRED_KEYS = (
    "schema_version",
    "schema_date",
    "process",
    "methods",
    "allocator",
    "consume_stoichiometry",
    "produce_stoichiometry",
    "compartment_routing",
    "unit_conversion_chain",
    "dependencies",
    "ordering_constraints",
    "source_anchors",
    "provenance",
    "deviations",
)
PROCESS_REQUIRED_KEYS = (
    "name",
    "matlab_class",
    "matlab_file",
    "oc_class",
    "oc_file",
    "whole_cell_model_id",
)
METHOD_REQUIRED_NAMES = (
    "calcResourceRequirements_Current",
    "evolveState",
    "calcFluxBounds",
)
METHOD_STATUS_VALUES = {"implemented", "partial", "not_implemented"}
COMPARTMENT_VALUES = {"cytosol", "extracellular", "membrane"}
TUPLE_ENTRY_SOURCES = {"karr", "oc", "both", "deviation"}
VERSION_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINES_RE = re.compile(r"^\d+-\d+$")


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _format_process_name(row: dict[str, Any], fallback: str) -> str:
    process = row.get("process")
    if isinstance(process, dict):
        name = process.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback


def _parse_version(value: str) -> tuple[int, int] | None:
    match = VERSION_RE.fullmatch(str(value).strip())
    if not match:
        return None
    return int(match.group("major")), int(match.group("minor"))


def _is_version_compatible(schema_version: str, row_version: str) -> bool:
    schema_parsed = _parse_version(schema_version)
    row_parsed = _parse_version(row_version)
    if schema_parsed is None or row_parsed is None:
        return False
    schema_major, schema_minor = schema_parsed
    row_major, row_minor = row_parsed
    return schema_major == row_major and row_minor <= schema_minor


def _source_anchor_errors(anchor: Any, label: str, *, require_symbol: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(anchor, dict):
        return [f"{label}: expected mapping"]

    for key in ("path", "lines", "note"):
        value = anchor.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: missing or invalid {key}")

    lines = anchor.get("lines")
    if isinstance(lines, str) and not LINES_RE.fullmatch(lines):
        errors.append(f"{label}: lines must match start-end")

    if "symbol" in anchor and require_symbol:
        symbol = anchor.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            errors.append(f"{label}: missing or invalid symbol")
    elif require_symbol:
        errors.append(f"{label}: missing symbol")

    return errors


def _validate_tuple_entry(entry: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(entry, dict):
        return [f"{label}: expected mapping"]
    for key in ("wid", "compartment", "source", "note"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: missing or invalid {key}")
    compartment = entry.get("compartment")
    if isinstance(compartment, str) and compartment not in COMPARTMENT_VALUES:
        errors.append(f"{label}: invalid compartment {compartment!r}")
    source = entry.get("source")
    if isinstance(source, str) and source not in TUPLE_ENTRY_SOURCES:
        errors.append(f"{label}: invalid source {source!r}")
    return errors


def _validate_stoich_entry(entry: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(entry, dict):
        return [f"{label}: expected mapping"]
    for key in ("wid", "compartment", "formula_or_constant"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: missing or invalid {key}")
    compartment = entry.get("compartment")
    if isinstance(compartment, str) and compartment not in COMPARTMENT_VALUES:
        errors.append(f"{label}: invalid compartment {compartment!r}")
    errors.extend(_source_anchor_errors(entry.get("matlab_anchor"), f"{label}.matlab_anchor"))
    errors.extend(_source_anchor_errors(entry.get("oc_anchor"), f"{label}.oc_anchor"))
    return errors


def _validate_conversion_step(step: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(step, dict):
        return [f"{label}: expected mapping"]
    for key in ("from_units", "to_units", "operation"):
        value = step.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: missing or invalid {key}")
    errors.extend(_source_anchor_errors(step.get("anchor"), f"{label}.anchor"))
    return errors


def _validate_method_binding(name: str, binding: Any) -> list[str]:
    errors: list[str] = []
    label = f"methods.{name}"
    if not isinstance(binding, dict):
        return [f"{label}: expected mapping"]

    for key in ("matlab", "oc", "status"):
        if key not in binding:
            errors.append(f"{label}: missing {key}")

    status = binding.get("status")
    if isinstance(status, str) and status not in METHOD_STATUS_VALUES:
        errors.append(f"{label}: invalid status {status!r}")

    matlab = binding.get("matlab")
    if not isinstance(matlab, dict):
        errors.append(f"{label}.matlab: expected mapping")
    else:
        matlab_symbol = matlab.get("symbol")
        if not isinstance(matlab_symbol, str) or not matlab_symbol.strip():
            errors.append(f"{label}.matlab: missing or invalid symbol")
        errors.extend(_source_anchor_errors(matlab.get("source"), f"{label}.matlab.source"))

    oc = binding.get("oc")
    if not isinstance(oc, dict):
        errors.append(f"{label}.oc: expected mapping")
    else:
        oc_symbol = oc.get("symbol")
        if not isinstance(oc_symbol, str) or not oc_symbol.strip():
            errors.append(f"{label}.oc: missing or invalid symbol")
        errors.extend(_source_anchor_errors(oc.get("source"), f"{label}.oc.source"))
        supporting = oc.get("supporting")
        if supporting is not None:
            if not isinstance(supporting, list):
                errors.append(f"{label}.oc.supporting: expected list")
            else:
                for idx, anchor in enumerate(supporting):
                    errors.extend(_source_anchor_errors(anchor, f"{label}.oc.supporting[{idx}]"))

    return errors


def _validate_row(row: Any, schema_version: str, row_path: Path) -> tuple[str, list[str]]:
    errors: list[str] = []
    fallback_name = row_path.stem
    if not isinstance(row, dict):
        return fallback_name, [f"{row_path.name}: expected mapping"]

    process_name = _format_process_name(row, fallback_name)
    missing_top = [key for key in TOP_LEVEL_REQUIRED_KEYS if key not in row]
    if missing_top:
        errors.append(f"missing top-level keys: {', '.join(missing_top)}")

    row_schema_version = row.get("schema_version")
    if not isinstance(row_schema_version, str) or not row_schema_version.strip():
        errors.append("schema_version missing or invalid")
    elif not _is_version_compatible(schema_version, row_schema_version):
        errors.append(f"schema_version {row_schema_version!r} incompatible with schema {schema_version!r}")

    row_schema_date = row.get("schema_date")
    if not isinstance(row_schema_date, str) or not DATE_RE.fullmatch(row_schema_date):
        errors.append("schema_date missing or not YYYY-MM-DD")

    process = row.get("process")
    if not isinstance(process, dict):
        errors.append("process: expected mapping")
    else:
        missing_process = [key for key in PROCESS_REQUIRED_KEYS if key not in process]
        if missing_process:
            errors.append(f"process missing keys: {', '.join(missing_process)}")
        process_name_value = process.get("name")
        if isinstance(process_name_value, str) and process_name_value.strip():
            process_name = process_name_value.strip()

    methods = row.get("methods")
    if not isinstance(methods, dict):
        errors.append("methods: expected mapping")
    else:
        missing_methods = [key for key in METHOD_REQUIRED_NAMES if key not in methods]
        if missing_methods:
            errors.append(f"methods missing required bindings: {', '.join(missing_methods)}")
        for method_name in METHOD_REQUIRED_NAMES:
            if method_name in methods:
                errors.extend(_validate_method_binding(method_name, methods[method_name]))

    allocator = row.get("allocator")
    if not isinstance(allocator, dict):
        errors.append("allocator: expected mapping")
    else:
        for key in ("mode", "request_formula", "requests", "bypasses"):
            if key not in allocator:
                errors.append(f"allocator missing {key}")
        mode = allocator.get("mode")
        if not isinstance(mode, dict):
            errors.append("allocator.mode: expected mapping")
        else:
            for key in ("karr", "oc_current"):
                value = mode.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"allocator.mode: missing or invalid {key}")
        request_formula = allocator.get("request_formula")
        if not isinstance(request_formula, dict):
            errors.append("allocator.request_formula: expected mapping")
        else:
            for key in ("matlab", "oc"):
                value = request_formula.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"allocator.request_formula: missing or invalid {key}")
        for list_key in ("requests", "bypasses"):
            entries = allocator.get(list_key)
            if not isinstance(entries, list):
                errors.append(f"allocator.{list_key}: expected list")
            else:
                for idx, entry in enumerate(entries):
                    errors.extend(_validate_tuple_entry(entry, f"allocator.{list_key}[{idx}]"))

    for list_key in ("consume_stoichiometry", "produce_stoichiometry"):
        entries = row.get(list_key)
        if not isinstance(entries, list):
            errors.append(f"{list_key}: expected list")
        else:
            for idx, entry in enumerate(entries):
                errors.extend(_validate_stoich_entry(entry, f"{list_key}[{idx}]"))

    compartment_routing = row.get("compartment_routing")
    if not isinstance(compartment_routing, list):
        errors.append("compartment_routing: expected list")
    else:
        for idx, entry in enumerate(compartment_routing):
            label = f"compartment_routing[{idx}]"
            if not isinstance(entry, dict):
                errors.append(f"{label}: expected mapping")
                continue
            wid = entry.get("wid")
            if not isinstance(wid, str) or not wid.strip():
                errors.append(f"{label}: missing or invalid wid")
            for key in ("consume_compartment", "produce_compartment"):
                value = entry.get(key)
                if value is not None and (not isinstance(value, str) or value not in COMPARTMENT_VALUES):
                    errors.append(f"{label}: invalid {key}")
            mismatch = entry.get("mismatch")
            if not isinstance(mismatch, bool):
                errors.append(f"{label}: mismatch must be boolean")
            consume = entry.get("consume_compartment")
            produce = entry.get("produce_compartment")
            if isinstance(consume, str) and isinstance(produce, str):
                expected = consume != produce
                if mismatch != expected:
                    errors.append(
                        f"{label}: mismatch={mismatch!r} does not match compartments {consume!r}/{produce!r}"
                    )
            note = entry.get("note")
            if not isinstance(note, str) or not note.strip():
                errors.append(f"{label}: missing or invalid note")

    unit_conversion_chain = row.get("unit_conversion_chain")
    if not isinstance(unit_conversion_chain, dict):
        errors.append("unit_conversion_chain: expected mapping")
    else:
        for key in ("source_units", "target_units", "steps"):
            if key not in unit_conversion_chain:
                errors.append(f"unit_conversion_chain missing {key}")
        for key in ("source_units", "target_units"):
            value = unit_conversion_chain.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"unit_conversion_chain.{key}: missing or invalid")
        steps = unit_conversion_chain.get("steps")
        if not isinstance(steps, list):
            errors.append("unit_conversion_chain.steps: expected list")
        else:
            for idx, step in enumerate(steps):
                errors.extend(_validate_conversion_step(step, f"unit_conversion_chain.steps[{idx}]"))

    dependencies = row.get("dependencies")
    if not isinstance(dependencies, dict):
        errors.append("dependencies: expected mapping")
    else:
        for key in ("produces_inputs_for", "consumes_outputs_of"):
            value = dependencies.get(key)
            if not isinstance(value, list):
                errors.append(f"dependencies.{key}: expected list")
        note = dependencies.get("note")
        if note is not None and not isinstance(note, str):
            errors.append("dependencies.note: must be string if present")

    ordering_constraints = row.get("ordering_constraints")
    if not isinstance(ordering_constraints, dict):
        errors.append("ordering_constraints: expected mapping")
    else:
        for key in ("hard_before", "hard_after", "soft_before", "soft_after"):
            value = ordering_constraints.get(key)
            if not isinstance(value, list):
                errors.append(f"ordering_constraints.{key}: expected list")
        note = ordering_constraints.get("note")
        if note is not None and not isinstance(note, str):
            errors.append("ordering_constraints.note: must be string if present")

    source_anchors = row.get("source_anchors")
    if not isinstance(source_anchors, dict):
        errors.append("source_anchors: expected mapping")
    else:
        for block_key in ("matlab_blocks", "oc_blocks"):
            blocks = source_anchors.get(block_key)
            if not isinstance(blocks, dict):
                errors.append(f"source_anchors.{block_key}: expected mapping")
            else:
                for block_name, anchor in blocks.items():
                    errors.extend(_source_anchor_errors(anchor, f"source_anchors.{block_key}.{block_name}"))

    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance: expected mapping")
    else:
        last_audited = provenance.get("last_audited")
        if not isinstance(last_audited, str) or not DATE_RE.fullmatch(last_audited):
            errors.append("provenance.last_audited missing or not YYYY-MM-DD")
        for key in ("matlab_files_referenced", "oc_files_referenced"):
            value = provenance.get(key)
            if not isinstance(value, list) or not value:
                errors.append(f"provenance.{key}: expected non-empty list")
            elif not all(isinstance(item, str) and item.strip() for item in value):
                errors.append(f"provenance.{key}: must contain only non-empty strings")

    deviations = row.get("deviations")
    if not isinstance(deviations, dict):
        errors.append("deviations: expected mapping")
    else:
        lp_bounds_source = deviations.get("lp_bounds_source")
        if not isinstance(lp_bounds_source, dict):
            errors.append("deviations.lp_bounds_source: expected mapping")
        else:
            for key in ("karr", "oc_current"):
                value = lp_bounds_source.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"deviations.lp_bounds_source: missing or invalid {key}")
            errors.extend(
                _source_anchor_errors(lp_bounds_source.get("matlab_anchor"), "deviations.lp_bounds_source.matlab_anchor")
            )
            errors.extend(
                _source_anchor_errors(lp_bounds_source.get("oc_anchor"), "deviations.lp_bounds_source.oc_anchor")
            )
        if not isinstance(deviations.get("shared_pool_projection_merges_compartments"), bool):
            errors.append("deviations.shared_pool_projection_merges_compartments: expected boolean")
        known_deviations = deviations.get("known_deviations")
        if not isinstance(known_deviations, list):
            errors.append("deviations.known_deviations: expected list")
        elif not all(isinstance(item, str) for item in known_deviations):
            errors.append("deviations.known_deviations: must contain strings")
        note = deviations.get("note")
        if note is not None and not isinstance(note, str):
            errors.append("deviations.note: must be string if present")

    return process_name, errors


def _load_canonical_processes() -> list[str]:
    payload = _load_yaml(CANONICAL_MANIFEST)
    fixtures = payload.get("fixtures", []) if isinstance(payload, dict) else []
    names = [str(entry["name"]) for entry in fixtures if isinstance(entry, dict) and entry.get("kind") == "process" and entry.get("name")]
    unique_names = sorted(dict.fromkeys(names))
    return unique_names


def _load_rows(source_dir: Path, schema_version: str) -> tuple[list[dict[str, Any]], list[tuple[str, list[str]]]]:
    rows: list[dict[str, Any]] = []
    failures: list[tuple[str, list[str]]] = []
    for row_path in sorted(p for p in source_dir.glob("*.yaml") if not p.name.startswith("_")):
        try:
            payload = _load_yaml(row_path)
        except Exception as exc:  # pragma: no cover - exercised through CLI
            failures.append((row_path.stem, [f"YAML parse error: {exc}"]))
            continue
        process_name, errors = _validate_row(payload, schema_version, row_path)
        if errors:
            failures.append((process_name, errors))
        if isinstance(payload, dict):
            rows.append(payload)
    rows.sort(key=lambda item: _format_process_name(item, ""))
    return rows, failures


def _cross_row_checks(rows: list[dict[str, Any]], canonical_processes: list[str]) -> tuple[list[str], list[str], list[str]]:
    reciprocal_mismatches: list[str] = []
    cyclic_ordering: list[str] = []
    missing_rows: list[str] = []

    rows_by_name = {name: row for name, row in ((_format_process_name(row, f"row-{idx}"), row) for idx, row in enumerate(rows))}

    for process_name, row in rows_by_name.items():
        dependencies = row.get("dependencies") if isinstance(row, dict) else None
        produces = dependencies.get("produces_inputs_for", []) if isinstance(dependencies, dict) else []
        for consumer_name in produces:
            if not isinstance(consumer_name, str) or not consumer_name.strip():
                continue
            consumer = rows_by_name.get(consumer_name)
            if consumer is None:
                reciprocal_mismatches.append(
                    f"[CROSS] reciprocal mismatch: {process_name} -> {consumer_name} (consumer row missing)"
                )
                continue
            consumer_deps = consumer.get("dependencies") if isinstance(consumer, dict) else None
            consumer_note = ""
            if isinstance(consumer_deps, dict) and isinstance(consumer_deps.get("note"), str):
                consumer_note = consumer_deps["note"].lower()
            if "intentionally" in consumer_note or "asymmetry" in consumer_note:
                continue
            reciprocal = consumer_deps.get("consumes_outputs_of", []) if isinstance(consumer_deps, dict) else []
            if process_name not in reciprocal:
                reciprocal_mismatches.append(
                    f"[CROSS] reciprocal mismatch: {process_name} -> {consumer_name} (missing consumes_outputs_of back-edge)"
                )

    for process_name, row in rows_by_name.items():
        ordering = row.get("ordering_constraints") if isinstance(row, dict) else None
        hard_before = ordering.get("hard_before", []) if isinstance(ordering, dict) else []
        for later_name in hard_before:
            if not isinstance(later_name, str) or not later_name.strip():
                continue
            later = rows_by_name.get(later_name)
            if later is None:
                continue
            later_order = later.get("ordering_constraints") if isinstance(later, dict) else None
            later_hard_before = later_order.get("hard_before", []) if isinstance(later_order, dict) else []
            if process_name in later_hard_before:
                cyclic_ordering.append(
                    f"[CROSS] cyclic ordering: {process_name} hard_before {later_name} and {later_name} hard_before {process_name}"
                )

    present = set(rows_by_name)
    missing_rows = [name for name in canonical_processes if name not in present]
    return reciprocal_mismatches, cyclic_ordering, missing_rows


def _emit_combined_yaml(
    out_path: Path,
    rows: list[dict[str, Any]],
    *,
    schema_version: str,
    schema_date: str,
    validation_status: str,
    row_failures: int,
    cross_failures: int,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    commit_result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = commit_result.stdout.strip() if commit_result.returncode == 0 and commit_result.stdout.strip() else "unknown"
    payload = {
        "metadata": {
            "generated_at": generated_at,
            "generator_commit": commit,
            "schema_version": schema_version,
            "schema_date": schema_date,
            "row_count": len(rows),
            "validation_status": validation_status,
        },
        "processes": rows,
    }
    header = [
        "# AUTOGENERATED by scripts/build_wiring_db.py - DO NOT EDIT",
        "# Source files: data/schemas/per_process_wiring/*.yaml (excluding _*.yaml)",
        f"# Generated:    {generated_at}",
        f"# Generator commit: {commit}",
        f"# Schema version:   {schema_version}",
        f"# Validation:       {validation_status} ({row_failures} row failures, {cross_failures} cross-row failures)",
        "",
    ]
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(header))
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate inputs without writing the combined file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path to the generated combined YAML file.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing per-process wiring rows and _schema.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_dir = args.source_dir
    schema_path = source_dir / "_schema.yaml"
    if not schema_path.exists():
        print(f"[FAIL schema] missing schema file: {schema_path}")
        return 1

    schema_payload = _load_yaml(schema_path)
    if not isinstance(schema_payload, dict):
        print(f"[FAIL schema] {schema_path} did not parse to a mapping")
        return 1

    schema_version = str(schema_payload.get("schema_version", "")).strip()
    if not schema_version:
        print(f"[FAIL schema] {schema_path} missing schema_version")
        return 1

    schema_date = schema_payload.get("schema_date")
    if not isinstance(schema_date, str) or not DATE_RE.fullmatch(schema_date):
        schema_date = datetime.now(timezone.utc).date().isoformat()

    rows, row_failures = _load_rows(source_dir, schema_version)
    canonical_processes = _load_canonical_processes()
    reciprocal_mismatches, cyclic_ordering, missing_rows = _cross_row_checks(rows, canonical_processes)

    for process_name, reasons in row_failures:
        print(f"[FAIL row={process_name}] {'; '.join(reasons)}")

    cross_failures = len(reciprocal_mismatches) + len(cyclic_ordering) + len(missing_rows)
    for message in reciprocal_mismatches:
        print(message)
    for message in cyclic_ordering:
        print(message)
    if missing_rows:
        print(f"[CROSS] missing canonical rows: {', '.join(missing_rows)}")
    print(f"[CROSS] {len(reciprocal_mismatches)} reciprocal mismatches, {len(cyclic_ordering)} cyclic ordering, {len(missing_rows)} missing rows")

    validation_status = "PASS" if not row_failures and cross_failures == 0 else "FAIL"

    if not args.validate_only:
        _emit_combined_yaml(
            args.out,
            rows,
            schema_version=schema_version,
            schema_date=schema_date,
            validation_status=validation_status,
            row_failures=len(row_failures),
            cross_failures=cross_failures,
        )
        print(f"[WRITE] {args.out}")

    print(validation_status)
    return 0 if validation_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
