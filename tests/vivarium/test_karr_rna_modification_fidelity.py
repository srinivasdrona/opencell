"""RNAModification.m:259-271,289-362 executable production-readiness freeze.

Counts are exact; every expected output comes from fixture stoichiometry and
explicit input interventions, never F-trace answers. The historical no-op replay
is not evidence for these contracts. Mutable RNG is persistent within a test;
each independent case starts a fresh process and no process-global RNG is seeded.
"""

from copy import deepcopy

import numpy as np
import pytest
from _rna_fidelity_helpers import (
    UniformInputs,
    assert_modification_output,
    builder,
    exact_counts,
    fixture,
    live_enzymes,
    modification_requirements,
    pathway,
    processed_keys,
    production_slice,
    seed_modification,
    vector,
    wids,
)


@pytest.mark.parametrize(
    "case",
    [
        "demand_limited",
        "enzyme_limited",
        "ceil_below",
        "ceil_above",
        "zero_pool",
        "zero_enzyme",
        "zero_precursor",
    ],
)
def test_request_exact_source_algebra_without_availability_cap(case):
    fx = fixture("RNAModification")
    dt = float(fx["stepSizeSec"]) / 2
    rp, rm, calc, state = pathway(dt)
    mapping, stoich, _ = modification_requirements(dt)
    catalysis = np.asarray(fx["reactionCatalysisMatrix"], dtype=float)
    count = 1 if case == "demand_limited" else 7  # synthetic pool interventions
    precursor = (mapping.sum(axis=0) > 0).astype(float) * count
    enzymes = np.ones(catalysis.shape[1])
    if case == "demand_limited":
        enzymes *= np.ceil(mapping @ precursor).sum() / dt
    if case in ("ceil_below", "ceil_above"):
        enzymes *= np.nextafter(1.0, 0.0 if case == "ceil_below" else 2.0) / dt
    if case == "zero_enzyme":
        enzymes[:] = 0
    if case == "zero_precursor":
        precursor[:] = 0
    state["rna"]["counts"].update(zip(processed_keys(), map(float, precursor), strict=True))
    live_enzymes(state, fx, enzymes)
    state["substrates"] = dict.fromkeys(state["substrates"], 0.0 if case == "zero_pool" else 113.0)
    expected = np.maximum(0, -stoich) @ np.minimum(
        np.ceil(catalysis @ enzymes * dt), mapping @ precursor
    )
    if case not in ("zero_enzyme", "zero_precursor"):
        assert np.any(expected > 0), "nonvacuous request witness"
    rm._rng = UniformInputs()
    rp._rng = UniformInputs()
    before = deepcopy(state)
    # Vivarium Steps receive zero elapsed time; configured process dt must survive.
    update = calc.next_update(0.0, state)
    assert state == before
    assert rm._rng.calls == rp._rng.calls == []
    observed = update["requests"][rm.name]
    assert set(observed) == set(wids(fx, "substrateWholeCellModelIDs"))
    exact_counts(vector(observed, rm.substrate_wids), expected)


def test_requests_ignore_mature_legacy_and_wrong_enzyme_shadows():
    fx = fixture("RNAModification")
    _, rm, calc, state = pathway()
    mapping, stoich, _ = modification_requirements()
    flux = (mapping.sum(axis=0) > 0).astype(float)
    seed_modification(state, rm, flux)
    state["rna"]["counts"] = dict.fromkeys(state["rna"]["counts"], 0.0)
    state["rna"]["modified_counts"] = dict.fromkeys(state["rna"]["modified_counts"], 31.0)
    state["unmodifiedRNAs"] = dict.fromkeys(processed_keys(), 31.0)
    state["enzymes"] = dict.fromkeys(rm.enzyme_wids, 31.0)
    # Nonzero global pool makes a false legacy activation numerically visible.
    state["substrates"] = dict.fromkeys(state["substrates"], 113.0)
    exact_counts(
        vector(calc.next_update(0, state)["requests"][rm.name], rm.substrate_wids),
        np.zeros(stoich.shape[0]),
    )
    # Live source is zero despite positive legacy enzyme shadows.
    state["rna"]["counts"].update(zip(processed_keys(), map(float, flux), strict=True))
    live_enzymes(state, fx, np.zeros(len(rm.enzyme_wids)))
    exact_counts(
        vector(calc.next_update(0, state)["requests"][rm.name], rm.substrate_wids),
        np.zeros(stoich.shape[0]),
    )
    assert_modification_output(rm.next_update(1.0, state), np.zeros_like(flux))


