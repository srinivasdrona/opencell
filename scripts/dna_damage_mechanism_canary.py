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
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from l2_replay_common import build_state_template  # noqa: E402

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess  # noqa: E402

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
# ports_schema() does NOT wire (see karr_dna_damage.py `_SPARSE_DAMAGE_FIELDS`
# -- 6 of the 11 ChromosomeStore.FIELDS, missing `hollidayJunctions`). This is
# a structural OC-side gap, independent of any Karr-trace availability
# question; the canary must report it explicitly rather than silently
# treating an absent port as a zero-event field.
_STRUCTURALLY_ABSENT_OC_FIELDS = frozenset({"hollidayJunctions"})

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
    return tuple(
        field
        for field in PRIMARY_PROJECTION_FIELDS
        if field not in _STRUCTURALLY_ABSENT_OC_FIELDS
    )


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
    """
    spec = load_spec()
    condition = spec["conditions"][condition_name]
    radiation_wid = condition.get("radiation_wid")
    dose = float(condition.get("injected_radiation_value", 0.0)) if radiation_wid else 0.0

    pooled_fire_ticks = 0
    per_field_delta_nnz: dict[str, int] = {field: 0 for field in _available_sparse_fields()}
    per_seed_event_counts: list[int] = []

    for i in range(n_seeds):
        process = KarrDNADamageProcess({"rng_seed": _PROCESS_SEED_BASE + i})
        available_fields = _available_sparse_fields()
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
                if delta > 0:
                    tick_fired = True
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
        "pooled_fire_ticks": pooled_fire_ticks,
        "per_field_delta_nnz": per_field_delta_nnz,
        "structurally_absent_fields": sorted(_STRUCTURALLY_ABSENT_OC_FIELDS),
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
    for field in sorted(_STRUCTURALLY_ABSENT_OC_FIELDS):
        payload_component[field] = {
            "oc_observed_delta_nnz": None,
            "karr_analytical_expected_count": float(field_expected.get(field, 0.0)),
            "applicable": False,
            "blocker": "NOT_GATEABLE_MISSING_OC_CHANNEL: DNADamage ports_schema() does not wire this field",
        }

    out["event_rate_component"] = event_rate_component
    out["payload_component"] = payload_component
    # Mechanism-fidelity verdict is deliberately structural, not a pass/fail
    # threshold call: OC's firing algorithm uses a lumped per-kind rate
    # (`_DEFAULT_KIND_RATES_PER_S`), not Karr's per-reaction
    # `calcExpectedReactionRates`, so the event-rate component is EXPECTED to
    # diverge from the Karr-analytical prediction whenever it is exercised.
    # Reporting `within_oc_ci95: false` here is not the harness lying about
    # a threshold breach -- it is the honest output of a real structural
    # mismatch that a future higher-fidelity DNADamage port would need to
    # close. See MECHANISM_FIDELITY_CANARY note in the proposal doc.
    out["verdict"] = "MECHANISM_MISMATCH" if not event_rate_component["within_oc_ci95"] else "MECHANISM_CONSISTENT"
    return out


def probe_biological_gate_blocker() -> dict[str, Any]:
    """Check whether a REAL, empirically-executed Karr trace exists under
    any stimulus condition for DNADamage. If not (the case at the time of
    writing -- no MATLAB toolchain is available in this environment and no
    such trace has ever been extracted), return a precise, non-fabricated
    extraction contract rather than silently passing or skipping the
    biological L2.2 event-class gate.
    """
    candidate_roots = [
        REPO_ROOT / "data" / "m1_sources" / "karr_native",
        Path("/mnt/e/opencell/data/m1_sources/karr_native"),
        Path("E:/opencell/data/m1_sources/karr_native"),
    ]
    found: list[str] = []
    for root in candidate_roots:
        if not root.is_dir():
            continue
        for candidate_dir in sorted(root.glob("per_process_traces_v2_event_s*")):
            for mat in candidate_dir.glob("DNADamage_*ticks.mat"):
                found.append(str(mat))

    spec = load_spec()
    uvb = spec["conditions"]["uvb_mechanism"]
    gamma = spec["conditions"]["gamma_mechanism"]
    required_extraction_contract = {
        "process": "DNADamage",
        "required_seed_count": spec["support_design"]["n_seeds"],
        "required_m_ticks": spec["support_design"]["m_ticks"],
        "required_conditions": {
            "uvb_mechanism": {
                "radiation_wid": uvb["radiation_wid"],
                "injected_radiation_value": uvb["injected_radiation_value"],
            },
            "gamma_mechanism": {
                "radiation_wid": gamma["radiation_wid"],
                "injected_radiation_value": gamma["injected_radiation_value"],
            },
        },
        "rng_schedule": spec["rng_schedule"],
        "expected_output_path_pattern": (
            "data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/DNADamage_20ticks.mat"
        ),
        "extractor_gap": (
            "extract_per_process_traces_v2*.m has no per-condition substrate-override "
            "argument today; it would need to accept an injected UVB_radiation/"
            "gamma_radiation override before a stimulus-conditioned MATLAB run could "
            "be launched at all."
        ),
        "oc_port_gap": (
            "Independently of any extraction, KarrDNADamageProcess.ports_schema() does "
            f"not wire {sorted(_STRUCTURALLY_ABSENT_OC_FIELDS)!r} -- no delta on that "
            "field can ever be observed on the OC side until that port is extended."
        ),
    }

    return {
        "real_stimulus_karr_traces_found": found,
        "biological_gate_verdict": "BLOCKED_MISSING_KARR_STIMULUS_TRACE" if not found else "NEEDS_MANUAL_REVIEW",
        "required_extraction_contract": required_extraction_contract,
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
