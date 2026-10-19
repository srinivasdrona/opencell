"""Source-backed RNA-form mass boundary, independent of statistical gates.

Rna.m:149-163,191-196 defines global row identity and form-specific MW.
RNAProcessing.m:353-367,456-487 and RNAModification.m:239-251,297-361,367-380
require nascent/processed/fragment/mature mass from those rows. Fixture MW
(numerically Da per molecule or g/mol) times molecule count / AVOGADRO gives
grams, using the existing runtime SI Avogadro authority. No trace outputs.

Real public RP/RM updates produce the tested state. A bounded Engine slice
retains the production observer class, parameters and topology; it does not
claim to test whole-chassis ordering or RNADecay consumption. Tiny gram values
require abs=0: pytest's default absolute tolerance would accept missing mass.
"""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from _rna_fidelity_helpers import (
    assert_modification_output,
    assert_processing_output,
    blank_state,
    fixture,
    seed_modification,
    seed_processing,
    vector,
    wids,
)
from vivarium.core.engine import Engine

from opencell.analysis.cell_mass import AVOGADRO
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_observability_step import KarrObservabilityStep
from scripts import l2_4_verify_conservation as conservation

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def production():
    return build_karr_chassis_v6(
        time_step_s=1.0,
        emit_step_s=1.0,
        enable_pool_replenishment=False,
    )


@pytest.fixture(scope="module")
def authority():
    fx = fixture("Rna")
    ids = wids(fx, "wholeCellModelIDs")
    mw = np.asarray(fx["molecularWeights"], dtype=float).reshape(-1)
    rows = {
        form: np.atleast_1d(fx[field]).astype(int) - 1
        for form, field in (
            ("nascent", "nascentIndexs"),
            ("processed", "processedIndexs"),
            ("intergenic", "intergenicIndexs"),
            ("mature", "matureIndexs"),
            ("bound", "boundIndexs"),
        )
    }
    with np.load(ROOT / "data" / "karr_fixtures" / "karr_native_m2.npz") as payload:
        gene_mw = np.asarray(payload["rna_molecular_weight"], dtype=float).reshape(-1)
    return {"ids": ids, "mw": mw, "rows": rows, "gene_mw": gene_mw}


def _apply_rna(state, update):
    for form, deltas in update.get("rna", {}).items():
        for key, delta in deltas.items():
            state["rna"].setdefault(form, {}).setdefault(key, 0.0)
            state["rna"][form][key] += delta


@pytest.fixture(scope="module")
def real_outputs(production, authority):
    rp = production.processes["karr_rna_processing"]
    rm = production.processes["karr_rna_modification"]
    state = blank_state(rp, rm)
    events = np.ones(len(rp.unprocessed_rna_wids))
    seed_processing(state, rp, events)
    before = deepcopy(state["rna"])
    rp_update = rp.next_update(1.0, state)
    assert_processing_output(rp_update, events)
    _apply_rna(state, rp_update)
    processed = deepcopy(state["rna"])
    flux = vector(processed["counts"], rp.processed_rna_wids)
    assert np.all(flux > 0)
    seed_modification(state, rm, flux)
    assert state["rna"] == processed, "RM inputs must be actual RP outputs"
    rm_update = rm.next_update(1.0, state)
    assert_modification_output(rm_update, flux)
    _apply_rna(state, rm_update)
    assert all(state["rna"]["counts"][key] == 0 for key in rm.processed_rna_wids)
    assert [authority["ids"][i] for i in authority["rows"]["nascent"]] == rp.unprocessed_rna_wids
    assert [authority["ids"][i] for i in authority["rows"]["mature"]] == rm.mature_rna_wids
    return {"nascent": before, "processed": processed, "mature": deepcopy(state["rna"])}


def _source_mass_g(rna, production, authority):
    rp = production.processes["karr_rna_processing"]
    rm = production.processes["karr_rna_modification"]
    total_da = 0.0
    for form, store, keys in (
        ("nascent", "counts", rp.unprocessed_rna_wids),
        ("processed", "counts", rp.processed_rna_wids),
        ("intergenic", "counts", rp.intergenic_rna_keys),
        ("mature", "modified_counts", rm.mature_rna_wids),
    ):
        rows = authority["rows"][form]
        assert len(keys) == len(rows)
        total_da += sum(
            rna.get(store, {}).get(key, 0.0) * authority["mw"][row]
            for key, row in zip(keys, rows, strict=True)
        )
    return total_da / AVOGADRO


def _engine_mass_g(production, rna, extra=None):
    name = "karr_observability_step"
    registered = production.steps[name]
    assert type(registered) is KarrObservabilityStep
    observer = type(registered)(dict(registered.parameters))
    state = {"rna": deepcopy(rna), **deepcopy(extra or {})}
    engine = Engine(
        steps={name: observer},
        topology={name: deepcopy(production.topology[name])},
        initial_state=state,
        display_info=False,
        emit_step=1.0,
    )
    engine.update(1.0)
    return engine.state.get_value()["phenotype_observables"]["rna_mass_g"]


