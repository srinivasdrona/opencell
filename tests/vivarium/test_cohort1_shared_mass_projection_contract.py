"""Finite source-state mass boundary; deliberately RED before implementation.

NOT an L2 output-oracle/distribution gate or a natural-trajectory claim.
ProteinMonomer.m:95-130 and Rna.m:149-196 supply form rows and MW;
ProteinComplex.m:101-120 and ProteinActivation.m:235-310 also supply
already-present mature/physical inactive complex stocks, not activity views.
MoleculeCountState.m:86-92 supplies count * MW / Avogadro in grams.
UNIT baskets exercise existing axes, never enlarge production pools. Public
PT/PP2/RP/RM updates additionally establish bounded reachable output states.
The three live readers must see the same physical pools, not cached phenotype
outputs, mature-only protein views, or separately counted bound-enzyme views.
"""

from __future__ import annotations

import csv
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.constants import Avogadro

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _rna_fidelity_helpers as rna_inputs
import test_karr_protein_processing_ii_fidelity as pp2_inputs
import test_rna_total_mass_consumer_contract as frozen_total
from vivarium.core.engine import Engine

import opencell
from opencell.analysis.cell_mass import compute_cell_mass
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_observability_step import KarrObservabilityStep
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.protein_state import COMPARTMENTS, FORMS, MIGRATED_WIDS
from scripts import run_chassis_v6_32400t as csv_runner

for module in (opencell, csv_runner, sys.modules[compute_cell_mass.__module__]):
    assert Path(module.__file__).resolve().is_relative_to(ROOT), "wrong worktree import"

READERS = ("helper", "observer", "csv")
FORM_FIELDS = {
    "nascent": "nascentIndexs",
    "processed_i": "processedIIndexs",
    "processed_ii": "processedIIIndexs",
    "signal_sequence": "signalSequenceIndexs",
    "folded": "foldedIndexs",
    "mature": "matureIndexs",
    "inactivated": "inactivatedIndexs",
    "bound": "boundIndexs",
    "misfolded": "misfoldedIndexs",
    "damaged": "damagedIndexs",
}
# Actual existing producers/consumers, not suffix/prefix aliases. The flat
# nonmigrated counts compatibility input keeps its existing mature m3 meaning.
QUEUE_SOURCES = {
    "unprocessed_counts": ("ProteinProcessingI", "unprocessedMonomerWholeCellModelIDs", "nascent"),
    "processed_counts": ("ProteinProcessingII", "unprocessedMonomerWholeCellModelIDs", "processed_i"),
    "unfolded_counts": ("ProteinProcessingII", "processedMonomerWholeCellModelIDs", "processed_ii"),
    "signal_sequence_counts": ("ProteinProcessingII", "signalSequenceMonomerWholeCellModelIDs", "signal_sequence"),
    "unmodified_counts": ("ProteinModification", "unmodifiedMonomerWholeCellModelIDs", "folded"),
    "modified_counts": ("ProteinModification", "modifiedMonomerWholeCellModelIDs", "mature"),
}
ACTIVATION_STORES = {
    "activation_active_noncytosol_counts": "mature",
    "activation_inactive_counts": "inactivated",
}


