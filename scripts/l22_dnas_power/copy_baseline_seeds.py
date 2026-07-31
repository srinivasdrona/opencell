"""Copy the already-accepted seeds 0-49 DNASupercoiling raw Karr traces from
another worktree (the source of record for the canonical N=50 evidence
bundle) into this worktree's `data/m1_sources/karr_native/` tree.

DNASupercoiling-only: every seed directory in the source root bundles many
processes' `<Process>_100ticks.mat` files together (they are per-seed, not
per-process, directories), but this tool copies *only*
`DNASupercoiling_100ticks.mat` for each requested seed -- it never touches
any other process's trace file, and never writes/deletes anything outside
the exact destination paths it computes.

Read-only with respect to the source: this module only ever reads from
`source_root` and copies bytes; it does not mutate the source worktree.
Every copy is hash-verified (sha256(source) == sha256(destination)) so a
downstream diagnostic run can trust the copied seeds 0-49 are bit-identical
to the ones underlying the canonical, already-accepted N=50 evidence
bundle (no silent corruption/edit in transit).

Preserves the existing source-root directory-naming convention: seed 0 ->
`per_process_traces_v2/` (unsuffixed), seed N>=1 -> `per_process_traces_v2_s{N:03d}/`.
Reuses `scripts/l22_extraction/launcher.py`'s own path helpers
(`canonical_seed0_path`, `seed_mat_path`) so this tool can never drift from
the launcher's own notion of where a seed's trace file lives.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.launcher import (  # noqa: E402
    KARR_NATIVE_ROOT,
    canonical_seed0_path,
    seed_mat_path,
)
from scripts.l22_extraction.trace_validation import sha256_file  # noqa: E402

PROCESS = "DNASupercoiling"
BASELINE_SEEDS = tuple(range(50))  # 0-49: the existing accepted canonical seeds.


@dataclass
class CopyRecord:
    seed: int
    source_path: str
    dest_path: str
    action: str  # "copied" | "skipped_identical" | "would_copy" (dry_run)
    sha256: str | None = None
    verified: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def copy_dnas_baseline(
    *,
    source_native_root: Path,
    dest_native_root: Path = KARR_NATIVE_ROOT,
    seeds: tuple[int, ...] = BASELINE_SEEDS,
    dry_run: bool = False,
) -> list[CopyRecord]:
    """Copy `DNASupercoiling_100ticks.mat` for every seed in `seeds` from
    `source_native_root` to `dest_native_root`, hash-verifying each copy.

    Idempotent: if the destination file already exists with a matching
    sha256, it is left untouched (`skipped_identical`) rather than
    re-copied. A destination file that exists with a *different* hash is
    an error (refuses to silently overwrite diverging data) unless the
    caller has removed it first.
    """
    records: list[CopyRecord] = []
    for seed in seeds:
        if seed == 0:
            src = canonical_seed0_path(PROCESS, karr_native_root=source_native_root)
            dst = canonical_seed0_path(PROCESS, karr_native_root=dest_native_root)
        else:
            src = seed_mat_path(PROCESS, seed, karr_native_root=source_native_root)
            dst = seed_mat_path(PROCESS, seed, karr_native_root=dest_native_root)

        if not src.exists():
            raise FileNotFoundError(f"Missing source baseline trace for seed {seed}: {src}")

        if dst.exists():
            src_hash = sha256_file(src)
            dst_hash = sha256_file(dst)
            if src_hash == dst_hash:
                records.append(
                    CopyRecord(
                        seed=seed,
                        source_path=str(src),
                        dest_path=str(dst),
                        action="skipped_identical",
                        sha256=dst_hash,
                        verified=True,
                    )
                )
                continue
            raise FileExistsError(
                f"Destination {dst} already exists with a DIFFERENT hash than source {src} "
                f"({dst_hash} != {src_hash}); refusing to overwrite. Remove it manually first "
                "if you intend to replace it."
            )

        if dry_run:
            records.append(
                CopyRecord(seed=seed, source_path=str(src), dest_path=str(dst), action="would_copy")
            )
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        src_hash = sha256_file(src)
        dst_hash = sha256_file(dst)
        records.append(
            CopyRecord(
                seed=seed,
                source_path=str(src),
                dest_path=str(dst),
                action="copied",
                sha256=dst_hash,
                verified=(src_hash == dst_hash),
            )
        )
        if src_hash != dst_hash:
            raise OSError(f"Copy verification FAILED for seed {seed}: {src} -> {dst}")

    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-native-root",
        required=True,
        help="Path to the source worktree's data/m1_sources/karr_native (e.g. of l22-final-sweep).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    records = copy_dnas_baseline(
        source_native_root=Path(args.source_native_root),
        dry_run=args.dry_run,
    )
    n_copied = sum(1 for r in records if r.action == "copied")
    n_skipped = sum(1 for r in records if r.action == "skipped_identical")
    n_would = sum(1 for r in records if r.action == "would_copy")
    print(
        f"[copy_baseline_seeds] seeds={len(records)} copied={n_copied} "
        f"skipped_identical={n_skipped} would_copy={n_would}"
    )
    unverified = [r for r in records if r.action == "copied" and not r.verified]
    if unverified:
        print(f"UNVERIFIED COPIES: {[r.seed for r in unverified]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
