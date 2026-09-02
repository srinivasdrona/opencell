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

from opencell.vivarium.karr_chromosome_condensation import KarrChromosomeCondensationProcess


def _base_state(
    process: KarrChromosomeCondensationProcess,
    *,
    smc_bound_count: float,
    condensation_level: float,
    atp: float,
    h2o: float,
    replication_state: str = "idle",
    forks_passing: bool = False,
    allocated_atp: float | None = None,
    allocated_h2o: float | None = None,
) -> dict[str, Any]:
    state = {
        "chromosome": {
            "smc_bound_count": float(smc_bound_count),
            "condensation_level": float(condensation_level),
            "replication_state": replication_state,
            "forks_passing": forks_passing,
        },
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "requests": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
        "substrates_allocated": {
            process.name: {
                process.atp_wid: float(atp if allocated_atp is None else allocated_atp),
                process.water_wid: float(h2o if allocated_h2o is None else allocated_h2o),
            }
        },
    }
    state["substrates"][process.atp_wid] = float(atp)
    state["substrates"][process.water_wid] = float(h2o)
    return state


def _apply_update(
    process: KarrChromosomeCondensationProcess,
    state: dict[str, Any],
    update: dict[str, Any],
) -> None:
    for key, delta in update.get("chromosome", {}).items():
        if key not in state["chromosome"]:
            state["chromosome"][key] = 0.0
        state["chromosome"][key] = float(state["chromosome"][key] + float(delta))

    state["chromosome"]["smc_bound_count"] = max(0.0, float(state["chromosome"]["smc_bound_count"]))
    state["chromosome"]["condensation_level"] = float(
        min(1.0, max(0.0, state["chromosome"]["condensation_level"]))
    )

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))
        state["substrates"][wid] = max(0.0, state["substrates"][wid])

    # Mimic one allocator mode where next tick allocation sees current pools.
    alloc = state["substrates_allocated"][process.name]
    alloc[process.atp_wid] = float(state["substrates"].get(process.atp_wid, 0.0))
    alloc[process.water_wid] = float(state["substrates"].get(process.water_wid, 0.0))


def test_process_initializes_with_fixture_defaults() -> None:
    p = KarrChromosomeCondensationProcess({})
    assert p.name == "karr_chromosome_condensation"
    assert p.atp_wid == "ATP"
    assert p.water_wid == "H2O"
    assert p.adp_wid == "ADP"
    assert p.pi_wid == "PI"
    assert p.trace_anchor_bound > 0
    assert p.default_target_bound > 0
    assert 0.0 <= p.default_condensation_level <= 1.0


def test_replay_rng_starts_from_seeded_process_stream() -> None:
    p = KarrChromosomeCondensationProcess({"rng_seed": 0})
    # The replay/extraction path reseeds process streams after loading the
    # fitted simulation surface, so tick 0 must begin from the seeded
    # process stream (not any warmup-endpoint stream state).
    assert p._rng.get_state()["mcg_state"] == 931_316_785


def test_one_tick_binding_and_condensation_sign() -> None:
    p = KarrChromosomeCondensationProcess(
        {
            "rng_seed": 5,
            "binding_relaxation_time_s": 0.5,
            "trace_gap_tolerance_for_binding": 0.0,
            "fork_pause_probability": 0.0,
            "displacement_rate_per_s": 0.0,
        }
    )
    state = _base_state(
        p,
        smc_bound_count=0.0,
        condensation_level=0.0,
        atp=50_000.0,
        h2o=50_000.0,
    )
    update = p.next_update(1.0, state)
    smc_delta = float(update.get("chromosome", {}).get("smc_bound_count", 0.0))
    cond_delta = float(update.get("chromosome", {}).get("condensation_level", 0.0))

    assert smc_delta > 0.0
    assert cond_delta >= 0.0
    assert update["substrates"][p.atp_wid] == pytest.approx(-smc_delta)
    assert update["substrates"][p.water_wid] == pytest.approx(-smc_delta)


