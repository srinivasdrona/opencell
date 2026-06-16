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


def _enzyme_counts(
    process: KarrCytokinesisProcess,
    overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    counts = {wid: 0.0 for wid in process.fixture_enzyme_wids}
    if overrides:
        counts.update({wid: float(value) for wid, value in overrides.items()})
    return counts


def _substrate_counts(
    process: KarrCytokinesisProcess,
    overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    counts = {wid: 0.0 for wid in process._substrate_wids}
    if overrides:
        counts.update({wid: float(value) for wid, value in overrides.items()})
    return counts


def _allocated_counts(
    process: KarrCytokinesisProcess,
    overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    counts = {process.gtp_wid: 0.0, process.water_wid: 0.0}
    if overrides:
        counts.update({wid: float(value) for wid, value in overrides.items()})
    return counts


def _base_state(
    process: KarrCytokinesisProcess,
    *,
    segregated: bool = True,
    segregation_progress: float | None = None,
    pinched_diameter: float | None = None,
    width: float | None = None,
    num_edges_one_straight: int = 0,
    num_edges_two_straight: int = 0,
    num_edges_two_bent: int = 0,
    num_residual_bent: int = 0,
    enzymes: dict[str, float] | None = None,
    bound_enzymes: dict[str, float] | None = None,
    substrates: dict[str, float] | None = None,
    allocated: dict[str, float] | None = None,
    division_progress: float | None = None,
    division_complete: bool = False,
    ftsz_ring_complete: bool = True,
    filament_length_nm: float | None = None,
) -> dict[str, Any]:
    width_value = float(width if width is not None else process.initial_width)
    pinched_value = float(
        pinched_diameter if pinched_diameter is not None else process.initial_pinched_diameter
    )
    filament_length_value = float(
        filament_length_nm if filament_length_nm is not None else process.default_filament_length_nm
    )
    num_edges = (
        0
        if pinched_value <= 0.0
        else process.calc_num_edges(
            pinched_diameter=pinched_value,
            filament_length_nm=filament_length_value,
        )
    )

    if division_progress is None:
        if process.initial_pinched_diameter <= 0.0:
            progress = 1.0 if pinched_value <= 0.0 else 0.0
        else:
            progress = 1.0 - (pinched_value / process.initial_pinched_diameter)
        division_progress = max(0.0, min(1.0, progress))

    if segregation_progress is None:
        segregation_progress = 1.0 if segregated else 0.0

    return {
        "cell": {
            "ftsz_ring_complete": bool(ftsz_ring_complete),
            "division_progress": float(division_progress),
            "division_complete": bool(division_complete),
        },
        "chromosome": {
            "segregation_progress": float(segregation_progress),
            "segregated": bool(segregated),
        },
        "geometry": {
            "width": width_value,
            "pinchedDiameter": pinched_value,
            "pinched": bool(pinched_value <= 0.0),
        },
        "ftsZRing": {
            "numEdges": int(num_edges),
            "numEdgesOneStraight": int(num_edges_one_straight),
            "numEdgesTwoStraight": int(num_edges_two_straight),
            "numEdgesTwoBent": int(num_edges_two_bent),
            "numResidualBent": int(num_residual_bent),
            "numFtsZSubunitsPerFilament": int(process.num_ftsz_subunits_per_filament),
            "filamentLengthInNm": filament_length_value,
        },
        "substrates": _substrate_counts(process, substrates),
        "enzymes": _enzyme_counts(process, enzymes),
        "boundEnzymes": _enzyme_counts(process, bound_enzymes),
        "requests": {
            process.name: {
                process.gtp_wid: 0.0,
                process.water_wid: 0.0,
            }
        },
        "substrates_allocated": {
            process.name: _allocated_counts(process, allocated),
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    if "cell" in update:
        if "division_progress" in update["cell"]:
            state["cell"]["division_progress"] = float(
                state["cell"].get("division_progress", 0.0) + float(update["cell"]["division_progress"])
            )
        if "division_complete" in update["cell"]:
            state["cell"]["division_complete"] = bool(update["cell"]["division_complete"])
        if "ftsz_ring_complete" in update["cell"]:
            state["cell"]["ftsz_ring_complete"] = bool(update["cell"]["ftsz_ring_complete"])

    if "chromosome" in update:
        state["chromosome"].update(update["chromosome"])

    if "geometry" in update:
        state["geometry"].update(update["geometry"])

    if "ftsZRing" in update:
        state["ftsZRing"].update(update["ftsZRing"])

    for port in ("substrates", "enzymes", "boundEnzymes"):
        for wid, delta in update.get(port, {}).items():
            state[port][wid] = float(state[port].get(wid, 0.0) + float(delta))

    if "requests" in update:
        state["requests"][list(update["requests"].keys())[0]].update(
            list(update["requests"].values())[0]
        )


def _total_ftsz_subunits(process: KarrCytokinesisProcess, state: dict[str, Any]) -> int:
    polymer_wids = (
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer],
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp_polymer],
    )
    monomer_wids = (
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp],
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp],
    )

    total = 0
    for wid in polymer_wids:
        total += process.num_ftsz_subunits_per_filament * (
            int(round(state["enzymes"].get(wid, 0.0))) + int(round(state["boundEnzymes"].get(wid, 0.0)))
        )
    for wid in monomer_wids:
        total += int(round(state["enzymes"].get(wid, 0.0))) + int(round(state["boundEnzymes"].get(wid, 0.0)))
    return total


def test_process_instantiates_with_faithful_surface() -> None:
    process = KarrCytokinesisProcess({})
    schema = process.ports_schema()

    assert process.name == "karr_cytokinesis"
    assert process.rate_filament_binding_membrane == pytest.approx(0.7)
    assert process.rate_filament_dissociation == pytest.approx(0.7)
    assert process.rate_ftsz_gtp_hydrolysis == pytest.approx(0.15)
    assert process.num_ftsz_subunits_per_filament == 9
    assert process.calc_num_edges(process.initial_pinched_diameter, process.default_filament_length_nm) == 22

    assert "geometry" in schema
    assert "ftsZRing" in schema
    assert "segregated" in schema["chromosome"]
    assert process.water_wid in schema["requests"][process.name]
    assert process.gtp_wid in schema["requests"][process.name]
    assert schema["cell"]["division_progress"]["_updater"] == "accumulate"
    assert schema["geometry"]["pinchedDiameter"]["_updater"] == "set"
    assert schema["ftsZRing"]["numEdgesTwoBent"]["_updater"] == "set"


def test_five_phase_cycle_collapses_one_tick_when_rates_are_one() -> None:
    process = KarrCytokinesisProcess(
        {
            "rate_filament_binding_membrane": 1.0,
            "rate_filament_dissociation": 1.0,
            "rate_ftsz_gtp_hydrolysis": 1.0,
        }
    )
    num_edges = process.calc_num_edges(process.initial_pinched_diameter, process.default_filament_length_nm)
    hydrolysis_cost = 2 * process.num_ftsz_subunits_per_filament * num_edges

    state = _base_state(
        process,
        segregated=True,
        enzymes={
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]: float(2 * num_edges),
        },
        substrates={
            process.water_wid: float(hydrolysis_cost),
            process.pi_wid: 0.0,
            process.hydrogen_wid: 0.0,
        },
        allocated={process.water_wid: float(hydrolysis_cost)},
    )

    update = process.next_update(1.0, state)
    _apply_update(state, update)

    assert state["ftsZRing"]["numEdgesOneStraight"] == 0
    assert state["ftsZRing"]["numEdgesTwoStraight"] == 0
    assert state["ftsZRing"]["numEdgesTwoBent"] == 0
    assert state["ftsZRing"]["numResidualBent"] == num_edges
    assert state["geometry"]["pinchedDiameter"] < process.initial_pinched_diameter
    assert 0.0 < state["cell"]["division_progress"] < 1.0

    assert update["substrates"][process.water_wid] == pytest.approx(-float(hydrolysis_cost))
    assert update["substrates"][process.pi_wid] == pytest.approx(float(hydrolysis_cost))
    assert update["substrates"][process.hydrogen_wid] == pytest.approx(float(hydrolysis_cost))
    assert update["enzymes"][process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]] == pytest.approx(
        -float(2 * num_edges)
    )
    assert update["enzymes"][process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp]] == pytest.approx(
        float(num_edges * process.num_ftsz_subunits_per_filament)
    )
    assert update["boundEnzymes"][
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp_polymer]
    ] == pytest.approx(float(num_edges))


