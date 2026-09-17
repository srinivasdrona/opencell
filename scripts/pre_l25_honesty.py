#!/usr/bin/env python3
"""Validate the source-faithfulness baseline required before L2.5.

The lower gates answer narrower questions:

* L1b proves that runtime methods and wiring records are present and internally
  consistent, including records that truthfully disclose a deviation.
* L2.1/L2.2 prove isolated behavior under their registered oracle contracts.
* L2.4 proves short-horizon chassis conservation.

None of those gates alone proves that a process has no known implementation or
validation-configuration gap. This validator makes that final prerequisite
explicit and machine-checkable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "pre_l25"
    / "PRE_L25_HONESTY_BASELINE.yaml"
)
PROCESS_CATALOG = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
)
L2_2_EVIDENCE_INDEX = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "evidence_index.json"
)
METHOD_MAP = REPO_ROOT / "data" / "karr_method_inventory" / "oc_method_map.yaml"
WIRING_DIR = REPO_ROOT / "data" / "schemas" / "per_process_wiring"
PROCESS_SCHEMA_DIR = REPO_ROOT / "data" / "schemas" / "per_process"
AUDIT_DIR = REPO_ROOT / "docs" / "phase_f" / "audits"

ELIGIBILITY_VALUES = frozenset(
    {
        "ELIGIBLE",
        "BLOCKED_LOWER_GATE",
        "BLOCKED_CODE_DEVIATION",
        "BLOCKED_EVIDENCE_CONFIG_MISMATCH",
        "BLOCKED_STALE_OR_MISSING_AUDIT",
    }
)
FINDING_KINDS = frozenset(
    {
        "CODE_DEVIATION",
        "EVIDENCE_CONFIG_MISMATCH",
        "STALE_OR_MISSING_AUDIT",
        "REPRESENTATION_DIFFERENCE",
        "IMPLEMENTATION_SHAPE_DIFFERENCE",
    }
)
FINDING_DISPOSITIONS = frozenset(
    {
        "OPEN",
        "NEEDS_EXECUTION",
        "RESOLVED",
        "ACCEPTED_EQUIVALENT",
    }
)
BLOCKING_DISPOSITIONS = frozenset({"OPEN", "NEEDS_EXECUTION"})
BLOCKING_ELIGIBILITY_BY_KIND = {
    "CODE_DEVIATION": "BLOCKED_CODE_DEVIATION",
    "EVIDENCE_CONFIG_MISMATCH": "BLOCKED_EVIDENCE_CONFIG_MISMATCH",
    "STALE_OR_MISSING_AUDIT": "BLOCKED_STALE_OR_MISSING_AUDIT",
}
ELIGIBILITY_PRECEDENCE = (
    "BLOCKED_CODE_DEVIATION",
    "BLOCKED_EVIDENCE_CONFIG_MISMATCH",
    "BLOCKED_STALE_OR_MISSING_AUDIT",
)
LINE_SPAN_RE = re.compile(r"^(\d+)-(\d+)$")


@dataclass(frozen=True)
class BaselineAudit:
    integrity_ok: bool
    all_eligible: bool
    process_count: int
    eligible_count: int
    blocked_count: int
    problems: tuple[str, ...]
    blockers: tuple[str, ...]
    source_digest: str
    source_file_count: int


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _canonical_process_rows(root: Path) -> dict[str, dict[str, Any]]:
    path = root / PROCESS_CATALOG.relative_to(REPO_ROOT)
    data = _load_yaml(path)
    rows = data.get("processes")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must define a `processes` list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        if name in result:
            raise ValueError(f"duplicate process {name!r} in {path}")
        result[name] = row
    return result


def _method_map_rows(root: Path) -> dict[str, dict[str, Any]]:
    path = root / METHOD_MAP.relative_to(REPO_ROOT)
    data = _load_yaml(path)
    rows = data.get("processes")
    if not isinstance(rows, dict):
        raise ValueError(f"{path} must define a `processes` mapping")
    return {
        str(name): row
        for name, row in rows.items()
        if isinstance(name, str) and isinstance(row, dict)
    }


def _l2_2_rows(root: Path) -> dict[str, dict[str, Any]]:
    path = root / L2_2_EVIDENCE_INDEX.relative_to(REPO_ROOT)
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must define a `rows` list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("process", "")).strip()
        if not name:
            continue
        if name in result:
            raise ValueError(f"duplicate L2.2 evidence row {name!r}")
        result[name] = row
    return result


def _resolve_process_schema(root: Path, name: str) -> Path | None:
    schema_dir = root / PROCESS_SCHEMA_DIR.relative_to(REPO_ROOT)
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    candidates: list[Path] = []
    for path in schema_dir.glob("*.toml"):
        stem = re.sub(r"[^a-z0-9]", "", path.stem.lower())
        if stem == normalized:
            candidates.append(path)
    if len(candidates) > 1:
        raise ValueError(f"ambiguous per-process schema for {name}: {candidates}")
    return candidates[0] if candidates else None


def collect_source_dependencies(root: Path = REPO_ROOT) -> tuple[Path, ...]:
    """Return the tracked files whose changes invalidate this baseline."""
    catalog_rows = _canonical_process_rows(root)
    method_rows = _method_map_rows(root)
    paths: set[Path] = {
        root / PROCESS_CATALOG.relative_to(REPO_ROOT),
        root / L2_2_EVIDENCE_INDEX.relative_to(REPO_ROOT),
        root / METHOD_MAP.relative_to(REPO_ROOT),
        root / WIRING_DIR.relative_to(REPO_ROOT) / "_schema.yaml",
    }
    for name, catalog_row in catalog_rows.items():
        paths.add(root / WIRING_DIR.relative_to(REPO_ROOT) / f"{name}.yaml")
        paths.add(root / AUDIT_DIR.relative_to(REPO_ROOT) / f"{name}_semantic_audit.md")
        process_schema = _resolve_process_schema(root, name)
        if process_schema is not None:
            paths.add(process_schema)
        oc_module = str(catalog_row.get("oc_module", "")).strip()
        if oc_module:
            paths.add(root / Path(oc_module))
        method_row = method_rows.get(name, {})
        for value in method_row.get("oc_files", []):
            paths.add(root / Path(str(value)))
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def compute_source_digest(root: Path = REPO_ROOT) -> tuple[str, int]:
    records: list[dict[str, str]] = []
    for path in collect_source_dependencies(root):
        if not path.is_file():
            raise FileNotFoundError(f"baseline dependency missing: {path}")
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), len(records)


def _expected_eligibility(
    findings: list[dict[str, Any]],
    *,
    lower_gate_passed: bool,
) -> str:
    if not lower_gate_passed:
        return "BLOCKED_LOWER_GATE"
    blocking_values: set[str] = set()
    for finding in findings:
        if str(finding.get("disposition", "")).strip() not in BLOCKING_DISPOSITIONS:
            continue
        kind = str(finding.get("kind", "")).strip()
        blocking = BLOCKING_ELIGIBILITY_BY_KIND.get(kind)
        if blocking is not None:
            blocking_values.add(blocking)
    for value in ELIGIBILITY_PRECEDENCE:
        if value in blocking_values:
            return value
    return "ELIGIBLE"


def _validate_evidence(
    *,
    root: Path,
    process_name: str,
    finding_id: str,
    evidence: Any,
    problems: list[str],
) -> None:
    if not isinstance(evidence, list) or not evidence:
        problems.append(f"{process_name}/{finding_id}: evidence must be a non-empty list")
        return
    for index, item in enumerate(evidence):
        label = f"{process_name}/{finding_id}/evidence[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label}: entry must be a mapping")
            continue
        path_text = str(item.get("path", "")).strip()
        lines_text = str(item.get("lines", "")).strip()
        if not path_text:
            problems.append(f"{label}: missing path")
            continue
        path = root / Path(path_text)
        if not path.is_file():
            problems.append(f"{label}: path does not exist: {path_text}")
            continue
        match = LINE_SPAN_RE.fullmatch(lines_text)
        if match is None:
            problems.append(f"{label}: invalid inclusive line span {lines_text!r}")
            continue
        start, end = int(match.group(1)), int(match.group(2))
        line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if start <= 0 or end < start or end > line_count:
            problems.append(
                f"{label}: line span {lines_text} outside 1-{line_count} for {path_text}"
            )


def audit_baseline(
    baseline_path: Path = DEFAULT_BASELINE,
    *,
    root: Path = REPO_ROOT,
    expected_process_count: int | None = 28,
) -> BaselineAudit:
    problems: list[str] = []
    blockers: list[str] = []
    try:
        baseline = _load_yaml(baseline_path)
        canonical_rows = _canonical_process_rows(root)
        l2_2_rows = _l2_2_rows(root)
        actual_digest, actual_file_count = compute_source_digest(root)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return BaselineAudit(
            integrity_ok=False,
            all_eligible=False,
            process_count=0,
            eligible_count=0,
            blocked_count=0,
            problems=(str(exc),),
            blockers=(),
            source_digest="",
            source_file_count=0,
        )

    if str(baseline.get("schema_version", "")) != "1.0":
        problems.append("schema_version must be '1.0'")
    declared_count = baseline.get("canonical_process_count")
    if declared_count != len(canonical_rows):
        problems.append(
            "canonical_process_count mismatch: "
            f"baseline={declared_count}, catalog={len(canonical_rows)}"
        )
    if expected_process_count is not None and len(canonical_rows) != expected_process_count:
        problems.append(
            f"canonical process denominator drift: expected {expected_process_count}, "
            f"found {len(canonical_rows)}"
        )

    source_tree = baseline.get("source_tree")
    if not isinstance(source_tree, dict):
        problems.append("source_tree must be a mapping")
    else:
        if source_tree.get("sha256") != actual_digest:
            problems.append(
                "source_tree.sha256 is stale: "
                f"baseline={source_tree.get('sha256')}, current={actual_digest}"
            )
        if source_tree.get("file_count") != actual_file_count:
            problems.append(
                "source_tree.file_count mismatch: "
                f"baseline={source_tree.get('file_count')}, current={actual_file_count}"
            )

    process_entries = baseline.get("processes")
    if not isinstance(process_entries, list):
        problems.append("processes must be a list")
        process_entries = []

    by_name: dict[str, dict[str, Any]] = {}
    finding_ids: set[str] = set()
    eligible_count = 0
    for entry in process_entries:
        if not isinstance(entry, dict):
            problems.append("process entry must be a mapping")
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            problems.append("process entry missing name")
            continue
        if name in by_name:
            problems.append(f"duplicate process entry: {name}")
            continue
        by_name[name] = entry

        eligibility = str(entry.get("eligibility", "")).strip()
        if eligibility not in ELIGIBILITY_VALUES:
            problems.append(f"{name}: invalid eligibility {eligibility!r}")

        behavior_gate = str(entry.get("behavior_gate", "")).strip()
        behavior_verdict = str(entry.get("behavior_verdict", "")).strip()
        lower_gate_passed = False
        catalog_row = canonical_rows.get(name, {})
        in_scope_l2_2 = bool(catalog_row.get("in_scope_L2_2", False))
        expected_gate = "L2.2" if in_scope_l2_2 else "L2.1"
        if behavior_gate != expected_gate:
            problems.append(
                f"{name}: behavior_gate={behavior_gate!r}, expected {expected_gate!r}"
            )
        if behavior_gate == "L2.2":
            evidence_row = l2_2_rows.get(name)
            if evidence_row is None:
                problems.append(f"{name}: no L2.2 evidence row")
            else:
                current_verdict = str(evidence_row.get("mechanical_verdict", ""))
                if behavior_verdict != current_verdict:
                    problems.append(
                        f"{name}: behavior_verdict={behavior_verdict!r}, "
                        f"L2.2 evidence={current_verdict!r}"
                    )
                if current_verdict != "PASS":
                    blockers.append(f"{name}: L2.2 verdict is {current_verdict}")
                lower_gate_passed = current_verdict == "PASS"
        elif behavior_verdict != "GENUINE":
            blockers.append(f"{name}: L2.1 verdict is {behavior_verdict or '<missing>'}")
        else:
            lower_gate_passed = True

        findings = entry.get("findings")
        if not isinstance(findings, list):
            problems.append(f"{name}: findings must be a list")
            findings = []
        for finding in findings:
            if not isinstance(finding, dict):
                problems.append(f"{name}: finding must be a mapping")
                continue
            finding_id = str(finding.get("id", "")).strip()
            kind = str(finding.get("kind", "")).strip()
            disposition = str(finding.get("disposition", "")).strip()
            summary = str(finding.get("summary", "")).strip()
            if not finding_id:
                problems.append(f"{name}: finding missing id")
                finding_id = "<missing>"
            elif finding_id in finding_ids:
                problems.append(f"duplicate finding id: {finding_id}")
            finding_ids.add(finding_id)
            if kind not in FINDING_KINDS:
                problems.append(f"{name}/{finding_id}: invalid kind {kind!r}")
            if disposition not in FINDING_DISPOSITIONS:
                problems.append(
                    f"{name}/{finding_id}: invalid disposition {disposition!r}"
                )
            if not summary:
                problems.append(f"{name}/{finding_id}: summary is required")
            if (
                disposition in BLOCKING_DISPOSITIONS
                and kind not in BLOCKING_ELIGIBILITY_BY_KIND
            ):
                problems.append(
                    f"{name}/{finding_id}: blocking disposition {disposition} "
                    f"is invalid for nonblocking kind {kind}"
                )
            _validate_evidence(
                root=root,
                process_name=name,
                finding_id=finding_id,
                evidence=finding.get("evidence"),
                problems=problems,
            )
            if disposition in BLOCKING_DISPOSITIONS:
                blockers.append(f"{name}/{finding_id}: {summary or kind}")

        expected_eligibility = _expected_eligibility(
            findings,
            lower_gate_passed=lower_gate_passed,
        )
        if eligibility != expected_eligibility:
            problems.append(
                f"{name}: eligibility={eligibility!r}, derived={expected_eligibility!r}"
            )
        if eligibility == "ELIGIBLE":
            eligible_count += 1

    canonical_names = set(canonical_rows)
    baseline_names = set(by_name)
    if canonical_names != baseline_names:
        missing = sorted(canonical_names - baseline_names)
        extra = sorted(baseline_names - canonical_names)
        problems.append(f"process registry mismatch: missing={missing}, extra={extra}")

    summary = baseline.get("summary")
    blocked_count = len(canonical_names) - eligible_count
    if not isinstance(summary, dict):
        problems.append("summary must be a mapping")
    else:
        expected_summary = {
            "eligible": eligible_count,
            "blocked": blocked_count,
        }
        for key, expected in expected_summary.items():
            if summary.get(key) != expected:
                problems.append(
                    f"summary.{key} mismatch: baseline={summary.get(key)}, derived={expected}"
                )

    integrity_ok = not problems
    return BaselineAudit(
        integrity_ok=integrity_ok,
        all_eligible=integrity_ok and eligible_count == len(canonical_names),
        process_count=len(canonical_names),
        eligible_count=eligible_count,
        blocked_count=blocked_count,
        problems=tuple(problems),
        blockers=tuple(blockers),
        source_digest=actual_digest,
        source_file_count=actual_file_count,
    )


def _print_report(result: BaselineAudit) -> None:
    print(
        "PRE-L2.5 HONESTY BASELINE: "
        f"{'INTEGRITY_OK' if result.integrity_ok else 'INTEGRITY_FAIL'}; "
        f"eligible={result.eligible_count}/{result.process_count}; "
        f"blocked={result.blocked_count}"
    )
    print(
        f"source_tree_sha256={result.source_digest} "
        f"files={result.source_file_count}"
    )
    for problem in result.problems:
        print(f"PROBLEM: {problem}")
    for blocker in result.blockers:
        print(f"BLOCKER: {blocker}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "source-digest"))
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--require-all-eligible",
        action="store_true",
        help="Return nonzero when any canonical process remains blocked.",
    )
    args = parser.parse_args(argv)

    if args.command == "source-digest":
        digest, count = compute_source_digest(REPO_ROOT)
        print(f"{digest} {count}")
        return 0

    result = audit_baseline(args.baseline)
    _print_report(result)
    if not result.integrity_ok:
        return 1
    if args.require_all_eligible and not result.all_eligible:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
