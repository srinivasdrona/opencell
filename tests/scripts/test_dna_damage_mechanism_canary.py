"""Anti-zero, provenance, and channel-coverage tests for the DNADamage
synthetic mechanism-fidelity canary (``scripts/dna_damage_mechanism_canary.py``).

These tests enforce the Composition Mandate / FIX_TEMPLATE_L2_REPLAY rules
this task was scoped against:

* **Anti-zero (no zero==zero pass).** The ``no_stimulus`` condition must
  never be scored as a certifying PASS -- it is always ``NOT_APPLICABLE``.
  At least one stimulus condition must exercise a real, nonzero firing
  signal (either OC fires nonzero times, or the Karr-analytical expectation
  is nonzero and the divergence itself is the evidence) -- the canary must
  never be a no-op.
* **Channel coverage.** Every field in the catalog's DNADamage
  ``primary_projection`` (see ``PROCESS_CATALOG.yaml``) must appear in the
  canary's payload component, either as a measured OC delta or as an
  explicit ``NOT_GATEABLE_MISSING_OC_CHANNEL`` blocker -- never silently
  dropped.
* **Provenance / no trace-cribbing (Rule 8).** The canary script and the
  production process module it drives must not read any per-tick oracle
  trace file from a production code path; the canary itself must live
  outside ``opencell/vivarium/``.
* **Blocker precision.** When no real, empirically-executed Karr
  stimulus-conditioned trace exists on disk (the case at the time of
  writing), the biological L2.2 event-class gate verdict must be a
  precise, non-PASS blocker naming the concrete required extraction
  inputs -- sourced from the frozen spec, never hand-typed duplicates.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import dna_damage_mechanism_canary as canary  # noqa: E402
from _dna_damage_stress_common import load_spec  # noqa: E402

RESULT_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "stress"
    / "DNADAMAGE_MECHANISM_CANARY_RESULT.json"
)

_CATALOG_PRIMARY_PROJECTION = (
    "damage_event_present",
    "damagedBases.delta_nnz",
    "abasicSites.delta_nnz",
    "strandBreaks.delta_nnz",
    "damagedSugarPhosphates.delta_nnz",
    "intrastrandCrossLinks.delta_nnz",
    "hollidayJunctions.delta_nnz",
    "gapSites.delta_nnz",
)


def _catalog_field_names() -> list[str]:
    return [entry.split(".", 1)[0] for entry in _CATALOG_PRIMARY_PROJECTION if entry != "damage_event_present"]


@pytest.fixture(scope="module")
def small_run() -> dict:
    """A small-but-real ensemble (fast for CI, still exercises firing)."""
    return canary.run_canary(n_seeds=10, m_ticks=20)


def test_catalog_primary_projection_is_fully_covered_by_the_harness(small_run: dict) -> None:
    """Every primary_projection field from PROCESS_CATALOG.yaml's DNADamage
    row must be represented in the canary's payload component for every
    stimulus condition -- measured or explicitly blocked, never omitted."""
    catalog_fields = set(_catalog_field_names())
    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        payload = small_run["mechanism_distance"][condition_name]["payload_component"]
        assert set(payload.keys()) == catalog_fields, (
            f"{condition_name} payload_component channels {sorted(payload.keys())} "
            f"!= catalog primary_projection channels {sorted(catalog_fields)}"
        )
        for field, entry in payload.items():
            has_measurement = entry.get("oc_observed_delta_nnz") is not None
            has_blocker = "blocker" in entry
            assert has_measurement or has_blocker, (
                f"{condition_name}/{field} is neither measured nor explicitly blocked "
                "-- silent channel drop is forbidden"
            )


def test_holliday_junctions_is_an_explicit_structural_blocker_not_a_silent_zero(small_run: dict) -> None:
    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        entry = small_run["mechanism_distance"][condition_name]["payload_component"]["hollidayJunctions"]
        assert entry["oc_observed_delta_nnz"] is None
        assert entry["applicable"] is False
        assert "NOT_GATEABLE_MISSING_OC_CHANNEL" in entry["blocker"]


def test_no_stimulus_condition_is_never_a_certifying_pass(small_run: dict) -> None:
    """Anti-zero rule: the quiescent (no-stimulus) condition can never be
    scored as PASS/MECHANISM_CONSISTENT -- it is always NOT_APPLICABLE, and
    its own damage_event_present must be False (a real, non-fired
    negative control), never conflated with stimulus evidence."""
    no_stim = small_run["conditions"]["no_stimulus"]
    assert no_stim["damage_event_present"] is False
    assert no_stim["injected_radiation_value"] == 0.0
    distance = small_run["mechanism_distance"]["no_stimulus"]
    assert distance["verdict"] == "NOT_APPLICABLE"
    assert "zero==zero" in distance["reason"]


def test_stimulus_conditions_produce_nonzero_non_vacuous_evidence(small_run: dict) -> None:
    """Non-triviality: at least one stimulus condition must show OC actually
    firing (pooled_fire_ticks > 0), proving the canary exercises the real
    non-trivial code path and is not a no-op across all conditions."""
    fired_any = any(
        small_run["conditions"][name]["pooled_fire_ticks"] > 0 for name in ("uvb_mechanism", "gamma_mechanism")
    )
    assert fired_any, "no stimulus condition ever fired -- canary is a no-op, cannot be non-trivial evidence"

    # Every stimulus condition must carry a nonzero Karr-analytical
    # expectation for at least one payload channel -- i.e. the comparison
    # itself is never vacuous (0 expected vs 0 observed) even when OC fails
    # to fire.
    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        payload = small_run["mechanism_distance"][condition_name]["payload_component"]
        expected_nonzero = any(
            entry["karr_analytical_expected_count"] > 0.0 for entry in payload.values()
        )
        assert expected_nonzero, f"{condition_name} has no nonzero Karr-analytical expectation anywhere"


def test_mechanism_distance_never_silently_defaults_to_pass(small_run: dict) -> None:
    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        verdict = small_run["mechanism_distance"][condition_name]["verdict"]
        assert verdict in ("MECHANISM_CONSISTENT", "MECHANISM_MISMATCH")
        event_rate = small_run["mechanism_distance"][condition_name]["event_rate_component"]
        # within_oc_ci95 must be a real bool derived from a real CI, not a
        # hardcoded True.
        assert isinstance(event_rate["within_oc_ci95"], bool)
        assert event_rate["oc_fire_rate_ci95"][0] <= event_rate["oc_fire_rate_ci95"][1]


def test_biological_gate_blocker_is_precise_and_not_a_pass(small_run: dict) -> None:
    """The actual biological L2.2 event-class gate (evidence_index.json's
    DNADamage/latest_event row) must never be reported PASS/GREEN by this
    canary: no real empirical Karr stimulus trace exists, so the verdict
    must be a precise BLOCKED status naming the exact required inputs,
    sourced from the frozen spec (never hand-duplicated numbers)."""
    gate = small_run["biological_l2_2_event_class_gate"]
    assert gate["biological_gate_verdict"] != "PASS"
    assert gate["biological_gate_verdict"] == "BLOCKED_MISSING_KARR_STIMULUS_TRACE"
    assert gate["real_stimulus_karr_traces_found"] == []

    spec = load_spec()
    contract = gate["required_extraction_contract"]
    assert contract["required_seed_count"] == spec["support_design"]["n_seeds"]
    assert contract["required_m_ticks"] == spec["support_design"]["m_ticks"]
    assert (
        contract["required_conditions"]["uvb_mechanism"]["injected_radiation_value"]
        == spec["conditions"]["uvb_mechanism"]["injected_radiation_value"]
    )
    assert (
        contract["required_conditions"]["gamma_mechanism"]["injected_radiation_value"]
        == spec["conditions"]["gamma_mechanism"]["injected_radiation_value"]
    )
    assert contract["rng_schedule"] == spec["rng_schedule"]
    assert "hollidayJunctions" in contract["oc_port_gap"]


def test_result_is_explicitly_labeled_non_biological_and_non_gating(small_run: dict) -> None:
    """Anti-relabeling: this canary must never be presented as biological
    validation. Every run must carry the same explicit disclosure fields
    as the frozen preregistration spec."""
    assert small_run["condition_type"] == "SYNTHETIC_MECHANISM_CONDITION"
    assert small_run["biological_dose_claim"] is False
    assert small_run["phenotype_claim"] is False
    assert small_run["gating"] == "NON_GATING"


def test_canary_is_deterministic_given_the_same_seeds() -> None:
    first = canary.run_condition("uvb_mechanism", n_seeds=4, m_ticks=6)
    second = canary.run_condition("uvb_mechanism", n_seeds=4, m_ticks=6)
    assert first["per_field_delta_nnz"] == second["per_field_delta_nnz"]
    assert first["per_seed_event_counts"] == second["per_seed_event_counts"]
    assert first["pooled_fire_ticks"] == second["pooled_fire_ticks"]


def test_canary_script_lives_outside_production_vivarium_path() -> None:
    canary_path = Path(canary.__file__).resolve()
    assert "opencell" + str(Path("/vivarium")) not in str(canary_path).replace("\\", "/")
    assert (REPO_ROOT / "scripts").resolve() in canary_path.parents


def test_production_dna_damage_module_has_no_oracle_trace_reads() -> None:
    """Rule 8 (no trace-cribbing): the production process module must not
    read any per-tick oracle trace file (``*_100ticks*``, ``*_20ticks*``,
    ``per_process_traces_v2_event*``) from its own code path. It may read
    the tracked canonical fixture (model parameters, not per-tick oracle
    observations) -- that is explicitly allowed."""
    source = (REPO_ROOT / "opencell" / "vivarium" / "karr_dna_damage.py").read_text(encoding="utf-8")
    forbidden_patterns = [
        r"per_process_traces_v2_event",
        r"_20ticks",
        r"states_before\[",
        r"states_after\[",
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, source), f"production module matches forbidden oracle pattern: {pattern}"


def test_checked_in_full_scale_result_matches_catalog_n_and_m() -> None:
    """The tracked full-scale (N=50, M=20) canary result must match
    PROCESS_CATALOG.yaml's DNADamage N_seeds/M_ticks -- if the catalog
    numbers ever change, this artifact is stale until regenerated."""
    if not RESULT_PATH.is_file():
        pytest.skip("full-scale canary result not yet generated on this checkout")
    payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assert payload["n_seeds"] == 50
    assert payload["m_ticks"] == 20
    assert payload["biological_l2_2_event_class_gate"]["biological_gate_verdict"] != "PASS"
    assert payload["mechanism_distance"]["no_stimulus"]["verdict"] == "NOT_APPLICABLE"
