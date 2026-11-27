from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from vivarium.core.engine import Engine

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

from opencell.state.chromosome_store import SparseTriplet
from opencell.vivarium.karr_allocation_step import KarrAllocationStep
from opencell.vivarium.karr_chromosome_segregation import (
    KarrChromosomeSegregationEvolutionStep,
    KarrChromosomeSegregationProcess,
)

# Real linkingNumbers values pulled from the tick-99 anchor trace
# (data/m1_sources/karr_native/per_process_traces_v2_event_s000/
# ChromosomeSegregation_100ticks.mat), one per strand 0-3 at position 0,
# each spanning the full chromosome length -- i.e. the fully-replicated,
# fully-supercoiled state that gates a genuine Karr segregation completion.
_FULLY_SUPERCOILED_LINKING_VALUES = (52013, 52013, 52026, 52026)


def _full_polymerized_regions(process: KarrChromosomeSegregationProcess) -> dict[str, Any]:
    length = process.sequence_len
    return {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": [length, length, length, length],
        "shape": process.chromosome_shape,
    }


def _partial_polymerized_regions(process: KarrChromosomeSegregationProcess) -> dict[str, Any]:
    length = process.sequence_len
    return {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": [length, length, length, length - 1],
        "shape": process.chromosome_shape,
    }


def _fully_supercoiled_linking_numbers(process: KarrChromosomeSegregationProcess) -> dict[str, Any]:
    return {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": list(_FULLY_SUPERCOILED_LINKING_VALUES),
        "shape": process.chromosome_shape,
    }


def _not_supercoiled_linking_numbers(process: KarrChromosomeSegregationProcess) -> dict[str, Any]:
    # Sigma = (lk - lk0) / lk0 must land far outside
    # [equilibrium - tolerance, equilibrium + tolerance] = [-0.16, 0.04].
    # A relaxed linking number (lk == lk0, sigma == 0.0) is actually WITHIN
    # that band, so use a strongly overwound value (sigma ~= +0.5) instead.
    length = process.sequence_len
    lk0 = length / process.relaxed_bases_per_turn
    overwound = round(lk0 * 1.5)
    return {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": [overwound, overwound, overwound, overwound],
        "shape": process.chromosome_shape,
    }


def _base_state(
    process: KarrChromosomeSegregationProcess,
    *,
    segregated: bool = False,
    polymerized: dict[str, Any] | None = None,
    linking: dict[str, Any] | None = None,
    enzyme_count: float = 10.0,
    gtp: float = 10.0,
    h2o: float = 10.0,
) -> dict[str, Any]:
    protein_counts = {wid: float(enzyme_count) for wid in process.monomer_enzyme_wids}
    complex_counts = {wid: float(enzyme_count) for wid in process.complex_enzyme_wids}

    return {
        "chromosome": {
            "segregated": segregated,
            "polymerizedRegions": (
                _full_polymerized_regions(process) if polymerized is None else polymerized
            ),
            "linkingNumbers": (
                _fully_supercoiled_linking_numbers(process) if linking is None else linking
            ),
        },
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        "substrates_allocated": {process.name: {process.gtp_wid: gtp, process.h2o_wid: h2o}},
    }


def _evolution_step(
    process: KarrChromosomeSegregationProcess,
) -> KarrChromosomeSegregationEvolutionStep:
    return KarrChromosomeSegregationEvolutionStep({"segregation_process": process})


