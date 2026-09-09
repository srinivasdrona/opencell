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
    _read_metadata_int,
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
            try:
                canary = validate_dual_division_canary(seed, karr_native_root=karr_native_root)
            except (OSError, ValueError, KeyError) as exc:
                raise CohortContractError(
                    f"seed {seed}: COMPLETED attempt record at {record_path} but combined "
                    f"validation could not even be attempted -- the trace file(s) are malformed/"
                    f"unreadable ({type(exc).__name__}: {exc})"
                ) from exc
            if canary.status != "PASS":
                raise CohortContractError(
                    f"seed {seed}: COMPLETED attempt record at {record_path} but the paired trace "
                    f"files fail combined validation: {canary.reasons}"
                )
            # Record identity cross-check (second Opus re-review,
            # 2026-09-09): a sidecar's self-claimed identity fields must
            # NEVER be trusted at face value, even when the paired trace
            # files independently validate PASS -- a copied/tampered
            # sidecar (or one written for a different seed/trace pair
            # entirely) could otherwise smuggle a false onset/anchor/hash
            # claim past the mutual-exclusivity and PASS checks above,
            # since those only confirm the TRACE FILES are valid, not
            # that the SIDECAR's own numbers describe them. Every
            # identity field the sidecar claims is cross-checked against
            # the MEASURED value from the real trace files; any
            # disagreement raises rather than silently trusting either
            # side. Cross-root agreement checks (discover_ledger) then
            # only ever compare these MEASURED values, never unverified
            # self-claims.
            measured_max_search_ticks = _read_metadata_int(cyt_path, "max_search_ticks")
            measured_identity = {
                "max_search_ticks": measured_max_search_ticks,
                "mnrnd_provider_sha256": canary.cytokinesis_provider_sha256,
                "dnadamage_source_resolved_sha256": canary.cytokinesis_dnadamage_source_sha256,
                "onset_tick": canary.cytokinesis_onset_tick,
                "completion_tick": canary.cytokinesis_window_anchor,
                "cytokinesis_trace_sha256": canary.cytokinesis_sha256,
                "ftsz_trace_sha256": canary.ftsz_sha256,
            }
            mismatches = [
                (field_name, raw.get(field_name), measured_value)
                for field_name, measured_value in measured_identity.items()
                if raw.get(field_name) is not None and raw.get(field_name) != measured_value
            ]
            if mismatches:
                raise CohortContractError(
                    f"seed {seed}: attempt record at {record_path} claims identity field(s) that do "
                    f"NOT match the MEASURED trace validation: "
                    + "; ".join(
                        f"{name}: sidecar claims {claimed!r}, measured {measured!r}"
                        for name, claimed, measured in mismatches
                    )
                    + " -- a copied/tampered/mismatched sidecar is never trusted at face value; "
                    "investigate by hand."
                )
            return AttemptRecord(
                seed=seed,
                status=status,
                max_search_ticks=measured_identity["max_search_ticks"],
                source_root=karr_native_root,
                mnrnd_provider_sha256=measured_identity["mnrnd_provider_sha256"],
                dnadamage_source_resolved_sha256=measured_identity["dnadamage_source_resolved_sha256"],
                onset_tick=measured_identity["onset_tick"],
                completion_tick=measured_identity["completion_tick"],
                cytokinesis_trace_sha256=measured_identity["cytokinesis_trace_sha256"],
                ftsz_trace_sha256=measured_identity["ftsz_trace_sha256"],
                backfilled=False,
                reason=str(raw.get("reason", "")),
            )
        # RIGHT_CENSORED: no trace files exist (mutual exclusivity already
        # enforced above), so there is nothing on disk to measure the
        # sidecar's identity claims against -- the sidecar itself IS the
        # sole evidence, and its identity fields are used as recorded
        # (still subject to the horizon/current-identity-binding checks
        # audit_cohort applies afterward).
        recorded_seed = raw.get("seed")
        if recorded_seed is not None and int(recorded_seed) != seed:
            raise CohortContractError(
                f"seed {seed}: RIGHT_CENSORED attempt record claims seed={recorded_seed!r}; "
                "refusing a sidecar copied from a different seed directory"
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
    try:
        canary = validate_dual_division_canary(seed, karr_native_root=karr_native_root)
    except (OSError, ValueError, KeyError) as exc:
        raise CohortContractError(
            f"seed {seed}: trace files exist at {out_dir} but combined validation could not even "
            f"be attempted -- the trace file(s) are malformed/unreadable, and no attempt record "
            f"exists to explain the discrepancy ({type(exc).__name__}: {exc})"
        ) from exc
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

    Checked, in order:

    1. This checkout's own path (covers the case this code runs FROM the
       consolidation worktree itself, or a future layout where the
       dedicated root lives directly under the current checkout).
    2. A sibling worktree named ``main-integrate`` (the REAL operational
       location as of the 2026-09-09 second Opus re-review: every
       worktree, including this one, lives as a sibling directory under
       ``<repo_root>/../`` -- e.g. ``E:\\opencell-worktrees\\<name>`` --
       so ``repo_root.parent / "main-integrate" / ...`` resolves
       correctly regardless of drive letter or which worktree this code
       happens to run from. This candidate is what makes discovery
       "robust" rather than requiring the caller to hardcode an absolute
       path -- the previous round's candidates (this checkout, and the
       MAIN CHECKOUT's own data dir) never actually matched where the
       real consolidated data lives, silently falling through to
       ``autodiscover_karr_native_roots``'s full sibling-worktree scan on
       every default invocation.
    3/4. Main-checkout Windows/WSL path fallbacks (legacy -- kept in case
       a future consolidation moves the dedicated root there).

    Returns the first candidate that exists, or the worktree-relative
    candidate (the canonical target a future consolidation would create)
    if none do yet. Preferred FIRST by :func:`default_search_roots`,
    never treated as the ONLY valid root -- see :func:`discover_ledger`'s
    multi-root, never-first-wins contradiction check."""
    worktrees_root = repo_root.parent
    candidates = (
        repo_root / "data" / "m1_sources" / "karr_native" / AUTHORITATIVE_ROOT_SUBDIR,
        worktrees_root / "main-integrate" / "data" / "m1_sources" / "karr_native" / AUTHORITATIVE_ROOT_SUBDIR,
        MAIN_CHECKOUT_KARR_NATIVE_ROOT_WINDOWS / AUTHORITATIVE_ROOT_SUBDIR,
        MAIN_CHECKOUT_KARR_NATIVE_ROOT_WSL / AUTHORITATIVE_ROOT_SUBDIR,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def broad_search_roots(*, repo_root: Path = REPO_ROOT) -> list[Path]:
    """Opt-in broader scan: the authoritative root (if found) followed by
    every root ``prepare_cytokinesis_cohort.autodiscover_karr_native_roots``
    finds (this worktree's own scattered karr_native root, the main
    checkout, and every sibling worktree). NEVER used by
    :func:`default_search_roots` or the CLI's no-arg default (Opus second
    re-review: "never scan 93 sibling worktrees" by default) -- a caller
    that explicitly wants this broader scan (e.g. a one-off manual
    consolidation audit) calls this function by name instead."""
    roots: list[Path] = list(default_search_roots(repo_root=repo_root))
    for root in autodiscover_karr_native_roots(repo_root=repo_root):
        if root not in roots:
            roots.append(root)
    return roots


def default_search_roots(*, repo_root: Path = REPO_ROOT) -> list[Path]:
    """The default search-root list: the authoritative dedicated root
    ONLY, if it can be found (see :func:`authoritative_karr_native_root`).

    Division-censor-contract, second Opus re-review (2026-09-09): this
    deliberately does NOT fall back to
    ``prepare_cytokinesis_cohort.autodiscover_karr_native_roots``'s full
    sibling-worktree scan by default -- doing so previously meant every
    default invocation (including the CLI's no-arg default) silently
    inspected every one of ~93 sibling worktrees on this machine, many
    holding documented-superseded/legacy trace data unrelated to this
    cohort, and could take unreasonably long or (before the
    ``rejected_root_traces`` fix) crash outright on an invalid/stale
    trace pair with no explanatory attempt record.

    Returns an EMPTY list if the authoritative root cannot be found
    anywhere -- callers (the CLI's ``main()``) must then fail closed with
    an actionable message asking for an explicit ``--search-root``,
    never silently broaden the scan on the caller's behalf. A caller that
    genuinely wants to search sibling worktrees too may pass them
    explicitly via repeated ``--search-root`` arguments (or call
    ``prepare_cytokinesis_cohort.autodiscover_karr_native_roots`` directly
    and combine the lists itself)."""
    authoritative = authoritative_karr_native_root(repo_root=repo_root)
    return [authoritative] if authoritative.exists() else []


# Fields that define an AttemptRecord's real identity -- two records for
# the SAME seed found under different roots must agree on every one of
# these, or discover_ledger raises CohortContractError rather than
# silently preferring one root over another (Opus re-review, 2026-09-09:
# "never first-wins").
_IDENTITY_FIELDS = (
    "status",
    "max_search_ticks",
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
    search_roots: list[Path],
    *,
    max_seed_scan: int = 10_000,
    authoritative_root: Path | None = None,
) -> tuple[dict[int, AttemptRecord], list[dict[str, Any]]]:
    """Build ``{seed: AttemptRecord}`` across every search root, plus a
    list of non-fatal ``rejected_root_traces`` entries.

    Multi-root integrity (Opus re-review, 2026-09-09): EVERY root is
    inspected for EVERY seed -- never "first root wins". If more than one
    root has a VALID record for the same seed, they must agree on every
    identity field (:data:`_IDENTITY_FIELDS`); any disagreement raises
    :class:`CohortContractError` immediately (a hard mechanical
    contradiction between two worktrees' claims about the same seed is
    never silently resolved by picking one). Agreeing duplicates are
    deduplicated (the authoritative root's copy is kept when present,
    else the first search order match) -- this is not "first-wins" in the
    unsafe sense, because agreement was verified first.

    Second Opus re-review (2026-09-09): a NON-authoritative root's
    ``resolve_seed_attempt`` failure (an invalid/superseded trace pair
    with no attempt record to explain it, a mutual-exclusivity
    violation, or any other :class:`CohortContractError`) is caught and
    recorded in the returned ``rejected_root_traces`` list rather than
    propagated -- sibling worktrees legitimately hold documented-
    superseded/legacy data unrelated to this cohort (e.g. pre-overlay
    4000-tick Cytokinesis traces), and a single such trace must never
    crash a default, no-arg audit invocation. A failure from the
    AUTHORITATIVE root itself (``authoritative_root``, when given)
    remains fatal and propagates unchanged -- that root is curated
    specifically for this cohort, so a broken trace there indicates a
    real problem worth a hard stop.

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
    rejected_root_traces: list[dict[str, Any]] = []
    for seed in sorted(seed_numbers):
        records_by_root: list[tuple[Path, AttemptRecord]] = []
        for root in search_roots:
            is_authoritative = authoritative_root is not None and root == authoritative_root
            try:
                record = resolve_seed_attempt(seed, karr_native_root=root)
            except Exception as exc:  # noqa: BLE001 - deliberately broad: a
                # non-authoritative root may hold ANY kind of documented-
                # superseded/legacy/corrupt trace data (a genuine
                # CohortContractError, or a raw OSError/ValueError from the
                # underlying HDF5/hashing machinery on a malformed file --
                # e.g. validate_dual_division_canary's own metadata readers
                # do not universally guard against a non-HDF5 file). Every
                # one of these must be caught and reported, never allowed
                # to crash a default, no-arg audit invocation over data
                # this cohort does not even own (second Opus re-review:
                # "never scan 93 sibling worktrees and traceback").
                if is_authoritative:
                    raise
                rejected_root_traces.append(
                    {"seed": seed, "root": str(root), "reason": f"{type(exc).__name__}: {exc}"}
                )
                continue
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
    return ledger, rejected_root_traces


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
    # Non-fatal rejections of an invalid/superseded trace pair found in a
    # NON-authoritative search root (second Opus re-review, 2026-09-09) --
    # never raised, always reported, and never counted toward anything.
    rejected_root_traces: list[dict[str, Any]] = field(default_factory=list)
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
            "rejected_root_traces": self.rejected_root_traces,
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
    authoritative_root: Path | None = None,
) -> CohortAudit:
    """The single entry point this module exposes. Builds (or accepts a
    pre-built, e.g. test-fixture) ledger, then mechanically derives the
    contiguous-attempt prefix, the valid censored/completed partitions,
    duplicate/source-mismatch findings, and the selected cohort -- never
    reports a satisfied selection for fewer than
    ``required_completed_windows`` genuinely contiguous completions.

    ``authoritative_root`` (second Opus re-review, 2026-09-09): when
    ``ledger`` is not given (the normal, real-discovery path),
    ``discover_ledger`` treats this root's own resolution failures as
    fatal (never silently downgraded to ``rejected_root_traces``) --
    defaults to :func:`authoritative_karr_native_root` when omitted, so
    ``audit_cohort()``'s own no-arg default matches the CLI's."""
    start = candidate_seed_start()
    required = required_completed_windows()
    horizon = selection_horizon_max_search_ticks()

    rejected_root_traces: list[dict[str, Any]] = []
    if ledger is None:
        roots = search_roots if search_roots is not None else default_search_roots()
        if authoritative_root is None:
            authoritative_root = authoritative_karr_native_root()
        ledger, rejected_root_traces = discover_ledger(roots, authoritative_root=authoritative_root)

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
        rejected_root_traces=rejected_root_traces,
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
        help="Optional karr_native root(s) to audit (repeatable). Defaults to the authoritative "
        "dual_division_cohort_current root ONLY (see authoritative_karr_native_root()/"
        "default_search_roots()) -- NEVER a broad sibling-worktree scan. If the authoritative "
        "root cannot be found anywhere, this flag becomes required (fail-closed, see below).",
    )
    args = parser.parse_args(argv)
    authoritative_root = authoritative_karr_native_root()
    if args.search_root:
        roots = [p.resolve() for p in args.search_root]
    else:
        roots = default_search_roots()
        if not roots:
            print(
                "[division_cohort_selector] ERROR: could not resolve the authoritative "
                f"{AUTHORITATIVE_ROOT_SUBDIR} root anywhere (checked: this worktree, the sibling "
                "main-integrate worktree, and the main checkout's Windows/WSL paths). Refusing to "
                "fall back to scanning every sibling worktree. Pass --search-root explicitly to "
                "point at the real data location, e.g.:\n"
                "  python scripts/l2_event/division_cohort_selector.py --search-root "
                "/path/to/data/m1_sources/karr_native/dual_division_cohort_current",
                file=sys.stderr,
            )
            return 2
    audit = audit_cohort(roots, authoritative_root=authoritative_root)
    print(json.dumps(audit.to_json(), indent=2, sort_keys=True))
    print(
        f"\nnext_seed_to_attempt={audit.next_seed_to_attempt} "
        f"completed={audit.completed_count} required={audit.required_completed_windows} "
        f"selection_satisfied={audit.selection_satisfied} "
        f"gap_seeds={audit.gap_seeds} premature_seeds={audit.premature_seeds} "
        f"rejected_root_traces={len(audit.rejected_root_traces)}"
    )
    return 0 if audit.selection_satisfied else 2


if __name__ == "__main__":
    raise SystemExit(main())
