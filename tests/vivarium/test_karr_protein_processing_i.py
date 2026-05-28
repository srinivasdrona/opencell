from __future__ import annotations

import sys
from copy import deepcopy
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

from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_composite import build_karr_chassis_v6


def _blank_state(process: KarrProteinProcessingIProcess) -> dict[str, Any]:
    return {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {
            "unprocessed_counts": {wid: 0.0 for wid in process.unprocessed_monomer_wids},
            "processed_counts": {wid: 0.0 for wid in process.processed_monomer_wids},
            "counts": {wid: 0.0 for wid in process.protein_enzyme_wids},
            "enzyme_counts": {wid: 0.0 for wid in process.protein_enzyme_wids},
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }


def _set_substrates_available(
    state: dict[str, Any], process: KarrProteinProcessingIProcess, value: float
) -> None:
    for wid in process.substrate_wids:
        state["substrates"][wid] = float(value)
        state["substrates_allocated"][process.name][wid] = float(value)


def test_fixture_loads() -> None:
    p = KarrProteinProcessingIProcess({})
    assert p.name == "karr_protein_processing_i"
    assert len(p.substrate_wids) == 4
    assert set(p.substrate_wids) == {"H2O", "H", "MET", "FOR"}
    assert len(p.enzyme_wids) == 2
    assert p.enzyme_wids == ["MG_106_DIMER", "MG_172_MONOMER"]
    assert len(p.unprocessed_monomer_wids) == 482
    assert len(p.processed_monomer_wids) == 482
    assert int(np.sum(p.met_cleavage_mask)) == 35
    assert p.deformylase_specific_rate == 38.0
    assert p.methionine_aminopeptidase_specific_rate == 6.0

    schema = p.ports_schema()
    assert all(leaf["_updater"] == "accumulate" for leaf in schema["substrates"].values())
    assert all(
        leaf["_updater"] == "accumulate"
        for leaf in schema["protein"]["unprocessed_counts"].values()
    )
    assert all(
        leaf["_updater"] == "accumulate"
        for leaf in schema["protein"]["processed_counts"].values()
    )
    assert all(leaf["_updater"] == "accumulate" for leaf in schema["protein"]["counts"].values())


def test_no_unprocessed_no_action() -> None:
    p = KarrProteinProcessingIProcess({})
    state = _blank_state(p)
    _set_substrates_available(state, p, value=1_000.0)
    state["complex"]["counts"]["MG_106_DIMER"] = 10.0
    state["protein"]["enzyme_counts"]["MG_172_MONOMER"] = 10.0
    assert p.next_update(1.0, state) == {}


def test_deformylase_always_required() -> None:
    p = KarrProteinProcessingIProcess({"rng_seed": 7})
    state = _blank_state(p)
    _set_substrates_available(state, p, value=1_000.0)

    non_cleavage_idx = int(np.flatnonzero(~p.met_cleavage_mask)[0])
    non_cleavage_wid = p.unprocessed_monomer_wids[non_cleavage_idx]
    state["protein"]["unprocessed_counts"][non_cleavage_wid] = 10.0

    state["complex"]["counts"]["MG_106_DIMER"] = 0.0
    state["protein"]["enzyme_counts"]["MG_172_MONOMER"] = 100.0
    assert p.next_update(1.0, state) == {}

    state["complex"]["counts"]["MG_106_DIMER"] = 1.0
    update = p.next_update(1.0, state)
    assert float(update["protein"]["processed_counts"][non_cleavage_wid]) == 10.0


def test_met_cleavage_subset() -> None:
    p = KarrProteinProcessingIProcess({"rng_seed": 11})
    cleavage_wid = p.unprocessed_monomer_wids[int(np.flatnonzero(p.met_cleavage_mask)[0])]
    non_cleavage_wid = p.unprocessed_monomer_wids[int(np.flatnonzero(~p.met_cleavage_mask)[0])]
    met_wid = p.substrate_wids[p.substrate_idx_methionine]

    no_map_state = _blank_state(p)
    _set_substrates_available(no_map_state, p, value=1_000.0)
    no_map_state["protein"]["unprocessed_counts"][cleavage_wid] = 5.0
    no_map_state["protein"]["unprocessed_counts"][non_cleavage_wid] = 5.0
    no_map_state["complex"]["counts"]["MG_106_DIMER"] = 2.0
    no_map_state["protein"]["enzyme_counts"]["MG_172_MONOMER"] = 0.0
    no_map_update = p.next_update(1.0, no_map_state)
    assert float(no_map_update["protein"]["processed_counts"].get(cleavage_wid, 0.0)) == 0.0
    assert float(no_map_update["protein"]["processed_counts"].get(non_cleavage_wid, 0.0)) == 5.0
    assert float(no_map_update["substrates"].get(met_wid, 0.0)) == 0.0

    with_map_state = deepcopy(no_map_state)
    with_map_state["protein"]["enzyme_counts"]["MG_172_MONOMER"] = 1.0
    with_map_update = p.next_update(1.0, with_map_state)
    assert float(with_map_update["protein"]["processed_counts"].get(cleavage_wid, 0.0)) == 5.0
    assert float(with_map_update["substrates"].get(met_wid, 0.0)) == 5.0


def test_mass_conservation() -> None:
    p = KarrProteinProcessingIProcess({"rng_seed": 19})
    state = _blank_state(p)
    _set_substrates_available(state, p, value=5_000.0)
    state["complex"]["counts"]["MG_106_DIMER"] = 20.0
    state["protein"]["enzyme_counts"]["MG_172_MONOMER"] = 20.0

    cleavage_idx = np.flatnonzero(p.met_cleavage_mask)[:3]
    non_cleavage_idx = np.flatnonzero(~p.met_cleavage_mask)[:4]
    for idx in cleavage_idx:
        state["protein"]["unprocessed_counts"][p.unprocessed_monomer_wids[int(idx)]] = 8.0
    for idx in non_cleavage_idx:
        state["protein"]["unprocessed_counts"][p.unprocessed_monomer_wids[int(idx)]] = 9.0

    update = p.next_update(1.0, state)
    processed_deltas = update["protein"]["processed_counts"]
    total_processed = float(sum(processed_deltas.values()))
    total_unprocessed_delta = float(sum(update["protein"]["unprocessed_counts"].values()))
    assert total_unprocessed_delta == -total_processed

    monomer_index = {wid: i for i, wid in enumerate(p.processed_monomer_wids)}
    cleaved_processed = float(
        sum(
            delta
            for wid, delta in processed_deltas.items()
            if p.met_cleavage_mask[monomer_index[wid]]
        )
    )

    water_wid = p.substrate_wids[p.substrate_idx_water]
    formate_wid = p.substrate_wids[p.substrate_idx_formate]
    methionine_wid = p.substrate_wids[p.substrate_idx_methionine]
    assert float(update["substrates"][water_wid]) == -(total_processed + cleaved_processed)
    assert float(update["substrates"][formate_wid]) == total_processed
    assert float(update["substrates"][methionine_wid]) == cleaved_processed


def test_enzyme_kinetics_limit() -> None:
    p = KarrProteinProcessingIProcess({"rng_seed": 0})
    state = _blank_state(p)
    _set_substrates_available(state, p, value=10_000.0)

    cleavage_wid = p.unprocessed_monomer_wids[int(np.flatnonzero(p.met_cleavage_mask)[0])]
    state["protein"]["unprocessed_counts"][cleavage_wid] = 100.0
    state["complex"]["counts"]["MG_106_DIMER"] = 1.0
    state["protein"]["enzyme_counts"]["MG_172_MONOMER"] = 1.0

    update = p.next_update(1.0, state)
    assert float(update["protein"]["processed_counts"][cleavage_wid]) == 6.0


def test_deterministic_with_seed() -> None:
    p1 = KarrProteinProcessingIProcess({"rng_seed": 123})
    p2 = KarrProteinProcessingIProcess({"rng_seed": 123})
    s1 = _blank_state(p1)
    _set_substrates_available(s1, p1, value=5_000.0)
    s1["complex"]["counts"]["MG_106_DIMER"] = 10.0
    s1["protein"]["enzyme_counts"]["MG_172_MONOMER"] = 10.0

    for idx in np.flatnonzero(p1.met_cleavage_mask)[:10]:
        s1["protein"]["unprocessed_counts"][p1.unprocessed_monomer_wids[int(idx)]] = 5.0
    for idx in np.flatnonzero(~p1.met_cleavage_mask)[:20]:
        s1["protein"]["unprocessed_counts"][p1.unprocessed_monomer_wids[int(idx)]] = 7.0

    s2 = deepcopy(s1)
    assert p1.next_update(1.0, s1) == p2.next_update(1.0, s2)


def test_chassis_seeded_complex_enzyme_drives_processing_output() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_protein_processing_i"]
    state = deepcopy(composite["state"])

    deformylase_seed = float(state["complex"]["counts"]["MG_106_DIMER"])
    assert deformylase_seed > 0.0

    non_cleavage_idx = int(np.flatnonzero(~process.met_cleavage_mask)[0])
    non_cleavage_wid = process.unprocessed_monomer_wids[non_cleavage_idx]

    for wid in process.unprocessed_monomer_wids:
        state["protein"]["unprocessed_counts"][wid] = 0.0
    state["protein"]["unprocessed_counts"][non_cleavage_wid] = 1_000.0

    water_wid = process.substrate_wids[process.substrate_idx_water]
    state.setdefault("substrates_allocated", {}).setdefault(
        process.name, {wid: 0.0 for wid in process.substrate_wids}
    )
    state["substrates_allocated"][process.name][water_wid] = 10_000.0

    update = process.next_update(1.0, state)
    expected_processed = float(min(1_000, int(np.floor(deformylase_seed * process.deformylase_specific_rate))))
    assert float(update["protein"]["processed_counts"][non_cleavage_wid]) == expected_processed
