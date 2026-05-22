from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from vivarium.core.engine import Engine
from vivarium.core.process import Process
from vivarium.core.process import Step

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

from opencell.vivarium.karr_allocation_step import KarrAllocationStep
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess
from opencell.vivarium.karr_request_calculators import RequestCalculatorRibAsm
from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess


def _build_state(
    process: KarrRibosomeAssemblyProcess,
    *,
    n_30s_capacity: int,
    n_50s_capacity: int,
    gtp_alloc: float,
    h2o_alloc: float,
) -> dict[str, Any]:
    idx_30s = process.complex_index_by_wid["RIBOSOME_30S"]
    idx_50s = process.complex_index_by_wid["RIBOSOME_50S"]

    rna_needed = (
        process.protein_complex_rna_composition[:, idx_30s] * int(n_30s_capacity)
        + process.protein_complex_rna_composition[:, idx_50s] * int(n_50s_capacity)
    )
    monomer_needed = (
        process.protein_complex_monomer_composition[:, idx_30s] * int(n_30s_capacity)
        + process.protein_complex_monomer_composition[:, idx_50s] * int(n_50s_capacity)
    )
    gtpase_needed = (
        process.complexation_catalysis[:, idx_30s] * int(n_30s_capacity)
        + process.complexation_catalysis[:, idx_50s] * int(n_50s_capacity)
    )

    protein_counts = {wid: 0.0 for wid in process.protein_state_wids}
    for i, wid in enumerate(process.monomer_subunit_wids):
        if monomer_needed[i] > 0:
            protein_counts[wid] = float(monomer_needed[i])
    for i, wid in enumerate(process.gtpase_wids):
        if gtpase_needed[i] > 0:
            protein_counts[wid] = max(protein_counts.get(wid, 0.0), float(gtpase_needed[i]))

    substrates = {wid: 0.0 for wid in process.substrate_wids}
    substrates[process.substrate_wid_gtp] = float(gtp_alloc)
    substrates[process.substrate_wid_h2o] = float(h2o_alloc)

    return {
        "substrates": substrates,
        "rna": {
            "counts": {
                wid: float(rna_needed[i]) for i, wid in enumerate(process.rna_subunit_wids)
            }
        },
        "protein": {"counts": protein_counts},
        "complex": {"counts": {wid: 0.0 for wid in process.complex_wids}},
        "requests": {
            process.name: {
                process.substrate_wid_gtp: 0.0,
                process.substrate_wid_h2o: 0.0,
            }
        },
        "substrates_allocated": {
            process.name: {
                process.substrate_wid_gtp: float(gtp_alloc),
                process.substrate_wid_h2o: float(h2o_alloc),
            }
        },
    }


def test_fixture_loads() -> None:
    p = KarrRibosomeAssemblyProcess({})
    assert p.name == "karr_ribosome_assembly"
    assert p.complex_wids == ["RIBOSOME_30S", "RIBOSOME_50S"]
    assert len(p.rna_subunit_wids) == 3
    assert len(p.monomer_subunit_wids) == 52
    assert len(p.gtpase_wids) == 6
    assert p.substrate_wids == ["GTP", "GDP", "PI", "H2O", "H"]
    assert p.n_gtpases_per_particle["RIBOSOME_30S"] == 2
    assert p.n_gtpases_per_particle["RIBOSOME_50S"] == 4
    assert p.gtpase_wids_by_name == {
        "EngA": "MG_329_MONOMER",
        "EngB": "MG_335_MONOMER",
        "Era": "MG_387_MONOMER",
        "Obg": "MG_384_MONOMER",
        "RbfA": "MG_143_MONOMER",
        "RbgA": "MG_442_MONOMER",
    }


def test_no_subunits_no_assembly() -> None:
    p = KarrRibosomeAssemblyProcess({})
    state = _build_state(p, n_30s_capacity=0, n_50s_capacity=0, gtp_alloc=100.0, h2o_alloc=100.0)
    update = p.next_update(1.0, state)
    assert update == {}


def test_no_gtp_no_assembly() -> None:
    p = KarrRibosomeAssemblyProcess({})
    state = _build_state(p, n_30s_capacity=1, n_50s_capacity=0, gtp_alloc=0.0, h2o_alloc=10.0)
    update = p.next_update(1.0, state)
    assert update == {}


def test_one_formation_consumes_gtp() -> None:
    p = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    state = _build_state(
        p,
        n_30s_capacity=1,
        n_50s_capacity=0,
        gtp_alloc=2.0,
        h2o_alloc=2.0,
    )
    update = p.next_update(1.0, state)

    assert update["complex"]["counts"] == {"RIBOSOME_30S": 1.0}
    assert update["substrates"][p.substrate_wid_gtp] == -2.0
    assert update["substrates"][p.substrate_wid_h2o] == -2.0


