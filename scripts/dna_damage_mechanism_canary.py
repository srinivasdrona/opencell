"""DNADamage synthetic mechanism-fidelity canary (executor).

Executes the profile preregistered in
``docs/phase_f/l2_2_design_a/stress/DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json``
and ``DNADAMAGE_STRESS_PROFILE_PROPOSAL.md``: injects only Karr's own
``UVB_radiation``/``gamma_radiation`` substrate at the frozen, fixture-derived
dose, runs the real ``KarrDNADamageProcess.next_update`` across an N-seed x
M-tick ensemble (default 50 x 20, matching ``PROCESS_CATALOG.yaml``'s
DNADamage ``N_seeds``/``M_ticks``), and reports:

1.  OC-empirical damage_event_present + per-chromosome-field ``delta_nnz``
    incidence, for every channel in the catalog's ``primary_projection``.
2.  The Karr-source ANALYTICAL expectation for the same channels, re-derived
    from ``DNADamage.m::calcExpectedReactionRates`` via the tracked fixture
    (see ``_dna_damage_stress_common.py``) -- never a fabricated or
    hand-typed number.
3.  A precise, non-fabricated blocker for the actual biological L2.2
    event-class gate (the one ``evidence_index.json`` tracks under
    ``DNADamage/latest_event``): whether any REAL empirical Karr trace
    exists under stimulus conditions (checked, and none does at the time of
    writing), what extraction would be required to produce one, and which OC
    chromosome ports/fields are structurally absent regardless.

Explicitly NON-BIOLOGICAL and NON-GATING (see the proposal doc's own
disclosure): a PASS or FAIL here can never certify or deny the actual L2.2
DNADamage event-class row. It is a mechanism-fidelity cross-check only:
does OC's stochastic firing reproduce the *statistics* Karr's own rate
formula predicts, once the same source-derived dose is injected. No
production code (``opencell/vivarium/``) is imported for its oracle-reading
behavior -- ``KarrDNADamageProcess`` is exercised purely through its public
``next_update`` port, as any Vivarium caller would.

CLI:
    bin\\oc-py scripts/dna_damage_mechanism_canary.py [--seeds 50] [--ticks 20] [--out PATH]
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (
    REPO_ROOT,
    REPO_ROOT / "tests" / "vivarium",
    REPO_ROOT / "tests" / "scripts",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from _dna_damage_stress_common import (  # noqa: E402
    load_spec,
    per_field_expected_counts,
)
from l2_replay_common import build_state_template, cell_vector  # noqa: E402

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess  # noqa: E402
from scripts.l2_event import dna_damage_stimulus_cohort as cohort  # noqa: E402

# Catalog authoritative spec (PROCESS_CATALOG.yaml DNADamage row):
#   primary_channel: chromosome
#   primary_projection: [damage_event_present, damagedBases.delta_nnz,
#     abasicSites.delta_nnz, strandBreaks.delta_nnz,
#     damagedSugarPhosphates.delta_nnz, intrastrandCrossLinks.delta_nnz,
#     hollidayJunctions.delta_nnz, gapSites.delta_nnz]
PRIMARY_PROJECTION_FIELDS = (
    "damagedBases",
    "abasicSites",
    "strandBreaks",
    "damagedSugarPhosphates",
    "intrastrandCrossLinks",
    "hollidayJunctions",
    "gapSites",
)

# Karr-recognized damage-associated chromosome fields DNADamage's own
# ports_schema() does NOT wire. Derived dynamically (never hardcoded) from
# a live KarrDNADamageProcess().ports_schema()["chromosome"] key set, so
# this stays correct automatically if the production port is ever extended
# -- a structural OC-side gap, independent of any Karr-trace availability
# question; the canary must report it explicitly rather than silently
# treating an absent port as a zero-event field.
@functools.lru_cache(maxsize=1)
def _structurally_absent_oc_fields() -> frozenset[str]:
    schema = KarrDNADamageProcess({}).ports_schema()["chromosome"]
    return frozenset(PRIMARY_PROJECTION_FIELDS) - set(schema.keys())


CONDITIONS = ("no_stimulus", "uvb_mechanism", "gamma_mechanism")

# Process-side RNG seed schedule (spec `rng_schedule.process_rng_seed_ids`:
# "2000..2049"). NOTE (must stay documented, never silently assumed
# equivalent): Karr's `process_rng_seed_ids`/`chromosome_rng_seed_ids` name a
# *dual-stream* MATLAB `RandStream('mcg16807', ...)` pairing that this OC
# port does not reproduce -- `KarrDNADamageProcess` draws from a single
# `numpy.random.default_rng(rng_seed)` stream. Using `2000 + i` here only
# preserves the seed *label* for cross-reference with the frozen spec; it is
# NOT a claim that OC's RNG stream is bit-equivalent to Karr's for the same
# label.
_PROCESS_SEED_BASE = 2000


def _available_sparse_fields() -> tuple[str, ...]:
    absent = _structurally_absent_oc_fields()
    return tuple(field for field in PRIMARY_PROJECTION_FIELDS if field not in absent)


def _apply_chromosome_update(state: dict[str, Any], update: dict[str, Any], process: KarrDNADamageProcess) -> None:
    chrom_update = update.get("chromosome")
    if not isinstance(chrom_update, dict):
        return
    chrom_state = state.setdefault("chromosome", {})
    if "damage_events_cumulative" in chrom_update:
        existing = chrom_state.get("damage_events_cumulative", [])
        if not isinstance(existing, list):
            existing = []
        existing = existing + list(chrom_update["damage_events_cumulative"])
        chrom_state["damage_events_cumulative"] = existing
    if "replication_stall_flag" in chrom_update:
        chrom_state["replication_stall_flag"] = float(
            float(chrom_state.get("replication_stall_flag", 0.0)) + float(chrom_update["replication_stall_flag"])
        )
    for field in PRIMARY_PROJECTION_FIELDS:
        if field in chrom_update:
            chrom_state[field] = SparseTriplet.from_state(
                chrom_update[field], shape=process.chromosome_shape
            ).to_state()


def _field_nnz(state: dict[str, Any], process: KarrDNADamageProcess, field: str) -> int:
    store = ChromosomeStore.from_state_mapping(state.get("chromosome", {}), shape=process.chromosome_shape)
    return store.calc_num_edges(field)


def run_condition(
    condition_name: str,
    *,
    n_seeds: int,
    m_ticks: int,
) -> dict[str, Any]:
    """Run the OC-empirical ensemble for one preregistered condition.

    Returns per-seed-tick incidence + pooled totals for every field the OC
    chromosome port actually exposes, plus an explicit
    ``structurally_absent_fields`` list for the ones it does not (never
    silently coerced to a measured zero).

    Per the frozen spec's own ``support_design.fire_predicate`` and each
    stimulus condition's ``allowed_chromosome_fields``, the "did this tick
    fire" determination (and hence ``pooled_fire_ticks``/
    ``damage_event_present``) is restricted to only that condition's
    allowed field(s) -- e.g. ``uvb_mechanism`` fires only on
    ``intrastrandCrossLinks``. Any nonzero delta observed on a field
    OUTSIDE the condition's allowed set (e.g. the spontaneous, unradiated
    ``depurination``/``abasicSites`` pathway firing during a UVB
    condition) is measured and reported but explicitly excluded from the
    fire count, and flagged under ``out_of_scope_nonzero_fields`` as a
    potential exact-invariant violation rather than silently pooled in.
    ``no_stimulus`` has no ``allowed_chromosome_fields`` in the spec (it is
    a negative control, not a mechanism condition) -- all available fields
    are checked for firing there, since the point is to prove nothing
    fires anywhere.
    """
    spec = load_spec()
    condition = spec["conditions"][condition_name]
    radiation_wid = condition.get("radiation_wid")
    dose = float(condition.get("injected_radiation_value", 0.0)) if radiation_wid else 0.0
    available_fields = _available_sparse_fields()
    allowed_fields = tuple(condition.get("allowed_chromosome_fields", available_fields))
    out_of_scope_fields = tuple(f for f in available_fields if f not in allowed_fields)

    pooled_fire_ticks = 0
    per_field_delta_nnz: dict[str, int] = {field: 0 for field in available_fields}
    per_seed_event_counts: list[int] = []
    out_of_scope_nonzero_fields: set[str] = set()

    for i in range(n_seeds):
        process = KarrDNADamageProcess({"rng_seed": _PROCESS_SEED_BASE + i})
        state = build_state_template(process)
        if radiation_wid:
            state.setdefault("substrates", {})[radiation_wid] = dose

        seed_events = 0
        for _tick in range(m_ticks):
            before = {field: _field_nnz(state, process, field) for field in available_fields}
            update = process.next_update(1.0, state)
            _apply_chromosome_update(state, update, process)
            after = {field: _field_nnz(state, process, field) for field in available_fields}
            tick_fired = False
            for field in available_fields:
                delta = after[field] - before[field]
                assert delta >= 0, f"field {field} unexpectedly lost damage (delta={delta})"
                per_field_delta_nnz[field] += delta
                if delta > 0 and field in allowed_fields:
                    tick_fired = True
                if delta > 0 and field in out_of_scope_fields:
                    out_of_scope_nonzero_fields.add(field)
            if tick_fired:
                pooled_fire_ticks += 1
                seed_events += 1
        per_seed_event_counts.append(seed_events)

    return {
        "condition": condition_name,
        "radiation_wid": radiation_wid,
        "injected_radiation_value": dose,
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "n_trials": n_seeds * m_ticks,
        "allowed_chromosome_fields": sorted(allowed_fields),
        "out_of_scope_nonzero_fields": sorted(out_of_scope_nonzero_fields),
        "pooled_fire_ticks": pooled_fire_ticks,
        "per_field_delta_nnz": per_field_delta_nnz,
        "structurally_absent_fields": sorted(_structurally_absent_oc_fields()),
        "per_seed_event_counts": per_seed_event_counts,
        "damage_event_present": pooled_fire_ticks > 0,
    }


# Wilson score interval z-quantile for a two-sided 95% confidence level
# (statistics constant, NOT a biology parameter -- same value already used
# unflagged elsewhere in the repo, e.g. scripts/l22_dnas_power/power_decision.py).
_Z_SCORE_95PCT_TWO_SIDED = 1.959963984540054
_WILSON_Z_SQUARED = _Z_SCORE_95PCT_TWO_SIDED * _Z_SCORE_95PCT_TWO_SIDED


def _binomial_ci95(count: int, n_trials: int) -> tuple[float, float]:
    """Wilson score 95% CI for a pooled event-rate proportion. Used only to
    report OC's empirical rate uncertainty -- never as a fixed numeric
    tolerance (Composition Mandate anti-fabrication: uncertainty must be
    labeled, not hidden behind a bare point estimate)."""
    if n_trials <= 0:
        return (0.0, 0.0)
    z_squared = _WILSON_Z_SQUARED
    p = count / n_trials
    denom = 1.0 + z_squared / n_trials
    center = p + z_squared / (2.0 * n_trials)
    half = _Z_SCORE_95PCT_TWO_SIDED * np.sqrt(p * (1.0 - p) / n_trials + z_squared / (4.0 * n_trials * n_trials))
    lo = (center - half) / denom
    hi = (center + half) / denom
    return (max(0.0, lo), min(1.0, hi))


def evaluate_mechanism_distance(result: dict[str, Any], *, n_seeds: int, m_ticks: int) -> dict[str, Any]:
    """Hurdle-style comparison of OC-empirical incidence/payload against the
    Karr-source ANALYTICAL expectation (never a fabricated/executed Karr
    trace -- there is no stimulus-conditioned Karr trace on disk; see
    `probe_biological_gate_blocker`). Component 1 is the event-rate hurdle;
    component 2 is the per-field conditional payload distance. Both
    components are reported with explicit uncertainty, never a bare pass/
    fail number.
    """
    condition_name = result["condition"]
    n_trials = result["n_trials"]
    out: dict[str, Any] = {"condition": condition_name}

    if condition_name == "no_stimulus":
        out["verdict"] = "NOT_APPLICABLE"
        out["reason"] = "no-stimulus zero==zero cannot certify this event process (anti-zero rule)"
        return out

    spec = load_spec()
    condition = spec["conditions"][condition_name]
    expected_pooled_fire_ticks = float(condition["expected_pooled_fire_ticks"]) * (
        (n_seeds * m_ticks) / (spec["support_design"]["n_seeds"] * spec["support_design"]["m_ticks"])
    )
    lo, hi = _binomial_ci95(result["pooled_fire_ticks"], n_trials)
    expected_p = expected_pooled_fire_ticks / n_trials if n_trials else 0.0
    event_rate_component = {
        "oc_pooled_fire_ticks": result["pooled_fire_ticks"],
        "oc_fire_rate": result["pooled_fire_ticks"] / n_trials if n_trials else 0.0,
        "oc_fire_rate_ci95": [lo, hi],
        "karr_analytical_expected_fire_ticks": expected_pooled_fire_ticks,
        "karr_analytical_expected_fire_rate": expected_p,
        "within_oc_ci95": bool(lo <= expected_p <= hi),
    }

    field_expected = per_field_expected_counts(condition_name, n_seeds=n_seeds, m_ticks=m_ticks)
    payload_component: dict[str, Any] = {}
    for field in _available_sparse_fields():
        expected = float(field_expected.get(field, 0.0))
        observed = int(result["per_field_delta_nnz"].get(field, 0))
        payload_component[field] = {
            "oc_observed_delta_nnz": observed,
            "karr_analytical_expected_count": expected,
            "applicable": expected > 0.0 or observed > 0,
        }
    for field in sorted(_structurally_absent_oc_fields()):
        payload_component[field] = {
            "oc_observed_delta_nnz": None,
            "karr_analytical_expected_count": float(field_expected.get(field, 0.0)),
            "applicable": False,
            "blocker": "NOT_GATEABLE_MISSING_OC_CHANNEL: DNADamage ports_schema() does not wire this field",
        }

    out["event_rate_component"] = event_rate_component
    out["payload_component"] = payload_component
    # Mechanism-fidelity verdict is deliberately structural, not a pass/fail
    # threshold call. Even after the 2026-09-02 review remediation (items
    # 3/4: OC's firing algorithm now uses Karr's own literal per-reaction
    # `evolveState`/`setSiteDamaged` selectionProbability/stochasticRound
    # law, not a lumped per-kind rate), this canary's Karr-analytical
    # comparator is `calcExpectedReactionRates`/`calcNumberVulnerableSites`
    # -- a *different* Karr formula, used in Karr itself only for FBA
    # resource-request bookkeeping (no footprint/maxReactions/stochastic
    # rounding terms). The two formulas are not expected to agree even in
    # real Karr, so `within_oc_ci95: false` here is not the harness lying
    # about a threshold breach -- it is the honest output of a real
    # structural difference between two genuine Karr code paths. See
    # MECHANISM_FIDELITY_CANARY note in the proposal doc.
    out["verdict"] = "MECHANISM_MISMATCH" if not event_rate_component["within_oc_ci95"] else "MECHANISM_CONSISTENT"
    return out


# Karr per-process trace subdirectory names/patterns to scan for a DNADamage
# trace. `per_process_traces`/`per_process_traces_v2` each hold a single
# quiescent 100-tick trace; `dnadamage_stimulus_cohort/<condition>/per_process_
# traces_v2_event_s*` is the canonical condition-rooted 50-seed stimulus
# cohort leaf pattern planned by scripts/l2_event/dna_damage_stimulus_cohort.py;
# `dnadamage_fullcycle` holds one long (32400-tick) full-cell-cycle trace.
# Every known path family is individually classified (never treated as absent
# merely because it is nested, and never treated as sufficient merely because
# it exists -- see `_classify_trace`).
_TRACE_DIR_PATTERNS: tuple[str, ...] = (
    "per_process_traces",
    "per_process_traces_v2",
    "per_process_traces_v2_event_s*",
    "dnadamage_stimulus_cohort/*/per_process_traces_v2_event_s*",
    "dnadamage_fullcycle",
)

# Statistics/classification ratio, NOT a biology parameter (same category as
# the Wilson z-score constant above): a trace's observed radiation-substrate
# value must reach at least this fraction of the frozen spec's own
# injected_radiation_value for that condition before the trace is
# classified "stimulus_conditioned" rather than "vacuous_no_stimulus"
# ambient noise. The known ambient baseline in every DNADamage trace on
# disk today is UVB_radiation ~= 0.0 and gamma_radiation ~= 2.8e-11 -- 9-12
# orders of magnitude below 1% of any frozen dose (~0.94-7.47) -- so the
# exact fraction chosen here does not affect the classification of any
# currently known trace; it only needs to separate "genuinely ambient" from
# "an actually injected dose," which any value across a wide range would do
# identically for the traces that exist today.
_STIMULUS_CLASSIFICATION_MIN_DOSE_FRACTION = 0.01


@functools.lru_cache(maxsize=1)
def _radiation_substrate_indices() -> dict[str, int]:
    process = KarrDNADamageProcess({})
    return {name: process.substrate_wids.index(name) for name in ("UVB_radiation", "gamma_radiation")}


def _trace_max_radiation_values(path: Path, *, max_samples: int = 200) -> dict[str, float]:
    """Scan a v7.3/HDF5 Karr per-process trace (h5py; scipy.io.loadmat
    cannot parse the v7.3 format these traces are stored in) and return the
    max observed UVB_radiation/gamma_radiation substrate value across up to
    ``max_samples`` evenly spaced ticks in ``states_before/substrates``.
    """
    indices = _radiation_substrate_indices()
    maxima = {name: 0.0 for name in indices}
    with h5py.File(path, "r") as handle:
        ds = handle["states_before/substrates"]
        n_ticks = max(ds.shape)
        step = max(1, n_ticks // max_samples)
        for tick in range(0, n_ticks, step):
            vec = cell_vector(handle, "states_before", "substrates", tick)
            for name, idx in indices.items():
                if idx < vec.size:
                    maxima[name] = max(maxima[name], float(vec[idx]))
    return maxima


def _classify_trace(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Classify one on-disk DNADamage trace as vacuous/ambient or
    stimulus-conditioned, using the frozen spec's own injected doses as the
    (non-fabricated) classification reference -- never a hand-typed
    biology number."""
    try:
        maxima = _trace_max_radiation_values(path)
    except Exception as exc:  # unreadable/corrupt/unexpected-shape trace
        return {"path": str(path), "classification": "UNREADABLE", "error": str(exc)}

    uvb_dose = float(spec["conditions"]["uvb_mechanism"]["injected_radiation_value"])
    gamma_dose = float(spec["conditions"]["gamma_mechanism"]["injected_radiation_value"])
    uvb_max = maxima.get("UVB_radiation", 0.0)
    gamma_max = maxima.get("gamma_radiation", 0.0)
    is_stimulus_conditioned = (
        uvb_max >= uvb_dose * _STIMULUS_CLASSIFICATION_MIN_DOSE_FRACTION
        or gamma_max >= gamma_dose * _STIMULUS_CLASSIFICATION_MIN_DOSE_FRACTION
    )
    return {
        "path": str(path),
        "observed_max_UVB_radiation": uvb_max,
        "observed_max_gamma_radiation": gamma_max,
        "spec_uvb_mechanism_injected_dose": uvb_dose,
        "spec_gamma_mechanism_injected_dose": gamma_dose,
        "classification": "stimulus_conditioned" if is_stimulus_conditioned else "vacuous_no_stimulus",
    }


