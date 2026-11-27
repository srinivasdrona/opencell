"""Freeze actual total-mass consumers, not the old whole-cell target ratio.

Established authority: Rna.m:149-163,191-196 and MoleculeCountState.m:86-92;
numeric MW comes from unchanged fixtures. Actual public RP/RM output counts
are reused from the frozen producer helper. Counts are never scaled up to
make tiny gram differences visible: all mass comparisons use abs=0.

The v5 full-state fixture has no observer. Stale/poisoned phenotype sidecars
must not change compute_cell_mass or the production extractor's computed
cell_dry_mass_g. The extractor's separately forwarded RNA sidecar field is
not redefined by this contract.
"""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import test_rna_form_mass_observability_contract as frozen

from opencell.analysis.cell_mass import compute_cell_mass
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import build_karr_chassis_v5
from opencell.vivarium.karr_observability_step import KarrObservabilityStep
from scripts.phase_e1_real_match import _extract_observables

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def contract():
    models = (km.load_default(), tx.load_default(), tl.load_default())
    chassis = build_karr_chassis_v5(
        time_step_s=1.0, emit_step_s=1.0, enable_pool_replenishment=False
    )
    assert "karr_observability_step" not in chassis.steps
    base = deepcopy(chassis.initial_state)
    authority = frozen.authority.__wrapped__()
    products = frozen.real_outputs.__wrapped__(chassis, authority)
    rp = chassis.processes["karr_rna_processing"]
    rm = chassis.processes["karr_rna_modification"]
    rows = authority["rows"]
    fx = frozen.fixture("Rna")
    charged_rows = np.atleast_1d(fx["aminoacylatedIndexs"]).astype(int) - 1
    legacy = dict(zip(models[1].gene_wcm_ids, authority["gene_mw"], strict=True))
    source = {"counts": {}, "modified_counts": {}, "aminoacylated_counts": {}}
    for store, keys, indices in (
        ("counts", rp.unprocessed_rna_wids, rows["nascent"]),
        ("counts", rp.processed_rna_wids, rows["processed"]),
        ("counts", rp.intergenic_rna_keys, rows["intergenic"]),
        ("modified_counts", rm.mature_rna_wids, rows["mature"]),
        ("aminoacylated_counts", [authority["ids"][i] for i in charged_rows], charged_rows),
    ):
        assert len(set(keys)) == len(keys) == len(indices)
        assert not set(keys) & set(source[store])
        source[store].update(
            (key, float(authority["mw"][row]))
            for key, row in zip(keys, indices, strict=True)
        )
    weights = {store: {**legacy, **values} for store, values in source.items()}
    with np.load(ROOT / "data" / "karr_fixtures" / "karr_native_m1.npz") as native:
        sub_mw = np.asarray(native["substrate_molecular_weight"], dtype=float).reshape(-1)
    substrate = dict(zip(models[0].raw["ids"]["substrate_wcm_585"], sub_mw, strict=True))
    protein = dict(zip(models[2].protein_wcm_ids, models[2].molecular_weight, strict=True))
    fragments = {
        key: products["processed"]["counts"][key] for key in rp.intergenic_rna_keys
    }
    aliases = {
        key: products["processed"]["counts"][key]
        for key in rp.processed_rna_wids
        if key.startswith("processed::")
    }
    mature = dict(products["mature"]["modified_counts"])
    mixed = deepcopy(products["processed"])
    mixed["modified_counts"] = mature
    # Preserve actual chassis charged pools; do not manufacture extra copies.
    mixed["aminoacylated_counts"] = deepcopy(base["rna"]["aminoacylated_counts"])
    assert any(value > 0 for value in mixed["aminoacylated_counts"].values())
    assert all(value > 0 for value in fragments.values())
    assert all(value > 0 for value in aliases.values())
    duplicate = next(
        [(key, row) for key, row in zip(rp.intergenic_rna_keys, rows["intergenic"], strict=True)
         if authority["ids"][row] == wid]
        for wid in dict.fromkeys(authority["ids"][row] for row in rows["intergenic"])
        if sum(authority["ids"][row] == wid for row in rows["intergenic"]) > 1
    )
    assert len({authority["mw"][row] for _, row in duplicate}) > 1
    return {
        "models": models, "base": base, "weights": weights,
        "substrate": substrate, "protein": protein, "source": source,
        "duplicate": duplicate, "fragments": fragments,
        "cases": {
            "rp_fragments": {"counts": fragments},
            "rp_processed_aliases": {"counts": aliases},
            "rm_mature": {"modified_counts": mature},
            "mixed_forms": mixed,
        },
    }


