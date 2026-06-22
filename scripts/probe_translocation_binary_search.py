"""Translocation L2.1 vs composition binary search at tick 21.

For Day-36, identify which early-return guard in next_update trips in L2.1
but not in composition. Three candidates (lines from karr_protein_translocation.py):

  Line 338: if not cytoplasmic_counts (empty queue)
  Line 350: if total_copies <= 0 (degenerate cumsum)
  Line 356: if atp_remaining <= 0 or h2o_remaining <= 0 (no substrate budget)

This monkey-patches Translocation's next_update to log which guard trips,
then runs the L2.1 test and the composition pair test back-to-back.
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests" / "vivarium"))

# Monkey-patch Translocation's next_update to log diagnostics at tick 21.
from opencell.vivarium import karr_protein_translocation as kpt  # type: ignore
_original_next_update = kpt.KarrProteinTranslocationProcess.next_update

TICK_TARGET = 21
_call_log = []


def _instrumented_next_update(self, timestep, states):
    """Replicate the early-exit logic to log which guard trips."""
    # Tick-counter heuristic: assume each next_update is one tick.
    self._diag_tick_index = getattr(self, "_diag_tick_index", -1) + 1

    if self._diag_tick_index != TICK_TARGET:
        return _original_next_update(self, timestep, states)

    protein_state = states.get("protein", {})
    pc = protein_state.get("counts", {})
    queue = protein_state.get("unprocessed_counts", pc)
    pe = protein_state.get("enzyme_counts", {})
    loc = protein_state.get("location", {})
    cc = states.get("complex", {}).get("counts", {})
    sa = states.get("substrates_allocated", {}).get(self.name, {})
    top_enz = states.get("enzymes", {})

    pc_nonzero = {k: v for k, v in pc.items() if isinstance(v, (int, float)) and v}
    queue_nonzero = {k: v for k, v in queue.items() if isinstance(v, (int, float)) and v}
    pe_nonzero = {k: v for k, v in pe.items() if isinstance(v, (int, float)) and v}
    cc_nonzero = {k: v for k, v in cc.items() if isinstance(v, (int, float)) and v}
    sa_nonzero = {k: v for k, v in sa.items() if isinstance(v, (int, float)) and v}
    enz_nonzero = {k: v for k, v in top_enz.items() if isinstance(v, (int, float)) and v}

    cytoplasmic_first_pass = sum(
        1 for wid in self.translocatable_wids_in_fixture_order
        if str(loc.get(wid, kpt._CYTOPLASM)) == kpt._CYTOPLASM
        and kpt._read_nonnegative_count(queue, wid) > 0
    )
    cytoplasmic_fallback = sum(
        1 for wid in self.translocatable_wids_in_fixture_order
        if kpt._read_nonnegative_count(queue, wid) > 0
    )

    atp = kpt._read_nonnegative_count(sa, self.atp_wid) if sa else 0
    h2o = kpt._read_nonnegative_count(sa, self.h2o_wid) if sa else 0

    _call_log.append({
        "tick": self._diag_tick_index,
        "queue_nonzero": len(queue_nonzero),
        "queue_detail": queue_nonzero,
        "pc_nonzero": len(pc_nonzero),
        "pe_nonzero": pe_nonzero,
        "complex_nonzero": cc_nonzero,
        "substrates_allocated": sa_nonzero,
        "top_state_enzymes_nonzero_count": len(enz_nonzero),
        "cytoplasmic_first_pass": cytoplasmic_first_pass,
        "cytoplasmic_fallback": cytoplasmic_fallback,
        "atp_remaining": atp,
        "h2o_remaining": h2o,
        "srp_wid_in_top_enzymes": kpt._read_nonnegative_count(top_enz, self.srp_wid),
        "srp_recv_in_top_enzymes": kpt._read_nonnegative_count(top_enz, self.srp_receptor_wid),
    })

    return _original_next_update(self, timestep, states)


kpt.KarrProteinTranslocationProcess.next_update = _instrumented_next_update


def _reset_log(label: str):
    _call_log.clear()
    print(f"\n{'='*78}\n=== {label}\n{'='*78}")


def _print_log(label: str):
    if not _call_log:
        print(f"  [no tick-21 invocation in {label}]")
        return
    for rec in _call_log:
        print(f"  tick={rec['tick']}")
        print(f"  queue (unprocessed_counts) nonzero: {rec['queue_nonzero']} : {rec['queue_detail']}")
        print(f"  cytoplasmic count (first pass with location filter): {rec['cytoplasmic_first_pass']}")
        print(f"  cytoplasmic count (fallback ignoring location): {rec['cytoplasmic_fallback']}")
        print(f"  substrates_allocated[Translocation]: {rec['substrates_allocated']}")
        print(f"  atp_remaining={rec['atp_remaining']}, h2o_remaining={rec['h2o_remaining']}")
        print(f"  protein.enzyme_counts nonzero: {rec['pe_nonzero']}")
        print(f"  protein.counts nonzero: {rec['pc_nonzero']}")
        print(f"  complex.counts nonzero: {rec['complex_nonzero']}")
        print(f"  top-level state.enzymes nonzero count: {rec['top_state_enzymes_nonzero_count']}")
        print(f"  srp_wid in top.enzymes: {rec['srp_wid_in_top_enzymes']}")
        print(f"  srp_recv in top.enzymes: {rec['srp_recv_in_top_enzymes']}")

        # Trip analysis:
        if rec['cytoplasmic_first_pass'] == 0 and rec['cytoplasmic_fallback'] == 0:
            print(f"  >> WOULD EXIT at line 338 (empty cytoplasmic queue)")
        elif rec['atp_remaining'] <= 0 or rec['h2o_remaining'] <= 0:
            print(f"  >> WOULD EXIT at line 356 (atp/h2o <= 0)")
        else:
            print(f"  >> would proceed to enzyme/sampler loop")


def main() -> int:
    # Mode 1: L2.1 isolation
    _reset_log("MODE A: L2.1 isolation (test_karr_protein_translocation_l2_replay)")
    import pytest
    pytest.main([
        str(_REPO / "tests" / "vivarium" / "test_karr_protein_translocation_l2_replay.py"),
        "-x", "--tb=no", "-q", "--no-header",
    ])
    _print_log("L2.1")

    # Mode 2: Composition (ProteinFolding+ProteinTranslocation)
    _reset_log("MODE B: composition L2.5 (ProteinFolding+ProteinTranslocation)")
    pytest.main([
        str(_REPO / "tests" / "vivarium" / "test_l25_stochastic_stochastic_clean_pairs.py"),
        "-k", "ProteinFolding+ProteinTranslocation",
        "--tb=no", "-q", "--no-header",
    ])
    _print_log("composition")

    return 0


if __name__ == "__main__":
    sys.exit(main())
