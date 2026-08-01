"""Portable evidence index + sidecar writer for L2.event (S8/S9, requirement 5).

Layout (mirrors ``scripts/l22_evidence``'s live/tracked split so fresh-clone
audits work without any raw MAT data present):

* Live, gitignored run artifacts:
  ``artifacts/l2_event/<Process>/<run_id>/{result.json, input_manifest.json,
  null_calibration.json, provenance.json, SUMMARY.json}``
* Tracked, portable bundle (paths normalized to repo-relative POSIX, no
  absolute worktree paths committed):
  ``docs/phase_f/l2_event/evidence_bundle/<Process>/{same 5 files}``
* Tracked compact index:
  ``docs/phase_f/l2_event/evidence_index.json``

This is a **separate** index from ``docs/phase_f/l2_2_design_a/evidence_index.json``
-- L2.event results must never be silently folded into the Design-A
scoreboard (surface S9).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.l2_event.schema import (
    EVIDENCE_INDEX_SCHEMA_VERSION,
    read_json,
    write_json_atomic,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

LIVE_EVIDENCE_ROOT = _REPO_ROOT / "artifacts" / "l2_event"
TRACKED_BUNDLE_ROOT = _REPO_ROOT / "docs" / "phase_f" / "l2_event" / "evidence_bundle"
TRACKED_INDEX_PATH = _REPO_ROOT / "docs" / "phase_f" / "l2_event" / "evidence_index.json"

MANDATORY_FILES = (
    "result.json",
    "input_manifest.json",
    "null_calibration.json",
    "provenance.json",
    "SUMMARY.json",
)


class EvidenceIntegrityError(Exception):
    """Raised by :func:`audit_index` when a tracked artifact's recorded
    hash no longer matches the file on disk (tamper/stale detection)."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative_to_repo(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def default_evidence_root() -> Path:
    """Return the tracked portable bundle root.

    Indexing/audit always reads from the *bundled* (flattened,
    run-id-stripped) tracked copy, never the live per-run-id scratch tree
    under ``artifacts/l2_event/<process>/<run_id>/`` -- ``_row_for_process``
    expects ``<root>/<process>/<file>`` directly, one level shallower than
    the live layout. This is also what makes a fresh-clone audit work with
    zero live-run history (requirement 5): the tracked bundle is the only
    copy that ships in git."""
    return TRACKED_BUNDLE_ROOT


def _translate_windows_gitdir(path: str) -> str | None:
    """Translate a Windows-style absolute path (``E:/foo/bar``) to the
    equivalent WSL mount path (``/mnt/e/foo/bar``).

    Git worktree admin files (``.git`` gitlinks, ``.git/worktrees/<name>/gitdir``)
    are written with whatever path style the git client used to create the
    worktree. On this project, worktrees are created from Windows git, so the
    linked ``.git`` file's ``gitdir:`` line is a Windows absolute path. A
    Linux-hosted ``git`` binary (invoked via WSL, as ``bin/oc-py`` always
    does) cannot resolve that path directly and silently fails with
    "not a git repository" -- it needs the ``/mnt/<drive>/...`` equivalent.
    Returns ``None`` if ``path`` is not a recognizable Windows absolute path.
    """
    match = re.match(r"^([A-Za-z]):[/\\](.*)$", path.strip())
    if not match:
        return None
    drive, rest = match.groups()
    return f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"


