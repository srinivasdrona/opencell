"""One-shot migration + mechanical equivalence proof:
`sweep_provenance.json["source_hashes"]["chromosome_store_module"]` after the
accepted DNASupercoiling hidden-chromosome-state extension to
`opencell/state/chromosome_store.py` (R8).

Context (2026-09 DNASupercoiling integration): the accepted DNAS candidate
extends `ChromosomeStore` with an OPT-IN hidden-state surface (new
`CHROMOSOME_HIDDEN_SPARSE_FIELDS`/`CHROMOSOME_HIDDEN_SCALAR_FIELDS`,
`AuxiliarySparseField`, `set_hidden_sparse_field`/`get_hidden_sparse_field`/
`set_hidden_scalar`/`get_hidden_scalar`, and a new protein-binding helper
producing `ChromosomeBindingResult`) that only DNASupercoiling's own new
ledgers/tests exercise. `opencell/state/chromosome_store.py` is a REGISTERED
`PROCESS_DEPENDENCY_FILES` entry for DNARepair, Replication,
ReplicationInitiation, and (informationally, event_class) DNADamage, so this
one file's whole-file hash mechanically stales all four rows the moment it
changes at all, regardless of whether the change touches anything THEY
actually exercise.

Unlike the R7 helpers-provenance fix, this file has no natural per-process
partition to redact (`ChromosomeStore` is one shared class every
chromosome-coupled process uses the SAME way, not a dispatch table of
per-process functions) -- so instead of a hash-granularity redesign, this
tool proves the SAME thing a redesign would have proven, by RUNNING the code:
for each target process, it loads its own REAL, tracked/local oracle trace
data through the OLD (`--pre-ref`) `ChromosomeStore` implementation (dynamically
executed from the exact git blob text, never checked out to disk) and the
CURRENT one, and asserts every sampled tick's `to_state()` output is BYTE-
IDENTICAL between the two (after canonical JSON-safe serialization). This is
a direct, executable, mechanical equivalence proof -- not a source-reading
argument -- using the exact data each process's own evidence was generated
against.

Fails closed per row:

  - Takes an EXPLICIT ``--pre-ref``. Never guesses it.
  - Verifies the row's recorded `source_hashes["chromosome_store_module"]`
    equals the ACTUAL sha256 of `opencell/state/chromosome_store.py` as it
    existed at `--pre-ref` (via ``git show``, never a local checkout).
  - Verifies every OTHER recorded `source_hashes` entry still matches the
    CURRENT tree -- any unrelated drift leaves the row untouched.
  - Verifies every mandatory authority/sidecar file's recorded
    `sidecar_hashes` entry still matches current bytes on disk.
  - Runs the equivalence check (see above) against a real, on-disk oracle
    trace registered for that process. A trace-loading failure, an empty
    sample set, or ANY tick mismatch refuses the row (never silently
    skipped/ignored).
  - Only then rewrites `source_hashes["chromosome_store_module"]` to the
    CURRENT file's plain sha256. Every other field is copied through
    unchanged -- this tool never touches `result.json`/`thresholds.json`/
    any other authority/sidecar file, and never touches
    `input_manifest.json` (chromosome_store.py is not one of its recorded
    "code" inputs).
  - Writes atomically (temp file + `os.replace`); idempotent/resumable.

CLI:
    bin\\oc-py scripts/l22_evidence/migrate_chromosome_store_provenance.py \\
        --pre-ref 8692137 [--processes DNARepair,Replication] [--apply]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
DEPENDENCY_KEY = "chromosome_store_module"

STATUS_MIGRATED = "MIGRATED"
STATUS_WOULD_MIGRATE = "WOULD_MIGRATE"
STATUS_ALREADY_MIGRATED = "ALREADY_MIGRATED"
STATUS_NO_EVIDENCE = "NO_EVIDENCE"
STATUS_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"
STATUS_HARNESS_MISMATCH = "SKIPPED_HARNESS_MISMATCH"
STATUS_NO_DEPENDENCY_KEY = "SKIPPED_NO_DEPENDENCY_KEY"
STATUS_PRE_REF_MISMATCH = "SKIPPED_PRE_REF_MISMATCH"
STATUS_OTHER_SOURCE_DRIFT = "SKIPPED_OTHER_SOURCE_DRIFT"
STATUS_SIDECAR_DRIFT = "SKIPPED_SIDECAR_DRIFT"
STATUS_NO_TRACE_REGISTERED = "SKIPPED_NO_TRACE_REGISTERED"
STATUS_TRACE_UNAVAILABLE = "SKIPPED_TRACE_UNAVAILABLE"
STATUS_EQUIVALENCE_FAILED = "SKIPPED_EQUIVALENCE_FAILED"

_TERMINAL_NO_OP_STATUSES = frozenset({STATUS_ALREADY_MIGRATED, STATUS_NO_EVIDENCE})


class MigrationError(Exception):
    """Operational failure (bad ref, unreadable git object) -- distinct from
    a per-row `SKIPPED_*` refusal, which is an expected, handled outcome."""


@dataclass
class TraceSample:
    """One real, on-disk oracle trace this tool samples for a process's
    equivalence check. `path` is repo-relative. `ticks` is the exact list of
    tick indices to sample from `group_name` (never "every tick that
    happens to exist" -- explicit and reviewable)."""

    path: str
    group_name: str
    ticks: list[int]


# Explicit, hand-maintained registry (mirrors `schema.PROCESS_DEPENDENCY_
# FILES`'s own "explicit, never mechanically derived" policy): which real,
# locally-available oracle trace(s) to replay through both chromosome_store
# implementations for each migratable process. Chosen to be the process's
# OWN canonical single-seed trace (already used by its L2.1 gate), which
# uniquely identifies a real, on-disk file and needs no cross-seed tick-
# count consistency (unlike the full N-seed corpus a sweep rerun would need).
TRACE_REGISTRY: dict[str, list[TraceSample]] = {
    "DNARepair": [
        TraceSample("data/m1_sources/karr_native/per_process_traces_v2/DNARepair_100ticks.mat", "states_before", list(range(100))),
        TraceSample("data/m1_sources/karr_native/per_process_traces_v2/DNARepair_100ticks.mat", "states_after", list(range(100))),
    ],
    "Replication": [
        TraceSample("data/m1_sources/karr_native/per_process_traces_v2/Replication_100ticks.mat", "states_before", list(range(100))),
        TraceSample("data/m1_sources/karr_native/per_process_traces_v2/Replication_100ticks.mat", "states_after", list(range(100))),
    ],
    "ReplicationInitiation": [
        TraceSample(
            "data/m1_sources/karr_native/per_process_traces_v2/ReplicationInitiation_100ticks.mat", "states_before", list(range(100))
        ),
        TraceSample(
            "data/m1_sources/karr_native/per_process_traces_v2/ReplicationInitiation_100ticks.mat", "states_after", list(range(100))
        ),
    ],
    "DNADamage": [
        TraceSample(
            "data/m1_sources/karr_native/genuine_signedzero_full_v2/dnadamage_stimulus_cohort/uvb_mechanism/"
            "per_process_traces_v2_event_s2000/DNADamage_20ticks.mat",
            "states_before",
            list(range(20)),
        ),
        TraceSample(
            "data/m1_sources/karr_native/genuine_signedzero_full_v2/dnadamage_stimulus_cohort/uvb_mechanism/"
            "per_process_traces_v2_event_s2000/DNADamage_20ticks.mat",
            "states_after",
            list(range(20)),
        ),
    ],
}


@dataclass
class RowPlan:
    process: str
    status: str
    reason: str | None = None
    evidence_dir: Path | None = None
    new_source_hashes: dict[str, Any] | None = None
    old_source_hashes: dict[str, Any] | None = None
    n_ticks_verified: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"process": self.process, "status": self.status, "reason": self.reason, "n_ticks_verified": self.n_ticks_verified}


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


