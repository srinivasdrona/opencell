from __future__ import annotations

import math
import sys
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

from opencell.vivarium.karr_terminal_organelle_assembly import (
    KarrTerminalOrganelleAssemblyProcess,
)


def _base_state(process: KarrTerminalOrganelleAssemblyProcess) -> dict[str, Any]:
    return {
        "protein": {"activity": {wid: 0.0 for wid in process.component_wids}},
        "cell": {
            "terminal_organelle_count": 0.0,
            "terminal_organelle_components_assembled": {
                wid: 0.0 for wid in process.component_wids
            },
        },
    }


def _enable_all_components(state: dict[str, Any], process: KarrTerminalOrganelleAssemblyProcess) -> None:
    for wid in process.component_wids:
        state["protein"]["activity"][wid] = 1.0


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    cell_update = update.get("cell", {})
    if "terminal_organelle_count" in cell_update:
        state["cell"]["terminal_organelle_count"] = float(
            state["cell"]["terminal_organelle_count"] + float(cell_update["terminal_organelle_count"])
        )
    for wid, delta in cell_update.get("terminal_organelle_components_assembled", {}).items():
        state["cell"]["terminal_organelle_components_assembled"][wid] = float(
            state["cell"]["terminal_organelle_components_assembled"].get(wid, 0.0) + float(delta)
        )


def test_fixture_loads_and_schema_defaults() -> None:
    process = KarrTerminalOrganelleAssemblyProcess({})
    assert process.name == "karr_terminal_organelle_assembly"
    assert len(process.component_wids) == 8
    assert len(process.reaction_wids) == 10
    assert process.target_terminal_organelle_count == 1
    assert process.component_wids == [
        "MG_191_MONOMER",
        "MG_192_MONOMER",
        "MG_217_MONOMER",
        "MG_218_MONOMER",
        "MG_312_MONOMER",
        "MG_317_MONOMER",
        "MG_318_MONOMER",
        "MG_386_MONOMER",
    ]

    schema = process.ports_schema()
    assert schema["cell"]["terminal_organelle_count"]["_updater"] == "accumulate"
    assert (
        schema["cell"]["terminal_organelle_components_assembled"]["MG_191_MONOMER"]["_updater"]
        == "accumulate"
    )
    assert schema["protein"]["activity"]["MG_191_MONOMER"]["_updater"] == "set"


def test_one_tick_positive_component_delta_and_no_substrate_contract() -> None:
    process = KarrTerminalOrganelleAssemblyProcess({})
    state = _base_state(process)
    _enable_all_components(state, process)

    update = process.next_update(1.0, state)
    component_delta = update["cell"]["terminal_organelle_components_assembled"]
    assert component_delta
    assert all(float(delta) >= 0.0 for delta in component_delta.values())
    assert update["cell"]["terminal_organelle_count"] == pytest.approx(1.0)

    # No shared-substrate contract for this process in Karr fixture/docstring.
    assert "requests" not in update
    assert "substrates" not in update
    assert "substrates_allocated" not in update


def test_activity_gate_blocks_all_assembly_when_off() -> None:
    process = KarrTerminalOrganelleAssemblyProcess({})
    state = _base_state(process)
    update = process.next_update(1.0, state)
    assert update == {}


def test_hmw_pair_dependency_blocks_mg312_when_mg218_inactive() -> None:
    process = KarrTerminalOrganelleAssemblyProcess({})
    state = _base_state(process)
    _enable_all_components(state, process)
    state["protein"]["activity"]["MG_218_MONOMER"] = 0.0

    update = process.next_update(1.0, state)
    assembled_delta = update["cell"]["terminal_organelle_components_assembled"]
    assert "MG_312_MONOMER" not in assembled_delta


def test_incorporated_dependency_allows_mg218_with_preassembled_mg312() -> None:
    process = KarrTerminalOrganelleAssemblyProcess({})
    state = _base_state(process)
    _enable_all_components(state, process)
    state["protein"]["activity"]["MG_312_MONOMER"] = 0.0
    state["cell"]["terminal_organelle_components_assembled"]["MG_312_MONOMER"] = 1.0

    update = process.next_update(1.0, state)
    assembled_delta = update["cell"]["terminal_organelle_components_assembled"]
    # Reaction 4 uses MG_312 incorporated dependency; this should still allow MG_218.
    assert assembled_delta.get("MG_218_MONOMER", 0.0) == pytest.approx(1.0)


def test_100_tick_progression_reaches_and_holds_target_two() -> None:
    process = KarrTerminalOrganelleAssemblyProcess({"target_terminal_organelle_count": 2})
    state = _base_state(process)
    _enable_all_components(state, process)

    observed_count: list[int] = []
    for _ in range(100):
        update = process.next_update(1.0, state)
        _apply_update(state, update)
        observed_count.append(int(state["cell"]["terminal_organelle_count"]))

    # Fixture-derived light trajectory: 0 -> 1 -> 2 then stable.
    assert observed_count[0] == 1
    assert observed_count[1] == 2
    assert all(v == 2 for v in observed_count[2:])
    for wid in process.component_wids:
        assert int(state["cell"]["terminal_organelle_components_assembled"][wid]) == 2


def test_no_nan_or_negative_regressions_over_100_ticks() -> None:
    process = KarrTerminalOrganelleAssemblyProcess({"target_terminal_organelle_count": 2})
    state = _base_state(process)
    _enable_all_components(state, process)

    for tick in range(100):
        # Alternate one component gate to stress dependency checks.
        state["protein"]["activity"]["MG_318_MONOMER"] = 0.0 if tick % 2 == 0 else 1.0
        update = process.next_update(1.0, state)

        if "cell" in update:
            count_delta = float(update["cell"].get("terminal_organelle_count", 0.0))
            assert math.isfinite(count_delta)
            assert count_delta >= 0.0
            for delta in update["cell"].get("terminal_organelle_components_assembled", {}).values():
                val = float(delta)
                assert math.isfinite(val)
                assert val >= 0.0

        _apply_update(state, update)
        assert state["cell"]["terminal_organelle_count"] >= 0.0
        for val in state["cell"]["terminal_organelle_components_assembled"].values():
            assert math.isfinite(float(val))
            assert float(val) >= 0.0
