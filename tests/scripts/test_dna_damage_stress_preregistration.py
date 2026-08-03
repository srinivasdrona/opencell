from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "stress"
    / "DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json"
)
FIXTURE_PATH = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "DNADamage_flat.mat"


def _scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return ""
        out = out.flat[0]
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _fixture_details() -> dict:
    fixture = loadmat(FIXTURE_PATH, squeeze_me=True, struct_as_record=False)["data"].fixture
    substrate_wids = [
        str(_scalar(value))
        for value in np.asarray(fixture.substrateWholeCellModelIDs, dtype=object).ravel()
    ]
    bounds = np.asarray(fixture.reactionBounds, dtype=np.float64)
    radiation = np.asarray(fixture.reactionRadiation, dtype=np.int64).reshape(-1)
    motifs = np.asarray(fixture.reactionVulnerableMotifs, dtype=object).ravel()
    reaction_ids = [
        str(_scalar(value))
        for value in np.asarray(fixture.reactionWholeCellModelIDs, dtype=object).ravel()
    ]
    damage_types = [
        str(_scalar(value))
        for value in np.asarray(fixture.reactionDamageTypes, dtype=object).ravel()
    ]

    sequence_len = None
    gc_content = None
    ploidy = None
    for state in np.asarray(fixture.states, dtype=object).ravel():
        if str(getattr(state, "x_class_", "")).endswith("Chromosome"):
            sequence_len = int(state.sequenceLen)
            gc_content = float(state.sequenceGCContent)
            ploidy = float(state.ploidy)
            break
    assert sequence_len is not None and gc_content is not None and ploidy is not None
    assert ploidy == 1.0

    polymerized_nt = 2.0 * sequence_len * ploidy
    composition = {
        "A": (1.0 - gc_content) / 2.0,
        "C": gc_content / 2.0,
        "G": gc_content / 2.0,
        "T": (1.0 - gc_content) / 2.0,
    }
    vulnerable = np.zeros(bounds.shape[0], dtype=np.float64)
    for index, motif in enumerate(motifs):
        motif = _scalar(motif)
        if not isinstance(motif, str) or not motif:
            continue
        vulnerable[index] = polymerized_nt * float(np.prod([composition[base] for base in motif]))
    per_unit_rates = vulnerable * bounds[:, 1]

    result: dict[str, dict] = {}
    for wid in ("UVB_radiation", "gamma_radiation"):
        local_index_1b = substrate_wids.index(wid) + 1
        mask = radiation == local_index_1b
        indices = np.flatnonzero(mask)
        result[wid] = {
            "count": int(mask.sum()),
            "sum_rate": float(per_unit_rates[mask].sum()),
            "per_unit_rates": per_unit_rates[mask],
            "reaction_ids": [reaction_ids[index] for index in indices],
            "damage_types": [damage_types[index] for index in indices],
        }
    return {"ploidy": ploidy, "radiation": result}


def test_spec_is_explicitly_non_biological_and_non_gating():
    spec = _load_spec()
    assert spec["condition_type"] == "SYNTHETIC_MECHANISM_CONDITION"
    assert spec["biological_dose_claim"] is False
    assert spec["phenotype_claim"] is False
    assert spec["gating"] == "NON_GATING"
    assert spec["unblocks_l2_5"] is False
    assert spec["execution_status"] == "PREREGISTERED_NOT_EXECUTED"


def test_fixture_hash_and_mechanical_doses_rederive_exactly():
    spec = _load_spec()
    assert _sha256(FIXTURE_PATH) == spec["fixture"]["sha256"]
    details = _fixture_details()
    assert details["ploidy"] == spec["baseline_state_assumptions"]["fixture_ploidy"]
    support = spec["support_design"]
    target = support["target_expected_pooled_site_events"]
    denominator_count = support["n_seeds"] * support["m_ticks"]

    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        condition = spec["conditions"][condition_name]
        rate_details = details["radiation"][condition["radiation_wid"]]
        count = rate_details["count"]
        rate = rate_details["sum_rate"]
        dose = target / (denominator_count * rate)
        assert count == condition["radiation_gated_reaction_count"]
        assert rate == condition["sum_per_unit_radiation_rate_per_tick"]
        assert dose == condition["injected_radiation_value"]
        assert np.isclose(
            rate * dose * support["m_ticks"],
            condition["expected_events_per_seed_window"],
            rtol=1.0e-15,
            atol=0.0,
        )
        lambdas = rate_details["per_unit_rates"] * dose
        expected_fire_ticks = denominator_count * (1.0 - float(np.prod(1.0 - lambdas)))
        assert expected_fire_ticks == condition["expected_pooled_fire_ticks"]
        assert (
            expected_fire_ticks / support["existing_pooled_support_floor"]
            == condition["fire_tick_support_multiplier"]
        )