def _build_production_phase_engine(
    process: KarrChromosomeSegregationProcess,
    *,
    gtp_pool: float,
    h2o_pool: float,
) -> Engine:
    evolution = _evolution_step(process)
    allocation = KarrAllocationStep(
        {
            "consumer_processes": [(process.name, [process.gtp_wid, process.h2o_wid])],
            "substrate_wids": list(process.substrate_wids),
        }
    )
    state = _base_state(process, gtp=0.0, h2o=0.0)
    state["substrates"] = {wid: 0.0 for wid in process.substrate_wids}
    state["substrates"][process.gtp_wid] = gtp_pool
    state["substrates"][process.h2o_wid] = h2o_pool
    state["requests"] = {
        process.name: {
            process.gtp_wid: 0.0,
            process.h2o_wid: 0.0,
        }
    }

    return Engine(
        processes={process.name: process},
        steps={
            allocation.name: allocation,
            evolution.name: evolution,
        },
        flow={
            allocation.name: [],
            evolution.name: [(allocation.name,)],
        },
        topology={
            process.name: {
                "chromosome": ("chromosome",),
                "protein": ("protein",),
                "complex": ("complex",),
                "requests": ("requests",),
            },
            allocation.name: {
                "substrates": ("substrates",),
                "requests": ("requests",),
                "substrates_allocated": ("substrates_allocated",),
            },
            evolution.name: {
                "chromosome": ("chromosome",),
                "protein": ("protein",),
                "complex": ("complex",),
                "substrates": ("substrates",),
                "substrates_allocated": ("substrates_allocated",),
            },
        },
        initial_state=state,
        emit_step=1.0,
        display_info=False,
    )


def test_instantiates_with_expected_defaults() -> None:
    p = KarrChromosomeSegregationProcess({"time_step": 1.0})
    assert p.name == "karr_chromosome_segregation"
    assert p.gtp_wid == "GTP"
    assert p.h2o_wid == "H2O"
    assert p.gtp_cost == pytest.approx(1.0)
    # Literal Karr gate requires all 5 fixture enzymes, unconditionally
    # (ChromosomeSegregation.m `all(this.enzymes)`), including topoisomerase
    # IV (MG_203_204_TETRAMER) -- no longer an optional gate.
    assert len(p.required_enzyme_wids) == 5
    assert p.topoiv_wid in p.required_enzyme_wids


def test_request_and_evolution_surfaces_are_split_without_duplicate_enzyme_ports() -> None:
    p = KarrChromosomeSegregationProcess({})
    request_ports = p.ports_schema()
    evolution_ports = p.evolution_ports_schema()

    assert "linkingNumbers" not in request_ports["chromosome"]
    assert "substrates" not in request_ports
    assert "substrates_allocated" not in request_ports
    assert "linkingNumbers" in evolution_ports["chromosome"]
    assert "requests" not in evolution_ports
    for ports in (request_ports, evolution_ports):
        assert "enzymes" not in ports
        assert "boundEnzymes" not in ports


def test_request_helper_does_not_mutate_state() -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, gtp=0.0, h2o=0.0)
    before = deepcopy(state)

    assert p.calculate_request(state) == {
        p.gtp_wid: p.gtp_cost,
        p.h2o_wid: p.gtp_cost,
    }
    assert state == before


def test_fires_and_applies_exact_stoichiometry_when_all_gates_open() -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, gtp=1.0, h2o=1.0)

    request_update = p.next_update(1.0, state)
    update = _evolution_step(p).next_update(1.0, state)

    assert request_update["requests"][p.name] == {p.gtp_wid: 1.0, p.h2o_wid: 1.0}
    assert update["chromosome"]["segregated"] is True
    assert update["chromosome"]["segregation_complete"] is True
    assert update["chromosome"]["cell_cycle_event"] == "segregation_complete"
    assert update["chromosome"]["segregation_progress"] == pytest.approx(1.0)
    assert update["chromosome"]["daughter_pole_positions"] == {"left": -1.0, "right": 1.0}
    # Exact Karr stoichiometry: GTP + H2O -> GDP + PI + H, gtpCost=1 each.
    assert update["substrates"] == {
        p.gtp_wid: -1.0,
        p.h2o_wid: -1.0,
        p.gdp_wid: 1.0,
        p.pi_wid: 1.0,
        p.h_wid: 1.0,
    }
    assert "requests" not in update


def test_already_segregated_is_a_no_op() -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, segregated=True, gtp=100.0, h2o=100.0)

    request_update = p.next_update(1.0, state)
    update = _evolution_step(p).next_update(1.0, state)

    assert "segregated" not in update["chromosome"]
    assert "substrates" not in update
    assert request_update["requests"][p.name] == {p.gtp_wid: 0.0, p.h2o_wid: 0.0}
    assert update["chromosome"]["cell_cycle_event"] == "none"


