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


def test_holliday_junctions_is_measured_once_the_port_is_wired(small_run: dict) -> None:
    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        entry = small_run["mechanism_distance"][condition_name]["payload_component"]["hollidayJunctions"]
        assert entry["oc_observed_delta_nnz"] == 0
        assert entry["karr_analytical_expected_count"] == 0.0
        assert entry["applicable"] is False
        assert "blocker" not in entry


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
    canary: no NONTRIVIAL (stimulus-conditioned) empirical Karr trace
    exists, so the verdict must be a precise BLOCKED status naming the
    exact required inputs, sourced from the frozen spec (never
    hand-duplicated numbers). The blocker must be precise about *why*:
    traces DO exist on disk (per_process_traces, per_process_traces_v2,
    dnadamage_fullcycle all carry a DNADamage trace) but every one of them
    is classified vacuous/ambient, not stimulus-conditioned -- the
    canary must never conflate "found but vacuous" with "no files found
    at all"."""
    gate = small_run["biological_l2_2_event_class_gate"]
    assert gate["biological_gate_verdict"] != "PASS"
    assert gate["biological_gate_verdict"] == "BLOCKED_MISSING_NONTRIVIAL_KARR_STIMULUS_TRACE"
    assert gate["real_stimulus_karr_traces_found"] == []

    # Precision requirement: the blocker must be "no nontrivial stimulus
    # trace", not "no files exist" -- assert traces were actually found and
    # explicitly classified as vacuous, not merely absent, whenever the
    # known Karr trace data is reachable in this environment.
    karr_native_root = Path("/mnt/e/opencell/data/m1_sources/karr_native")
    if not karr_native_root.is_dir():
        karr_native_root = Path("E:/opencell/data/m1_sources/karr_native")
    if karr_native_root.is_dir():
        assert gate["karr_traces_found_count"] >= 1
        assert gate["nontrivial_stimulus_conditioned_traces_found_count"] == 0
        assert gate["vacuous_no_stimulus_traces_found_count"] == gate["karr_traces_found_count"]
        for trace in gate["karr_traces_found"]:
            assert trace["classification"] == "vacuous_no_stimulus"
            # Ambient radiation baseline must be far below the frozen spec's
            # injected dose -- never itself misclassified as a real stimulus.
            assert trace["observed_max_UVB_radiation"] < trace["spec_uvb_mechanism_injected_dose"]
            assert trace["observed_max_gamma_radiation"] < trace["spec_gamma_mechanism_injected_dose"]
        found_dir_names = {Path(t["path"]).parent.name for t in gate["karr_traces_found"]}
        assert "per_process_traces" in found_dir_names
        assert "per_process_traces_v2" in found_dir_names
        assert "dnadamage_fullcycle" in found_dir_names

    spec = load_spec()
    contract = gate["required_extraction_contract"]
    assert contract["required_seed_count"] == spec["support_design"]["n_seeds"]
    assert contract["required_m_ticks"] == spec["support_design"]["m_ticks"]
    assert contract["preflight_status"] == "READY_FOR_MATLAB"
    assert contract["planned_seed_ids"] == list(range(2000, 2050))
    assert contract["required_observables"] == ["chromosome", "substrates"]
    assert contract["condition_root_dirname"] == "dnadamage_stimulus_cohort"
    assert contract["planner"] == "scripts/l2_event/dna_damage_stimulus_cohort.py"
    assert (
        contract["required_conditions"]["uvb_mechanism"]["injected_radiation_value"]
        == spec["conditions"]["uvb_mechanism"]["injected_radiation_value"]
    )
    assert (
        contract["required_conditions"]["gamma_mechanism"]["injected_radiation_value"]
        == spec["conditions"]["gamma_mechanism"]["injected_radiation_value"]
    )
    assert contract["required_conditions"]["uvb_mechanism"]["output_path_pattern"].endswith(
        "dnadamage_stimulus_cohort/uvb_mechanism/per_process_traces_v2_event_s{seed}/DNADamage_20ticks.mat"
    )
    assert contract["required_conditions"]["gamma_mechanism"]["output_path_pattern"].endswith(
        "dnadamage_stimulus_cohort/gamma_mechanism/per_process_traces_v2_event_s{seed}/DNADamage_20ticks.mat"
    )
    assert (
        json.loads(contract["required_conditions"]["uvb_mechanism"]["extraction_identity_json"])["condition"]
        == "uvb_mechanism"
    )
    assert (
        json.loads(contract["required_conditions"]["gamma_mechanism"]["extraction_identity_json"])["condition"]
        == "gamma_mechanism"
    )
    assert contract["rng_schedule"] == spec["rng_schedule"]
    assert contract["stimulus_cohort_preflight"]["preflight_status"] == "READY_FOR_MATLAB"
    assert "shared-lock MATLAB execution" in contract["matlab_execution_blocker"]
    assert "wired through" in contract["oc_port_gap"]


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
    observations) -- that is explicitly allowed. Regression for the Rule 8
    violation flagged in review: a `_load_trace_kind_rates`/`trace_path`
    per-tick oracle-rate override previously existed (silently inert only
    because scipy.io.loadmat cannot parse the v7.3 trace format) and has
    since been removed entirely."""
    source = (REPO_ROOT / "opencell" / "vivarium" / "karr_dna_damage.py").read_text(encoding="utf-8")
    forbidden_patterns = [
        r"per_process_traces_v2_event",
        r"_100ticks",
        r"_20ticks",
        r"states_before\[",
        r"states_after\[",
        r"trace_path",
        r"_load_trace_kind_rates",
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


def test_structurally_absent_fields_are_schema_derived_not_hardcoded() -> None:
    """The set of catalog primary_projection fields DNADamage's own
    ports_schema() does not wire must be computed live from a real
    KarrDNADamageProcess().ports_schema()["chromosome"] key set, not a
    hardcoded frozenset -- so it stays correct automatically if the
    production port is ever extended or narrowed."""
    from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess

    live_schema_keys = set(KarrDNADamageProcess({}).ports_schema()["chromosome"].keys())
    expected_absent = frozenset(canary.PRIMARY_PROJECTION_FIELDS) - live_schema_keys

    canary._structurally_absent_oc_fields.cache_clear()
    computed_absent = canary._structurally_absent_oc_fields()
    assert computed_absent == expected_absent
    assert computed_absent == frozenset()
    assert "_STRUCTURALLY_ABSENT_OC_FIELDS" not in dir(canary)


def test_fire_predicate_is_restricted_to_each_conditions_allowed_fields() -> None:
    """Per the frozen spec's own `support_design.fire_predicate` and each
    condition's `allowed_chromosome_fields`, a tick only counts as "fired"
    for a stimulus condition if the net nnz increase is on that condition's
    allowed field(s) -- e.g. uvb_mechanism may only fire on
    intrastrandCrossLinks, gamma_mechanism only on damagedBases/
    strandBreaks. A field outside the allowed set (e.g. the unradiated,
    always-on depurination pathway writing abasicSites) must never be
    pooled into that condition's fire count."""
    spec = load_spec()
    for condition_name in ("uvb_mechanism", "gamma_mechanism"):
        result = canary.run_condition(condition_name, n_seeds=10, m_ticks=20)
        allowed = set(spec["conditions"][condition_name]["allowed_chromosome_fields"])
        assert set(result["allowed_chromosome_fields"]) == allowed
        # Every reported out-of-scope-nonzero field (if any) must be
        # outside the allowed set -- proves the restriction is real, not
        # a no-op relabeling of the same field set.
        for field in result["out_of_scope_nonzero_fields"]:
            assert field not in allowed
            assert field in result["per_field_delta_nnz"]

    # no_stimulus has no allowed_chromosome_fields in the frozen spec (it
    # is a negative control, not a mechanism condition) -- all available
    # fields must be checked there, since the point is proving nothing
    # fires anywhere.
    no_stim_result = canary.run_condition("no_stimulus", n_seeds=10, m_ticks=20)
    assert set(no_stim_result["allowed_chromosome_fields"]) == set(canary._available_sparse_fields())
    assert "allowed_chromosome_fields" not in spec["conditions"]["no_stimulus"]