def probe_biological_gate_blocker() -> dict[str, Any]:
    """Check whether a REAL, empirically-executed, NONTRIVIAL (stimulus-
    conditioned) Karr trace exists for DNADamage. Every known trace
    directory (`per_process_traces`, `per_process_traces_v2`,
    `per_process_traces_v2_event_s*`, `dnadamage_fullcycle`) is scanned and
    every found trace is individually classified via
    `_classify_trace` -- traces that exist but carry only ambient
    radiation-substrate values are reported as `vacuous_no_stimulus`, not
    silently omitted or conflated with "no trace exists at all". Only if
    zero NONTRIVIAL stimulus-conditioned traces are found does the
    biological L2.2 event-class gate return BLOCKED, together with a
    precise, non-fabricated extraction contract for what a stimulus-
    conditioned trace would require.
    """
    candidate_roots = [
        REPO_ROOT / "data" / "m1_sources" / "karr_native",
        Path("/mnt/e/opencell/data/m1_sources/karr_native"),
        Path("E:/opencell/data/m1_sources/karr_native"),
    ]
    found_paths: set[Path] = set()
    for root in candidate_roots:
        if not root.is_dir():
            continue
        for pattern in _TRACE_DIR_PATTERNS:
            for candidate_dir in sorted(root.glob(pattern)):
                if not candidate_dir.is_dir():
                    continue
                for mat in candidate_dir.glob("DNADamage_*ticks.mat"):
                    found_paths.add(mat.resolve())

    spec = load_spec()
    classified_traces = [_classify_trace(path, spec) for path in sorted(found_paths, key=str)]
    nontrivial_traces = [c for c in classified_traces if c.get("classification") == "stimulus_conditioned"]
    vacuous_traces = [c for c in classified_traces if c.get("classification") == "vacuous_no_stimulus"]

    stimulus_preflight = cohort.build_cohort_plan(validate_existing=True)
    uvb = spec["conditions"]["uvb_mechanism"]
    gamma = spec["conditions"]["gamma_mechanism"]
    required_extraction_contract = {
        "process": "DNADamage",
        "required_seed_count": spec["support_design"]["n_seeds"],
        "required_m_ticks": spec["support_design"]["m_ticks"],
        "preflight_status": stimulus_preflight["preflight_status"],
        "planned_seed_ids": stimulus_preflight["planned_seed_ids"],
        "condition_root_dirname": stimulus_preflight["condition_root_dirname"],
        "required_observables": stimulus_preflight["required_observables"],
        "planner": "scripts/l2_event/dna_damage_stimulus_cohort.py",
        "required_conditions": {
            "uvb_mechanism": {
                "radiation_wid": uvb["radiation_wid"],
                "injected_radiation_value": uvb["injected_radiation_value"],
                "output_path_pattern": cohort.condition_output_path_pattern("uvb_mechanism"),
                "extraction_identity_json": cohort.condition_identity_json(spec, "uvb_mechanism"),
            },
            "gamma_mechanism": {
                "radiation_wid": gamma["radiation_wid"],
                "injected_radiation_value": gamma["injected_radiation_value"],
                "output_path_pattern": cohort.condition_output_path_pattern("gamma_mechanism"),
                "extraction_identity_json": cohort.condition_identity_json(spec, "gamma_mechanism"),
            },
        },
        "rng_schedule": spec["rng_schedule"],
        "stimulus_cohort_preflight": stimulus_preflight,
        "matlab_execution_blocker": (
            "No REAL stimulus-conditioned DNADamage MATLAB traces were found on disk. "
            "The extractor/launcher preflight is READY_FOR_MATLAB, but a shared-lock "
            "MATLAB execution must still produce the planned UVB/gamma cohort before "
            "the biological L2.2 event-class verdict can be evaluated."
        ),
        "oc_port_gap": (
            "All primary_projection chromosome fields are wired through "
            "KarrDNADamageProcess.ports_schema()."
            if not _structurally_absent_oc_fields()
            else (
                "Independently of any extraction, KarrDNADamageProcess.ports_schema() does "
                f"not wire {sorted(_structurally_absent_oc_fields())!r} -- no delta on that "
                "field can ever be observed on the OC side until that port is extended."
            )
        ),
    }

    verdict = "NEEDS_MANUAL_REVIEW" if nontrivial_traces else "BLOCKED_MISSING_NONTRIVIAL_KARR_STIMULUS_TRACE"

    return {
        "karr_traces_found": classified_traces,
        "karr_traces_found_count": len(classified_traces),
        "vacuous_no_stimulus_traces_found_count": len(vacuous_traces),
        "nontrivial_stimulus_conditioned_traces_found_count": len(nontrivial_traces),
        "real_stimulus_karr_traces_found": [c["path"] for c in nontrivial_traces],
        "blocker_precision_note": (
            f"{len(classified_traces)} DNADamage trace(s) exist on disk and were scanned "
            f"({len(vacuous_traces)} classified vacuous_no_stimulus, "
            f"{len(nontrivial_traces)} classified stimulus_conditioned). The blocker is "
            "'no NONTRIVIAL stimulus-conditioned Karr trace', not 'no files exist'."
        ),
        "biological_gate_verdict": verdict,
        "required_extraction_contract": required_extraction_contract,
    }