def test_not_fully_replicated_blocks_request_and_segregation() -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, polymerized=_partial_polymerized_regions(p), gtp=100.0, h2o=100.0)

    request_update = p.next_update(1.0, state)
    update = _evolution_step(p).next_update(1.0, state)

    assert "segregated" not in update["chromosome"]
    assert "substrates" not in update
    assert request_update["requests"][p.name] == {p.gtp_wid: 0.0, p.h2o_wid: 0.0}


def test_not_fully_supercoiled_blocks_segregation_but_not_request() -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, linking=_not_supercoiled_linking_numbers(p), gtp=100.0, h2o=100.0)

    request_update = p.next_update(1.0, state)
    update = _evolution_step(p).next_update(1.0, state)

    # calcResourceRequirements_Current does not gate on supercoiled -- Karr
    # still requests GTP/H2O -- but evolveState's extra supercoiled
    # requirement blocks the actual segregation event.
    assert request_update["requests"][p.name] == {p.gtp_wid: 1.0, p.h2o_wid: 1.0}
    assert "segregated" not in update["chromosome"]
    assert "substrates" not in update


@pytest.mark.parametrize(
    "missing_wid_attr",
    ["cobq_wid", "mraz_wid", "obg_wid", "era_wid", "topoiv_wid"],
)
def test_missing_each_enzyme_blocks_request_and_segregation(missing_wid_attr: str) -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, gtp=100.0, h2o=100.0)
    missing_wid = getattr(p, missing_wid_attr)
    if missing_wid in state["protein"]["counts"]:
        state["protein"]["counts"][missing_wid] = 0.0
    if missing_wid in state["complex"]["counts"]:
        state["complex"]["counts"][missing_wid] = 0.0

    request_update = p.next_update(1.0, state)
    update = _evolution_step(p).next_update(1.0, state)

    assert request_update["requests"][p.name] == {p.gtp_wid: 0.0, p.h2o_wid: 0.0}
    assert "segregated" not in update["chromosome"]
    assert "substrates" not in update


def test_missing_required_complex_input_raises_keyerror() -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, gtp=10.0, h2o=10.0)
    missing_wid = p.required_complex_enzyme_wids[0]
    state["complex"]["counts"].pop(missing_wid, None)

    with pytest.raises(KeyError, match=missing_wid):
        p.next_update(1.0, state)
    with pytest.raises(KeyError, match=missing_wid):
        _evolution_step(p).next_update(1.0, state)


@pytest.mark.parametrize("gtp,h2o", [(0.0, 10.0), (10.0, 0.0), (0.5, 0.5)])
def test_insufficient_allocated_gtp_or_h2o_blocks_segregation(gtp: float, h2o: float) -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, gtp=gtp, h2o=h2o)

    request_update = p.next_update(1.0, state)
    update = _evolution_step(p).next_update(1.0, state)

    # Request is still emitted (calcResourceRequirements_Current does not
    # gate on the substrates it is requesting), but evolveState's
    # `substrates(gtp) >= gtpCost && substrates(water) >= gtpCost` blocks.
    assert request_update["requests"][p.name] == {p.gtp_wid: 1.0, p.h2o_wid: 1.0}
    assert "segregated" not in update["chromosome"]
    assert "substrates" not in update


def test_fires_at_most_once_across_ticks() -> None:
    p = KarrChromosomeSegregationProcess({})
    state = _base_state(p, gtp=1.0, h2o=1.0)

    evolution = _evolution_step(p)
    update1 = evolution.next_update(1.0, state)
    assert update1["chromosome"]["segregated"] is True

    # Apply the segregated flag (as the real Engine/replay harness would)
    # and re-derive: the process must not fire again.
    state["chromosome"]["segregated"] = True
    update2 = evolution.next_update(1.0, state)
    assert "segregated" not in update2["chromosome"]
    assert "substrates" not in update2


