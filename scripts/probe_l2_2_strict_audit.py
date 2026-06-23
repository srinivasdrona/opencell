"""L2.2 strict-rubric audit: cross-reference 22 in-scope GREEN claims against
Day-36 L2.1 strict-rubric verdicts and short-circuit/port-mismatch audits.

L2.2 inherits L2.1's per-tick bit-identity at its core, PLUS distributional
comparison across an ensemble (50 seeds × 100 ticks). The design_a runner
(_l2_2_design_a_runner_helpers.py:1396-1413) explicitly feeds trace_hints
for substrates/boundEnzymes/RNAs. This means:

  - For processes with trace_hint short-circuits (Day-35 catalog), the L2.2
    PASS is LAUNDERED — biology is bypassed; OC echoes the hint; "match"
    is tautological.
  - For processes with port-mismatch bugs (Day-36 catalog), biology returns
    trivially empty in isolation. With the hint, the harness papers over
    the empty return.
  - For uninformative-trace processes (Karr ensemble all-zero), the L2.2
    distributional comparison is trivially zero=zero.

The honest L2.2 verdict per process is at most as strong as its L2.1
strict-rubric verdict. This audit codifies that into per-process verdicts.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests" / "vivarium"))

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

# Day-35 short-circuit catalog (severity classes)
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

# Day-36 port-mismatch catalog (Translocation-class)
PORT_MISMATCH = {
    "ProteinTranslocation": "confirmed (Day-36 tick-21 instrumentation)",
    "ProteinProcessingII": "suspected (protein.enzyme_counts read)",
    "ProteinModification": "suspected (protein.unmodified_counts read)",
    "RNAProcessing": "suspected (protein.counts + complex.counts read)",
    "RNAModification": "suspected (protein.counts + complex.counts read)",
    "tRNAAminoacylation": "suspected (protein.counts + complex.counts read)",
}

# Per PROCESS_STATUS_ALL_29.md Table 1, processes claimed L2.2 in-scope GREEN
# (column "L2.2"). Excludes:
#   - 🟢 N/A (DETERMINISTIC) cases: ChromCondensation, ChromSeg, TerminalOrg,
#     HostInteraction, ProteinActivation, TxReg (only stochastic processes are
#     in L2.2's distributional scope per the spec)
#   - SHIM: cell_cycle_coordinator (out of scope)
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
    "ProteinDecay",          # decay_light
    "MacromolecularComplexation",
    "Metabolism",
    "Transcription",
    "Translation",
]


# Per-process L2.2 runner functions that EXPLICITLY call overlay_trace_after_hint
# (per grep audit). The other 15 runners do NOT feed trace_hint, but their
# biology may still depend on port-overlay state in subtler ways.
RUNNER_FEEDS_TRACE_HINT = {
    "Transcription",  # _run_transcription_tick: 3x overlay_trace_after_hint
    "Translation",    # _run_translation_tick: 3x overlay_trace_after_hint
}


def classify_l2_2(process: str) -> tuple[str, str]:
    """Apply strict L2.2 rubric to a single process.

    Returns (verdict, reasoning).
    """
    l21 = L2_1_VERDICTS.get(process, "UNKNOWN")
    in_shortcircuit = process in TRACE_HINT_SHORTCIRCUITS
    in_port_mismatch = process in PORT_MISMATCH
    runner_feeds_hint = process in RUNNER_FEEDS_TRACE_HINT

    # Case 1: L2.2 runner explicitly feeds trace_hint AND biology has
    # short-circuit. This is unambiguous oracle laundering.
    if runner_feeds_hint and in_shortcircuit:
        sc_class = TRACE_HINT_SHORTCIRCUITS[process]
        return (
            "LAUNDERED_VIA_HINT_FEED",
            f"L2.2 runner feeds overlay_trace_after_hint for "
            f"substrates/boundEnzymes/RNAs; biology has {sc_class} short-circuit "
            f"that echoes the hint. PASS is tautological.",
        )

    # Case 2: L2.1 strict shows biology fails (returns empty or wrong output).
    # L2.2 PASS must come from some other mechanism — likely the L2.2 runner's
    # per-process state overlay (which populates more ports than L2.1's harness)
    # accidentally provides the inputs that L2.1's harness left empty.
    if l21 == "FAIL":
        if in_shortcircuit:
            sc_class = TRACE_HINT_SHORTCIRCUITS[process]
            return (
                "SUSPECT_LAUNDERED",
                f"L2.1 strict FAIL (biology fires wrong or empty without hint), "
                f"but L2.2 PASS claimed. Process has trace-hint {sc_class} "
                f"short-circuit. L2.2 runner may be papering over the L2.1 "
                f"failure via additional state overlays. Verification needed.",
            )
        if in_port_mismatch:
            return (
                "SUSPECT_LAUNDERED",
                f"L2.1 strict FAIL, port-mismatch ({PORT_MISMATCH[process]}). "
                f"L2.2 runner's per-process state overlay may populate the "
                f"mismatched ports, masking the failure.",
            )
        return (
            "SUSPECT_LAUNDERED",
            "L2.1 strict FAIL without obvious cause. L2.2 PASS suspect.",
        )

    # Case 3: Port-mismatch on an L2.1 GENUINE process.
    # In L2.1 isolation, biology fires correctly. In L2.2 with the runner's
    # rich state overlay, may also fire correctly OR may be LAUNDERED.
    if in_port_mismatch and l21 == "GENUINE":
        return (
            "SUSPECT_LAUNDERED",
            f"L2.1 GENUINE but port-mismatch ({PORT_MISMATCH[process]}) means "
            f"biology reads ports outside its declared observables. L2.2 runner "
            f"may overlay those ports with values that mask the read-surface gap.",
        )

    # Case 4: L2.1 UNINFORMATIVE — Karr's trace shows no activity.
    if l21 == "UNINFORMATIVE":
        return (
            "UNINFORMATIVE",
            "Karr's L2.1 trace shows zero activity for 100-tick window. "
            "L2.2 ensemble distribution likely also all-zero. PASS is vacuous.",
        )

    if l21 == "COINCIDENTAL":
        return (
            "COINCIDENTAL",
            "L2.1 strict shows biology silent on Karr-active tick. L2.2 "
            "ensemble likely matches Karr by both being near-zero.",
        )

    if l21 == "GENUINE":
        return (
            "PROVISIONAL_GENUINE",
            "L2.1 strict GENUINE, no port-mismatch, no hint feed in L2.2 runner. "
            "L2.2 PASS plausibly genuine; needs no-hint distributional run "
            "to verify.",
        )

    return ("UNKNOWN", f"L2.1 verdict missing for {process}")


def main() -> int:
    print("# L2.2 strict-rubric re-audit\n")
    print(f"Cross-referencing {len(L2_2_IN_SCOPE_GREEN_CLAIMS)} claimed L2.2 in-scope")
    print("GREEN entries against Day-36 L2.1 strict-rubric, trace-hint short-circuit")
    print("catalog (Day-35), and port-mismatch audit (Day-36).\n")

    print(f"{'Process':<32} {'L2.1':>14} {'L2.2 verdict':>22}")
    print("-" * 80)
    rows = []
    for p in L2_2_IN_SCOPE_GREEN_CLAIMS:
        l21 = L2_1_VERDICTS.get(p, "?")
        verdict, reasoning = classify_l2_2(p)
        rows.append((p, l21, verdict, reasoning))
        print(f"{p:<32} {l21:>14} {verdict:>22}")

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

    print(f"\n## Bottom line")
    laundered_hint = sum(1 for _, _, v, _ in rows if v == "LAUNDERED_VIA_HINT_FEED")
    suspect = sum(1 for _, _, v, _ in rows if v == "SUSPECT_LAUNDERED")
    uninformative = sum(1 for _, _, v, _ in rows if v == "UNINFORMATIVE")
    coincidental = sum(1 for _, _, v, _ in rows if v == "COINCIDENTAL")
    provisional = sum(1 for _, _, v, _ in rows if v == "PROVISIONAL_GENUINE")
    fail = sum(1 for _, _, v, _ in rows if v == "FAIL")
    total = len(rows)
    print(f"  Of {total} L2.2 in-scope GREEN claims:")
    print(f"    LAUNDERED_VIA_HINT_FEED: {laundered_hint}  (L2.2 runner explicitly feeds trace_after_hint)")
    print(f"    SUSPECT_LAUNDERED      : {suspect}  (L2.1 strict FAIL/port-mismatch; L2.2 mechanism unclear)")
    print(f"    UNINFORMATIVE          : {uninformative}  (Karr trace is all-zero)")
    print(f"    COINCIDENTAL           : {coincidental}  (biology silent on active ticks)")
    print(f"    PROVISIONAL_GENUINE    : {provisional}  (L2.1 strict GENUINE; needs L2.2-specific verification)")
    print(f"    FAIL                   : {fail}")
    print()
    print(f"  Real upper bound on honest L2.2 PASSes: {provisional} of {total}.")
    print(f"  (The {provisional} PROVISIONAL_GENUINE need verification: re-run the L2.2")
    print(f"   distributional test with disable_trace_hints AND check that OC's biology")
    print(f"   fires non-trivially across the ensemble. The {suspect} SUSPECT_LAUNDERED")
    print(f"   need empirical investigation of how L2.2 PASS is achieved despite L2.1")
    print(f"   strict FAIL — likely the runner's per-process state overlay papers")
    print(f"   over the L2.1 failure.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