@pytest.fixture(scope="module")
def contract():
    legacy = frozen_total.contract.__wrapped__()
    charged_keys = rna_inputs.wids(
        rna_inputs.fixture("tRNAAminoacylation"), "aminoacylatedRNAWholeCellModelIDs",
    )
    assert set(charged_keys) == set(legacy["base"]["rna"]["aminoacylated_counts"])
    assert set(charged_keys) <= set(legacy["weights"]["aminoacylated_counts"])
    unit_rna_keys = {
        store: tuple(weights) if store != "aminoacylated_counts" else tuple(charged_keys)
        for store, weights in legacy["weights"].items()
    }
    fx = rna_inputs.fixture("ProteinMonomer")
    ids = rna_inputs.wids(fx, "wholeCellModelIDs")
    mw = np.asarray(fx["molecularWeights"], dtype=float).reshape(-1)
    rows = {
        form: np.atleast_1d(fx[field]).astype(int) - 1
        for form, field in FORM_FIELDS.items()
    }
    protein = {
        form: dict(zip((ids[row] for row in indices), mw[indices], strict=True))
        for form, indices in rows.items()
    }
    assert set(FORMS) == set(protein)
    assert np.asarray(fx["counts"]).shape == (len(ids), len(COMPARTMENTS))
    assert np.all(np.isfinite(mw)) and np.all(mw >= 0), "zero signal MW is legitimate"
    assert all(len(set(ids[row] for row in indices)) == len(indices) for indices in rows.values())
    pt = rna_inputs.fixture("ProteinTranslocation")
    toa = rna_inputs.fixture("TerminalOrganelleAssembly")
    pt_ids = rna_inputs.wids(pt, "monomerWholeCellModelIDs")
    enrolled = set(rna_inputs.wids(toa, "substrateWholeCellModelIDs")) | {
        pt_ids[i] for i in np.atleast_1d(pt["monomerIndexs_translocating"]).astype(int) - 1
    }
    assert enrolled == set(MIGRATED_WIDS)
    queues = {}
    for store, (name, field, form) in QUEUE_SOURCES.items():
        keys = rna_inputs.wids(rna_inputs.fixture(name), field)
        assert set(keys) <= set(protein[form])
        queues[store] = {key: protein[form][key] for key in keys if key not in enrolled}
    # These two incumbent branches are physical monomer pools, unlike
    # protein.activity/enzyme_counts. Pin their three actual current owners
    # by one fixture/global-row comparison, not a new migration.
    activation_fx = rna_inputs.fixture("ProteinActivation")
    activation_ids = rna_inputs.wids(activation_fx, "substrateWholeCellModelIDs")
    activation_rows = np.atleast_1d(activation_fx["substrateMonomerLocalIndexs"]).astype(int) - 1
    activation_global = np.asarray(activation_fx["substrateMonomerGlobalIndexs"]).astype(int) - 1
    source_activation = {}
    for local, global_rows in zip(activation_rows, activation_global, strict=True):
        wid = activation_ids[local]
        assert np.all(global_rows == global_rows[0])
        assert ids[rows["mature"][global_rows[0]]] == wid
        source_activation[wid] = int(global_rows[0])
    activation = {}
    for store, form in ACTIVATION_STORES.items():
        owners = legacy["base"]["protein"][store]
        assert set(owners) <= set(source_activation)
        assert not set(owners) & enrolled, "do not create a second canonical authority"
        activation[store] = {
            wid: {"mw": protein[form][wid], "compartments": tuple(by_comp)}
            for wid, by_comp in owners.items()
        }
    # Compare rows to m3 rather than treating the reader's MW lookup as authority.
    np.testing.assert_allclose(
        [protein["mature"][wid] for wid in legacy["models"][2].protein_wcm_ids],
        legacy["models"][2].molecular_weight, rtol=1e-12, atol=0,
    )
    complex_fx = rna_inputs.fixture("ProteinComplex")
    complex_ids = rna_inputs.wids(complex_fx, "wholeCellModelIDs")
    complex_mw = np.asarray(complex_fx["molecularWeights"], dtype=float).reshape(-1)
    complex_rows = {
        form: np.atleast_1d(complex_fx[field]).astype(int) - 1
        for form, field in (("mature", "matureIndexs"), ("inactivated", "inactivatedIndexs"))
    }
    assert np.all(np.isfinite(complex_mw)) and np.all(complex_mw >= 0)
    assert np.asarray(complex_fx["counts"]).shape == (len(complex_ids), len(COMPARTMENTS))
    complex_forms = {
        form: dict(zip((complex_ids[row] for row in indices), complex_mw[indices], strict=True))
        for form, indices in complex_rows.items()
    }
    assert not set(complex_forms["mature"]) & set(protein["mature"]), "do not count monomer aliases twice"
    clocal = np.atleast_1d(activation_fx["substrateComplexLocalIndexs"]).astype(int) - 1
    cglobal = np.asarray(activation_fx["substrateComplexGlobalIndexs"]).astype(int) - 1
    ccolumns = np.asarray(activation_fx["substrateComplexCompartmentIndexs"]).astype(int) - 1
    source_complex_owners = {}
    for local, global_row, columns in zip(clocal, cglobal, ccolumns, strict=True):
        wid = activation_ids[local]
        assert np.all(global_row == global_row[0])
        assert complex_ids[complex_rows["mature"][global_row[0]]] == wid
        source_complex_owners[wid] = tuple(str(comp) for comp in columns)
        for form, field in (("mature", "substrates"), ("inactivated", "inactivatedSubstrates")):
            np.testing.assert_array_equal(
                complex_fx["counts"][complex_rows[form][global_row[0]], :],
                activation_fx[field][local, :],
            )
    complex_activation = {}
    for store, form in ACTIVATION_STORES.items():
        owners = legacy["base"]["complex"][store]
        assert set(owners) <= set(source_complex_owners)
        complex_activation[store] = {}
        for wid, by_comp in owners.items():
            index = activation_ids.index(wid)
            columns = source_complex_owners[wid]
            columns = columns[1:] if form == "mature" else columns
            assert set(by_comp) <= set(columns)
            seed = activation_fx["substrates" if form == "mature" else "inactivatedSubstrates"][index]
            assert legacy["base"]["complex"]["counts"][wid] == activation_fx["substrates"][index, 0]
            for comp, count in by_comp.items():
                assert count == seed[int(comp)]
            complex_activation[store][wid] = {
                "mw": complex_forms[form][wid], "compartments": tuple(by_comp),
            }
    return {**legacy, "protein_forms": protein, "queues": queues, "activation": activation,
            "unit_rna_keys": unit_rna_keys, "charged_keys": charged_keys, "enrolled": enrolled,
            "protein_rows": rows, "protein_fixture": fx,
            "complex_forms": complex_forms, "complex_activation": complex_activation,
            "complex_rows": complex_rows, "complex_fixture": complex_fx}


