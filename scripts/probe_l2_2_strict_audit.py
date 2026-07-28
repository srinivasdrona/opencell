"""L2.2 strict-rubric audit: human-readable report over the mechanically
generated evidence index.

This script used to contain a hand-written `EMPIRICAL_VERDICTS` dict (and a
`classify_l2_2` fallback over `L2_1_VERDICTS` / `TRACE_HINT_SHORTCIRCUITS` /
`PORT_MISMATCH`) -- i.e. it *was* the ground truth, asserted by hand, with no
connection to any actual runner output. That is exactly the circularity this
generator/audit rewrite exists to remove: see
docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md.

The only thing this script does now is call
``scripts.l22_evidence.generator.build_evidence_index()`` -- which mechanically
re-derives every verdict from raw per-process evidence via
``scripts.l22_evidence.verdict`` (stored verdict strings are never trusted) --
and print the same kind of human-readable table/tally the old hand-classified
version printed, sourced honestly instead of asserted.

Usage:
    bin\\oc-py scripts/probe_l2_2_strict_audit.py            # human report, live regeneration
    bin\\oc-py scripts/probe_l2_2_strict_audit.py --require-all-pass  # nonzero unless all GREEN
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.l22_evidence import generator as gen  # noqa: E402


def _print_report(payload: dict[str, Any]) -> None:
    rows = payload["rows"]
    print("# L2.2 evidence-index audit (mechanically re-derived; stored verdicts are not authoritative)\n")
    print(f"catalog: {payload['catalog_path']} (sha256={payload['catalog_sha256'][:12]}..)")
    print(f"evidence_root: {payload['evidence_root']}")
    print(f"schema_version: {payload['schema_version']}\n")

    print(f"{'Process':<32} {'mechanical_verdict':>26} {'green':>7}")
    print("-" * 68)
    for row in sorted(rows, key=lambda r: r["process"]):
        print(f"{row['process']:<32} {row['mechanical_verdict']:>26} {str(row['green']):>7}")

    print("\n## Summary buckets")
    for status, count in sorted(payload["tally"].items()):
        print(f"  {status}: {count}")

    print("\n## Detail per verdict")
    for verdict in sorted({row["mechanical_verdict"] for row in rows}):
        members = [row for row in rows if row["mechanical_verdict"] == verdict]
        print(f"\n### {verdict} ({len(members)})")
        for row in sorted(members, key=lambda r: r["process"]):
            print(f"  - {row['process']} (bucket={row['bucket']}, harness_type={row['harness_type']})")
            for reason in row["reasons"]:
                print(f"      {reason}")

    green = sum(1 for row in rows if row["green"])
    print("\n## Final tally")
    print(f"  Of {len(rows)} L2.2 in-scope processes:")
    print(f"    GREEN (mechanically verified): {green}")
    print(f"    non-green                    : {len(rows) - green}")
    print(f"\n  aggregate_verdict: {payload['aggregate_verdict']}")
    print(f"  content_hash: {payload['content_hash']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-all-pass",
        action="store_true",
        help="Acceptance gate: exit nonzero unless every in-scope process is GREEN. "
        "Expected to fail until process closure; not yet wired into CI.",
    )
    args = parser.parse_args(argv)

    payload = gen.build_evidence_index()
    _print_report(payload)

    if args.require_all_pass and payload["aggregate_verdict"] != "GREEN":
        print("\n--require-all-pass: aggregate verdict is not GREEN; acceptance gate not yet activated in CI")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
