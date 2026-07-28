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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence.catalog import REPO_ROOT, ProcessEntry  # noqa: E402


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
    if aggregation != "per_tick_vector_w1_mean":
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} uses aggregation={aggregation!r}; "
                "no mechanical re-derivation evaluator implemented for this metric type yet"
            ],
        )

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
    saw_primary = False
    for channel_name, channel_payload in channels.items():
        is_primary = bool(channel_payload.get("is_primary", False))
        saw_primary = saw_primary or is_primary
        verdict, channel_reasons = rederive_channel(channel_name, channel_payload, is_primary=is_primary)
        channel_verdicts[channel_name] = verdict
        reasons.extend(channel_reasons)

    if channels and not saw_primary:
        reasons.append(
            f"{schema.STATUS_SCHEMA_INVALID}: no channel in result.json marked is_primary=true "
            f"(catalog primary_channel={entry.primary_channel!r})"
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