def test_production_engine_fires_on_tick_one_with_exact_stoichiometry() -> None:
    p = KarrChromosomeSegregationProcess({})
    engine = _build_production_phase_engine(p, gtp_pool=p.gtp_cost, h2o_pool=p.gtp_cost)
    before = deepcopy(engine.state.get_value())

    engine.update(1.0)
    after = engine.state.get_value()

    assert before["chromosome"]["segregated"] is False
    assert after["chromosome"]["segregated"] is True
    assert after["requests"][p.name] == {
        p.gtp_wid: p.gtp_cost,
        p.h2o_wid: p.gtp_cost,
    }
    assert after["substrates_allocated"][p.name] == {
        p.gtp_wid: p.gtp_cost,
        p.h2o_wid: p.gtp_cost,
    }
    expected_deltas = {
        p.gtp_wid: -p.gtp_cost,
        p.h2o_wid: -p.gtp_cost,
        p.gdp_wid: p.gtp_cost,
        p.pi_wid: p.gtp_cost,
        p.h_wid: p.gtp_cost,
    }
    assert {
        wid: after["substrates"][wid] - before["substrates"][wid]
        for wid in expected_deltas
    } == expected_deltas


def test_production_engine_insufficient_allocation_is_no_op() -> None:
    p = KarrChromosomeSegregationProcess({})
    engine = _build_production_phase_engine(p, gtp_pool=0.0, h2o_pool=p.gtp_cost)
    before = deepcopy(engine.state.get_value())

    engine.update(1.0)
    after = engine.state.get_value()

    assert after["requests"][p.name] == {
        p.gtp_wid: p.gtp_cost,
        p.h2o_wid: p.gtp_cost,
    }
    assert after["substrates_allocated"][p.name][p.gtp_wid] == 0.0
    assert after["chromosome"]["segregated"] is False
    assert {
        wid: after["substrates"][wid] - before["substrates"][wid]
        for wid in p.substrate_wids
    } == {wid: 0.0 for wid in p.substrate_wids}


def test_production_engine_executes_transition_only_once() -> None:
    p = KarrChromosomeSegregationProcess({})
    engine = _build_production_phase_engine(
        p,
        gtp_pool=2.0 * p.gtp_cost,
        h2o_pool=2.0 * p.gtp_cost,
    )

    engine.update(1.0)
    after_tick_one = deepcopy(engine.state.get_value())
    engine.update(1.0)
    after_tick_two = engine.state.get_value()

    assert after_tick_one["chromosome"]["segregated"] is True
    assert after_tick_two["chromosome"]["segregated"] is True
    assert after_tick_two["requests"][p.name] == {
        p.gtp_wid: 0.0,
        p.h2o_wid: 0.0,
    }
    assert {
        wid: after_tick_two["substrates"][wid] - after_tick_one["substrates"][wid]
        for wid in p.substrate_wids
    } == {wid: 0.0 for wid in p.substrate_wids}


def test_double_stranded_region_helper_matches_direct_algebra() -> None:
    """Cross-check the double-stranded-region + supercoiled derivation
    against a hand-computed sigma for the real tick-99 anchor values."""
    from opencell.vivarium.karr_chromosome_segregation import _supercoiled_pass_count

    p = KarrChromosomeSegregationProcess({})
    polymerized = SparseTriplet.from_state(_full_polymerized_regions(p), shape=p.chromosome_shape)
    linking = SparseTriplet.from_state(
        _fully_supercoiled_linking_numbers(p), shape=p.chromosome_shape
    )

    pass_count = _supercoiled_pass_count(
        polymerized=polymerized,
        linking=linking,
        bp_per_turn=p.relaxed_bases_per_turn,
        equilibrium_sigma=p.equilibrium_superhelical_density,
        tolerance=p.supercoiled_tolerance,
    )
    assert pass_count == p.n_compartments

    lk0 = p.sequence_len / p.relaxed_bases_per_turn
    for lk in _FULLY_SUPERCOILED_LINKING_VALUES:
        sigma = (lk - lk0) / lk0
        assert abs(sigma - p.equilibrium_superhelical_density) < p.supercoiled_tolerance