def test_kind_rates_provenance_reports_no_trace_override(small_run: dict) -> None:
    """Fix #1 companion: the canary result must record the process's
    effective kind_rates_per_s and explicitly confirm no per-tick
    oracle-trace-rate override mechanism exists on the production process
    (expected: False/no such path)."""
    provenance = small_run["kind_rates_provenance"]
    assert provenance["trace_rate_override_mechanism_exists"] is False
    assert provenance["trace_rate_override_path_used"] is False
    from opencell.vivarium.karr_dna_damage import _DEFAULT_KIND_RATES_PER_S

    assert provenance["kind_rates_per_s"] == _DEFAULT_KIND_RATES_PER_S


def test_execution_status_is_reconciled_without_biological_claim(small_run: dict) -> None:
    """Fix #5: the frozen spec's `execution_status` (which describes
    whether a real Karr/MATLAB stimulus-conditioned run has ever executed
    -- it has not) must not be conflated with whether this OC-side
    mechanism canary has executed (it has, repeatedly). The result JSON
    must carry an explicit, separate status for the OC-canary execution
    that is clearly labeled non-biological, non-L2.2 evidence."""
    spec = load_spec()
    assert small_run["spec_execution_status_at_run"] == spec["execution_status"] == "PREREGISTERED_NOT_EXECUTED"
    assert small_run["oc_mechanism_canary_execution_status"] == "EXECUTED"
    assert small_run["oc_mechanism_canary_is_biological_l2_2_evidence"] is False
    assert "spec_execution_status_note" in small_run
    assert "does not" in small_run["spec_execution_status_note"] or "NOT describe" in small_run[
        "spec_execution_status_note"
    ]
