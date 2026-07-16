"""L2.2 strict-rubric test — pins honest baseline for the 22 L2.2 in-scope GREEN claims.

Sibling test to test_l2_1_strict_rubric.py. Where the L2.1 strict rubric ran
the actual per-tick biology to measure fire rate, the L2.2 strict rubric is
a STATIC cross-reference audit because:
  - The L2.2 design_a runner is not invoked from pytest CI today (the per-process
    PASS claims in PROCESS_STATUS_ALL_29.md come from offline runs of the runner)
  - Re-running each L2.2 process ensemble (50 seeds x 100 ticks) is computationally
    expensive
  - The L2.1 strict rubric already pins the per-tick verdict; L2.2 cannot be
    stronger than its underlying L2.1 verdict

This test pins each L2.2 in-scope GREEN claim to its Day-37 strict-rubric
verdict. Verdicts can be:
  - LAUNDERED_VIA_HINT_FEED: L2.2 runner explicitly calls overlay_trace_after_hint
    for this process (Transcription, Translation per current code).
  - SUSPECT_LAUNDERED: L2.1 strict FAIL or port-mismatch suspect, but L2.2
    claims PASS. Mechanism by which L2.2 passes is unclear; likely the runner's
    per-process state overlay accidentally populates the read-surface gap.
  - UNINFORMATIVE: Karr's L2.1 trace shows no activity for the 100-tick window;
    distributional comparison reduces to zero=zero.
  - PROVISIONAL_GENUINE: L2.1 strict GENUINE AND no trace-hint short-circuit AND
    no port-mismatch AND no explicit hint feed. L2.2 PASS plausibly genuine but
    still needs distributional verification with disable_trace_hints=True.

If any L2.2 verdict moves from PROVISIONAL_GENUINE -> VERIFIED_GENUINE
(after a no-hint distributional re-run), update the pin AND celebrate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))


# Day-37 (2026-06-23) PHASE B baseline — empirically verified via design_a runner
# Source: scripts/probe_l2_2_strict_audit.py + runner output files in tmp/l2_2_audit/
# Runner ran with 50 seeds x 10 ticks per process; runner-vs-catalog string-drift bug fixed.
EXPECTED_L2_2_VERDICTS = {
    # 13 VERIFIED_GENUINE (Day-37 Phase B baseline + Day-37 PM updates:
    # +ProteinTranslocation after shape fix, +Transcription/+Translation after
    # explicit hint-feed removal — biology actually matches Karr distributionally
    # without the hint, so LAUNDERED classification was overly conservative)
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
    # 1 VERIFIED_FAIL — real biology divergence (claim was wrong)
    "Metabolism": "VERIFIED_FAIL",
    # 2 design-A UNVALIDATABLE (runner correctly refuses EVENT_CLASS to avoid
    # fake zero-W1 passes). These verdicts pin the DESIGN-A audit output ONLY;
    # they are NOT the whole validation picture — see the two-axis note below.
    #   - RibosomeAssembly: COVERED via the event-window replay track —
    #     test_karr_ribosome_assembly_l2_replay.py::test_karr_ribosome_assembly_l2_event_replay
    #     PASSES bit-identically on the tick_offset=200 event window (253
    #     events/cycle). Catalog already marks it "L2.2 GREEN". NOT an open gap.
    #   - Cytokinesis: GENUINELY unvalidatable in isolation — evolveState returns
    #     until chromosome.segregated (end-of-cycle), so no isolated oracle window
    #     can exist. Its division event is a full-cycle phenotype → L5 (2026-07-15).
    "Cytokinesis": "UNVALIDATABLE_EVENT_CLASS",
    "RibosomeAssembly": "UNVALIDATABLE_EVENT_CLASS",
    # 2 design-A NOT_WIRED (EVENT_CLASS, out of design-A scope). Split by reality:
    #   - FtsZPolymerization: COVERED via the bit-identity replay track —
    #     test_karr_ftsz_polymerization_l2_replay.py PASSES on an ACTIVE window
    #     (substrates 60/100, enzymes 100/100 ticks). ODE-deterministic port, so
    #     bit-identity is the right bar. NOT an open gap; "needs distributional"
    #     catalog note is stale (pre-ODE-port).
    #   - DNADamage: GENUINELY open — standard trace is a sampling-artifact no-op
    #     (~8 spontaneous events/cycle per DNADamage.m:94, ~1/4000 ticks). Fix =
    #     full-cycle MATLAB scan to locate firing ticks → event-window replay
    #     harness (mirrors RibosomeAssembly). Pending 2026-07-15.
    "Replication": "VERIFIED_GENUINE",
    "ReplicationInitiation": "VERIFIED_GENUINE",
    "DNASupercoiling": "VERIFIED_GENUINE",
    "DNARepair": "VERIFIED_GENUINE",
    "DNADamage": "NOT_WIRED",
    "FtsZPolymerization": "NOT_WIRED",
}

assert len(EXPECTED_L2_2_VERDICTS) == 22, (
    f"Expected 22 L2.2 in-scope GREEN claims, found {len(EXPECTED_L2_2_VERDICTS)}"
)


# Imported from the audit script for the live classification
import importlib.util

_audit_path = _REPO / "scripts" / "probe_l2_2_strict_audit.py"
_spec = importlib.util.spec_from_file_location("_l2_2_audit_module", _audit_path)
_audit = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_audit)


@pytest.mark.parametrize("process_name", sorted(EXPECTED_L2_2_VERDICTS.keys()))
def test_l2_2_strict_rubric_matches_expected(process_name: str) -> None:
    """Pin per-process L2.2 strict-rubric verdict to its Day-37 baseline.

    The strict rubric is static today — derived from L2.1 verdict + trace-hint
    catalog + port-mismatch catalog + explicit-hint-feed catalog. To upgrade
    a process from PROVISIONAL_GENUINE to VERIFIED_GENUINE, run the L2.2
    distributional test with disable_trace_hints=True equivalent AND confirm
    OC's biology fires non-trivially across the ensemble; then update the
    expected pin AND add the empirical-verification commit reference here.

    Day-37 baseline scoreboard:
      LAUNDERED_VIA_HINT_FEED: 2  (Transcription, Translation - runner-injected)
      SUSPECT_LAUNDERED      : 12 (L2.1 FAIL or port-mismatch; mechanism unclear)
      UNINFORMATIVE          : 4  (Karr trace all-zero; vacuous)
      PROVISIONAL_GENUINE    : 4  (DNARepair, ProcI, Folding, MacromolComplex)

    Real upper bound on honest L2.2 PASSes: 4 of 22.
    """
    expected = EXPECTED_L2_2_VERDICTS[process_name]
    actual, reasoning = _audit.classify_l2_2(process_name)

    if actual != expected:
        pytest.fail(
            f"L2.2 strict-rubric verdict drift for {process_name}: "
            f"expected={expected}, actual={actual}.\n"
            f"Reasoning: {reasoning}\n"
            f"If this is intentional (e.g., a trace-hint short-circuit was "
            f"removed, or a port-mismatch was fixed), update the expected "
            f"pin in this file AND the source-of-truth audit catalog in "
            f"scripts/probe_l2_2_strict_audit.py."
        )
