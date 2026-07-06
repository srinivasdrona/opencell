#!/usr/bin/env python3
"""Align wiring-row OC touchpoint anchors to the Half A method map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
except ImportError:  # pragma: no cover
    YAML = None
    CommentedMap = dict


REPO_ROOT = Path(__file__).resolve().parents[1]
HALF_A_MAP_PATH = REPO_ROOT / "data" / "karr_method_inventory" / "oc_method_map.yaml"
WIRING_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
TOUCHPOINTS = (
    "calcResourceRequirements_Current",
    "evolveState",
    "calcFluxBounds",
)
SKIP_HALF_A_STATUSES = {"gap", "none", ""}


def _mapping() -> Any:
    return CommentedMap() if YAML is not None else {}


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


def _discover_wiring_rows() -> list[Path]:
    return sorted(
        path
        for path in WIRING_DIR.glob("*.yaml")
        if not path.name.startswith("_")
    )


def _process_name(row: Any, fallback: str) -> str:
    process = row.get("process")
    if isinstance(process, dict):
        name = process.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback


def _parse_half_a_oc(anchor: str) -> tuple[str, str, int]:
    path_text, symbol, line_text = anchor.rsplit(":", 2)
    line_number = int(line_text)
    return path_text, symbol, line_number


def _status_value(binding: Any) -> Any:
    if not isinstance(binding, dict):
        return None
    return binding.get("status")


def _half_a_method_entry(
    half_a_processes: dict[str, Any],
    process_name: str,
    method_name: str,
) -> dict[str, Any] | None:
    process_entry = half_a_processes.get(process_name)
    if not isinstance(process_entry, dict):
        return None
    runtime_methods = process_entry.get("runtime_methods")
    if not isinstance(runtime_methods, dict):
        return None
    method_entry = runtime_methods.get(method_name)
    return method_entry if isinstance(method_entry, dict) else None


def _ensure_mapping(parent: Any, key: str) -> Any:
    current = parent.get(key)
    if isinstance(current, dict):
        return current
    created = _mapping()
    parent[key] = created
    return created


def _sync_touchpoint_oc(
    *,
    process_name: str,
    method_name: str,
    binding: dict[str, Any],
    half_a_entry: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
    if half_a_entry is None:
        return False, None, {"process": process_name, "method": method_name, "reason": "skipped: no Half A oc"}

    raw_status = half_a_entry.get("status")
    normalized_status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    raw_oc = half_a_entry.get("oc")
    if normalized_status in SKIP_HALF_A_STATUSES or not isinstance(raw_oc, str) or not raw_oc.strip():
        return False, None, {"process": process_name, "method": method_name, "reason": "skipped: no Half A oc"}

    path_text, symbol, line_number = _parse_half_a_oc(raw_oc.strip())
    oc_block = _ensure_mapping(binding, "oc")
    source_block = _ensure_mapping(oc_block, "source")

    old_symbol = oc_block.get("symbol")
    old_path = source_block.get("path")
    old_source_symbol = source_block.get("symbol")
    old_lines = source_block.get("lines")

    new_lines = f"{line_number}-{line_number}"
    changed = (
        old_symbol != symbol
        or old_path != path_text
        or old_source_symbol != symbol
        or old_lines != new_lines
    )

    oc_block["symbol"] = symbol
    source_block["path"] = path_text
    source_block["symbol"] = symbol
    source_block["lines"] = new_lines

    if not changed:
        return False, None, None

    return True, {
        "process": process_name,
        "method": method_name,
        "old": {
            "symbol": old_symbol,
            "path": old_path,
            "source_symbol": old_source_symbol,
            "lines": old_lines,
        },
        "new": {
            "symbol": symbol,
            "path": path_text,
            "source_symbol": symbol,
            "lines": new_lines,
        },
    }, None


def _align_row(
    row_path: Path,
    *,
    half_a_processes: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    row, backend = _load_yaml_document(row_path)
    if not isinstance(row, dict):
        raise TypeError(f"{row_path.name} did not parse as a mapping")

    process_name = _process_name(row, row_path.stem)
    touchpoints = row.get("integration_touchpoints")
    if not isinstance(touchpoints, dict):
        raise TypeError(f"{row_path.name} is missing integration_touchpoints")

    before_statuses = {
        method_name: _status_value(touchpoints.get(method_name))
        for method_name in TOUCHPOINTS
        if method_name in touchpoints
    }

    changed_entries: list[dict[str, Any]] = []
    skipped_entries: list[dict[str, Any]] = []

    for method_name in TOUCHPOINTS:
        binding = touchpoints.get(method_name)
        if not isinstance(binding, dict):
            continue

        changed, changed_entry, skipped_entry = _sync_touchpoint_oc(
            process_name=process_name,
            method_name=method_name,
            binding=binding,
            half_a_entry=_half_a_method_entry(half_a_processes, process_name, method_name),
        )
        if changed and changed_entry is not None:
            changed_entries.append(changed_entry)
        if skipped_entry is not None:
            skipped_entries.append(skipped_entry)

    after_statuses = {
        method_name: _status_value(touchpoints.get(method_name))
        for method_name in TOUCHPOINTS
        if method_name in touchpoints
    }
    status_changes = [
        {
            "process": process_name,
            "method": method_name,
            "before": before_statuses.get(method_name),
            "after": after_statuses.get(method_name),
        }
        for method_name in sorted(set(before_statuses) | set(after_statuses))
        if before_statuses.get(method_name) != after_statuses.get(method_name)
    ]

    if changed_entries and not dry_run:
        _write_yaml_document(row_path, row, backend)

    return {
        "process": process_name,
        "file": row_path.name,
        "changed": changed_entries,
        "skipped": skipped_entries,
        "status_changes": status_changes,
        "written": bool(changed_entries) and not dry_run,
    }


def _aggregate_report(row_reports: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
    changed = [entry for row in row_reports for entry in row["changed"]]
    skipped = [entry for row in row_reports for entry in row["skipped"]]
    status_changes = [entry for row in row_reports for entry in row["status_changes"]]
    written_files = [row["file"] for row in row_reports if row["written"]]
    return {
        "dry_run": dry_run,
        "rows_total": len(row_reports),
        "rows_written": written_files,
        "changes_total": len(changed),
        "changes": changed,
        "skipped_total": len(skipped),
        "skipped": skipped,
        "status_changes_total": len(status_changes),
        "status_changes": status_changes,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Align integration_touchpoints.*.oc anchors to Half A canonical OC anchors.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the required changes without writing the wiring files.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional path for the JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    half_a_doc, _ = _load_yaml_document(HALF_A_MAP_PATH)
    if not isinstance(half_a_doc, dict):
        raise TypeError(f"{HALF_A_MAP_PATH} did not parse as a mapping")

    half_a_processes = half_a_doc.get("processes")
    if not isinstance(half_a_processes, dict):
        raise TypeError(f"{HALF_A_MAP_PATH} is missing processes")

    row_reports = [
        _align_row(
            row_path,
            half_a_processes=half_a_processes,
            dry_run=args.dry_run,
        )
        for row_path in _discover_wiring_rows()
    ]
    report = _aggregate_report(row_reports, dry_run=args.dry_run)
    rendered = json.dumps(report, indent=2, sort_keys=False)
    print(rendered)

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
