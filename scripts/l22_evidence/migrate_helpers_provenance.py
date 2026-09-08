"""One-shot migration: whole-catalog-file `sweep_provenance.json["source_hashes"]
["helpers"]` (a plain sha256 of the ENTIRE `_l2_2_design_a_runner_helpers.py`)
-> the R7 redesign: a per-process-redacted generic `"helpers"` hash plus a new,
genuinely per-process `"tick_runner"` hash (R7 catalog-provenance-style fix,
mirroring `migrate_catalog_provenance.py`'s R6 precedent for exactly the same
class of bug -- see `scripts/l22_evidence/schema.py::runner_helpers_generic_hash`
/`tick_runner_entry_hash`'s docstrings for the full design).

Context (2026-09 DNASupercoiling integration): DNASupercoiling's accepted
persistent-process-pool fix moved its tick-runner function out of the shared,
universally-hashed `_l2_2_design_a_runner_helpers.py` into its own sibling
module, `_l2_2_dnas_runner_helpers.py`. `_tick_dispatch()`'s dict entry for
`"DNASupercoiling"` therefore had to change (from a local `def` to an
imported name) -- a genuinely unavoidable one-line edit to the shared file,
which changed its whole-file sha256 and would otherwise have staled every
OTHER in-scope Design-A process's evidence at once (exactly the failure mode
R2/R6 already fixed for `oc_module`/catalog+registry). This tool migrates
every OTHER process's ALREADY-TRACKED `sweep_provenance.json` from the old
whole-file key to the new pair, WITHOUT rerunning the (slow, oracle-dependent)
sweep and WITHOUT rewriting a single byte of `result.json`/`thresholds.json`/
any other authority/sidecar file. DNASupercoiling itself is NEVER migrated by
this tool -- its own row must come from a genuine fresh sweep run, since its
runner code (and therefore its `"tick_runner"` hash) genuinely changed.

This tool is deliberately conservative and fails closed per row:

  - Takes an EXPLICIT ``--pre-ref`` (a commit-ish naming the tree state
    BEFORE the DNASupercoiling dispatcher edit). Never guesses/assumes it.
  - For each row with existing evidence, verifies its recorded
    `source_hashes["helpers"]` (whole-file) hash equals the ACTUAL sha256 of
    `_l2_2_design_a_runner_helpers.py` as it existed at `--pre-ref` (via
    ``git show <ref>:<path>``, never a local checkout of that ref) -- a row
    whose recorded hash does NOT match this is left completely untouched
    (never migrated), since we cannot otherwise prove what it was actually
    compared against.
  - Computes the NEW-style `"helpers"` (redacted-generic) value from the
    `--pre-ref` blob's text and from the CURRENT tree's file, and refuses to
    migrate unless they are IDENTICAL -- this is the mechanical proof that
    nothing outside a per-process tick-runner function body changed for this
    row (the redaction excludes every `_tick_dispatch()`-mapped function body
    from the hash, so it is completely insensitive to any of THEM changing;
    an inequality here means real, non-runner-body shared code changed, and
    the row is correctly refused, not silently migrated).
  - Computes this process's OWN `"tick_runner"` value (its dispatched
    function's own source) from the `--pre-ref` blob's text and from the
    current tree, and likewise refuses to migrate unless they are IDENTICAL
    -- this is what makes DNASupercoiling itself always refuse (its function
    moved/changed), while every other process's own runner function, which
    is untouched, always matches.
  - Verifies every OTHER recorded `source_hashes` entry (runner/projections/
    vivarium_init/catalog_entry/oc_module/process- and harness-scoped
    dependency modules) still matches the CURRENT tree -- any drift leaves
    the row untouched (it has a real, unrelated staleness problem this
    migration must not paper over).
  - Verifies every mandatory authority/sidecar file's recorded
    `sidecar_hashes` entry still matches the CURRENT bytes on disk -- same
    reasoning.
  - Only then rewrites `source_hashes`: replaces `"helpers"` with the new
    redacted-generic value (current tree) and adds `"tick_runner"` (current
    tree) -- both PROVEN identical in content to what `--pre-ref` would have
    produced by the equality checks above. Every other field in the
    sentinel is copied through completely unchanged -- this tool never
    touches `result.json`/`thresholds.json`/`null_calibration.json`/
    `SUMMARY.json`/`analytical_check.json`/`input_manifest.json`/
    `provenance.json` at all.
  - Writes atomically (temp file + `os.replace`) so a crash mid-run never
    corrupts a row; idempotent/resumable (a row already migrated -- both
    `"helpers"` in its new form AND `"tick_runner"` present -- is reported
    `ALREADY_MIGRATED` and left alone).

CLI:
    bin\\oc-py scripts/l22_evidence/migrate_helpers_provenance.py \\
        --pre-ref <ref> [--processes P1,P2] [--apply]

Dry-run (no ``--apply``) prints the per-row plan and touches nothing.
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

OLD_HELPERS_KEY = "helpers"
NEW_TICK_RUNNER_KEY = "tick_runner"
# DNASupercoiling's own row is never migrated: its runner code genuinely
# moved, so its `"tick_runner"` pre-ref/current comparison is EXPECTED to
# differ. It must come from a real fresh sweep run instead.
NEVER_MIGRATE_PROCESSES = frozenset({"DNASupercoiling"})

STATUS_MIGRATED = "MIGRATED"
STATUS_WOULD_MIGRATE = "WOULD_MIGRATE"
STATUS_ALREADY_MIGRATED = "ALREADY_MIGRATED"
STATUS_NO_EVIDENCE = "NO_EVIDENCE"
STATUS_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"
STATUS_HARNESS_MISMATCH = "SKIPPED_HARNESS_MISMATCH"
STATUS_NO_OLD_HELPERS_KEY = "SKIPPED_NO_OLD_HELPERS_KEY"
STATUS_PRE_REF_HELPERS_MISMATCH = "SKIPPED_PRE_REF_HELPERS_MISMATCH"
STATUS_GENERIC_HASH_DRIFT = "SKIPPED_GENERIC_HASH_DRIFT"
STATUS_TICK_RUNNER_DRIFT = "SKIPPED_TICK_RUNNER_DRIFT"
STATUS_OTHER_SOURCE_DRIFT = "SKIPPED_OTHER_SOURCE_DRIFT"
STATUS_SIDECAR_DRIFT = "SKIPPED_SIDECAR_DRIFT"
STATUS_NEVER_MIGRATE = "SKIPPED_NEVER_MIGRATE"
STATUS_INPUT_MANIFEST_DRIFT = "SKIPPED_INPUT_MANIFEST_DRIFT"

_TERMINAL_NO_OP_STATUSES = frozenset({STATUS_ALREADY_MIGRATED, STATUS_NO_EVIDENCE})


class MigrationError(Exception):
    """Operational failure (bad ref, unreadable git object) -- distinct from
    a per-row `SKIPPED_*` refusal, which is an expected, handled outcome."""


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
    """``git show <ref>:<rel_path>`` as text -- see
    `migrate_catalog_provenance.git_show_text`'s docstring for the worktree
    gitdir/encoding rationale this mirrors exactly."""
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


def _evidence_dir_for(entry: cat.ProcessEntry, bundle_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return bundle_root / entry.name / subdir


def _plan_input_manifest_migration(
    name: str,
    evidence_dir: Path,
    *,
    pre_ref: str,
    pre_ref_helpers_hash: str,
) -> tuple[str | None, int | None, RowPlan | None]:
    """`input_manifest.json` separately records a PLAIN whole-file hash of
    `_l2_2_design_a_runner_helpers.py` (R3 input attestation -- a
    completely separate mechanism from `sweep_provenance.json
    ["source_hashes"]`, with no per-process granularity concept at all).
    It is not migrated to a "generic" hash; it is re-stamped to the file's
    CURRENT plain whole-file hash, justified by the SAME pre-ref-vs-current
    generic/tick_runner equality proof `plan_row_migration` already
    established for `sweep_provenance.json` (the only change to this file,
    relative to `--pre-ref`, is confined to a region with zero influence
    on any OTHER process's own runner code). Returns
    ``(new_sha256_or_None, matching_input_index_or_None, refusal_RowPlan_or_None)``
    -- a non-None third element means "refuse the whole row", mirroring
    every other precondition check in this module. If no
    `input_manifest.json`/no matching entry exists, returns ``(None, None,
    None)`` (nothing to migrate, not an error -- not every evidence layout
    necessarily has this entry)."""
    input_manifest_path = evidence_dir / "input_manifest.json"
    if not input_manifest_path.is_file():
        return None, None, None
    try:
        manifest_payload = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, None, RowPlan(name, STATUS_INPUT_MANIFEST_DRIFT, f"input_manifest.json unreadable: {exc}", evidence_dir)
    manifest_inputs = manifest_payload.get("inputs") or []
    helpers_module_resolved = schema.RUNNER_HELPERS_MODULE.resolve()
    for idx, record in enumerate(manifest_inputs):
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
            # Already migrated (or never drifted in the first place).
            return None, None, None
        if recorded_manifest_sha != pre_ref_helpers_hash:
            return (
                None,
                None,
                RowPlan(
                    name,
                    STATUS_INPUT_MANIFEST_DRIFT,
                    f"input_manifest.json helpers entry sha256 {str(recorded_manifest_sha)[:12]!r}.. != "
                    f"--pre-ref {pre_ref!r} whole-file hash {pre_ref_helpers_hash[:12]!r}..",
                    evidence_dir,
                ),
            )
        return current_plain_hash, idx, None
    return None, None, None


def plan_row_migration(
    entry: cat.ProcessEntry,
    *,
    pre_ref: str,
    pre_ref_helpers_text: str,
    pre_ref_helpers_hash: str,
    bundle_root: Path,
    catalog_path: Path,
    registry_path: Path,
) -> RowPlan:
    """Evaluate ONE process's tracked `sweep_provenance.json` (and, when
    present, `input_manifest.json`) against every fail-closed precondition
    and return the migration decision -- never writes anything (see
    `apply_plan` for that). Handles resuming a partially-applied migration
    (e.g. `sweep_provenance.json` already migrated on an earlier `--apply`
    run but `input_manifest.json` not yet, or vice versa) correctly: each
    half is independently checked, and the row is only `ALREADY_MIGRATED`
    when NEITHER needs any further write."""
    name = entry.name
    evidence_dir = _evidence_dir_for(entry, bundle_root)

    if name in NEVER_MIGRATE_PROCESSES:
        return RowPlan(
            name, STATUS_NEVER_MIGRATE, "registered as never-migrate: its own runner code moved", evidence_dir
        )
    if entry.harness_type != "design_a_per_tick":
        return RowPlan(
            name, STATUS_NOT_APPLICABLE, f"harness_type={entry.harness_type!r} never had a 'helpers' key", evidence_dir
        )

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
    sweep_provenance_already_migrated = OLD_HELPERS_KEY in source_hashes and NEW_TICK_RUNNER_KEY in source_hashes
    new_source_hashes: dict[str, Any] | None = None

    if OLD_HELPERS_KEY not in source_hashes:
        return RowPlan(
            name, STATUS_NO_OLD_HELPERS_KEY, f"source_hashes has no {OLD_HELPERS_KEY!r} key -- unexpected format", evidence_dir
        )

    if not sweep_provenance_already_migrated:
        # (1) The recorded whole-file "helpers" hash must match the
        # EXPLICIT --pre-ref the operator supplied.
        recorded_helpers_hash = source_hashes.get(OLD_HELPERS_KEY)
        if recorded_helpers_hash != pre_ref_helpers_hash:
            return RowPlan(
                name,
                STATUS_PRE_REF_HELPERS_MISMATCH,
                f"recorded helpers hash {str(recorded_helpers_hash)[:12]!r}.. != --pre-ref {pre_ref!r} "
                f"whole-file hash {pre_ref_helpers_hash[:12]!r}.. -- this row was generated against a DIFFERENT "
                "runner-helpers state than --pre-ref names; leaving untouched",
                evidence_dir,
            )

        # (2) The NEW-style redacted-generic hash must be IDENTICAL between
        # --pre-ref and the current tree -- proves no shared/generic code
        # changed for this row (only, at most, some OTHER process's own
        # tick-runner function body, which redaction already excludes).
        pre_ref_generic_hash = schema.runner_helpers_generic_hash(source=pre_ref_helpers_text)
        current_generic_hash = schema.runner_helpers_generic_hash()
        if pre_ref_generic_hash != current_generic_hash:
            return RowPlan(
                name,
                STATUS_GENERIC_HASH_DRIFT,
                f"redacted-generic helpers hash changed between --pre-ref {pre_ref!r} "
                f"({str(pre_ref_generic_hash)[:12]!r}..) and current tree ({str(current_generic_hash)[:12]!r}..) -- "
                "real shared/generic runner-helpers code changed, not just a per-process runner body",
                evidence_dir,
            )

        # (3) This process's OWN tick_runner hash must ALSO be identical
        # between --pre-ref and the current tree -- this is what correctly
        # refuses DNASupercoiling (already short-circuited above) and any
        # OTHER process whose own runner function happened to change too.
        pre_ref_tick_runner_hash = schema.tick_runner_entry_hash(name, source=pre_ref_helpers_text)
        current_tick_runner_hash = schema.tick_runner_entry_hash(name)
        if pre_ref_tick_runner_hash is None or pre_ref_tick_runner_hash != current_tick_runner_hash:
            return RowPlan(
                name,
                STATUS_TICK_RUNNER_DRIFT,
                f"this process's own tick-runner source changed between --pre-ref {pre_ref!r} "
                f"({str(pre_ref_tick_runner_hash)[:12]!r}..) and current tree ({str(current_tick_runner_hash)[:12]!r}..)",
                evidence_dir,
            )

        # (4) Every OTHER recorded source hash must still match the current
        # tree (excluding the two keys this migration itself changes).
        current_hashes = sweep.current_source_hashes(
            entry.oc_module, process=name, harness_type=entry.harness_type, catalog_path=catalog_path, registry_path=registry_path
        )
        excluded = {OLD_HELPERS_KEY, NEW_TICK_RUNNER_KEY}
        non_migrated_current = {k: v for k, v in current_hashes.items() if k not in excluded}
        non_migrated_recorded = {k: v for k, v in source_hashes.items() if k not in excluded}
        if non_migrated_current != non_migrated_recorded:
            drifted = sorted(
                set(non_migrated_current) ^ set(non_migrated_recorded)
                | {k for k in non_migrated_current if non_migrated_current.get(k) != non_migrated_recorded.get(k)}
            )
            return RowPlan(
                name, STATUS_OTHER_SOURCE_DRIFT, f"non-migrated source_hashes drifted vs current tree: {drifted!r}", evidence_dir
            )

        # (5) Every mandatory authority/sidecar file's recorded
        # sidecar_hashes entry must still match its CURRENT bytes on disk.
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

        new_source_hashes = dict(source_hashes)
        new_source_hashes[OLD_HELPERS_KEY] = current_generic_hash
        new_source_hashes[NEW_TICK_RUNNER_KEY] = current_tick_runner_hash

    new_input_manifest_sha256, input_manifest_helpers_index, refusal = _plan_input_manifest_migration(
        name, evidence_dir, pre_ref=pre_ref, pre_ref_helpers_hash=pre_ref_helpers_hash
    )
    if refusal is not None:
        return refusal

    if new_source_hashes is None and new_input_manifest_sha256 is None:
        return RowPlan(name, STATUS_ALREADY_MIGRATED, None, evidence_dir)

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
    """Read-only: evaluate every (or every requested) in-scope process and
    return its migration decision. Never writes anything -- see
    `apply_plan`."""
    entries = cat.in_scope_processes(catalog_path)
    names = sorted(entries) if processes is None else list(processes)
    unknown = [n for n in names if n not in entries]
    if unknown:
        raise MigrationError(f"unknown/not-in-scope process(es): {unknown}; available: {sorted(entries)}")

    helpers_rel = _relative_to_repo_root(repo_root, schema.RUNNER_HELPERS_MODULE)
    pre_ref_helpers_text = git_show_text(pre_ref, helpers_rel, repo_root=repo_root)
    pre_ref_helpers_hash = hashlib.sha256(pre_ref_helpers_text.encode("utf-8")).hexdigest()

    return {
        name: plan_row_migration(
            entries[name],
            pre_ref=pre_ref,
            pre_ref_helpers_text=pre_ref_helpers_text,
            pre_ref_helpers_hash=pre_ref_helpers_hash,
            bundle_root=bundle_root,
            catalog_path=catalog_path,
            registry_path=registry_path,
        )
        for name in names
    }


def apply_plan(plans: dict[str, RowPlan]) -> dict[str, RowPlan]:
    """Atomically write every `STATUS_WOULD_MIGRATE` row's migrated
    `sweep_provenance.json` (temp file + `os.replace`) and, when planned,
    its `input_manifest.json` helpers-entry sha256; every other status is
    left completely untouched. Idempotent/resumable.

    Write order matters: `input_manifest.json` (if planned) is rewritten
    FIRST, then its NEW sha256 is folded into the SAME
    `sweep_provenance.json` write as `source_hashes` -- `sweep_provenance.
    json["sidecar_hashes"]["input_manifest.json"]` binds the sentinel to
    that file's exact bytes (R1), so editing `input_manifest.json` without
    also updating this would immediately re-break the row's own integrity
    check the next time it is audited."""
    results: dict[str, RowPlan] = {}
    for name, plan in plans.items():
        if plan.status != STATUS_WOULD_MIGRATE:
            results[name] = plan
            continue
        assert plan.evidence_dir is not None

        new_input_manifest_sidecar_sha: str | None = None
        if plan.new_input_manifest_sha256 is not None and plan.input_manifest_helpers_index is not None:
            manifest_path = plan.evidence_dir / "input_manifest.json"
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_payload["inputs"][plan.input_manifest_helpers_index]["sha256"] = plan.new_input_manifest_sha256
            manifest_tmp_path = manifest_path.with_suffix(".json.tmp")
            manifest_tmp_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(manifest_tmp_path, manifest_path)
            new_input_manifest_sidecar_sha = _sha256_file(manifest_path)

        if plan.new_source_hashes is not None or new_input_manifest_sidecar_sha is not None:
            prov_path = plan.evidence_dir / schema.SWEEP_PROVENANCE_FILE
            payload = json.loads(prov_path.read_text(encoding="utf-8"))
            if plan.new_source_hashes is not None:
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
    parser.add_argument(
        "--pre-ref",
        required=True,
        help="Explicit commit-ish naming the tree state BEFORE the DNASupercoiling dispatcher edit to "
        "_l2_2_design_a_runner_helpers.py. Never assumed/guessed by this tool.",
    )
    parser.add_argument("--bundle-root", default=str(schema.BUNDLE_ROOT))
    parser.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    parser.add_argument("--registry", default=str(schema.L2_EVENT_REGISTRY_PATH))
    parser.add_argument("--processes", default=None, help="Comma-separated subset; default: every in-scope process.")
    parser.add_argument("--apply", action="store_true", help="Actually write migrated files (default: dry run).")
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
