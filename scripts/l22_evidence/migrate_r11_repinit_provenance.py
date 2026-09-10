"""One-shot migration: R11's ReplicationInitiation trace-resolver redirect
(a genuinely new, narrowly-scoped addition to
`_l2_2_design_a_runner_helpers.py` -- see `scripts/l22_evidence/schema.py`'s
"R11" section and `tests/vivarium/_l2_2_repinit_runner_helpers.py`'s module
docstring for the full design) changes that shared file's raw bytes, which
`input_manifest.json` records a PLAIN whole-file sha256 of for every
`design_a_per_tick` process (a completely separate mechanism from
`sweep_provenance.json["source_hashes"]["helpers"]`, which schema.py's R11
redaction is specifically designed to leave UNCHANGED for every process
other than ReplicationInitiation -- see below).

Unlike `migrate_helpers_provenance.py` (R7's migration, which rewrote BOTH
`sweep_provenance.json["source_hashes"]["helpers"]` AND `input_manifest.
json`'s whole-file entry, because R7 changed the MEANING of the recorded
`"helpers"` key from a whole-file hash to a redacted-generic one), this
migration only ever touches `input_manifest.json`'s whole-file entry (plus
the `sweep_provenance.json["sidecar_hashes"]["input_manifest.json"]` binding
that must track it). `sweep_provenance.json["source_hashes"]["helpers"]`
itself needs NO rewrite for any of these rows: `schema.runner_helpers_
generic_hash()` is proven (empirically, by THIS tool, before it writes
anything) to return the IDENTICAL value whether evaluated against
`--pre-ref`'s blob or the current tree, for every process this migration
touches -- R11's redaction was specifically designed around this property
(see `schema.py`'s `_r11_repinit_insertion_spans` docstring), not asserted.

This tool is deliberately conservative and fails closed per row, mirroring
`migrate_helpers_provenance.py`'s structure exactly:

  - Takes an EXPLICIT ``--pre-ref`` (a commit-ish naming the tree state
    BEFORE the R11 redirect was added to `_l2_2_design_a_runner_helpers.
    py`). Never guesses/assumes it.
  - Verifies, ONCE, globally: `schema.runner_helpers_generic_hash()`
    evaluated against `--pre-ref`'s blob text equals the CURRENT tree's
    value. If this fails, the tool refuses EVERY row outright (the R11
    redaction is not doing what it claims, so nothing downstream can be
    trusted) -- see `--pre-ref`'s check in `main()`.
  - Per row (process), verifies `schema.tick_runner_entry_hash(process)`
    is ALSO unchanged pre-ref vs current -- catches any row whose OWN
    runner function happened to change for an unrelated reason.
  - Reuses `migrate_helpers_provenance._plan_input_manifest_migration`
    (imported, not duplicated) for the actual `input_manifest.json`
    whole-file-hash re-stamp plan: it independently verifies the row's
    recorded whole-file hash matches `--pre-ref`'s actual whole-file
    hash before proposing any change, and refuses (not silently skips)
    on any mismatch.
  - `ReplicationInitiation` itself is NEVER migrated by this tool -- its
    row requires a genuine fresh sweep, since its own trace-loading code
    (and therefore its evidence) genuinely, substantively changed.
  - Writes atomically (temp file + `os.replace`); idempotent/resumable.

CLI:
    bin\\oc-py scripts/l22_evidence/migrate_r11_repinit_provenance.py \\
        --pre-ref <ref> [--processes P1,P2] [--apply]

Dry-run (no ``--apply``) prints the per-row plan and touches nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import migrate_helpers_provenance as mhp  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

REPO_ROOT = cat.REPO_ROOT

NEVER_MIGRATE_PROCESSES = frozenset({"ReplicationInitiation"})

STATUS_MIGRATED = "MIGRATED"
STATUS_WOULD_MIGRATE = "WOULD_MIGRATE"
STATUS_ALREADY_MIGRATED = "ALREADY_MIGRATED"
STATUS_NO_EVIDENCE = "NO_EVIDENCE"
STATUS_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"
STATUS_NEVER_MIGRATE = "SKIPPED_NEVER_MIGRATE"
STATUS_TICK_RUNNER_DRIFT = "SKIPPED_TICK_RUNNER_DRIFT"
STATUS_INPUT_MANIFEST_DRIFT = "SKIPPED_INPUT_MANIFEST_DRIFT"


class MigrationError(Exception):
    """Operational failure (bad ref, unreadable git object, or the global
    R11 redaction-equality precondition itself failing) -- distinct from a
    per-row `SKIPPED_*` refusal, which is an expected, handled outcome."""


@dataclass
class RowPlan:
    process: str
    status: str
    reason: str | None = None
    evidence_dir: Path | None = None
    new_input_manifest_sha256: str | None = None
    input_manifest_helpers_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"process": self.process, "status": self.status, "reason": self.reason}


def _evidence_dir_for(entry: cat.ProcessEntry, bundle_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return bundle_root / entry.name / subdir


def plan_row_migration(
    entry: cat.ProcessEntry,
    *,
    pre_ref: str,
    pre_ref_helpers_hash: str,
    bundle_root: Path,
) -> RowPlan:
    """Evaluate ONE process's tracked evidence against every fail-closed
    precondition and return the migration decision -- never writes
    anything (see `apply_plan`)."""
    name = entry.name
    evidence_dir = _evidence_dir_for(entry, bundle_root)

    if name in NEVER_MIGRATE_PROCESSES:
        return RowPlan(name, STATUS_NEVER_MIGRATE, "its own trace-loading code genuinely changed (R11)", evidence_dir)
    if entry.harness_type != "design_a_per_tick":
        return RowPlan(
            name, STATUS_NOT_APPLICABLE, f"harness_type={entry.harness_type!r} never routes through the runner-helpers file", evidence_dir
        )

    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    if not prov_path.is_file():
        return RowPlan(name, STATUS_NO_EVIDENCE, "no sweep_provenance.json under the tracked bundle", evidence_dir)

    # This process's OWN tick-runner function must be untouched between
    # --pre-ref and the current tree -- R11 only ever redirects trace
    # resolution/oracle loading, never any process's per-tick execution
    # function, but this is verified mechanically here rather than assumed.
    pre_ref_tick_runner_hash = schema.tick_runner_entry_hash(name, source=mhp.git_show_text(pre_ref, "tests/vivarium/_l2_2_design_a_runner_helpers.py", repo_root=REPO_ROOT))
    current_tick_runner_hash = schema.tick_runner_entry_hash(name)
    if pre_ref_tick_runner_hash is None or pre_ref_tick_runner_hash != current_tick_runner_hash:
        return RowPlan(
            name,
            STATUS_TICK_RUNNER_DRIFT,
            f"this process's own tick-runner source changed between --pre-ref {pre_ref!r} "
            f"({str(pre_ref_tick_runner_hash)[:12]!r}..) and current tree ({str(current_tick_runner_hash)[:12]!r}..)",
            evidence_dir,
        )

    new_input_manifest_sha256, input_manifest_helpers_index, refusal = mhp._plan_input_manifest_migration(
        name, evidence_dir, pre_ref=pre_ref, pre_ref_helpers_hash=pre_ref_helpers_hash
    )
    if refusal is not None:
        return RowPlan(name, STATUS_INPUT_MANIFEST_DRIFT, refusal.reason, evidence_dir)

    if new_input_manifest_sha256 is None:
        return RowPlan(name, STATUS_ALREADY_MIGRATED, None, evidence_dir)

    return RowPlan(
        name,
        STATUS_WOULD_MIGRATE,
        None,
        evidence_dir,
        new_input_manifest_sha256=new_input_manifest_sha256,
        input_manifest_helpers_index=input_manifest_helpers_index,
    )


def plan_migration(
    *,
    pre_ref: str,
    bundle_root: Path = schema.BUNDLE_ROOT,
    catalog_path: Path = schema.CATALOG_PATH,
    processes: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, RowPlan]:
    """Read-only: evaluate every (or every requested) in-scope process and
    return its migration decision. Never writes anything -- see
    `apply_plan`.

    Before evaluating any individual row, verifies the GLOBAL R11
    precondition this entire migration depends on:
    `schema.runner_helpers_generic_hash()` evaluated against `--pre-ref`'s
    blob text must equal its value on the current tree. This is the
    mechanical proof that R11's redaction makes the shared, redacted
    `"helpers"` hash insensitive to the ReplicationInitiation redirect for
    every OTHER process -- if it does not hold, this tool refuses outright
    (raises `MigrationError`) rather than silently proceeding on individual
    rows with a broken foundational assumption."""
    entries = cat.in_scope_processes(catalog_path)
    names = sorted(entries) if processes is None else list(processes)
    unknown = [n for n in names if n not in entries]
    if unknown:
        raise MigrationError(f"unknown/not-in-scope process(es): {unknown}; available: {sorted(entries)}")

    helpers_rel = mhp._relative_to_repo_root(repo_root, schema.RUNNER_HELPERS_MODULE)
    pre_ref_helpers_text = mhp.git_show_text(pre_ref, helpers_rel, repo_root=repo_root)
    pre_ref_helpers_hash = hashlib.sha256(pre_ref_helpers_text.encode("utf-8")).hexdigest()

    pre_ref_generic_hash = schema.runner_helpers_generic_hash(source=pre_ref_helpers_text)
    current_generic_hash = schema.runner_helpers_generic_hash()
    if pre_ref_generic_hash != current_generic_hash:
        raise MigrationError(
            "GLOBAL R11 PRECONDITION FAILED: schema.runner_helpers_generic_hash() differs between "
            f"--pre-ref {pre_ref!r} ({str(pre_ref_generic_hash)[:12]!r}..) and the current tree "
            f"({str(current_generic_hash)[:12]!r}..) -- the R11 redaction does not make this hash "
            "insensitive to the ReplicationInitiation redirect as designed; refusing to migrate ANY row."
        )

    return {
        name: plan_row_migration(
            entries[name],
            pre_ref=pre_ref,
            pre_ref_helpers_hash=pre_ref_helpers_hash,
            bundle_root=bundle_root,
        )
        for name in names
    }


def apply_plan(plans: dict[str, RowPlan]) -> dict[str, RowPlan]:
    """Atomically write every `STATUS_WOULD_MIGRATE` row's migrated
    `input_manifest.json` helpers-entry sha256, and fold the resulting
    file's own new sha256 into `sweep_provenance.json["sidecar_hashes"]
    ["input_manifest.json"]` (R1: that key binds the sentinel to
    `input_manifest.json`'s exact bytes) -- every other status/field is
    left completely untouched."""
    results: dict[str, RowPlan] = {}
    for name, plan in plans.items():
        if plan.status != STATUS_WOULD_MIGRATE:
            results[name] = plan
            continue
        assert plan.evidence_dir is not None
        assert plan.new_input_manifest_sha256 is not None
        assert plan.input_manifest_helpers_index is not None

        manifest_path = plan.evidence_dir / "input_manifest.json"
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload["inputs"][plan.input_manifest_helpers_index]["sha256"] = plan.new_input_manifest_sha256
        manifest_tmp_path = manifest_path.with_suffix(".json.tmp")
        manifest_tmp_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(manifest_tmp_path, manifest_path)
        new_input_manifest_sidecar_sha = mhp._sha256_file(manifest_path)

        prov_path = plan.evidence_dir / schema.SWEEP_PROVENANCE_FILE
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
        if "input_manifest.json" in (payload.get("sidecar_hashes") or {}):
            payload["sidecar_hashes"]["input_manifest.json"] = new_input_manifest_sidecar_sha
            tmp_path = prov_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp_path, prov_path)

        results[name] = RowPlan(
            name,
            STATUS_MIGRATED,
            None,
            plan.evidence_dir,
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
        help="Explicit commit-ish naming the tree state BEFORE the R11 ReplicationInitiation redirect "
        "was added to _l2_2_design_a_runner_helpers.py. Never assumed/guessed by this tool.",
    )
    parser.add_argument("--bundle-root", default=str(schema.BUNDLE_ROOT))
    parser.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    parser.add_argument("--processes", default=None, help="Comma-separated subset; default: every in-scope process.")
    parser.add_argument("--apply", action="store_true", help="Actually write migrated files (default: dry run).")
    args = parser.parse_args(argv)

    processes = [p.strip() for p in args.processes.split(",") if p.strip()] if args.processes else None

    try:
        plans = plan_migration(
            pre_ref=args.pre_ref,
            bundle_root=Path(args.bundle_root),
            catalog_path=Path(args.catalog),
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
