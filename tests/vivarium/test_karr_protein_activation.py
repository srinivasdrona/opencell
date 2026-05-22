from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

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

from opencell.vivarium.karr_protein_activation import KarrProteinActivationProcess

_REGULATED = {
    "MG_085_HEXAMER",
    "MG_101_MONOMER",
    "MG_127_MONOMER",
    "MG_205_DIMER",
    "MG_236_MONOMER",
    "MG_409_DIMER",
}


def _base_state(process: KarrProteinActivationProcess) -> dict[str, Any]:
    return {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "stimuli": {wid: 0.0 for wid in process.stimuli_wids},
        "protein": {
            "activity": {wid: 0 for wid in process.regulated_protein_wids}
        },
    }


def _apply_set_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for wid, value in update.get("protein", {}).get("activity", {}).items():
        state["protein"]["activity"][wid] = int(value)


def test_fixture_loads() -> None:
    process = KarrProteinActivationProcess({})
    assert process.name == "karr_protein_activation"
    assert len(process.regulated_protein_wids) == 6
    assert set(process.regulated_protein_wids) == _REGULATED
    assert set(process.rules.keys()) == _REGULATED
    assert all(process.rule_strings[wid] for wid in process.regulated_protein_wids)


def test_unregulated_proteins_unaffected() -> None:
    process = KarrProteinActivationProcess({})
    state = _base_state(process)
    state["protein"]["activity"]["MG_999_MONOMER"] = 1

    update = process.next_update(1.0, state)
    assert "MG_999_MONOMER" not in update["protein"]["activity"]
    _apply_set_update(state, update)
    assert state["protein"]["activity"]["MG_999_MONOMER"] == 1


def test_high_metabolite_activates() -> None:
    process = KarrProteinActivationProcess({})
    state = _base_state(process)
    state["stimuli"]["temperature"] = 43.0

    update = process.next_update(1.0, state)
    assert update["protein"]["activity"]["MG_205_DIMER"] == 1


def test_low_metabolite_deactivates() -> None:
    process = KarrProteinActivationProcess({})
    state = _base_state(process)
    state["stimuli"]["PI"] = 30.0

    active = process.next_update(1.0, state)
    assert active["protein"]["activity"]["MG_409_DIMER"] == 1

    state["stimuli"]["PI"] = 1.0
    inactive = process.next_update(1.0, state)
    assert inactive["protein"]["activity"]["MG_409_DIMER"] == 0


def test_rule_evaluation_per_tick() -> None:
    process = KarrProteinActivationProcess({})
    state = _base_state(process)

    observed: list[int] = []
    for pi in (0.0, 30.0, 30.0, 0.0):
        state["stimuli"]["PI"] = pi
        update = process.next_update(1.0, state)
        _apply_set_update(state, update)
        observed.append(state["protein"]["activity"]["MG_409_DIMER"])

    assert observed == [0, 1, 1, 0]


def test_no_random_no_seed_dependence() -> None:
    p1 = KarrProteinActivationProcess({"rng_seed": 1})
    p2 = KarrProteinActivationProcess({"rng_seed": 999})
    state = _base_state(p1)
    state["stimuli"]["G6P"] = 10.0
    state["stimuli"]["PI"] = 25.0
    state["stimuli"]["temperature"] = 45.0
    state["stimuli"]["stimulus_ironStress"] = 1.0
    state["stimuli"]["stimulus_thiolStress"] = 1.0

    update_1a = p1.next_update(1.0, state)
    update_1b = p1.next_update(1.0, state)
    update_2 = p2.next_update(1.0, state)
    assert update_1a == update_1b == update_2


def test_activation_state_emitted() -> None:
    process = KarrProteinActivationProcess({})
    schema = process.ports_schema()

    for wid in process.regulated_protein_wids:
        entry = schema["protein"]["activity"][wid]
        assert entry["_default"] == 0
        assert entry["_updater"] == "set"
        assert entry["_emit"] is True

    state = _base_state(process)
    state["stimuli"]["G6P"] = 7.0
    state["stimuli"]["stimulus_ironStress"] = 1.0
    update = process.next_update(1.0, state)
    activity = update["protein"]["activity"]

    assert set(activity.keys()) == _REGULATED
    assert set(activity.values()).issubset({0, 1})
