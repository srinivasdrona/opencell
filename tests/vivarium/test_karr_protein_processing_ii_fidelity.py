"""PP2 pre-L2.5 production contracts, independent of replay output oracles.

Primary authority: ProteinProcessingII.m:180-268 (form/compartment routing),
325-345 (ceil/min requests), 348-445 (all-or-nothing two-phase evolution);
Process.m:611-670 (live mature enzyme reads). Parameters and WIDs below are
loaded independently from ProteinProcessingII_flat.mat. Small precursor,
substrate, and competing-demand interventions are explicitly synthetic,
not claims about default chassis event density or eligibility.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from functools import cache
from math import ceil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.io import loadmat
from vivarium.core.engine import Engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess
from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_request_calculators import RequestCalculatorProteinPathway
from opencell.vivarium.protein_state import COMPARTMENTS, MIGRATED_WIDS, initial_compartment_counts


@cache
def _source() -> Any:
    return loadmat(
        _REPO_ROOT / "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture


def _indices(field: str) -> np.ndarray:
    return np.atleast_1d(getattr(_source(), field)).astype(int) - 1


def _wid(index: int) -> str:
    return str(_source().unprocessedMonomerWholeCellModelIDs[index])


def _comp(index: int) -> str:
    return COMPARTMENTS[int(_source().monomerCompartments[index]) - 1]


def _sub(field: str) -> str:
    return str(_source().substrateWholeCellModelIDs[int(getattr(_source(), field)) - 1])


def _enzyme_comp(index: int) -> str:
    return COMPARTMENTS[int(_source().enzymeMonomerCompartmentIndexs[index]) - 1]


def _pair(dt: float | None = None) -> tuple[KarrProteinProcessingIIProcess, Any]:
    p = KarrProteinProcessingIIProcess(
        {"time_step": float(_source().stepSizeSec) if dt is None else dt, "rng_seed": 0}
    )
    calc = RequestCalculatorProteinPathway({
        "protein_processing_i_proc": KarrProteinProcessingIProcess({}),
        "protein_processing_ii_proc": p,
        "protein_modification_proc": KarrProteinModificationProcess({}),
        "protein_folding_proc": KarrProteinFoldingProcess({}),
        "protein_translocation_proc": KarrProteinTranslocationProcess({}),
    })
    return p, calc


def _state(supply: float = 1000.0) -> dict[str, Any]:
    fx = _source()
    enzyme_wids = [str(w) for w in fx.enzymeWholeCellModelIDs]
    enzyme_counts = dict(zip(enzyme_wids, map(float, fx.enzymes), strict=True))
    state = {
        "substrates": {str(w): supply for w in fx.substrateWholeCellModelIDs},
        "protein": {
            "counts": dict(enzyme_counts),
            "enzyme_counts": dict(enzyme_counts),
            "processed_counts": {},
            "unprocessed_counts": {},
            "unfolded_counts": {},
            "unmodified_counts": {},
            "signal_sequence_counts": {},
            "compartment_counts": initial_compartment_counts(),
        },
        "requests": {},
        "substrates_allocated": {},
    }
    for wid, comp, count in zip(
        enzyme_wids, fx.enzymeMonomerCompartmentIndexs, fx.enzymes, strict=True
    ):
        state["protein"]["compartment_counts"]["mature"][wid][COMPARTMENTS[int(comp) - 1]] = (
            float(count)
        )
    return state


def _precursor(state: dict[str, Any], index: int, count: float, *, mirror: bool = False) -> None:
    wid = _wid(index)
    if wid in MIGRATED_WIDS:
        state["protein"]["compartment_counts"]["processed_i"][wid][_comp(index)] = count
    else:
        state["protein"]["counts"][wid] = count
    if mirror:
        # Test-only legacy shadow, to isolate algebra from the separate authority defect.
        state["protein"]["processed_counts"][wid] = count


def _enzyme_values(state: dict[str, Any]) -> np.ndarray:
    fx = _source()
    mature = state["protein"]["compartment_counts"]["mature"]
    return np.asarray([
        mature[str(wid)][COMPARTMENTS[int(comp) - 1]]
        for wid, comp in zip(
            fx.enzymeWholeCellModelIDs, fx.enzymeMonomerCompartmentIndexs, strict=True
        )
    ])


def _expected_requests(state: dict[str, Any], dt: float) -> dict[str, float]:
    """Independent MATLAB algebra; never reads process helpers or states_after."""
    fx = _source()
    protein = state["protein"]
    pools = np.asarray([
        protein["compartment_counts"]["processed_i"][str(wid)][_comp(i)]
        if str(wid) in MIGRATED_WIDS else protein["counts"].get(str(wid), 0)
        for i, wid in enumerate(fx.unprocessedMonomerWholeCellModelIDs)
    ])
    enzymes = _enzyme_values(state)
    lipo = _indices("lipoproteinMonomerIndexs")
    secret = _indices("secretedMonomerIndexs")
    expected = {str(w): 0.0 for w in fx.substrateWholeCellModelIDs}
    expected[_sub("substrateIndexs_water")] = min(
        ceil(enzymes[int(fx.enzymeIndexs_signalPeptidase) - 1]
             * float(fx.lipoproteinSignalPeptidaseSpecificRate) * dt),
        float(pools[np.concatenate((lipo, secret))].sum()),
    )
    expected[_sub("substrateIndexs_PG160")] = min(
        ceil(enzymes[int(fx.enzymeIndexs_diacylglycerylTransferase) - 1]
             * float(fx.lipoproteinDiacylglycerylTransferaseSpecificRate) * dt),
        float(pools[lipo].sum()),
    )
    return expected


def _requests(calc: Any, state: dict[str, Any], p: Any) -> dict[str, float]:
    return calc.next_update(1.0, state)["requests"][p.name]


def _grant(state: dict[str, Any], p: Any, count: float) -> None:
    state["substrates_allocated"][p.name] = {str(w): count for w in _source().substrateWholeCellModelIDs}


def _transition(update: dict[str, Any], index: int, events: int) -> None:
    authority = update.get("protein", {}).get("compartment_counts", {})
    wid, comp = _wid(index), _comp(index)
    assert authority.get("processed_i", {}).get(wid, {}).get(comp, 0) == -events
    assert authority.get("processed_ii", {}).get(wid, {}).get(comp, 0) == events
    substrates = update.get("substrates", {})
    assert substrates.get(_sub("substrateIndexs_water"), 0) == -events
    if index in _indices("lipoproteinMonomerIndexs"):
        assert substrates.get(_sub("substrateIndexs_PG160"), 0) == -events
        assert substrates.get(_sub("substrateIndexs_SNGLYP"), 0) == events
        assert substrates.get(_sub("substrateIndexs_hydrogen"), 0) == events
    else:
        assert substrates.get(_sub("substrateIndexs_PG160"), 0) == 0


def test_fixture_parameter_and_source_compartment_alignment() -> None:
    p, _ = _pair()
    fx = _source()
    assert p.substrate_wids == list(map(str, fx.substrateWholeCellModelIDs))
    assert p.enzyme_wids == list(map(str, fx.enzymeWholeCellModelIDs))
    np.testing.assert_array_equal(p.lipoprotein_indices, _indices("lipoproteinMonomerIndexs"))
    np.testing.assert_array_equal(p.secreted_indices, _indices("secretedMonomerIndexs"))
    assert p.lipoprotein_signal_peptidase_specific_rate == float(fx.lipoproteinSignalPeptidaseSpecificRate)
    assert p.lipoprotein_diacylglyceryl_transferase_specific_rate == float(
        fx.lipoproteinDiacylglycerylTransferaseSpecificRate
    )
    for i, wid in enumerate(fx.unprocessedMonomerWholeCellModelIDs):
        if str(wid) in MIGRATED_WIDS:
            assert p.migrated_compartment_by_wid[str(wid)] == _comp(i)


@pytest.mark.parametrize("regime", [
    "enzyme_limited", "demand_limited", "fractional_ceil", "nonunit_step",
    "zero_enzymes", "zero_peptidase", "zero_transferase", "zero_demand", "secreted_only",
])
def test_requests_match_matlab_ceil_min_algebra(regime: str) -> None:
    fx = _source()
    dt = float(fx.stepSizeSec) * (0.25 if regime == "nonunit_step" else 1)
    p, calc = _pair(dt)
    state = _state()
    if regime == "fractional_ceil":
        # One transferase molecule has fractional fixture-derived capacity.
        enzyme_index = int(fx.enzymeIndexs_diacylglycerylTransferase) - 1
        wid = str(fx.enzymeWholeCellModelIDs[enzyme_index])
        state["protein"]["enzyme_counts"][wid] = 1
        state["protein"]["counts"][wid] = 1
        state["protein"]["compartment_counts"]["mature"][wid][_enzyme_comp(enzyme_index)] = 1
    if regime.startswith("zero_") and regime != "zero_demand":
        indices = range(len(fx.enzymeWholeCellModelIDs)) if regime == "zero_enzymes" else [
            int(fx.enzymeIndexs_signalPeptidase if regime == "zero_peptidase"
                else fx.enzymeIndexs_diacylglycerylTransferase) - 1
        ]
        for i in indices:
            wid = str(fx.enzymeWholeCellModelIDs[i])
            state["protein"]["enzyme_counts"][wid] = 0
            state["protein"]["counts"][wid] = 0
            state["protein"]["compartment_counts"]["mature"][wid][_enzyme_comp(i)] = 0
    lipo, secret = 2, 3  # Synthetic demand-limited intervention.
    if regime in {"enzyme_limited", "nonunit_step"}:
        lipo = ceil(float(fx.enzymes[int(fx.enzymeIndexs_diacylglycerylTransferase) - 1])
                    * float(fx.lipoproteinDiacylglycerylTransferaseSpecificRate) * dt) + 1
        secret = ceil(float(fx.enzymes[int(fx.enzymeIndexs_signalPeptidase) - 1])
                      * float(fx.lipoproteinSignalPeptidaseSpecificRate) * dt) + 1
    if regime == "zero_demand":
        lipo = secret = 0
    if regime == "secreted_only":
        lipo = 0
    _precursor(state, int(_indices("lipoproteinMonomerIndexs")[0]), lipo, mirror=True)
    _precursor(state, int(_indices("secretedMonomerIndexs")[0]), secret, mirror=True)
    assert _requests(calc, state, p) == _expected_requests(state, dt)


@pytest.mark.parametrize("supply", [0.0, 0.5, 10000.0], ids=["zero", "tiny", "huge"])
def test_requests_are_independent_of_shared_substrate_availability(supply: float) -> None:
    p, calc = _pair()
    state = _state(supply)
    _precursor(state, int(_indices("lipoproteinMonomerIndexs")[0]), 2, mirror=True)
    _precursor(state, int(_indices("secretedMonomerIndexs")[0]), 3, mirror=True)
    assert _requests(calc, state, p) == _expected_requests(state, float(_source().stepSizeSec))


def test_requests_sum_all_fixture_lipo_and_secreted_indices() -> None:
    p, calc = _pair()
    state = _state()
    for field in ("lipoproteinMonomerIndexs", "secretedMonomerIndexs"):
        for index in _indices(field):
            _precursor(state, int(index), 1, mirror=True)
    assert _requests(calc, state, p) == _expected_requests(state, float(_source().stepSizeSec))


def test_deterministic_requests_do_not_mutate_state_or_consume_rng(monkeypatch: Any) -> None:
    p, calc = _pair()
    state = _state()
    _precursor(state, int(_indices("lipoproteinMonomerIndexs")[0]), 2, mirror=True)
    before = deepcopy(state)
    dependencies = [v for v in calc.parameters.values() if hasattr(v, "_rng")]
    class NoDraws:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"deterministic request calculator accessed RNG: {name}")

    for dependency in dependencies:
        monkeypatch.setattr(dependency, "_rng", NoDraws())

    def forbidden_draw(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("deterministic request calculator consumed global RNG")

    for name in (
        "seed", "random", "random_sample", "rand", "randn", "randint", "choice",
        "multinomial", "uniform", "poisson", "binomial", "normal", "permutation", "default_rng",
    ):
        monkeypatch.setattr(np.random, name, forbidden_draw)
    first = _requests(calc, state, p)
    assert _requests(calc, state, p) == first
    assert state == before


@pytest.mark.parametrize("shadow", [0, 100], ids=["empty_shadow", "large_shadow"])
def test_requests_use_compartment_processed_i_not_legacy_shadows(shadow: int) -> None:
    p, calc = _pair()
    state = _state()
    for field, count in (("lipoproteinMonomerIndexs", 2), ("secretedMonomerIndexs", 3)):
        index = int(_indices(field)[0])
        _precursor(state, index, count)
        state["protein"]["processed_counts"][_wid(index)] = shadow
        state["protein"]["counts"][_wid(index)] = shadow
    assert _requests(calc, state, p) == _expected_requests(state, float(_source().stepSizeSec))


@pytest.mark.parametrize("field", ["lipoproteinMonomerIndexs", "secretedMonomerIndexs"])
def test_wrong_compartment_and_mature_only_counts_do_not_create_demand(field: str) -> None:
    p, calc = _pair()
    state = _state()
    index = int(_indices(field)[0])
    wid = _wid(index)
    wrong = next(c for c in COMPARTMENTS if c != _comp(index))
    state["protein"]["compartment_counts"]["processed_i"][wid][wrong] = 100
    state["protein"]["compartment_counts"]["mature"][wid][_comp(index)] = 100
    state["protein"]["counts"][wid] = 100
    assert _requests(calc, state, p) == {str(w): 0 for w in _source().substrateWholeCellModelIDs}
    _grant(state, p, 100)
    assert p.next_update(1.0, state) == {}


def test_non_target_processed_i_transitions_without_substrate_demand() -> None:
    p, calc = _pair()
    state = _state()
    index = next(int(i) for i in _indices("unprocessedMonomerIndexs") if _wid(int(i)) not in MIGRATED_WIDS)
    _precursor(state, index, 3)
    assert _requests(calc, state, p) == {str(w): 0 for w in _source().substrateWholeCellModelIDs}
    update = p.next_update(1.0, state)
    assert update.get("substrates", {}) == {}
    assert update["protein"]["counts"][_wid(index)] == -3
    assert update["protein"]["processed_counts"][_wid(index)] == 3


@pytest.mark.parametrize("field", ["lipoproteinMonomerIndexs", "secretedMonomerIndexs"])
def test_evolution_uses_source_compartment_not_conflicting_legacy_pool(field: str) -> None:
    p, _ = _pair()
    state = _state()
    index = int(_indices(field)[0])
    _precursor(state, index, 2)
    state["protein"]["counts"][_wid(index)] = 100
    state["protein"]["processed_counts"][_wid(index)] = 200
    _grant(state, p, 2)
    update = p.next_update(1.0, state)
    _transition(update, index, 2)
    for key in ("counts", "processed_counts", "unfolded_counts", "signal_sequence_counts"):
        assert not set(update.get("protein", {}).get(key, {})) & set(MIGRATED_WIDS)
    assert "location" not in update.get("protein", {})


@pytest.mark.parametrize("live", [True, False], ids=["live_on_shadow_off", "live_off_shadow_on"])
def test_evolution_uses_live_mature_enzymes_not_seeded_compatibility_branch(live: bool) -> None:
    p, _ = _pair()
    state = _state()
    index = int(_indices("lipoproteinMonomerIndexs")[0])
    _precursor(state, index, 2)
    for wid in _source().enzymeWholeCellModelIDs:
        wid = str(wid)
        state["protein"]["enzyme_counts"][wid] *= not live
        state["protein"]["counts"][wid] *= live
        for c in COMPARTMENTS:
            state["protein"]["compartment_counts"]["mature"][wid][c] *= live
    _grant(state, p, 2)
    _transition(p.next_update(1.0, state), index, 2 if live else 0)


@pytest.mark.parametrize("live", [True, False], ids=["live_on_shadow_off", "live_off_shadow_on"])
def test_requests_use_live_mature_enzymes_when_compatibility_disagrees(live: bool) -> None:
    p, calc = _pair()
    state = _state()
    _precursor(state, int(_indices("lipoproteinMonomerIndexs")[0]), 2, mirror=True)
    for wid in _source().enzymeWholeCellModelIDs:
        wid = str(wid)
        state["protein"]["enzyme_counts"][wid] *= not live
        state["protein"]["counts"][wid] *= live
        for c in COMPARTMENTS:
            state["protein"]["compartment_counts"]["mature"][wid][c] *= live
    assert _requests(calc, state, p) == _expected_requests(state, float(_source().stepSizeSec))


def test_zero_grant_blocks_real_precursor_even_with_huge_shared_pool() -> None:
    p, _ = _pair()
    state = _state(10000)
    _precursor(state, int(_indices("lipoproteinMonomerIndexs")[0]), 2)
    _grant(state, p, 0)
    assert p.next_update(1.0, state) == {}


@pytest.fixture(scope="module", params=["v5", "v6"])
def chassis(request: Any) -> Any:
    from opencell.vivarium import karr_composite

    built = getattr(karr_composite, f"build_karr_chassis_{request.param}")(
        time_step_s=float(_source().stepSizeSec), emit_step_s=float(_source().stepSizeSec)
    )
    # v5 returns an Engine; v6 returns the canonical Composite.
    return built if isinstance(built, Engine) else Engine(
        composite=built, display_info=False, progress_bar=False
    )


def _production_slice(chassis: Any, state: dict[str, Any]) -> Engine:
    """Retain the builder's actual PP2 phase registration/flow, not a repaired test flow."""
    selected = {
        key for key in set(chassis.processes) | set(chassis.steps)
        if "protein_processing_ii" in key
        or key in {"request_calculator_protein_pathway", "karr_allocation_step",
                   "protein_flat_projection_pre", "protein_flat_projection_post"}
    }
    return Engine(
        processes={k: v for k, v in chassis.processes.items() if k in selected},
        steps={k: v for k, v in chassis.steps.items() if k in selected},
        topology={k: v for k, v in chassis.topology.items() if k in selected},
        flow={k: [d for d in deps if d[0] in selected]
              for k, deps in chassis.flow.items() if k in selected},
        initial_state=deepcopy(state),
        display_info=False,
        progress_bar=False,
    )


