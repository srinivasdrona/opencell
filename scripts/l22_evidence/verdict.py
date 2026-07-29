"""Mechanical verdict re-derivation for the L2.2 evidence index.

The whole point of this module: a process's ``result.json["verdict"]``
string (and each channel's ``result.json["channels"][c]["verdict"]``
string) is written by ``tests/vivarium/l2_2_design_a_runner.py`` at run
time, but is **never trusted** here. Every row's ``mechanical_verdict`` is
recomputed from the raw numeric channel payload (``w1_oc_vs_karr``,
``threshold``, ``q95_null``, ``n_nonzero_oc``, ``n_nonzero_karr``) plus the
catalog's own N/M and sentinel-warning strings, so a hand-tampered stored
PASS can never override a failing (or absent) raw metric.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence.catalog import REPO_ROOT, ProcessEntry  # noqa: E402

# Metadata-only version tag for the mechanical re-derivation logic in this
# module (channel/process verdict functions below) -- bump this whenever
# `rederive_channel`/`rederive_process`/the per-channel-kind helpers change
# in a way that could produce a different verdict for the SAME raw
# result.json payload. This never affects any threshold/metric/biology
# value itself; it exists purely so `sweep_provenance.json` (written by
# `scripts/l22_evidence/sweep.py` at evidence-generation time) can record
# which evaluator logic produced a given row's evidence, and so the
# generator can mechanically detect "this evidence was generated under an
# older evaluator and must be re-run" rather than silently re-scoring old
# raw numbers under new logic and calling that equivalent to a real rerun.
# v2 (F3, Opus5 final review): `rederive_process` now requires the
# catalog's declared `primary_channel` name to be marked `is_primary=true`
# on EXACTLY one channel -- previously a boolean OR across channels meant
# some OTHER channel marked is_primary=true (with the real primary_channel
# silently False) or more than one channel marked is_primary=true could
# both pass through undetected. This can change the verdict for the SAME
# raw result.json payload versus v1, so any evidence generated under v1
# must be treated as stale, not silently re-scored as equivalent.
EVALUATOR_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ProcessVerdict:
    mechanical_verdict: str
    channel_verdicts: dict[str, str]
    reasons: list[str]


def _has_valid_h12_support(result_payload: dict[str, Any]) -> bool:
    """True iff a linked H12 evidence file exists with a machine-checked,
    nonzero count of nontrivial samples.

    This is the *only* way ``PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE`` is
    allowed to avoid demoting a row to non-green (per
    docs/phase_f/l2_2_design_a/LAUNDERING_VS_CONVERGENCE.md's H12 anchor).
    Catalog-level ``closed_form_dominant: confirmed*`` alone is a soft flag
    and is NOT sufficient support on its own.
    """
    ref = result_payload.get("h12_evidence_ref")
    if not ref:
        return False
    path = Path(str(ref))
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    nontrivial = payload.get("nontrivial_sample_count")
    return isinstance(nontrivial, (int, float)) and not isinstance(nontrivial, bool) and nontrivial > 0


_SCALED_DISTANCE_EPSILON = 1e-12


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _is_nonnegative_count(value: object) -> bool:
    return _is_finite_number(value) and float(value) >= 0.0


def rederive_channel(name: str, payload: dict[str, Any], *, is_primary: bool) -> tuple[str, list[str]]:
    """Recompute a single channel's verdict from raw numbers only.

    Returns (verdict, reasons). ``reasons`` is empty for SEED_NOISE/PASS/
    EVENT_CHANNEL_DEFERRED/INSUFFICIENT_SAMPLES (those are legitimate,
    non-gating-or-green outcomes); it is populated for FAIL,
    MISSING_EVALUATOR, and PRIMARY_CHANNEL_VACUOUS.
    """
    if bool(payload.get("is_event_channel", False)):
        return "EVENT_CHANNEL_DEFERRED", []

    aggregation = str(payload.get("aggregation", "per_tick_vector_w1_mean"))
    if aggregation == "per_tick_vector_w1_mean":
        return _rederive_w1_channel(name, payload, is_primary=is_primary)
    if aggregation == "per_component_scaled":
        return _rederive_per_component_scaled_channel(name, payload, is_primary=is_primary)
    if aggregation == "hurdle_event_rate_plus_conditional_scaled_distance":
        return _rederive_hurdle_channel(name, payload, is_primary=is_primary)
    if aggregation == "fva_feasibility":
        return _rederive_fva_channel(name, payload, is_primary=is_primary)

    return (
        schema.STATUS_MISSING_EVALUATOR,
        [
            f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} uses aggregation={aggregation!r}; "
            "no mechanical re-derivation evaluator implemented for this metric type yet"
        ],
    )


def _rederive_w1_channel(name: str, payload: dict[str, Any], *, is_primary: bool) -> tuple[str, list[str]]:
    required_fields = ("w1_oc_vs_karr", "threshold", "q95_null", "n_nonzero_oc", "n_nonzero_karr")
    missing_fields = [key for key in required_fields if key not in payload]
    if missing_fields:
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} missing raw field(s) {missing_fields}"],
        )

    n_nonzero_oc = payload["n_nonzero_oc"]
    n_nonzero_karr = payload["n_nonzero_karr"]

    if is_primary and n_nonzero_oc == 0 and n_nonzero_karr == 0:
        return (
            schema.STATUS_PRIMARY_VACUOUS,
            [
                f"{schema.STATUS_PRIMARY_VACUOUS}: primary channel {name!r} has zero nonzero observations "
                "on both OC and Karr (non-vacuous primary channel requirement failed)"
            ],
        )

    if n_nonzero_oc < schema.MIN_NONZERO_EVENTS or n_nonzero_karr < schema.MIN_NONZERO_EVENTS:
        return "INSUFFICIENT_SAMPLES", []

    w1 = float(payload["w1_oc_vs_karr"])
    q95_null = float(payload["q95_null"])
    threshold = float(payload["threshold"])

    if w1 <= q95_null:
        return "SEED_NOISE", []
    if w1 <= threshold:
        return "PASS", []
    return schema.STATUS_FAIL, [f"{schema.STATUS_FAIL}: channel {name!r} w1={w1} exceeds threshold={threshold}"]


def _rederive_per_component_scaled_channel(
    name: str, payload: dict[str, Any], *, is_primary: bool
) -> tuple[str, list[str]]:
    """Re-derive a ``per_component_scaled`` channel straight from
    ``payload["per_component"]``'s raw numbers, never from its stored
    ``component_verdicts``/``joint_verdict`` strings.

    Formula (mirrors ``tests/vivarium/_l2_2_design_a_projections.py``'s
    ``per_component_scaled_distance``, without altering it): for each
    projection component, ``scaled_w1 = raw_w1 / max(scale, 1e-12)``;
    component verdict is PASS iff ``scaled_w1 <= scaled_distance_threshold``;
    the channel joint verdict is PASS iff every component is PASS.
    """
    block = payload.get("per_component")
    if not isinstance(block, dict):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} missing raw field 'per_component'"],
        )

    required_fields = (
        "component_raw_w1",
        "component_scales",
        "scaled_distance_threshold",
        "component_n_nonzero_oc",
        "component_n_nonzero_karr",
    )
    missing_fields = [key for key in required_fields if key not in block]
    if missing_fields:
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} per_component block missing "
                f"raw field(s) {missing_fields}"
            ],
        )

    raw_w1_by_component = block["component_raw_w1"]
    scales_by_component = block["component_scales"]
    n_nonzero_oc_by_component = block["component_n_nonzero_oc"]
    n_nonzero_karr_by_component = block["component_n_nonzero_karr"]
    if not all(
        isinstance(mapping, dict)
        for mapping in (
            raw_w1_by_component,
            scales_by_component,
            n_nonzero_oc_by_component,
            n_nonzero_karr_by_component,
        )
    ):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} per_component raw fields are not mappings"],
        )

    component_names = set(raw_w1_by_component)
    if (
        component_names != set(scales_by_component)
        or component_names != set(n_nonzero_oc_by_component)
        or component_names != set(n_nonzero_karr_by_component)
        or not component_names
    ):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} per_component raw fields do not all "
                "share the same (non-empty) set of component names"
            ],
        )

    if not _is_finite_number(block["scaled_distance_threshold"]):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} scaled_distance_threshold is not a finite number"],
        )
    threshold = float(block["scaled_distance_threshold"])

    reasons: list[str] = []
    component_verdicts: dict[str, str] = {}
    all_vacuous = True
    for component_name in sorted(component_names):
        raw_w1 = raw_w1_by_component[component_name]
        scale = scales_by_component[component_name]
        n_oc = n_nonzero_oc_by_component[component_name]
        n_karr = n_nonzero_karr_by_component[component_name]
        if not _is_finite_number(raw_w1) or not _is_finite_number(scale) or float(scale) <= 0.0:
            return (
                schema.STATUS_MISSING_EVALUATOR,
                [
                    f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} component {component_name!r} has "
                    f"non-finite or non-positive raw_w1/scale (raw_w1={raw_w1!r}, scale={scale!r})"
                ],
            )
        if not _is_nonnegative_count(n_oc) or not _is_nonnegative_count(n_karr):
            return (
                schema.STATUS_MISSING_EVALUATOR,
                [
                    f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} component {component_name!r} has "
                    f"negative or non-finite nonzero counts (n_oc={n_oc!r}, n_karr={n_karr!r})"
                ],
            )
        if not (float(n_oc) == 0.0 and float(n_karr) == 0.0):
            all_vacuous = False

        scaled_w1 = float(raw_w1) / max(float(scale), _SCALED_DISTANCE_EPSILON)
        verdict = "PASS" if scaled_w1 <= threshold else "FAIL"
        component_verdicts[component_name] = verdict
        if verdict == "FAIL":
            reasons.append(
                f"{schema.STATUS_FAIL}: channel {name!r} component {component_name!r} scaled_w1={scaled_w1} "
                f"exceeds threshold={threshold}"
            )

    if is_primary and all_vacuous:
        return (
            schema.STATUS_PRIMARY_VACUOUS,
            [
                f"{schema.STATUS_PRIMARY_VACUOUS}: primary channel {name!r} has zero nonzero observations "
                "on both OC and Karr for every projection component (non-vacuous primary channel "
                "requirement failed)"
            ],
        )

    if reasons:
        return schema.STATUS_FAIL, reasons
    return "PASS", []


def _rederive_hurdle_channel(name: str, payload: dict[str, Any], *, is_primary: bool) -> tuple[str, list[str]]:
    """Re-derive a ``hurdle_event_rate_plus_conditional_scaled_distance``
    channel straight from ``payload["hurdle"]``'s raw numbers, never from
    its stored ``component_verdicts``/``joint_verdict`` strings.

    Formula (mirrors ``hurdle_event_rate_plus_conditional_distance`` in
    ``tests/vivarium/_l2_2_design_a_projections.py``, without altering it):
    an event-rate verdict PASS iff ``event_rate_diff <=
    event_rate_threshold``; each conditional component's
    ``scaled_w1 = raw_w1 / max(scale, 1e-12)`` is PASS iff
    ``scaled_w1 <= conditional_scaled_distance_threshold``; the channel
    joint verdict is PASS iff the event-rate check AND every conditional
    component are PASS.
    """
    block = payload.get("hurdle")
    if not isinstance(block, dict):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} missing raw field 'hurdle'"],
        )

    required_fields = (
        "event_rate_diff",
        "event_rate_threshold",
        "conditional_w1_per_component",
        "conditional_component_scales",
        "conditional_scaled_distance_threshold",
        "n_events_oc",
        "n_events_karr",
    )
    missing_fields = [key for key in required_fields if key not in block]
    if missing_fields:
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} hurdle block missing raw field(s) {missing_fields}"],
        )

    event_rate_diff = block["event_rate_diff"]
    event_rate_threshold = block["event_rate_threshold"]
    n_events_oc = block["n_events_oc"]
    n_events_karr = block["n_events_karr"]
    raw_w1_by_component = block["conditional_w1_per_component"]
    scales_by_component = block["conditional_component_scales"]
    conditional_threshold = block["conditional_scaled_distance_threshold"]

    if not _is_finite_number(event_rate_diff) or not _is_finite_number(event_rate_threshold):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} event_rate_diff/threshold are not finite numbers"],
        )
    if not _is_nonnegative_count(n_events_oc) or not _is_nonnegative_count(n_events_karr):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} has negative or non-finite event counts "
                f"(n_events_oc={n_events_oc!r}, n_events_karr={n_events_karr!r})"
            ],
        )
    if not _is_finite_number(conditional_threshold):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} "
                "conditional_scaled_distance_threshold is not a finite number"
            ],
        )
    if not isinstance(raw_w1_by_component, dict) or not isinstance(scales_by_component, dict):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} conditional raw fields are not mappings"],
        )
    if set(raw_w1_by_component) != set(scales_by_component):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} conditional_w1_per_component and "
                "conditional_component_scales do not share the same component names"
            ],
        )

    reasons: list[str] = []
    event_rate_diff = float(event_rate_diff)
    event_rate_threshold = float(event_rate_threshold)
    event_pass = event_rate_diff <= event_rate_threshold
    if not event_pass:
        reasons.append(
            f"{schema.STATUS_FAIL}: channel {name!r} event_rate_diff={event_rate_diff} "
            f"exceeds event_rate_threshold={event_rate_threshold}"
        )

    conditional_threshold = float(conditional_threshold)
    for component_name in sorted(raw_w1_by_component):
        raw_w1 = raw_w1_by_component[component_name]
        scale = scales_by_component[component_name]
        if not _is_finite_number(raw_w1) or not _is_finite_number(scale) or float(scale) <= 0.0:
            return (
                schema.STATUS_MISSING_EVALUATOR,
                [
                    f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} component {component_name!r} has "
                    f"non-finite or non-positive raw_w1/scale (raw_w1={raw_w1!r}, scale={scale!r})"
                ],
            )
        scaled_w1 = float(raw_w1) / max(float(scale), _SCALED_DISTANCE_EPSILON)
        if scaled_w1 > conditional_threshold:
            reasons.append(
                f"{schema.STATUS_FAIL}: channel {name!r} conditional component {component_name!r} "
                f"scaled_w1={scaled_w1} exceeds threshold={conditional_threshold}"
            )

    # Non-vacuous primary channel requirement, hurdle flavor: every
    # conditional component above shares the same event mask, so zero
    # events on BOTH sides across the whole ensemble means the hurdle
    # never actually observed anything to compare -- the runner's own
    # joint_verdict computation forces a trivial PASS in that case (raw_w1
    # hardcoded to 0.0 for every component; see
    # `hurdle_event_rate_plus_conditional_distance`'s all-empty branch),
    # which this mechanical re-derivation must not launder into a green row.
    if is_primary and n_events_oc == 0 and n_events_karr == 0:
        return (
            schema.STATUS_PRIMARY_VACUOUS,
            [
                f"{schema.STATUS_PRIMARY_VACUOUS}: primary channel {name!r} recorded zero events on both "
                "OC and Karr across the whole ensemble (non-vacuous primary channel requirement failed)"
            ],
        )

    if reasons:
        return schema.STATUS_FAIL, reasons
    return "PASS", []


def _rederive_fva_channel(name: str, payload: dict[str, Any], *, is_primary: bool) -> tuple[str, list[str]]:
    """Re-derive an ``fva_feasibility`` channel from
    ``fva_feasible_pairs``/``fva_pairs_total``/``fva_threshold`` only --
    never from the stored ``fva_feasibility_fraction`` or ``verdict``
    strings. PASS iff ``feasible_pairs / total_pairs >= fva_threshold`` and
    ``total_pairs > 0``.
    """
    required_fields = (
        "fva_feasibility_fraction",
        "fva_feasible_pairs",
        "fva_pairs_total",
        "fva_tolerance",
        "fva_threshold",
    )
    missing_fields = [key for key in required_fields if key not in payload]
    if missing_fields:
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} missing raw field(s) {missing_fields}"],
        )

    feasible_pairs = payload["fva_feasible_pairs"]
    total_pairs = payload["fva_pairs_total"]
    threshold = payload["fva_threshold"]
    stored_fraction = payload["fva_feasibility_fraction"]

    if not _is_nonnegative_count(feasible_pairs) or not _is_nonnegative_count(total_pairs):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} has negative or non-finite "
                f"fva_feasible_pairs/fva_pairs_total (feasible={feasible_pairs!r}, total={total_pairs!r})"
            ],
        )
    if not _is_finite_number(threshold) or not _is_finite_number(stored_fraction):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} fva_threshold/fva_feasibility_fraction are not finite numbers"],
        )

    feasible_pairs = float(feasible_pairs)
    total_pairs = float(total_pairs)
    threshold = float(threshold)
    stored_fraction = float(stored_fraction)

    if total_pairs <= 0.0:
        return (
            schema.STATUS_FAIL,
            [f"{schema.STATUS_FAIL}: channel {name!r} fva_pairs_total={total_pairs} is not > 0; feasibility undefined"],
        )
    if feasible_pairs > total_pairs:
        return (
            schema.STATUS_FAIL,
            [
                f"{schema.STATUS_FAIL}: channel {name!r} fva_feasible_pairs={feasible_pairs} exceeds "
                f"fva_pairs_total={total_pairs}"
            ],
        )

    recomputed_fraction = feasible_pairs / total_pairs
    if not math.isclose(recomputed_fraction, stored_fraction, rel_tol=1e-9, abs_tol=1e-9):
        return (
            schema.STATUS_FAIL,
            [
                f"{schema.STATUS_FAIL}: channel {name!r} stored fva_feasibility_fraction={stored_fraction} is "
                f"inconsistent with feasible_pairs/total_pairs={recomputed_fraction}"
            ],
        )

    if recomputed_fraction >= threshold:
        return "PASS", []
    return (
        schema.STATUS_FAIL,
        [
            f"{schema.STATUS_FAIL}: channel {name!r} fva feasibility fraction={recomputed_fraction} "
            f"is below fva_threshold={threshold}"
        ],
    )


def rederive_process(process_name: str, entry: ProcessEntry, result_payload: dict[str, Any]) -> ProcessVerdict:
    reasons: list[str] = []
    warnings = [str(warning) for warning in result_payload.get("warnings", ())]

    if str(result_payload.get("process")) != process_name:
        reasons.append(
            f"{schema.STATUS_PROCESS_NAME_MISMATCH}: result.json process={result_payload.get('process')!r} "
            f"!= expected {process_name!r}"
        )

    # --- N/M consistency: catches e.g. stale evidence generated at M=10 while
    # the catalog now specifies M=100 for this process (an M=10-vs-M=100 lie).
    seeds = result_payload.get("seeds")
    n_actual = len(seeds) if isinstance(seeds, list) else None
    m_actual = result_payload.get("ticks")
    if entry.n_seeds is not None and n_actual != entry.n_seeds:
        reasons.append(
            f"{schema.STATUS_NM_MISMATCH}: N actual={n_actual!r} vs catalog N_seeds={entry.n_seeds!r}"
        )
    if entry.m_ticks is not None and m_actual != entry.m_ticks:
        reasons.append(
            f"{schema.STATUS_NM_MISMATCH}: M actual={m_actual!r} vs catalog M_ticks={entry.m_ticks!r}"
        )

    # --- Hard-fail sentinel warnings (oracle laundering / single-seed reuse /
    # trivial-RNG leak) unconditionally demote to non-green.
    for warning in warnings:
        if any(warning.startswith(prefix) for prefix in schema.HARD_FAIL_SENTINEL_PREFIXES):
            reasons.append(f"{schema.STATUS_SENTINEL_FAIL}: {warning}")

    # --- Demoted deterministic-convergence warning requires machine-checked
    # H12 support; catalog closed_form_dominant alone is not enough.
    for warning in warnings:
        if warning.startswith(schema.DETERMINISTIC_CONVERGENCE_PREFIX) and not _has_valid_h12_support(result_payload):
            reasons.append(
                f"{schema.STATUS_SENTINEL_FAIL}: {schema.DETERMINISTIC_CONVERGENCE_PREFIX} demotion claimed "
                "without a machine-checked h12_evidence_ref (nontrivial_sample_count > 0); treated as non-green"
            )

    # --- DEFERRED is always non-green, and requires a decision reference plus
    # a resolvable alternate-evidence reference when claimed at all.
    process_level_deferred = str(result_payload.get("verdict")) == "DEFERRED"
    channel_level_deferred = any(
        str(channel_payload.get("verdict")) == "DEFERRED"
        for channel_payload in result_payload.get("channels", {}).values()
    )
    if process_level_deferred or channel_level_deferred:
        decision_ref = result_payload.get("decision_ref")
        alternate_ref = result_payload.get("alternate_evidence_ref")
        if not decision_ref:
            reasons.append(f"{schema.STATUS_DEFERRED}: missing decision_ref")
        resolved_alt = None
        if alternate_ref:
            candidate = Path(str(alternate_ref))
            if not candidate.is_absolute():
                candidate = REPO_ROOT / candidate
            if candidate.is_file():
                resolved_alt = candidate
        if resolved_alt is None:
            reasons.append(f"{schema.STATUS_DEFERRED}: missing or unresolved alternate_evidence_ref")
        reasons.append(f"{schema.STATUS_DEFERRED}: DEFERRED verdicts are never GREEN, decision/evidence notwithstanding")

    # --- Per-channel mechanical re-derivation.
    channels = result_payload.get("channels", {})
    channel_verdicts: dict[str, str] = {}
    primary_channel_names: list[str] = []
    for channel_name, channel_payload in channels.items():
        is_primary = bool(channel_payload.get("is_primary", False))
        if is_primary:
            primary_channel_names.append(channel_name)
        verdict, channel_reasons = rederive_channel(channel_name, channel_payload, is_primary=is_primary)
        channel_verdicts[channel_name] = verdict
        reasons.extend(channel_reasons)

    # F3: the catalog's declared `primary_channel` name must itself be
    # marked `is_primary=true` exactly once -- not zero times (the
    # pre-existing check below), not more than once (ambiguous which
    # channel is actually primary), and not on some OTHER channel name
    # while the catalog's declared primary_channel is absent/False (a
    # "vacuous substitution": e.g. result.json marks a decoy channel
    # is_primary=true while the real primary_channel silently sits at
    # is_primary=false, which would otherwise let the mechanical
    # non-vacuity check above pass against the wrong channel entirely).
    if channels:
        if not primary_channel_names:
            reasons.append(
                f"{schema.STATUS_SCHEMA_INVALID}: no channel in result.json marked is_primary=true "
                f"(catalog primary_channel={entry.primary_channel!r})"
            )
        elif len(primary_channel_names) > 1:
            reasons.append(
                f"{schema.STATUS_PRIMARY_VACUOUS}: {len(primary_channel_names)} channels marked is_primary=true "
                f"({sorted(primary_channel_names)!r}); exactly one is required "
                f"(catalog primary_channel={entry.primary_channel!r})"
            )
        elif entry.primary_channel and primary_channel_names[0] != entry.primary_channel:
            reasons.append(
                f"{schema.STATUS_PRIMARY_VACUOUS}: channel {primary_channel_names[0]!r} is marked "
                f"is_primary=true but catalog primary_channel={entry.primary_channel!r} is not -- "
                "vacuous primary-channel substitution"
            )

    gateable = {
        name: verdict
        for name, verdict in channel_verdicts.items()
        if verdict not in schema.NON_GATING_CHANNEL_VERDICTS
    }

    if not gateable:
        reasons.append(f"{schema.STATUS_NO_GATEABLE_CHANNELS}: every channel is deferred or insufficient")
        mechanical_verdict = schema.STATUS_NO_GATEABLE_CHANNELS
    elif reasons:
        mechanical_verdict = schema.STATUS_FAIL
    elif all(verdict in schema.GREEN_CHANNEL_VERDICTS for verdict in gateable.values()):
        mechanical_verdict = schema.STATUS_PASS
    else:
        mechanical_verdict = schema.STATUS_FAIL

    return ProcessVerdict(mechanical_verdict=mechanical_verdict, channel_verdicts=channel_verdicts, reasons=reasons)