@pytest.fixture(autouse=True)
def no_observer_runtime(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("standalone mass consumer must not construct/run an observer")

    monkeypatch.setattr(KarrObservabilityStep, "__init__", forbidden)
    monkeypatch.setattr(KarrObservabilityStep, "next_update", forbidden)


def _expected(state, contract):
    from scipy.constants import Avogadro

    rna_da = sum(
        float(count) * contract["weights"][store][key]
        for store, counts in state["rna"].items()
        if store in contract["weights"]
        for key, count in counts.items()
        if key in contract["weights"][store]
    )
    sub_da = sum(
        float(count) * contract["substrate"][key]
        for key, count in state["substrates"].items()
        if key in contract["substrate"]
    )
    # This is a full-state reference, not an RNA-only isolated input. Physical
    # canonical/form/activation pools already existed in the original basket.
    # Derive their rows independently; never copy a production projection.
    fx = frozen.fixture("ProteinMonomer")
    ids = frozen.wids(fx, "wholeCellModelIDs")
    mw = np.asarray(fx["molecularWeights"], dtype=float).reshape(-1)
    fields = {
        "nascent": "nascentIndexs", "processed_i": "processedIIndexs",
        "processed_ii": "processedIIIndexs", "signal_sequence": "signalSequenceIndexs",
        "folded": "foldedIndexs", "mature": "matureIndexs",
        "inactivated": "inactivatedIndexs", "bound": "boundIndexs",
        "misfolded": "misfoldedIndexs", "damaged": "damagedIndexs",
    }
    rows = {form: np.atleast_1d(fx[field]).astype(int) - 1 for form, field in fields.items()}
    weights = {
        form: dict(zip((ids[row] for row in indices), mw[indices], strict=True))
        for form, indices in rows.items()
    }
    pt = frozen.fixture("ProteinTranslocation")
    pt_ids = frozen.wids(pt, "monomerWholeCellModelIDs")
    migrated = set(frozen.wids(frozen.fixture("TerminalOrganelleAssembly"), "substrateWholeCellModelIDs"))
    migrated.update(pt_ids[row] for row in np.atleast_1d(pt["monomerIndexs_translocating"]).astype(int) - 1)
    protein = state["protein"]
    canonical = protein.get("compartment_counts") or {}
    prot_da = sum(
        float(count) * contract["protein"][key]
        for key, count in protein["counts"].items()
        if key in contract["protein"]
        and (not canonical or key not in migrated)
    )
    for form, by_wid in canonical.items():
        for wid, by_comp in by_wid.items():
            if wid in migrated:
                prot_da += sum(map(float, by_comp.values())) * weights[form][wid]
    queues = {
        "unprocessed_counts": ("ProteinProcessingI", "unprocessedMonomerWholeCellModelIDs", "nascent"),
        "processed_counts": ("ProteinProcessingII", "unprocessedMonomerWholeCellModelIDs", "processed_i"),
        "unfolded_counts": ("ProteinProcessingII", "processedMonomerWholeCellModelIDs", "processed_ii"),
        "signal_sequence_counts": ("ProteinProcessingII", "signalSequenceMonomerWholeCellModelIDs", "signal_sequence"),
        "unmodified_counts": ("ProteinModification", "unmodifiedMonomerWholeCellModelIDs", "folded"),
        "modified_counts": ("ProteinModification", "modifiedMonomerWholeCellModelIDs", "mature"),
    }
    for store, (name, field, form) in queues.items():
        owners = set(frozen.wids(frozen.fixture(name), field)) - migrated
        prot_da += sum(
            float(count) * weights[form][wid]
            for wid, count in protein.get(store, {}).items() if wid in owners
        )
    activation = frozen.fixture("ProteinActivation")
    activation_ids = frozen.wids(activation, "substrateWholeCellModelIDs")
    local = np.atleast_1d(activation["substrateMonomerLocalIndexs"]).astype(int) - 1
    global_rows = np.asarray(activation["substrateMonomerGlobalIndexs"]).astype(int) - 1
    columns = np.asarray(activation["substrateMonomerCompartmentIndexs"]).astype(int) - 1
    source_owners = {}
    for index, global_row, comps in zip(local, global_rows, columns, strict=True):
        wid = activation_ids[index]
        assert np.all(global_row == global_row[0])
        assert ids[rows["mature"][global_row[0]]] == wid
        source_owners[wid] = tuple(str(comp) for comp in comps)
    for store, form in (("activation_active_noncytosol_counts", "mature"),
                        ("activation_inactive_counts", "inactivated")):
        # Actual seeded owners are fixture-validated monomers, not activity or
        # enzyme projections. Active compartment 0 is already in flat counts.
        owners = contract["base"]["protein"].get(store, {})
        for wid, by_comp in protein.get(store, {}).items():
            if wid in owners:
                assert wid in source_owners and wid not in migrated
                comps = source_owners[wid][1:] if form == "mature" else source_owners[wid]
                assert set(by_comp) <= set(comps)
                prot_da += sum(map(float, by_comp.values())) * weights[form][wid]
    # Current mature complex.counts is seeded from ProteinComplex counts,
    # not an enzyme/activity view. Do not include future/unmerged nascent
    # stores or unknown/monomer aliases in this existing physical stock.
    cf = frozen.fixture("ProteinComplex")
    complex_ids = frozen.wids(cf, "wholeCellModelIDs")
    complex_mw = np.asarray(cf["molecularWeights"], dtype=float).reshape(-1)
    complex_rows = {
        form: np.atleast_1d(cf[field]).astype(int) - 1
        for form, field in (("mature", "matureIndexs"), ("inactivated", "inactivatedIndexs"))
    }
    complex_weights = {
        form: dict(zip((complex_ids[row] for row in indices), complex_mw[indices], strict=True))
        for form, indices in complex_rows.items()
    }
    complex_state = state.get("complex", {})
    prot_da += sum(
        float(count) * complex_weights["mature"][wid]
        for wid, count in complex_state.get("counts", {}).items()
        if wid in complex_weights["mature"] and wid not in weights["mature"]
    )
    clocal = np.atleast_1d(activation["substrateComplexLocalIndexs"]).astype(int) - 1
    cglobal = np.asarray(activation["substrateComplexGlobalIndexs"]).astype(int) - 1
    ccolumns = np.asarray(activation["substrateComplexCompartmentIndexs"]).astype(int) - 1
    cowners = {}
    for index, global_row, comps in zip(clocal, cglobal, ccolumns, strict=True):
        wid = activation_ids[index]
        assert np.all(global_row == global_row[0])
        assert complex_ids[complex_rows["mature"][global_row[0]]] == wid
        cowners[wid] = tuple(str(comp) for comp in comps)
    for store, form in (("activation_active_noncytosol_counts", "mature"),
                        ("activation_inactive_counts", "inactivated")):
        owners = contract["base"].get("complex", {}).get(store, {})
        for wid, by_comp in complex_state.get(store, {}).items():
            if wid in owners:
                assert wid in cowners
                comps = cowners[wid][1:] if form == "mature" else cowners[wid]
                assert set(by_comp) <= set(comps)
                prot_da += sum(map(float, by_comp.values())) * complex_weights[form][wid]
    values = tuple(float(value / Avogadro) for value in (rna_da, sub_da, prot_da))
    return (*values, sum(values))


def _state(contract, rna, hint):
    state = deepcopy(contract["base"])
    state["rna"] = deepcopy(rna)
    state.pop("phenotype_observables", None)
    if hint != "absent":
        expected_rna, _, _, total = _expected(state, contract)
        cached = 0.0 if hint == "stale" else -(total + expected_rna)
        state["phenotype_observables"] = {
            "rna_mass_g": cached,
            "cell_dry_mass_g": cached,
        }
    return state


def _check(consumer, state, contract, record_property):
    expected_rna, expected_sub, expected_prot, expected_total = _expected(state, contract)
    before = deepcopy(state)
    models = contract["models"]
    if consumer == "helper":
        result = compute_cell_mass(state, *models)
        actual_total = result.total_g
        record_property("actual_rna_mass_g", result.rna_mass_g)
    else:
        result = _extract_observables(
            state, m1_model=models[0], m2_model=models[1], m3_model=models[2],
            fork_scale_bp=1.0, tick_s=0.0, division_detected=False,
        )
        actual_total = result["cell_dry_mass_g"]
    np.testing.assert_equal(state, before)
    record_property("expected_source_rna_mass_g", expected_rna)
    record_property("expected_total_mass_g", expected_total)
    record_property("actual_total_mass_g", actual_total)
    if consumer == "helper":
        assert result.rna_mass_g == pytest.approx(expected_rna, rel=1e-12, abs=0.0)
        assert result.substrate_mass_g == pytest.approx(expected_sub, rel=1e-12, abs=0.0)
        assert result.protein_mass_g == pytest.approx(expected_prot, rel=1e-12, abs=0.0)
    assert actual_total == pytest.approx(expected_total, rel=1e-12, abs=0.0)


def test_full_state_fixture_has_no_observer_dependency(contract):
    assert {"rna", "substrates", "protein", "cell", "chromosome"} <= set(contract["base"])
    assert set(contract["cases"]) == {
        "rp_fragments", "rp_processed_aliases", "rm_mature", "mixed_forms"
    }


@pytest.mark.parametrize("consumer", ["helper", "production_extractor"])
@pytest.mark.parametrize("case", ["rp_fragments", "rp_processed_aliases", "rm_mature", "mixed_forms"])
@pytest.mark.parametrize("hint", ["absent", "stale", "poisoned"])
def test_real_products_total_mass_ignores_cached_observer_hints(
    consumer, case, hint, contract, record_property
):
    state = _state(contract, contract["cases"][case], hint)
    assert _expected(state, contract)[0] > 0
    _check(consumer, state, contract, record_property)


@pytest.mark.parametrize("consumer", ["helper", "production_extractor"])
def test_duplicate_fragment_rows_have_individual_source_total_mass(
    consumer, contract, record_property
):
    for key, _ in contract["duplicate"]:
        rna = {"counts": {key: contract["fragments"][key]}}
        _check(consumer, _state(contract, rna, "absent"), contract, record_property)


@pytest.mark.parametrize("consumer", ["helper", "production_extractor"])
def test_legacy_protein_and_substrate_components_are_preserved(
    consumer, contract, record_property
):
    for hint in ("absent", "stale", "poisoned"):
        state = _state(contract, {}, hint)
        expected = _expected(state, contract)
        assert expected[0] == 0 and expected[1] > 0 and expected[2] > 0
        _check(consumer, state, contract, record_property)


@pytest.mark.parametrize("consumer", ["helper", "production_extractor"])
def test_nonoverlapping_legacy_gene_rna_is_preserved(consumer, contract, record_property):
    counts = {
        key: count for key, count in contract["base"]["rna"]["counts"].items()
        if key in contract["weights"]["counts"] and key not in contract["source"]["counts"]
    }
    assert any(value > 0 for value in counts.values())
    for hint in ("absent", "stale", "poisoned"):
        state = _state(contract, {"counts": counts}, hint)
        _check(consumer, state, contract, record_property)
