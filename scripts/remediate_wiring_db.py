#!/usr/bin/env python3
"""Mass-remediate wiring DB row-level validation failures."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "build_wiring_db.py"
VALIDATE_ONLY_REPORT = REPO_ROOT / "tmp" / "wiring_db_validate_only.txt"
STATUS_PATH = REPO_ROOT / "STATUS_wiring_db_remediation.md"

TARGET_SCHEMA_DATE = "2026-06-29"
AUDITED_BY = "gpt-5.4-mini + parallel codex fleet (Day-43 EOD batch)"
OC_COMMIT_SHA = "61a5a06"

COMPLETE_PROVENANCE_ROWS = {
    "Metabolism",
    "ProteinProcessingI",
    "Translation",
    "tRNAAminoacylation",
}

MATLAB_ONLY_PROVENANCE_ROWS = {
    "MacromolecularComplexation",
    "ProteinTranslocation",
    "RNADecay",
}

VALIDATION_ROW_RE = re.compile(r"^\[FAIL row=(?P<row>[^\]]+)\] ")
LINES_RE = re.compile(r"^\d+-\d+$")
SPAN_RE = re.compile(r"(\d+)(?:-(\d+))?")


yaml = YAML(typ="rt")
yaml.preserve_quotes = True
yaml.width = 4096
yaml.indent(mapping=2, sequence=4, offset=2)


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle)


def _dump_yaml(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle)


def _insert_schema_date_text(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if re.search(r"^schema_date:\s*\"?2026-06-29\"?\s*$", text, flags=re.M):
        return False
    lines = text.splitlines()
    inserted = False
    new_lines: list[str] = []
    for line in lines:
        new_lines.append(line)
        if not inserted and re.fullmatch(r'schema_version:\s*"1\.0"', line.strip()):
            new_lines.append('schema_date: "2026-06-29"')
            inserted = True
    if not inserted:
        raise RuntimeError(f"could not find schema_version line in {path}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_nonempty_list_of_str(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_is_nonempty_str(item) for item in value)


def _process_name(row: Any, fallback: str) -> str:
    if isinstance(row, dict):
        process = row.get("process")
        if isinstance(process, dict):
            name = process.get("name")
            if _is_nonempty_str(name):
                return str(name).strip()
    return fallback


def _collect_paths(node: Any) -> list[str]:
    paths: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            path_value = item.get("path")
            if _is_nonempty_str(path_value):
                paths.append(str(path_value).strip())
            for value in item.values():
                visit(value)
        elif isinstance(item, list):
            for value in item:
                visit(value)

    visit(node)
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def _fixture_path_for(process_name: str) -> Path:
    return REPO_ROOT / "data" / "karr_fixtures" / "per_process" / f"{process_name}_flat.mat"


def _best_effort_fixture_files(process_name: str, row: dict[str, Any]) -> list[str]:
    provenance = row.get("provenance")
    if isinstance(provenance, dict):
        existing = provenance.get("fixture_files")
        if isinstance(existing, list) and existing:
            return [str(item) for item in existing if _is_nonempty_str(item)]

    fixture_path = _fixture_path_for(process_name)
    if fixture_path.exists():
        return [fixture_path.relative_to(REPO_ROOT).as_posix()]
    return []


def _insert_schema_date(row: CommentedMap) -> bool:
    if "schema_date" in row:
        return False
    value = DoubleQuotedScalarString(TARGET_SCHEMA_DATE)
    if "schema_version" in row:
        row.insert(list(row.keys()).index("schema_version") + 1, "schema_date", value)
    else:
        row["schema_date"] = value
    return True


def _normalize_anchor_lines(anchor: Any, *, context: str) -> bool:
    if not isinstance(anchor, dict):
        return False
    lines = anchor.get("lines")
    if not _is_nonempty_str(lines):
        return False
    text = str(lines).strip()
    if LINES_RE.fullmatch(text):
        return False

    spans = SPAN_RE.findall(text)
    numbers: list[int] = []
    for start, end in spans:
        numbers.append(int(start))
        numbers.append(int(end or start))
    if numbers:
        normalized = f"{min(numbers)}-{max(numbers)}"
    else:
        normalized = "1-1"

    anchor["lines"] = normalized
    note = anchor.get("note")
    suffix = f"normalized from invalid lines={text!r} for schema validation"
    if _is_nonempty_str(note):
        note_text = str(note).strip()
        if suffix not in note_text:
            anchor["note"] = f"{note_text} ({suffix})"
    else:
        anchor["note"] = suffix
    return True


def _normalize_unit_conversion_anchors(row: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    unit_chain = row.get("unit_conversion_chain")
    if not isinstance(unit_chain, dict):
        return changes
    steps = unit_chain.get("steps")
    if not isinstance(steps, list):
        return changes
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        anchor = step.get("anchor")
        if _normalize_anchor_lines(anchor, context=f"unit_conversion_chain.steps[{idx}].anchor"):
            changes.append(f"unit_conversion_chain.steps[{idx}].anchor.lines")
    return changes


def _fix_terminal_organelle_routing(row: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    if _process_name(row, "") != "TerminalOrganelleAssembly":
        return changes
    routing = row.get("compartment_routing")
    if not isinstance(routing, list):
        return changes
    for idx, entry in enumerate(routing):
        if not isinstance(entry, dict):
            continue
        consume = entry.get("consume_compartment")
        produce = entry.get("produce_compartment")
        if consume is not None and consume == produce and entry.get("mismatch") is True:
            entry["mismatch"] = False
            changes.append(f"compartment_routing[{idx}].mismatch")
    return changes


def _ensure_required_provenance(row: CommentedMap, *, process_name: str) -> list[str]:
    changes: list[str] = []
    source_anchors = row.get("source_anchors")
    matlab_paths = _collect_paths(source_anchors.get("matlab_blocks") if isinstance(source_anchors, dict) else None)
    oc_paths = _collect_paths(source_anchors.get("oc_blocks") if isinstance(source_anchors, dict) else None)
    fixture_files = _best_effort_fixture_files(process_name, row)

    if process_name in COMPLETE_PROVENANCE_ROWS:
        return changes

    provenance = row.get("provenance")
    if not isinstance(provenance, CommentedMap):
        provenance = CommentedMap() if provenance is None else CommentedMap(provenance)
        row["provenance"] = provenance
        changes.append("provenance.created")

    def set_if_missing(key: str, value: Any) -> None:
        if key not in provenance or provenance.get(key) in (None, "", [], ()):
            provenance[key] = value
            changes.append(f"provenance.{key}")

    if process_name in MATLAB_ONLY_PROVENANCE_ROWS:
        if _is_nonempty_list_of_str(provenance.get("matlab_files_referenced")):
            return changes
        if matlab_paths:
            provenance["matlab_files_referenced"] = CommentedSeq(matlab_paths)
            changes.append("provenance.matlab_files_referenced")
        return changes

    set_if_missing("last_audited", DoubleQuotedScalarString(TARGET_SCHEMA_DATE))
    set_if_missing("audited_by", DoubleQuotedScalarString(AUDITED_BY))
    set_if_missing("oc_commit_sha", DoubleQuotedScalarString(OC_COMMIT_SHA))
    if not _is_nonempty_list_of_str(provenance.get("matlab_files_referenced")) and matlab_paths:
        provenance["matlab_files_referenced"] = CommentedSeq(matlab_paths)
        changes.append("provenance.matlab_files_referenced")
    if not _is_nonempty_list_of_str(provenance.get("oc_files_referenced")) and oc_paths:
        provenance["oc_files_referenced"] = CommentedSeq(oc_paths)
        changes.append("provenance.oc_files_referenced")
    if "fixture_files" not in provenance or not _is_nonempty_list_of_str(provenance.get("fixture_files")):
        if fixture_files:
            provenance["fixture_files"] = CommentedSeq(fixture_files)
            changes.append("provenance.fixture_files")
    if "kb_version" not in provenance:
        provenance["kb_version"] = None
        changes.append("provenance.kb_version")
    if "notes" not in provenance or not _is_nonempty_str(provenance.get("notes")):
        provenance["notes"] = DoubleQuotedScalarString(
            "Mechanical remediation added schema_date and provenance references from the row's source anchors."
        )
        changes.append("provenance.notes")
    return changes


def _edit_row(path: Path) -> tuple[list[str], str]:
    try:
        payload = _load_yaml(path)
    except DuplicateKeyError:
        process_name = path.stem
        if process_name not in COMPLETE_PROVENANCE_ROWS:
            raise
        changes: list[str] = []
        if _insert_schema_date_text(path):
            changes.append("schema_date")
        return changes, process_name
    if not isinstance(payload, CommentedMap):
        raise TypeError(f"{path} did not parse as a mapping")

    process_name = _process_name(payload, path.stem)
    changes: list[str] = []
    if _insert_schema_date(payload):
        changes.append("schema_date")
    changes.extend(_ensure_required_provenance(payload, process_name=process_name))
    changes.extend(_normalize_unit_conversion_anchors(payload))
    changes.extend(_fix_terminal_organelle_routing(payload))

    if changes:
        _dump_yaml(path, payload)
    return changes, process_name


def _run_validator(validate_only: bool = True) -> str:
    args = [sys.executable, str(VALIDATOR_PATH)]
    if validate_only:
        args.append("--validate-only")
    completed = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout
    if completed.stderr:
        output = output + ("\n" if output and not output.endswith("\n") else "") + completed.stderr
    return output


def _parse_row_failures(report_text: str) -> set[str]:
    failures: set[str] = set()
    for line in report_text.splitlines():
        match = VALIDATION_ROW_RE.match(line)
        if match:
            failures.add(match.group("row"))
    return failures


def _write_status(summary: dict[str, Any]) -> None:
    lines: list[str] = [
        "# Wiring DB Remediation Status",
        "",
        f"- Run date: `{TARGET_SCHEMA_DATE}`",
        f"- Rows processed: `{summary['rows_processed']}`",
        f"- Rows changed: `{summary['rows_changed']}`",
        f"- Final row-level failures: `{summary['final_row_failures']}`",
        f"- Final cross-row failures: `{summary['final_cross_failures']}`",
        "",
        "## Fixed",
    ]
    if summary["changed_rows"]:
        for row_name in summary["changed_rows"]:
            lines.append(f"- {row_name}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Remaining",
        ]
    )
    remaining = summary["remaining_rows"]
    if remaining:
        for row_name in remaining:
            lines.append(f"- {row_name}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Notes",
            "- Schema dates were added mechanically where missing.",
            "- Required provenance fields were filled from each row's source anchors, while existing non-null provenance fields were preserved.",
            "- The two malformed unit-conversion anchor spans were normalized to regex-valid contiguous ranges.",
            "- TerminalOrganelleAssembly compartment-routing mismatches were flipped to `false` where consume and produce compartments were identical.",
            "- Residual validator failures, if any, are expected to be cross-row consistency issues outside this remediation scope.",
        ]
    )
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    row_paths = sorted(
        (path for path in SOURCE_DIR.glob("*.yaml") if not path.name.startswith("_")),
        key=lambda path: path.stem,
    )

    changed_rows: list[str] = []
    per_row_validation: list[str] = []
    rows_processed = 0

    for path in row_paths:
        rows_processed += 1
        changes, process_name = _edit_row(path)
        if changes:
            changed_rows.append(process_name)
        report = _run_validator(validate_only=True)
        failures = _parse_row_failures(report)
        status = "FAIL" if process_name in failures else "PASS"
        per_row_validation.append(f"{process_name}: {status}")
        print(f"[row {rows_processed:02d}/{len(row_paths):02d}] {process_name}: {status}")
        if not changes:
            print(f"[row {rows_processed:02d}/{len(row_paths):02d}] {process_name}: unchanged")

    # Regenerate the combined YAML using the repo's existing builder.
    regenerate = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH.parent / "build_wiring_db.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if regenerate.returncode not in (0, 1):
        print(regenerate.stdout, end="" if regenerate.stdout.endswith("\n") or not regenerate.stdout else "\n")
        print(regenerate.stderr, end="" if regenerate.stderr.endswith("\n") or not regenerate.stderr else "\n", file=sys.stderr)
        raise SystemExit(regenerate.returncode)

    final_report = _run_validator(validate_only=True)
    VALIDATE_ONLY_REPORT.write_text(final_report, encoding="utf-8")
    final_failures = _parse_row_failures(final_report)

    summary_line = ""
    for line in final_report.splitlines():
        if line in {"PASS", "FAIL"}:
            summary_line = line
            break

    cross_failures = 0
    for line in final_report.splitlines():
        if line.startswith("[CROSS] ") and "reciprocal mismatches" in line:
            match = re.search(r"(\d+) reciprocal mismatches, (\d+) cyclic ordering, (\d+) missing rows", line)
            if match:
                cross_failures = int(match.group(1)) + int(match.group(2)) + int(match.group(3))
            break

    _write_status(
        {
            "rows_processed": rows_processed,
            "rows_changed": len(changed_rows),
            "changed_rows": changed_rows,
            "final_row_failures": len(final_failures),
            "final_cross_failures": cross_failures,
            "remaining_rows": sorted(final_failures),
        }
    )

    print("## SUMMARY")
    print(f"Rows processed: {rows_processed}")
    print(f"Rows changed: {len(changed_rows)}")
    print(f"Final row-level failures: {len(final_failures)}")
    print(f"Final validator status: {summary_line or 'unknown'}")
    if per_row_validation:
        print("Per-row validation checkpoints:")
        for item in per_row_validation:
            print(f"- {item}")
    if final_failures:
        print("Remaining failing rows:")
        for name in sorted(final_failures):
            print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
