from __future__ import annotations

import math
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

from opencell.vivarium.karr_replication import KarrReplicationProcess


def _base_state(
    process: KarrReplicationProcess,
    *,
    replication_state: str = "idle",
    initial_substrate: float = 0.0,
    allocated_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    request_wids = [*process.dntp_wids, process.atp_wid]
    return {
        "chromosome": {
            "replication_state": replication_state,
            "fork_position_bp": {"left": 0.0, "right": 0.0},
            "events": {"replication_complete": 0.0},
        },
        "substrates": {wid: float(initial_substrate) for wid in process.substrate_wids},
        "requests": {process.name: {wid: 0.0 for wid in request_wids}},
        "substrates_allocated": {
            process.name: {
                wid: float((allocated_override or {}).get(wid, 0.0)) for wid in request_wids
            }
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any], process: KarrReplicationProcess) -> None:
    chrom_update = update.get("chromosome", {})
    if "replication_state" in chrom_update:
        state["chromosome"]["replication_state"] = str(chrom_update["replication_state"])

    for side, delta in chrom_update.get("fork_position_bp", {}).items():
        state["chromosome"]["fork_position_bp"][side] = float(
            state["chromosome"]["fork_position_bp"].get(side, 0.0) + float(delta)
        )

    for key, delta in chrom_update.get("events", {}).items():
        state["chromosome"]["events"][key] = float(
            state["chromosome"]["events"].get(key, 0.0) + float(delta)
        )

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))

    if "requests" in update and process.name in update["requests"]:
        state["requests"][process.name].update(
            {wid: float(v) for wid, v in update["requests"][process.name].items()}
        )


def test_process_instantiates() -> None:
    p = KarrReplicationProcess({})
    assert p.name == "karr_replication"
    assert p.dna_polymerase_elongation_rate_bp_per_s == 100.0
    assert p.fork_polymerization_rate_bp_per_s == 100.0
    assert p.terc_position_bp == 290038
    assert p.dntp_wids == ["DATP", "DCTP", "DGTP", "DTTP"]
    assert p.atp_wid == "ATP"


def test_idle_state_no_progress_no_request() -> None:
    p = KarrReplicationProcess({})
    state = _base_state(p, replication_state="idle", initial_substrate=1e6)
    update = p.next_update(1.0, state)
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    assert all(v == 0.0 for v in update["requests"][p.name].values())
    assert "substrates" not in update


def test_initiating_transitions_to_elongating_and_starts_at_zero() -> None:
    p = KarrReplicationProcess({})
    state = _base_state(
        p,
        replication_state="initiating",
        initial_substrate=1e6,
        allocated_override={wid: 1e6 for wid in [*p.dntp_wids, p.atp_wid]},
    )
    update = p.next_update(1.0, state)
    assert update["chromosome"]["replication_state"] == "elongating"
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    assert all(v == 0.0 for v in update["requests"][p.name].values())


def test_elongation_advances_and_consumes_dntps() -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    ticks = 5
    for _ in range(ticks):
        update = p.next_update(1.0, state)
        _apply_update(state, update, p)

    assert state["chromosome"]["fork_position_bp"]["left"] == float(ticks * 100)
    assert state["chromosome"]["fork_position_bp"]["right"] == float(ticks * 100)
    assert state["substrates"]["DATP"] < 1e9
    assert state["substrates"]["DCTP"] < 1e9
    assert state["substrates"]["DGTP"] < 1e9
    assert state["substrates"]["DTTP"] < 1e9


def test_completion_sets_state_and_emits_event_once() -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["chromosome"]["fork_position_bp"]["left"] = float(p.terc_position_bp - 10)
    state["chromosome"]["fork_position_bp"]["right"] = float(p.terc_position_bp - 10)

    update1 = p.next_update(1.0, state)
    _apply_update(state, update1, p)
    assert state["chromosome"]["replication_state"] == "complete"
    assert state["chromosome"]["events"]["replication_complete"] == 1.0

    update2 = p.next_update(1.0, state)
    _apply_update(state, update2, p)
    assert state["chromosome"]["events"]["replication_complete"] == 1.0


def test_limited_allocation_scales_progress_proportionally() -> None:
    p = KarrReplicationProcess({})
    desired = p._demand_from_advances(100, 100)
    alloc = {wid: math.floor(val * 0.25) for wid, val in desired.items()}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override={wid: float(alloc[wid]) for wid in alloc},
    )

    update = p.next_update(1.0, state)
    fork_delta = update["chromosome"]["fork_position_bp"]
    scale = min(float(alloc[wid]) / float(desired[wid]) for wid in desired if desired[wid] > 0)
    expected_per_fork = float(math.floor(100.0 * scale))
    assert fork_delta["left"] == expected_per_fork
    assert fork_delta["right"] == expected_per_fork
    assert update["requests"][p.name][p.atp_wid] == float(desired[p.atp_wid])


def test_long_partial_run_monotonic_no_nan_mass_closes() -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e12 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e12,
        allocated_override=alloc,
    )

    prev_left = 0.0
    prev_right = 0.0
    ticks = 1000
    for _ in range(ticks):
        update = p.next_update(1.0, state)
        _apply_update(state, update, p)
        left = state["chromosome"]["fork_position_bp"]["left"]
        right = state["chromosome"]["fork_position_bp"]["right"]
        assert left >= prev_left
        assert right >= prev_right
        assert np.isfinite(left)
        assert np.isfinite(right)
        prev_left = left
        prev_right = right

    total_advance_bp = int(
        state["chromosome"]["fork_position_bp"]["left"] + state["chromosome"]["fork_position_bp"]["right"]
    )
    consumed_datp = int(round(1e12 - state["substrates"]["DATP"]))
    consumed_dctp = int(round(1e12 - state["substrates"]["DCTP"]))
    consumed_dgtp = int(round(1e12 - state["substrates"]["DGTP"]))
    consumed_dttp = int(round(1e12 - state["substrates"]["DTTP"]))
    consumed_atp = int(round(1e12 - state["substrates"]["ATP"]))

    assert consumed_datp >= 0
    assert consumed_dctp >= 0
    assert consumed_dgtp >= 0
    assert consumed_dttp >= 0
    assert consumed_atp >= 0

    # DNA synthesis consumes 2 nucleotides per bp advanced across both forks.
    assert consumed_datp + consumed_dctp + consumed_dgtp + consumed_dttp == 2 * total_advance_bp
    assert consumed_atp == total_advance_bp