def _rate_law_provenance() -> dict[str, Any]:
    """Fix #1 companion (Rule 8), updated for the Sept-2 review's item-3/4
    fix: record a live, runtime check that no per-tick oracle trace-rate
    override path -- nor the older lumped per-kind rate override
    (`kind_rates_per_s`) -- exists on the production process at all (not
    merely "was not used this run"). Expected: no such
    path/attribute -- `trace_rate_override_mechanism_exists` and
    `kind_rate_override_mechanism_exists` must both be False.
    """
    process = KarrDNADamageProcess({})
    return {
        "trace_rate_override_mechanism_exists": (
            hasattr(process, "_load_trace_kind_rates")
            or "trace_path" in KarrDNADamageProcess.defaults
            or "use_trace_rates_if_available" in KarrDNADamageProcess.defaults
            or hasattr(process, "trace_kind_rates_per_s")
            or hasattr(process, "used_trace_rates")
        ),
        "trace_rate_override_path_used": False,
        "kind_rate_override_mechanism_exists": (
            hasattr(process, "kind_rates_per_s")
            or hasattr(process, "_kind_rate_override_active")
            or hasattr(process, "_scaled_reaction_rates_from_kind_override")
            or "kind_rates_per_s" in KarrDNADamageProcess.defaults
        ),
        "note": (
            "KarrDNADamageProcess no longer supports any per-tick oracle trace-rate "
            "override (Rule 8 fix, 2026-08-05 remediation) NOR the lumped per-kind "
            "rate override removed in the 2026-09-02 review remediation (items 3/4). "
            "Firing is governed solely by the literal per-reaction "
            "selectionProbability/stochasticRound law "
            "(DNADamage.m::evolveState/Chromosome.m::setSiteDamaged); there is no "
            "override re-entry path of any kind left in production."
        ),
    }


