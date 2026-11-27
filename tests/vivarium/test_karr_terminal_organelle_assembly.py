from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_terminal_organelle_assembly import (
    KarrTerminalOrganelleAssemblyProcess,
)

EXPECTED_COMPONENT_WIDS = [
    "MG_191_MONOMER",
    "MG_192_MONOMER",
    "MG_217_MONOMER",
    "MG_218_MONOMER",
    "MG_312_MONOMER",
    "MG_317_MONOMER",
    "MG_318_MONOMER",
    "MG_386_MONOMER",
]
COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")


def test_fixture_loads_and_metadata() -> None:
    """Preserve fixture-loading and biological metadata assertions from source."""
    process = KarrTerminalOrganelleAssemblyProcess({})
    assert process.name == "karr_terminal_organelle_assembly"
    assert len(process.component_wids) == 8
    assert len(process.reaction_wids) == 10
    assert list(process.component_wids) == EXPECTED_COMPONENT_WIDS


def test_localization_matrices_and_thresholds() -> None:
    """Verify localization reaction stoichiometry and threshold vectors from fixture."""
    process = KarrTerminalOrganelleAssemblyProcess({})
    # localizationReactions is 10 reactions x 8 substrates x 2 compartments (inc/uninc)
    assert process.localization_reactions.shape == (10, 8, 2)
    assert process.localization_substrates.shape == (10, 8)
    expected_threshold = np.array([1, 0, 1, 1, 1, 1, 1, 1, 1, 1], dtype=np.int64)
    threshold_arr = getattr(process, "localization_threshold", getattr(process, "localization_thresholds", None))
    assert threshold_arr is not None, "Process must expose localization threshold"
    assert np.array_equal(np.asarray(threshold_arr).reshape(-1), expected_threshold)



def test_ports_schema_declares_only_protein_port() -> None:
    """Design D4: Process declares ONE port ('protein'); dropped ports are cell,

    substrates, enzymes, boundEnzymes.
    """
    process = KarrTerminalOrganelleAssemblyProcess({})
    schema = process.ports_schema()

    # Must declare protein port
    assert "protein" in schema, "ports_schema must declare 'protein' port"

    # Must NOT declare deleted legacy ports
    forbidden_ports = {"cell", "substrates", "enzymes", "boundEnzymes"}
    declared_forbidden = forbidden_ports & set(schema.keys())
    assert not declared_forbidden, (
        f"Design D4 violation: ports_schema still declares deleted ports: {declared_forbidden}"
    )

    # protein port must connect to compartmental authority (compartment_counts.mature)
    protein_schema = schema["protein"]
    assert "compartment_counts" in protein_schema or "mature" in protein_schema, (
        f"protein port must declare compartment_counts.mature structure, got: {list(protein_schema.keys())}"
    )


def test_no_reduced_state_attributes_or_target_caps() -> None:
    """Design D4: target_terminal_organelle_count cap and activity gates are deleted."""
    process = KarrTerminalOrganelleAssemblyProcess({})
    # Should not cap assembly by target count
    assert not hasattr(process, "target_terminal_organelle_count") or process.target_terminal_organelle_count is None, (
        "target_terminal_organelle_count must be deleted per Design D4"
    )

    schema = process.ports_schema()
    if "protein" in schema:
        assert "activity" not in schema["protein"], (
            "protein.activity gate must be deleted per Design D4"
        )


def test_single_step_transfer_via_authority() -> None:
    """Verify single-step transfer executes on protein.compartment_counts.mature."""
    process = KarrTerminalOrganelleAssemblyProcess({})

    # Setup state: MG_312 (HMW1) has 1 unincorporated copy in 'c', MG_218 (HMW2) has 33 in 'tc'
    state: dict[str, Any] = {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {c: 0.0 for c in COMPARTMENTS}
                    for wid in EXPECTED_COMPONENT_WIDS
                }
            }
        }
    }
    state["protein"]["compartment_counts"]["mature"]["MG_312_MONOMER"]["c"] = 1.0
    state["protein"]["compartment_counts"]["mature"]["MG_218_MONOMER"]["tc"] = 33.0

    update = process.next_update(1.0, state)
    assert update, "Expected non-empty update for valid TOA transfer"

    # Assert update is on protein port and not cell/substrates
    assert "cell" not in update
    assert "substrates" not in update
    assert "protein" in update

    # Verify deltas: MG_312_MONOMER must have c: -1.0, tc: +1.0 (integer-exact)
    prot_up = update["protein"]
    mature_up = prot_up.get("compartment_counts", prot_up).get("mature", prot_up)
    assert "MG_312_MONOMER" in mature_up
    assert mature_up["MG_312_MONOMER"]["c"] == -1.0
    assert mature_up["MG_312_MONOMER"]["tc"] == 1.0
    assert float(mature_up["MG_312_MONOMER"]["c"]).is_integer()
    assert float(mature_up["MG_312_MONOMER"]["tc"]).is_integer()


def test_empty_update_when_unincorporated_is_zero() -> None:
    """When all unincorporated counts are zero, next_update returns empty dict."""
    process = KarrTerminalOrganelleAssemblyProcess({})
    state: dict[str, Any] = {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {c: 0.0 for c in COMPARTMENTS}
                    for wid in EXPECTED_COMPONENT_WIDS
                }
            }
        }
    }
    # Only incorporated counts exist
    state["protein"]["compartment_counts"]["mature"]["MG_312_MONOMER"]["tc"] = 26.0
    state["protein"]["compartment_counts"]["mature"]["MG_218_MONOMER"]["tc"] = 33.0

    update = process.next_update(1.0, state)
    assert update == {}, f"Expected empty update when uninc is 0, got {update}"
