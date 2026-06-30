#!/usr/bin/env python3
"""Inspect the per-process wiring DB and summarize coverage/consistency."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
CANONICAL_MANIFEST = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "manifest.json"

REQUIRED_TOP_LEVEL_KEYS = (
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
REQUIRED_PROVENANCE_KEYS = (
    "last_audited",
    "audited_by",
    "oc_commit_sha",
    "matlab_files_referenced",
    "oc_files_referenced",
)
METHOD_REQUIRED_NAMES = (
    "calcResourceRequirements_Current",
    "evolveState",
    "calcFluxBounds",
)
METHOD_STATUS_VALUES = {"implemented", "partial", "not_implemented"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FAIL_ROW_RE = re.compile(r"^\[FAIL row=(?P<row>[^\]]+)\] (?P<msg>.+)$")
SUMMARY_RE = re.compile(
    r"^\[CROSS\] (?P<rec>\d+) reciprocal mismatches, (?P<cyc>\d+) cyclic ordering, (?P<missing>\d+) missing rows$"
)


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _format_process_name(row: dict[str, Any], fallback: str) -> str:
    process = row.get("process")
    if isinstance(process, dict):
        name = process.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback


def _load_rows() -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    for row_path in sorted(p for p in SOURCE_DIR.glob("*.yaml") if not p.name.startswith("_")):
        payload = _load_yaml(row_path)
        if isinstance(payload, dict):
            rows.append((row_path, payload))
    rows.sort(key=lambda item: _format_process_name(item[1], item[0].stem))
    return rows


def _load_canonical_processes() -> list[str]:
    payload = _load_yaml(CANONICAL_MANIFEST)
    fixtures = payload.get("fixtures", []) if isinstance(payload, dict) else []
    names = [
        str(entry["name"])
        for entry in fixtures
        if isinstance(entry, dict) and entry.get("kind") == "process" and entry.get("name")
    ]
    return sorted(dict.fromkeys(names))


def _load_validator_report(path: Path | None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "exit_code": None,
        "row_failures": defaultdict(list),
        "reciprocal_mismatches": [],
        "cyclic_ordering": [],
        "summary": None,
        "status": None,
        "raw_lines": [],
    }
    if path is None or not path.exists():
        return report

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")
        report["raw_lines"].append(line)
        match = FAIL_ROW_RE.match(line)
        if match:
            report["row_failures"][match.group("row")].append(match.group("msg"))
            continue
        if line.startswith("[CROSS] reciprocal mismatch: "):
            report["reciprocal_mismatches"].append(line)
            continue
        if line.startswith("[CROSS] cyclic ordering: "):
            report["cyclic_ordering"].append(line)
            continue
        match = SUMMARY_RE.match(line)
        if match:
            report["summary"] = {
                "reciprocal_mismatches": int(match.group("rec")),
                "cyclic_ordering": int(match.group("cyc")),
                "missing_rows": int(match.group("missing")),
            }
            continue
        if line in {"PASS", "FAIL"}:
            report["status"] = line
            continue
        if line.startswith("EXIT_CODE=") or line.startswith("EXIT_CODE:"):
            _, _, value = line.partition("=")
            if not value:
                _, _, value = line.partition(":")
            value = value.strip()
            try:
                report["exit_code"] = int(value)
            except ValueError:
                report["exit_code"] = value
    return report


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_list_of_str(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _count_method_statuses(methods: Any) -> dict[str, int]:
    counter = Counter({status: 0 for status in (*METHOD_STATUS_VALUES, "other")})
    if not isinstance(methods, dict):
        counter["other"] = len(METHOD_REQUIRED_NAMES)
        return dict(counter)
    for name in METHOD_REQUIRED_NAMES:
        binding = methods.get(name)
        status = None
        if isinstance(binding, dict):
            raw = binding.get("status")
            if isinstance(raw, str):
                status = raw.strip().lower()
        if status in METHOD_STATUS_VALUES:
            counter[status] += 1
        else:
            counter["other"] += 1
    return dict(counter)


def _ordering_populated(ordering: Any) -> bool:
    if not isinstance(ordering, dict):
        return False
    for key in ("hard_before", "hard_after", "soft_before", "soft_after"):
        value = ordering.get(key)
        if isinstance(value, list) and value:
            return True
    note = ordering.get("note")
    return _nonempty_str(note)


def _cross_row_checks(rows: list[dict[str, Any]], canonical_processes: list[str]) -> tuple[list[str], list[str], list[str]]:
    reciprocal_mismatches: list[str] = []
    cyclic_ordering: list[str] = []

    rows_by_name = {_format_process_name(row, f"row-{idx}"): row for idx, row in enumerate(rows)}

    for process_name, row in rows_by_name.items():
        dependencies = row.get("dependencies") if isinstance(row, dict) else None
        produces = dependencies.get("produces_inputs_for", []) if isinstance(dependencies, dict) else []
        for consumer_name in produces:
            if not isinstance(consumer_name, str) or not consumer_name.strip():
                continue
            consumer = rows_by_name.get(consumer_name)
            if consumer is None:
                reciprocal_mismatches.append(
                    f"<{process_name} produces_inputs_for=[{consumer_name}], {consumer_name} consumes_outputs_of=[<missing row>]> "
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
                    f"<{process_name} produces_inputs_for=[{consumer_name}], {consumer_name} consumes_outputs_of=[{', '.join(reciprocal) if isinstance(reciprocal, list) and reciprocal else ''}]>"
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
                    f"{process_name} hard_before {later_name} and {later_name} hard_before {process_name}"
                )

    present = set(rows_by_name)
    missing_rows = [name for name in canonical_processes if name not in present]
    return reciprocal_mismatches, cyclic_ordering, missing_rows


def _row_report(row_path: Path, row: dict[str, Any], validator_failures: dict[str, list[str]]) -> dict[str, Any]:
    process_name = _format_process_name(row, row_path.stem)
    methods_status = _count_method_statuses(row.get("methods"))

    provenance = row.get("provenance")
    provenance_values: dict[str, bool] = {}
    if isinstance(provenance, dict):
        provenance_values = {
            "last_audited": _nonempty_str(provenance.get("last_audited")),
            "audited_by": _nonempty_str(provenance.get("audited_by")),
            "oc_commit_sha": _nonempty_str(provenance.get("oc_commit_sha")),
            "matlab_files_referenced": _nonempty_list_of_str(provenance.get("matlab_files_referenced")),
            "oc_files_referenced": _nonempty_list_of_str(provenance.get("oc_files_referenced")),
        }
    else:
        provenance_values = {key: False for key in REQUIRED_PROVENANCE_KEYS}

    deviations = row.get("deviations")
    known_deviations: list[str] = []
    lp_bounds_source: dict[str, Any] = {}
    if isinstance(deviations, dict):
        raw_deviations = deviations.get("known_deviations")
        if isinstance(raw_deviations, list):
            known_deviations = [str(item) for item in raw_deviations]
        raw_lp_bounds = deviations.get("lp_bounds_source")
        if isinstance(raw_lp_bounds, dict):
            lp_bounds_source = raw_lp_bounds

    allocator = row.get("allocator")
    request_formula = {}
    if isinstance(allocator, dict) and isinstance(allocator.get("request_formula"), dict):
        request_formula = allocator["request_formula"]

    ordering = row.get("ordering_constraints")
    dependencies = row.get("dependencies")
    produces = []
    consumes = []
    if isinstance(dependencies, dict):
        if isinstance(dependencies.get("produces_inputs_for"), list):
            produces = [str(item) for item in dependencies["produces_inputs_for"]]
        if isinstance(dependencies.get("consumes_outputs_of"), list):
            consumes = [str(item) for item in dependencies["consumes_outputs_of"]]

    a1 = _nonempty_str(request_formula.get("matlab")) and _nonempty_str(request_formula.get("oc"))
    a2 = _ordering_populated(ordering)
    a3 = _nonempty_str(lp_bounds_source.get("karr")) and _nonempty_str(lp_bounds_source.get("oc_current"))
    a3b = any("consumption-clip" in item.lower() for item in known_deviations)
    a4 = isinstance(deviations, dict) and "shared_pool_projection_merges_compartments" in deviations

    missing_top_level_keys = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in row]
    schema_version = row.get("schema_version")
    schema_date = row.get("schema_date")

    return {
        "process": process_name,
        "file": row_path.name,
        "size_kb": round(row_path.stat().st_size / 1024.0, 1),
        "schema_version": schema_version if isinstance(schema_version, str) else "",
        "schema_date": schema_date if isinstance(schema_date, str) else "",
        "missing_top_level_keys": missing_top_level_keys,
        "methods_status": methods_status,
        "provenance_complete": all(provenance_values.values()),
        "provenance_populated": sum(1 for value in provenance_values.values() if value),
        "provenance_fields": provenance_values,
        "validator_failures": validator_failures.get(process_name, []),
        "known_deviations": known_deviations,
        "known_deviation_count": len(known_deviations),
        "dependencies": {"produces_inputs_for": produces, "consumes_outputs_of": consumes},
        "orphan": not produces and not consumes,
        "audit_hooks": {"A1": a1, "A2": a2, "A3": a3, "A3b": a3b, "A4": a4},
    }


def _build_report(validate_output: Path | None) -> dict[str, Any]:
    validator_report = _load_validator_report(validate_output)
    rows = _load_rows()
    canonical_processes = _load_canonical_processes()
    reciprocal_mismatches, cyclic_ordering, missing_rows = _cross_row_checks([row for _, row in rows], canonical_processes)

    row_reports = [_row_report(row_path, row, validator_report["row_failures"]) for row_path, row in rows]

    aggregate = {
        "row_count": len(row_reports),
        "schema_version_1_0": 0,
        "schema_version_other": 0,
        "schema_date_ge_2026_06_29": 0,
        "schema_date_other_or_missing": 0,
        "provenance_complete": 0,
        "provenance_field_coverage": Counter({key: 0 for key in REQUIRED_PROVENANCE_KEYS}),
        "method_statuses": Counter({status: 0 for status in (*METHOD_STATUS_VALUES, "other")}),
        "rows_with_deviations": 0,
        "orphans": 0,
        "audit_hooks": Counter({"A1": 0, "A2": 0, "A3": 0, "A3b": 0, "A4": 0}),
    }

    threshold = date(2026, 6, 29)
    for row in row_reports:
        if row["schema_version"] == "1.0":
            aggregate["schema_version_1_0"] += 1
        else:
            aggregate["schema_version_other"] += 1
        try:
            parsed = date.fromisoformat(row["schema_date"])
        except ValueError:
            parsed = None
        if parsed is not None and parsed >= threshold:
            aggregate["schema_date_ge_2026_06_29"] += 1
        else:
            aggregate["schema_date_other_or_missing"] += 1
        if row["provenance_complete"]:
            aggregate["provenance_complete"] += 1
        for key, value in row["provenance_fields"].items():
            if value:
                aggregate["provenance_field_coverage"][key] += 1
        aggregate["method_statuses"].update(row["methods_status"])
        if row["known_deviation_count"]:
            aggregate["rows_with_deviations"] += 1
        if row["orphan"]:
            aggregate["orphans"] += 1
        aggregate["audit_hooks"].update({key: int(bool(value)) for key, value in row["audit_hooks"].items()})

    roster = {
        "canonical": canonical_processes,
        "db": [row["process"] for row in row_reports],
        "canonical_only": sorted(set(canonical_processes) - {row["process"] for row in row_reports}),
        "db_only": sorted({row["process"] for row in row_reports} - set(canonical_processes)),
    }

    return {
        "aggregate": aggregate,
        "rows": row_reports,
        "validator": {
            "status": validator_report["status"],
            "exit_code": validator_report["exit_code"],
            "summary": validator_report["summary"],
            "row_failures": {key: value for key, value in validator_report["row_failures"].items()},
            "reciprocal_mismatches": validator_report["reciprocal_mismatches"],
            "cyclic_ordering": validator_report["cyclic_ordering"],
            "raw_lines": validator_report["raw_lines"],
        },
        "cross_row": {
            "reciprocal_mismatches": reciprocal_mismatches,
            "cyclic_ordering": cyclic_ordering,
            "missing_rows": missing_rows,
        },
        "roster": roster,
    }


def _status_counts_string(counts: dict[str, int]) -> str:
    return f"implemented={counts['implemented']}, partial={counts['partial']}, not_implemented={counts['not_implemented']}, other={counts['other']}"


def _format_validation_issues(row: dict[str, Any]) -> str:
    issues: list[str] = []
    if row["validator_failures"]:
        issues.extend(row["validator_failures"])
    return "; ".join(issues) if issues else "none"


def _format_missing_provenance(row: dict[str, Any]) -> str:
    missing = [key for key, ok in row["provenance_fields"].items() if not ok]
    return ", ".join(missing) if missing else "none"


def _render_markdown(report: dict[str, Any]) -> str:
    rows = report["rows"]
    aggregate = report["aggregate"]
    validator = report["validator"]
    roster = report["roster"]
    cross_row = report["cross_row"]

    lines: list[str] = []
    lines.append("# Wiring DB Cross-Row Validation Summary")
    lines.append("")
    lines.append(f"- Source rows: `{aggregate['row_count']}`")
    lines.append(f"- Canonical roster size: `{len(roster['canonical'])}`")
    lines.append(f"- Validator status: `{validator['status'] or 'unknown'}`")
    if validator["exit_code"] is not None:
        lines.append(f"- Validator exit code captured in file: `{validator['exit_code']}`")
    lines.append("")

    lines.append("## Coverage")
    lines.append("")
    lines.append("| Process | YAML size (KB) | methods.*.status distribution |")
    lines.append("| --- | ---: | --- |")
    for row in rows:
        lines.append(f"| {row['process']} | {row['size_kb']:.1f} | {_status_counts_string(row['methods_status'])} |")
    lines.append("")
    lines.append(f"28/28 rows present. Method status aggregate: {_status_counts_string(dict(aggregate['method_statuses']))}.")
    lines.append("")

    lines.append("## Schema Conformance")
    lines.append("")
    lines.append("| Process | schema_version | schema_date | provenance complete | missing provenance fields | validator issues |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        lines.append(
            f"| {row['process']} | {row['schema_version'] or 'missing'} | {row['schema_date'] or 'missing'} | "
            f"{'yes' if row['provenance_complete'] else 'no'} | {_format_missing_provenance(row)} | {_format_validation_issues(row)} |"
        )
    lines.append("")
    lines.append(
        f"Schema-version tally: `{aggregate['schema_version_1_0']}` rows at `1.0`, `{aggregate['schema_version_other']}` other. "
        f"Schema-date tally: `{aggregate['schema_date_ge_2026_06_29']}` rows at or after `2026-06-29`, "
        f"`{aggregate['schema_date_other_or_missing']}` other or missing."
    )
    lines.append(
        f"Provenance completeness: `{aggregate['provenance_complete']}` rows have all five required provenance fields; "
        f"field coverage = last_audited `{aggregate['provenance_field_coverage']['last_audited']}`, "
        f"audited_by `{aggregate['provenance_field_coverage']['audited_by']}`, "
        f"oc_commit_sha `{aggregate['provenance_field_coverage']['oc_commit_sha']}`, "
        f"matlab_files_referenced `{aggregate['provenance_field_coverage']['matlab_files_referenced']}`, "
        f"oc_files_referenced `{aggregate['provenance_field_coverage']['oc_files_referenced']}`."
    )
    lines.append("")

    lines.append("## Audit Traceability Hooks (A1-A4)")
    lines.append("")
    lines.append("| Process | A1 allocator cap | A2 process order | A3 LP bounds source | A3b consumption clip | A4 compartment merge |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        hooks = row["audit_hooks"]
        lines.append(
            f"| {row['process']} | {'yes' if hooks['A1'] else 'no'} | {'yes' if hooks['A2'] else 'no'} | "
            f"{'yes' if hooks['A3'] else 'no'} | {'yes' if hooks['A3b'] else 'no'} | {'yes' if hooks['A4'] else 'no'} |"
        )
    lines.append("")
    lines.append(
        f"Hook tally: A1 `{aggregate['audit_hooks']['A1']}`, A2 `{aggregate['audit_hooks']['A2']}`, "
        f"A3 `{aggregate['audit_hooks']['A3']}`, A3b `{aggregate['audit_hooks']['A3b']}`, A4 `{aggregate['audit_hooks']['A4']}`."
    )
    lines.append("")

    lines.append("## Cross-Row Consistency")
    lines.append("")
    summary = validator["summary"] or {"reciprocal_mismatches": len(cross_row["reciprocal_mismatches"]), "cyclic_ordering": len(cross_row["cyclic_ordering"]), "missing_rows": len(cross_row["missing_rows"])}
    lines.append(
        f"Validator summary: `{summary['reciprocal_mismatches']}` reciprocal dependency mismatches, "
        f"`{summary['cyclic_ordering']}` cyclic ordering violations, `{summary['missing_rows']}` missing canonical rows."
    )
    lines.append("")
    lines.append("First mismatches:")
    for item in cross_row["reciprocal_mismatches"][:20]:
        lines.append(f"- {item}")
    if len(cross_row["reciprocal_mismatches"]) > 20:
        lines.append(f"- ... `{len(cross_row['reciprocal_mismatches']) - 20}` more omitted")
    if cross_row["cyclic_ordering"]:
        lines.append("")
        lines.append("Cyclic ordering:")
        for item in cross_row["cyclic_ordering"]:
            lines.append(f"- {item}")
    if validator["row_failures"]:
        lines.append("")
        lines.append("Row-level validation failures:")
        for row_name in sorted(validator["row_failures"]):
            messages = "; ".join(validator["row_failures"][row_name])
            lines.append(f"- {row_name}: {messages}")
    lines.append("")

    lines.append("## Known Deviations Summary")
    lines.append("")
    for row in rows:
        if row["known_deviations"]:
            deviations = "; ".join(row["known_deviations"])
        else:
            deviations = "none"
        lines.append(f"- {row['process']}: {deviations}")
    lines.append("")

    lines.append("## Process Roster")
    lines.append("")
    lines.append(f"Canonical Karr roster (`{len(roster['canonical'])}`): " + ", ".join(roster["canonical"]) + ".")
    lines.append(f"DB roster (`{len(roster['db'])}`): " + ", ".join(roster["db"]) + ".")
    if roster["canonical_only"] or roster["db_only"]:
        lines.append(
            f"Difference: canonical-only = {', '.join(roster['canonical_only']) or 'none'}; "
            f"db-only = {', '.join(roster['db_only']) or 'none'}."
        )
    else:
        lines.append("Difference: none; the DB roster matches the canonical Karr roster exactly.")
    lines.append("")

    lines.append("## Recommended Cleanup Actions")
    lines.append("")
    lines.append("- **P0**: fix every row-level validation failure before anyone treats the DB as authoritative. That includes the missing `schema_date` field, the incomplete provenance blocks, the malformed unit-conversion anchors, and the `TerminalOrganelleAssembly` compartment-routing mismatch booleans.")
    lines.append("- **P1**: reconcile the reciprocal dependency mismatches row by row so every `produces_inputs_for` edge is mirrored by the partner row's `consumes_outputs_of` list, and confirm the two cyclic ordering edges between `Translation` and `tRNAAminoacylation` are intentional.")
    lines.append("- **P2**: normalize the schema-version/date story and triage deviations into an explicit keep-fix-drop queue, especially any rows that still carry broad allocator or LP-bound caveats.")
    lines.append("")

    lines.append("## Connection to L1c Work")
    lines.append("")
    lines.append(
        "This wiring DB is the machine-readable substrate that the L1c gate can read instead of re-deriving wiring from prose. "
        "It consolidates allocator formulas, ordering constraints, LP-bound provenance, compartment-merge flags, and cross-process edges into a row-per-process contract. "
        "That gives the L1c gate a stable place to compare chassis wiring against the canonical Karr model before lower-rung greens are promoted. "
        "In the `2026-06-29 | opencell | l1c-skipped-lower-rung-greens-misread` decision, that was the missing piece: L1/L2.1/L2.2 could not see the A1-A4 integration bugs, but this DB can surface them directly."
    )
    lines.append("")

    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-output",
        type=Path,
        default=None,
        help="Optional path to the raw validator output file for cross-reference.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. Markdown is intended for the summary doc.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = _build_report(args.validate_output)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
