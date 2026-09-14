"""Fail-closed one-shot migration for newly registered process imports.

This migration adds only dependency hashes that were omitted from an
otherwise-current ``sweep_provenance.json``. It never reruns or rewrites
biology. For each row it requires an explicit evidence-source ref and proves:

* the ref is bound to the evidence, either by matching the sentinel's
  ``git_sha`` or by containing byte-identical copies of every authority and
  mandatory sidecar file;
* every newly registered dependency exists at that ref and has bytes
  identical to the current tree;
* every pre-existing source hash and sidecar hash still matches current
  bytes.

Only then are the missing dependency keys added atomically to
``sweep_provenance.json["source_hashes"]``. No other file or field changes.

CLI::

    bin\\oc-py scripts/l22_evidence/migrate_import_dependency_provenance.py \
      --source-ref Replication=<ref> --source-ref DNADamage=<ref> --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema, sweep  # noqa: E402
from scripts.l22_evidence.populate import _resolve_worktree_gitdir  # noqa: E402

REPO_ROOT = cat.REPO_ROOT

NEW_DEPENDENCY_KEYS: dict[str, tuple[str, ...]] = {
    "Replication": ("m1_protein_complexes_module", "util_module"),
    "DNADamage": ("karr_dna_damage_rng_module",),
}

STATUS_MIGRATED = "MIGRATED"
STATUS_WOULD_MIGRATE = "WOULD_MIGRATE"
STATUS_ALREADY_MIGRATED = "ALREADY_MIGRATED"
STATUS_NO_EVIDENCE = "NO_EVIDENCE"
STATUS_HARNESS_MISMATCH = "SKIPPED_HARNESS_MISMATCH"
STATUS_PARTIAL_MIGRATION = "SKIPPED_PARTIAL_MIGRATION"
STATUS_SOURCE_REF_UNBOUND = "SKIPPED_SOURCE_REF_UNBOUND"
STATUS_DEPENDENCY_MISSING = "SKIPPED_DEPENDENCY_MISSING"
STATUS_DEPENDENCY_DRIFT = "SKIPPED_DEPENDENCY_DRIFT"
STATUS_OTHER_SOURCE_DRIFT = "SKIPPED_OTHER_SOURCE_DRIFT"
STATUS_SIDECAR_DRIFT = "SKIPPED_SIDECAR_DRIFT"


class MigrationError(Exception):
    """Operational failure distinct from a per-row fail-closed refusal."""


@dataclass
class RowPlan:
    process: str
    status: str
    reason: str | None = None
    evidence_dir: Path | None = None
    new_source_hashes: dict[str, Any] | None = None
    old_source_hashes: dict[str, Any] | None = None
    source_ref: str | None = None
    proven_dependency_hashes: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "status": self.status,
            "reason": self.reason,
            "source_ref": self.source_ref,
            "proven_dependency_hashes": self.proven_dependency_hashes or {},
        }


def _git_args(repo_root: Path, *args: str) -> list[str]:
    worktree_gitdir = _resolve_worktree_gitdir(repo_root)
    if worktree_gitdir is not None:
        return ["git", "--git-dir", str(worktree_gitdir), *args]
    return ["git", "-C", str(repo_root), *args]


def _run_git(repo_root: Path, *args: str) -> bytes:
    command = _git_args(repo_root, *args)
    try:
        result = subprocess.run(command, capture_output=True, check=True, timeout=30)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        raise MigrationError(f"{' '.join(command)} failed (exit {exc.returncode}): {stderr}") from exc
    except OSError as exc:
        raise MigrationError(f"{' '.join(command)} failed to start: {exc}") from exc
    return result.stdout


def _resolve_ref(ref: str, *, repo_root: Path) -> str:
    return _run_git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode("ascii").strip()


def _git_show_bytes(ref: str, rel_path: str, *, repo_root: Path) -> bytes:
    try:
        return _run_git(repo_root, "show", f"{ref}:{rel_path}")
    except MigrationError as exc:
        raise MigrationError(f"git object missing/unreadable at {ref}:{rel_path}: {exc}") from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    return _sha256_bytes(path.read_bytes()) if path.is_file() else None


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise MigrationError(f"registered dependency {path} is outside repository root {repo_root}") from exc


def _evidence_dir_for(entry: cat.ProcessEntry, bundle_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return bundle_root / entry.name / subdir


def _source_ref_is_bound_to_evidence(
    *,
    source_ref: str,
    source_commit: str,
    payload: dict[str, Any],
    evidence_dir: Path,
    repo_root: Path,
) -> tuple[bool, str | None]:
    recorded_git_sha = payload.get("git_sha")
    if isinstance(recorded_git_sha, str) and recorded_git_sha not in {"", "unknown"}:
        try:
            if _resolve_ref(recorded_git_sha, repo_root=repo_root) == source_commit:
                return True, None
        except MigrationError:
            pass

    try:
        evidence_rel = evidence_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return False, f"evidence directory {evidence_dir} is outside repository root {repo_root}"

    mismatches: list[str] = []
    for filename in schema.SWEEP_PROVENANCE_SIDECAR_FILES:
        current_path = evidence_dir / filename
        if not current_path.is_file():
            mismatches.append(f"{filename}:missing-current")
            continue
        try:
            source_bytes = _git_show_bytes(source_ref, f"{evidence_rel}/{filename}", repo_root=repo_root)
        except MigrationError:
            mismatches.append(f"{filename}:missing-at-source-ref")
            continue
        if source_bytes != current_path.read_bytes():
            mismatches.append(f"{filename}:bytes-differ")
    if mismatches:
        return (
            False,
            f"source ref {source_ref!r} neither matches sentinel git_sha={recorded_git_sha!r} "
            f"nor contains byte-identical evidence authority: {mismatches}",
        )
    return True, None


def plan_row_migration(
    entry: cat.ProcessEntry,
    *,
    source_ref: str,
    dependency_keys: tuple[str, ...],
    bundle_root: Path,
    catalog_path: Path,
    registry_path: Path,
    repo_root: Path = REPO_ROOT,
) -> RowPlan:
    name = entry.name
    evidence_dir = _evidence_dir_for(entry, bundle_root)
    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    if not prov_path.is_file():
        return RowPlan(name, STATUS_NO_EVIDENCE, "no sweep_provenance.json under the tracked bundle", evidence_dir)
    try:
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return RowPlan(name, STATUS_NO_EVIDENCE, f"sweep_provenance.json unreadable: {exc}", evidence_dir)
    if payload.get("process") != name:
        return RowPlan(
            name,
            STATUS_HARNESS_MISMATCH,
            f"sweep_provenance.json process={payload.get('process')!r} != {name!r}",
            evidence_dir,
        )

    registered = schema.PROCESS_DEPENDENCY_FILES.get(name, {})
    missing_registry_keys = [key for key in dependency_keys if key not in registered]
    if missing_registry_keys:
        raise MigrationError(f"{name}: dependency keys not registered in schema: {missing_registry_keys}")
    normalized = [key for key in dependency_keys if (name, key) in schema.LF_NORMALIZED_PROCESS_DEPENDENCIES]
    if normalized:
        raise MigrationError(
            f"{name}: this raw-byte-identity migration cannot migrate LF-normalized dependency keys: {normalized}"
        )

    source_hashes = payload.get("source_hashes") or {}
    present = [key for key in dependency_keys if key in source_hashes]
    if present and len(present) != len(dependency_keys):
        return RowPlan(
            name,
            STATUS_PARTIAL_MIGRATION,
            f"only a subset of dependency keys is present: present={present}, expected={list(dependency_keys)}",
            evidence_dir,
            source_ref=source_ref,
        )

    current_hashes = sweep.current_source_hashes(
        entry.oc_module,
        process=name,
        harness_type=entry.harness_type,
        catalog_path=catalog_path,
        registry_path=registry_path,
    )
    non_migrated_current = {key: value for key, value in current_hashes.items() if key not in dependency_keys}
    non_migrated_recorded = {key: value for key, value in source_hashes.items() if key not in dependency_keys}
    if non_migrated_current != non_migrated_recorded:
        drifted = sorted(
            set(non_migrated_current) ^ set(non_migrated_recorded)
            | {
                key
                for key in non_migrated_current
                if non_migrated_current.get(key) != non_migrated_recorded.get(key)
            }
        )
        return RowPlan(
            name,
            STATUS_OTHER_SOURCE_DRIFT,
            f"non-migrated source_hashes drifted vs current tree: {drifted!r}",
            evidence_dir,
            source_ref=source_ref,
        )

    current_sidecars = {
        filename: _sha256_file(evidence_dir / filename)
        for filename in schema.SWEEP_PROVENANCE_SIDECAR_FILES
        if (evidence_dir / filename).is_file()
    }
    recorded_sidecars = payload.get("sidecar_hashes") or {}
    if current_sidecars != recorded_sidecars:
        drifted = sorted(
            set(current_sidecars) ^ set(recorded_sidecars)
            | {
                key
                for key in current_sidecars
                if current_sidecars.get(key) != recorded_sidecars.get(key)
            }
        )
        return RowPlan(
            name,
            STATUS_SIDECAR_DRIFT,
            f"sidecar_hashes drifted vs current bytes: {drifted!r}",
            evidence_dir,
            source_ref=source_ref,
        )

    source_commit = _resolve_ref(source_ref, repo_root=repo_root)
    bound, bind_reason = _source_ref_is_bound_to_evidence(
        source_ref=source_ref,
        source_commit=source_commit,
        payload=payload,
        evidence_dir=evidence_dir,
        repo_root=repo_root,
    )
    if not bound:
        return RowPlan(
            name,
            STATUS_SOURCE_REF_UNBOUND,
            bind_reason,
            evidence_dir,
            source_ref=source_ref,
        )

    proven_hashes: dict[str, str] = {}
    for key in dependency_keys:
        current_path = registered[key]
        if not current_path.is_file():
            return RowPlan(
                name,
                STATUS_DEPENDENCY_MISSING,
                f"{key}: current dependency file missing: {current_path}",
                evidence_dir,
                source_ref=source_ref,
            )
        rel_path = _relative_to_repo(repo_root, current_path)
        try:
            source_bytes = _git_show_bytes(source_ref, rel_path, repo_root=repo_root)
        except MigrationError as exc:
            return RowPlan(
                name,
                STATUS_DEPENDENCY_MISSING,
                f"{key}: {exc}",
                evidence_dir,
                source_ref=source_ref,
            )
        current_bytes = current_path.read_bytes()
        if source_bytes != current_bytes:
            return RowPlan(
                name,
                STATUS_DEPENDENCY_DRIFT,
                f"{key}: bytes differ between evidence source {source_ref!r} and current tree ({rel_path})",
                evidence_dir,
                source_ref=source_ref,
            )
        proven_hashes[key] = _sha256_bytes(current_bytes)
        if current_hashes.get(key) != proven_hashes[key]:
            raise MigrationError(
                f"{name}.{key}: schema hash {current_hashes.get(key)!r} disagrees with exact-byte sha256 "
                f"{proven_hashes[key]!r}"
            )

    if present:
        mismatched = [key for key in dependency_keys if source_hashes.get(key) != proven_hashes[key]]
        if mismatched:
            return RowPlan(
                name,
                STATUS_DEPENDENCY_DRIFT,
                f"already-present dependency hashes do not match proven bytes: {mismatched}",
                evidence_dir,
                source_ref=source_ref,
                proven_dependency_hashes=proven_hashes,
            )
        return RowPlan(
            name,
            STATUS_ALREADY_MIGRATED,
            None,
            evidence_dir,
            source_ref=source_ref,
            proven_dependency_hashes=proven_hashes,
        )

    new_source_hashes = dict(source_hashes)
    new_source_hashes.update(proven_hashes)
    return RowPlan(
        name,
        STATUS_WOULD_MIGRATE,
        None,
        evidence_dir,
        new_source_hashes=new_source_hashes,
        old_source_hashes=source_hashes,
        source_ref=source_ref,
        proven_dependency_hashes=proven_hashes,
    )


def plan_migration(
    *,
    source_refs: dict[str, str],
    bundle_root: Path = schema.BUNDLE_ROOT,
    catalog_path: Path = schema.CATALOG_PATH,
    registry_path: Path = schema.L2_EVENT_REGISTRY_PATH,
    processes: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, RowPlan]:
    entries = cat.in_scope_processes(catalog_path)
    names = sorted(NEW_DEPENDENCY_KEYS) if processes is None else list(processes)
    unknown = [name for name in names if name not in NEW_DEPENDENCY_KEYS or name not in entries]
    if unknown:
        raise MigrationError(
            f"unknown/not-migratable process(es): {unknown}; available: {sorted(NEW_DEPENDENCY_KEYS)}"
        )
    missing_refs = [name for name in names if name not in source_refs]
    if missing_refs:
        raise MigrationError(f"missing explicit --source-ref for process(es): {missing_refs}")
    return {
        name: plan_row_migration(
            entries[name],
            source_ref=source_refs[name],
            dependency_keys=NEW_DEPENDENCY_KEYS[name],
            bundle_root=bundle_root,
            catalog_path=catalog_path,
            registry_path=registry_path,
            repo_root=repo_root,
        )
        for name in names
    }


def apply_plan(plans: dict[str, RowPlan]) -> dict[str, RowPlan]:
    results: dict[str, RowPlan] = {}
    for name, plan in plans.items():
        if plan.status != STATUS_WOULD_MIGRATE:
            results[name] = plan
            continue
        assert plan.evidence_dir is not None and plan.new_source_hashes is not None
        prov_path = plan.evidence_dir / schema.SWEEP_PROVENANCE_FILE
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
        payload["source_hashes"] = plan.new_source_hashes
        tmp_path = prov_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, prov_path)
        results[name] = RowPlan(
            name,
            STATUS_MIGRATED,
            None,
            plan.evidence_dir,
            plan.new_source_hashes,
            plan.old_source_hashes,
            plan.source_ref,
            plan.proven_dependency_hashes,
        )
    return results


def _parse_source_refs(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise MigrationError(f"--source-ref must be PROCESS=REF, got {value!r}")
        process, ref = (part.strip() for part in value.split("=", 1))
        if not process or not ref:
            raise MigrationError(f"--source-ref must be PROCESS=REF, got {value!r}")
        if process in parsed:
            raise MigrationError(f"duplicate --source-ref for {process}")
        parsed[process] = ref
    return parsed


def _print_report(plans: dict[str, RowPlan], *, applied: bool) -> None:
    for plan in plans.values():
        suffix = f" -- {plan.reason}" if plan.reason else ""
        print(f"{plan.process:28s} {plan.status}{suffix}")
        for key, digest in sorted((plan.proven_dependency_hashes or {}).items()):
            print(f"  proof {key}: source/current exact bytes sha256={digest}")
    print("APPLIED" if applied else "DRY RUN (pass --apply to write)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--source-ref",
        action="append",
        default=[],
        metavar="PROCESS=REF",
        help="Explicit evidence-source commit/tree for one process; repeat per process.",
    )
    parser.add_argument("--bundle-root", default=str(schema.BUNDLE_ROOT))
    parser.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    parser.add_argument("--registry", default=str(schema.L2_EVENT_REGISTRY_PATH))
    parser.add_argument("--processes", default=None, help="Comma-separated subset; default: all migratable rows.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        source_refs = _parse_source_refs(args.source_ref)
        processes = [part.strip() for part in args.processes.split(",") if part.strip()] if args.processes else None
        plans = plan_migration(
            source_refs=source_refs,
            bundle_root=Path(args.bundle_root),
            catalog_path=Path(args.catalog),
            registry_path=Path(args.registry),
            processes=processes,
        )
    except MigrationError as exc:
        print(f"MIGRATION REFUSED: {exc}", file=sys.stderr)
        return 1

    if args.apply:
        plans = apply_plan(plans)
    _print_report(plans, applied=args.apply)
    refused = [
        plan
        for plan in plans.values()
        if plan.status not in {STATUS_WOULD_MIGRATE, STATUS_MIGRATED, STATUS_ALREADY_MIGRATED}
    ]
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
