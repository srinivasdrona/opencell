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

from scripts.l2_event.registry import registry_sha256
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


def _git_commit_exists(sha: str) -> bool | None:
    """Check whether ``sha`` (already validated by the caller to look like
    a real 40-hex git commit sha) exists as a real commit in this repo's
    history (Opus5 review round 3, item #4: "audit verifies git_sha ...,
    not merely stores").

    Returns ``True``/``False`` when git could actually be invoked against
    this worktree, and ``None`` when git itself could not be run at all
    (e.g. a bare temp directory with no ``.git``, as
    ``test_fresh_clone_audit_works_from_tracked_bundle_only`` uses, or any
    other environment where git is genuinely unavailable) -- callers must
    treat ``None`` as "unable to check, not a problem" so a fresh-clone or
    non-repo test fixture is never penalized for something the audit
    cannot actually verify there.
    """

    def _try(git_dir_args: list[str]) -> bool | None:
        try:
            out = subprocess.run(
                ["git", *git_dir_args, "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return None
        if "not a git repository" in (out.stderr or "").lower():
            return None
        return out.returncode == 0

    result = _try([])
    if result is not None:
        return result
    # Windows-worktree gitdir-translation fallback (see
    # _translate_windows_gitdir's docstring for why this is needed).
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
    except Exception:
        return None
    return _try([f"--git-dir={translated}"])


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
    normalizing ``input_manifest.json``'s recorded paths AND
    ``provenance.json``'s ``karr_source`` field to repo-relative POSIX
    strings (never an absolute worktree path in the tracked bundle).

    The ``karr_source`` normalization (Opus5 review round 3, item #4/#5)
    closes a gap the ``input_manifest.json`` normalization already handled:
    before this fix, only the manifest's input paths were made portable --
    ``provenance.json``'s own ``karr_source`` field still recorded whatever
    absolute worktree path (e.g. ``E:\\opencell-worktrees\\...``) the run
    happened to be generated from, which would never match on a different
    machine/clone and made ``audit_index``'s karr_source-vs-manifest
    consistency check (below) meaningless.
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
        if filename == "provenance.json":
            karr_source = payload.get("karr_source")
            if karr_source:
                payload["karr_source"] = relative_to_repo(Path(karr_source))
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

    Opus5 review round 3 additions (items #4/#5) -- each new check below is
    deliberately gated so it is a no-op against the existing
    ``test_l2_event_evidence.py`` fake fixtures (which use placeholder
    values like ``git_sha="deadbeef"`` and never set ``registry_sha256``/
    ``karr_source`` at all), and only activates for real/deliberately-forged
    provenance:

    * "exact coverage" (item #5): the recorded artifact filename set must
      equal :data:`MANDATORY_FILES` exactly (not just "hash matches for
      whatever happens to be recorded"), and the evidence directory must
      not contain unexpected extra files beyond those.
    * git_sha (item #4): only checked when it looks like a real 40-hex
      commit sha (``_git_commit_exists`` returns ``None`` -- "can't check,
      not a problem" -- for short placeholders and for environments where
      git itself can't run, e.g. the fresh-clone bare-tempdir test).
    * registry_sha256 (item #4): only checked when the key is present at
      all, against the registry file's OWN current hash (not merely
      re-storing what was recorded).
    * karr_source (item #4): only checked when the key is present, cross-
      referenced against ``input_manifest.json``'s own recorded input
      directories for internal consistency.
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

        recorded_files = set(artifact_hashes)
        if recorded_files != set(MANDATORY_FILES):
            missing = sorted(set(MANDATORY_FILES) - recorded_files)
            extra = sorted(recorded_files - set(MANDATORY_FILES))
            problems.append(
                f"{row['process']}: recorded artifact set {sorted(recorded_files)} does "
                f"not exactly cover MANDATORY_FILES {sorted(MANDATORY_FILES)} "
                f"(missing={missing}, extra={extra}) (item #5 exact coverage)."
            )
        if process_dir.exists():
            on_disk = {p.name for p in process_dir.iterdir() if p.is_file()}
            unexpected = sorted(on_disk - set(MANDATORY_FILES))
            if unexpected:
                problems.append(
                    f"{row['process']}: unexpected file(s) {unexpected} present in "
                    f"{relative_to_repo(process_dir)} beyond MANDATORY_FILES "
                    "(item #5 exact coverage)."
                )

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

        provenance_path = process_dir / "provenance.json"
        if provenance_path.exists():
            provenance = read_json(provenance_path)
            git_sha = provenance.get("git_sha")
            if git_sha and re.match(r"^[0-9a-f]{40}$", git_sha):
                commit_exists = _git_commit_exists(git_sha)
                if commit_exists is False:
                    problems.append(
                        f"{row['process']}: provenance.json git_sha={git_sha!r} does not "
                        "exist as a real commit in this repository's history (item #4)."
                    )
            registry_sha = provenance.get("registry_sha256")
            if registry_sha:
                actual_registry_sha = registry_sha256()
                if registry_sha != actual_registry_sha:
                    problems.append(
                        f"{row['process']}: provenance.json registry_sha256="
                        f"{registry_sha[:12]}... does not match the registry's actual "
                        f"current hash {actual_registry_sha[:12]}... (item #4)."
                    )
            karr_source = provenance.get("karr_source")
            if karr_source:
                input_manifest_path = process_dir / "input_manifest.json"
                if input_manifest_path.exists():
                    manifest = read_json(input_manifest_path)
                    manifest_dirs = {
                        Path(entry["path"]).parent.as_posix()
                        for entry in manifest.get("inputs", [])
                        if entry.get("path")
                    }
                    karr_source_posix = str(karr_source).replace("\\", "/")
                    if manifest_dirs and karr_source_posix not in manifest_dirs:
                        problems.append(
                            f"{row['process']}: provenance.json karr_source="
                            f"{karr_source_posix!r} does not match input_manifest.json's "
                            f"recorded input directory/directories {sorted(manifest_dirs)} "
                            "(item #4)."
                        )
    recomputed = _content_hash(index)
    if recomputed != index.get("content_hash"):
        problems.append(
            f"content_hash mismatch: recorded={index.get('content_hash')}, recomputed={recomputed}"
        )
    return problems