def test_builders_wire_every_actual_calculator_port_and_allocator_consumer(chassis: Any) -> None:
    calc = chassis.steps["request_calculator_protein_pathway"]
    p = calc.parameters["protein_processing_ii_proc"]
    topology = chassis.topology[calc.name]
    assert set(calc.ports_schema()) <= set(topology)
    assert topology["protein"] == ("protein",)
    assert topology["requests"] == ("requests",)
    assert chassis.topology["karr_allocation_step"]["requests"] == topology["requests"]
    assert set(dict(chassis.steps["karr_allocation_step"].parameters["consumer_processes"])[p.name]) == {
        _sub("substrateIndexs_water"), _sub("substrateIndexs_PG160"),
    }
    assert any(v is p for v in chassis.processes.values()) or any(
        "protein_processing_ii" in k for k in chassis.steps
    )


def test_builders_preserve_migrated_projection_and_reject_dual_writer(chassis: Any) -> None:
    actual = chassis.state.get_value()
    protein = actual["protein"]
    for wid in map(str, _source().enzymeWholeCellModelIDs):
        assert wid in MIGRATED_WIDS
        assert protein["counts"][wid] == sum(protein["compartment_counts"]["mature"][wid].values())
    for key in ("processed_counts", "unfolded_counts", "signal_sequence_counts"):
        assert not set(protein.get(key, {})) & set(MIGRATED_WIDS)
    wid = _wid(int(_indices("lipoproteinMonomerIndexs")[0]))
    before = protein["counts"][wid]
    with pytest.raises(Exception, match="failed update|forbidden"):
        chassis.state.apply_update({"protein": {"counts": {wid: 1}}})
    assert chassis.state.get_value()["protein"]["counts"][wid] == before