def _empty(contract):
    state = deepcopy(contract["base"])
    state["substrates"] = dict.fromkeys(state["substrates"], 0.0)
    state["rna"] = {store: {} for store in contract["weights"]}
    protein = state["protein"]
    for store in ("counts", *QUEUE_SOURCES, "enzyme_counts"):
        protein[store] = {}
    for store in ACTIVATION_STORES:
        protein[store] = {}
    protein["compartment_counts"] = {
        form: {wid: dict.fromkeys(COMPARTMENTS, 0.0) for wid in sorted(contract["enrolled"])}
        for form in FORMS
    }
    # These baskets isolate RNA/monomer material. The unchanged full/mixed
    # cases copy base directly and retain every physical complex stock.
    complexes = state["complex"]
    for wid in complexes["counts"]:
        if wid in contract["complex_forms"]["mature"]:
            complexes["counts"][wid] = 0.0
    for store, owners in contract["complex_activation"].items():
        for wid, by_comp in complexes.get(store, {}).items():
            if wid in owners:
                for comp in by_comp:
                    by_comp[comp] = 0.0
    state.pop("phenotype_observables", None)
    return state


def _expected(state, contract):
    rna_da = sum(
        float(count) * contract["weights"][store].get(key, 0.0)
        for store in contract["weights"]
        for key, count in state.get("rna", {}).get(store, {}).items()
    )
    sub_da = sum(
        float(count) * contract["substrate"].get(key, 0.0)
        for key, count in state.get("substrates", {}).items()
    )
    protein = state.get("protein", {})
    canonical = protein.get("compartment_counts", {})
    # Only enrollment makes a flat mature WID a derived view. A legacy-only
    # input without a canonical pool remains valid; no global migration.
    prot_da = sum(
        float(count) * contract["protein_forms"]["mature"].get(key, 0.0)
        for key, count in protein.get("counts", {}).items()
        if not canonical or key not in contract["enrolled"]
    )
    for form, by_wid in canonical.items():
        for wid, by_comp in by_wid.items():
            assert wid in contract["enrolled"] and form in contract["protein_forms"]
            assert set(by_comp) <= set(COMPARTMENTS)
            prot_da += sum(map(float, by_comp.values())) * contract["protein_forms"][form][wid]
    for store, weights in contract["queues"].items():
        prot_da += sum(
            float(count) * weights[key]
            for key, count in protein.get(store, {}).items()
            if key in weights
        )
    for store, owners in contract["activation"].items():
        for wid, by_comp in protein.get(store, {}).items():
            if wid in owners:
                assert set(by_comp) <= set(owners[wid]["compartments"])
                prot_da += sum(map(float, by_comp.values())) * owners[wid]["mw"]
    complexes = state.get("complex", {})
    mature_complex_mw = contract["complex_forms"]["mature"]
    prot_da += sum(
        float(count) * mature_complex_mw[wid]
        for wid, count in complexes.get("counts", {}).items()
        if wid in mature_complex_mw
    )
    for store, owners in contract["complex_activation"].items():
        for wid, by_comp in complexes.get(store, {}).items():
            if wid in owners:
                assert set(by_comp) <= set(owners[wid]["compartments"])
                prot_da += sum(map(float, by_comp.values())) * owners[wid]["mw"]
    values = dict(zip(("rna", "substrate", "protein"),
                      (x / Avogadro for x in (rna_da, sub_da, prot_da)), strict=True))
    return {**values, "total": sum(values.values())}


