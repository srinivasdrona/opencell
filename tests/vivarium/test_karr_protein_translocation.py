from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
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
            "unprocessed_counts": {wid: 0.0 for wid in process.translocatable_wids},
            "location": {wid: "cytoplasm" for wid in process.translocatable_wids},
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_count_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.request_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.vector_wids}},
    }


def _set_pending_monomer(state: dict[str, Any], wid: str, count: float) -> None:
    state["protein"]["counts"][wid] = float(count)
    state["protein"]["unprocessed_counts"][wid] = float(count)


def _set_enzyme_count(
    state: dict[str, Any],
    process: KarrProteinTranslocationProcess,
    wid: str,
    count: float,
) -> None:
    if wid in process.complex_count_wids:
        state["complex"]["counts"][wid] = float(count)
        return
    state["protein"]["counts"][wid] = float(count)


def _enable_core_enzymes(state: dict[str, Any], process: KarrProteinTranslocationProcess) -> None:
    _set_enzyme_count(state, process, process.srp_wid, 2.0)
    _set_enzyme_count(state, process, process.srp_receptor_wid, 2.0)
    _set_enzyme_count(state, process, process.translocase_atpase_wid, 2.0)
    _set_enzyme_count(state, process, process.translocase_pore_wid, 2.0)


def _set_allocated_resources(
    state: dict[str, Any],
    process: KarrProteinTranslocationProcess,
    *,
    atp: float,
    gtp: float,
    h2o: float,
) -> None:
    state["substrates"][process.atp_wid] = float(atp)
    state["substrates"][process.gtp_wid] = float(gtp)
    state["substrates"][process.h2o_wid] = float(h2o)
    state["requests"][process.name][process.atp_wid] = float(atp)
    state["requests"][process.name][process.gtp_wid] = float(gtp)
    state["requests"][process.name][process.h2o_wid] = float(h2o)
    state["substrates_allocated"][process.name][process.atp_wid] = float(atp)
    state["substrates_allocated"][process.name][process.gtp_wid] = float(gtp)
    state["substrates_allocated"][process.name][process.h2o_wid] = float(h2o)


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
    assert all(
        process.destination_by_wid[wid] == "membrane" for wid in process.integral_membrane_wids
    )
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
    _set_allocated_resources(state, process, atp=100.0, gtp=100.0, h2o=200.0)

    update = process.next_update(1.0, state)
    assert update == {}


def test_srp_mediated_integral_membrane_path() -> None:
    process = KarrProteinTranslocationProcess({"rng_seed": 1})
    state = _base_state(process)
    wid = process.integral_membrane_wids[0]
    atp_cost = process.atp_cost_by_wid[wid]

    _set_pending_monomer(state, wid, 1.0)
    _set_enzyme_count(state, process, process.srp_wid, 1.0)
    _set_enzyme_count(state, process, process.srp_receptor_wid, 1.0)
    _set_enzyme_count(state, process, process.translocase_atpase_wid, 1.0)
    _set_enzyme_count(state, process, process.translocase_pore_wid, 1.0)
    gtp_cost = float(process.srp_gtp_cost_per_monomer)
    _set_allocated_resources(
        state,
        process,
        atp=float(atp_cost),
        gtp=gtp_cost,
        h2o=float(atp_cost) + gtp_cost,
    )

    update = process.next_update(1.0, state)
    assert update["protein"]["location"][wid] == "membrane"
    assert update["substrates"][process.atp_wid] == pytest.approx(-float(atp_cost))
    assert update["substrates"][process.gtp_wid] == pytest.approx(-gtp_cost)
    assert update["substrates"][process.adp_wid] == pytest.approx(float(atp_cost))
    assert update["substrates"][process.gdp_wid] == pytest.approx(gtp_cost)


def test_direct_lipoprotein_path() -> None:
    process = KarrProteinTranslocationProcess({})
    state = _base_state(process)
    wid = process.lipoprotein_wids[0]
    atp_cost = process.atp_cost_by_wid[wid]

    _set_pending_monomer(state, wid, 1.0)
    _set_enzyme_count(state, process, process.translocase_atpase_wid, 1.0)
    _set_enzyme_count(state, process, process.translocase_pore_wid, 1.0)
    _set_enzyme_count(state, process, process.srp_wid, 0.0)
    _set_enzyme_count(state, process, process.srp_receptor_wid, 0.0)
    _set_allocated_resources(state, process, atp=float(atp_cost), gtp=0.0, h2o=float(atp_cost))

    update = process.next_update(1.0, state)
    assert update["protein"]["location"][wid] == "membrane"
    assert update["substrates"][process.atp_wid] == pytest.approx(-float(atp_cost))
    assert process.gtp_wid not in update["substrates"]
    assert process.gdp_wid not in update["substrates"]


