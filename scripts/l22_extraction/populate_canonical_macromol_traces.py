"""Populate the canonical `per_process_traces_v2_sNNN/` layout with the
accepted MacromolecularComplexation active-window cohort.

Rationale: the ordinary, UNMODIFIED shared Design-A oracle loader
(`tests/vivarium/_l2_2_design_a_runner_helpers.py`, never edited for this
process) already looks for exactly this layout for every
`design_a_per_tick` process:

    data/m1_sources/karr_native/per_process_traces_v2_s{seed:03d}/
        MacromolecularComplexation_100ticks.mat

An earlier iteration of this closure routed the shared loader to the
active-window cohort via a process-scoped environment-variable override
(`OPENCELL_L22_PROCESS_ORACLE_ROOT__MACROMOLECULARCOMPLEXATION`), which
required editing the shared, universally-hashed loader module -- rejected
on review because it staled every OTHER `design_a_per_tick` process's
`sweep_provenance.json`. This script instead makes the shared loader find
the SAME accepted data at the SAME canonical path every other process
uses, by physically copying the 50 accepted, already-validated seed traces
from their tracked home under
`data/m1_sources/karr_native/macromol_active_window/` to the canonical
`per_process_traces_v2_s000/` .. `per_process_traces_v2_s049/` directories
-- zero shared code changes required.

Every copy is verified byte-for-byte (sha256 equality, both immediately
after copy and via a final independent re-hash pass). If a canonical
destination already exists with DIFFERENT content, this script fails
closed and reports the conflict rather than silently overwriting it --
there was no such conflict as of this writing (verified: zero
canonical-path MacromolecularComplexation traces existed before this
script first ran).

CLI:
    bin\\oc-py scripts/l22_extraction/populate_canonical_macromol_traces.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402

CANONICAL_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native"


class PopulationConflictError(RuntimeError):
    """A canonical destination path already exists with content that does
    NOT match the accepted active-window source -- fail closed, never
    silently overwrite."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_dest_path(seed: int) -> Path:
    return CANONICAL_ROOT / f"per_process_traces_v2_s{int(seed):03d}" / f"{maw.PROCESS_NAME}_100ticks.mat"


@dataclass(frozen=True)
class SeedPopulationRecord:
    seed: int
    source_path: Path
    dest_path: Path
    source_sha256: str
    dest_sha256_before: str | None
    dest_sha256_after: str
    action: str  # "copied" | "already_present_identical" | "dry_run_would_copy"

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "source_path": str(self.source_path),
            "dest_path": str(self.dest_path),
            "source_sha256": self.source_sha256,
            "dest_sha256_before": self.dest_sha256_before,
            "dest_sha256_after": self.dest_sha256_after,
            "action": self.action,
        }


def populate_canonical_traces(
    *, data_root: Path = maw.ACTIVE_WINDOW_ROOT, dry_run: bool = False
) -> list[SeedPopulationRecord]:
    """Copy all `maw.REQUIRED_N_SEEDS` accepted active-window seed traces to
    the canonical `per_process_traces_v2_sNNN/` layout. Fails closed
    (raises `PopulationConflictError`) if the FULL active-window cohort is
    not itself `SUFFICIENT_ENSEMBLE`-valid first (never populates a
    canonical path from unvalidated source data), or if any destination
    path already exists with content that disagrees with the accepted
    source."""
    audit = maw.audit_active_window_evidence(data_roots=(data_root,))
    if audit.status != "SUFFICIENT_ENSEMBLE":
        raise PopulationConflictError(
            f"active-window cohort at {data_root} is not SUFFICIENT_ENSEMBLE "
            f"(status={audit.status}); refusing to populate the canonical layout from "
            "unvalidated source data."
        )

    records: list[SeedPopulationRecord] = []
    for seed in range(maw.REQUIRED_N_SEEDS):
        source_path = maw._seed_trace_path(seed, data_root)  # noqa: SLF001
        if not source_path.is_file():
            raise PopulationConflictError(f"seed {seed}: expected accepted source trace missing: {source_path}")
        source_sha256 = _sha256_file(source_path)

        dest_path = _canonical_dest_path(seed)
        dest_sha256_before: str | None = None
        if dest_path.is_file():
            dest_sha256_before = _sha256_file(dest_path)
            if dest_sha256_before == source_sha256:
                records.append(
                    SeedPopulationRecord(
                        seed=seed,
                        source_path=source_path,
                        dest_path=dest_path,
                        source_sha256=source_sha256,
                        dest_sha256_before=dest_sha256_before,
                        dest_sha256_after=dest_sha256_before,
                        action="already_present_identical",
                    )
                )
                continue
            raise PopulationConflictError(
                f"seed {seed}: canonical destination {dest_path} already exists with DIFFERENT "
                f"content (dest sha256={dest_sha256_before}, accepted source sha256={source_sha256}). "
                "Refusing to overwrite -- resolve the conflict manually before re-running."
            )

        if dry_run:
            records.append(
                SeedPopulationRecord(
                    seed=seed,
                    source_path=source_path,
                    dest_path=dest_path,
                    source_sha256=source_sha256,
                    dest_sha256_before=None,
                    dest_sha256_after=source_sha256,
                    action="dry_run_would_copy",
                )
            )
            continue

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, dest_path)
        dest_sha256_after = _sha256_file(dest_path)
        if dest_sha256_after != source_sha256:
            raise PopulationConflictError(
                f"seed {seed}: post-copy hash mismatch (source={source_sha256}, "
                f"copied={dest_sha256_after}) -- filesystem-level corruption during copy; aborting."
            )
        records.append(
            SeedPopulationRecord(
                seed=seed,
                source_path=source_path,
                dest_path=dest_path,
                source_sha256=source_sha256,
                dest_sha256_before=dest_sha256_before,
                dest_sha256_after=dest_sha256_after,
                action="copied",
            )
        )

    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=maw.ACTIVE_WINDOW_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        records = populate_canonical_traces(data_root=args.data_root, dry_run=args.dry_run)
    except PopulationConflictError as exc:
        print(f"[populate-canonical-macromol-traces] FAILED CLOSED: {exc}", file=sys.stderr)
        return 2

    by_action: dict[str, int] = {}
    for record in records:
        by_action[record.action] = by_action.get(record.action, 0) + 1
    print(f"[populate-canonical-macromol-traces] {len(records)} seeds processed: {by_action}", file=sys.stderr)

    # Final independent re-hash pass over every destination path, proving
    # byte-for-byte equality with the source one more time after all copies
    # completed (catches any cross-seed clobbering bug in this script itself).
    if not args.dry_run:
        for record in records:
            current = _sha256_file(record.dest_path)
            if current != record.source_sha256:
                print(
                    f"[populate-canonical-macromol-traces] POST-HOC VERIFICATION FAILED for seed "
                    f"{record.seed}: {record.dest_path} sha256={current} != source sha256="
                    f"{record.source_sha256}",
                    file=sys.stderr,
                )
                return 3
        print("[populate-canonical-macromol-traces] final re-hash pass: all 50 destinations byte-identical to source", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