def current_git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0:
            sha = out.stdout.strip()
            if sha:
                return sha
    except Exception:
        pass
    # Fallback for worktrees whose `.git` gitlink stores a Windows-style
    # absolute gitdir path that a WSL-hosted `git` cannot resolve directly
    # (see _translate_windows_gitdir docstring).
    try:
        git_file = _REPO_ROOT / ".git"
        if not git_file.is_file():
            return None
        content = git_file.read_text().strip()
        if not content.startswith("gitdir:"):
            return None
        gitdir = content.split(":", 1)[1].strip()
        translated = _translate_windows_gitdir(gitdir)
        if translated is None:
            return None
        out = subprocess.run(
            ["git", f"--git-dir={translated}", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip() or None
    except Exception:
        return None


def write_run_artifacts(process: str, run_id: str, artifacts: dict[str, dict[str, Any]]) -> Path:
    """Write one run's artifact set atomically under
    ``artifacts/l2_event/<process>/<run_id>/``.

    ``artifacts`` keys must all be members of :data:`MANDATORY_FILES` --
    a caller supplying an unrecognized filename is a bug, not silently
    tolerated.
    """
    unknown = set(artifacts) - set(MANDATORY_FILES)
    if unknown:
        raise ValueError(f"Unrecognized artifact filenames: {sorted(unknown)}")
    run_dir = LIVE_EVIDENCE_ROOT / process / run_id
    for filename, payload in artifacts.items():
        write_json_atomic(run_dir / filename, payload)
    return run_dir


def bundle_run(run_dir: Path, process: str) -> Path:
    """Copy a live run's mandatory files into the tracked portable bundle,
    normalizing ``input_manifest.json``'s recorded paths to repo-relative
    POSIX strings (never an absolute worktree path in the tracked bundle).
    """
    missing = [f for f in MANDATORY_FILES if not (run_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Missing mandatory artifact(s) {missing} in {run_dir}")

    bundle_dir = TRACKED_BUNDLE_ROOT / process
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for filename in MANDATORY_FILES:
        payload = read_json(run_dir / filename)
        if filename == "input_manifest.json":
            for entry in payload.get("inputs", []):
                entry["path"] = relative_to_repo(Path(entry["path"]))
        write_json_atomic(bundle_dir / filename, payload)
    return bundle_dir


@dataclass(frozen=True)
class ProcessEvidenceRow:
    process: str
    evidence_dir: str
    artifact_hashes: dict[str, str]
    mode: str
    verdict: str | None


def _row_for_process(process: str, evidence_root: Path) -> ProcessEvidenceRow | None:
    process_dir = evidence_root / process
    if not process_dir.exists():
        return None
    missing = [f for f in MANDATORY_FILES if not (process_dir / f).exists()]
    if missing:
        return ProcessEvidenceRow(
            process=process,
            evidence_dir=relative_to_repo(process_dir),
            artifact_hashes={},
            mode="INCOMPLETE",
            verdict=None,
        )
    hashes = {f: sha256_file(process_dir / f) for f in MANDATORY_FILES}
    result = read_json(process_dir / "result.json")
    return ProcessEvidenceRow(
        process=process,
        evidence_dir=relative_to_repo(process_dir),
        artifact_hashes=hashes,
        mode=str(result.get("mode", "unknown")),
        verdict=result.get("verdict"),
    )


def build_index(processes: list[str], evidence_root: Path | None = None) -> dict[str, Any]:
    evidence_root = evidence_root or default_evidence_root()
    rows = []
    for process in processes:
        row = _row_for_process(process, evidence_root)
        if row is not None:
            rows.append(row)
    index = {
        "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_root": relative_to_repo(evidence_root),
        "git_sha": current_git_sha(),
        "n_rows": len(rows),
        "rows": [
            {
                "process": r.process,
                "evidence_dir": r.evidence_dir,
                "artifact_hashes": r.artifact_hashes,
                "mode": r.mode,
                "verdict": r.verdict,
            }
            for r in rows
        ],
    }
    index["content_hash"] = _content_hash(index)
    return index


def _content_hash(index: dict[str, Any]) -> str:
    """Hash of the index contents, excluding volatile fields
    (``generated_at``, ``content_hash`` itself, and each row's own
    ``evidence_dir`` -- matches ``scripts/l22_evidence/generator.py``'s
    convention so a rerun in a different worktree location doesn't spuriously
    change the hash).

    M-metric-correctness ("bind git_sha in stable integrity where
    practical"): ``git_sha`` IS included here (unlike ``generated_at``,
    which is genuinely volatile per-run) so tampering with the recorded
    commit provenance is caught by ``audit_index``'s content_hash
    comparison, not just a per-file artifact hash mismatch. Full
    cryptographic binding (e.g. signing) is out of scope for this
    foundation task -- this only makes git_sha part of the *existing*
    content-hash tamper check."""
    import json

    stable = {
        "schema_version": index["schema_version"],
        "git_sha": index.get("git_sha"),
        "rows": [
            {
                "process": r["process"],
                "artifact_hashes": r["artifact_hashes"],
                "mode": r["mode"],
                "verdict": r["verdict"],
            }
            for r in index["rows"]
        ],
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def write_index(processes: list[str], evidence_root: Path | None = None) -> Path:
    index = build_index(processes, evidence_root=evidence_root)
    write_json_atomic(TRACKED_INDEX_PATH, index)
    return TRACKED_INDEX_PATH


def audit_index(index_path: Path = TRACKED_INDEX_PATH) -> list[str]:
    """Recompute every hash the index claims and compare. Returns a list
    of problems (empty = integrity OK). Raises FileNotFoundError if the
    index itself is missing.

    M6 (Opus5 review): an ``INCOMPLETE`` row (missing mandatory artifacts,
    empty ``artifact_hashes``) has nothing to hash-check, so the loop below
    silently produces zero problems for it -- this must be an explicit,
    reported problem instead of a silent pass. Likewise an evidence
    directory that exists but produced zero recorded hashes for a
    non-INCOMPLETE row is itself suspicious and must be flagged.
    """
    index = read_json(index_path)
    problems: list[str] = []
    evidence_root = _REPO_ROOT / index["evidence_root"]
    for row in index.get("rows", []):
        process_dir = evidence_root / row["process"]
        artifact_hashes = row.get("artifact_hashes", {})
        if row.get("mode") == "INCOMPLETE" or not artifact_hashes:
            problems.append(
                f"{row['process']}: evidence row has mode={row.get('mode')!r} "
                f"with {'no' if not artifact_hashes else len(artifact_hashes)} "
                "recorded artifact hash(es) -- an incomplete/empty-hash row "
                "cannot be a silent audit pass (M6)."
            )
            continue
        for filename, recorded_hash in artifact_hashes.items():
            path = process_dir / filename
            if not path.exists():
                problems.append(f"{row['process']}/{filename}: file missing at {path}")
                continue
            actual_hash = sha256_file(path)
            if actual_hash != recorded_hash:
                problems.append(
                    f"{row['process']}/{filename}: sha256 mismatch "
                    f"(recorded={recorded_hash[:12]}..., actual={actual_hash[:12]}...)"
                )
    recomputed = _content_hash(index)
    if recomputed != index.get("content_hash"):
        problems.append(
            f"content_hash mismatch: recorded={index.get('content_hash')}, recomputed={recomputed}"
        )
    return problems
