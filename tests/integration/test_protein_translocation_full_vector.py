from __future__ import annotations

import sys
from pathlib import Path

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

from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess


def test_protein_translocation_consumer_vector_enrolls_all_7_channels() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_protein_translocation"]
    allocator = composite["steps"]["karr_allocation_step"]

    consumers = dict(allocator.parameters["consumer_processes"])
    assert set(consumers[process.name]) == set(process.vector_wids)

    req_schema = process.ports_schema()["requests"][process.name]
    assert set(req_schema) == set(process.request_wids)


def test_protein_translocation_signed_deltas_cover_full_vector() -> None:
    process = KarrProteinTranslocationProcess({"rng_seed": 11})
    target_wid = process.integral_membrane_wids[0]
    atp_need = int(process.atp_cost_by_wid[target_wid])
    gtp_need = int(process.srp_gtp_cost_per_monomer)
    h2o_need = atp_need + gtp_need
    assert gtp_need > 0

    state = {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {
            "counts": {wid: 0.0 for wid in process.protein_count_wids},
            "location": {wid: "cytoplasm" for wid in process.translocatable_wids},
        },
        "requests": {
            process.name: {
                process.atp_wid: float(atp_need),
                process.gtp_wid: float(gtp_need),
                process.h2o_wid: float(h2o_need),
            }
        },
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.vector_wids}},
    }
    state["substrates"][process.atp_wid] = float(atp_need)
    state["substrates"][process.gtp_wid] = float(gtp_need)
    state["substrates"][process.h2o_wid] = float(h2o_need)
    state["substrates_allocated"][process.name][process.atp_wid] = float(atp_need)
    state["substrates_allocated"][process.name][process.gtp_wid] = float(gtp_need)
    state["substrates_allocated"][process.name][process.h2o_wid] = float(h2o_need)
    state["protein"]["counts"][target_wid] = 1.0
    state["protein"]["counts"][process.srp_wid] = 1.0
    state["protein"]["counts"][process.srp_receptor_wid] = 1.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 1.0
    state["protein"]["counts"][process.translocase_pore_wid] = 1.0

    update = process.next_update(1.0, state)
    delta = update["substrates"]

    assert delta[process.atp_wid] < 0.0
    assert delta[process.gtp_wid] < 0.0
    assert delta[process.h2o_wid] < 0.0
    assert delta[process.adp_wid] > 0.0
    assert delta[process.gdp_wid] > 0.0
    assert delta[process.pi_wid] > 0.0
    assert delta[process.h_wid] > 0.0

    assert delta[process.adp_wid] == pytest.approx(float(atp_need))
    assert delta[process.gdp_wid] == pytest.approx(float(gtp_need))
    assert delta[process.pi_wid] == pytest.approx(float(h2o_need))
    assert delta[process.h_wid] == pytest.approx(float(h2o_need))
