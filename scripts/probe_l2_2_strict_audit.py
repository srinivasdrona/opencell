"""L2.2 strict-rubric audit: cross-reference claims against empirical runs.

Day-37 (2026-06-23) Phase B update: empirical results from running the L2.2
design_a runner against each runner-supported process (50 seeds × 10 ticks)
revealed:

  - 10 processes VERIFIED_GENUINE (pass distributional comparison; exact match
    treated as legitimate convergence per `closed_form_dominant` catalog flag,
    after Day-37 fix to recognize `confirmed_biology_validated` value)
  - 1 process VERIFIED_FAIL (Metabolism, W1=171.39 on substrates — real divergence)
  - 1 process CRASH (ProteinTranslocation, monomers projection shape mismatch)
  - 2 processes UNVALIDATABLE_EVENT_CLASS (Cytokinesis, RibosomeAssembly —
    runner refuses; needs L2.event harness)
  - 2 processes LAUNDERED_VIA_HINT_FEED (Transcription, Translation — runner
    explicitly feeds trace_after_hint)
  - 6 processes NOT_WIRED (chromosome-port processes — never added to runner)

This module retains the static classification logic for use by the
test_l2_2_strict_rubric.py pin, but the actual ground-truth verdicts now come
from empirical_results below. The static logic is used as a fallback / drift
detector for processes that get re-added or removed from the runner.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests" / "vivarium"))

# Day-37 empirical verdicts from running tests/vivarium/l2_2_design_a_runner.py
# at 50 seeds x 10 ticks, post runner string-drift fix (commit Day-37).
EMPIRICAL_VERDICTS = {
    # 13 VERIFIED_GENUINE (Day-37 PM cumulative)
    "MacromolecularComplexation": "VERIFIED_GENUINE",
    "ProteinFolding": "VERIFIED_GENUINE",
    "ProteinProcessingI": "VERIFIED_GENUINE",
    "ProteinProcessingII": "VERIFIED_GENUINE",
    "tRNAAminoacylation": "VERIFIED_GENUINE",
    "ProteinModification": "VERIFIED_GENUINE",
    "ProteinDecay": "VERIFIED_GENUINE",
    "RNADecay": "VERIFIED_GENUINE",
    "RNAModification": "VERIFIED_GENUINE",
    "RNAProcessing": "VERIFIED_GENUINE",
    "ProteinTranslocation": "VERIFIED_GENUINE",
    "Transcription": "VERIFIED_GENUINE",
    "Translation": "VERIFIED_GENUINE",
    # 1 VERIFIED_FAIL — real biology divergence
    "Metabolism": "VERIFIED_FAIL",
    # 2 UNVALIDATABLE — runner refuses
    "Cytokinesis": "UNVALIDATABLE_EVENT_CLASS",
    "RibosomeAssembly": "UNVALIDATABLE_EVENT_CLASS",
    # 2 NOT_WIRED — 4 of 4 in-scope chromosome processes wired on Day-39
    # (DNADamage + FtsZ remain NOT_WIRED because they are EVENT_CLASS, out of design-A scope)
    "Replication": "VERIFIED_GENUINE",
    "ReplicationInitiation": "VERIFIED_GENUINE",
    "DNASupercoiling": "VERIFIED_GENUINE",
    "DNARepair": "VERIFIED_GENUINE",
    "DNADamage": "NOT_WIRED",
    "FtsZPolymerization": "NOT_WIRED",
}


# Day-36 L2.1 strict-rubric verdicts (pinned baseline)
L2_1_VERDICTS = {
    # GENUINE (9)
    "DNARepair": "GENUINE",
    "MacromolecularComplexation": "GENUINE",
    "ProteinActivation": "GENUINE",
    "ProteinFolding": "GENUINE",
    "ProteinProcessingI": "GENUINE",
    "ProteinProcessingII": "GENUINE",
    "RNAProcessing": "GENUINE",
    "Translation": "GENUINE",
    "tRNAAminoacylation": "GENUINE",
    # UNINFORMATIVE (6)
    "ChromosomeSegregation": "UNINFORMATIVE",
    "Cytokinesis": "UNINFORMATIVE",
    "DNADamage": "UNINFORMATIVE",
    "HostInteraction": "UNINFORMATIVE",
    "RNAModification": "UNINFORMATIVE",
    "RibosomeAssembly": "UNINFORMATIVE",
    # COINCIDENTAL (1)
    "TranscriptionalRegulation": "COINCIDENTAL",
    # FAIL strict (11)
    "ChromosomeCondensation": "FAIL",
    "DNASupercoiling": "FAIL",
    "FtsZPolymerization": "FAIL",
    "Metabolism": "FAIL",
    "ProteinDecay": "FAIL",
    "ProteinModification": "FAIL",
    "ProteinTranslocation": "FAIL",
    "RNADecay": "FAIL",
    "Replication": "FAIL",
    "ReplicationInitiation": "FAIL",
    "Transcription": "FAIL",
    # ERROR (1)
    "TerminalOrganelleAssembly": "ERROR",
}

# Day-35 short-circuit catalog (severity classes) — kept for static fallback
TRACE_HINT_SHORTCIRCUITS = {
    "Replication": "FULL_BYPASS",
    "ReplicationInitiation": "FULL_BYPASS",
    "Metabolism": "CHEMISTRY_BYPASS",
    "RNADecay": "CHEMISTRY_BYPASS",
    "ProteinDecay": "CHEMISTRY_BYPASS",
    "Transcription": "CHEMISTRY_BYPASS",
    "TerminalOrganelleAssembly": "CHEMISTRY_BYPASS",
    "FtsZPolymerization": "CHEMISTRY_BYPASS",
    "ChromosomeCondensation": "GATED_BIOLOGY",
    "ProteinModification": "GATED_BIOLOGY",
    "DNASupercoiling": "CHANNEL_OVERLAY",
    "TranscriptionalRegulation": "CHANNEL_OVERLAY",
    "Translation": "REPLAY_GUARD",
}

# Day-36 port-mismatch catalog
PORT_MISMATCH = {
    "ProteinTranslocation": "confirmed (Day-36 tick-21 instrumentation)",
    "ProteinProcessingII": "suspected (protein.enzyme_counts read)",
    "ProteinModification": "suspected (protein.unmodified_counts read)",
    "RNAProcessing": "suspected (protein.counts + complex.counts read)",
    "RNAModification": "suspected (protein.counts + complex.counts read)",
    "tRNAAminoacylation": "suspected (protein.counts + complex.counts read)",
}

# 22 L2.2 in-scope GREEN claims (per PROCESS_STATUS_ALL_29 Table 1)
L2_2_IN_SCOPE_GREEN_CLAIMS = [
    "Replication",
    "ReplicationInitiation",
    "DNASupercoiling",
    "DNADamage",
    "DNARepair",
    "FtsZPolymerization",
    "Cytokinesis",
    "RNADecay",
    "RNAProcessing",
    "RNAModification",
    "tRNAAminoacylation",
    "RibosomeAssembly",
    "ProteinProcessingI",
    "ProteinProcessingII",
    "ProteinFolding",
    "ProteinModification",
    "ProteinTranslocation",
    "ProteinDecay",
    "MacromolecularComplexation",
    "Metabolism",
    "Transcription",
    "Translation",
]


def classify_l2_2(process: str) -> tuple[str, str]:
    """Empirical-first classification of an L2.2 in-scope GREEN claim.

    If the process has an empirical verdict from Day-37 phase B runs, use it.
    Otherwise, fall back to static classification (drift detection).
    """
    empirical = EMPIRICAL_VERDICTS.get(process)
    if empirical is not None:
        # Map empirical verdicts to reasoning strings
        if empirical == "VERIFIED_GENUINE":
            return (
                empirical,
                "Empirically verified PASS via L2.2 design_a runner (50 seeds x 10 ticks, "
                "Day-37 phase B). W1 either zero (legitimate convergence per "
                "closed_form_dominant) or within SEED_NOISE threshold.",
            )
        if empirical == "VERIFIED_FAIL":
            return (
                empirical,
                "Empirically FAIL via L2.2 design_a runner. Primary channel W1 "
                "exceeds threshold. L2.2 PASS claim in PROCESS_STATUS_ALL_29 is "
                "either stale or was always wrong.",
            )
        if empirical == "CRASH_HARNESS_BUG":
            return (
                empirical,
                "L2.2 design_a runner crashes on this process due to a shape "
                "mismatch. Cannot validate until harness bug is fixed.",
            )
        if empirical == "UNVALIDATABLE_EVENT_CLASS":
            return (
                empirical,
                "Per catalog, this process has harness_type=event_class and is "
                "EVENT_CLASS bucket. Runner refuses to validate via per-tick "
                "distributional comparison because sparse events don't fire in "
                "100-tick window. Needs L2.event harness (not yet built).",
            )
        if empirical == "LAUNDERED_VIA_HINT_FEED":
            return (
                empirical,
                "Runner explicitly feeds overlay_trace_after_hint for this "
                "process's substrates/boundEnzymes/RNAs channels. Match is "
                "tautological. Need to remove hint feed and re-run to verify "
                "honest distributional match.",
            )
        if empirical == "NOT_WIRED":
            return (
                empirical,
                "Chromosome-port process never wired into L2.2 design_a runner. "
                "L2.2 PASS claim in PROCESS_STATUS_ALL_29 has no automated test "
                "backing it. Custom validation path (chromosome port doc) was "
                "designed but never integrated into CI.",
            )

    # Fallback: static classification
    l21 = L2_1_VERDICTS.get(process, "UNKNOWN")
    if process in TRACE_HINT_SHORTCIRCUITS or process in PORT_MISMATCH:
        return ("SUSPECT_LAUNDERED_FALLBACK", "Static fallback; no empirical verdict")
    if l21 == "UNINFORMATIVE":
        return ("UNINFORMATIVE", "Static fallback")
    return ("UNKNOWN", "No empirical verdict and no fallback rule matches")


def main() -> int:
    print("# L2.2 strict-rubric audit (Day-37 phase B: empirical)\n")
    print(f"{'Process':<32} {'L2.1':>14} {'L2.2 verdict':>26}")
    print("-" * 86)
    rows = []
    for p in L2_2_IN_SCOPE_GREEN_CLAIMS:
        l21 = L2_1_VERDICTS.get(p, "?")
        verdict, reasoning = classify_l2_2(p)
        rows.append((p, l21, verdict, reasoning))
        print(f"{p:<32} {l21:>14} {verdict:>26}")

    print("\n## Summary buckets")
    counts: dict[str, int] = {}
    for _, _, v, _ in rows:
        counts[v] = counts.get(v, 0) + 1
    for k in sorted(counts.keys()):
        print(f"  {k}: {counts[k]}")

    print("\n## Detail per verdict")
    for verdict in sorted(set(r[2] for r in rows)):
        members = [r for r in rows if r[2] == verdict]
        print(f"\n### {verdict} ({len(members)})")
        for p, l21, v, reason in members:
            print(f"  - {p} (L2.1={l21})")
            print(f"    {reason}")

    verified_pass = sum(1 for _, _, v, _ in rows if v == "VERIFIED_GENUINE")
    verified_fail = sum(1 for _, _, v, _ in rows if v == "VERIFIED_FAIL")
    crash = sum(1 for _, _, v, _ in rows if v == "CRASH_HARNESS_BUG")
    unvalidatable = sum(1 for _, _, v, _ in rows if v == "UNVALIDATABLE_EVENT_CLASS")
    laundered = sum(1 for _, _, v, _ in rows if v == "LAUNDERED_VIA_HINT_FEED")
    not_wired = sum(1 for _, _, v, _ in rows if v == "NOT_WIRED")
    print(f"\n## Final tally")
    print(f"  Of {len(rows)} L2.2 in-scope GREEN claims:")
    print(f"    VERIFIED_GENUINE          : {verified_pass}  <-- the actual, validated count")
    print(f"    VERIFIED_FAIL             : {verified_fail}  (claim was wrong)")
    print(f"    CRASH_HARNESS_BUG         : {crash}")
    print(f"    UNVALIDATABLE_EVENT_CLASS : {unvalidatable}")
    print(f"    LAUNDERED_VIA_HINT_FEED   : {laundered}")
    print(f"    NOT_WIRED                 : {not_wired}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
