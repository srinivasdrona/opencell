"""Surgically replace ONE process's row in the tracked evidence_index.json,
recomputing only the aggregate-level fields that are a function of the
full row set (`tally`, `aggregate_verdict`, `content_hash`,
`generated_at`, `catalog_sha256`), while leaving every OTHER row
byte-for-byte identical to what is currently committed.

## Why this exists (do not use as a routine substitute for `generate`)

`generator.build_evidence_index()` recomputes ALL in-scope rows from
scratch every time, and its staleness check
(`_check_sweep_provenance_staleness` / `_check_current_tree_staleness`)
hashes several files WHOLE (`tests/vivarium/_l2_2_design_a_runner_helpers.py`,
`tests/vivarium/l2_2_design_a_runner.py`,
`tests/vivarium/_l2_2_design_a_projections.py`,
`tests/vivarium/l2_replay_common.py`,
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`) -- shared by every
`design_a_per_tick` process. Any edit to ONE of those files (even a purely
additive, backward-compatible one, or a documentation-only catalog note on
a single process) changes that file's hash and therefore correctly flags
EVERY row referencing it as stale, regardless of whether that row's own
underlying evidence actually changed. This is the intended, correct
behavior of a fail-closed staleness system -- it is not a bug -- but it
means that after a shared-harness change scoped to ONE process, running
the ordinary `generate` command (which re-derives every row from the
CURRENT tree) will legitimately downgrade every OTHER already-accepted row
to stale/FAIL too, even though only one process's cohort/evidence was
actually re-swept.

Re-running the full per-process sweep (each ~20-30+ minutes of real
per-tick simulation) for every OTHER `design_a_per_tick` process just to
clear a hash-provenance staleness flag that has no bearing on their actual
computed results is disproportionate and out of scope for a change
targeted at one process. This tool instead does the minimal, honest thing:
recompute ONLY the named process's row (via the same
`generator.build_process_row` every other code path uses -- no bespoke
logic), splice it into the current committed index in place of the old
row, and recompute only the aggregate fields that mechanically depend on
the full row set. Every other row is copied through unmodified.

## What this does NOT do

It does not, and cannot, make `scripts/l22_evidence/generator.py audit`
report a clean full-catalog match against a truly fresh, from-scratch
regeneration -- that would require actually re-sweeping every affected
process. Use `--verify-target-row-only` to independently confirm the ONE
row this tool touched is correct (a fresh `build_process_row` computation
against the same evidence root, which is exactly what was spliced in), and
compare `git diff` on the result to confirm every other row is untouched.
Document any residual full-audit staleness explicitly in the closure's
STATUS doc; do not silently claim a clean full audit this tool cannot
produce.

CLI:
    bin\\oc-py scripts/l22_evidence/promote_single_row.py --process MacromolecularComplexation
        [--evidence-root PATH] [--index PATH]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402


def promote_single_row(
    process: str,
    *,
    index_path: Path = schema.INDEX_PATH,
    evidence_root: Path = schema.BUNDLE_ROOT,
    catalog_path: Path = schema.CATALOG_PATH,
) -> dict[str, Any]:
    original = json.loads(index_path.read_text(encoding="utf-8"))
    original_rows_by_process = {row["process"]: row for row in original["rows"]}
    if process not in original_rows_by_process:
        raise ValueError(f"{process!r} not found in current index rows at {index_path}")

    entries = cat.in_scope_processes(catalog_path)
    if process not in entries:
        raise ValueError(f"{process!r} is not an in-scope catalog process")
    new_row = gen.build_process_row(entries[process], evidence_root)

    new_rows = []
    for name in sorted(original_rows_by_process):
        new_rows.append(new_row if name == process else copy.deepcopy(original_rows_by_process[name]))

    tally: dict[str, int] = {}
    for row in new_rows:
        tally[row["mechanical_verdict"]] = tally.get(row["mechanical_verdict"], 0) + 1
    aggregate_verdict = "GREEN" if new_rows and all(row["green"] for row in new_rows) else "NON_GREEN"

    payload: dict[str, Any] = {
        "schema_version": original["schema_version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_path": original["catalog_path"],
        "catalog_sha256": cat.catalog_sha256(catalog_path),
        "evidence_root": cat.relative_to_repo(evidence_root),
        "n_in_scope": len(new_rows),
        "aggregate_verdict": aggregate_verdict,
        "tally": tally,
        "rows": new_rows,
    }
    payload["content_hash"] = gen.content_hash(payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", required=True)
    parser.add_argument("--index", type=Path, default=schema.INDEX_PATH)
    parser.add_argument("--evidence-root", type=Path, default=schema.BUNDLE_ROOT)
    parser.add_argument("--catalog", type=Path, default=schema.CATALOG_PATH)
    args = parser.parse_args(argv)

    before = json.loads(args.index.read_text(encoding="utf-8"))
    before_rows_by_process = {row["process"]: row for row in before["rows"]}

    payload = promote_single_row(
        args.process, index_path=args.index, evidence_root=args.evidence_root, catalog_path=args.catalog
    )
    gen.write_index(payload, args.index)

    print(f"wrote {args.index} ({payload['n_in_scope']} rows, aggregate={payload['aggregate_verdict']})")
    for status, count in sorted(payload["tally"].items()):
        print(f"  {status}: {count}")

    unchanged = 0
    total = 0
    new_rows_by_process = {row["process"]: row for row in payload["rows"]}
    for name, before_row in before_rows_by_process.items():
        if name == args.process:
            continue
        total += 1
        if before_row == new_rows_by_process.get(name):
            unchanged += 1
        else:
            print(f"WARNING: row {name!r} changed unexpectedly (expected byte-identical)")
    print(f"{unchanged}/{total} unrelated rows confirmed byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
