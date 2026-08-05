"""Process-local N=50 seed audit for RibosomeAssembly event-window evidence.

Read-only, resumable, non-destructive: this module never writes, deletes,
or regenerates a trace file -- it only classifies the 50 seeds this task's
catalog contract (``N_seeds: 50``) requires as already-on-disk-and-valid
or not, reusing the SAME validation gauntlet
(:func:`scripts.l2_event.launcher.validate_existing_event_window`) the
resumable extraction planner already applies, so "valid" here means
exactly what "skip_valid" means there: seed identity
(``metadata.rng_seed``), n_ticks, window kind, the M4
stride/tick_start/tick_end contract, AND the current
``scripts/matlab/mnrnd.m`` shim version/hash all match -- never mere
file-existence.

Beyond per-seed validity, this module adds one more check
``validate_existing_event_window`` cannot perform on its own (it only ever
sees one file at a time): a **cross-seed** duplicate-content-hash scan.
Four candidate seed-000 files existed across sibling worktrees before this
task started, three different SHA-256 hashes among them -- i.e. it is a
real, observed failure mode for stale evidence to be silently reused
across seeds or worktrees. A seed cohort where two or more "valid" seeds
share an identical file hash is refused here even though each file
individually passes ``validate_existing_event_window`` -- that is exactly
the "seed 0 replicated/aliased as 50" failure this audit exists to catch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.evidence import sha256_file  # noqa: E402
from scripts.l2_event.launcher import (  # noqa: E402
    KARR_NATIVE_ROOT,
    _spec_from_dict,
    event_window_mat_path,
    validate_existing_event_window,
)

DEFAULT_SPECS_PATH = REPO_ROOT / "artifacts" / "l2_event_extraction" / "ribosome_n50_specs.json"
REQUIRED_N_SEEDS = 50


class SeedAuditError(Exception):
    """Raised for a malformed spec list (wrong count/seed set) -- distinct
    from an individual seed simply being invalid/missing, which is
    reported per-seed in the audit report rather than raised."""


def audit_ribosome_assembly_n50_seeds(
    specs_path: Path = DEFAULT_SPECS_PATH, *, karr_native_root: Path = KARR_NATIVE_ROOT
) -> dict[str, Any]:
    """Validate every one of the 50 required RibosomeAssembly event-window
    seeds against its own spec, and cross-check for duplicated (aliased)
    file content across seeds. Never mutates any trace file. Returns a
    plain JSON-serializable report; raises :class:`SeedAuditError` only
    for a malformed spec list (never for individual missing/invalid
    seeds -- those are reported, not raised, so a caller always gets a
    complete picture of exactly which seeds are missing)."""
    rows = json.loads(Path(specs_path).read_text(encoding="utf-8"))
    if len(rows) != REQUIRED_N_SEEDS:
        raise SeedAuditError(
            f"expected exactly {REQUIRED_N_SEEDS} seed specs in {specs_path}, found {len(rows)}"
        )
    seeds_declared = sorted(int(row["seed"]) for row in rows)
    if seeds_declared != list(range(REQUIRED_N_SEEDS)):
        raise SeedAuditError(
            f"expected seeds 0..{REQUIRED_N_SEEDS - 1} exactly once each in {specs_path}, "
            f"got {seeds_declared}"
        )

    per_seed: list[dict[str, Any]] = []
    hash_to_seeds: dict[str, list[int]] = {}
    n_valid = 0
    for row in sorted(rows, key=lambda r: int(r["seed"])):
        spec = _spec_from_dict(row)
        path = event_window_mat_path(
            spec.process, spec.seed, n_ticks=spec.n_ticks, karr_native_root=karr_native_root
        )
        ok, reason = validate_existing_event_window(path, spec)
        file_sha256 = None
        if path.exists():
            file_sha256 = sha256_file(path)
            hash_to_seeds.setdefault(file_sha256, []).append(spec.seed)
        per_seed.append(
            {
                "seed": spec.seed,
                "path": str(path),
                "ok": ok,
                "reason": reason,
                "sha256": file_sha256,
            }
        )
        if ok:
            n_valid += 1

    duplicated_hashes = {h: s for h, s in hash_to_seeds.items() if len(s) > 1}
    # A duplicated hash between two seeds that are BOTH otherwise "ok" is
    # the actual laundering failure mode (one physical file copy-pasted
    # under two seed directories); flag those seeds as invalid too so
    # `all_seeds_valid` cannot be true while an alias exists, even though
    # `validate_existing_event_window` itself has no way to see this
    # (it only ever inspects one file at a time).
    aliased_seeds: set[int] = set()
    for seeds in duplicated_hashes.values():
        aliased_seeds.update(seeds)
    if aliased_seeds:
        for row in per_seed:
            if row["seed"] in aliased_seeds and row["ok"]:
                row["ok"] = False
                row["reason"] = (
                    f"{row['reason'] or 'structurally valid'}; REFUSED: file content is "
                    f"byte-identical to seed(s) "
                    f"{sorted(s for s in duplicated_hashes[row['sha256']] if s != row['seed'])} "
                    "-- aliased/duplicated evidence, not an independent seed."
                )
                n_valid -= 1

    all_seeds_valid = n_valid == REQUIRED_N_SEEDS and not duplicated_hashes

    return {
        "process": "RibosomeAssembly",
        "required_n_seeds": REQUIRED_N_SEEDS,
        "n_seeds_valid": n_valid,
        "n_seeds_total": len(rows),
        "all_seeds_valid": all_seeds_valid,
        "duplicated_hashes": duplicated_hashes,
        "per_seed": per_seed,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", default=str(DEFAULT_SPECS_PATH))
    parser.add_argument("--karr-native-root", default=str(KARR_NATIVE_ROOT))
    parser.add_argument("--out", default=None, help="Optional path to write the full JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        report = audit_ribosome_assembly_n50_seeds(
            Path(args.specs), karr_native_root=Path(args.karr_native_root)
        )
    except SeedAuditError as exc:
        print(f"AUDIT REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {k: v for k, v in report.items() if k != "per_seed"}
    print(json.dumps(summary, indent=2, sort_keys=True))

    if not report["all_seeds_valid"]:
        invalid = [row for row in report["per_seed"] if not row["ok"]]
        print(f"FAIL: {len(invalid)} invalid/missing seed(s) of {REQUIRED_N_SEEDS} required:", file=sys.stderr)
        for row in invalid:
            print(f"  seed={row['seed']:03d}: {row['reason']}", file=sys.stderr)
        return 1

    print(f"OK: all {report['n_seeds_valid']} seeds valid, hash-bound, and non-aliased.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
