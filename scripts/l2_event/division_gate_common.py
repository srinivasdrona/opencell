"""Shared fail-closed plumbing for the division N=20 gate surfaces.

This module owns only cohort selection and artifact placement. Process
semantics remain in the Cytokinesis and FtsZPolymerization gate modules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from scripts.l2_event import division_cohort_selector
from scripts.l2_event.division_window_spec import required_completed_windows
from scripts.l22_evidence import catalog as l22_catalog
from scripts.l22_evidence import schema as l22_schema
from scripts.l22_evidence import sweep as l22_sweep
from scripts.l22_evidence import verdict as l22_verdict
from scripts.l22_evidence.populate import _git_dirty, _git_sha

GateMode = Literal["pilot", "authority"]

PILOT_ROOT = l22_catalog.REPO_ROOT / "artifacts" / "division_n20_pilots"


class DivisionGateRefusalError(RuntimeError):
    """Raised when cohort or output preconditions forbid a gate run."""


@dataclass(frozen=True)
class DivisionGateContext:
    mode: GateMode
    source_root: Path
    selected_seeds: tuple[int, ...]
    audit: division_cohort_selector.CohortAudit

    @property
    def authoritative(self) -> bool:
        return self.mode == "authority"

    @property
    def cohort_status(self) -> str:
        if self.authoritative:
            return "AUTHORITATIVE_N20"
        if len(self.selected_seeds) < required_completed_windows():
            return "PILOT_INSUFFICIENT_ENSEMBLE"
        return "PILOT_NON_AUTHORITATIVE"


def resolve_gate_context(*, source_root: Path, mode: GateMode) -> DivisionGateContext:
    """Resolve the exact selector-owned seed cohort for one gate run.

    ``source_root`` is mandatory at every CLI surface. No sibling-worktree
    scan or fallback root is permitted here: the caller must name the
    curated cohort root explicitly.
    """
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise DivisionGateRefusalError(f"source root does not exist or is not a directory: {root}")
    if mode not in ("pilot", "authority"):
        raise DivisionGateRefusalError(f"unsupported gate mode: {mode!r}")

    audit = division_cohort_selector.audit_cohort(
        search_roots=[root],
        authoritative_root=root,
    )
    selected = tuple(audit.selected_seeds)
    required = required_completed_windows()

    if mode == "authority":
        if not audit.selection_satisfied or len(selected) != required:
            raise DivisionGateRefusalError(
                "authoritative division evidence requires exactly "
                f"N={required} selector-owned COMPLETED windows; got "
                f"selected={len(selected)}, completed={audit.completed_count}, "
                f"selection_satisfied={audit.selection_satisfied}. Censors never "
                "count, and premature/noncontiguous seeds are never substituted."
            )
        if audit.duplicate_trace_hashes or audit.source_hash_mismatches:
            raise DivisionGateRefusalError(
                "authoritative division evidence refused because cohort integrity "
                "findings remain: duplicate_trace_hashes="
                f"{audit.duplicate_trace_hashes}, source_hash_mismatches="
                f"{audit.source_hash_mismatches}"
            )
    elif not selected:
        raise DivisionGateRefusalError(
            "pilot mode needs at least one selector-owned COMPLETED window; "
            "no completed seeds are currently eligible."
        )
    if audit.duplicate_trace_hashes or audit.source_hash_mismatches:
        raise DivisionGateRefusalError(
            "division cohort integrity failure: duplicate/copy hashes and "
            "mixed source identity are rejected in pilot and authority modes; "
            f"duplicate_trace_hashes={audit.duplicate_trace_hashes}, "
            f"source_hash_mismatches={audit.source_hash_mismatches}"
        )

    return DivisionGateContext(
        mode=mode,
        source_root=root,
        selected_seeds=selected,
        audit=audit,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative_or_absolute(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(l22_catalog.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def portable_oracle_path(path: Path) -> str:
    """Return a portable repo-relative oracle-data suffix when possible."""
    normalized = Path(path).resolve().as_posix()
    marker = "/data/"
    if marker in normalized:
        return "data/" + normalized.split(marker, 1)[1]
    return str(Path(path).resolve())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def pilot_output_dir(process: str) -> Path:
    return PILOT_ROOT / process


def authority_output_dir(process: str, harness_type: str) -> Path:
    entry = l22_catalog.in_scope_processes()[process]
    if entry.harness_type != harness_type:
        raise DivisionGateRefusalError(
            f"{process} catalog harness_type={entry.harness_type!r}, expected {harness_type!r}"
        )
    subdir = l22_schema.subdir_for_harness(harness_type)
    return l22_schema.EVIDENCE_ROOT / process / subdir


def write_pilot_report(*, process: str, payload: dict[str, Any]) -> Path:
    """Write a diagnostic pilot report outside every authority location."""
    out_dir = pilot_output_dir(process)
    if l22_schema.BUNDLE_ROOT in out_dir.parents or l22_schema.EVIDENCE_ROOT in out_dir.parents:
        raise DivisionGateRefusalError(
            f"pilot output path overlaps an authority root: {out_dir}"
        )
    path = out_dir / "pilot_report.json"
    write_json(path, payload)
    return path


def _verify_input_hashes(inputs: list[dict[str, Any]]) -> None:
    for record in inputs:
        path = Path(str(record.get("_verify_path", record["path"])))
        if not path.is_absolute():
            path = l22_catalog.REPO_ROOT / path
        if not path.is_file():
            raise DivisionGateRefusalError(f"authority input no longer exists: {path}")
        actual = sha256_file(path)
        if actual != record.get("sha256"):
            raise DivisionGateRefusalError(
                f"authority input hash drift for {path}: "
                f"recorded={record.get('sha256')}, actual={actual}"
            )


def write_authority_bundle(
    *,
    process: str,
    harness_type: str,
    result: dict[str, Any],
    inputs: list[dict[str, Any]],
    thresholds: dict[str, Any],
    null_calibration: dict[str, Any],
    summary: dict[str, Any],
    analytical_check: dict[str, Any],
) -> Path:
    """Write a live, gitignored L2.2 authority bundle at exactly N=20.

    This never writes the tracked portable bundle. The existing
    ``generator bundle`` command remains the sole tracked-bundle writer.
    """
    entry = l22_catalog.in_scope_processes()[process]
    expected_n = required_completed_windows()
    seeds = result.get("seeds")
    if (
        not isinstance(seeds, list)
        or len(seeds) != expected_n
        or len(set(int(seed) for seed in seeds)) != expected_n
    ):
        raise DivisionGateRefusalError(
            f"refusing authority write for {process}: result must carry exactly "
            f"{expected_n} unique selected seeds, got {seeds!r}"
        )
    if entry.n_seeds != expected_n:
        raise DivisionGateRefusalError(
            f"refusing authority write for {process}: catalog N_seeds="
            f"{entry.n_seeds}, selector requires {expected_n}"
        )
    if result.get("ticks") != entry.m_ticks:
        raise DivisionGateRefusalError(
            f"refusing authority write for {process}: result ticks="
            f"{result.get('ticks')!r}, catalog M_ticks={entry.m_ticks!r}"
        )
    if entry.harness_type != harness_type:
        raise DivisionGateRefusalError(
            f"refusing authority write for {process}: catalog harness_type="
            f"{entry.harness_type!r}, requested {harness_type!r}"
        )

    _verify_input_hashes(inputs)
    output_dir = authority_output_dir(process, harness_type)
    if l22_schema.BUNDLE_ROOT in output_dir.parents:
        raise DivisionGateRefusalError(
            "division gate code must never write the tracked portable authority bundle"
        )

    manifest_inputs = [
        {key: value for key, value in record.items() if not key.startswith("_")}
        for record in inputs
    ]
    input_manifest = {
        "process": process,
        "resolved_seeds": [int(seed) for seed in seeds],
        "m_ticks": entry.m_ticks,
        "seed_selection": {
            "selector": "division_cohort_selector",
            "required_completed_windows": expected_n,
            "selected_seeds": [int(seed) for seed in seeds],
        },
        "inputs": manifest_inputs,
    }
    provenance = {
        "process": process,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(l22_catalog.REPO_ROOT),
        "git_dirty": _git_dirty(l22_catalog.REPO_ROOT),
        "gate_kind": harness_type,
        "cohort_selector": "scripts/l2_event/division_cohort_selector.py",
    }
    payloads = {
        "result.json": result,
        "input_manifest.json": input_manifest,
        "provenance.json": provenance,
        "thresholds.json": thresholds,
        "null_calibration.json": null_calibration,
        "SUMMARY.json": summary,
        "analytical_check.json": analytical_check,
    }
    for filename, payload in payloads.items():
        write_json(output_dir / filename, payload)

    sidecar_hashes = {
        filename: l22_sweep._sha256_file(output_dir / filename)
        for filename in l22_schema.SWEEP_PROVENANCE_SIDECAR_FILES
    }
    sweep_provenance = {
        "schema_version": l22_schema.SWEEP_PROVENANCE_SCHEMA_VERSION,
        "process": process,
        "n_seeds": entry.n_seeds,
        "m_ticks": entry.m_ticks,
        "completion_status": l22_schema.COMPLETION_STATUS_COMPLETE,
        "git_sha": _git_sha(l22_catalog.REPO_ROOT),
        "git_dirty": _git_dirty(l22_catalog.REPO_ROOT),
        "source_hashes": l22_sweep.current_source_hashes(
            entry.oc_module,
            process=process,
            harness_type=harness_type,
        ),
        "sidecar_hashes": sidecar_hashes,
        "inputs_verified": True,
        "evaluator_schema_version": l22_verdict.EVALUATOR_SCHEMA_VERSION,
        "result_schema_version": l22_schema.RESULT_SCHEMA_VERSION,
        "written_at": datetime.now(UTC).isoformat(),
    }
    write_json(output_dir / l22_schema.SWEEP_PROVENANCE_FILE, sweep_provenance)
    return output_dir


__all__ = [
    "DivisionGateContext",
    "DivisionGateRefusalError",
    "GateMode",
    "authority_output_dir",
    "pilot_output_dir",
    "portable_oracle_path",
    "repo_relative_or_absolute",
    "resolve_gate_context",
    "sha256_file",
    "write_authority_bundle",
    "write_pilot_report",
]
