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

from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess


def _base_state(
    process: KarrCytokinesisProcess,
    *,
    ftsz_ring_complete: bool,
    segregation_progress: float,
    division_progress: float = 0.0,
    division_complete: bool = False,
    gtp_substrate: float = 0.0,
    gtp_allocated: float = 0.0,
) -> dict[str, Any]:
    return {
        "cell": {
            "ftsz_ring_complete": bool(ftsz_ring_complete),
            "division_progress": float(division_progress),
            "division_complete": bool(division_complete),
        },
        "chromosome": {
            "segregation_progress": float(segregation_progress),
        },
        "substrates": {
            wid: 0.0 for wid in process._substrate_wids
        }
        | {process.gtp_wid: float(gtp_substrate)},
        "requests": {
            process.name: {process.gtp_wid: 0.0},
        },
        "substrates_allocated": {
            process.name: {process.gtp_wid: float(gtp_allocated)},
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    if "cell" in update and "division_progress" in update["cell"]:
        state["cell"]["division_progress"] = float(
            state["cell"]["division_progress"] + float(update["cell"]["division_progress"])
        )
    if "cell" in update and "division_complete" in update["cell"]:
        state["cell"]["division_complete"] = bool(update["cell"]["division_complete"])

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))


def test_process_instantiates_with_defaults() -> None:
    process = KarrCytokinesisProcess({"time_step": 1.0})
    assert process.name == "karr_cytokinesis"
    assert process.gtp_wid == "GTP"
    assert process.trace_n_ticks >= 100
    assert process.active_division_rate_per_s == pytest.approx(1.0 / float(process.trace_n_ticks))

    schema = process.ports_schema()
    assert schema["cell"]["division_progress"]["_updater"] == "accumulate"
    assert schema["cell"]["division_complete"]["_updater"] == "set"
    assert schema["requests"][process.name][process.gtp_wid]["_updater"] == "set"
    assert "_updater" not in schema["substrates_allocated"][process.name][process.gtp_wid]


def test_dependency_gating_blocks_progress() -> None:
    process = KarrCytokinesisProcess({"active_division_rate_per_s": 0.2, "progress_per_gtp": 0.1})

    ring_incomplete = _base_state(
        process,
        ftsz_ring_complete=False,
        segregation_progress=1.0,
        gtp_substrate=100.0,
        gtp_allocated=100.0,
    )
    seg_incomplete = _base_state(
        process,
        ftsz_ring_complete=True,
        segregation_progress=0.5,
        gtp_substrate=100.0,
        gtp_allocated=100.0,
    )

    update_ring = process.next_update(1.0, ring_incomplete)
    update_seg = process.next_update(1.0, seg_incomplete)

    assert "cell" not in update_ring
    assert "substrates" not in update_ring
    assert update_ring["requests"][process.name][process.gtp_wid] == pytest.approx(0.0)

    assert "cell" not in update_seg
    assert "substrates" not in update_seg
    assert update_seg["requests"][process.name][process.gtp_wid] == pytest.approx(0.0)


def test_progress_advances_when_gates_true() -> None:
    process = KarrCytokinesisProcess({"active_division_rate_per_s": 0.2, "progress_per_gtp": 0.1})
    state = _base_state(
        process,
        ftsz_ring_complete=True,
        segregation_progress=1.0,
        gtp_substrate=100.0,
        gtp_allocated=100.0,
    )

    update = process.next_update(1.0, state)

    assert update["cell"]["division_progress"] == pytest.approx(0.2)
    assert update["requests"][process.name][process.gtp_wid] == pytest.approx(2.0)
    assert update["substrates"][process.gtp_wid] == pytest.approx(-2.0)


def test_allocation_contract_bounds_progress() -> None:
    process = KarrCytokinesisProcess({"active_division_rate_per_s": 0.2, "progress_per_gtp": 0.1})
    state = _base_state(
        process,
        ftsz_ring_complete=True,
        segregation_progress=1.0,
        gtp_substrate=100.0,
        gtp_allocated=0.5,
    )

    update = process.next_update(1.0, state)

    assert update["requests"][process.name][process.gtp_wid] == pytest.approx(2.0)
    assert update["cell"]["division_progress"] == pytest.approx(0.05)
    assert update["substrates"][process.gtp_wid] == pytest.approx(-0.5)


def test_completion_event_emitted_at_progress_one() -> None:
    process = KarrCytokinesisProcess({"active_division_rate_per_s": 0.2, "progress_per_gtp": 0.1})
    state = _base_state(
        process,
        ftsz_ring_complete=True,
        segregation_progress=1.0,
        division_progress=0.95,
        division_complete=False,
        gtp_substrate=100.0,
        gtp_allocated=100.0,
    )

    update = process.next_update(1.0, state)
    assert update["cell"]["division_progress"] == pytest.approx(0.05)
    assert update["cell"]["division_complete"] is True


def test_100_tick_rate_matches_trace_window_calibration() -> None:
    process = KarrCytokinesisProcess({})
    state = _base_state(
        process,
        ftsz_ring_complete=True,
        segregation_progress=1.0,
        gtp_substrate=1.0e6,
        gtp_allocated=1.0e6,
    )

    total_gtp_consumed = 0.0
    for _ in range(100):
        update = process.next_update(1.0, state)
        total_gtp_consumed += -float(update.get("substrates", {}).get(process.gtp_wid, 0.0))
        _apply_update(state, update)

    expected_progress = min(1.0, 100.0 * process.active_division_rate_per_s)
    assert state["cell"]["division_progress"] == pytest.approx(expected_progress, abs=1.0e-9)
    assert total_gtp_consumed == pytest.approx(
        state["cell"]["division_progress"] / process.progress_per_gtp,
        rel=1.0e-9,
    )


def test_no_nan_or_negative_progress_regression() -> None:
    process = KarrCytokinesisProcess({"active_division_rate_per_s": 0.1, "progress_per_gtp": 0.05})
    state = _base_state(
        process,
        ftsz_ring_complete=True,
        segregation_progress=1.0,
        division_progress=-2.0,
        gtp_substrate=0.0,
        gtp_allocated=0.0,
    )

    for _ in range(120):
        update = process.next_update(1.0, state)
        _apply_update(state, update)
        assert 0.0 <= state["cell"]["division_progress"] <= 1.0
        assert math.isfinite(state["cell"]["division_progress"])
        gtp_delta = float(update.get("substrates", {}).get(process.gtp_wid, 0.0))
        assert math.isfinite(gtp_delta)
        assert gtp_delta <= 0.0
