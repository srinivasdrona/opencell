"""Resumable cohort selector/auditor for the Cytokinesis + FtsZPolymerization
division-window dual-tap cohort (division-censor-contract, preregistered
2026-09-08, docs/phase_f/l2_event/division_window_spec.json's
``selection_contract``).

WHAT THIS MODULE ENFORCES

* Deterministic ascending attempted seeds starting at
  ``candidate_seed_start`` (0). Every seed must be attempted exactly once;
  no skipping, no resampling, no out-of-order jumps counted as valid until
  the seeds preceding them are also attempted.
* A common censoring horizon (``max_search_ticks``, 100000) every
  RIGHT_CENSORED claim must have been attempted at to count as a valid
  censor. A censor record at a smaller horizon does not prove
  non-completion over the full horizon and is reported as invalid/pending
  re-attempt, never silently accepted.
* Mutual exclusivity: a COMPLETED record requires both trace files to
  exist and validate; a RIGHT_CENSORED record requires NEITHER trace file
  to exist. A record (or on-disk state) violating this raises
  :class:`CohortContractError` -- this is a hard mechanical contract
  violation, never silently repaired.
* The authoritative cohort is the first ``required_completed_windows``
  (50) COMPLETED seeds in ascending order, drawn ONLY from the
  CONTIGUOUS prefix of attempted seeds starting at
  ``candidate_seed_start`` -- a COMPLETED trace for a seed that lies
  beyond the first gap in the attempt ledger is preserved (never deleted
  or invalidated) but does not yet count toward the cohort until every
  seed before it has also been attempted. This is the mechanical
  enforcement of "no gaps, no aliases" and "return the exact next seed".

WHAT THIS MODULE NEVER DOES

* Never launches MATLAB.
* Never rewrites or deletes any existing trace (.mat) file.
* Never invents a RIGHT_CENSORED (or COMPLETED) record for a seed that has
  neither an on-disk ``division_window_attempt.json`` nor a validating
  trace pair -- an empty/absent seed directory is reported as a GAP
  requiring a real attempt, never silently treated as "probably censored"
  from prose/plan.md narrative alone.
* Never treats a censored attempt as counting toward
  ``required_completed_windows``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.division_window_spec import (  # noqa: E402
    attempt_record_filename,
    candidate_seed_start,
    censor_record_required_identity_fields,
    required_completed_windows,
    selection_horizon_max_search_ticks,
)
from scripts.l2_event.prepare_cytokinesis_cohort import (  # noqa: E402
    autodiscover_karr_native_roots,
)
from scripts.l2_event.validate_dual_division_canary import (  # noqa: E402
    CYTOKINESIS_N_TICKS,
    FTSZ_N_TICKS,
    event_window_dir,
    validate_dual_division_canary,
)

COMPLETED = "COMPLETED"
RIGHT_CENSORED = "RIGHT_CENSORED"
VALID_STATUSES = (COMPLETED, RIGHT_CENSORED)

_SEED_DIR_RE = re.compile(r"per_process_traces_v2_event_s(\d+)$")


class CohortContractError(Exception):
    """Raised for a mechanical division-censor-contract violation this
    module detects directly from on-disk state or a record file: a
    RIGHT_CENSORED record co-existing with trace files, a COMPLETED
    record with a missing/mismatched trace file, an attempt-record
    ``status`` outside :data:`VALID_STATUSES`, or a malformed record
    file. Never silently repaired or downgraded to a warning."""


@dataclass(frozen=True)
class AttemptRecord:
    """One seed's resolved attempt outcome, either read directly from a
    real ``division_window_attempt.json`` or synthesized (``backfilled=
    True``) from an already-validated COMPLETED trace pair that predates
    this contract's attempt-record writer."""

    seed: int
    status: str
    max_search_ticks: int | None
    source_root: Path
    mnrnd_provider_sha256: str | None = None
    dnadamage_source_resolved_sha256: str | None = None
    onset_tick: int | None = None
    completion_tick: int | None = None
    cytokinesis_trace_sha256: str | None = None
    ftsz_trace_sha256: str | None = None
    backfilled: bool = False
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "status": self.status,
            "max_search_ticks": self.max_search_ticks,
            "source_root": str(self.source_root),
            "mnrnd_provider_sha256": self.mnrnd_provider_sha256,
            "dnadamage_source_resolved_sha256": self.dnadamage_source_resolved_sha256,
            "onset_tick": self.onset_tick,
            "completion_tick": self.completion_tick,
            "cytokinesis_trace_sha256": self.cytokinesis_trace_sha256,
            "ftsz_trace_sha256": self.ftsz_trace_sha256,
            "backfilled": self.backfilled,
            "reason": self.reason,
        }