def test_phase_three_unbinds_residual_bent_before_hydrolysis() -> None:
    process = KarrCytokinesisProcess(
        {
            "rate_filament_binding_membrane": 0.0,
            "rate_filament_dissociation": 1.0,
            "rate_ftsz_gtp_hydrolysis": 0.0,
        }
    )
    num_edges = process.calc_num_edges(process.initial_pinched_diameter, process.default_filament_length_nm)
    residual_bent = 3

    state = _base_state(
        process,
        segregated=True,
        num_edges_two_straight=num_edges,
        num_residual_bent=residual_bent,
        bound_enzymes={
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]: float(2 * num_edges),
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp_polymer]: float(residual_bent),
        },
    )

    update = process.next_update(1.0, state)
    _apply_update(state, update)

    assert state["ftsZRing"]["numResidualBent"] == 0
    assert state["ftsZRing"]["numEdgesTwoStraight"] == num_edges
    assert process.water_wid not in update.get("substrates", {})
    assert update["boundEnzymes"][
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp_polymer]
    ] == pytest.approx(-float(residual_bent))
    assert update["enzymes"][process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp]] == pytest.approx(
        float(residual_bent * process.num_ftsz_subunits_per_filament)
    )


def test_zero_rates_leave_ring_and_accounting_unchanged() -> None:
    process = KarrCytokinesisProcess(
        {
            "rate_filament_binding_membrane": 0.0,
            "rate_filament_dissociation": 0.0,
            "rate_ftsz_gtp_hydrolysis": 0.0,
        }
    )
    num_edges = process.calc_num_edges(process.initial_pinched_diameter, process.default_filament_length_nm)
    hydrolysis_cost = 2 * process.num_ftsz_subunits_per_filament * num_edges

    state = _base_state(
        process,
        segregated=True,
        num_edges_two_straight=num_edges,
        bound_enzymes={
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]: float(2 * num_edges),
        },
        substrates={process.water_wid: float(hydrolysis_cost)},
        allocated={process.water_wid: float(hydrolysis_cost)},
    )

    before = {
        "geometry": dict(state["geometry"]),
        "ftsZRing": dict(state["ftsZRing"]),
        "enzymes": dict(state["enzymes"]),
        "boundEnzymes": dict(state["boundEnzymes"]),
        "substrates": dict(state["substrates"]),
    }

    update = process.next_update(1.0, state)
    _apply_update(state, update)

    assert state["geometry"] == before["geometry"]
    assert state["ftsZRing"] == before["ftsZRing"]
    assert state["enzymes"] == before["enzymes"]
    assert state["boundEnzymes"] == before["boundEnzymes"]
    assert state["substrates"] == before["substrates"]
    assert "division_progress" not in update.get("cell", {})


