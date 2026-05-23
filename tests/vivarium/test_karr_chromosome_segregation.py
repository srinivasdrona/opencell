from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
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

from opencell.vivarium.karr_chromosome_segregation import KarrChromosomeSegregationProcess


def _base_state(
    process: KarrChromosomeSegregationProcess,
    *,
    replication_state: str = "complete",
    supercoiled: bool = True,
    progress: float = 0.0,
    gtp: float = 10.0,
    h2o: float = 10.0,
    enzyme_count: float = 2.0,
) -> dict[str, Any]:
    protein_counts = {wid: 0.0 for wid in process.enzyme_wids}
    for wid in process.required_enzyme_wids:
        protein_counts[wid] = float(enzyme_count)

    return {
        "chromosome": {
            "replication_state": replication_state,
            "supercoiled": supercoiled,
            "segregation_progress": float(progress),
            "daughter_pole_positions": {"left": float(-progress), "right": float(progress)},
            "segregation_complete": False,
            "cell_cycle_event": "none",
        },
        "protein": {"counts": protein_counts},
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "requests": {process.name: {process.gtp_wid: 0.0, process.h2o_wid: 0.0}},
        "substrates_allocated": {
            process.name: {process.gtp_wid: float(gtp), process.h2o_wid: float(h2o)}
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    chrom = update.get("chromosome", {})
    if "segregation_progress" in chrom:
        state["chromosome"]["segregation_progress"] = float(
            state["chromosome"]["segregation_progress"] + float(chrom["segregation_progress"])
        )
    if "daughter_pole_positions" in chrom:
        for side, delta in chrom["daughter_pole_positions"].items():
            state["chromosome"]["daughter_pole_positions"][side] = float(
                state["chromosome"]["daughter_pole_positions"][side] + float(delta)
            )
    if "segregation_complete" in chrom:
        state["chromosome"]["segregation_complete"] = bool(chrom["segregation_complete"])
    if "cell_cycle_event" in chrom:
        state["chromosome"]["cell_cycle_event"] = str(chrom["cell_cycle_event"])

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))

    if "requests" in update:
        for wid, val in update["requests"][next(iter(update["requests"]))].items():
            state["requests"][next(iter(state["requests"]))][wid] = float(val)