def _load_chromosome_store_module_from_source(module_name: str, source_text: str, real_path: Path) -> Any:
    """Dynamically execute `source_text` (e.g. a `--pre-ref` git blob's exact
    bytes) as a real, importable Python module named `module_name`, WITHOUT
    ever writing it to disk. `real_path` is used only as the module's
    `__file__`/spec origin (for tracebacks); it is never read from. Raises
    `MigrationError` on any import/exec failure -- never returns a partially
    initialized module."""
    spec = importlib.util.spec_from_loader(module_name, loader=None, origin=str(real_path))
    if spec is None:
        raise MigrationError(f"could not build a module spec for {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        exec(compile(source_text, str(real_path), "exec"), module.__dict__)  # noqa: S102
    except Exception as exc:
        del sys.modules[module_name]
        raise MigrationError(f"failed to exec {module_name} from source: {exc}") from exc
    return module


def _canonical_state(value: Any) -> Any:
    """Recursively convert a `ChromosomeStore.to_state()`-shaped payload
    (nested dict/numpy-array/numpy-scalar/tuple) into plain, JSON-safe,
    order-independent Python types so two independently constructed payloads
    can be compared for EXACT equality regardless of numpy dtype/array
    object identity."""
    import numpy as np

    if isinstance(value, dict):
        return {key: _canonical_state(val) for key, val in sorted(value.items())}
    if isinstance(value, np.ndarray):
        return [_canonical_state(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (tuple, list)):
        return [_canonical_state(item) for item in value]
    if isinstance(value, float):
        # Exact-bit comparison via repr rather than `==` -- NaN-safe and
        # immune to any accidental float/int coercion difference between
        # the two implementations being compared.
        return repr(value)
    return value


def _tick_ref(dataset: Any, tick: int) -> Any:
    return dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]


def _replay_chromosome_state(module: Any, handle: Any, group_name: str, tick: int) -> dict[str, Any]:
    dataset = handle[f"{group_name}/chromosome"]
    ref = _tick_ref(dataset, tick)
    store = module.ChromosomeStore.from_hdf5_group(handle[ref])
    return _canonical_state(store.to_state())


def verify_process_equivalence(
    process: str,
    *,
    old_module: Any,
    new_module: Any,
    repo_root: Path = REPO_ROOT,
) -> tuple[bool, str | None, int]:
    """Real, executable equivalence check for `process`: replays every
    registered `TraceSample` tick through BOTH `old_module.ChromosomeStore`
    and `new_module.ChromosomeStore` and requires the canonicalized
    `to_state()` output to be byte-for-byte identical. Returns
    ``(ok, reason_or_None, n_ticks_verified)`` -- `ok=False` on the FIRST
    mismatch (reason names the exact file/group/tick), on a missing trace
    file, or on an empty sample registry (never silently "nothing to
    check")."""
    import h5py

    samples = TRACE_REGISTRY.get(process)
    if not samples:
        return False, f"no TraceSample entries registered for {process!r}", 0

    n_verified = 0
    for sample in samples:
        trace_path = repo_root / sample.path
        if not trace_path.is_file():
            return False, f"trace file not present on disk: {sample.path}", n_verified
        if not sample.ticks:
            return False, f"empty tick sample list for {sample.path}", n_verified
        with h5py.File(trace_path, "r") as handle:
            if sample.group_name not in handle:
                return False, f"{sample.path} has no group {sample.group_name!r}", n_verified
            for tick in sample.ticks:
                try:
                    old_state = _replay_chromosome_state(old_module, handle, sample.group_name, tick)
                except Exception as exc:  # noqa: BLE001
                    return False, f"{sample.path}:{sample.group_name}[{tick}] old module raised: {exc}", n_verified
                try:
                    new_state = _replay_chromosome_state(new_module, handle, sample.group_name, tick)
                except Exception as exc:  # noqa: BLE001
                    return False, f"{sample.path}:{sample.group_name}[{tick}] current module raised: {exc}", n_verified
                if old_state != new_state:
                    return (
                        False,
                        f"{sample.path}:{sample.group_name}[{tick}] to_state() mismatch between --pre-ref and current "
                        "chromosome_store.py",
                        n_verified,
                    )
                n_verified += 1
    return True, None, n_verified


def _evidence_dir_for(entry: cat.ProcessEntry, bundle_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return bundle_root / entry.name / subdir


def plan_row_migration(
    entry: cat.ProcessEntry,
    *,
    pre_ref: str,
    pre_ref_module: Any,
    pre_ref_hash: str,
    new_module: Any,
    bundle_root: Path,
    catalog_path: Path,
    registry_path: Path,
) -> RowPlan:
    name = entry.name
    evidence_dir = _evidence_dir_for(entry, bundle_root)

    if name not in TRACE_REGISTRY:
        return RowPlan(name, STATUS_NO_TRACE_REGISTERED, f"{name!r} has no registered TraceSample entries", evidence_dir)

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
    if recorded is None:
        return RowPlan(name, STATUS_NO_DEPENDENCY_KEY, f"source_hashes has no {DEPENDENCY_KEY!r} key", evidence_dir)

    current_hash = _sha256_file(schema.CHROMOSOME_STORE_MODULE)
    if recorded == current_hash:
        return RowPlan(name, STATUS_ALREADY_MIGRATED, None, evidence_dir)

    if recorded != pre_ref_hash:
        return RowPlan(
            name,
            STATUS_PRE_REF_MISMATCH,
            f"recorded {DEPENDENCY_KEY} hash {str(recorded)[:12]!r}.. != --pre-ref {pre_ref!r} "
            f"whole-file hash {pre_ref_hash[:12]!r}..",
            evidence_dir,
        )

    # Every OTHER recorded source hash must still match the current tree.
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

    ok, reason, n_verified = verify_process_equivalence(name, old_module=pre_ref_module, new_module=new_module)
    if not ok:
        return RowPlan(name, STATUS_EQUIVALENCE_FAILED, reason, evidence_dir, n_ticks_verified=n_verified)

    new_source_hashes = dict(source_hashes)
    new_source_hashes[DEPENDENCY_KEY] = current_hash
    return RowPlan(
        name,
        STATUS_WOULD_MIGRATE,
        None,
        evidence_dir,
        new_source_hashes=new_source_hashes,
        old_source_hashes=source_hashes,
        n_ticks_verified=n_verified,
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

    module_rel = _relative_to_repo_root(repo_root, schema.CHROMOSOME_STORE_MODULE)
    pre_ref_text = git_show_text(pre_ref, module_rel, repo_root=repo_root)
    pre_ref_hash = hashlib.sha256(pre_ref_text.encode("utf-8")).hexdigest()

    relevant = [n for n in names if n in TRACE_REGISTRY]
    pre_ref_module = None
    new_module = None
    if relevant:
        pre_ref_module = _load_chromosome_store_module_from_source(
            "_chromosome_store_pre_ref", pre_ref_text, schema.CHROMOSOME_STORE_MODULE
        )
        new_module = _load_chromosome_store_module_from_source(
            "_chromosome_store_current_for_migration", schema.CHROMOSOME_STORE_MODULE.read_text(encoding="utf-8"), schema.CHROMOSOME_STORE_MODULE
        )

    return {
        name: plan_row_migration(
            entries[name],
            pre_ref=pre_ref,
            pre_ref_module=pre_ref_module,
            pre_ref_hash=pre_ref_hash,
            new_module=new_module,
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
        prov_path = plan.evidence_dir / schema.SWEEP_PROVENANCE_FILE
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
        payload["source_hashes"] = plan.new_source_hashes
        tmp_path = prov_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, prov_path)
        results[name] = RowPlan(
            name, STATUS_MIGRATED, None, plan.evidence_dir, plan.new_source_hashes, plan.old_source_hashes, plan.n_ticks_verified
        )
    return results


def _print_report(plans: dict[str, RowPlan], *, applied: bool) -> None:
    tally: dict[str, int] = {}
    for plan in plans.values():
        tally[plan.status] = tally.get(plan.status, 0) + 1
        suffix = f"  -- {plan.reason}" if plan.reason else (f"  ({plan.n_ticks_verified} ticks verified)" if plan.n_ticks_verified else "")
        print(f"{plan.process:28s} {plan.status}{suffix}")
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
