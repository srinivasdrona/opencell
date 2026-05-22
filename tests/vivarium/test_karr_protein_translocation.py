from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

import pytest

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

from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess


def _base_state(process: KarrProteinTranslocationProcess) -> dict[str, Any]:
    return {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {
            "counts": {wid: 0.0 for wid in process.protein_count_wids},
            "location": {wid: "cytoplasm" for wid in process.translocatable_wids},
        },
        "requests": {process.name: {process.atp_wid: 0.0}},
        "substrates_allocated": {process.name: {process.atp_wid: 0.0}},
    }


def _enable_core_enzymes(state: dict[str, Any], process: KarrProteinTranslocationProcess) -> None:
    state["protein"]["counts"][process.srp_wid] = 2.0
    state["protein"]["counts"][process.srp_receptor_wid] = 2.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 2.0
    state["protein"]["counts"][process.translocase_pore_wid] = 2.0


def test_fixture_loads() -> None:
    process = KarrProteinTranslocationProcess({})
    assert process.name == "karr_protein_translocation"
    assert len(process.enzyme_wids) == 4
    assert len(process.translocatable_wids) == 117
    assert len(process.integral_membrane_wids) > 0
    assert len(process.lipoprotein_wids) > 0
    assert len(process.extracellular_wids) > 0
    assert (
        len(process.integral_membrane_wids)
        + len(process.lipoprotein_wids)
        + len(process.extracellular_wids)
    ) == 117
    assert all(process.destination_by_wid[wid] == "membrane" for wid in process.integral_membrane_wids)
    assert all(process.destination_by_wid[wid] == "membrane" for wid in process.lipoprotein_wids)
    assert all(
        process.destination_by_wid[wid] == "extracellular" for wid in process.extracellular_wids
    )


def test_no_cytoplasmic_no_translocation() -> None:
    process = KarrProteinTranslocationProcess({})
    state = _base_state(process)
    wid = process.integral_membrane_wids[0]
    state["protein"]["counts"][wid] = 1.0
    state["protein"]["location"][wid] = "membrane"
    _enable_core_enzymes(state, process)
    state["substrates"][process.atp_wid] = 100.0

    update = process.next_update(1.0, state)
    assert update == {}


def test_srp_mediated_integral_membrane_path() -> None:
    process = KarrProteinTranslocationProcess({"rng_seed": 1})
    state = _base_state(process)
    wid = process.integral_membrane_wids[0]
    atp_cost = process.atp_cost_by_wid[wid]

    state["protein"]["counts"][wid] = 1.0
    state["protein"]["counts"][process.srp_wid] = 1.0
    state["protein"]["counts"][process.srp_receptor_wid] = 1.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 1.0
    state["protein"]["counts"][process.translocase_pore_wid] = 1.0
    state["substrates"][process.atp_wid] = float(atp_cost)

    update = process.next_update(1.0, state)
    assert update["protein"]["location"][wid] == "membrane"
    assert update["substrates"][process.atp_wid] == pytest.approx(-float(atp_cost))


def test_direct_lipoprotein_path() -> None:
    process = KarrProteinTranslocationProcess({})
    state = _base_state(process)
    wid = process.lipoprotein_wids[0]
    atp_cost = process.atp_cost_by_wid[wid]

    state["protein"]["counts"][wid] = 1.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 1.0
    state["protein"]["counts"][process.translocase_pore_wid] = 1.0
    state["protein"]["counts"][process.srp_wid] = 0.0
    state["protein"]["counts"][process.srp_receptor_wid] = 0.0
    state["substrates"][process.atp_wid] = float(atp_cost)

    update = process.next_update(1.0, state)
    assert update["protein"]["location"][wid] == "membrane"
    assert update["substrates"][process.atp_wid] == pytest.approx(-float(atp_cost))


def test_atp_consumption_per_translocation() -> None:
    process = KarrProteinTranslocationProcess({"rng_seed": 3})
    state = _base_state(process)
    wid_integral = process.integral_membrane_wids[0]
    wid_extracellular = process.extracellular_wids[0]
    atp_need = (
        process.atp_cost_by_wid[wid_integral] + process.atp_cost_by_wid[wid_extracellular]
    )

    state["protein"]["counts"][wid_integral] = 1.0
    state["protein"]["counts"][wid_extracellular] = 1.0
    state["protein"]["counts"][process.srp_wid] = 1.0
    state["protein"]["counts"][process.srp_receptor_wid] = 1.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 2.0
    state["protein"]["counts"][process.translocase_pore_wid] = 2.0
    state["substrates"][process.atp_wid] = float(atp_need)

    update = process.next_update(1.0, state)
    assert update["substrates"][process.atp_wid] == pytest.approx(-float(atp_need))
    assert update["protein"]["location"][wid_integral] == "membrane"
    assert update["protein"]["location"][wid_extracellular] == "extracellular"