def test_atp_consumption_per_translocation() -> None:
    process = KarrProteinTranslocationProcess({"rng_seed": 3})
    state = _base_state(process)
    wid_integral = process.integral_membrane_wids[0]
    wid_extracellular = process.extracellular_wids[0]
    atp_need = process.atp_cost_by_wid[wid_integral] + process.atp_cost_by_wid[wid_extracellular]

    _set_pending_monomer(state, wid_integral, 1.0)
    _set_pending_monomer(state, wid_extracellular, 1.0)
    _set_enzyme_count(state, process, process.srp_wid, 1.0)
    _set_enzyme_count(state, process, process.srp_receptor_wid, 1.0)
    _set_enzyme_count(state, process, process.translocase_atpase_wid, 2.0)
    _set_enzyme_count(state, process, process.translocase_pore_wid, 2.0)
    gtp_need = float(process.srp_gtp_cost_per_monomer)
    _set_allocated_resources(
        state,
        process,
        atp=float(atp_need),
        gtp=gtp_need,
        h2o=float(atp_need) + gtp_need,
    )

    update = process.next_update(1.0, state)
    assert update["substrates"][process.atp_wid] == pytest.approx(-float(atp_need))
    assert update["substrates"][process.gtp_wid] == pytest.approx(-gtp_need)
    assert update["protein"]["location"][wid_integral] == "membrane"
    assert update["protein"]["location"][wid_extracellular] == "extracellular"


def test_srp_starvation_blocks_membrane_only() -> None:
    process = KarrProteinTranslocationProcess({})
    state = _base_state(process)
    wid_integral = process.integral_membrane_wids[0]
    wid_lipoprotein = process.lipoprotein_wids[0]
    atp_need = process.atp_cost_by_wid[wid_integral] + process.atp_cost_by_wid[wid_lipoprotein]

    _set_pending_monomer(state, wid_integral, 1.0)
    _set_pending_monomer(state, wid_lipoprotein, 1.0)
    _set_enzyme_count(state, process, process.srp_wid, 0.0)
    _set_enzyme_count(state, process, process.srp_receptor_wid, 0.0)
    _set_enzyme_count(state, process, process.translocase_atpase_wid, 2.0)
    _set_enzyme_count(state, process, process.translocase_pore_wid, 2.0)
    _set_allocated_resources(state, process, atp=float(atp_need), gtp=0.0, h2o=float(atp_need))

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

    _set_pending_monomer(state, wid_integral, 1.0)
    _set_pending_monomer(state, wid_lipoprotein, 1.0)
    _set_enzyme_count(state, process, process.srp_wid, 2.0)
    _set_enzyme_count(state, process, process.srp_receptor_wid, 2.0)
    _set_enzyme_count(state, process, process.translocase_atpase_wid, 0.0)
    _set_enzyme_count(state, process, process.translocase_pore_wid, 0.0)
    _set_allocated_resources(state, process, atp=500.0, gtp=500.0, h2o=1000.0)

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
    _set_pending_monomer(state, example_wid, 1.0)
    _set_enzyme_count(state, process, process.translocase_atpase_wid, 1.0)
    _set_enzyme_count(state, process, process.translocase_pore_wid, 1.0)
    atp_need = float(process.atp_cost_by_wid[example_wid])
    _set_allocated_resources(state, process, atp=atp_need, gtp=0.0, h2o=atp_need)
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

    _set_pending_monomer(state, wid_a, 1.0)
    _set_pending_monomer(state, wid_b, 1.0)
    _set_enzyme_count(state, process_1, process_1.srp_wid, 1.0)
    _set_enzyme_count(state, process_1, process_1.srp_receptor_wid, 1.0)
    _set_enzyme_count(state, process_1, process_1.translocase_atpase_wid, 1.0)
    _set_enzyme_count(state, process_1, process_1.translocase_pore_wid, 1.0)
    gtp_need = float(process_1.srp_gtp_cost_per_monomer)
    _set_allocated_resources(
        state,
        process_1,
        atp=float(max_atp),
        gtp=gtp_need,
        h2o=float(max_atp) + gtp_need,
    )

    state_2 = deepcopy(state)
    update_1 = process_1.next_update(1.0, state)
    update_2 = process_2.next_update(1.0, state_2)
    assert update_1 == update_2
