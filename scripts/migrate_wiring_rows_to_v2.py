#!/usr/bin/env python3
"""Deterministically migrate per-process wiring rows from schema v1 to v2."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WIRING_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
STOICH_ORACLE_DIR = REPO_ROOT / "data" / "karr_method_inventory" / "karr_stoichiometry"
SCHEMA_VERSION = "2.0"
SCHEMA_DATE = "2026-07-07"
REQUIRED_TOUCHPOINTS = (
    "calcResourceRequirements_Current",
    "evolveState",
    "calcFluxBounds",
)
ORACLE_NOTE = (
    "Exhaustive per-tick substrate set lives in the HB1 oracle; this row's "
    "consume/produce arrays carry integration-relevant hand-curated entries."
)
TOP_LEVEL_ORDER = (
    "schema_version",
    "schema_date",
    "process",
    "integration_touchpoints",
    "allocator",
    "consume_stoichiometry",
    "produce_stoichiometry",
    "stoichiometry_oracle",
    "compartment_routing",
    "unit_conversion_chain",
    "dependencies",
    "ordering_constraints",
    "source_anchors",
    "provenance",
    "deviations",
)
PER_FLUX_RE = re.compile(r"flux", re.IGNORECASE)
PER_REACTION_RE = re.compile(r"(reaction|rxn|\[i\]|_i\b)", re.IGNORECASE)
DOC_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
TEXT_DOC_SUFFIXES = {".md", ".txt", ".rst"}
MATLAB_FUNCTION_RE = re.compile(
    r"^\s*function\b(?:\s+\[[^\]]*\]\s*=\s*|\s+[A-Za-z_]\w*\s*=\s*)?(?P<name>[A-Za-z_]\w*)\b"
)
MATLAB_CLASSDEF_RE = re.compile(
    r"^\s*classdef\b(?:\s*\([^)]+\))?\s+(?P<name>[A-Za-z_]\w*)\b"
)

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
except ImportError:  # pragma: no cover - exercised only when ruamel is absent
    YAML = None
    CommentedMap = dict


def _load_verifier_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "l1b_verify_wiring",
        REPO_ROOT / "scripts" / "l1b_verify_wiring.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load scripts/l1b_verify_wiring.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = _load_verifier_module()


def _mapping() -> Any:
    return CommentedMap() if YAML is not None else {}


def _is_non_empty_symbol(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _load_yaml_document(path: Path) -> tuple[Any, str]:
    text = path.read_text(encoding="utf-8")
    if YAML is None:
        return yaml.safe_load(text), "pyyaml"
    parser = YAML()
    parser.preserve_quotes = True
    return parser.load(text), "ruamel"


def _write_yaml_document(path: Path, payload: Any, backend: str) -> None:
    if backend == "ruamel" and YAML is not None:
        emitter = YAML()
        emitter.preserve_quotes = True
        emitter.width = 4096
        emitter.indent(mapping=2, sequence=4, offset=2)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            emitter.dump(payload, handle)
        return

    dumped = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    path.write_text(dumped, encoding="utf-8", newline="\n")


def _process_name(row: dict[str, Any], fallback: str) -> str:
    process = row.get("process")
    if isinstance(process, dict):
        name = process.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback


def _json_path(parent: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    if not parent:
        return str(key)
    return f"{parent}.{key}"


def _resolve_source_path(anchor_path: str) -> Path:
    normalized = anchor_path.replace("\\", "/")
    if normalized.lower().endswith(".m") or normalized.lower().startswith("e:/opencell-mirrors/"):
        resolved, _ = VERIFY._resolve_matlab_anchor_path(anchor_path, REPO_ROOT)
        return resolved
    return VERIFY._resolve_anchor_path(anchor_path, REPO_ROOT)


def _extract_python_symbol(cache: Any, resolved: Path, start_line: int) -> str | None:
    occurrences, error = cache.symbols(resolved)
    if error is not None or occurrences is None:
        return None
    containing = [
        item
        for item in occurrences
        if item.start_line <= start_line <= item.end_line
    ]
    if not containing:
        return "<module>"
    innermost = min(
        containing,
        key=lambda item: (item.end_line - item.start_line, -item.start_line),
    )
    return innermost.full_name


def _extract_matlab_symbol(cache: Any, resolved: Path, start_line: int) -> str | None:
    lines = cache.lines(resolved)
    if start_line <= 0 or start_line > len(lines):
        return None

    class_name: str | None = None
    function_headers: list[tuple[int, str]] = []
    for line_number, line_text in enumerate(lines, start=1):
        if class_name is None:
            class_match = MATLAB_CLASSDEF_RE.match(line_text)
            if class_match is not None:
                class_name = class_match.group("name")
        function_match = MATLAB_FUNCTION_RE.match(line_text)
        if function_match is not None:
            function_headers.append((line_number, function_match.group("name")))

    eligible = [item for item in function_headers if item[0] <= start_line]
    if eligible:
        return eligible[-1][1]
    return class_name


def _extract_doc_heading_symbol(cache: Any, resolved: Path, start_line: int) -> str:
    lines = cache.lines(resolved)
    if not lines:
        return resolved.stem

    search_end = min(max(start_line, 1), len(lines))
    for line_number in range(search_end, 0, -1):
        match = DOC_HEADING_RE.match(lines[line_number - 1])
        if match is not None:
            heading = match.group(1).strip()
            if heading:
                return heading
    return resolved.stem


def _extract_symbol_from_anchor(anchor: Any, cache: Any) -> str | None:
    anchor_path = anchor.get("path")
    lines_text = anchor.get("lines")
    if not isinstance(anchor_path, str) or not isinstance(lines_text, str):
        return None

    span = VERIFY._parse_line_span(lines_text)
    if span is None:
        return None

    resolved = _resolve_source_path(anchor_path)
    if not resolved.exists():
        return None

    start_line, _ = span
    suffix = resolved.suffix.lower()
    if suffix == ".py":
        return _extract_python_symbol(cache, resolved, start_line)
    if suffix == ".m":
        return _extract_matlab_symbol(cache, resolved, start_line)
    if suffix in TEXT_DOC_SUFFIXES:
        return _extract_doc_heading_symbol(cache, resolved, start_line)
    return None


def _classify_kind(formula_or_constant: Any) -> str:
    text = str(formula_or_constant).strip()
    try:
        float(text)
        return "constant"
    except ValueError:
        pass
    if PER_FLUX_RE.search(text):
        return "per_flux"
    if PER_REACTION_RE.search(text):
        return "per_reaction"
    return "expression"


def _strip_v1_escape_hatch(notes: Any) -> tuple[Any, bool]:
    if not isinstance(notes, str):
        return notes, False

    lowered = notes.lower()
    if "example shape" not in lowered and "not a full" not in lowered:
        return notes, False

    pieces = re.split(r"(?<=[.?!])\s+", notes.strip())
    kept = [
        piece
        for piece in pieces
        if "example shape" not in piece.lower() and "not a full" not in piece.lower()
    ]
    if kept:
        return " ".join(kept).strip(), True
    return "", True


def _build_oracle_block(process_name: str) -> tuple[dict[str, Any] | None, str | None]:
    record_path = STOICH_ORACLE_DIR / f"{process_name}.json"
    if not record_path.exists():
        return None, f"missing stoichiometry oracle record {record_path.relative_to(REPO_ROOT).as_posix()}"

    record = json.loads(record_path.read_text(encoding="utf-8"))
    substrates = record.get("substrates", [])
    substrate_count = record.get("n_substrates", len(substrates))
    return {
        "class": record["class"],
        "record_path": f"data/karr_method_inventory/karr_stoichiometry/{process_name}.json",
        "substrate_count": substrate_count,
        "note": ORACLE_NOTE,
    }, None


def _canonicalize_touchpoints(methods: Any) -> tuple[Any | None, list[str]]:
    if not isinstance(methods, dict):
        return None, []
    missing = [name for name in REQUIRED_TOUCHPOINTS if name not in methods]
    if missing:
        return None, missing

    touchpoints = _mapping()
    for name in REQUIRED_TOUCHPOINTS:
        touchpoints[name] = methods[name]
    return touchpoints, []


def _reorder_top_level(row: Any, touchpoints: Any) -> Any:
    ordered = _mapping()
    row_copy = dict(row)
    row_copy.pop("methods", None)
    row_copy["integration_touchpoints"] = touchpoints

    for key in TOP_LEVEL_ORDER:
        if key in row_copy:
            ordered[key] = row_copy[key]

    for key, value in row_copy.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _fill_method_source_shortcuts(
    touchpoints: Any,
    *,
    row_report: dict[str, Any],
) -> None:
    for method_name in REQUIRED_TOUCHPOINTS:
        binding = touchpoints.get(method_name)
        if not isinstance(binding, dict):
            continue
        for side in ("matlab", "oc"):
            side_block = binding.get(side)
            if not isinstance(side_block, dict):
                continue
            source = side_block.get("source")
            parent_symbol = side_block.get("symbol")
            if not isinstance(source, dict):
                continue
            if _is_non_empty_symbol(source.get("symbol")):
                row_report["preserved_symbols"] += 1
                continue
            if _is_non_empty_symbol(parent_symbol):
                source["symbol"] = parent_symbol
                row_report["copy_parent_fills"] += 1
                row_report["copy_parent_paths"].append(
                    f"integration_touchpoints.{method_name}.{side}.source"
                )


def _fill_anchor_symbols_recursive(
    node: Any,
    *,
    json_path: str,
    process_name: str,
    cache: Any,
    row_report: dict[str, Any],
) -> None:
    if isinstance(node, dict):
        if "path" in node and "lines" in node:
            if _is_non_empty_symbol(node.get("symbol")):
                if json_path not in row_report["copy_parent_paths"]:
                    row_report["preserved_symbols"] += 1
            else:
                extracted = _extract_symbol_from_anchor(node, cache)
                if extracted is not None:
                    node["symbol"] = extracted
                    row_report["source_extract_fills"] += 1
                    row_report["source_extract_paths"].append(json_path)
                else:
                    row_report["unresolved"].append(
                        {
                            "process": process_name,
                            "json_path": json_path,
                            "anchor_path": node.get("path"),
                            "lines": node.get("lines"),
                        }
                    )
            return

        for key, value in node.items():
            _fill_anchor_symbols_recursive(
                value,
                json_path=_json_path(json_path, key),
                process_name=process_name,
                cache=cache,
                row_report=row_report,
            )
        return

    if isinstance(node, list):
        for index, value in enumerate(node):
            _fill_anchor_symbols_recursive(
                value,
                json_path=_json_path(json_path, index),
                process_name=process_name,
                cache=cache,
                row_report=row_report,
            )


def _apply_kind_tags(row: Any, row_report: dict[str, Any]) -> None:
    counts = {
        "constant": 0,
        "per_reaction": 0,
        "per_flux": 0,
        "expression": 0,
    }
    for key in ("consume_stoichiometry", "produce_stoichiometry"):
        entries = row.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            kind = _classify_kind(entry.get("formula_or_constant", ""))
            entry["kind"] = kind
            counts[kind] += 1
    row_report["stoich_kind_counts"] = counts


def _migrate_row(row_path: Path, *, dry_run: bool, yaml_backend: str) -> dict[str, Any]:
    row, _ = _load_yaml_document(row_path)
    if not isinstance(row, dict):
        raise TypeError(f"{row_path.name} did not parse as a mapping")

    process_name = _process_name(row, row_path.stem)
    row_report: dict[str, Any] = {
        "process": process_name,
        "file": row_path.name,
        "status": "migrated",
        "blocked": [],
        "copy_parent_fills": 0,
        "copy_parent_paths": [],
        "source_extract_fills": 0,
        "source_extract_paths": [],
        "preserved_symbols": 0,
        "unresolved": [],
        "dropped_methods": [],
        "oracle_added": False,
        "notes_changed": False,
        "stoich_kind_counts": {},
        "yaml_backend": yaml_backend,
        "written": False,
    }

    if row_path.name in {"Metabolism.yaml", "_schema.yaml"} or row_path.name.startswith("_"):
        row_report["status"] = "skipped"
        return row_report

    if str(row.get("schema_version", "")).strip() == SCHEMA_VERSION:
        row_report["status"] = "already_v2"
        return row_report

    methods = row.get("methods")
    touchpoints, missing = _canonicalize_touchpoints(methods)
    if missing:
        row_report["status"] = "blocked"
        row_report["blocked"].append(
            f"missing required touchpoints: {', '.join(missing)}"
        )
        return row_report

    if isinstance(methods, dict):
        row_report["dropped_methods"] = [
            key for key in methods.keys() if key not in REQUIRED_TOUCHPOINTS
        ]

    migrated = _reorder_top_level(row, touchpoints)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated["schema_date"] = SCHEMA_DATE

    process_block = migrated.get("process")
    if isinstance(process_block, dict):
        cleaned_notes, changed = _strip_v1_escape_hatch(process_block.get("notes"))
        if changed:
            process_block["notes"] = cleaned_notes
            row_report["notes_changed"] = True

    _fill_method_source_shortcuts(
        migrated.get("integration_touchpoints", {}),
        row_report=row_report,
    )

    cache = VERIFY.FileCache()
    _fill_anchor_symbols_recursive(
        migrated,
        json_path="",
        process_name=process_name,
        cache=cache,
        row_report=row_report,
    )

    oracle_block, blocker = _build_oracle_block(process_name)
    if blocker is not None:
        row_report["blocked"].append(blocker)
    else:
        migrated["stoichiometry_oracle"] = oracle_block
        row_report["oracle_added"] = True

    _apply_kind_tags(migrated, row_report)

    migrated = _reorder_top_level(
        migrated,
        migrated.get("integration_touchpoints", {}),
    )

    if not dry_run:
        _write_yaml_document(row_path, migrated, yaml_backend)
        reloaded, _ = _load_yaml_document(row_path)
        if not isinstance(reloaded, dict):
            raise TypeError(f"{row_path.name} did not parse as a mapping after write")
        row_report["written"] = True

    return row_report


def _discover_target_rows() -> list[Path]:
    return sorted(
        path
        for path in WIRING_DIR.glob("*.yaml")
        if path.name != "Metabolism.yaml" and not path.name.startswith("_")
    )


def _aggregate_report(row_reports: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "yaml_backend": row_reports[0]["yaml_backend"] if row_reports else "unknown",
        "rows_total": len(row_reports),
        "rows_migrated": [row["process"] for row in row_reports if row["status"] == "migrated"],
        "rows_blocked": [
            {
                "process": row["process"],
                "blocked": row["blocked"],
            }
            for row in row_reports
            if row["status"] == "blocked" or row["blocked"]
        ],
        "copy_parent_fills_total": sum(row["copy_parent_fills"] for row in row_reports),
        "source_extract_fills_total": sum(row["source_extract_fills"] for row in row_reports),
        "unresolved_total": sum(len(row["unresolved"]) for row in row_reports),
        "row_reports": row_reports,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate per-process wiring rows from schema v1 to v2.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the migration report without writing files.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional path for a JSON migration report.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    row_reports: list[dict[str, Any]] = []
    for row_path in _discover_target_rows():
        _, yaml_backend = _load_yaml_document(row_path)
        row_reports.append(
            _migrate_row(
                row_path,
                dry_run=args.dry_run,
                yaml_backend=yaml_backend,
            )
        )

    report = _aggregate_report(row_reports, dry_run=args.dry_run)
    rendered = json.dumps(report, indent=2, sort_keys=False)
    print(rendered)

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