def _check_mass(production, rna, expected, record_property):
    actual = _engine_mass_g(production, rna)
    record_property("expected_source_mass_g", float(expected))
    record_property("actual_production_mass_g", float(actual))
    assert expected > 0, "nonvacuous source molecule mass"
    assert actual == pytest.approx(expected, rel=1e-12, abs=0.0)


def test_registered_conservation_and_production_use_shared_observer(production):
    assert conservation.build_karr_chassis_v6 is build_karr_chassis_v6
    assert type(production.steps["karr_observability_step"]) is KarrObservabilityStep
    assert production.topology["karr_observability_step"]["rna"] == ("rna",)
    for name in ("karr_rna_processing", "karr_rna_modification"):
        assert production.topology[name]["rna"] == ("rna",)


@pytest.mark.parametrize("stage", ["nascent", "processed", "mature"])
def test_actual_rp_rm_handoff_has_source_form_mass(
    stage, production, authority, real_outputs, record_property
):
    rna = real_outputs[stage]
    _check_mass(
        production, rna, _source_mass_g(rna, production, authority), record_property
    )


def test_every_real_processed_alias_is_visible_with_processed_row_mw(
    production, authority, real_outputs, record_property
):
    rp = production.processes["karr_rna_processing"]
    aliases = [
        (key, row)
        for key, row in zip(rp.processed_rna_wids, authority["rows"]["processed"], strict=True)
        if key.startswith("processed::")
    ]
    assert aliases
    counts = {key: real_outputs["processed"]["counts"][key] for key, _ in aliases}
    assert all(count > 0 for count in counts.values())
    expected = sum(counts[key] * authority["mw"][row] for key, row in aliases) / AVOGADRO
    record_property("processed_alias_count", len(aliases))
    _check_mass(production, {"counts": counts}, expected, record_property)
    for key, row in aliases:
        _check_mass(
            production,
            {"counts": {key: counts[key]}},
            counts[key] * authority["mw"][row] / AVOGADRO,
            record_property,
        )


def test_real_fragment_output_has_all_global_row_masses(
    production, authority, real_outputs, record_property
):
    rp = production.processes["karr_rna_processing"]
    counts = {key: real_outputs["processed"]["counts"][key] for key in rp.intergenic_rna_keys}
    assert all(count > 0 for count in counts.values())
    expected = sum(
        counts[key] * authority["mw"][row]
        for key, row in zip(rp.intergenic_rna_keys, authority["rows"]["intergenic"], strict=True)
    ) / AVOGADRO
    record_property("distinct_fragment_rows", len(counts))
    _check_mass(production, {"counts": counts}, expected, record_property)


def test_duplicate_biological_fragment_wids_keep_individual_row_weights(
    production, authority, real_outputs, record_property
):
    rp = production.processes["karr_rna_processing"]
    groups = defaultdict(list)
    for key, row in zip(rp.intergenic_rna_keys, authority["rows"]["intergenic"], strict=True):
        groups[authority["ids"][row]].append((key, row))
    duplicate_rows = next(
        group
        for group in groups.values()
        if len(group) > 1 and len({authority["mw"][row] for _, row in group}) > 1
    )
    assert len({key for key, _ in duplicate_rows}) == len(duplicate_rows)
    for key, row in duplicate_rows:
        count = real_outputs["processed"]["counts"][key]
        assert count > 0
        _check_mass(
            production,
            {"counts": {key: count}},
            count * authority["mw"][row] / AVOGADRO,
            record_property,
        )
    declared = production.steps["karr_observability_step"].ports_schema()["rna"]["counts"]
    assert all(key in declared for key, _ in duplicate_rows)


@pytest.mark.parametrize("form", ["counts", "modified_counts", "aminoacylated_counts"])
def test_legacy_gene_forms_and_bound_views_do_not_lose_or_duplicate_mass(
    form, production, authority, record_property
):
    observer = production.steps["karr_observability_step"]
    gene_ids = list(observer.m2_model.gene_wcm_ids)
    assert len(gene_ids) == len(authority["gene_mw"])
    # Gene-split legacy mRNAs and source TU/form rows are different representations.
    legacy = [
        (key, mw)
        for key, mw in zip(gene_ids, authority["gene_mw"], strict=True)
        if key not in set(authority["ids"])
    ]
    assert legacy
    rna = {form: dict.fromkeys((key for key, _ in legacy), 1.0)}
    expected = sum(mw for _, mw in legacy) / AVOGADRO
    _check_mass(production, rna, expected, record_property)
    mature_rows = authority["rows"]["mature"]
    bound_rows = authority["rows"]["bound"]
    np.testing.assert_array_equal(authority["mw"][mature_rows], authority["mw"][bound_rows])
    # Existing boundEnzymes is a protein/complex occupancy view, not extra RNA.
    # Do not invent a new bound-RNA store or count a bound view as new molecules.
    extra = {"boundEnzymes": dict.fromkeys(production.initial_state["boundEnzymes"], 1.0)}
    assert extra["boundEnzymes"]
    assert _engine_mass_g(production, rna, extra) == pytest.approx(expected, rel=1e-12, abs=0.0)
