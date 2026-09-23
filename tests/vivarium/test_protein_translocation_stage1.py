from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess

STAGE1_TRANSLOCATING_WIDS = ("MG_191_MONOMER", "MG_192_MONOMER", "MG_318_MONOMER")
COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")


def _base_stage1_state(proc: KarrProteinTranslocationProcess) -> dict[str, Any]:
    state = {
        "substrates": {wid: 1000.0 for wid in proc.substrate_wids},
        "protein": {
            "counts": {wid: 10.0 for wid in proc.protein_count_wids},
            "unprocessed_counts": {wid: 0.0 for wid in proc.translocatable_wids},
            "location": {wid: "cytoplasm" for wid in proc.translocatable_wids},
            "compartment_counts": {
                "nascent": {},
                "processed_i": {},
            },
        },
        "complex": {"counts": {wid: 10.0 for wid in proc.complex_count_wids}},
        "requests": {proc.name: {wid: 0.0 for wid in proc.request_wids}},
        "substrates_allocated": {
            proc.name: {wid: 1000.0 for wid in proc.vector_wids}
        },
    }
    # Enable core translocase enzymes
    for enzyme_wid in (
        proc.srp_wid,
        proc.srp_receptor_wid,
        proc.translocase_atpase_wid,
        proc.translocase_pore_wid,
    ):
        if enzyme_wid in proc.complex_count_wids:
            state["complex"]["counts"][enzyme_wid] = 10.0
        else:
            state["protein"]["counts"][enzyme_wid] = 10.0
    return state


def test_stage1_no_terminal_organelle_exclusions() -> None:
    """Design C16 / Finding PT-TO-EXCLUSION: MG_191 and MG_192 must NOT be excluded from

    translocation. Both have KB compartment tm which remaps to m, making them translocating.
    """
    import opencell.vivarium.karr_protein_translocation as pt_mod

    # If _TERMINAL_ORGANELLE_EXCLUSIONS survives, it must not exclude MG_191 or MG_192
    if hasattr(pt_mod, "_TERMINAL_ORGANELLE_EXCLUSIONS"):
        exclusions = pt_mod._TERMINAL_ORGANELLE_EXCLUSIONS
        for wid in ("MG_191_MONOMER", "MG_192_MONOMER"):
            assert wid not in exclusions, (
                f"PT-TO-EXCLUSION violation: {wid} must not be in _TERMINAL_ORGANELLE_EXCLUSIONS"
            )

    proc = KarrProteinTranslocationProcess({})
    # Check that MG_191, MG_192, and MG_318 are recognized as translocating monomers
    translocating = set(getattr(proc, "translocating_monomer_wids", []))
    if translocating:
        for wid in STAGE1_TRANSLOCATING_WIDS:
            assert wid in translocating, f"{wid} missing from proc.translocating_monomer_wids"


def test_stage1_translocation_form_discipline_processed_i_only() -> None:
    """Design C17 / Finding PT-QUEUE-CONFLATION: Translocation reads and writes ONLY

    the processed_i form; nascent is untouched.
    """
    proc = KarrProteinTranslocationProcess({})
    state = _base_stage1_state(proc)

    # Provide state with nascent counts and processed_i counts
    state["protein"]["compartment_counts"]["nascent"] = {
        wid: {"c": 5.0, "m": 0.0} for wid in STAGE1_TRANSLOCATING_WIDS
    }
    state["protein"]["compartment_counts"]["processed_i"] = {
        wid: {"c": 3.0, "m": 0.0} for wid in STAGE1_TRANSLOCATING_WIDS
    }

    update = proc.next_update(1.0, state)
    prot_update = update.get("protein", {})
    comp_update = prot_update.get("compartment_counts", prot_update)

    # Nascent form MUST NOT be modified
    assert "nascent" not in comp_update, (
        "PT-QUEUE-CONFLATION: translocation must not write to nascent form"
    )


def test_stage1_translocation_exact_compartments_and_conservation() -> None:
    """Design C15 / C16: For Stage-1 WIDs (MG_191, MG_192, MG_318), copies move

    cytosol ('c') -> membrane ('m') on processed_i form, and total count is conserved.
    """
    proc = KarrProteinTranslocationProcess({})
    state = _base_stage1_state(proc)

    wid = "MG_318_MONOMER"
    state["protein"]["compartment_counts"]["processed_i"][wid] = {
        c: 0.0 for c in COMPARTMENTS
    }
    state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 4.0

    update = proc.next_update(1.0, state)
    prot_update = update.get("protein", {})
    comp_update = prot_update.get("compartment_counts", prot_update)
    proc_i_update = comp_update.get("processed_i", comp_update)

    assert wid in proc_i_update, f"Expected update for {wid} in processed_i"
    deltas = proc_i_update[wid]
    # Destination must be membrane ('m'), source cytosol ('c')
    assert "m" in deltas and "c" in deltas, f"Expected deltas on 'c' and 'm', got {deltas}"
    assert deltas["c"] < 0, f"Expected negative delta on source cytosol 'c', got {deltas['c']}"
    assert deltas["m"] > 0, f"Expected positive delta on destination membrane 'm', got {deltas['m']}"
    assert deltas["c"] + deltas["m"] == pytest.approx(0.0), "Mass conservation violated in translocation"


def test_stage1_no_location_string_for_migrated_wids() -> None:
    """Design C15: Translocation must not emit species-level 'location' strings

    for migrated WIDs.
    """
    proc = KarrProteinTranslocationProcess({})
    state = _base_stage1_state(proc)

    for wid in STAGE1_TRANSLOCATING_WIDS:
        state["protein"]["compartment_counts"]["processed_i"][wid] = {
            c: 0.0 for c in COMPARTMENTS
        }
        state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 2.0

    update = proc.next_update(1.0, state)
    prot_update = update.get("protein", {})

    # If location branch exists in update, it must not contain any migrated WIDs
    if "location" in prot_update:
        written_locations = prot_update["location"]
        for wid in STAGE1_TRANSLOCATING_WIDS:
            assert wid not in written_locations, (
                f"Design C15 violation: 'location' string still written for migrated WID {wid}"
            )

