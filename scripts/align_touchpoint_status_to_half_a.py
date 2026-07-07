#!/usr/bin/env python3
"""Align wiring-row touchpoint statuses to the Half A method map."""

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
TARGET_METHODS = (
    "calcResourceRequirements_Current",
    "evolveState",
)
HALF_A_TO_ROW_STATUS = {
    "confirmed": "implemented",
    "inlined": "implemented",
    "gap": "not_implemented",
}


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
    return sorted(path for path in WIRING_DIR.glob("*.yaml") if not path.name.startswith("_"))


def _process_name(row: Any, fallback: str) -> str:
    process = row.get("process")
    if isinstance(process, dict):
        name = process.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback


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


def _normalize_half_a_status(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _align_touchpoint_status(
    *,
    process_name: str,
    method_name: str,
    binding: dict[str, Any],
    half_a_entry: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
    current_status = binding.get("status")
    if half_a_entry is None:
        return False, None, {
            "process": process_name,
            "method": method_name,
            "current_status": current_status,
            "reason": "missing_half_a_entry",
        }

    half_a_status = _normalize_half_a_status(half_a_entry.get("status"))
    if half_a_status == "noop":
        return False, None, {
            "process": process_name,
            "method": method_name,
            "current_status": current_status,
            "half_a_status": half_a_status,
            "reason": "noop_left_unchanged",
        }

    mapped_status = HALF_A_TO_ROW_STATUS.get(half_a_status)
    if mapped_status is None:
        return False, None, {
            "process": process_name,
            "method": method_name,
            "current_status": current_status,
            "half_a_status": half_a_status,
            "reason": "unmapped_half_a_status",
        }

    if current_status == mapped_status:
        return False, None, {
            "process": process_name,
            "method": method_name,
            "current_status": current_status,
            "half_a_status": half_a_status,
            "reason": "already_aligned",
        }

    binding["status"] = mapped_status
    return True, {
        "process": process_name,
        "method": method_name,
        "before": current_status,
        "after": mapped_status,
        "half_a_status": half_a_status,
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

    changed_entries: list[dict[str, Any]] = []
    skipped_entries: list[dict[str, Any]] = []

    for method_name in TARGET_METHODS:
        binding = touchpoints.get(method_name)
        if not isinstance(binding, dict):
            skipped_entries.append(
                {
                    "process": process_name,
                    "method": method_name,
                    "reason": "missing_row_touchpoint",
                }
            )
            continue

        changed, changed_entry, skipped_entry = _align_touchpoint_status(
            process_name=process_name,
            method_name=method_name,
            binding=binding,
            half_a_entry=_half_a_method_entry(half_a_processes, process_name, method_name),
        )
        if changed and changed_entry is not None:
            changed_entries.append(changed_entry)
        if skipped_entry is not None:
            skipped_entries.append(skipped_entry)

    if changed_entries and not dry_run:
        _write_yaml_document(row_path, row, backend)

    return {
        "process": process_name,
        "file": row_path.name,
        "changed": changed_entries,
        "skipped": skipped_entries,
        "written": bool(changed_entries) and not dry_run,
    }


def _aggregate_report(row_reports: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
    changes = [entry for row in row_reports for entry in row["changed"]]
    skipped = [entry for row in row_reports for entry in row["skipped"]]
    return {
        "dry_run": dry_run,
        "rows_total": len(row_reports),
        "rows_written": [row["file"] for row in row_reports if row["written"]],
        "changes_total": len(changes),
        "changes": changes,
        "skipped_total": len(skipped),
        "skipped": skipped,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Align integration_touchpoints statuses to Half A canonical statuses.",
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