def test_builders_expose_live_processed_i_and_enzyme_inputs(chassis: Any) -> None:
    calc = chassis.steps["request_calculator_protein_pathway"]
    protein = calc.ports_schema()["protein"]
    peptidase_wids = {
        _wid(int(i))
        for field in ("lipoproteinMonomerIndexs", "secretedMonomerIndexs")
        for i in _indices(field)
    } & set(MIGRATED_WIDS)
    declared = protein.get("compartment_counts", {})
    assert peptidase_wids <= set(declared.get("processed_i", {})), (
        "Engine views must expose the same processed-I authority that direct next_update reads"
    )
    for wid in map(str, _source().enzymeWholeCellModelIDs):
        assert wid in declared.get("mature", {}) or wid in protein.get("counts", {}), (
            "live enzyme authority or its protected mature projection must reach the calculator"
        )


def test_engine_construction_does_not_evolve_biology(chassis: Any) -> None:
    state = _state(2)
    index = int(_indices("lipoproteinMonomerIndexs")[0])
    _precursor(state, index, 2)
    p = chassis.steps["request_calculator_protein_pathway"].parameters["protein_processing_ii_proc"]
    _grant(state, p, 0)
    engine = _production_slice(chassis, state)
    actual = engine.state.get_value()
    assert actual["substrates"][_sub("substrateIndexs_water")] == 2
    assert actual["substrates"][_sub("substrateIndexs_PG160")] == 2
    assert actual["protein"]["compartment_counts"] == state["protein"]["compartment_counts"]