def test_allocation_contract_caps_binding() -> None:
    p = KarrChromosomeCondensationProcess(
        {
            "rng_seed": 7,
            "binding_relaxation_time_s": 1.0e-3,
            "trace_gap_tolerance_for_binding": 0.0,
            "fork_pause_probability": 0.0,
            "displacement_rate_per_s": 0.0,
        }
    )
    state = _base_state(
        p,
        smc_bound_count=0.0,
        condensation_level=0.0,
        atp=50_000.0,
        h2o=50_000.0,
        allocated_atp=1.0,
        allocated_h2o=1.0,
    )
    update = p.next_update(1.0, state)
    smc_delta = float(update.get("chromosome", {}).get("smc_bound_count", 0.0))

    assert smc_delta <= 1.0
    assert abs(float(update.get("substrates", {}).get(p.atp_wid, 0.0))) <= 1.0
    assert abs(float(update.get("substrates", {}).get(p.water_wid, 0.0))) <= 1.0


def test_100_tick_steady_state_matches_trace_anchor() -> None:
    p = KarrChromosomeCondensationProcess({"rng_seed": 0})
    state = _base_state(
        p,
        smc_bound_count=float(p.trace_anchor_bound),
        condensation_level=float(p.default_condensation_level),
        atp=36_234.0,
        h2o=3.09737899e8,
    )

    for _ in range(100):
        update = p.next_update(1.0, state)
        _apply_update(p, state, update)

    final_cond = float(state["chromosome"]["condensation_level"])
    atp_activity = 36_234.0 / (36_234.0 + float(p.parameters["atp_half_saturation"]))
    trace_ref = min(1.0, (float(p.trace_anchor_bound) / float(p.default_target_bound)) * atp_activity)
    rel_err = abs(final_cond - trace_ref) / max(1.0e-9, abs(trace_ref))
    assert rel_err <= 0.10


def test_no_nan_or_negative_regression_100_ticks() -> None:
    p = KarrChromosomeCondensationProcess(
        {
            "rng_seed": 12,
            "binding_relaxation_time_s": 2.0,
            "trace_gap_tolerance_for_binding": 0.0,
            "fork_pause_probability": 0.2,
            "displacement_rate_per_s": 1.0e-3,
        }
    )
    state = _base_state(
        p,
        smc_bound_count=10.0,
        condensation_level=0.2,
        atp=100_000.0,
        h2o=100_000.0,
    )

    for tick in range(100):
        state["chromosome"]["forks_passing"] = bool(tick % 7 == 0)
        state["chromosome"]["replication_state"] = "elongating" if tick % 5 == 0 else "idle"
        update = p.next_update(1.0, state)
        _apply_update(p, state, update)

        smc = float(state["chromosome"]["smc_bound_count"])
        cond = float(state["chromosome"]["condensation_level"])
        assert smc >= 0.0
        assert 0.0 <= cond <= 1.0
        assert math.isfinite(smc)
        assert math.isfinite(cond)
        for wid, count in state["substrates"].items():
            assert count >= 0.0, f"negative substrate {wid}: {count}"
            assert math.isfinite(count), f"non-finite substrate {wid}: {count}"


def test_replication_pause_reduces_binding() -> None:
    params = {
        "rng_seed": 19,
        "binding_relaxation_time_s": 0.5,
        "trace_gap_tolerance_for_binding": 0.0,
        "displacement_rate_per_s": 0.0,
    }
    p_idle = KarrChromosomeCondensationProcess({**params, "fork_pause_probability": 0.0})
    p_paused = KarrChromosomeCondensationProcess({**params, "fork_pause_probability": 1.0})

    idle_state = _base_state(
        p_idle,
        smc_bound_count=0.0,
        condensation_level=0.0,
        atp=50_000.0,
        h2o=50_000.0,
        replication_state="idle",
        forks_passing=False,
    )
    paused_state = _base_state(
        p_paused,
        smc_bound_count=0.0,
        condensation_level=0.0,
        atp=50_000.0,
        h2o=50_000.0,
        replication_state="elongating",
        forks_passing=True,
    )

    idle_update = p_idle.next_update(1.0, idle_state)
    paused_update = p_paused.next_update(1.0, paused_state)
    idle_delta = float(idle_update.get("chromosome", {}).get("smc_bound_count", 0.0))
    paused_delta = float(paused_update.get("chromosome", {}).get("smc_bound_count", 0.0))
    assert idle_delta >= paused_delta