def _observer(state, contract):
    models = contract["models"]
    observer = KarrObservabilityStep(dict(zip(("m1_model", "m2_model", "m3_model"), models, strict=True)))
    seen = []
    original = observer.next_update

    def capture(dt, inputs):
        seen.append(deepcopy(inputs))
        return original(dt, inputs)

    observer.next_update = capture
    # Genuine production Step, topology and Engine port projection. No manually
    # passing a full state into next_update to circumvent undeclared reads.
    engine = Engine(
        steps={"karr_observability_step": observer},
        topology={"karr_observability_step": {
            name: (name,) for name in observer.ports_schema()
        }},
        initial_state=deepcopy(state), display_info=False, emit_step=1.0,
    )
    engine.update(1.0)
    assert seen
    return engine.state.get_value()["phenotype_observables"], seen[-1], observer.ports_schema()


def _read(reader, state, contract):
    if reader == "helper":
        result = compute_cell_mass(state, *contract["models"])
        return {"rna": result.rna_mass_g, "substrate": result.substrate_mass_g,
                "protein": result.protein_mass_g, "total": result.total_g}
    if reader == "observer":
        result, _, _ = _observer(state, contract)
        return {"rna": result["rna_mass_g"], "protein": result["protein_mass_g"],
                "total": result.get("cell_dry_mass_g")}
    return {"total": csv_runner.MassEstimator.build(*contract["models"]).dry_mass_g(state)}


def _compare(reader, state, contract, label, record_property):
    expected = _expected(state, contract)
    before = deepcopy(state)
    actual = _read(reader, state, contract)
    np.testing.assert_equal(state, before)
    mismatches = []
    for component, value in actual.items():
        record_property(f"{label}.{reader}.{component}.source_g", expected[component])
        record_property(f"{label}.{reader}.{component}.actual_g", value)
        if value is None or not np.isclose(value, expected[component], rtol=1e-12, atol=0):
            mismatches.append(
                f"{label}/{reader}/{component}: actual={value!r}, "
                f"source_g={expected[component]:.17g}"
            )
    return mismatches