def test_gdp_pi_h_byproducts() -> None:
    p = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    state = _build_state(
        p,
        n_30s_capacity=0,
        n_50s_capacity=3,
        gtp_alloc=12.0,
        h2o_alloc=12.0,
    )
    update = p.next_update(1.0, state)

    assert update["complex"]["counts"] == {"RIBOSOME_50S": 3.0}
    assert update["substrates"][p.substrate_wid_gdp] == 12.0
    assert update["substrates"][p.substrate_wid_phosphate] == 12.0
    assert update["substrates"][p.substrate_wid_h] == 12.0


def test_randomization_changes_outcome() -> None:
    state_seed_30 = _build_state(
        KarrRibosomeAssemblyProcess({"rng_seed": 0}),
        n_30s_capacity=2,
        n_50s_capacity=1,
        gtp_alloc=4.0,
        h2o_alloc=4.0,
    )
    p_30_first = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    update_30_first = p_30_first.next_update(1.0, state_seed_30)

    state_seed_50 = _build_state(
        KarrRibosomeAssemblyProcess({"rng_seed": 3}),
        n_30s_capacity=2,
        n_50s_capacity=1,
        gtp_alloc=4.0,
        h2o_alloc=4.0,
    )
    p_50_first = KarrRibosomeAssemblyProcess({"rng_seed": 3})
    update_50_first = p_50_first.next_update(1.0, state_seed_50)

    assert update_30_first["complex"]["counts"] == {"RIBOSOME_30S": 2.0}
    assert update_50_first["complex"]["counts"] == {"RIBOSOME_50S": 1.0}
    assert update_30_first["substrates"]["GTP"] == update_50_first["substrates"]["GTP"] == -4.0


def test_mass_conservation() -> None:
    p = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    state = _build_state(
        p,
        n_30s_capacity=3,
        n_50s_capacity=2,
        gtp_alloc=14.0,
        h2o_alloc=14.0,
    )
    update = p.next_update(1.0, state)

    formed = np.asarray(
        [int(update["complex"]["counts"].get(wid, 0.0)) for wid in p.complex_wids],
        dtype=np.int64,
    )
    expected_rna = -(p.protein_complex_rna_composition @ formed)
    expected_monomer = -(p.protein_complex_monomer_composition @ formed)
    hydrolysis = int(sum(
        int(formed[p.complex_index_by_wid[wid]]) * p.n_gtpases_per_particle[wid]
        for wid in p.complex_wids
    ))

    observed_rna = np.asarray(
        [int(update["rna"]["counts"].get(wid, 0.0)) for wid in p.rna_subunit_wids],
        dtype=np.int64,
    )
    observed_monomer = np.asarray(
        [int(update["protein"]["counts"].get(wid, 0.0)) for wid in p.monomer_subunit_wids],
        dtype=np.int64,
    )

    np.testing.assert_array_equal(observed_rna, expected_rna)
    np.testing.assert_array_equal(observed_monomer, expected_monomer)
    assert update["substrates"][p.substrate_wid_gtp] == float(-hydrolysis)
    assert update["substrates"][p.substrate_wid_h2o] == float(-hydrolysis)
    assert update["substrates"][p.substrate_wid_gdp] == float(hydrolysis)
    assert update["substrates"][p.substrate_wid_phosphate] == float(hydrolysis)
    assert update["substrates"][p.substrate_wid_h] == float(hydrolysis)


def test_integration_with_chassis_v3() -> None:
    pytest.importorskip("opencell.vivarium.karr_composite")

    class _TickDriver(Process):
        defaults = {"time_step": 1.0}

        def ports_schema(self) -> dict[str, Any]:
            return {"driver": {"_default": 0.0, "_updater": "set", "_emit": False}}

        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            del timestep, states
            return {}

    ribasm = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    request_calc = RequestCalculatorRibAsm({"ribasm_proc": ribasm})
    allocation = KarrAllocationStep({
        "consumer_processes": [(ribasm.name, [ribasm.substrate_wid_gtp, ribasm.substrate_wid_h2o])],
        "substrate_wids": list(ribasm.substrate_wids),
    })

    initial_state = _build_state(
        ribasm,
        n_30s_capacity=2,
        n_50s_capacity=1,
        gtp_alloc=100.0,
        h2o_alloc=100.0,
    )
    initial_state["substrates_allocated"][ribasm.name][ribasm.substrate_wid_gtp] = 0.0
    initial_state["substrates_allocated"][ribasm.name][ribasm.substrate_wid_h2o] = 0.0
    initial_state["requests"][ribasm.name][ribasm.substrate_wid_gtp] = 0.0
    initial_state["requests"][ribasm.name][ribasm.substrate_wid_h2o] = 0.0

    engine = Engine(
        processes={"tick_driver": _TickDriver(), ribasm.name: ribasm},
        steps={request_calc.name: request_calc, allocation.name: allocation},
        flow={
            request_calc.name: [],
            allocation.name: [(request_calc.name,)],
        },
        topology={
            "tick_driver": {"driver": ("driver",)},
            ribasm.name: {
                "substrates": ("substrates",),
                "rna": ("rna",),
                "protein": ("protein",),
                "complex": ("complex",),
                "requests": ("_internal_requests",),
                "substrates_allocated": ("substrates_allocated",),
            },
            request_calc.name: {
                "substrates": ("substrates",),
                "rna": ("rna",),
                "protein": ("protein",),
                "requests": ("requests",),
            },
            allocation.name: {
                "substrates": ("substrates",),
                "requests": ("requests",),
                "substrates_allocated": ("substrates_allocated",),
            },
        },
        initial_state=initial_state,
        emit_step=1.0,
        display_info=False,
    )
    engine.update(1.0)
    state = engine.state.get_value()
    formed_total = float(state["complex"]["counts"]["RIBOSOME_30S"]) + float(
        state["complex"]["counts"]["RIBOSOME_50S"]
    )
    assert formed_total > 0.0