def test_per_kind_support_and_gamma_field_mapping_rederive_from_fixture():
    spec = _load_spec()
    details = _fixture_details()["radiation"]
    support = spec["support_design"]
    denominator_count = support["n_seeds"] * support["m_ticks"]

    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        condition = spec["conditions"][condition_name]
        rate_details = details[condition["radiation_wid"]]
        expected = (
            rate_details["per_unit_rates"]
            * condition["injected_radiation_value"]
            * denominator_count
        )
        supported_ids = {
            reaction_id
            for reaction_id, count in zip(
                rate_details["reaction_ids"], expected.tolist(), strict=True
            )
            if count >= support["existing_pooled_support_floor"]
        }
        assert supported_ids == set(condition["per_kind_support"]["supported_reaction_ids"])
        assert (
            len(expected) - len(supported_ids)
            == condition["per_kind_support"]["unsupported_reaction_count"]
        )

        nonzero_expected = expected[expected > 0.0]
        assert np.isclose(
            float(nonzero_expected.min()),
            condition["per_kind_support"]["rarest_nonzero_expected_pooled_site_events"],
            rtol=1.0e-15,
            atol=0.0,
        )

    gamma = spec["conditions"]["gamma_mechanism"]
    gamma_types = details["gamma_radiation"]["damage_types"]
    assert gamma_types.count("damagedBases") == gamma["reaction_count_by_field"]["damagedBases"]
    assert gamma_types.count("strandBreaks") == gamma["reaction_count_by_field"]["strandBreaks"]
    assert set(gamma_types) == set(gamma["allowed_chromosome_fields"])
    uvb = spec["conditions"]["uvb_mechanism"]
    assert set(details["UVB_radiation"]["damage_types"]) == set(uvb["allowed_chromosome_fields"])


def test_seed_streams_are_disjoint_and_complete():
    spec = _load_spec()
    assert (
        spec["rng_schedule"]["generator"]
        == "edu.stanford.covert.util.RandStream('mcg16807', 'Seed', seed)"
    )
    assert spec["rng_schedule"]["process_rng_seed_ids"] == "2000..2049"
    assert spec["rng_schedule"]["chromosome_rng_seed_ids"] == "3000..3049"
    process_seeds = set(range(2000, 2050))
    chromosome_seeds = set(range(3000, 3050))
    assert len(process_seeds) == len(chromosome_seeds) == 50
    assert process_seeds.isdisjoint(chromosome_seeds)


def test_conditions_change_only_one_radiation_substrate():
    conditions = _load_spec()["conditions"]
    assert conditions["no_stimulus"]["UVB_radiation"] == 0.0
    assert conditions["no_stimulus"]["gamma_radiation"] == 0.0
    assert conditions["uvb_mechanism"]["radiation_wid"] == "UVB_radiation"
    assert conditions["gamma_mechanism"]["radiation_wid"] == "gamma_radiation"
    assert "combined" not in conditions


def test_evidence_contract_refuses_vacuity_and_separates_dna_repair():
    support = _load_spec()["support_design"]
    assert support["event_timing_model"] == "repeated_firing"
    assert support["fire_predicate"].startswith("net increase in nnz")
    assert "in-place subtype conversion" in support["fire_predicate"]
    contract = _load_spec()["evidence_contract"]
    assert contract["control_verdict"] == "NOT_APPLICABLE"
    assert contract["stimulus_support_failure"] == "INSUFFICIENT_KARR_SUPPORT"
    assert contract["numeric_threshold_source"] == "Karr-only seed-cluster null; no fixed tolerance"
    assert "no DNARepair output is consumed" in contract["exact_invariants"]


def test_anti_laundering_boundary_is_frozen():
    anti = _load_spec()["anti_laundering"]
    assert anti["states_after_access"] == "compare phase only"
    assert anti["sut_access"] is False
    assert anti["trace_hint_access"] is False
    assert anti["stored_verdict_authority"] is False


def test_primary_source_hash_and_formula_when_wholecell_source_is_available():
    configured_root = os.environ.get("OPENCELL_WHOLECELL_SRC_ROOT")
    candidates = []
    if configured_root:
        candidates.append(Path(configured_root))
    candidates.append(Path("/mnt/e/opencell/data/m1_sources/WholeCell/src"))
    source_root = next((path for path in candidates if path.is_dir()), None)
    if source_root is None:
        pytest.skip("WholeCell source root unavailable; primary-source hash check not runnable")

    source_path = (
        source_root
        / "+edu"
        / "+stanford"
        / "+covert"
        / "+cell"
        / "+sim"
        / "+process"
        / "DNADamage.m"
    )
    spec = _load_spec()
    assert _sha256(source_path) == spec["primary_source"]["sha256"]
    source = source_path.read_text(encoding="latin-1")
    assert "rates = nVulnerableSites .* this.reactionBounds(:, 2);" in source
    assert "rates(this.reactionRadiation ~= 0) .*" in source
    assert "this.substrates(this.reactionRadiation(this.reactionRadiation ~= 0))" in source
    assert "this.randStream.randperm" in source
    assert "this.chromosome.setSiteDamaged" in source
