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
from scripts.l22_evidence.channel_names import normalize_channel_name  # noqa: E402

# Metadata-only version tag for the mechanical re-derivation logic in this
# module (channel/process verdict functions below) -- bump this whenever
# `rederive_channel`/`rederive_process`/the per-channel-kind helpers change
# in a way that could produce a different verdict for the SAME raw
# result.json payload. This never affects any threshold/metric/biology
# value itself; it exists purely so `sweep_provenance.json` (written by
# `scripts/l22_evidence/sweep.py` at evidence-generation time) can record
# which evaluator logic produced a given row's evidence, as an audit trail.
# As of v3 (see below), a recorded value that no longer matches this
# constant is INFORMATIONAL ONLY: it does NOT by itself force a sweep
# rerun (`sweep.evidence_is_valid`) and does NOT by itself mark evidence
# stale (`generator._check_sweep_provenance_staleness`) -- see each
# function's own docstring. Whether already-stored raw evidence can be
# safely re-scored under newer evaluator logic is answered per-channel by
# each `_rederive_*_channel` function's own `required_fields`/
# `missing_fields` check (`schema.STATUS_MISSING_EVALUATOR`), never by
# this version tag alone.
# v2 (F3, Opus5 final review): `rederive_process` now requires the
# catalog's declared `primary_channel` name to be marked `is_primary=true`
# on EXACTLY one channel -- previously a boolean OR across channels meant
# some OTHER channel marked is_primary=true (with the real primary_channel
# silently False) or more than one channel marked is_primary=true could
# both pass through undetected. This changed the verdict for the SAME raw
# result.json payload versus v1; at the time v2 was introduced, evidence
# generated under v1 WAS gated as stale by this field (superseded by the
# v3 policy change below, which decouples this version tag from sweep-
# provenance staleness/rerun-necessity entirely -- see v3's note).
# v3 (P0/P2 re-derivation hardening): two independent fixes, both of which
# can change the mechanical verdict for the SAME raw result.json payload:
#   (1) P0 channel-name-alias fix -- the primary-channel-name comparison in
#       `rederive_process` now normalizes BOTH sides through
#       `channel_names.normalize_channel_name` before comparing, mirroring
#       the runner's own `_CHANNEL_NAME_ALIASES` (e.g. catalog `"rnas"` vs
#       result.json key `"RNAs"`). Previously this was a byte-exact
#       comparison, so every one of the 5 `rnas`-primary processes
#       (Transcription, RNAProcessing, RNAModification, RNADecay,
#       tRNAAminoacylation) spuriously hit `PRIMARY_CHANNEL_VACUOUS`
#       regardless of their real numeric evidence.
#   (2) P2 zero-activity guard -- `_rederive_w1_channel`,
#       `_rederive_per_component_scaled_channel`, and
#       `_rederive_hurdle_channel` now also demote a PRIMARY channel/
#       component to `schema.STATUS_PRIMARY_ACTIVITY_MISSING` (non-green)
#       whenever OC shows zero activity while Karr shows real activity
#       (previously only the SYMMETRIC both-sides-zero case was caught by
#       `PRIMARY_CHANNEL_VACUOUS`; an asymmetric OC-dead/Karr-alive primary
#       channel or component silently computed and could PASS on a
#       scaled/hardcoded distance formula alone).
# IMPORTANT: this version bump is informational only -- it is NOT used to
# gate `sweep_provenance.json` staleness (see
# `generator._check_sweep_provenance_staleness`/`sweep.evidence_is_valid`,
# which no longer compare it against a recorded sentinel value at all).
# Content hashes (`source_hashes`/`sidecar_hashes`) are the sole gating
# authority for whether stored raw evidence is safe to re-derive under
# newer evaluator logic; bumping this constant therefore re-scores every
# existing, byte-identical raw result.json under the v3 logic above
# WITHOUT forcing a sweep rerun, exactly as intended for a pure
# evaluator-side fix with no process/oracle/threshold changes.
# v4 (H12 machine-evidence wiring, scripts/l22_evidence/h12.py):
# `_has_valid_h12_support` now requires (a) the referenced H12 artifact's
# own `verdict` field == "H12_CONFIRMED" (never "H12_OBSERVED_REGIME" or
# any FAIL variant) with `exact_match_rate == 1.0`, `trivial_mismatch_count
# == 0`, `nontrivial_sample_count > 0`, and a satisfied branch-coverage
# requirement (previously `nontrivial_sample_count > 0` alone was
# sufficient -- a hand-edited artifact with a nonzero nontrivial count but
# a real mismatch, or an artifact documenting only a partially-observed
# regime, could previously launder a row); (b) the artifact's recorded
# `predictor_source_sha256_lf_normalized`/`fixture_sha256`/Karr-source
# hashes match a fresh re-hash (LF-normalized for text sources, raw bytes
# for binary `.mat` fixtures -- NOT a git-blob-object hash) of
# the on-disk predictor source / fixture / vendored Karr source referenced
# by the artifact (stale-evidence detection: if h12.py, the fixture, or
# the vendored Karr source has changed since the artifact was generated,
# the artifact no longer proves anything about the CURRENT predictor and
# must be rejected); and (c) `predictor_source_path` is the exact expected
# module path (a dangling or substituted path hard-fails rather than
# soft-trusting whatever file happens to hash-match). Like v3 above, this
# is a pure evaluator/gate-side hardening with no process/oracle/threshold
# change, so it does not force a sweep rerun -- but it DOES change the
# mechanical verdict for the SAME raw result.json payload versus v3 (an
# H12-gated row that cleared the sentinel under v3's weaker check can
# newly fail under v4), so any H12 evidence generated/verified under v3
# semantics must be treated as stale, not silently re-scored as
# equivalent.
# v4 artifact-gate hardening (Opus5 round-3 follow-up, same v4 tag --
# these are within-v4 gate-hardening fixes, not a further semantic verdict
# change requiring a version bump): `validate_h12_support` additionally
# now (d) cross-checks the artifact's own `process` field against the
# `expected_process` the caller resolved it for, rejecting cross-process
# substitution via a mis-keyed `h12_evidence_index.json` side-index entry;
# (e) requires `n_seeds`/`m_ticks` to equal the catalog's real
# `CATALOG_N_M[process]` (a shrunken/degenerate sample domain no longer
# passes even at 100% match); (f) explicitly rejects `bool` values for
# every numeric count/rate field (Python's `bool` is an `int` subtype, so
# `True == 1.0`/`False == 0` could otherwise silently satisfy those
# checks); (g) requires internal count consistency
# (`exact_match_count == nontrivial_sample_count`,
# `nontrivial_sample_count + trivial_checked_count <= total_sample_count`);
# (h) requires a fully-`match`/`accepted` `oracle_manifest_cross_check`
# and full per-seed `oracle_seed_file_sha256` coverage; (i) requires a
# well-formed `raw_prediction_hash`; and (j) pins `formula_version` and
# the Karr citation's `upstream_repo`/`upstream_commit`/`line_ranges` to
# this module's own registry constants, rejecting a forged/edited claim
# even where the referenced files' hashes still happen to match.
EVALUATOR_SCHEMA_VERSION = 4