def test_srp_starvation_blocks_membrane_only() -> None:
    process = KarrProteinTranslocationProcess({})
    state = _base_state(process)
    wid_integral = process.integral_membrane_wids[0]
    wid_lipoprotein = process.lipoprotein_wids[0]
    atp_need = process.atp_cost_by_wid[wid_integral] + process.atp_cost_by_wid[wid_lipoprotein]

    state["protein"]["counts"][wid_integral] = 1.0
    state["protein"]["counts"][wid_lipoprotein] = 1.0
    state["protein"]["counts"][process.srp_wid] = 0.0
    state["protein"]["counts"][process.srp_receptor_wid] = 0.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 2.0
    state["protein"]["counts"][process.translocase_pore_wid] = 2.0
    state["substrates"][process.atp_wid] = float(atp_need)

    update = process.next_update(1.0, state)
    assert wid_integral not in update["protein"]["location"]
    assert update["protein"]["location"][wid_lipoprotein] == "membrane"
    assert update["substrates"][process.atp_wid] == pytest.approx(
        -float(process.atp_cost_by_wid[wid_lipoprotein])
    )


def test_translocase_starvation_blocks_all() -> None:
    process = KarrProteinTranslocationProcess({})
    state = _base_state(process)
    wid_integral = process.integral_membrane_wids[0]
    wid_lipoprotein = process.lipoprotein_wids[0]

    state["protein"]["counts"][wid_integral] = 1.0
    state["protein"]["counts"][wid_lipoprotein] = 1.0
    state["protein"]["counts"][process.srp_wid] = 2.0
    state["protein"]["counts"][process.srp_receptor_wid] = 2.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 0.0
    state["protein"]["counts"][process.translocase_pore_wid] = 0.0
    state["substrates"][process.atp_wid] = 500.0

    update = process.next_update(1.0, state)
    assert update == {}


def test_protein_location_store_updates() -> None:
    process = KarrProteinTranslocationProcess({})
    schema = process.ports_schema()
    example_wid = process.extracellular_wids[0]
    assert schema["protein"]["location"][example_wid]["_updater"] == "set"
    assert schema["protein"]["counts"][example_wid]["_updater"] == "accumulate"
    assert schema["substrates"][process.atp_wid]["_updater"] == "accumulate"

    state = _base_state(process)
    state["protein"]["counts"][example_wid] = 1.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 1.0
    state["protein"]["counts"][process.translocase_pore_wid] = 1.0
    state["substrates"][process.atp_wid] = float(process.atp_cost_by_wid[example_wid])
    update = process.next_update(1.0, state)

    assert update["protein"]["location"] == {example_wid: "extracellular"}
    assert "counts" not in update.get("protein", {})


def test_deterministic_with_seed() -> None:
    process_1 = KarrProteinTranslocationProcess({"rng_seed": 42})
    process_2 = KarrProteinTranslocationProcess({"rng_seed": 42})
    state = _base_state(process_1)

    wid_a = process_1.integral_membrane_wids[0]
    wid_b = process_1.integral_membrane_wids[1]
    max_atp = max(process_1.atp_cost_by_wid[wid_a], process_1.atp_cost_by_wid[wid_b])

    state["protein"]["counts"][wid_a] = 1.0
    state["protein"]["counts"][wid_b] = 1.0
    state["protein"]["counts"][process_1.srp_wid] = 1.0
    state["protein"]["counts"][process_1.srp_receptor_wid] = 1.0
    state["protein"]["counts"][process_1.translocase_atpase_wid] = 1.0
    state["protein"]["counts"][process_1.translocase_pore_wid] = 1.0
    state["substrates"][process_1.atp_wid] = float(max_atp)

    state_2 = deepcopy(state)
    update_1 = process_1.next_update(1.0, state)
    update_2 = process_2.next_update(1.0, state_2)
    assert update_1 == update_2