def test_hydrolysis_stoichiometry_matches_karr_per_edge_cost() -> None:
    process = KarrCytokinesisProcess(
        {
            "rate_filament_binding_membrane": 0.0,
            "rate_filament_dissociation": 0.0,
            "rate_ftsz_gtp_hydrolysis": 1.0,
        }
    )
    num_edges = process.calc_num_edges(process.initial_pinched_diameter, process.default_filament_length_nm)
    hydrolysis_cost = 2 * process.num_ftsz_subunits_per_filament * num_edges

    state = _base_state(
        process,
        segregated=True,
        num_edges_two_straight=num_edges,
        bound_enzymes={
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]: float(2 * num_edges),
        },
        substrates={
            process.water_wid: float(hydrolysis_cost),
            process.pi_wid: 0.0,
            process.hydrogen_wid: 0.0,
        },
        allocated={process.water_wid: float(hydrolysis_cost)},
    )

    update = process.next_update(1.0, state)
    _apply_update(state, update)

    assert state["ftsZRing"]["numEdgesTwoStraight"] == 0
    assert state["ftsZRing"]["numEdgesTwoBent"] == num_edges
    assert state["ftsZRing"]["numResidualBent"] == 0
    assert update["substrates"][process.water_wid] == pytest.approx(-float(hydrolysis_cost))
    assert update["substrates"][process.pi_wid] == pytest.approx(float(hydrolysis_cost))
    assert update["substrates"][process.hydrogen_wid] == pytest.approx(float(hydrolysis_cost))
    assert update["boundEnzymes"][
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]
    ] == pytest.approx(-float(2 * num_edges))
    assert update["boundEnzymes"][
        process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp_polymer]
    ] == pytest.approx(float(2 * num_edges))


def test_total_ftsz_subunits_are_conserved_across_many_ticks() -> None:
    process = KarrCytokinesisProcess(
        {
            "rate_filament_binding_membrane": 1.0,
            "rate_filament_dissociation": 1.0,
            "rate_ftsz_gtp_hydrolysis": 1.0,
        }
    )
    state = _base_state(
        process,
        segregated=True,
        enzymes={
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]: 10_000.0,
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp]: 3.0,
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp]: 6.0,
        },
        substrates={process.water_wid: 1_000_000.0},
        allocated={process.water_wid: 1_000_000.0},
    )

    conserved_before = _total_ftsz_subunits(process, state)
    cycles = process.calc_required_pinching_cycles(
        process.initial_pinched_diameter,
        process.default_filament_length_nm,
    )

    for _ in range(cycles):
        update = process.next_update(1.0, state)
        _apply_update(state, update)
        assert _total_ftsz_subunits(process, state) == conserved_before


def test_division_completes_when_pinched_diameter_reaches_zero() -> None:
    process = KarrCytokinesisProcess(
        {
            "rate_filament_binding_membrane": 1.0,
            "rate_filament_dissociation": 1.0,
            "rate_ftsz_gtp_hydrolysis": 1.0,
        }
    )
    cycles = process.calc_required_pinching_cycles(
        process.initial_pinched_diameter,
        process.default_filament_length_nm,
    )
    state = _base_state(
        process,
        segregated=True,
        enzymes={
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]: 10_000.0,
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp]: 3.0,
            process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp]: 6.0,
        },
        substrates={process.water_wid: 1_000_000.0},
        allocated={process.water_wid: 1_000_000.0},
    )

    for _ in range(cycles - 1):
        update = process.next_update(1.0, state)
        _apply_update(state, update)

    assert state["cell"]["division_complete"] is False
    assert state["geometry"]["pinchedDiameter"] > 0.0

    update = process.next_update(1.0, state)
    _apply_update(state, update)

    assert state["cell"]["division_complete"] is True
    assert state["geometry"]["pinchedDiameter"] == pytest.approx(0.0)
    assert state["geometry"]["pinched"] is True
    assert state["cell"]["division_progress"] == pytest.approx(1.0)
    assert math.isclose(
        state["geometry"]["pinchedDiameter"],
        0.0,
        abs_tol=1.0e-12,
    )
