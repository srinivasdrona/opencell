"""One-shot migration: whole-catalog `sweep_provenance.json` -> per-process
catalog-contract `sweep_provenance.json` (R6 catalog-provenance fix).

Context (2026-09-04): every tracked `evidence_bundle/<Process>/<subdir>/
sweep_provenance.json`'s `source_hashes` recorded a whole-file sha256 of
``PROCESS_CATALOG.yaml`` (and, for `event_class` rows, `event_registry.yaml`)
under a `"catalog"`/`"l2_event_registry"` key. `schema.py`/`sweep.py`/
`generator.py` no longer compute or check those whole-file keys (see
``schema.process_contract_hashes`` / EVIDENCE_INDEX_SPEC.md Section 13.18) --
they now compute a process-specific resolved `"catalog_entry"`/
`"event_registry_entry"` hash instead. Every EXISTING tracked
`sweep_provenance.json` must therefore be migrated from the old key(s) to
the new one(s) so it stops looking stale under the new (correct) staleness
check, WITHOUT rerunning the (slow, oracle-dependent) sweep and WITHOUT
rewriting a single byte of `result.json`/`thresholds.json`/any other
authority/sidecar file.

This tool is deliberately conservative and fails closed per row:

  - Takes an EXPLICIT ``--pre-ref`` (a commit-ish naming the tree state
    BEFORE the catalog/registry edit that broke this row's whole-file
    hash). Never guesses/assumes it.
  - For each row with existing evidence, verifies its recorded
    `source_hashes["catalog"]` (whole-file) hash equals the ACTUAL sha256
    of ``PROCESS_CATALOG.yaml`` as it existed at ``--pre-ref`` (via
    ``git show <ref>:<path>``, never a local checkout of that ref) --
    a row whose recorded hash does NOT match this is left completely
    untouched (never migrated), since we cannot otherwise prove what it
    was actually compared against.
  - Verifies every OTHER recorded `source_hashes` entry (runner/helpers/
    projections/vivarium_init/oc_module/process- and harness-scoped
    dependency modules) still matches the CURRENT tree, and every
    `sidecar_hashes` entry still matches the CURRENT bytes on disk --
    any drift leaves the row untouched (it has a real, unrelated
    staleness problem this migration must not paper over).
  - Resolves the process's OWN catalog contract (`schema.
    resolve_catalog_process_contract`) at BOTH `--pre-ref` and the
    CURRENT tree and requires them to be BYTE-IDENTICAL (after canonical
    JSON serialization) -- a process whose own row genuinely changed
    (e.g. Cytokinesis's M_ticks 4000->5000) is correctly refused, not
    silently migrated. Same check for the event-registry contract on
    `event_class` rows.
  - Only then rewrites `source_hashes`: drops the old `"catalog"`
    (+`"l2_event_registry"`) key(s), adds the new `"catalog_entry"`
    (+`"event_registry_entry"`) key(s) computed against the CURRENT tree
    (proven identical to the pre-ref value by the contract-equality check
    above). Every other field in the sentinel (`process`/`n_seeds`/
    `m_ticks`/`completion_status`/`git_sha`/`git_dirty`/`sidecar_hashes`/
    `inputs_verified`/`evaluator_schema_version`/`result_schema_version`/
    every OTHER `source_hashes` entry) is copied through completely
    unchanged -- this tool never touches `result.json`/`thresholds.json`/
    `null_calibration.json`/`SUMMARY.json`/`analytical_check.json`/
    `input_manifest.json`/`provenance.json` at all.
  - Writes atomically (temp file + `os.replace`) so a crash mid-run never
    corrupts a row; idempotent/resumable (a row already migrated -- no
    `"catalog"` key present -- is reported `ALREADY_MIGRATED` and left
    alone, so re-running after a partial/interrupted run is always safe).

CLI:
    bin\\oc-py scripts/l22_evidence/migrate_catalog_provenance.py \\
        --pre-ref f71cfbb [--processes P1,P2] [--apply]

Dry-run (no ``--apply``) prints the per-row plan and touches nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import sweep  # noqa: E402
from scripts.l22_evidence.populate import _resolve_worktree_gitdir  # noqa: E402
from scripts.l22_extraction import derive_scope as _ds  # noqa: E402

REPO_ROOT = cat.REPO_ROOT

# Old (pre-migration) whole-file keys this tool removes.
OLD_CATALOG_KEY = "catalog"
OLD_REGISTRY_KEY = "l2_event_registry"
# New (post-migration) process-specific keys `schema.process_contract_hashes`
# computes -- see that function's docstring.
NEW_CATALOG_KEY = "catalog_entry"
NEW_REGISTRY_KEY = "event_registry_entry"

STATUS_MIGRATED = "MIGRATED"
STATUS_WOULD_MIGRATE = "WOULD_MIGRATE"
STATUS_ALREADY_MIGRATED = "ALREADY_MIGRATED"
STATUS_NO_EVIDENCE = "NO_EVIDENCE"
STATUS_NO_OLD_CATALOG_KEY = "SKIPPED_NO_OLD_CATALOG_KEY"
STATUS_PRE_REF_CATALOG_MISMATCH = "SKIPPED_PRE_REF_CATALOG_MISMATCH"
STATUS_PRE_REF_REGISTRY_MISMATCH = "SKIPPED_PRE_REF_REGISTRY_MISMATCH"
STATUS_NON_CATALOG_SOURCE_DRIFT = "SKIPPED_NON_CATALOG_SOURCE_DRIFT"
STATUS_SIDECAR_DRIFT = "SKIPPED_SIDECAR_DRIFT"
STATUS_CONTRACT_CHANGED = "SKIPPED_CONTRACT_CHANGED"
STATUS_HARNESS_MISMATCH = "SKIPPED_HARNESS_MISMATCH"
STATUS_PROCESS_NOT_IN_PRE_REF = "SKIPPED_PROCESS_NOT_IN_PRE_REF"

# Statuses that mean "nothing changed, and nothing needed to" -- distinct
# from a genuine refusal (SKIPPED_*), which always names a concrete reason
# a maintainer should investigate before ever migrating that row by hand.
_TERMINAL_NO_OP_STATUSES = frozenset({STATUS_ALREADY_MIGRATED, STATUS_NO_EVIDENCE})


class MigrationError(Exception):
    """Raised for an operational failure (bad ref, unreadable git object,
    malformed JSON/YAML) -- distinct from a per-row `SKIPPED_*` refusal,
    which is an expected, handled outcome, never an exception."""


@dataclass
class RowPlan:
    process: str
    status: str
    reason: str | None = None
    evidence_dir: Path | None = None
    new_source_hashes: dict[str, Any] | None = None
    old_source_hashes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"process": self.process, "status": self.status, "reason": self.reason}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_show_text(ref: str, rel_path: str, *, repo_root: Path = REPO_ROOT) -> str:
    """``git show <ref>:<rel_path>`` as text, resolving a Windows-created
    linked worktree's gitdir the same way `populate._git_sha` does (native
    WSL/Linux git cannot otherwise resolve an absolute `E:/...`-style
    `.git` pointer target -- see that function's docstring). Raises
    `MigrationError` naming the ref/path on any failure; never returns a
    guessed/empty/partial string. `rel_path` uses forward slashes (a git
    pathspec, not an OS path) regardless of host platform.
    """
    worktree_gitdir = _resolve_worktree_gitdir(repo_root)
    args = (
        ["git", "--git-dir", str(worktree_gitdir), "show", f"{ref}:{rel_path}"]
        if worktree_gitdir is not None
        else ["git", "-C", str(repo_root), "show", f"{ref}:{rel_path}"]
    )
    try:
        # `encoding="utf-8"` is explicit and mandatory here: `text=True`
        # alone lets `subprocess` fall back to `locale.getpreferredencoding()`
        # (e.g. cp1252 on a default-locale Windows host), which both
        # mis-decodes any non-ASCII byte actually committed to the YAML
        # (a UnicodeDecodeError, or worse, silent mojibake under
        # `errors="replace"`-style fallbacks) and can never reproduce the
        # UTF-8 bytes `_sha256_text`/`yaml.safe_load` below expect -- git
        # itself stores/emits these files as UTF-8 regardless of host
        # locale, so decoding as anything else is never correct.
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    except subprocess.CalledProcessError as exc:
        raise MigrationError(
            f"git show {ref}:{rel_path} failed (exit {exc.returncode}): {(exc.stderr or '').strip()}"
        ) from exc
    except OSError as exc:
        raise MigrationError(f"git show {ref}:{rel_path} failed to start: {exc}") from exc
    return result.stdout


@dataclass
class PreRefState:
    """Everything resolved against `--pre-ref`, computed ONCE per migration
    run (never per-row) since it never depends on which process is being
    evaluated."""

    ref: str
    catalog_text: str
    catalog_hash: str
    catalog_dict: dict[str, Any] = field(repr=False)
    registry_text: str | None = None
    registry_hash: str | None = None
    registry_dict: dict[str, Any] | None = field(default=None, repr=False)


def _relative_to_repo_root(repo_root: Path, path: Path) -> str:
    """`path` expressed relative to `repo_root` as a forward-slash git
    pathspec. Deliberately parameterized on `repo_root` (never the
    module-global `cat.REPO_ROOT`) so this tool -- and its tests -- can
    resolve paths correctly against a synthetic/throwaway git repository,
    not only the real one. Falls back to `str(path)` unchanged if `path`
    is not actually under `repo_root` (mirrors `catalog.relative_to_repo`'s
    own fallback)."""
    try:
        return str(Path(path).resolve().relative_to(Path(repo_root).resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def load_pre_ref_state(
    pre_ref: str,
    *,
    catalog_path: Path = schema.CATALOG_PATH,
    registry_path: Path = schema.L2_EVENT_REGISTRY_PATH,
    repo_root: Path = REPO_ROOT,
    need_registry: bool = True,
) -> PreRefState:
    catalog_rel = _relative_to_repo_root(repo_root, catalog_path)
    catalog_text = git_show_text(pre_ref, catalog_rel, repo_root=repo_root)
    catalog_hash = _sha256_text(catalog_text)
    catalog_dict = yaml.safe_load(catalog_text) or {}

    registry_text = registry_hash = registry_dict = None
    if need_registry:
        registry_rel = _relative_to_repo_root(repo_root, registry_path)
        registry_text = git_show_text(pre_ref, registry_rel, repo_root=repo_root)
        registry_hash = _sha256_text(registry_text)
        registry_dict = yaml.safe_load(registry_text) or {}

    return PreRefState(
        ref=pre_ref,
        catalog_text=catalog_text,
        catalog_hash=catalog_hash,
        catalog_dict=catalog_dict,
        registry_text=registry_text,
        registry_hash=registry_hash,
        registry_dict=registry_dict,
    )


def _evidence_dir_for(entry: cat.ProcessEntry, bundle_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return bundle_root / entry.name / subdir


def plan_row_migration(
    entry: cat.ProcessEntry,
    *,
    pre_ref_state: PreRefState,
    bundle_root: Path,
    catalog_path: Path = schema.CATALOG_PATH,
    registry_path: Path = schema.L2_EVENT_REGISTRY_PATH,
) -> RowPlan:
    """Evaluate ONE process's tracked `sweep_provenance.json` against every
    fail-closed precondition and return the migration decision -- never
    writes anything (see `apply_plan` for that)."""
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
            name, STATUS_HARNESS_MISMATCH, f"sweep_provenance.json process={payload.get('process')!r} != {name!r}", evidence_dir
        )

    source_hashes = payload.get("source_hashes") or {}

    if OLD_CATALOG_KEY not in source_hashes:
        if NEW_CATALOG_KEY in source_hashes:
            return RowPlan(name, STATUS_ALREADY_MIGRATED, None, evidence_dir)
        return RowPlan(
            name,
            STATUS_NO_OLD_CATALOG_KEY,
            f"source_hashes has neither {OLD_CATALOG_KEY!r} nor {NEW_CATALOG_KEY!r} -- unexpected format, refusing to guess",
            evidence_dir,
        )

    # (1) The recorded whole-catalog hash must match the EXPLICIT --pre-ref
    # the operator supplied -- never assumed, never fuzzy-matched.
    recorded_catalog_hash = source_hashes.get(OLD_CATALOG_KEY)
    if recorded_catalog_hash != pre_ref_state.catalog_hash:
        return RowPlan(
            name,
            STATUS_PRE_REF_CATALOG_MISMATCH,
            f"recorded catalog hash {str(recorded_catalog_hash)[:12]!r}.. != --pre-ref {pre_ref_state.ref!r} "
            f"catalog hash {pre_ref_state.catalog_hash[:12]!r}.. -- this row was generated against a DIFFERENT "
            "catalog state than --pre-ref names; leaving untouched",
            evidence_dir,
        )

    is_event_class = entry.harness_type == "event_class"
    if is_event_class:
        if pre_ref_state.registry_hash is None:
            return RowPlan(
                name, STATUS_HARNESS_MISMATCH, "event_class row but PreRefState was built with need_registry=False", evidence_dir
            )
        recorded_registry_hash = source_hashes.get(OLD_REGISTRY_KEY)
        if recorded_registry_hash != pre_ref_state.registry_hash:
            return RowPlan(
                name,
                STATUS_PRE_REF_REGISTRY_MISMATCH,
                f"recorded l2_event_registry hash {str(recorded_registry_hash)[:12]!r}.. != --pre-ref "
                f"{pre_ref_state.ref!r} registry hash {pre_ref_state.registry_hash[:12]!r}..",
                evidence_dir,
            )

    # (2) Every OTHER recorded source hash (runner/helpers/projections/
    # vivarium_init/oc_module/process- and harness-scoped dependency
    # modules) must still match the CURRENT tree. Reuse the ALREADY-FIXED
    # `sweep.current_source_hashes` (it no longer computes catalog/registry
    # keys at all -- see schema.process_contract_hashes) so this check can
    # never itself drift from the real staleness-detection code path.
    current_hashes = sweep.current_source_hashes(
        entry.oc_module, process=name, harness_type=entry.harness_type, catalog_path=catalog_path, registry_path=registry_path
    )
    non_contract_current = {k: v for k, v in current_hashes.items() if k not in (NEW_CATALOG_KEY, NEW_REGISTRY_KEY)}
    non_contract_recorded = {k: v for k, v in source_hashes.items() if k not in (OLD_CATALOG_KEY, OLD_REGISTRY_KEY)}
    if non_contract_current != non_contract_recorded:
        drifted = sorted(
            set(non_contract_current) ^ set(non_contract_recorded)
            | {k for k in non_contract_current if non_contract_current.get(k) != non_contract_recorded.get(k)}
        )
        return RowPlan(
            name,
            STATUS_NON_CATALOG_SOURCE_DRIFT,
            f"non-catalog source_hashes drifted vs current tree: {drifted!r}",
            evidence_dir,
        )

    # (3) Every mandatory authority/sidecar file's recorded sidecar_hashes
    # entry must still match its CURRENT bytes on disk (mirrors
    # `sweep.build_sweep_provenance`'s own construction exactly).
    current_sidecars = {
        fname: _sha256_file(evidence_dir / fname)
        for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES
        if (evidence_dir / fname).is_file()
    }
    recorded_sidecars = payload.get("sidecar_hashes") or {}
    if current_sidecars != recorded_sidecars:
        drifted = sorted(set(current_sidecars) ^ set(recorded_sidecars) | {
            k for k in current_sidecars if current_sidecars.get(k) != recorded_sidecars.get(k)
        })
        return RowPlan(name, STATUS_SIDECAR_DRIFT, f"sidecar_hashes drifted vs current bytes: {drifted!r}", evidence_dir)

    # (4) The process's OWN resolved catalog contract must be IDENTICAL
    # between --pre-ref and the current tree -- a process whose own row
    # genuinely changed (Cytokinesis's M_ticks 4000->5000) must stay
    # refused, never silently migrated.
    try:
        old_contract = schema.resolve_catalog_process_contract(name, pre_ref_state.catalog_dict)
    except ValueError as exc:
        return RowPlan(name, STATUS_PROCESS_NOT_IN_PRE_REF, str(exc), evidence_dir)
    current_catalog_dict = _ds.load_catalog(Path(catalog_path))
    current_contract = schema.resolve_catalog_process_contract(name, current_catalog_dict)
    if old_contract != current_contract:
        return RowPlan(
            name,
            STATUS_CONTRACT_CHANGED,
            f"resolved catalog contract changed between --pre-ref {pre_ref_state.ref!r} and current tree "
            f"(old={old_contract!r} new={current_contract!r})",
            evidence_dir,
        )

    if is_event_class:
        try:
            old_registry_contract = schema.resolve_event_registry_process_contract(name, pre_ref_state.registry_dict)
        except ValueError as exc:
            return RowPlan(name, STATUS_PROCESS_NOT_IN_PRE_REF, str(exc), evidence_dir)
        current_registry_dict = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        current_registry_contract = schema.resolve_event_registry_process_contract(name, current_registry_dict)
        if old_registry_contract != current_registry_contract:
            return RowPlan(
                name,
                STATUS_CONTRACT_CHANGED,
                f"resolved event_registry contract changed between --pre-ref {pre_ref_state.ref!r} and current "
                f"tree (old={old_registry_contract!r} new={current_registry_contract!r})",
                evidence_dir,
            )

    # Every precondition holds: build the migrated source_hashes -- drop
    # the old whole-file key(s), add the new process-specific key(s)
    # (computed against the CURRENT tree; proven identical in content to
    # what --pre-ref would have produced by the contract-equality checks
    # above). Every OTHER key is copied through byte-for-byte unchanged.
    new_source_hashes = dict(source_hashes)
    new_source_hashes.pop(OLD_CATALOG_KEY, None)
    new_source_hashes.pop(OLD_REGISTRY_KEY, None)
    new_source_hashes.update(
        schema.process_contract_hashes(name, entry.harness_type, catalog_path=catalog_path, registry_path=registry_path)
    )

    return RowPlan(
        name,
        STATUS_WOULD_MIGRATE,
        None,
        evidence_dir,
        new_source_hashes=new_source_hashes,
        old_source_hashes=source_hashes,
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

    need_registry = any(entries[n].harness_type == "event_class" for n in names)
    pre_ref_state = load_pre_ref_state(
        pre_ref, catalog_path=catalog_path, registry_path=registry_path, repo_root=repo_root, need_registry=need_registry
    )

    return {
        name: plan_row_migration(
            entries[name],
            pre_ref_state=pre_ref_state,
            bundle_root=bundle_root,
            catalog_path=catalog_path,
            registry_path=registry_path,
        )
        for name in names
    }


def apply_plan(plans: dict[str, RowPlan]) -> dict[str, RowPlan]:
    """Atomically write every `STATUS_WOULD_MIGRATE` row's migrated
    `sweep_provenance.json` (temp file + `os.replace`, so a crash mid-run
    can never leave a half-written file); every other status is left
    completely untouched. Idempotent: re-running against the SAME plan (or
    a fresh `plan_migration()` call after a partial apply) never re-writes
    an already-migrated row -- `plan_row_migration` reports it
    `ALREADY_MIGRATED` before `apply_plan` is ever reached. Returns a NEW
    dict with `STATUS_WOULD_MIGRATE` rows updated to `STATUS_MIGRATED`."""
    results: dict[str, RowPlan] = {}
    for name, plan in plans.items():
        if plan.status != STATUS_WOULD_MIGRATE:
            results[name] = plan
            continue
        assert plan.evidence_dir is not None and plan.new_source_hashes is not None  # narrows for type-checkers
        prov_path = plan.evidence_dir / schema.SWEEP_PROVENANCE_FILE
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
        payload["source_hashes"] = plan.new_source_hashes
        tmp_path = prov_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, prov_path)
        results[name] = RowPlan(
            name, STATUS_MIGRATED, None, plan.evidence_dir, plan.new_source_hashes, plan.old_source_hashes
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
        help="Explicit commit-ish naming the tree state BEFORE the catalog/registry edit that broke the "
        "old whole-file hash (e.g. the commit immediately before Cytokinesis's M_ticks 4000->5000 change). "
        "Never assumed/guessed by this tool.",
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