def _resolve_trace_path() -> Path | None:
    rel = Path("data/m1_sources/karr_native/per_process_traces/ChromosomeSegregation_100ticks.mat")
    candidates = [
        _REPO_ROOT / rel,
        _REPO_ROOT.parents[1] / "opencell" / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _trace_mean_gtp_consumption_per_tick(trace_path: Path, gtp_index_zero_based: int) -> float:
    with h5py.File(trace_path, "r") as f:
        before_refs = f["states_before/substrates"]
        after_refs = f["states_after/substrates"]

        deltas: list[float] = []
        for tick in range(before_refs.shape[0]):
            before = np.asarray(f[before_refs[tick, 0]], dtype=np.float64).reshape(-1)
            after = np.asarray(f[after_refs[tick, 0]], dtype=np.float64).reshape(-1)
            deltas.append(float(after[gtp_index_zero_based] - before[gtp_index_zero_based]))

    consumed = [-d for d in deltas]
    return float(np.mean(consumed))


def test_instantiates_with_expected_defaults() -> None:
    p = KarrChromosomeSegregationProcess({"time_step": 1.0})
    assert p.name == "karr_chromosome_segregation"
    assert p.gtp_wid == "GTP"
    assert p.h2o_wid == "H2O"
    assert p.gtp_cost == pytest.approx(1.0)
    assert len(p.required_enzyme_wids) == 4


def test_one_tick_gated_run_advances_and_consumes_gtp() -> None:
    p = KarrChromosomeSegregationProcess({"segregation_rate_per_s": 0.2})
    state = _base_state(p, replication_state="complete", supercoiled=True, gtp=4.0, h2o=4.0)

    update = p.next_update(1.0, state)
    _apply_update(state, update)

    assert update["chromosome"]["segregation_progress"] == pytest.approx(0.2)
    assert update["substrates"][p.gtp_wid] == pytest.approx(-1.0)
    assert update["substrates"][p.gdp_wid] == pytest.approx(1.0)
    assert state["chromosome"]["daughter_pole_positions"]["left"] == pytest.approx(-0.2)
    assert state["chromosome"]["daughter_pole_positions"]["right"] == pytest.approx(0.2)


def test_no_progress_when_replication_not_complete() -> None:
    p = KarrChromosomeSegregationProcess({"segregation_rate_per_s": 0.5})
    state = _base_state(p, replication_state="elongating", supercoiled=True, gtp=10.0, h2o=10.0)

    update = p.next_update(1.0, state)
    assert "substrates" not in update
    assert "segregation_progress" not in update["chromosome"]
    assert update["chromosome"]["cell_cycle_event"] == "none"
    assert update["requests"][p.name][p.gtp_wid] == pytest.approx(0.0)


def test_allocation_contract_bounds_progress() -> None:
    p = KarrChromosomeSegregationProcess({"segregation_rate_per_s": 0.3})
    state = _base_state(p, replication_state="complete", supercoiled=True, gtp=0.0, h2o=10.0)

    update = p.next_update(1.0, state)
    assert "substrates" not in update
    assert "segregation_progress" not in update["chromosome"]
    assert update["requests"][p.name][p.gtp_wid] == pytest.approx(1.0)

    state["substrates_allocated"][p.name][p.gtp_wid] = 1.0
    update2 = p.next_update(1.0, state)
    assert update2["chromosome"]["segregation_progress"] > 0.0
    assert update2["substrates"][p.gtp_wid] == pytest.approx(-1.0)


def test_completion_emits_event_and_clamps_progress() -> None:
    p = KarrChromosomeSegregationProcess({"segregation_rate_per_s": 1.0})
    state = _base_state(
        p,
        replication_state="complete",
        supercoiled=True,
        progress=0.95,
        gtp=3.0,
        h2o=3.0,
    )

    update = p.next_update(1.0, state)
    _apply_update(state, update)
    assert state["chromosome"]["segregation_progress"] == pytest.approx(1.0)
    assert state["chromosome"]["segregation_complete"] is True
    assert state["chromosome"]["cell_cycle_event"] == "segregation_complete"

    update2 = p.next_update(1.0, state)
    assert update2["chromosome"]["cell_cycle_event"] == "none"
    assert "segregation_progress" not in update2["chromosome"]


def test_100_tick_default_behavior_matches_trace_rate_within_10_percent() -> None:
    p = KarrChromosomeSegregationProcess({})
    trace_path = _resolve_trace_path()
    if trace_path is None:
        pytest.skip("ChromosomeSegregation 100-tick trace is unavailable in this checkout")

    trace_mean_gtp_consumed = _trace_mean_gtp_consumption_per_tick(trace_path, p.substrate_index_gtp)
    # Karr snapshot trace is expected to be flat under default gates.
    state = _base_state(
        p,
        replication_state="elongating",
        supercoiled=True,
        progress=0.0,
        gtp=10.0,
        h2o=10.0,
    )
    progress_deltas: list[float] = []
    for _ in range(100):
        update = p.next_update(1.0, state)
        progress_deltas.append(float(update.get("chromosome", {}).get("segregation_progress", 0.0)))
        _apply_update(state, update)

    mean_progress_rate = float(np.mean(progress_deltas))
    # If the trace rate is effectively zero, enforce a small absolute tolerance band.
    if abs(trace_mean_gtp_consumed) < 1e-12:
        assert abs(mean_progress_rate) <= 0.1
    else:
        rel_err = abs(mean_progress_rate - trace_mean_gtp_consumed) / abs(trace_mean_gtp_consumed)
        assert rel_err <= 0.10


def test_no_nan_or_negative_regression_on_state_outputs() -> None:
    p = KarrChromosomeSegregationProcess({"segregation_rate_per_s": 0.25})
    state = _base_state(p, replication_state="complete", supercoiled=True, gtp=200.0, h2o=200.0)

    for _ in range(100):
        update = p.next_update(1.0, state)
        _apply_update(state, update)

        progress = float(state["chromosome"]["segregation_progress"])
        left = float(state["chromosome"]["daughter_pole_positions"]["left"])
        right = float(state["chromosome"]["daughter_pole_positions"]["right"])

        assert not math.isnan(progress)
        assert not math.isnan(left)
        assert not math.isnan(right)
        assert progress >= 0.0
        assert progress <= 1.0
        assert left <= 0.0
        assert right >= 0.0
