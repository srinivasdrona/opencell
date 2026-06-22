"""ProcII straggler probe: does ProteinProcessingII have its own port-mismatch bug?

ProcI+ProcII and Folding+ProcII both fail in the SS clean-vs-clean sweep.
ProcI+RNAProc and Folding+ProcI PASS. Suggests ProcII may have a Translocation-class
port-contamination bug.

Test: run ProcII against every other clean process and look at the pass/fail pattern.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# All clean SS partners for ProcII from the L2.5 audit
PROCII_PARTNERS = [
    "ProteinFolding",
    "ProteinProcessingI",
    "ProteinTranslocation",
    "RibosomeAssembly",
    "RNAModification",
    "RNAProcessing",
    "tRNAAminoacylation",
    "Cytokinesis",
    "DNADamage",
    "DNARepair",
]


def main() -> int:
    print(f"# ProcII straggler probe")
    print(f"# Running ProcessingII vs each clean partner in SS L2.5 honest mode\n")

    results = []
    for partner in PROCII_PARTNERS:
        test_id = f"ProteinProcessingII+{partner}"
        proc = subprocess.run(
            ["pytest",
             "tests/vivarium/test_l25_stochastic_stochastic_clean_pairs.py",
             "-k", f"ProteinProcessingII and {partner}",
             "--tb=no", "-q", "--no-header"],
            capture_output=True, text=True, timeout=120,
            cwd=str(_REPO),
        )
        tail = proc.stdout.strip().split("\n")[-1]
        if "passed" in tail.lower():
            verdict = "PASS"
        elif "failed" in tail.lower():
            verdict = "FAIL"
        elif "skipped" in tail.lower() and "no tests" not in tail.lower():
            verdict = "SKIP"
        elif "no tests ran" in tail.lower() or "deselected" in tail.lower():
            verdict = "NO_PAIR"
        else:
            verdict = "?"
        results.append((partner, verdict, tail))
        print(f"  ProcII+{partner:<30} {verdict}   ({tail})")

    print("\n## Summary")
    counts = {}
    for _, v, _ in results:
        counts[v] = counts.get(v, 0) + 1
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")

    fails = [partner for partner, v, _ in results if v == "FAIL"]
    passes = [partner for partner, v, _ in results if v == "PASS"]
    print(f"\nFAIL partners: {fails}")
    print(f"PASS partners: {passes}")

    if len(fails) >= len(passes) + 2:
        print("\nINTERPRETATION: ProcII looks broken on the SS-clean side (Translocation-class bug)")
    elif len(passes) > len(fails):
        print("\nINTERPRETATION: ProcII is mostly clean; the failures are partner-specific")
    return 0


if __name__ == "__main__":
    sys.exit(main())