@pytest.mark.parametrize("reader", READERS)
def test_UNIT_complete_canonical_form_compartment_matrix(reader, contract, record_property):
    failures = []
    # Form-isolated full matrices prevent a mature-only lookup, averaging form
    # weights, or summing just one compartment from passing an aggregate test.
    for form in FORMS:
        state = _empty(contract)
        for row in state["protein"]["compartment_counts"][form].values():
            row.update(dict.fromkeys(COMPARTMENTS, 1.0))
        assert _expected(state, contract)["protein"] > 0
        failures += _compare(reader, state, contract, f"UNIT_{form}_all_compartments", record_property)
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("reader", READERS)
def test_UNIT_same_wid_distinct_forms_and_poisoned_flat_authority(reader, contract, record_property):
    state = _empty(contract)
    wid = next(wid for wid in sorted(contract["enrolled"])
               if contract["protein_forms"]["processed_i"][wid] != contract["protein_forms"]["mature"][wid])
    state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 1.0
    state["protein"]["compartment_counts"]["mature"][wid]["m"] = 1.0
    expected = _expected(state, contract)["protein"]
    assert expected == (contract["protein_forms"]["processed_i"][wid]
                        + contract["protein_forms"]["mature"][wid]) / Avogadro
    failures = []
    for shadow in (0.0, 1.0, float("nan")):
        state["protein"]["counts"][wid] = shadow
        # Migrated legacy queue shadows and bound-enzyme views are not pools.
        for store in QUEUE_SOURCES:
            state["protein"][store][wid] = float("nan")
        state["protein"]["enzyme_counts"][wid] = float("nan")
        state["boundEnzymes"] = {wid: float("nan")}
        failures += _compare(reader, state, contract, f"UNIT_shadow_{shadow}", record_property)
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("reader", READERS)
def test_existing_nonmigrated_form_queues_use_actual_source_rows(reader, contract, record_property):
    failures = []
    for store, weights in contract["queues"].items():
        state = _empty(contract)
        state["protein"][store] = dict.fromkeys(weights, 1.0)
        # Zero signal rows are valid (most nonmigrated signal sequences are absent).
        failures += _compare(reader, state, contract, f"UNIT_legacy_{store}", record_property)
    for store, owners in contract["activation"].items():
        state = _empty(contract)
        state["protein"][store] = {
            wid: dict.fromkeys(owner["compartments"], 1.0)
            for wid, owner in owners.items()
        }
        failures += _compare(reader, state, contract, f"UNIT_incumbent_{store}", record_property)
    # Preserve standalone historical mature inputs, including migrated WIDs,
    # when the canonical pool is not present at all.
    state = _empty(contract)
    state["protein"].pop("compartment_counts")
    state["protein"]["counts"] = dict.fromkeys(contract["protein_forms"]["mature"], 1.0)
    failures += _compare(reader, state, contract, "legacy_only_mature", record_property)
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("case", ("rp_fragments", "rm_mature", "all_represented_rna"))
def test_actual_rna_products_and_all_existing_form_keys(reader, case, contract, record_property):
    state = _empty(contract)
    if case == "all_represented_rna":
        # UNIT basis includes every represented source row, actual charged
        # product WIDs and nonoverlapping historical gene keys; no new store.
        state["rna"] = {store: dict.fromkeys(keys, 1.0)
                        for store, keys in contract["unit_rna_keys"].items()}
    else:
        state["rna"] = deepcopy(contract["cases"][case])
    expected = _expected(state, contract)
    assert expected["rna"] > 0
    failures = _compare(reader, state, contract, case, record_property)
    # The observer's already-correct RNA component is a positive control;
    # its missing new shared total field is tested separately.
    if reader == "observer":
        failures = [failure for failure in failures if "/total:" not in failure]
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("reader", ("helper", "csv"))
def test_full_mixed_state_without_any_observer_or_cached_answers(
    reader, contract, monkeypatch, record_property,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("standalone mass reader constructed or updated observer")

    monkeypatch.setattr(KarrObservabilityStep, "__init__", forbidden)
    monkeypatch.setattr(KarrObservabilityStep, "next_update", forbidden)
    state = deepcopy(contract["base"])
    state["rna"] = deepcopy(contract["cases"]["mixed_forms"])
    wid = next(iter(sorted(contract["enrolled"])))
    state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 1.0
    failures = []
    for hint in (None, 0.0, float("nan")):
        state.pop("phenotype_observables", None)
        if hint is not None:
            state["phenotype_observables"] = dict.fromkeys(
                ("rna_mass_g", "protein_mass_g", "cell_dry_mass_g"), hint,
            )
        failures += _compare(reader, state, contract, f"mixed_cache_{hint}", record_property)
    assert not failures, "\n".join(failures)


def test_observer_mixed_rna_protein_substrate_total_is_source_mass(contract, record_property):
    state = deepcopy(contract["base"])
    state["rna"] = deepcopy(contract["cases"]["mixed_forms"])
    wid = next(iter(sorted(contract["enrolled"])))
    state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 1.0
    state["phenotype_observables"] = {"cell_dry_mass_g": float("nan")}
    expected = _expected(state, contract)
    assert all(expected[component] > 0 for component in ("rna", "substrate", "protein"))
    failures = _compare("observer", state, contract, "mixed_full_state", record_property)
    assert not failures, "\n".join(failures)


def test_observer_actual_engine_ports_see_all_source_authorities(contract, record_property):
    production = build_karr_chassis_v6(
        time_step_s=1.0, emit_step_s=1.0, enable_pool_replenishment=False,
    )
    assert type(production.steps["karr_observability_step"]) is KarrObservabilityStep
    assert production.topology["karr_observability_step"]["protein"] == ("protein",)
    assert production.topology["karr_observability_step"]["rna"] == ("rna",)
    state = _empty(contract)
    for by_wid in state["protein"]["compartment_counts"].values():
        for row in by_wid.values():
            row.update(dict.fromkeys(COMPARTMENTS, 1.0))
    for store, weights in contract["queues"].items():
        state["protein"][store] = dict.fromkeys(weights, 1.0)
    for store, owners in contract["activation"].items():
        state["protein"][store] = {
            wid: dict.fromkeys(owner["compartments"], 1.0)
            for wid, owner in owners.items()
        }
    state["rna"] = {store: dict.fromkeys(keys, 1.0)
                    for store, keys in contract["unit_rna_keys"].items()}
    result, seen, schema = _observer(state, contract)
    missing = []
    for form, by_wid in state["protein"]["compartment_counts"].items():
        for wid, row in by_wid.items():
            for comp, count in row.items():
                value = seen.get("protein", {}).get("compartment_counts", {}).get(form, {}).get(wid, {}).get(comp)
                if value != count:
                    missing.append(("compartment_counts", form, wid, comp))
    for store, weights in contract["queues"].items():
        for wid in weights:
            if seen.get("protein", {}).get(store, {}).get(wid) != 1:
                missing.append((store, wid))
    for store, owners in contract["activation"].items():
        for wid, owner in owners.items():
            for comp in owner["compartments"]:
                if seen.get("protein", {}).get(store, {}).get(wid, {}).get(comp) != 1:
                    missing.append((store, wid, comp))
    for store, keys in contract["unit_rna_keys"].items():
        assert all(seen["rna"][store][wid] == 1 for wid in keys)
    record_property("missing_actual_engine_leaves", len(missing))
    failures = _compare("observer", state, contract, "full_engine_basket", record_property)
    assert not missing and not failures and "cell_dry_mass_g" in schema["phenotype_observables"], (
        f"Engine hidden physical leaves={len(missing)} first={missing[:3]}; " + "\n".join(failures)
        + f"; observer fields={tuple(result)}"
    )


def _apply(state, update):
    for key, delta in update.items():
        if isinstance(delta, dict):
            _apply(state.setdefault(key, {}), delta)
        else:
            assert np.isfinite(delta) and delta == round(delta), "nonintegral public count delta"
            state[key] = state.get(key, 0.0) + delta


@pytest.mark.parametrize("process", ("PT", "PP2"))
def test_public_protein_transitions_reach_source_weighted_mass(process, contract, record_property):
    if process == "PP2":
        proc, _ = pp2_inputs._pair()
        state = _empty(contract)
        seeded = pp2_inputs._state(supply=1.0)
        state["protein"] = seeded["protein"]
        state["substrates"].update(seeded["substrates"])
        state["substrates_allocated"] = {}
        index = int(pp2_inputs._indices("lipoproteinMonomerIndexs")[0])
        pp2_inputs._precursor(state, index, 1.0)
        pp2_inputs._grant(state, proc, 1.0)
        update = proc.next_update(1.0, state)
        pp2_inputs._transition(update, index, 1)
    else:
        proc = KarrProteinTranslocationProcess({"rng_seed": 0})
        fx = rna_inputs.fixture("ProteinTranslocation")
        state = _empty(contract)
        state["substrates_allocated"] = {
            proc.name: dict(zip(rna_inputs.wids(fx, "substrateWholeCellModelIDs"),
                               map(float, np.asarray(fx["substrates"]).reshape(-1)), strict=True))
        }
        for field, store in (("enzymeMonomerLocalIndexs", "protein"),
                             ("enzymeComplexLocalIndexs", "complex")):
            for i in np.atleast_1d(fx[field]).astype(int) - 1:
                state[store]["counts"][rna_inputs.wids(fx, "enzymeWholeCellModelIDs")[i]] = float(fx["enzymes"][i])
        wid = proc.translocatable_wids[0]
        state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 1.0
        update = proc.next_update(1.0, state)
        changes = update.get("protein", {}).get("compartment_counts", {}).get("processed_i", {}).get(wid, {})
        assert changes.get("c") == -1 and sum(changes.values()) == 0, "PT must actually translocate"
    _apply(state, update)
    failures = []
    for reader in READERS:
        failures += _compare(reader, state, contract, f"public_{process}_after", record_property)
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("reader", READERS)
def test_zero_missing_unknown_inputs_and_valid_zero_signal_weights(reader, contract, record_property):
    failures = []
    for state in ({}, _empty(contract)):
        failures += _compare(reader, state, contract, "empty_inputs", record_property)
    state = _empty(contract)
    zero_wid = next(wid for wid in sorted(contract["enrolled"])
                    if contract["protein_forms"]["signal_sequence"][wid] == 0)
    state["protein"]["compartment_counts"]["signal_sequence"][zero_wid]["c"] = 1.0
    state["protein"]["counts"]["not_a_source_WID"] = 1.0
    state["substrates"]["not_a_source_WID"] = 1.0
    state["rna"]["counts"]["not_a_source_WID"] = 1.0
    failures += _compare(reader, state, contract, "source_zero_MW", record_property)
    assert not failures, "\n".join(failures)


def test_real_local_writer_loop_emits_estimated_mass_and_unchanged_conversions(
    contract, monkeypatch, tmp_path, record_property,
):
    # Mock only expensive biology/diagnostics and metadata. The actual runtime
    # state snapshot, estimator, nested write_key_row, and CSV formatting run.
    state = _empty(contract)
    state["rna"] = deepcopy(contract["cases"]["mixed_forms"])
    wid = next(iter(sorted(contract["enrolled"])))
    state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 1.0
    state["protein"]["counts"][wid] = float("nan")
    state["phenotype_observables"] = {"cell_dry_mass_g": float("nan")}
    expected = _expected(state, contract)["total"]
    models = contract["models"]
    for module, model in zip((csv_runner.km, csv_runner.tx, csv_runner.tl), models, strict=True):
        monkeypatch.setattr(module, "load_default", lambda model=model: model)
    probe = SimpleNamespace(processes={
        "karr_metabolism": SimpleNamespace(parameters={"time_step": 1.0}),
        "karr_translation": SimpleNamespace(aa_ids=()),
    })
    monkeypatch.setattr(csv_runner, "build_karr_chassis_v6", lambda **kwargs: probe)

    class Snapshot:
        def get_path(self, path):
            return SimpleNamespace(get_value=lambda: deepcopy(state.get(path[0], {})))

    class BoundedEngine:
        def __init__(self, **kwargs) -> None:
            self.state = Snapshot()

        def update(self, dt):
            assert dt == 1.0

    monkeypatch.setattr(csv_runner, "Engine", BoundedEngine)
    monkeypatch.setattr(csv_runner, "DiagnosticCollector", lambda **kwargs: SimpleNamespace(
        set_tick=lambda tick: None, close=lambda: None, exception_counts={},
    ))
    monkeypatch.setattr(csv_runner, "build_e2_payload", lambda *args, **kwargs: {})
    monkeypatch.setattr(csv_runner, "write_payload", lambda *args: None)
    monkeypatch.setattr(csv_runner, "_git", lambda *args: None)  # never WSL Git on linked .git
    monkeypatch.setattr(csv_runner.random, "seed", lambda *args: None)
    monkeypatch.setattr(csv_runner.np.random, "seed", lambda *args: None)  # no process-global RNG mutation
    manifest = csv_runner.run_full_cycle(
        out_dir=tmp_path, log_path=tmp_path / "progress.log", seed=0,
        biological_seconds=1.0, full_stride=1, conservation_stride=2,
        process_trace_stride=1, memory_retry_attempts=0, memory_retry_sleep_s=0,
    )
    assert manifest["ticks_completed"] == 1
    with (tmp_path / "key_substrates.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert [int(row["tick"]) for row in rows] == [0, 1], "actual writer loop must execute"
    estimator = csv_runner.MassEstimator.build(*models)
    import json
    parameters = json.loads((ROOT / "data/karr_fixtures/parameters.json").read_text())
    dry_fraction = 1.0 - parameters["states"]["Mass"]["fractionWetWeight"]
    density = parameters["states"]["Geometry"]["density"]
    assert estimator.total_mass_g(expected) == expected / dry_fraction
    assert estimator.volume_l(expected / dry_fraction) == expected / dry_fraction / density
    failures = []
    for row in rows:
        for column, value in (
            ("cell_dry_mass_g", expected),
            ("cell_total_mass_g", expected / dry_fraction),
            ("cell_volume_L", expected / dry_fraction / density),
        ):
            actual = float(row[column])
            record_property(f"CSV_tick{row['tick']}.{column}.source", value)
            record_property(f"CSV_tick{row['tick']}.{column}.actual", actual)
            if not np.isclose(actual, value, rtol=1e-10, atol=0):
                failures.append(f"tick={row['tick']} {column}: actual={actual!r}, source={value:.17g}")
    assert not failures, "\n".join(failures)
