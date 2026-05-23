from __future__ import annotations

import sys
from pathlib import Path
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

from opencell.vivarium.karr_cell_cycle_coordinator import CellCycleCoordinator


def _base_state(
    *,
    replication_state: str = "idle",
    cycle_phase: str = "idle",
    left_fork: float = 0.0,
    right_fork: float = 0.0,
    segregation_progress: float = 0.0,
    ftsz_ring_complete: bool = False,
    division_progress: float = 0.0,
    division_complete: bool = False,
) -> dict[str, Any]:
    return {
        "chromosome": {
            "replication_state": replication_state,
            "fork_position_bp": {"left": left_fork, "right": right_fork},
            "segregation_progress": segregation_progress,
        },
        "cell": {
            "cycle_phase": cycle_phase,
            "ftsz_ring_complete": ftsz_ring_complete,
            "division_progress": division_progress,
            "division_complete": division_complete,
        },
    }


def test_idle_to_initiating_on_replication_trigger() -> None:
    step = CellCycleCoordinator({})
    update = step.next_update(
        1.0,
        _base_state(replication_state="initiating", cycle_phase="idle"),
    )
    assert update["cell"]["cycle_phase"] == "initiating"


def test_initiating_to_elongating_one_tick_later() -> None:
    step = CellCycleCoordinator({})
    update = step.next_update(
        1.0,
        _base_state(replication_state="initiating", cycle_phase="initiating"),
    )
    assert update["cell"]["cycle_phase"] == "elongating"
    assert update["chromosome"]["replication_state"] == "elongating"


def test_elongating_to_complete_when_forks_reach_terc() -> None:
    step = CellCycleCoordinator({"terc_position_bp": 100.0})
    update = step.next_update(
        1.0,
        _base_state(
            replication_state="elongating",
            cycle_phase="elongating",
            left_fork=100.0,
            right_fork=100.0,
        ),
    )
    assert update["cell"]["cycle_phase"] == "complete"
    assert update["chromosome"]["replication_state"] == "complete"


def test_complete_to_segregating_when_progress_starts() -> None:
    step = CellCycleCoordinator({})
    update = step.next_update(
        1.0,
        _base_state(
            replication_state="complete",
            cycle_phase="complete",
            segregation_progress=0.2,
        ),
    )
    assert update["cell"]["cycle_phase"] == "segregating"


def test_segregating_to_dividing_when_gate_ready() -> None:
    step = CellCycleCoordinator({})
    update = step.next_update(
        1.0,
        _base_state(
            replication_state="complete",
            cycle_phase="segregating",
            segregation_progress=1.0,
            ftsz_ring_complete=True,
        ),
    )
    assert update["cell"]["cycle_phase"] == "dividing"
    assert update["cell"]["gate_allow_cytokinesis"] is True


def test_dividing_to_divided_when_division_completes() -> None:
    step = CellCycleCoordinator({})
    update = step.next_update(
        1.0,
        _base_state(
            replication_state="complete",
            cycle_phase="dividing",
            segregation_progress=1.0,
            ftsz_ring_complete=True,
            division_progress=1.0,
            division_complete=True,
        ),
    )
    assert update["cell"]["cycle_phase"] == "divided"