@pytest.mark.parametrize("kind", ["monomer", "complex"])
def test_live_enzyme_ownership_controls_nonzero_evolution(kind):
    fx = fixture("RNAModification")
    _, rm, _, state = pathway()
    mapping, _, enzyme_req = modification_requirements()
    candidates = np.atleast_1d(fx[f"enzyme{kind.title()}LocalIndexs"]).astype(int) - 1
    target = int(np.flatnonzero(np.any(enzyme_req[:, candidates] > 0, axis=1))[0])
    flux = np.zeros(mapping.shape[1])
    flux[target] = 1
    seed_modification(state, rm, flux)
    assert_modification_output(rm.next_update(1.0, state), flux)
    limiting = int(candidates[np.flatnonzero(enzyme_req[target, candidates] > 0)[0]])
    blocked = deepcopy(state)
    store = "protein" if kind == "monomer" else "complex"
    blocked[store]["counts"][rm.enzyme_wids[limiting]] = 0.0
    blocked["enzymes"] = dict.fromkeys(rm.enzyme_wids, 113.0)
    assert_modification_output(rm.next_update(1.0, blocked), np.zeros_like(flux))


def test_exhaustive_active_fixture_species_and_full_stoichiometric_writeback():
    _, rm, _, state = pathway()
    mapping, _, _ = modification_requirements()
    flux = (mapping.sum(axis=0) > 0).astype(float)
    assert flux.sum() > 1
    seed_modification(state, rm, flux)
    assert_modification_output(rm.next_update(1.0, state), flux)


def test_all_no_modification_required_species_pass_to_mature_same_tick():
    _, rm, _, state = pathway()
    mapping, _, _ = modification_requirements()
    flux = (mapping.sum(axis=0) == 0).astype(float)
    assert flux.sum() > 1
    seed_modification(state, rm, flux)
    assert_modification_output(rm.next_update(1.0, state), flux)


@pytest.mark.parametrize("obsolete_cap", [0, 1])
def test_weighted_loop_not_bulk_prepass_or_capped_residual(obsolete_cap):
    fx = fixture("RNAModification")
    _, rm, _, state = pathway()
    rm.parameters["max_stochastic_iterations"] = obsolete_cap
    mapping, stoich, _ = modification_requirements()
    # Two single-reaction RNAs competing for identical reactants and enzyme.
    singles = np.flatnonzero(mapping.sum(axis=0) == 1)
    pair = next(
        (int(a), int(b))
        for a in singles
        for b in singles
        if a < b
        and np.array_equal(mapping[:, a], mapping[:, b]) is False
        and np.array_equal(stoich @ mapping[:, a], stoich @ mapping[:, b])
        and np.array_equal(
            fx["reactionCatalysisMatrix"].T @ mapping[:, a],
            fx["reactionCatalysisMatrix"].T @ mapping[:, b],
        )
    )
    counts = np.zeros(mapping.shape[1])
    counts[list(pair)] = 2
    resources, _ = seed_modification(state, rm, counts)
    # Supply only two total events. High uniform draws select the later RNA twice.
    state["substrates_allocated"][rm.name] = dict(
        zip(rm.substrate_wids, resources / 2, strict=True)
    )
    stream = UniformInputs()
    rm._rng = stream
    expected = np.zeros_like(counts)
    expected[pair[1]] = 2
    assert_modification_output(rm.next_update(1.0, state), expected)
    assert sum(size is None for kind, size in stream.calls if kind == "random") == 2
    assert sum(size is not None for kind, size in stream.calls if kind == "random") >= 3


@pytest.mark.parametrize("uniform,expected_count", [(0.0, 1), (0.99, 0)])
def test_stochastic_feasibility_is_rounded_before_weighted_selection(uniform, expected_count):
    fx = fixture("RNAModification")
    _, rm, _, state = pathway()
    mapping, _, enzyme_req = modification_requirements()
    target = int(np.flatnonzero(mapping.sum(axis=0) == 1)[0])
    flux = np.zeros(mapping.shape[1])
    flux[target] = 1
    seed_modification(state, rm, flux)
    enzymes = np.floor(enzyme_req[target] / 2)
    assert np.any(enzymes > 0)
    live_enzymes(state, fx, enzymes)
    rm._rng = UniformInputs(array=uniform)
    assert_modification_output(rm.next_update(1.0, state), flux * expected_count)


def test_water_and_hydrogen_excluded_only_from_feasibility_not_writeback():
    _, rm, _, state = pathway()
    mapping, stoich, _ = modification_requirements()
    water = rm.substrate_wids.index("H2O")
    target = int(np.flatnonzero((stoich @ mapping)[water] < 0)[0])
    flux = np.zeros(mapping.shape[1])
    flux[target] = 1
    seed_modification(state, rm, flux)
    for wid in ("H2O", "H"):
        state["substrates_allocated"][rm.name][wid] = 0.0
    update = rm.next_update(1.0, state)
    assert_modification_output(update, flux)
    assert update["substrates"]["H2O"] < 0
    assert update["substrates"]["H"] > 0