@pytest.mark.parametrize("bounded", [False, True], ids=["demand_limited", "one_event_per_tick"])
def test_engine_new_precursor_requests_grants_and_consumes_in_same_tick(
    chassis: Any, monkeypatch: Any, bounded: bool,
) -> None:
    calc = chassis.steps["request_calculator_protein_pathway"]
    p = calc.parameters["protein_processing_ii_proc"]
    fx = _source()
    dt = float(fx.stepSizeSec)
    if bounded:
        # Synthetic configured timestep makes the fixture transferase budget one event.
        dt = 1 / (float(fx.enzymes[int(fx.enzymeIndexs_diacylglycerylTransferase) - 1])
                  * float(fx.lipoproteinDiacylglycerylTransferaseSpecificRate))
    monkeypatch.setitem(p.parameters, "time_step", dt)
    state = _state(3)
    index = int(_indices("lipoproteinMonomerIndexs")[0])
    wid, comp = _wid(index), _comp(index)
    _grant(state, p, 0)
    calls: list[dict[str, Any]] = []
    original = p.next_update

    def observed(timestep: float, inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(deepcopy(inputs))
        return original(timestep, inputs)

    monkeypatch.setattr(p, "next_update", observed)
    engine = _production_slice(chassis, state)
    before = engine.state.get_value()
    assert before["substrates_allocated"][p.name][_sub("substrateIndexs_PG160")] == 0
    assert before["protein"]["compartment_counts"]["processed_i"][wid][comp] == 0
    calls.clear()
    engine.state.apply_update({
        "protein": {
            "compartment_counts": {"processed_i": {wid: {comp: 3}}},
        },
    })
    engine.update(dt)
    actual = engine.state.get_value()
    events = 1 if bounded else 3
    # Consumption/transition is the gate. Request/grant presence alone is not success.
    assert actual["substrates"][_sub("substrateIndexs_water")] == 3 - events, (
        "PP2 must consume this tick's grant, not yesterday's zero grant; "
        f"new grant={actual['substrates_allocated'][p.name][_sub('substrateIndexs_PG160')]}, "
        "evolution saw grant="
        f"{calls[0]['substrates_allocated'][p.name][_sub('substrateIndexs_PG160')] if calls else 'no call'}"
    )
    assert actual["substrates"][_sub("substrateIndexs_PG160")] == 3 - events
    assert actual["protein"]["compartment_counts"]["processed_i"][wid][comp] == 3 - events
    assert actual["protein"]["compartment_counts"]["processed_ii"][wid][comp] == events
    assert len(calls) == 1, "exactly one real PP2 evolution, never a calculator-side evolution"
    assert calls[0]["substrates_allocated"][p.name][_sub("substrateIndexs_PG160")] == 3
    if bounded:
        engine.update(dt)
        after = engine.state.get_value()
        assert after["substrates"][_sub("substrateIndexs_PG160")] == 1
        assert after["protein"]["compartment_counts"]["processed_ii"][wid][comp] == 2
        assert len(calls) == 2


@pytest.mark.parametrize("mutation", ["stale_grant", "duplicate_evolution"])
def test_measured_transition_canary_rejects_stale_or_duplicated_evolution(mutation: str) -> None:
    p, _ = _pair()
    state = _state(1)
    index = int(_indices("lipoproteinMonomerIndexs")[0])
    _precursor(state, index, 1)
    _grant(state, p, 1)
    _transition(p.next_update(1.0, deepcopy(state)), index, 1)
    if mutation == "stale_grant":
        _grant(state, p, 0)
        wrong = p.next_update(1.0, state)
    else:
        # A duplicate execution from the same snapshot doubles measured public deltas.
        wrong = p.next_update(1.0, state)

        def double_leaves(tree: dict[str, Any]) -> None:
            for key, value in tree.items():
                if isinstance(value, dict):
                    double_leaves(value)
                else:
                    tree[key] = value * 2

        double_leaves(wrong)
    with pytest.raises(AssertionError):
        _transition(wrong, index, 1)
