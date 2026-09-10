"""One-shot migration + direct-evidence proof: `sweep_provenance.json
["source_hashes"]["helpers"]` after raising `_l2_2_design_a_runner_helpers.py
::_load_v2_ensemble`'s `max_seeds` default from 50 to 200 (R10).

Context (2026-09 DNASupercoiling integration): the accepted DNASupercoiling
N=200 evidence needs `load_karr_oracle("DNASupercoiling")` to find all 200
`per_process_traces_v2_s{NNN}/DNASupercoiling_100ticks.mat` seed files, but
`_load_v2_ensemble`'s search loop only ever checked `seed in range(max_seeds)`
with a hardcoded `max_seeds=50` default -- silently truncating the oracle to
50 seeds regardless of how many seed files actually exist on disk. Raising
the default to 200 is a genuinely SHARED/generic-code change (not a
per-process runner-body change R7's redaction scheme already isolates), so
it legitimately changes `schema.runner_helpers_generic_hash()`'s value for
EVERY `design_a_per_tick` process at once.

Unlike R7 (which proves inertness by construction -- the redacted span never
included this code) and R8 (which proves inertness by RUNNING both
implementations against real data), R10 proves inertness by DIRECT,
CHECKABLE EVIDENCE ABOUT THE ACTUAL DATA: `_load_v2_ensemble`'s search loop
is a pure "does this exact file exist" scan with no other side effects, so
raising its upper bound is a no-op for any process that has NO seed file at
any index in [50, 200) on the CURRENT filesystem -- widening the search
finds nothing new, so `seed_paths` (and therefore the oracle it builds) is
byte-for-byte identical before and after. This tool verifies that absence
directly (`Path.exists()` for every candidate index in the widened range,
for every `per_process_traces_v2_s*`-layout process being migrated) rather
than executing two versions of the function and diffing their output.

DNASupercoiling itself is NEVER migrated here -- its own row is a genuine
fresh N=200 promotion, not a migration.

Fails closed per row:
  - Verifies the row's recorded `source_hashes["helpers"]` equals the ACTUAL
    `schema.runner_helpers_generic_hash()` value at `--pre-ref` (computed
    from that ref's git-blob text via the SAME redaction logic, so this
    check is meaningful even though `--pre-ref` already reflects the R7
    migration).
  - Verifies NO seed file exists for this process at ANY index in
    `range(50, 200)` under `data/m1_sources/karr_native/
    per_process_traces_v2_s{NNN}/<process>_100ticks.mat` on the CURRENT
    filesystem -- a single existing file at any of those indices refuses
    the row (it would mean the widened search really can pick up new data
    for this process, so inertness is not proven).
  - Verifies every OTHER recorded `source_hashes` entry still matches the
    current tree, and every mandatory sidecar hash still matches current
    bytes on disk.
  - Only then rewrites `source_hashes["helpers"]` to the CURRENT tree's
    `runner_helpers_generic_hash()` value.

CLI:
    bin\\oc-py scripts/l22_evidence/migrate_oracle_seed_cap_provenance.py \\
        --pre-ref <ref> [--processes P1,P2] [--apply]
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
DEPENDENCY_KEY = "helpers"
NEVER_MIGRATE_PROCESSES = frozenset({"DNASupercoiling"})
OLD_MAX_SEEDS = 50
NEW_MAX_SEEDS = 200
TRACE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native"

STATUS_MIGRATED = "MIGRATED"
STATUS_WOULD_MIGRATE = "WOULD_MIGRATE"
STATUS_ALREADY_MIGRATED = "ALREADY_MIGRATED"
STATUS_NO_EVIDENCE = "NO_EVIDENCE"
STATUS_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"
STATUS_HARNESS_MISMATCH = "SKIPPED_HARNESS_MISMATCH"
STATUS_NEVER_MIGRATE = "SKIPPED_NEVER_MIGRATE"
STATUS_PRE_REF_MISMATCH = "SKIPPED_PRE_REF_MISMATCH"
STATUS_WIDENED_SEED_FOUND = "SKIPPED_WIDENED_SEED_FOUND"
STATUS_OTHER_SOURCE_DRIFT = "SKIPPED_OTHER_SOURCE_DRIFT"
STATUS_SIDECAR_DRIFT = "SKIPPED_SIDECAR_DRIFT"


class MigrationError(Exception):
    pass


@dataclass
class RowPlan:
    process: str
    status: str
    reason: str | None = None
    evidence_dir: Path | None = None
    new_source_hashes: dict[str, Any] | None = None
    old_source_hashes: dict[str, Any] | None = None
    new_input_manifest_sha256: str | None = None
    input_manifest_helpers_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"process": self.process, "status": self.status, "reason": self.reason}


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_show_text(ref: str, rel_path: str, *, repo_root: Path = REPO_ROOT) -> str:
    worktree_gitdir = _resolve_worktree_gitdir(repo_root)
    args = (
        ["git", "--git-dir", str(worktree_gitdir), "show", f"{ref}:{rel_path}"]
        if worktree_gitdir is not None
        else ["git", "-C", str(repo_root), "show", f"{ref}:{rel_path}"]
    )
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    except subprocess.CalledProcessError as exc:
        raise MigrationError(
            f"git show {ref}:{rel_path} failed (exit {exc.returncode}): {(exc.stderr or '').strip()}"
        ) from exc
    except OSError as exc:
        raise MigrationError(f"git show {ref}:{rel_path} failed to start: {exc}") from exc
    return result.stdout


def _relative_to_repo_root(repo_root: Path, path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(repo_root).resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _no_widened_seed_files_exist(process: str) -> bool:
    """True iff NO `per_process_traces_v2_s{NNN}/<process>_100ticks.mat`
    exists for seed index NNN in [OLD_MAX_SEEDS, NEW_MAX_SEEDS) on the
    CURRENT filesystem -- the direct evidence this migration relies on."""
    for seed in range(OLD_MAX_SEEDS, NEW_MAX_SEEDS):
        candidate = TRACE_ROOT / f"per_process_traces_v2_s{seed:03d}" / f"{process}_100ticks.mat"
        if candidate.is_file():
            return False
    return True


def _evidence_dir_for(entry: cat.ProcessEntry, bundle_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return bundle_root / entry.name / subdir


def plan_row_migration(
    entry: cat.ProcessEntry,
    *,
    pre_ref: str,
    pre_ref_generic_hash: str,
    pre_ref_helpers_plain_hash: str,
    bundle_root: Path,
    catalog_path: Path,
    registry_path: Path,
) -> RowPlan:
    name = entry.name
    evidence_dir = _evidence_dir_for(entry, bundle_root)

    if name in NEVER_MIGRATE_PROCESSES:
        return RowPlan(name, STATUS_NEVER_MIGRATE, "genuine fresh N=200 promotion, not a migration", evidence_dir)
    if entry.harness_type != "design_a_per_tick":
        return RowPlan(name, STATUS_NOT_APPLICABLE, f"harness_type={entry.harness_type!r} never had a 'helpers' key", evidence_dir)

    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    if not prov_path.is_file():
        return RowPlan(name, STATUS_NO_EVIDENCE, "no sweep_provenance.json under the tracked bundle", evidence_dir)
    try:
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return RowPlan(name, STATUS_NO_EVIDENCE, f"sweep_provenance.json unreadable: {exc}", evidence_dir)
    if payload.get("process") != name:
        return RowPlan(
            name, STATUS_HARNESS_MISMATCH, f"sweep_provenance.json process={payload.get('process')!r} != {name!r}", evidence_dir
        )

    source_hashes = payload.get("source_hashes") or {}
    recorded = source_hashes.get(DEPENDENCY_KEY)
    current_generic_hash = schema.runner_helpers_generic_hash()
    if recorded == current_generic_hash:
        return RowPlan(name, STATUS_ALREADY_MIGRATED, None, evidence_dir)
    if recorded != pre_ref_generic_hash:
        return RowPlan(
            name,
            STATUS_PRE_REF_MISMATCH,
            f"recorded {DEPENDENCY_KEY} hash {str(recorded)[:12]!r}.. != --pre-ref {pre_ref!r} "
            f"generic hash {pre_ref_generic_hash[:12]!r}..",
            evidence_dir,
        )

    if not _no_widened_seed_files_exist(name):
        return RowPlan(
            name,
            STATUS_WIDENED_SEED_FOUND,
            f"a per_process_traces_v2_s{{NNN}}/{name}_100ticks.mat file exists for some NNN in "
            f"[{OLD_MAX_SEEDS}, {NEW_MAX_SEEDS}) -- widening the search is NOT provably inert for this process",
            evidence_dir,
        )

    current_hashes = sweep.current_source_hashes(
        entry.oc_module, process=name, harness_type=entry.harness_type, catalog_path=catalog_path, registry_path=registry_path
    )
    non_migrated_current = {k: v for k, v in current_hashes.items() if k != DEPENDENCY_KEY}
    non_migrated_recorded = {k: v for k, v in source_hashes.items() if k != DEPENDENCY_KEY}
    if non_migrated_current != non_migrated_recorded:
        drifted = sorted(
            set(non_migrated_current) ^ set(non_migrated_recorded)
            | {k for k in non_migrated_current if non_migrated_current.get(k) != non_migrated_recorded.get(k)}
        )
        return RowPlan(
            name, STATUS_OTHER_SOURCE_DRIFT, f"non-migrated source_hashes drifted vs current tree: {drifted!r}", evidence_dir
        )

    current_sidecars = {
        fname: _sha256_file(evidence_dir / fname)
        for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES
        if (evidence_dir / fname).is_file()
    }
    recorded_sidecars = payload.get("sidecar_hashes") or {}
    if current_sidecars != recorded_sidecars:
        drifted = sorted(
            set(current_sidecars) ^ set(recorded_sidecars)
            | {k for k in current_sidecars if current_sidecars.get(k) != recorded_sidecars.get(k)}
        )
        return RowPlan(name, STATUS_SIDECAR_DRIFT, f"sidecar_hashes drifted vs current bytes: {drifted!r}", evidence_dir)

    # input_manifest.json separately records a PLAIN whole-file hash of
    # _l2_2_design_a_runner_helpers.py (R3 input attestation) -- re-stamped
    # to the CURRENT plain whole-file hash, justified by the SAME
    # "no widened seed file exists" proof already established above.
    new_input_manifest_sha256: str | None = None
    input_manifest_helpers_index: int | None = None
    input_manifest_path = evidence_dir / "input_manifest.json"
    if input_manifest_path.is_file():
        manifest_payload = json.loads(input_manifest_path.read_text(encoding="utf-8"))
        helpers_module_resolved = schema.RUNNER_HELPERS_MODULE.resolve()
        for idx, record in enumerate(manifest_payload.get("inputs") or []):
            record_path = record.get("path")
            if not record_path:
                continue
            resolved = Path(str(record_path))
            resolved = resolved.resolve() if resolved.is_absolute() else (REPO_ROOT / resolved).resolve()
            if resolved != helpers_module_resolved:
                continue
            recorded_manifest_sha = record.get("sha256")
            current_plain_hash = _sha256_file(schema.RUNNER_HELPERS_MODULE)
            if recorded_manifest_sha == current_plain_hash:
                break
            if recorded_manifest_sha != pre_ref_helpers_plain_hash:
                return RowPlan(
                    name,
                    STATUS_PRE_REF_MISMATCH,
                    f"input_manifest.json helpers entry sha256 {str(recorded_manifest_sha)[:12]!r}.. != "
                    f"--pre-ref {pre_ref!r} plain whole-file hash {pre_ref_helpers_plain_hash[:12]!r}..",
                    evidence_dir,
                )
            new_input_manifest_sha256 = current_plain_hash
            input_manifest_helpers_index = idx
            break

    new_source_hashes = dict(source_hashes)
    new_source_hashes[DEPENDENCY_KEY] = current_generic_hash
    return RowPlan(
        name,
        STATUS_WOULD_MIGRATE,
        None,
        evidence_dir,
        new_source_hashes=new_source_hashes,
        old_source_hashes=source_hashes,
        new_input_manifest_sha256=new_input_manifest_sha256,
        input_manifest_helpers_index=input_manifest_helpers_index,
    )



def plan_migration(
    *,
    pre_ref: str,
    bundle_root: Path = schema.BUNDLE_ROOT,
    catalog_path: Path = schema.CATALOG_PATH,
    registry_path: Path = schema.L2_EVENT_REGISTRY_PATH,
    processes: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, RowPlan]:
    entries = cat.in_scope_processes(catalog_path)
    names = sorted(entries) if processes is None else list(processes)
    unknown = [n for n in names if n not in entries]
    if unknown:
        raise MigrationError(f"unknown/not-in-scope process(es): {unknown}; available: {sorted(entries)}")

    helpers_rel = _relative_to_repo_root(repo_root, schema.RUNNER_HELPERS_MODULE)
    pre_ref_text = git_show_text(pre_ref, helpers_rel, repo_root=repo_root)
    pre_ref_generic_hash = schema.runner_helpers_generic_hash(source=pre_ref_text)
    pre_ref_helpers_plain_hash = hashlib.sha256(pre_ref_text.encode("utf-8")).hexdigest()

    return {
        name: plan_row_migration(
            entries[name],
            pre_ref=pre_ref,
            pre_ref_generic_hash=pre_ref_generic_hash,
            pre_ref_helpers_plain_hash=pre_ref_helpers_plain_hash,
            bundle_root=bundle_root,
            catalog_path=catalog_path,
            registry_path=registry_path,
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

        new_input_manifest_sidecar_sha: str | None = None
        if plan.new_input_manifest_sha256 is not None and plan.input_manifest_helpers_index is not None:
            manifest_path = plan.evidence_dir / "input_manifest.json"
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_payload["inputs"][plan.input_manifest_helpers_index]["sha256"] = plan.new_input_manifest_sha256
            manifest_tmp_path = manifest_path.with_suffix(".json.tmp")
            manifest_tmp_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(manifest_tmp_path, manifest_path)
            new_input_manifest_sidecar_sha = _sha256_file(manifest_path)

        prov_path = plan.evidence_dir / schema.SWEEP_PROVENANCE_FILE
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
        payload["source_hashes"] = plan.new_source_hashes
        if new_input_manifest_sidecar_sha is not None and "input_manifest.json" in (payload.get("sidecar_hashes") or {}):
            payload["sidecar_hashes"]["input_manifest.json"] = new_input_manifest_sidecar_sha
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
            plan.new_input_manifest_sha256,
            plan.input_manifest_helpers_index,
        )
    return results


def _print_report(plans: dict[str, RowPlan], *, applied: bool) -> None:
    tally: dict[str, int] = {}
    for plan in plans.values():
        tally[plan.status] = tally.get(plan.status, 0) + 1
        print(f"{plan.process:28s} {plan.status}" + (f"  -- {plan.reason}" if plan.reason else ""))
    print()
    print(f"{'APPLIED' if applied else 'DRY RUN (pass --apply to write)'} -- tally:")
    for status, count in sorted(tally.items()):
        print(f"  {status}: {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pre-ref", required=True)
    parser.add_argument("--bundle-root", default=str(schema.BUNDLE_ROOT))
    parser.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    parser.add_argument("--registry", default=str(schema.L2_EVENT_REGISTRY_PATH))
    parser.add_argument("--processes", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    processes = [p.strip() for p in args.processes.split(",") if p.strip()] if args.processes else None

    try:
        plans = plan_migration(
            pre_ref=args.pre_ref,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