def run_canary(*, n_seeds: int, m_ticks: int) -> dict[str, Any]:
    spec = load_spec()
    results = {name: run_condition(name, n_seeds=n_seeds, m_ticks=m_ticks) for name in CONDITIONS}
    distances = {
        name: evaluate_mechanism_distance(results[name], n_seeds=n_seeds, m_ticks=m_ticks)
        for name in CONDITIONS
    }
    blocker = probe_biological_gate_blocker()
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "process": "DNADamage",
        "condition_type": "SYNTHETIC_MECHANISM_CONDITION",
        "biological_dose_claim": False,
        "phenotype_claim": False,
        "gating": "NON_GATING",
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "spec_ref": "docs/phase_f/l2_2_design_a/stress/DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json",
        "spec_execution_status_at_run": spec["execution_status"],
        "spec_execution_status_note": (
            "execution_status describes whether a real Karr/MATLAB stimulus-conditioned "
            "run has ever been executed (it has not -- PREREGISTERED_NOT_EXECUTED remains "
            "true and is not changed by this canary). It does NOT describe whether this "
            "OC-side mechanism canary itself has run; see "
            "oc_mechanism_canary_execution_status for that, which is a distinct, "
            "explicitly non-biological, non-L2.2-evidence status."
        ),
        "oc_mechanism_canary_execution_status": "EXECUTED",
        "oc_mechanism_canary_is_biological_l2_2_evidence": False,
        "kind_rates_provenance": _rate_law_provenance(),
        "conditions": results,
        "mechanism_distance": distances,
        "biological_l2_2_event_class_gate": blocker,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--ticks", type=int, default=20)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "stress" / "DNADAMAGE_MECHANISM_CANARY_RESULT.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    payload = run_canary(n_seeds=args.seeds, m_ticks=args.ticks)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