def test_output_hints_cannot_override_zero_resources_or_live_enzymes():
    _, rm, _, state = pathway()
    mapping, _, _ = modification_requirements()
    target = int(np.flatnonzero(mapping.sum(axis=0) > 0)[0])
    flux = np.zeros(mapping.shape[1])
    flux[target] = 1
    state["rna"]["counts"].update(zip(processed_keys(), map(float, flux), strict=True))
    state["trace_hint"] = {
        "unmodifiedRNAs_next": dict.fromkeys(rm.unmodified_rna_wids, 0.0),
        "modifiedRNAs_next": {rm.modified_rna_wids[0]: 1.0},
    }
    assert_modification_output(rm.next_update(1.0, state), np.zeros_like(flux))


@pytest.mark.parametrize("version", [5, 6])
def test_real_builder_ports_expose_calculator_and_evolution_live_inputs(version):
    composite = builder(version)
    calc = composite["steps"]["request_calculator_rna_pathway"]
    rm = composite["processes"]["karr_rna_modification"]
    for name, proc in (("request_calculator_rna_pathway", calc), (rm.name, rm)):
        schema = proc.ports_schema()
        for port in ("rna", "protein", "complex"):
            assert port in schema, f"{name} hides live {port} input from Engine"
            assert composite["topology"][name].get(port) == (port,)
    assert set(processed_keys()) <= set(rm.ports_schema()["rna"]["counts"])


@pytest.mark.parametrize("version", [5, 6])
def test_same_tick_production_request_allocate_evolve_and_no_stale_consumption(version):
    composite = builder(version)
    rm = composite["processes"]["karr_rna_modification"]
    _, _, _, state = pathway()
    mapping, _, _ = modification_requirements()
    target = int(np.flatnonzero(mapping.sum(axis=0) == 1)[0])
    flux = np.zeros(mapping.shape[1])
    flux[target] = 1
    resources, _ = seed_modification(state, rm, flux)
    precursor_key = processed_keys()[target]
    state["rna"]["counts"][precursor_key] = 0.0
    state["substrates_allocated"][rm.name] = dict.fromkeys(rm.substrate_wids, 0.0)
    engine = production_slice(composite, rm.name, state)
    initialized = engine.state.get_value()
    exact_counts(
        vector(initialized["substrates_allocated"][rm.name], rm.substrate_wids),
        np.zeros(len(rm.substrate_wids)),
    )
    # A new source-form precursor arrives after construction, before this tick.
    # This is an input intervention, not a manual request/allocation/evolution.
    engine.state.set_value({"rna": {"counts": {precursor_key: 1.0}}})
    before = engine.state.get_value()
    assert before["rna"]["counts"][precursor_key] == 1
    assert before["rna"]["modified_counts"][precursor_key] == 0
    engine.update(1.0)
    after = engine.state.get_value()
    assert after["rna"]["counts"][processed_keys()[target]] == 0, (
        "stale zero grant delayed evolution"
    )
    assert after["rna"]["modified_counts"][processed_keys()[target]] == 1
    _, stoich, _ = modification_requirements()
    exact_counts(
        vector(after["substrates"], rm.substrate_wids) - resources, stoich @ mapping @ flux
    )
    engine.update(1.0)
    again = engine.state.get_value()
    assert again["rna"] == after["rna"], "duplicate/stale precursor consumption"
    exact_counts(
        vector(again["substrates"], rm.substrate_wids),
        vector(after["substrates"], rm.substrate_wids),
    )


def test_engine_construction_does_not_evolve_an_active_precursor():
    composite = builder(6)
    rm = composite["processes"]["karr_rna_modification"]
    _, _, _, state = pathway()
    mapping, _, _ = modification_requirements()
    target = int(np.flatnonzero(mapping.sum(axis=0) == 1)[0])
    flux = np.zeros(mapping.shape[1])
    flux[target] = 1
    seed_modification(state, rm, flux)
    state["substrates_allocated"][rm.name] = dict.fromkeys(rm.substrate_wids, 0.0)
    engine = production_slice(composite, rm.name, state)
    initialized = engine.state.get_value()
    for form, keys in (
        ("counts", processed_keys()),
        ("modified_counts", wids(fixture("RNAModification"), "modifiedRNAWholeCellModelIDs")),
    ):
        exact_counts(
            vector(initialized["rna"].get(form, {}), keys), vector(state["rna"][form], keys)
        )
    exact_counts(
        vector(initialized["substrates"], rm.substrate_wids),
        vector(state["substrates"], rm.substrate_wids),
    )


def test_full_output_checker_rejects_numerical_missing_product_mutation():
    _, rm, _, state = pathway()
    mapping, _, _ = modification_requirements()
    flux = (mapping.sum(axis=0) > 0).astype(float)
    seed_modification(state, rm, flux)
    update = rm.next_update(1.0, state)
    assert_modification_output(update, flux)
    mutated = deepcopy(update)
    product = next(wid for wid, delta in mutated["substrates"].items() if delta > 0)
    mutated["substrates"][product] -= 1
    with pytest.raises(AssertionError):
        assert_modification_output(mutated, flux)