@dataclass(frozen=True)
class ProcessVerdict:
    mechanical_verdict: str
    channel_verdicts: dict[str, str]
    reasons: list[str]


def h12_support_reason(result_payload: dict[str, Any], expected_process: str | None = None) -> str | None:
    """Return None if the linked H12 artifact is valid, else a short reason
    string explaining why it was rejected (used by both the gate below and
    by tests/diagnostics that want the "why").

    `expected_process` (the process name this evidence is being consulted
    for -- callers should always pass the row's own catalog process name)
    is forwarded to `h12.validate_h12_support` so it can reject cross-
    process substitution: without it, a `h12_evidence_ref` resolved via a
    mis-keyed `h12_evidence_index.json` side-index entry could point one
    process's row at a DIFFERENT process's real, valid H12_CONFIRMED
    artifact, and every other check below would still pass (they only
    validate the artifact's own internal consistency, not that it is
    actually evidence for the row being scored).

    Requirements (see scripts/l22_evidence/h12.py:validate_h12_support for
    the authoritative schema/hash checks -- this function is a thin loader
    that resolves ``h12_evidence_ref`` to a JSON payload and delegates the
    actual acceptance logic there so the producer and consumer of the H12
    artifact schema cannot drift apart):
      1. ``h12_evidence_ref`` resolves to a readable JSON file.
      2. ``scripts.l22_evidence.h12.validate_h12_support(payload,
         expected_process=expected_process)`` returns None (verdict ==
         H12_CONFIRMED, artifact's own `process` field matches
         `expected_process`, 100% exact match, zero trivial mismatches,
         numerically-typed (non-bool) counts/rates, full required branch
         coverage, catalog N/M coverage floor met, pinned predictor path,
         fresh LF-normalized hashes for the predictor module/fixture/
         vendored Karr source, a fully-accepted oracle-manifest cross-
         check, full per-seed raw-oracle hash coverage, a well-formed
         `raw_prediction_hash`, formula_version/Karr-citation pinned to
         the predictor registry, and non-negated anti-laundering
         attestation fields -- no soft-trust for any of these).
    """
    ref = result_payload.get("h12_evidence_ref")
    if not ref:
        return "h12_evidence_ref missing"
    path = Path(str(ref))
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        return f"h12_evidence_ref does not resolve to a file: {ref!r}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"h12_evidence_ref unreadable/invalid JSON: {exc}"

    from scripts.l22_evidence import h12  # local import: avoid import cost when H12 isn't invoked

    return h12.validate_h12_support(payload, expected_process=expected_process, repo_root=REPO_ROOT)