def _trace_paths(seed: int, *, karr_native_root: Path) -> tuple[Path, Path]:
    out_dir = event_window_dir(seed, karr_native_root=karr_native_root)
    cyt_path = out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat"
    ftsz_path = out_dir / f"FtsZPolymerization_{FTSZ_N_TICKS}ticks.mat"
    return cyt_path, ftsz_path


def read_attempt_record_file(path: Path) -> dict[str, Any] | None:
    """Parse one ``division_window_attempt.json`` file. Returns ``None``
    if ``path`` does not exist. Raises :class:`CohortContractError` if it
    exists but is not valid JSON, or is missing the ``status`` key, or
    ``status`` is outside :data:`VALID_STATUSES` -- never silently
    ignored."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CohortContractError(f"{path}: not valid JSON: {exc}") from exc
    if "status" not in raw:
        raise CohortContractError(f"{path}: missing required 'status' key")
    if raw["status"] not in VALID_STATUSES:
        raise CohortContractError(
            f"{path}: status {raw['status']!r} is not one of {VALID_STATUSES}"
        )
    return raw


def resolve_seed_attempt(
    seed: int, *, karr_native_root: Path
) -> AttemptRecord | None:
    """Resolve seed's attempt outcome under one search root.

    Precedence: a real ``division_window_attempt.json`` file (validated
    for mutual exclusivity against the seed's own trace files) wins over
    backfill. If no attempt-record file exists, attempt to backfill a
    COMPLETED record from an already-validated trace pair (never a
    RIGHT_CENSORED backfill -- see module docstring: an absent/empty
    directory with no record file is always a GAP, never inferred
    censoring). Returns ``None`` if this root has neither for this seed.
    """
    out_dir = event_window_dir(seed, karr_native_root=karr_native_root)
    record_path = out_dir / attempt_record_filename()
    cyt_path, ftsz_path = _trace_paths(seed, karr_native_root=karr_native_root)
    cyt_exists = cyt_path.exists()
    ftsz_exists = ftsz_path.exists()

    raw = read_attempt_record_file(record_path)
    if raw is not None:
        status = raw["status"]
        if status == RIGHT_CENSORED and (cyt_exists or ftsz_exists):
            raise CohortContractError(
                f"seed {seed}: RIGHT_CENSORED attempt record at {record_path} co-exists with a "
                f"trace file (cytokinesis_exists={cyt_exists}, ftsz_exists={ftsz_exists}) -- "
                "mutually exclusive by contract, never silently reconciled"
            )
        if status == COMPLETED and not (cyt_exists and ftsz_exists):
            raise CohortContractError(
                f"seed {seed}: COMPLETED attempt record at {record_path} but trace file(s) missing "
                f"(cytokinesis_exists={cyt_exists}, ftsz_exists={ftsz_exists})"
            )
        if status == COMPLETED:
            canary = validate_dual_division_canary(seed, karr_native_root=karr_native_root)
            if canary.status != "PASS":
                raise CohortContractError(
                    f"seed {seed}: COMPLETED attempt record at {record_path} but the paired trace "
                    f"files fail combined validation: {canary.reasons}"
                )
        return AttemptRecord(
            seed=seed,
            status=status,
            max_search_ticks=raw.get("max_search_ticks"),
            source_root=karr_native_root,
            mnrnd_provider_sha256=raw.get("mnrnd_provider_sha256"),
            dnadamage_source_resolved_sha256=raw.get("dnadamage_source_resolved_sha256"),
            onset_tick=raw.get("onset_tick"),
            completion_tick=raw.get("completion_tick"),
            cytokinesis_trace_sha256=raw.get("cytokinesis_trace_sha256"),
            ftsz_trace_sha256=raw.get("ftsz_trace_sha256"),
            backfilled=False,
            reason=str(raw.get("reason", "")),
        )

    # No attempt-record file. Only a COMPLETED outcome can ever be
    # mechanically backfilled from trace files alone -- see module
    # docstring: an absent/empty directory is always a gap, never an
    # inferred censor.
    if not (cyt_exists and ftsz_exists):
        return None
    canary = validate_dual_division_canary(seed, karr_native_root=karr_native_root)
    if canary.status != "PASS":
        raise CohortContractError(
            f"seed {seed}: trace files exist at {out_dir} but fail combined validation and no "
            f"attempt record exists to explain the discrepancy: {canary.reasons}"
        )
    return AttemptRecord(
        seed=seed,
        status=COMPLETED,
        max_search_ticks=None,
        source_root=karr_native_root,
        mnrnd_provider_sha256=canary.cytokinesis_provider_sha256,
        dnadamage_source_resolved_sha256=canary.cytokinesis_dnadamage_source_sha256,
        onset_tick=canary.cytokinesis_onset_tick,
        completion_tick=canary.cytokinesis_window_anchor,
        cytokinesis_trace_sha256=canary.cytokinesis_sha256,
        ftsz_trace_sha256=canary.ftsz_sha256,
        backfilled=True,
        reason="backfilled from validated trace pair; no division_window_attempt.json present",
    )


AUTHORITATIVE_ROOT_SUBDIR = "dual_division_cohort_current"
# Fallback main-checkout candidates (module-level, not inlined, so tests
# can monkeypatch them to keep authoritative_karr_native_root's "not found
# anywhere" behavior deterministic regardless of what happens to exist on
# the local dev machine's E:\opencell checkout).
MAIN_CHECKOUT_KARR_NATIVE_ROOT_WINDOWS = Path("E:/opencell/data/m1_sources/karr_native")
MAIN_CHECKOUT_KARR_NATIVE_ROOT_WSL = Path("/mnt/e/opencell/data/m1_sources/karr_native")


def authoritative_karr_native_root(*, repo_root: Path = REPO_ROOT) -> Path:
    """The dedicated, homogeneous ``dual_division_cohort_current`` banking
    root (division-censor-contract, 2026-09-08; named authoritative per
    Opus's 2026-09-09 re-review) every dual-tap Cytokinesis+
    FtsZPolymerization extraction should ultimately be consolidated into.
    Checked in the same (worktree, main-checkout-Windows-path,
    main-checkout-WSL-path) priority order
    ``ftsz_pre_division_evidence.DEFAULT_DATA_ROOTS`` already uses; returns
    the first candidate that exists, or the worktree-relative candidate
    (the canonical target a future consolidation would create) if none do
    yet. Preferred FIRST by :func:`default_search_roots`, never treated as
    the ONLY valid root -- see :func:`discover_ledger`'s multi-root,
    never-first-wins contradiction check."""
    candidates = (
        repo_root / "data" / "m1_sources" / "karr_native" / AUTHORITATIVE_ROOT_SUBDIR,
        MAIN_CHECKOUT_KARR_NATIVE_ROOT_WINDOWS / AUTHORITATIVE_ROOT_SUBDIR,
        MAIN_CHECKOUT_KARR_NATIVE_ROOT_WSL / AUTHORITATIVE_ROOT_SUBDIR,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def default_search_roots(*, repo_root: Path = REPO_ROOT) -> list[Path]:
    """Autodiscovery order: the authoritative dedicated root FIRST (see
    :func:`authoritative_karr_native_root`), then every root
    ``prepare_cytokinesis_cohort.autodiscover_karr_native_roots`` already
    finds (this worktree's own scattered karr_native root, the main
    checkout, and sibling worktrees) -- reused, not re-derived. Listing
    the authoritative root first is a preference for where a CONSOLIDATED
    record should be found/written, never an exclusivity rule: every root
    is still searched, and :func:`discover_ledger` hard-fails on any
    cross-root contradiction rather than silently trusting whichever root
    happens to be listed first."""
    roots: list[Path] = []
    authoritative = authoritative_karr_native_root(repo_root=repo_root)
    if authoritative.exists() and authoritative not in roots:
        roots.append(authoritative)
    for root in autodiscover_karr_native_roots(repo_root=repo_root):
        if root not in roots:
            roots.append(root)
    return roots


# Fields that define an AttemptRecord's real identity -- two records for
# the SAME seed found under different roots must agree on every one of
# these, or discover_ledger raises CohortContractError rather than
# silently preferring one root over another (Opus re-review, 2026-09-09:
# "never first-wins").
_IDENTITY_FIELDS = (
    "status",
    "onset_tick",
    "completion_tick",
    "cytokinesis_trace_sha256",
    "ftsz_trace_sha256",
    "dnadamage_source_resolved_sha256",
    "mnrnd_provider_sha256",
)


def _records_agree(a: AttemptRecord, b: AttemptRecord) -> bool:
    return all(getattr(a, field_name) == getattr(b, field_name) for field_name in _IDENTITY_FIELDS)


def discover_ledger(
    search_roots: list[Path], *, max_seed_scan: int = 10_000
) -> dict[int, AttemptRecord]:
    """Build ``{seed: AttemptRecord}`` across every search root.

    Multi-root integrity (Opus re-review, 2026-09-09): EVERY root is
    inspected for EVERY seed -- never "first root wins". If more than one
    root has a record for the same seed, they must agree on every
    identity field (:data:`_IDENTITY_FIELDS`); any disagreement raises
    :class:`CohortContractError` immediately (a hard mechanical
    contradiction between two worktrees' claims about the same seed is
    never silently resolved by picking one). Agreeing duplicates are
    deduplicated (the authoritative root's copy is kept when present,
    else the first search order match) -- this is not "first-wins" in the
    unsafe sense, because agreement was verified first.

    Never scans past the highest seed number any root's
    ``per_process_traces_v2_event_s*`` directory actually names (bounded
    additionally by ``max_seed_scan`` as a sanity cap)."""
    seed_numbers: set[int] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for child in root.glob("per_process_traces_v2_event_s*"):
            match = _SEED_DIR_RE.search(child.name)
            if match:
                seed = int(match.group(1))
                if seed <= max_seed_scan:
                    seed_numbers.add(seed)

    ledger: dict[int, AttemptRecord] = {}
    for seed in sorted(seed_numbers):
        records_by_root: list[tuple[Path, AttemptRecord]] = []
        for root in search_roots:
            record = resolve_seed_attempt(seed, karr_native_root=root)
            if record is not None:
                records_by_root.append((root, record))
        if not records_by_root:
            continue
        canonical_root, canonical_record = records_by_root[0]
        for other_root, other_record in records_by_root[1:]:
            if not _records_agree(canonical_record, other_record):
                raise CohortContractError(
                    f"seed {seed}: contradictory attempt records across roots -- "
                    f"{canonical_root} reports {canonical_record.to_json()} but "
                    f"{other_root} reports {other_record.to_json()}. Never resolved by "
                    "first-wins; investigate and reconcile by hand before re-running."
                )
        ledger[seed] = canonical_record
    return ledger


@dataclass
class CohortAudit:
    candidate_seed_start: int
    required_completed_windows: int
    selection_horizon_max_search_ticks: int
    contiguous_prefix_end: int  # last seed s such that every seed in [start, s] has a valid record
    next_seed_to_attempt: int
    attempted_seeds: list[int] = field(default_factory=list)
    completed_seeds: list[int] = field(default_factory=list)
    censored_seeds: list[int] = field(default_factory=list)
    invalid_censor_seeds: list[dict[str, Any]] = field(default_factory=list)
    gap_seeds: list[int] = field(default_factory=list)
    premature_seeds: list[int] = field(default_factory=list)
    duplicate_trace_hashes: list[dict[str, Any]] = field(default_factory=list)
    source_hash_mismatches: list[dict[str, Any]] = field(default_factory=list)
    selected_seeds: list[int] = field(default_factory=list)
    selection_satisfied: bool = False
    attempted_count: int = 0
    completed_count: int = 0
    completion_fraction: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_seed_start": self.candidate_seed_start,
            "required_completed_windows": self.required_completed_windows,
            "selection_horizon_max_search_ticks": self.selection_horizon_max_search_ticks,
            "contiguous_prefix_end": self.contiguous_prefix_end,
            "next_seed_to_attempt": self.next_seed_to_attempt,
            "attempted_seeds": self.attempted_seeds,
            "completed_seeds": self.completed_seeds,
            "censored_seeds": self.censored_seeds,
            "invalid_censor_seeds": self.invalid_censor_seeds,
            "gap_seeds": self.gap_seeds,
            "premature_seeds": self.premature_seeds,
            "duplicate_trace_hashes": self.duplicate_trace_hashes,
            "source_hash_mismatches": self.source_hash_mismatches,
            "selected_seeds": self.selected_seeds,
            "selection_satisfied": self.selection_satisfied,
            "attempted_count": self.attempted_count,
            "completed_count": self.completed_count,
            "completion_fraction": self.completion_fraction,
        }


def _current_censor_identity_values() -> dict[str, str]:
    """The CURRENT run's genuine identity values for every field
    :func:`~scripts.l2_event.division_window_spec.censor_record_required_identity_fields`
    names. Computed lazily (only when a RIGHT_CENSORED record actually
    needs checking) so importing this module, or auditing a ledger with
    no censored seeds, never requires a real WCM source tree or MATLAB
    installation to be present."""
    dnadamage = launcher.current_genuine_dnadamage_source()["patched_sha256_lf_normalized"]
    mnrnd_provider = launcher.current_genuine_mnrnd_provider()["sha256_lf_normalized"]
    return {
        "dnadamage_source_resolved_sha256": dnadamage,
        "mnrnd_provider_sha256": mnrnd_provider,
    }


def audit_cohort(
    search_roots: list[Path] | None = None,
    *,
    ledger: dict[int, AttemptRecord] | None = None,
) -> CohortAudit:
    """The single entry point this module exposes. Builds (or accepts a
    pre-built, e.g. test-fixture) ledger, then mechanically derives the
    contiguous-attempt prefix, the valid censored/completed partitions,
    duplicate/source-mismatch findings, and the selected cohort -- never
    reports a satisfied selection for fewer than
    ``required_completed_windows`` genuinely contiguous completions."""
    start = candidate_seed_start()
    required = required_completed_windows()
    horizon = selection_horizon_max_search_ticks()

    if ledger is None:
        roots = search_roots if search_roots is not None else default_search_roots()
        ledger = discover_ledger(roots)

    # Reclassify any RIGHT_CENSORED record whose own max_search_ticks does
    # not match the required horizon, OR whose required identity fields
    # (dnadamage_source_resolved_sha256/mnrnd_provider_sha256) do not bind
    # the CURRENT run's genuine values, as NOT attempted (contract-invalid
    # censor -- see module docstring's horizon/identity requirements). It
    # is reported separately, never silently dropped. Identity values are
    # only computed if at least one RIGHT_CENSORED record exists to check
    # (lazy -- see _current_censor_identity_values).
    invalid_censor_seeds: list[dict[str, Any]] = []
    effective_ledger: dict[int, AttemptRecord] = {}
    current_identity: dict[str, str] | None = None
    required_identity_fields = censor_record_required_identity_fields()
    for seed, record in ledger.items():
        if record.status != RIGHT_CENSORED:
            effective_ledger[seed] = record
            continue
        if record.max_search_ticks != horizon:
            invalid_censor_seeds.append(
                {
                    "seed": seed,
                    "recorded_max_search_ticks": record.max_search_ticks,
                    "required_max_search_ticks": horizon,
                    "reason": "RIGHT_CENSORED record's own horizon does not match the required "
                    "selection-contract horizon -- does not prove non-completion over the full "
                    "horizon, must be re-attempted",
                }
            )
            continue
        if current_identity is None:
            current_identity = _current_censor_identity_values()
        identity_mismatch = None
        for identity_field in required_identity_fields:
            recorded_value = getattr(record, identity_field, None)
            expected_value = current_identity.get(identity_field)
            if recorded_value is None or recorded_value != expected_value:
                identity_mismatch = (identity_field, recorded_value, expected_value)
                break
        if identity_mismatch is not None:
            field_name, recorded_value, expected_value = identity_mismatch
            invalid_censor_seeds.append(
                {
                    "seed": seed,
                    "identity_field": field_name,
                    "recorded_value": recorded_value,
                    "required_value": expected_value,
                    "reason": f"RIGHT_CENSORED record's {field_name} does not bind the current "
                    "run's genuine identity -- a censored claim produced under a different "
                    "source/provider is not comparable evidence about the current model and "
                    "must never advance the contiguous attempted-seed prefix",
                }
            )
            continue
        effective_ledger[seed] = record

    # Contiguous-attempt prefix from candidate_seed_start.
    contiguous_prefix_end = start - 1
    s = start
    while s in effective_ledger:
        contiguous_prefix_end = s
        s += 1
    next_seed_to_attempt = contiguous_prefix_end + 1

    max_seen_seed = max(effective_ledger) if effective_ledger else start - 1
    gap_seeds = sorted(
        seed
        for seed in range(next_seed_to_attempt, max_seen_seed + 1)
        if seed not in effective_ledger
    )
    premature_seeds = sorted(seed for seed in effective_ledger if seed > contiguous_prefix_end)

    attempted_seeds = sorted(seed for seed in effective_ledger if seed <= contiguous_prefix_end)
    completed_seeds = sorted(
        seed for seed in attempted_seeds if effective_ledger[seed].status == COMPLETED
    )
    censored_seeds = sorted(
        seed for seed in attempted_seeds if effective_ledger[seed].status == RIGHT_CENSORED
    )

    # Source-hash binding: every COMPLETED record within the contiguous
    # prefix must share one dnadamage_source_resolved_sha256 (dec-005).
    # A censored record with a recorded source hash is checked too, if
    # present (older/backfilled censor records may not carry one yet).
    source_hashes = {
        effective_ledger[seed].dnadamage_source_resolved_sha256
        for seed in attempted_seeds
        if effective_ledger[seed].dnadamage_source_resolved_sha256
    }
    source_hash_mismatches: list[dict[str, Any]] = []
    if len(source_hashes) > 1:
        for seed in attempted_seeds:
            sha = effective_ledger[seed].dnadamage_source_resolved_sha256
            if sha:
                source_hash_mismatches.append({"seed": seed, "dnadamage_source_resolved_sha256": sha})

    # Duplicate/aliased trace content: two distinct seeds must never share
    # a cytokinesis_trace_sha256 or ftsz_trace_sha256.
    seen_cyt: dict[str, int] = {}
    seen_ftsz: dict[str, int] = {}
    duplicate_trace_hashes: list[dict[str, Any]] = []
    for seed in completed_seeds:
        record = effective_ledger[seed]
        if record.cytokinesis_trace_sha256:
            prior = seen_cyt.get(record.cytokinesis_trace_sha256)
            if prior is not None:
                duplicate_trace_hashes.append(
                    {"seed": seed, "duplicate_of_seed": prior, "channel": "cytokinesis"}
                )
            else:
                seen_cyt[record.cytokinesis_trace_sha256] = seed
        if record.ftsz_trace_sha256:
            prior = seen_ftsz.get(record.ftsz_trace_sha256)
            if prior is not None:
                duplicate_trace_hashes.append(
                    {"seed": seed, "duplicate_of_seed": prior, "channel": "ftsz"}
                )
            else:
                seen_ftsz[record.ftsz_trace_sha256] = seed

    selected_seeds = completed_seeds[:required]
    # Opus re-review (2026-09-09): selection can never be satisfied while
    # ANY cross-seed integrity finding is outstanding, even if the raw
    # completed count already reached required_completed_windows -- a
    # cohort with mixed DNADamage source identity or aliased/duplicated
    # trace content is not a valid N=50 ensemble regardless of count.
    selection_satisfied = (
        len(selected_seeds) >= required
        and not source_hash_mismatches
        and not duplicate_trace_hashes
    )
    attempted_count = len(attempted_seeds)
    completed_count = len(completed_seeds)
    completion_fraction = (completed_count / attempted_count) if attempted_count else 0.0

    return CohortAudit(
        candidate_seed_start=start,
        required_completed_windows=required,
        selection_horizon_max_search_ticks=horizon,
        contiguous_prefix_end=contiguous_prefix_end,
        next_seed_to_attempt=next_seed_to_attempt,
        attempted_seeds=attempted_seeds,
        completed_seeds=completed_seeds,
        censored_seeds=censored_seeds,
        invalid_censor_seeds=invalid_censor_seeds,
        gap_seeds=gap_seeds,
        premature_seeds=premature_seeds,
        duplicate_trace_hashes=duplicate_trace_hashes,
        source_hash_mismatches=source_hash_mismatches,
        selected_seeds=selected_seeds,
        selection_satisfied=selection_satisfied,
        attempted_count=attempted_count,
        completed_count=completed_count,
        completion_fraction=completion_fraction,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-root",
        action="append",
        type=Path,
        default=None,
        help="Optional additional karr_native root(s) to audit. Defaults to the authoritative "
        "dual_division_cohort_current root followed by autodiscovery (this worktree, the main "
        "checkout, and sibling worktrees) -- see default_search_roots().",
    )
    args = parser.parse_args(argv)
    roots = [p.resolve() for p in args.search_root] if args.search_root else default_search_roots()
    audit = audit_cohort(roots)
    print(json.dumps(audit.to_json(), indent=2, sort_keys=True))
    print(
        f"\nnext_seed_to_attempt={audit.next_seed_to_attempt} "
        f"completed={audit.completed_count} required={audit.required_completed_windows} "
        f"selection_satisfied={audit.selection_satisfied} "
        f"gap_seeds={audit.gap_seeds} premature_seeds={audit.premature_seeds}"
    )
    return 0 if audit.selection_satisfied else 2


if __name__ == "__main__":
    raise SystemExit(main())
