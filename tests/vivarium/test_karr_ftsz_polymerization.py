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

from opencell.vivarium.karr_ftsz_polymerization import KarrFtsZPolymerizationProcess

_TRACE_PATH = Path(
    "/mnt/e/opencell/data/m1_sources/karr_native/per_process_traces/"
    "FtsZPolymerization_100ticks.mat"
)


def _base_state(
    process: KarrFtsZPolymerizationProcess,
    *,
    allocated_gtp: float,
    substrate_gtp: float = 1_000_000.0,
) -> dict[str, Any]:
    substrates = {wid: 1_000_000.0 for wid in process.substrate_wids}
    substrates[process.gtp_wid] = float(substrate_gtp)
    return {
        "cell": {
            "ftsz_ring_count": float(process.initial_ring_count),
            "ftsz_ring_complete": bool(
                process.initial_ring_count >= int(process.parameters["ring_complete_threshold"])
            ),
        },
        "substrates": substrates,
        "requests": {process.name: {process.gtp_wid: 0.0}},
        "substrates_allocated": {process.name: {process.gtp_wid: float(allocated_gtp)}},
    }


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
    process: KarrFtsZPolymerizationProcess,
) -> None:
    if "cell" in update and "ftsz_ring_count" in update["cell"]:
        state["cell"]["ftsz_ring_count"] = float(
            state["cell"]["ftsz_ring_count"] + float(update["cell"]["ftsz_ring_count"])
        )
    if "cell" in update and "ftsz_ring_complete" in update["cell"]:
        state["cell"]["ftsz_ring_complete"] = bool(update["cell"]["ftsz_ring_complete"])

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))

    req = update.get("requests", {}).get(process.name, {})
    if process.gtp_wid in req:
        state["requests"][process.name][process.gtp_wid] = float(req[process.gtp_wid])


def _trace_ring_tail_mean() -> float:
    if not _TRACE_PATH.exists():
        pytest.skip(f"Karr trace not available: {_TRACE_PATH}")

    with h5py.File(_TRACE_PATH, "r") as handle:
        ds = handle["states_after/enzymes"]
        ring_values: list[float] = []
        lengths = np.arange(2, 10, dtype=np.float64)
        for tick in range(ds.shape[0]):
            ref = ds[tick, 0]
            enzymes = np.asarray(handle[ref][()]).reshape(-1).astype(np.float64)
            ring_values.append(float(np.dot(enzymes[3:11], lengths)))
    tail = np.asarray(ring_values[-20:], dtype=np.float64)
    return float(np.mean(tail))


def test_fixture_loads() -> None:
    process = KarrFtsZPolymerizationProcess({})
    assert process.name == "karr_ftsz_polymerization"
    assert process.gtp_wid == "GTP"
    assert len(process.enzyme_wids) == 11
    assert process.initial_ring_count > 0
    assert process.parameters["ring_complete_threshold"] > 0


def test_integration_with_chassis_v4() -> None:
    pytest.importorskip("opencell.vivarium.karr_composite")
    from opencell.vivarium.karr_composite import build_karr_chassis_v4

    engine = build_karr_chassis_v4(time_step_s=1.0, emit_step_s=1.0)
    assert "karr_ftsz_polymerization" in engine.processes
    state = engine.state.get_value()
    assert "cell" in state
    assert "ftsz_ring_count" in state["cell"]
    assert "ftsz_ring_complete" in state["cell"]


def test_one_tick_growth_biased_ring_delta_positive() -> None:
    process = KarrFtsZPolymerizationProcess(
        {
            "rng_seed": 5,
            "nucleation_forward_scale": 8.0e6,
            "elongation_forward_scale": 6.0e7,
            "nucleation_reverse_scale": 1.0e12,
            "elongation_reverse_scale": 1.0e12,
            "deactivation_rate_scale": 1.0e12,
            "homeostasis_strength": 0.0,
        }
    )
    state = _base_state(process, allocated_gtp=50_000.0)
    update = process.next_update(1.0, state)

    assert float(update["requests"][process.name][process.gtp_wid]) >= 0.0
    ring_delta = float(update.get("cell", {}).get("ftsz_ring_count", 0.0))
    assert ring_delta > 0.0


def test_allocation_contract_zero_alloc_no_gtp_consumption() -> None:
    process = KarrFtsZPolymerizationProcess({"rng_seed": 7})
    state = _base_state(process, allocated_gtp=0.0, substrate_gtp=1_000_000.0)
    update = process.next_update(1.0, state)
    assert update.get("substrates", {}).get(process.gtp_wid, 0.0) == pytest.approx(0.0)


def test_steady_state_ring_count_matches_trace_within_ten_percent() -> None:
    process = KarrFtsZPolymerizationProcess({"rng_seed": 11})
    state = _base_state(process, allocated_gtp=5_000.0, substrate_gtp=1_000_000.0)

    for _ in range(100):
        state["substrates_allocated"][process.name][process.gtp_wid] = 5_000.0
        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

    observed = float(state["cell"]["ftsz_ring_count"])
    trace_target = _trace_ring_tail_mean()
    rel_err = abs(observed - trace_target) / max(1.0, abs(trace_target))
    assert rel_err <= 0.10, f"observed={observed} target={trace_target} rel_err={rel_err}"


def test_no_nan_no_negative_regressions_over_100_ticks() -> None:
    process = KarrFtsZPolymerizationProcess({"rng_seed": 3})
    state = _base_state(process, allocated_gtp=2_000.0, substrate_gtp=1_000_000.0)

    for _ in range(100):
        state["substrates_allocated"][process.name][process.gtp_wid] = 2_000.0
        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

        assert math.isfinite(float(state["cell"]["ftsz_ring_count"]))
        assert float(state["cell"]["ftsz_ring_count"]) >= 0.0
        assert np.all(np.isfinite(process._species_counts))
        assert np.all(process._species_counts >= 0)