def _has_valid_h12_support(result_payload: dict[str, Any], expected_process: str | None = None) -> bool:
    """True iff a linked H12 evidence file exists, is not stale relative to
    the current predictor/fixture on disk, is bound to `expected_process`
    (no cross-process substitution), and machine-confirms a 100%
    exact-match rate on a nonzero count of nontrivial samples covering the
    catalog's real N/M.

    This is the *only* way ``PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE`` is
    allowed to avoid demoting a row to non-green (per
    docs/phase_f/l2_2_design_a/LAUNDERING_VS_CONVERGENCE.md's H12 anchor).
    Catalog-level ``closed_form_dominant: confirmed*`` alone is a soft flag
    and is NOT sufficient support on its own.
    """
    return h12_support_reason(result_payload, expected_process) is None


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

    # Consistent with the `per_component_scaled` path's own
    # `_is_nonnegative_count` validation on `component_n_nonzero_oc`/
    # `component_n_nonzero_karr`: a non-finite or negative nonzero count is
    # malformed raw evidence, never a legitimate "insufficient samples"
    # (which the `== 0`/`< MIN_NONZERO_EVENTS` comparisons below would
    # otherwise silently accept for e.g. NaN or a negative count).
    if not _is_nonnegative_count(n_nonzero_oc) or not _is_nonnegative_count(n_nonzero_karr):
        return (
            schema.STATUS_MISSING_EVALUATOR,
            [
                f"{schema.STATUS_MISSING_EVALUATOR}: channel {name!r} has negative or non-finite nonzero "
                f"counts (n_nonzero_oc={n_nonzero_oc!r}, n_nonzero_karr={n_nonzero_karr!r})"
            ],
        )

    if is_primary and n_nonzero_oc == 0 and n_nonzero_karr == 0:
        return (
            schema.STATUS_PRIMARY_VACUOUS,
            [
                f"{schema.STATUS_PRIMARY_VACUOUS}: primary channel {name!r} has zero nonzero observations "
                "on both OC and Karr (non-vacuous primary channel requirement failed)"
            ],
        )

    # P2 zero-activity guard: OC showing literally zero activity while Karr
    # shows real activity is not "insufficient samples" (that verdict is
    # non-gating and would silently let the process PASS via its other
    # channels) -- it means the SUT never exhibited the behavior at all on
    # a channel the catalog designates as primary. Must be checked BEFORE
    # the MIN_NONZERO_EVENTS branch below, since 0 < MIN_NONZERO_EVENTS is
    # always true and would otherwise swallow this case as
    # INSUFFICIENT_SAMPLES first. Symmetric both-zero is handled above and
    # is deliberately excluded here (n_nonzero_karr > 0 is required).
    if is_primary and n_nonzero_oc == 0 and n_nonzero_karr > 0:
        return (
            schema.STATUS_PRIMARY_ACTIVITY_MISSING,
            [
                f"{schema.STATUS_PRIMARY_ACTIVITY_MISSING}: primary channel {name!r} has zero nonzero "
                f"observations on OC while Karr has {n_nonzero_karr} (OC never exhibited this primary "
                "channel's activity at all)"
            ],
        )

    # Primary low-sample false-green fix: checked AFTER both-zero VACUOUS
    # and OC-zero/Karr-nonzero ACTIVITY_MISSING above have already been
    # ruled out, so this only fires for a primary channel with SOME
    # activity on both sides but not enough to trust. Unlike the generic,
    # NON-GATING `"INSUFFICIENT_SAMPLES"` branch immediately below (which
    # still applies to non-primary channels), a primary channel below
    # MIN_NONZERO_EVENTS on either side must gate the process non-green --
    # otherwise it is silently excluded from aggregation
    # (`schema.NON_GATING_CHANNEL_VERDICTS`) and the process could go
    # green off its OTHER, non-primary channels alone despite its actual
    # primary comparison never having been validated at adequate sample
    # size.
    if is_primary and (n_nonzero_oc < schema.MIN_NONZERO_EVENTS or n_nonzero_karr < schema.MIN_NONZERO_EVENTS):
        return (
            schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES,
            [
                f"{schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES}: primary channel {name!r} has "
                f"n_nonzero_oc={n_nonzero_oc}, n_nonzero_karr={n_nonzero_karr}; below "
                f"MIN_NONZERO_EVENTS={schema.MIN_NONZERO_EVENTS} on at least one side (primary comparison "
                "not validated at adequate sample size)"
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
    activity_missing_components: list[str] = []
    insufficient_samples_components: list[str] = []
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

        # P2 zero-activity guard: this component's OC side never fired at
        # all while Karr's did -- do not let a hardcoded/hand-tuned
        # `component_scales` divisor launder that into a passing
        # scaled_w1. Independent of (and checked in addition to) the
        # all-both-zero `all_vacuous` check below; does not touch
        # `component_scales`/`scaled_distance_threshold` themselves.
        if is_primary and float(n_oc) == 0.0 and float(n_karr) > 0.0:
            activity_missing_components.append(component_name)
            reasons.append(
                f"{schema.STATUS_PRIMARY_ACTIVITY_MISSING}: channel {name!r} component {component_name!r} "
                f"has zero nonzero observations on OC while Karr has {n_karr} (OC never exhibited this "
                "primary component's activity at all)"
            )
            continue

        # Primary low-sample false-green fix: checked AFTER the both-zero
        # (`all_vacuous`, aggregated below) and OC-zero/Karr-nonzero
        # (`activity_missing_components` above) cases -- a component where
        # BOTH sides are genuinely zero is deliberately excluded here (it
        # is a trivial always-zero component, not a low-sample one; see
        # `test_per_component_not_vacuous_when_only_one_component_is_zero_nonzero`),
        # matching the existing "a single trivial-always-zero component
        # alongside otherwise-real components is not vacuous by itself"
        # policy. Joint semantics: ANY primary component below
        # MIN_NONZERO_EVENTS on either side gates the whole channel
        # non-green, mirroring how a single `activity_missing_components`
        # entry already gates the whole channel above.
        component_is_trivially_zero = float(n_oc) == 0.0 and float(n_karr) == 0.0
        if (
            is_primary
            and not component_is_trivially_zero
            and (float(n_oc) < schema.MIN_NONZERO_EVENTS or float(n_karr) < schema.MIN_NONZERO_EVENTS)
        ):
            insufficient_samples_components.append(component_name)
            reasons.append(
                f"{schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES}: channel {name!r} component {component_name!r} "
                f"has n_oc={n_oc}, n_karr={n_karr}; below MIN_NONZERO_EVENTS={schema.MIN_NONZERO_EVENTS} on "
                "at least one side (primary component comparison not validated at adequate sample size)"
            )
            continue

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

    if activity_missing_components:
        return schema.STATUS_PRIMARY_ACTIVITY_MISSING, reasons

    if insufficient_samples_components:
        return schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES, reasons

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

    # P2 zero-activity guard, hurdle flavor: OC recorded zero events across
    # the whole ensemble while Karr recorded real events -- the event mask
    # never fired on the OC side at all. Distinct from (and checked in
    # addition to) the symmetric both-zero VACUOUS check above.
    if is_primary and n_events_oc == 0 and n_events_karr > 0:
        # Preserve any reasons already accumulated above (event-rate FAIL,
        # conditional-component FAILs) rather than replacing them with a
        # fresh single-item list -- a hand-tampered stored PASS on those
        # earlier checks must remain visible in `reasons` alongside this
        # gating verdict, exactly like the `per_component_scaled` path's
        # `activity_missing_components` handling already does.
        reasons.append(
            f"{schema.STATUS_PRIMARY_ACTIVITY_MISSING}: primary channel {name!r} recorded zero events on "
            f"OC while Karr recorded {n_events_karr} across the whole ensemble (OC never exhibited this "
            "primary channel's activity at all)"
        )
        return schema.STATUS_PRIMARY_ACTIVITY_MISSING, reasons

    # Primary low-sample false-green fix, hurdle flavor: checked AFTER the
    # both-zero VACUOUS and OC-zero/Karr-nonzero ACTIVITY_MISSING cases
    # above -- reaching this point guarantees n_events_oc > 0, so this only
    # fires when at least one side's event count is below
    # MIN_NONZERO_EVENTS (either a low-but-nonzero OC count, or Karr
    # recording fewer/zero events than MIN_NONZERO_EVENTS while OC did
    # fire). Preserves accumulated `reasons`, same as the ACTIVITY_MISSING
    # fix above.
    if is_primary and (n_events_oc < schema.MIN_NONZERO_EVENTS or n_events_karr < schema.MIN_NONZERO_EVENTS):
        reasons.append(
            f"{schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES}: primary channel {name!r} recorded "
            f"n_events_oc={n_events_oc}, n_events_karr={n_events_karr} across the whole ensemble; below "
            f"MIN_NONZERO_EVENTS={schema.MIN_NONZERO_EVENTS} on at least one side (primary hurdle event "
            "count not validated at adequate sample size)"
        )
        return schema.STATUS_PRIMARY_INSUFFICIENT_SAMPLES, reasons

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
        if warning.startswith(schema.DETERMINISTIC_CONVERGENCE_PREFIX):
            rejection_reason = h12_support_reason(result_payload, process_name)
            if rejection_reason is not None:
                reasons.append(
                    f"{schema.STATUS_SENTINEL_FAIL}: {schema.DETERMINISTIC_CONVERGENCE_PREFIX} demotion claimed "
                    f"without valid machine-checked h12_evidence_ref ({rejection_reason}); treated as non-green"
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
        elif not entry.primary_channel:
            # F5/F3 gap fix: the previous `elif entry.primary_channel and
            # ...` guard silently SKIPPED this whole check whenever the
            # catalog's own `primary_channel` field was itself empty/None,
            # meaning ANY single is_primary=true channel passed unchallenged
            # -- exactly the vacuous-substitution risk this block exists to
            # prevent, just triggered by a missing catalog declaration
            # rather than a name mismatch. A non-empty `primary_channel` is
            # therefore asserted explicitly, never inferred as "nothing to
            # check against".
            reasons.append(
                f"{schema.STATUS_PRIMARY_VACUOUS}: catalog primary_channel is empty/missing for "
                f"{entry.name!r} -- cannot verify channel {primary_channel_names[0]!r} (is_primary=true) "
                "is the intended primary channel, not a vacuous substitution"
            )
        elif normalize_channel_name(primary_channel_names[0]) != normalize_channel_name(entry.primary_channel):
            # P0 fix: normalize BOTH sides through the shared
            # `channel_names.normalize_channel_name` before comparing. The
            # runner already normalizes channel-name aliases (e.g. catalog
            # `"rnas"` -> result.json key `"RNAs"`) before ever writing
            # `result.json`, but `catalog.py` deliberately reads
            # `entry.primary_channel` raw/un-normalized (so
            # `catalog_soft_flags` stays byte-exact to the YAML) -- a
            # byte-exact comparison here therefore spuriously mismatched
            # every aliased process regardless of its real numeric
            # evidence. Normalizing both sides (not just the catalog side)
            # keeps this a no-op for every already-normalized/non-aliased
            # process name.
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
