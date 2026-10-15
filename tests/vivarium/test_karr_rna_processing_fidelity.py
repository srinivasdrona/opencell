"""RNAProcessing.m:352-369,406-471 bounded production-readiness contracts.

No trace outputs, private flux helpers, oracle hints, tick/seed-fitted expectations,
or vacuous no-op acceptance. All source RNA classes/stoichiometric outputs are
covered, including every intergenic row. Synthetic resources are input
interventions, not evidence that the default chassis supplies these precursors.
"""

import pickle
from copy import deepcopy

import numpy as np
import pytest
from _rna_fidelity_helpers import (
    UniformInputs,
    assert_processing_output,
    builder,
    exact_counts,
    fixture,
    intergenic_keys,
    live_enzymes,
    modification_requirements,
    pathway,
    processed_keys,
    processing_indices,
    processing_output_vectors,
    production_slice,
    seed_modification,
    seed_processing,
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
def test_request_exact_source_matrix_algebra_and_configured_dt(case):
    fx = fixture("RNAProcessing")
    stoich = np.asarray(fx["reactantByproductMatrix"], dtype=float)
    catalysis = np.asarray(fx["catalysisMatrix"], dtype=float)
    precursor = np.full(stoich.shape[1], 7.0)  # synthetic intervention
    dt = float(fx["stepSizeSec"]) / 2
    enzymes = np.ones(catalysis.shape[0])
    if case == "demand_limited":
        precursor[:] = 1
        enzymes = np.ceil(catalysis @ precursor / dt) + 1
    if case.startswith("ceil_"):
        precursor[:] = 0
        target = int(processing_indices("rRNA")[0])
        precursor[target] = 7
        enzymes = np.ceil(catalysis[:, target]) + 1
        boundary = np.max(catalysis[:, target] / enzymes)
        dt = boundary * (1 - 1e-8 if case == "ceil_below" else 1 + 1e-8)
    if case == "zero_enzyme":
        enzymes[:] = 0
    if case == "zero_precursor":
        precursor[:] = 0
    rp, rm, calc, state = pathway(dt)
    state["rna"]["counts"].update(
        zip(wids(fx, "unprocessedRNAWholeCellModelIDs"), map(float, precursor), strict=True)
    )
    live_enzymes(state, fx, enzymes)
    state["substrates"] = dict.fromkeys(state["substrates"], 0.0 if case == "zero_pool" else 113.0)
    limits = np.divide(
        enzymes[:, None] * dt,
        catalysis,
        out=np.full(catalysis.shape, np.inf),
        where=catalysis > 0,
    )
    expected = np.maximum(0, -stoich) @ np.minimum(np.ceil(limits.min(axis=0)), precursor)
    if case not in ("zero_enzyme", "zero_precursor"):
        assert np.any(expected > 0)
    rp._rng = UniformInputs()
    rm._rng = UniformInputs()
    before = deepcopy(state)
    result = calc.next_update(0.0, state)["requests"][rp.name]
    assert set(result) == set(rp.substrate_wids)
    assert state == before
    assert rp._rng.calls == rm._rng.calls == []
    exact_counts(vector(result, wids(fx, "substrateWholeCellModelIDs")), expected)


def test_processed_mature_and_legacy_shadows_do_not_request_or_evolve():
    rp, _, calc, state = pathway()
    state["rna"]["counts"].update(dict.fromkeys(processed_keys(), 31.0))
    state["rna"]["modified_counts"] = dict.fromkeys(state["rna"]["modified_counts"], 31.0)
    state["unprocessedRNAs"] = dict.fromkeys(rp.unprocessed_rna_wids, 31.0)
    state["substrates"] = dict.fromkeys(state["substrates"], 113.0)
    exact_counts(
        vector(calc.next_update(0, state)["requests"][rp.name], rp.substrate_wids),
        np.zeros(len(rp.substrate_wids)),
    )
    assert_processing_output(rp.next_update(1.0, state), np.zeros(len(rp.unprocessed_rna_wids)))


def test_live_zero_enzymes_cannot_be_overridden_by_legacy_enzyme_shadow():
    fx = fixture("RNAProcessing")
    rp, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[processing_indices("rRNA")[0]] = 1
    seed_processing(state, rp, events)
    state["enzymes"] = dict.fromkeys(rp.enzyme_wids, 113.0)
    live_enzymes(state, fx, np.zeros(len(rp.enzyme_wids)))
    assert_processing_output(rp.next_update(1.0, state), np.zeros_like(events))


def test_default_zero_legacy_enzyme_port_cannot_hide_live_positive_enzymes():
    rp, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[processing_indices("sRNA")[0]] = 1
    seed_processing(state, rp, events)
    state["enzymes"] = dict.fromkeys(rp.enzyme_wids, 0.0)
    assert_processing_output(rp.next_update(1.0, state), events)


@pytest.mark.parametrize("seed", [0, 17])
def test_identity_maturation_has_no_first_active_tick_or_seed_specific_lag(seed):
    rp, _, _, state = pathway()
    rp.parameters["rng_seed"] = seed
    rp._rng = np.random.default_rng(seed)
    target = rp.unprocessed_rna_wids.index("TU_317")
    assert target in processing_indices("mRNA")
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[target] = 1
    seed_processing(state, rp, events)
    # Repeating the identical INPUT state must not "activate" a previously hidden tick.
    first = rp.next_update(1.0, state)
    second = rp.next_update(1.0, state)
    assert_processing_output(first, events)
    assert_processing_output(second, events)


@pytest.mark.parametrize("kind", ["mRNA", "rRNA", "sRNA", "tRNA"])
def test_every_fixture_species_in_each_class_full_output_contract(kind):
    rp, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[processing_indices(kind)] = 1
    seed_processing(state, rp, events)
    assert events.sum() > 0
    assert_processing_output(rp.next_update(1.0, state), events)


@pytest.mark.parametrize(
    "order,winner",
    [
        ((3, 1, 0, 2), "tRNA"),
        ((1, 3, 0, 2), "rRNA"),
    ],
)
def test_source_random_type_order_controls_competition_not_hidden_trna_suppression(order, winner):
    rp, _, _, state = pathway()
    r_index = int(processing_indices("rRNA")[0])
    stoich = np.asarray(fixture("RNAProcessing")["reactantByproductMatrix"], dtype=float)
    water_index = rp.substrate_wids.index("H2O")
    trna_indices = processing_indices("tRNA")
    # RNAProcessing.m:441 bounds against the WHOLE class, not selected precursors.
    # Choose a precursor that actually spends that bound: either order then leaves
    # too little water for the other class, rather than allowing both to mature.
    t_index = int(trna_indices[np.argmin(stoich[water_index, trna_indices])])
    shared_water = -stoich[water_index, t_index]
    assert shared_water == np.max(-stoich[water_index, trna_indices])
    assert 0 < -stoich[water_index, r_index] < shared_water
    inputs = np.zeros(len(rp.unprocessed_rna_wids))
    inputs[[r_index, t_index]] = 1
    seed_processing(state, rp, inputs)
    state["substrates_allocated"][rp.name]["H2O"] = shared_water
    stream = UniformInputs(order=order)
    rp._rng = stream
    expected = np.zeros_like(inputs)
    expected[t_index if winner == "tRNA" else r_index] = 1
    update = rp.next_update(1.0, state)
    assert_processing_output(update, expected)
    assert stream.calls[0] == ("permutation", 4)


def test_selected_trna_below_whole_class_water_bound_cannot_process():
    rp, _, _, state = pathway()
    stoich = np.asarray(fixture("RNAProcessing")["reactantByproductMatrix"], dtype=float)
    water_index = rp.substrate_wids.index("H2O")
    trna_indices = processing_indices("tRNA")
    selected = int(trna_indices[0])
    scarce_water = -stoich[water_index, processing_indices("rRNA")[0]]
    class_bound = np.max(-stoich[water_index, trna_indices])
    assert 0 < -stoich[water_index, selected] < scarce_water < class_bound
    inputs = np.zeros(len(rp.unprocessed_rna_wids))
    inputs[selected] = 1
    seed_processing(state, rp, inputs)
    state["substrates_allocated"][rp.name]["H2O"] = scarce_water
    rp._rng = UniformInputs(order=(3, 1, 0, 2))
    assert_processing_output(rp.next_update(1.0, state), np.zeros_like(inputs))


def test_mixed_rrna_trna_with_sufficient_resources_processes_both():
    rp, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[processing_indices("rRNA")[0]] = 1
    events[processing_indices("tRNA")[0]] = 1
    seed_processing(state, rp, events)
    rp._rng = UniformInputs(order=(3, 1, 0, 2))
    update = rp.next_update(1.0, state)
    exact_counts(vector(update.get("rna", {}).get("counts", {}), rp.unprocessed_rna_wids), -events)
    assert_processing_output(update, events)


@pytest.mark.parametrize(
    "limiter,expected_count",
    [
        ("substrate", 1),
        ("enzyme", 1),
        ("zero_substrate", 0),
        ("zero_enzyme", 0),
    ],
)
def test_substrate_and_live_enzyme_caps_on_actual_processing(limiter, expected_count):
    fx = fixture("RNAProcessing")
    rp, _, _, state = pathway()
    target = int(processing_indices("rRNA")[0])
    inputs = np.zeros(len(rp.unprocessed_rna_wids))
    inputs[target] = 3
    _, enzymes = seed_processing(state, rp, inputs)
    stoich = np.asarray(fx["reactantByproductMatrix"], dtype=float)
    if "substrate" in limiter:
        state["substrates_allocated"][rp.name] = dict(
            zip(
                rp.substrate_wids,
                np.maximum(0, -stoich[:, target]) * (0 if limiter.startswith("zero_") else 1),
                strict=True,
            )
        )
    else:
        req = np.asarray(fx["catalysisMatrix"], dtype=float)[:, target]
        limiting = int(np.argmax(req))
        enzymes[limiting] = 0 if limiter.startswith("zero_") else np.ceil(req[limiting])
        live_enzymes(state, fx, enzymes)
    rp._rng = UniformInputs()
    expected = np.zeros_like(inputs)
    expected[target] = expected_count
    update = rp.next_update(1.0, state)
    # Caps are measured independently of intergenic-output RED.
    exact_counts(
        vector(update.get("rna", {}).get("counts", {}), rp.unprocessed_rna_wids), -expected
    )
    exact_counts(vector(update.get("substrates", {}), rp.substrate_wids), stoich @ expected)


@pytest.mark.parametrize("uniform,chosen", [(0.0, 0), (0.99, 1)])
def test_actual_within_type_selection_samples_input_counts_without_replacement(uniform, chosen):
    fx = fixture("RNAProcessing")
    rna_fx = fixture("Rna")
    indices = processing_indices("tRNA")
    no_fragments = np.asarray(rna_fx["intergenicRNAMatrix"])[:, indices].sum(axis=0) == 0
    pair = indices[no_fragments][:2]
    assert len(pair) == 2
    catalysis = np.asarray(fx["catalysisMatrix"], dtype=float)
    dt = float(catalysis[:, pair[0]].max())
    rp, _, _, state = pathway(dt)
    inputs = np.zeros(len(rp.unprocessed_rna_wids))
    inputs[pair] = 2
    seed_processing(state, rp, inputs, dt)
    live_enzymes(state, fx, np.ones(len(rp.enzyme_wids)))
    rp._rng = UniformInputs(scalar=uniform)
    expected = np.zeros_like(inputs)
    expected[pair[chosen]] = 1
    assert_processing_output(rp.next_update(dt, state), expected)


def test_intergenic_output_keeps_each_source_row_and_cytosolic_routing():
    fx = fixture("RNAProcessing")
    rp, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    # Every intergenic-producing precursor, not just the rRNA exemplar.
    matrix = np.asarray(fixture("Rna")["intergenicRNAMatrix"], dtype=float)
    events[np.flatnonzero(matrix.sum(axis=0) > 0)] = 1
    seed_processing(state, rp, events)
    rp._rng = UniformInputs()
    expected = matrix @ events
    assert np.all(expected > 0)
    assert len(set(wids(fx, "intergenicRNAWholeCellModelIDs"))) < len(expected)
    assert len(set(intergenic_keys())) == len(expected)
    update = rp.next_update(1.0, state)
    exact_counts(vector(update.get("rna", {}).get("counts", {}), intergenic_keys()), expected)
    assert_processing_output(update, events)


def test_output_checker_rejects_one_molecule_missing_product_mutation():
    rp, _, _, state = pathway()
    target = int(processing_indices("sRNA")[0])
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[target] = 1
    seed_processing(state, rp, events)
    update = rp.next_update(1.0, state)
    assert_processing_output(update, events)
    mutated = deepcopy(update)
    product = next(key for key, value in mutated["rna"]["counts"].items() if value > 0)
    mutated["rna"]["counts"][product] -= 1
    with pytest.raises(AssertionError):
        assert_processing_output(mutated, events)


def test_anti_oracle_zero_grants_and_global_rng_preservation(monkeypatch):
    before_rng = pickle.dumps(np.random.get_state())
    rp, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[processing_indices("rRNA")[0]] = 1
    seed_processing(state, rp, events)
    state["substrates_allocated"][rp.name] = dict.fromkeys(rp.substrate_wids, 0.0)
    state["trace_hint"] = {
        "unprocessedRNAs_next": dict.fromkeys(rp.unprocessed_rna_wids, 0.0),
        "processedRNAs_next": dict.fromkeys(processed_keys(), 113.0),
    }

    def forbidden_io(*args, **kwargs):
        raise AssertionError("per-tick file I/O/oracle access")

    monkeypatch.setattr("builtins.open", forbidden_io)
    assert_processing_output(rp.next_update(1.0, state), np.zeros_like(events))
    assert pickle.dumps(np.random.get_state()) == before_rng


@pytest.mark.parametrize("version", [5, 6])
def test_builder_exposes_real_rna_forms_and_live_enzyme_calculator_inputs(version):
    composite = builder(version)
    rp = composite["processes"]["karr_rna_processing"]
    calc = composite["steps"]["request_calculator_rna_pathway"]
    for name, proc in (("request_calculator_rna_pathway", calc), (rp.name, rp)):
        for port in ("rna", "protein", "complex"):
            assert port in proc.ports_schema(), f"Engine cannot see {name}.{port}"
            assert composite["topology"][name].get(port) == (port,)
    # Same RNA authority; no unconnected process-local intergenic output port.
    assert set(intergenic_keys()) <= set(rp.ports_schema()["rna"]["counts"])
    assert set(processed_keys()) <= set(rp.ports_schema()["rna"]["counts"])


@pytest.mark.parametrize("version", [5, 6])
def test_new_precursor_same_tick_zero_grant_engine_transition_not_stale_or_duplicate(version):
    composite = builder(version)
    rp = composite["processes"]["karr_rna_processing"]
    _, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    target = int(processing_indices("rRNA")[0])
    events[target] = 1
    resources, _ = seed_processing(state, rp, events)
    precursor = rp.unprocessed_rna_wids[target]
    state["rna"]["counts"][precursor] = 0.0
    state["substrates_allocated"][rp.name] = dict.fromkeys(rp.substrate_wids, 0.0)
    engine = production_slice(composite, rp.name, state)
    initialized = engine.state.get_value()
    exact_counts(
        vector(initialized["substrates_allocated"][rp.name], rp.substrate_wids),
        np.zeros(len(rp.substrate_wids)),
    )
    engine.state.set_value({"rna": {"counts": {precursor: 1.0}}})
    engine.update(1.0)
    after = engine.state.get_value()
    assert after["rna"]["counts"][precursor] == 0, "first tick used stale zero grant"
    sub, processed, intergenic = processing_output_vectors(events)
    exact_counts(vector(after["substrates"], rp.substrate_wids) - resources, sub)
    exact_counts(vector(after["rna"]["counts"], processed_keys()), processed)
    exact_counts(vector(after["rna"]["counts"], intergenic_keys()), intergenic)
    engine.update(1.0)
    again = engine.state.get_value()
    assert again["rna"] == after["rna"], "duplicate/stale processing"
    exact_counts(
        vector(again["substrates"], rp.substrate_wids),
        vector(after["substrates"], rp.substrate_wids),
    )


def test_engine_construction_preserves_active_precursor_and_outputs():
    composite = builder(6)
    rp = composite["processes"]["karr_rna_processing"]
    _, _, _, state = pathway()
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[processing_indices("rRNA")[0]] = 1
    seed_processing(state, rp, events)
    state["substrates_allocated"][rp.name] = dict.fromkeys(rp.substrate_wids, 0.0)
    engine = production_slice(composite, rp.name, state)
    initialized = engine.state.get_value()
    keys = rp.unprocessed_rna_wids + processed_keys() + intergenic_keys()
    exact_counts(vector(initialized["rna"]["counts"], keys), vector(state["rna"]["counts"], keys))
    exact_counts(
        vector(initialized["substrates"], rp.substrate_wids),
        vector(state["substrates"], rp.substrate_wids),
    )


def test_real_processing_output_is_the_modification_precursor_not_a_second_authority():
    rp, rm, calc, state = pathway()
    no_fragments = np.asarray(fixture("Rna")["intergenicRNAMatrix"]).sum(axis=0) == 0
    target = int(next(index for index in processing_indices("tRNA") if no_fragments[index]))
    events = np.zeros(len(rp.unprocessed_rna_wids))
    events[target] = 1
    _, processed, _ = processing_output_vectors(events)
    seed_modification(state, rm, processed)
    # All processed products must come from real processing, never from this seeder.
    for key in processed_keys():
        state["rna"]["counts"][key] = 0.0
    seed_processing(state, rp, events)
    initial = deepcopy(state["rna"]["counts"])
    processing_update = rp.next_update(1.0, state)
    assert_processing_output(processing_update, events)
    for key, delta in processing_update["rna"]["counts"].items():
        state["rna"]["counts"][key] += delta
    exact_counts(vector(state["rna"]["counts"], processed_keys()), processed)
    assert state["rna"]["counts"][rp.unprocessed_rna_wids[target]] == 0
    assert sum(state["rna"]["modified_counts"].values()) == 0
    modification_update = rm.next_update(1.0, state)
    exact_counts(
        vector(modification_update.get("rna", {}).get("counts", {}), processed_keys()), -processed
    )
    assert any(delta > 0 for delta in modification_update["rna"]["modified_counts"].values())
    mapping, stoich, _ = modification_requirements()
    enz_fx = fixture("RNAModification")
    enzymes = np.zeros(len(rm.enzyme_wids))
    for field, store in (
        ("enzymeMonomerLocalIndexs", "protein"),
        ("enzymeComplexLocalIndexs", "complex"),
    ):
        for index in np.atleast_1d(enz_fx[field]).astype(int) - 1:
            enzymes[index] = state[store]["counts"][rm.enzyme_wids[index]]
    expected = np.maximum(0, -stoich) @ np.minimum(
        np.ceil(np.asarray(enz_fx["reactionCatalysisMatrix"], dtype=float) @ enzymes),
        mapping @ processed,
    )
    assert np.any(expected > 0)
    assert initial[rp.unprocessed_rna_wids[target]] == 1
    observed = calc.next_update(0, state)["requests"][rm.name]
    exact_counts(vector(observed, rm.substrate_wids), expected)


@pytest.mark.parametrize("process_name", ["karr_rna_processing", "karr_rna_modification"])
def test_real_engine_consumes_one_precursor_once_despite_previous_grant(process_name):
    composite = builder(6)
    rp = composite["processes"]["karr_rna_processing"]
    rm = composite["processes"]["karr_rna_modification"]
    _, _, _, state = pathway()
    if process_name == rp.name:
        target = int(processing_indices("rRNA")[0])
        events = np.zeros(len(rp.unprocessed_rna_wids))
        events[target] = 1
        resources, _ = seed_processing(state, rp, events)
        sub, products, _ = processing_output_vectors(events)
        product_keys = processed_keys()
        precursor_key = rp.unprocessed_rna_wids[target]
    else:
        mapping, stoich, _ = modification_requirements()
        target = int(np.flatnonzero(mapping.sum(axis=0) == 1)[0])
        events = np.zeros(mapping.shape[1])
        events[target] = 1
        resources, _ = seed_modification(state, rm, events)
        sub = stoich @ mapping @ events
        products = events
        product_keys = wids(fixture("RNAModification"), "modifiedRNAWholeCellModelIDs")
        precursor_key = processed_keys()[target]
    proc = rp if process_name == rp.name else rm
    # This case intentionally allows constructor REQUESTS (never evolution):
    # first-tick freshness from zero grants is independently frozen above.
    state["substrates_allocated"][process_name] = dict.fromkeys(proc.substrate_wids, 0.0)
    engine = production_slice(composite, process_name, state)
    engine.update(1.0)
    first = engine.state.get_value()
    assert first["rna"]["counts"][precursor_key] == 0
    output_form = "counts" if process_name == rp.name else "modified_counts"
    exact_counts(vector(first["rna"][output_form], product_keys), products)
    exact_counts(vector(first["substrates"], proc.substrate_wids) - resources, sub)
    engine.update(1.0)
    second = engine.state.get_value()
    assert second["rna"] == first["rna"]
    exact_counts(
        vector(second["substrates"], proc.substrate_wids),
        vector(first["substrates"], proc.substrate_wids),
    )


@pytest.mark.parametrize("process_name", ["karr_rna_processing", "karr_rna_modification"])
def test_real_evolution_observes_current_tick_grants_not_previous_zero_grants(process_name):
    composite = builder(6)
    proc = composite["processes"][process_name]
    _, _, _, state = pathway()
    if process_name == "karr_rna_processing":
        events = np.zeros(len(proc.unprocessed_rna_wids))
        events[processing_indices("rRNA")[0]] = 1
        resources, _ = seed_processing(state, proc, events)
        precursor = proc.unprocessed_rna_wids[processing_indices("rRNA")[0]]
    else:
        mapping, _, _ = modification_requirements()
        target = int(np.flatnonzero(mapping.sum(axis=0) == 1)[0])
        events = np.zeros(mapping.shape[1])
        events[target] = 1
        resources, _ = seed_modification(state, proc, events)
        precursor = processed_keys()[target]
    state["rna"]["counts"][precursor] = 0.0
    state["substrates_allocated"][process_name] = dict.fromkeys(proc.substrate_wids, 0.0)
    engine = production_slice(composite, process_name, state)
    reads = []
    original = proc.next_update

    def observe_actual_inputs(timestep, states):
        reads.append(deepcopy(states.get("substrates_allocated", {}).get(process_name, {})))
        return original(timestep, states)

    # Observation only: original production next_update still computes every output.
    proc.next_update = observe_actual_inputs
    engine.state.set_value({"rna": {"counts": {precursor: 1.0}}})
    engine.update(1.0)
    assert np.any(resources > 0)
    assert reads, "real evolution was not called"
    exact_counts(vector(reads[0], proc.substrate_wids), resources)