def test_steady_state_ribosome_count() -> None:
    class _NullStep(Step):
        name = "null_step"

        def ports_schema(self) -> dict[str, Any]:
            return {}

        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            del timestep, states
            return {}

    ribasm = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    decay = ProteinDecayLightProcess({
        "rng_seed": 1,
        "complex_wid_filter": ["RIBOSOME_30S", "RIBOSOME_50S"],
        "complex_half_lives": {"RIBOSOME_30S": 400.0, "RIBOSOME_50S": 400.0},
        "consume_atp_h2o": False,
    })
    request_calc = RequestCalculatorRibAsm({"ribasm_proc": ribasm})
    allocation = KarrAllocationStep({
        "consumer_processes": [(ribasm.name, [ribasm.substrate_wid_gtp, ribasm.substrate_wid_h2o])],
        "substrate_wids": list(ribasm.substrate_wids),
    })

    initial_state = _build_state(
        ribasm,
        n_30s_capacity=200,
        n_50s_capacity=200,
        gtp_alloc=0.0,
        h2o_alloc=0.0,
    )
    initial_state["substrates"][ribasm.substrate_wid_gtp] = 1_000_000.0
    initial_state["substrates"][ribasm.substrate_wid_h2o] = 1_000_000.0

    engine = Engine(
        processes={
            ribasm.name: ribasm,
            decay.name: decay,
        },
        steps={
            request_calc.name: request_calc,
            allocation.name: allocation,
            "null_step": _NullStep(),
        },
        flow={
            request_calc.name: [],
            allocation.name: [(request_calc.name,)],
            "null_step": [(allocation.name,)],
        },
        topology={
            ribasm.name: {
                "substrates": ("substrates",),
                "rna": ("rna",),
                "protein": ("protein",),
                "complex": ("complex",),
                "requests": ("_internal_requests_ribasm",),
                "substrates_allocated": ("substrates_allocated",),
            },
            decay.name: {
                "complex": ("complex",),
                "substrates": ("substrates",),
                "protein": ("protein",),
                "rna": ("rna",),
                "requests": ("_internal_requests_decay",),
                "substrates_allocated": ("_internal_sub_alloc_decay",),
            },
            request_calc.name: {
                "substrates": ("substrates",),
                "rna": ("rna",),
                "protein": ("protein",),
                "requests": ("requests",),
            },
            allocation.name: {
                "substrates": ("substrates",),
                "requests": ("requests",),
                "substrates_allocated": ("substrates_allocated",),
            },
            "null_step": {},
        },
        initial_state=initial_state,
        emit_step=10.0,
        display_info=False,
    )
    engine.update(500.0)

    final_state = engine.state.get_value()
    total_ribosomes = float(final_state["complex"]["counts"]["RIBOSOME_30S"]) + float(
        final_state["complex"]["counts"]["RIBOSOME_50S"]
    )
    upper_bound = 400.0
    assert 0.0 < total_ribosomes <= upper_bound

    timeseries = engine.emitter.get_timeseries()
    series_30s = np.asarray(timeseries["complex"]["counts"]["RIBOSOME_30S"], dtype=np.float64)
    series_50s = np.asarray(timeseries["complex"]["counts"]["RIBOSOME_50S"], dtype=np.float64)
    tail_total = series_30s[-10:] + series_50s[-10:]
    assert np.all(np.isfinite(tail_total))
    assert float(np.mean(tail_total)) > 0.0
    assert float(np.max(tail_total)) <= upper_bound
