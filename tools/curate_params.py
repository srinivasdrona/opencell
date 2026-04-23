"""CLI for biology-curator: orchestrate per-paper parameter extraction.

Usage:
    python tools/curate_params.py \\
        --manifest manifests/thattai2001.yaml \\
        --output-cards data/params/micro_model_thattai2001.yaml \\
        --output-dir data/curation/thattai2001/

Behaviour:
    * For each manifest entry, runs the deterministic extractor.
    * Auto-emits DRAFT cards ONLY for RECOMMEND results.
    * Queues AMBIGUOUS / NOT_FOUND entries to YAML for human review.
    * Refuses to overwrite REVIEWED or APPROVED cards (always).
    * Skips DRAFT cards that already exist unless --force is passed.

Exit codes:
    0  all entries either RECOMMEND or SKIPPED
    1  at least one AMBIGUOUS entry (human review needed)
    2  at least one NOT_FOUND / ALL_REJECTED entry
       (1+2 can both apply; the higher value wins)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from opencell.curation import (  # noqa: E402
    load_manifest,
    run_curation,
    write_outputs,
)


def _print_summary(run, paths: dict[str, Path]) -> None:
    cov = run.coverage
    print("=" * 72)
    print(f"CURATION SUMMARY  model={run.model_slug}  doi={run.doi}")
    print(f"  manifest:  {run.manifest_path}")
    print(f"  started:   {run.started_at}")
    print(f"  finished:  {run.finished_at}")
    print(f"  total:     {cov.get('TOTAL', 0)}")
    for k in ("RECOMMEND", "AMBIGUOUS", "NOT_FOUND", "ALL_REJECTED",
              "SKIPPED_EXISTS", "SKIPPED_LOCKED"):
        n = cov.get(k, 0)
        if n:
            print(f"    {k:<16} {n}")
    print()
    print("Outputs:")
    for name, p in paths.items():
        if p.exists():
            print(f"  {name:<20} {p}")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Biology-curator: per-paper extraction.")
    p.add_argument("--manifest", required=True, help="Path to manifest YAML")
    p.add_argument("--output-cards", required=True,
                   help="Path to cards YAML to write/append DRAFT cards into")
    p.add_argument("--output-dir", required=True,
                   help="Directory for queues, coverage report, provenance")
    p.add_argument("--force", action="store_true",
                   help="Re-extract DRAFT entries already present (REVIEWED/APPROVED always protected)")
    p.add_argument("--no-biomodels", action="store_true",
                   help="Skip BioModels lookup (offline mode)")
    args = p.parse_args(argv)

    manifest = load_manifest(args.manifest)
    cards_path = Path(args.output_cards)
    output_dir = Path(args.output_dir)

    run = run_curation(
        manifest,
        output_cards_path=cards_path,
        force=args.force,
        use_biomodels=not args.no_biomodels,
    )
    paths = write_outputs(run, cards_path=cards_path, output_dir=output_dir)
    _print_summary(run, paths)

    cov = run.coverage
    if cov.get("NOT_FOUND", 0) or cov.get("ALL_REJECTED", 0):
        return 2
    if cov.get("AMBIGUOUS", 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
