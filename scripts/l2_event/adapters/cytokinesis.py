"""Cytokinesis `single_firing` normalized event adapter (D7) -- round 3.

Round-1 correction (operator, 2026-08-02 ratified timing decision):
Cytokinesis is gated by chromosome segregation; its FtsZ-ring state is
explicit (``numEdgesOneStraight``/``numEdgesTwoStraight``/
``numEdgesTwoBent``/``numResidualBent``) and its geometry is explicit
(``pinchedDiameter``). Karr (``Cytokinesis.m``) decreases
``pinchedDiameter`` only after a completed ring has fully bent
(``Cytokinesis.m:220-221,238-239``: the diameter write is nested inside
the ``numEdgesTwoBent + numEdgesTwoStraight == numEdges`` full-ring guard
AND the ``numEdgesTwoStraight == 0`` fully-bent guard), and
``calcNextPinchedDiameter`` (``Cytokinesis.m:264-282``) sets it to exactly
zero once no further pinching is needed. ``CellGeometry.m:193-194``
defines ``pinched`` as a DERIVED getter (``pinchedDiameter == 0``), never
an independently-set flag -- OC's own ``geometry["pinched"]`` mirrors this
exactly (``karr_cytokinesis.py``'s ``_geometry_state``).

The process-local interval this adapter reports is gated from
**contraction onset** (the first strict ``pinchedDiameter`` decrease) to
**geometry-pinch completion** (``pinchedDiameter`` positive -> zero), both
derived PURELY from the ``pinchedDiameter`` sequence itself -- never from
``WindowGrid.tick_offset`` (window placement/burn-in metadata, not a
contraction-onset anchor).

Round-1 also used the Karr-side channel name ``division_complete`` --
no such field exists anywhere in ``Cytokinesis.m``/``CellGeometry.m``/
``FtsZRing.m`` (an extractor-invented label). This module now projects
the one field that *does* exist on both sides: ``pinchedDiameter``
(``CellGeometry.m:100``: "m; diameter where cell is pinched the most";
``karr_cytokinesis.py`` ``ports_schema()['geometry']['pinchedDiameter']``).

Round-3 correction (Opus5 structural-integration review, this round):
``window_anchor`` (``scripts/l2_event/window_loader.py``'s M4 stride
contract, ``_STRIDE_CONTRACT_END_KEYS = ("tick_end", "window_anchor")``)
is a **window-boundary / capture-completion** metadata field -- a
division-anchored window records it as an ALTERNATIVE to ``tick_end``,
i.e. it marks where the window's recording stops, not where contraction
began. Any future cross-check against this adapter's data-derived
timing must therefore compare it to this adapter's derived
**completion** tick (in absolute coordinates, after converting via
``window.tick_start``) -- NOT to onset. A separate, not-yet-existing
``onset_tick`` metadata field (which the extractor branch is adding
independently, not this one) is the only field that could ever be
cross-checked against this adapter's derived **onset** tick. This
adapter branch adds no loader/metadata fields of its own; see
:data:`REQUIRED_OC_STATE_ALTERNATIVE_PATHS` and the module-level
`for_process` factory below for the corresponding code changes this
round.

Scope of this module (l2-event-cytokinesis case directive, round 3):
adapter code plus its own unit/integration tests only. Same non-goals as
prior rounds (see git history for round-1/round-2 module docstrings): no
MATLAB extraction, no ``opencell/vivarium/karr_cytokinesis.py`` edits, no
``scripts/l2_event/window_loader.py``/``runner.py``/``metrics.py``/
``base.py``/``docs/phase_f/l2_event/event_registry.yaml`` edits.

Verified OC read/write surface (re-audited against
``opencell/vivarium/karr_cytokinesis.py`` HEAD for this round -- see
:data:`REQUIRED_OC_STATE_PATHS`, :data:`REQUIRED_OC_STATE_ALTERNATIVE_PATHS`,
and :func:`require_cytokinesis_dynamic_state_inputs` docstrings for the
line-by-line accounting): ``next_update()`` reads ``cell.division_progress``,
chromosome readiness via EITHER ``chromosome.segregated`` OR
``chromosome.segregation_progress`` (``karr_cytokinesis.py``'s
``_segregated()``, lines ~479-483: prefers ``segregated`` if present,
else falls back to ``segregation_progress`` + tolerance -- this adapter's
required-input check now mirrors that exact either/or precedence rather
than unconditionally requiring ``segregation_progress`` alone),
``geometry.width``, ``geometry.pinchedDiameter``, ``geometry.pinched``,
five ``ftsZRing`` edge-count/geometry fields, the full dynamic
``enzymes``/``boundEnzymes`` count dicts (keyed by the fixture's
runtime-derived FtsZ enzyme WIDs -- NOT hardcodable dotted paths), and
``substrates_allocated.karr_cytokinesis.<water_wid>`` (``water_wid`` is
itself fixture-derived, never hardcoded). ``cell.ftsz_ring_complete`` is
declared in ``ports_schema()`` but never read or assigned in
``next_update()`` -- vestigial, dropped from this adapter's required-input
manifest. ``GTP`` is declared for legacy-compatibility plumbing but
``next_update()`` hardcodes its request to ``0.0`` and never reads an
allocated ``GTP`` value back -- WATER is the process's actual
hydrolysis-limiting allocation channel; GTP is not, and is never, required
by this adapter.

Round-3 also makes the fixture/runtime-derived (enzyme-WID, WATER-WID)
validation an ACTUAL per-tick enforcement inside :meth:`oc_observation`,
not merely a docstring-promised standalone function nobody calls
automatically. A :class:`CytokinesisEventAdapter` instance must be bound
to a real process's dynamic vocabulary via :meth:`CytokinesisEventAdapter.for_process`
before its `oc_observation` will accept any state -- the DEFAULT
(unbound) construction deliberately refuses to guess, hardcode, or
silently skip this validation (no hidden/default biology is ever
instantiated inside `oc_observation` itself; the vocabulary is captured
ONCE, at construction, from a caller-supplied process instance).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from scripts.l2_event.schema import EventObservation
from scripts.l2_event.window_loader import WindowGrid

#: The one Karr-side channel this adapter projects on both sides: the
#: real ``CellGeometry.m``/``karr_cytokinesis.py`` ``pinchedDiameter``
#: field. Not an extractor-invented label -- see module docstring.
KARR_EVENT_CHANNEL = "pinchedDiameter"

#: Dotted-path manifest of the STATIC (fixture-independent) state inputs
#: `next_update()` reads every tick, re-audited against the current
#: `opencell/vivarium/karr_cytokinesis.py` HEAD (see module docstring).
#: Deliberately excludes `cell.ftsz_ring_complete` (declared, never read
#: -- vestigial) and any GTP path (declared for legacy plumbing, never
#: read back). Deliberately excludes `cell.division_complete` -- this
#: adapter no longer detects completion from that field (see
#: `oc_observation`); it is written by `next_update`, not read by it.
#: Deliberately excludes `chromosome.segregation_progress` as an
#: UNCONDITIONAL requirement -- see
#: :data:`REQUIRED_OC_STATE_ALTERNATIVE_PATHS` for the either/or
#: chromosome-readiness requirement that replaces it (round 3).
REQUIRED_OC_STATE_PATHS: tuple[tuple[str, ...], ...] = (
    ("cell", "division_progress"),
    ("geometry", "width"),
    ("geometry", "pinchedDiameter"),
    ("geometry", "pinched"),
    ("ftsZRing", "numEdgesOneStraight"),
    ("ftsZRing", "numEdgesTwoStraight"),
    ("ftsZRing", "numEdgesTwoBent"),
    ("ftsZRing", "numResidualBent"),
    ("ftsZRing", "numFtsZSubunitsPerFilament"),
    ("ftsZRing", "filamentLengthInNm"),
)

#: Groups of dotted paths where AT LEAST ONE path per group must be
#: present. Round-3 addition: mirrors `karr_cytokinesis.py`'s
#: `_segregated()` precedence exactly (prefers `chromosome.segregated` if
#: present, else falls back to `chromosome.segregation_progress`) rather
#: than unconditionally requiring `segregation_progress` alone -- a state
#: dict that supplies only `segregated` is a valid, complete conditioning
#: input, not a missing one.
REQUIRED_OC_STATE_ALTERNATIVE_PATHS: tuple[tuple[tuple[str, ...], ...], ...] = (
    (("chromosome", "segregated"), ("chromosome", "segregation_progress")),
)

#: Groups that must be present as dicts, but whose exact key sets are
#: fixture/runtime-derived (enzyme WIDs, the WATER substrate WID) and so
#: CANNOT be hardcoded as dotted-path leaves here -- their membership is
#: validated by :func:`require_cytokinesis_dynamic_state_inputs` /
#: :meth:`CytokinesisEventAdapter._require_bound_dynamic_inputs` against
#: the actual `KarrCytokinesisProcess` vocabulary instead.
REQUIRED_OC_STATE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("enzymes",),
    ("boundEnzymes",),
    ("substrates_allocated", "karr_cytokinesis"),
)


class CytokinesisProcessLike(Protocol):
    """Structural (duck-typed) contract for the real
    `KarrCytokinesisProcess` vocabulary this adapter must bind to --
    used in place of a bare `Any` parameter (round-3 ruff ANN401
    closeout). A real `KarrCytokinesisProcess` instance satisfies this
    directly; no adapter code ever constructs one itself."""

    name: str
    water_wid: str
    fixture_enzyme_wids: Sequence[str]


class MissingCytokinesisStateInputError(Exception):
    """Raised by :func:`require_cytokinesis_state_inputs` /
    :func:`require_cytokinesis_dynamic_state_inputs` /
    :meth:`CytokinesisEventAdapter._require_bound_dynamic_inputs` when the
    conditioned `state_before` dict (or an `update` dict this adapter
    must project) is missing a required Cytokinesis input, or when the
    adapter instance itself has not been bound to a process's dynamic
    vocabulary. Distinct from a silent `dict.get(..., default)` -- a
    harness that cannot supply one of these inputs has an incomplete
    Cytokinesis conditioning pipeline and must fail loudly, not compute a
    fire/no-fire verdict from a quietly defaulted value."""


class CytokinesisTimingError(Exception):
    """Base class for all Cytokinesis single-firing onset/completion
    timing-derivation failures raised by this module's sequence-scanning
    helpers (:func:`find_onset_tick`, :func:`find_completion_tick`,
    :func:`single_fire_offset_from_sequences`). These are distinct from
    :class:`MissingCytokinesisStateInputError` (conditioning-input
    coverage): they are raised only when an offset is computed from a
    *sequence* of ticks. `oc_observation`'s own per-tick, stateless fire
    projection never raises any of these -- only the sequence-level
    offset helpers do."""


class InvalidPinchedDiameterSequenceError(CytokinesisTimingError):
    """A `pinchedDiameter` before/after sequence (or a single reading) is
    non-finite, negative, non-scalar, or has mismatched before/after
    lengths -- cannot be scanned for onset/completion at all."""


class NoCompletionTickDetectedError(CytokinesisTimingError):
    """No tick in the sequence satisfies the completion predicate
    (`before > 0` then `after == 0`) -- an offset was requested but
    completion never occurred in this sequence. Includes the "no
    decrease ever occurs" case: a sequence with no strict decrease
    anywhere also, definitionally, never completes."""


class DuplicateCompletionTickDetectedError(CytokinesisTimingError):
    """More than one tick in the sequence satisfies the completion
    predicate -- violates single-firing semantics (`magnitude_gateable:
    false`; at most one completion event is possible per seed)."""


class CompletionWithoutPrecedingOnsetError(CytokinesisTimingError):
    """A completion tick was found, but no strict `pinchedDiameter`
    decrease exists anywhere in the sequence at or before it. Under a
    correctly-defined completion predicate this cannot occur naturally
    (completion itself is always a decrease at that tick -- see
    `find_completion_tick`), so this is a defensive Rule-1-style guard
    against a FUTURE regression that decouples onset detection from
    completion detection (e.g. an onset search that adds a tolerance/
    epsilon excluding the exact completion-tick drop). Exercised directly
    in tests via a monkeypatched onset search, not via naturally
    constructible data -- see
    `test_single_fire_offset_defensive_guard_completion_without_onset`."""


class OnsetAfterCompletionTickError(CytokinesisTimingError):
    """The detected onset tick occurs strictly after the detected
    completion tick. Structurally unreachable via `find_onset_tick`/
    `find_completion_tick` on validated data (the completion tick is
    itself always a valid onset candidate, so onset can never be found
    LATER than completion) -- retained as a defensive guard against a
    future regression, exercised via a monkeypatched onset search (see
    `test_single_fire_offset_defensive_guard_onset_after_completion`)."""


def _dotted_path_present(state: Mapping[str, object], path: tuple[str, ...]) -> bool:
    """`True` iff every key in `path` resolves through nested dicts of
    `state`. Pure existence check (no type/value validation of the leaf
    -- that is `_finite_nonnegative_scalar`'s job)."""
    node: object = state
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return False
        node = node[key]
    return True


def require_cytokinesis_state_inputs(state_before: Mapping[str, object]) -> None:
    """Raise :class:`MissingCytokinesisStateInputError` naming the first
    missing path in :data:`REQUIRED_OC_STATE_PATHS` +
    :data:`REQUIRED_OC_STATE_GROUPS`, or the first fully-absent
    alternative-path group in :data:`REQUIRED_OC_STATE_ALTERNATIVE_PATHS`
    (at least one path per group must be present). No-op if every
    static/group/alternative input is present. Does NOT validate the
    fixture-derived enzyme-WID / WATER-WID membership inside those groups
    -- see :func:`require_cytokinesis_dynamic_state_inputs` for that (it
    needs the process vocabulary, which this function deliberately does
    not require, so it stays a pure function of `state_before` alone)."""
    for path in REQUIRED_OC_STATE_PATHS + REQUIRED_OC_STATE_GROUPS:
        if not _dotted_path_present(state_before, path):
            dotted = ".".join(path)
            raise MissingCytokinesisStateInputError(
                f"state_before is missing required Cytokinesis input '{dotted}'; refusing to silently "
                "default it (FIX_TEMPLATE_L2_REPLAY Rule 1)."
            )
    for alternatives in REQUIRED_OC_STATE_ALTERNATIVE_PATHS:
        if not any(_dotted_path_present(state_before, path) for path in alternatives):
            dotted_alternatives = " or ".join(".".join(path) for path in alternatives)
            raise MissingCytokinesisStateInputError(
                f"state_before is missing all of the alternative Cytokinesis inputs '{dotted_alternatives}' "
                "-- at least one is required (mirrors karr_cytokinesis.py's _segregated() precedence: "
                "'segregated' if present, else fall back to 'segregation_progress'); refusing to silently "
                "default it (FIX_TEMPLATE_L2_REPLAY Rule 1)."
            )


def _require_dynamic_vocabulary_inputs(
    state_before: Mapping[str, object],
    *,
    substrates_allocated_port: str,
    water_wid: str,
    fixture_enzyme_wids: Sequence[str],
) -> None:
    """Core dynamic-vocabulary validation, parameterized by explicit
    primitives rather than a live process object -- shared by
    :func:`require_cytokinesis_dynamic_state_inputs` (process-based
    wrapper, for direct tests/harnesses holding a live process) and
    :meth:`CytokinesisEventAdapter._require_bound_dynamic_inputs`
    (adapter-bound wrapper, invoked automatically every `oc_observation`
    call -- round-3 correction: this was previously only reachable via a
    manually-invoked, never-actually-called-by-`oc_observation`
    function)."""
    allocated_group = state_before.get("substrates_allocated", {})
    allocated_group = allocated_group.get(substrates_allocated_port, {}) if isinstance(allocated_group, Mapping) else {}
    if not isinstance(allocated_group, Mapping) or water_wid not in allocated_group:
        raise MissingCytokinesisStateInputError(
            f"state_before is missing the allocated WATER input "
            f"'substrates_allocated.{substrates_allocated_port}.{water_wid}' -- this is the process's "
            "actual hydrolysis-limiting allocation channel (next_update() reads it back via "
            "_allocated_count); a GTP allocation alone does not satisfy this (GTP's allocated value "
            "is never read back -- see module docstring)."
        )

    enzymes_group = state_before.get("enzymes", {})
    bound_group = state_before.get("boundEnzymes", {})
    for wid in fixture_enzyme_wids:
        if not isinstance(enzymes_group, Mapping) or wid not in enzymes_group:
            raise MissingCytokinesisStateInputError(
                f"state_before is missing required dynamic Cytokinesis input 'enzymes.{wid}' "
                "(a fixture-derived FtsZ enzyme WID next_update() reads via _counts_from_state)."
            )
        if not isinstance(bound_group, Mapping) or wid not in bound_group:
            raise MissingCytokinesisStateInputError(
                f"state_before is missing required dynamic Cytokinesis input 'boundEnzymes.{wid}' "
                "(a fixture-derived FtsZ enzyme WID next_update() reads via _counts_from_state)."
            )


def require_cytokinesis_dynamic_state_inputs(
    state_before: Mapping[str, object], process: CytokinesisProcessLike
) -> None:
    """Validate the fixture/runtime-derived portions of the conditioning
    state that :func:`require_cytokinesis_state_inputs` cannot check
    without hardcoding WIDs that vary by fixture (correction: "If exact
    enzyme WIDs are runtime-derived, validate the group plus the process
    fixture WID set ... rather than hardcoding an incomplete dotted-path
    tuple").

    ``process`` must expose ``.name`` (the port key, ``"karr_cytokinesis"``),
    ``.water_wid`` (the fixture-derived WATER substrate WID
    `next_update()` actually reads back via `_allocated_count`), and
    ``.fixture_enzyme_wids`` (the full list of FtsZ enzyme WIDs
    `next_update()` reads via `_counts_from_state` for both `enzymes` and
    `boundEnzymes`). A real `KarrCytokinesisProcess` instance satisfies
    this duck-typed contract directly. This is a process-based wrapper
    for direct tests/harnesses holding a live process instance --
    :meth:`CytokinesisEventAdapter._require_bound_dynamic_inputs` is the
    adapter-bound equivalent that `oc_observation` invokes automatically
    every tick (round-3 correction; see class docstring).

    Raises :class:`MissingCytokinesisStateInputError` naming the first
    missing WID. Requires `require_cytokinesis_state_inputs` to have
    already passed (does not re-check the static/group/alternative
    paths).
    """
    _require_dynamic_vocabulary_inputs(
        state_before,
        substrates_allocated_port=process.name,
        water_wid=process.water_wid,
        fixture_enzyme_wids=process.fixture_enzyme_wids,
    )


def _finite_nonnegative_scalar(value: object, *, context: str) -> float:
    """Coerce `value` to a python float, raising
    :class:`InvalidPinchedDiameterSequenceError` if it is not a scalar
    (or a size-1 array-like), not finite, or negative. `pinchedDiameter`
    is a physical diameter (m); Karr/OC never produce a negative value,
    and a NaN/Inf reading cannot be scanned for a strict decrease."""
    try:
        arr = np.asarray(value)
    except Exception as exc:  # pragma: no cover - defensive, numpy is a hard dependency elsewhere
        raise InvalidPinchedDiameterSequenceError(
            f"{context}: could not interpret {value!r} as a scalar: {exc}"
        ) from exc
    if arr.ndim != 0 and arr.size != 1:
        raise InvalidPinchedDiameterSequenceError(
            f"{context}: not a scalar pinchedDiameter reading (shape {arr.shape})."
        )
    result = float(arr.reshape(()))
    if not math.isfinite(result):
        raise InvalidPinchedDiameterSequenceError(f"{context}: non-finite pinchedDiameter reading ({result!r}).")
    if result < 0.0:
        raise InvalidPinchedDiameterSequenceError(f"{context}: negative pinchedDiameter reading ({result!r}).")
    return result


def _validate_diameter_sequence(values: Sequence[object], *, label: str) -> tuple[float, ...]:
    if len(values) == 0:
        raise InvalidPinchedDiameterSequenceError(f"{label} sequence is empty; cannot scan for onset/completion.")
    return tuple(_finite_nonnegative_scalar(v, context=f"{label}[{i}]") for i, v in enumerate(values))


def _validate_matched_sequences(
    before: Sequence[object], after: Sequence[object]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    before_v = _validate_diameter_sequence(before, label="pinchedDiameter before")
    after_v = _validate_diameter_sequence(after, label="pinchedDiameter after")
    if len(before_v) != len(after_v):
        raise InvalidPinchedDiameterSequenceError(
            f"before/after pinchedDiameter sequences have mismatched lengths "
            f"({len(before_v)} vs {len(after_v)})."
        )
    return before_v, after_v


def find_onset_tick(before: Sequence[object], after: Sequence[object]) -> int | None:
    """Scan a COMPLETE per-seed/per-run `pinchedDiameter` before/after
    sequence and return the local tick index of the FIRST strict
    decrease (`after[t] < before[t]`) -- Karr's own contraction-onset
    definition per the ratified 2026-08-02 timing decision. Returns
    ``None`` (NOT an error) if no such tick exists anywhere in the
    sequence: "no onset in this window" is a valid, non-firing outcome on
    its own, only an error once an offset is requested against a
    completion that DID occur (see `single_fire_offset_from_sequences`).
    """
    before_v, after_v = _validate_matched_sequences(before, after)
    for t, (b, a) in enumerate(zip(before_v, after_v, strict=True)):
        if a < b:
            return t
    return None


def find_completion_tick(before: Sequence[object], after: Sequence[object]) -> int | None:
    """Scan a COMPLETE per-seed/per-run `pinchedDiameter` before/after
    sequence for the single tick where `before > 0` and `after == 0`
    (geometry-pinch completion, mechanically derived from the diameter
    itself -- never from an extractor-invented `division_complete`-style
    label). Returns ``None`` if no such tick exists (a valid, non-firing
    outcome). Raises :class:`DuplicateCompletionTickDetectedError` if
    MORE THAN ONE tick satisfies the predicate -- `single_firing`/
    `magnitude_gateable: false` semantics permit at most one completion
    event per seed."""
    before_v, after_v = _validate_matched_sequences(before, after)
    completions = [t for t, (b, a) in enumerate(zip(before_v, after_v, strict=True)) if b > 0.0 and a == 0.0]
    if len(completions) > 1:
        raise DuplicateCompletionTickDetectedError(
            f"{len(completions)} ticks satisfy the completion predicate (before>0, after==0) at local "
            f"ticks {completions}; single_firing semantics permit at most one completion event per seed."
        )
    return completions[0] if completions else None


def single_fire_offset_from_sequences(before: Sequence[object], after: Sequence[object]) -> float:
    """The ONLY place `t_completion - t_onset` arithmetic happens for
    Cytokinesis. Deliberately takes no `tick_offset`/`window_anchor`
    argument -- per the ratified 2026-08-02 timing decision, the
    process-local interval is gated from contraction onset (first strict
    `pinchedDiameter` decrease) to geometry-pinch completion
    (`pinchedDiameter` positive -> zero), both derived purely from the
    sequence itself. Raises:

    * :class:`NoCompletionTickDetectedError` -- no completion in this
      sequence (including the "no decrease ever occurs" case).
    * :class:`DuplicateCompletionTickDetectedError` -- more than one
      completion tick (propagated from `find_completion_tick`).
    * :class:`CompletionWithoutPrecedingOnsetError` -- completion found
      but no strict decrease anywhere (structurally unreachable on real
      data; defensive guard).
    * :class:`OnsetAfterCompletionTickError` -- onset found strictly
      after completion (structurally unreachable on real data; defensive
      guard).
    """
    completion_tick = find_completion_tick(before, after)
    if completion_tick is None:
        raise NoCompletionTickDetectedError(
            "No completion tick (pinchedDiameter before>0, after==0) found in this sequence; an offset "
            "cannot be computed for a sequence that never completes."
        )
    onset_tick = find_onset_tick(before, after)
    if onset_tick is None:
        raise CompletionWithoutPrecedingOnsetError(
            f"Completion detected at local tick {completion_tick}, but no tick anywhere in the sequence "
            "shows a strict pinchedDiameter decrease; completion without a preceding contraction-onset "
            "event is not a valid single Cytokinesis cycle."
        )
    if onset_tick > completion_tick:
        raise OnsetAfterCompletionTickError(
            f"Onset tick ({onset_tick}) occurs after completion tick ({completion_tick}); refusing to "
            "report a negative offset."
        )
    return float(completion_tick - onset_tick)


def karr_pinched_diameter_sequence(window: WindowGrid) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Project the Karr-side `pinchedDiameter` channel for EVERY tick in
    the window. Reads only `window`'s own `states_before`/`states_after`
    (never OC state, never `window.tick_offset`) -- anti-laundering, and
    the metadata-independence this adapter's timing arithmetic requires."""
    before = tuple(
        _finite_nonnegative_scalar(window.before(KARR_EVENT_CHANNEL, t), context=f"window.before[{t}]")
        for t in range(window.n_ticks)
    )
    after = tuple(
        _finite_nonnegative_scalar(window.after(KARR_EVENT_CHANNEL, t), context=f"window.after[{t}]")
        for t in range(window.n_ticks)
    )
    return before, after


def karr_single_fire_offset(window: WindowGrid) -> float:
    """Karr-side `t_completion - t_onset`, derived entirely from
    `window`'s own `pinchedDiameter` channel. `window.tick_offset` is
    never read anywhere in this call chain."""
    before, after = karr_pinched_diameter_sequence(window)
    return single_fire_offset_from_sequences(before, after)


def oc_pinched_diameter_sequence(
    rows: Iterable[tuple[Mapping[str, object], Mapping[str, object]]],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """OC sequence helper (correction: "Add an OC sequence helper over
    paired pre-state/update rows so OC onset is not inferred from Karr or
    metadata"). Scans a complete, in-order sequence of
    ``(state_before, update)`` pairs -- ONE pair per tick, exactly what a
    harness driving `KarrCytokinesisProcess.next_update()` in a loop
    already has -- and projects `geometry.pinchedDiameter` before (from
    `state_before`) and after (from `update`, the value `next_update()`
    itself returned) for every row. Never reads Karr data or any window
    metadata -- OC onset/completion is derived purely from OC's own
    state."""
    before: list[float] = []
    after: list[float] = []
    for idx, (state_before, update) in enumerate(rows):
        geometry_before = state_before.get("geometry", {}) if isinstance(state_before, Mapping) else {}
        if not isinstance(geometry_before, Mapping) or "pinchedDiameter" not in geometry_before:
            raise MissingCytokinesisStateInputError(
                f"row {idx}: state_before is missing required 'geometry.pinchedDiameter'."
            )
        geometry_update = update.get("geometry", {}) if isinstance(update, Mapping) else {}
        if not isinstance(geometry_update, Mapping) or "pinchedDiameter" not in geometry_update:
            raise MissingCytokinesisStateInputError(
                f"row {idx}: update is missing required 'geometry.pinchedDiameter' -- next_update() "
                "always emits this key via a 'set' updater every tick it runs (see "
                "opencell/vivarium/karr_cytokinesis.py's next_update); a caller handing in a partial/"
                "empty update dict has an incomplete Cytokinesis projection pipeline and must fail "
                "loudly, not be silently treated as a no-fire (FIX_TEMPLATE_L2_REPLAY Rule 1)."
            )
        before.append(
            _finite_nonnegative_scalar(geometry_before["pinchedDiameter"], context=f"row {idx} state_before.geometry.pinchedDiameter")
        )
        after.append(
            _finite_nonnegative_scalar(geometry_update["pinchedDiameter"], context=f"row {idx} update.geometry.pinchedDiameter")
        )
    return tuple(before), tuple(after)


def oc_single_fire_offset(rows: Iterable[tuple[Mapping[str, object], Mapping[str, object]]]) -> float:
    """OC-side `t_completion - t_onset`, derived entirely from a
    (state_before, update) row sequence -- never from Karr data or window
    metadata."""
    before, after = oc_pinched_diameter_sequence(rows)
    return single_fire_offset_from_sequences(before, after)


@dataclass(frozen=True)
class CytokinesisEventAdapter:
    """D7 normalized event adapter for Cytokinesis (single-firing,
    magnitude non-gateable per D6). See module docstring for the verified
    OC read/write surface and the required-input enforcement rationale.

    Round-3 correction: a DEFAULT-constructed instance is intentionally
    NOT bound to any process's dynamic (enzyme-WID/WATER-WID) vocabulary
    -- `water_wid` is `None` and `fixture_enzyme_wids` is empty. Use
    :meth:`for_process` to bind an instance to a real
    `KarrCytokinesisProcess`'s vocabulary ONCE, at construction time.
    `oc_observation` refuses to run against an unbound instance (raises
    :class:`MissingCytokinesisStateInputError`) rather than silently
    skipping per-tick dynamic validation or constructing a hidden default
    process internally.
    """

    adapter_id: str = "cytokinesis.pinched_diameter_completion.v1"
    process_name: str = "Cytokinesis"
    karr_event_channel: str = KARR_EVENT_CHANNEL
    #: Vivarium port key `next_update()` reads allocated substrates
    #: under (`KarrCytokinesisProcess.name`, a FIXED class attribute --
    #: not fixture-derived, safe to default here; see module docstring).
    substrates_allocated_port: str = "karr_cytokinesis"
    #: Fixture-derived WATER substrate WID. `None` means "unbound" --
    #: `oc_observation` refuses to run until bound via `for_process`.
    water_wid: str | None = None
    #: Fixture-derived FtsZ enzyme WIDs. Empty means "unbound" -- see
    #: `water_wid`.
    fixture_enzyme_wids: tuple[str, ...] = ()

    @classmethod
    def for_process(cls, process: CytokinesisProcessLike) -> CytokinesisEventAdapter:
        """Bind a new adapter instance to `process`'s dynamic vocabulary
        ONCE, at construction time -- the only sanctioned way to obtain
        an adapter whose `oc_observation` will accept real OC state.
        Never called internally by `oc_observation` itself (round-3
        correction: no hidden/default biology is instantiated on every
        observation)."""
        return cls(
            substrates_allocated_port=process.name,
            water_wid=process.water_wid,
            fixture_enzyme_wids=tuple(process.fixture_enzyme_wids),
        )

    def karr_observation(self, window: WindowGrid, tick: int) -> EventObservation:
        """Stateless per-tick completion projection on the Karr-side
        `pinchedDiameter` channel: fired only at the tick where
        `states_before` is positive and `states_after` is zero. Reading
        both sides of the SAME tick (never comparing across ticks, never
        caching) guarantees at most one fire per seed even though the
        underlying diameter clamps to (and stays at) zero for every
        remaining tick in the window."""
        before = _finite_nonnegative_scalar(window.before(self.karr_event_channel, tick), context=f"window.before[{tick}]")
        after = _finite_nonnegative_scalar(window.after(self.karr_event_channel, tick), context=f"window.after[{tick}]")
        fired = before > 0.0 and after == 0.0
        return EventObservation(
            tick=tick,
            fired=fired,
            fire_count=1 if fired else 0,
            timing_tick=tick if fired else None,
            payload={},
        )

    def _require_bound_dynamic_inputs(self, state_before: Mapping[str, object]) -> None:
        """Round-3 addition: the ACTUAL per-tick enforcement of the
        fixture/runtime-derived (enzyme-WID/WATER-WID) vocabulary,
        invoked automatically by `oc_observation` every call -- not a
        docstring-promised function nobody calls. Raises
        :class:`MissingCytokinesisStateInputError` if this instance is
        unbound (refuses to guess/default), or if `state_before` is
        missing any required enzyme/bound-enzyme/WATER key for the bound
        vocabulary."""
        if self.water_wid is None or not self.fixture_enzyme_wids:
            raise MissingCytokinesisStateInputError(
                "This CytokinesisEventAdapter instance is not bound to a process's dynamic vocabulary "
                "(water_wid/fixture_enzyme_wids are unset); construct it via "
                "CytokinesisEventAdapter.for_process(process) before calling oc_observation -- refusing "
                "to guess, hardcode, or silently skip per-tick dynamic enzyme/WATER validation."
            )
        _require_dynamic_vocabulary_inputs(
            state_before,
            substrates_allocated_port=self.substrates_allocated_port,
            water_wid=self.water_wid,
            fixture_enzyme_wids=self.fixture_enzyme_wids,
        )

    def oc_observation(
        self,
        tick: int,
        state_before: Mapping[str, object],
        update: Mapping[str, object],
    ) -> EventObservation:
        """Stateless per-tick completion projection on OC's real
        `next_update()` output. `state_before` must be the conditioned
        pre-tick state actually handed to `next_update` (with every path
        in :data:`REQUIRED_OC_STATE_PATHS`/:data:`REQUIRED_OC_STATE_GROUPS`/
        :data:`REQUIRED_OC_STATE_ALTERNATIVE_PATHS` present -- enforced by
        :func:`require_cytokinesis_state_inputs`; the fixture-derived
        enzyme/WATER vocabulary is enforced by
        :meth:`_require_bound_dynamic_inputs`, which requires this
        instance to have been constructed via :meth:`for_process` --
        both run before anything else). `update` is the raw dict
        `next_update()` returned; this method never calls `next_update`
        itself (that is the harness's job) and never reads Karr data --
        pure per-tick projection, no mutable carryover, matches
        `karr_observation`'s `pinchedDiameter` predicate exactly (before
        > 0, after == 0), not `cell.division_complete`. A missing/
        invalid-shape/non-finite `update.geometry.pinchedDiameter` is
        NEVER treated as a quiet no-fire -- it raises
        :class:`MissingCytokinesisStateInputError` (missing) or
        :class:`InvalidPinchedDiameterSequenceError` (invalid-shape/non-
        finite), matching `oc_pinched_diameter_sequence`'s row-level
        contract."""
        require_cytokinesis_state_inputs(state_before)
        self._require_bound_dynamic_inputs(state_before)
        before_diameter = _finite_nonnegative_scalar(
            state_before["geometry"]["pinchedDiameter"], context="state_before.geometry.pinchedDiameter"
        )
        geometry_update = update.get("geometry", {}) if isinstance(update, Mapping) else {}
        if not isinstance(geometry_update, Mapping) or "pinchedDiameter" not in geometry_update:
            raise MissingCytokinesisStateInputError(
                "update is missing required 'geometry.pinchedDiameter' -- next_update() always emits "
                "this key via a 'set' updater every tick it runs (see "
                "opencell/vivarium/karr_cytokinesis.py's next_update); a caller handing in a partial/"
                "empty update dict has an incomplete Cytokinesis projection pipeline and must fail "
                "loudly, not be silently treated as a no-fire (FIX_TEMPLATE_L2_REPLAY Rule 1)."
            )
        after_diameter = _finite_nonnegative_scalar(
            geometry_update["pinchedDiameter"], context="update.geometry.pinchedDiameter"
        )
        fired = before_diameter > 0.0 and after_diameter == 0.0
        return EventObservation(
            tick=tick,
            fired=fired,
            fire_count=1 if fired else 0,
            timing_tick=tick if fired else None,
            payload={},
        )


__all__ = [
    "KARR_EVENT_CHANNEL",
    "REQUIRED_OC_STATE_PATHS",
    "REQUIRED_OC_STATE_ALTERNATIVE_PATHS",
    "REQUIRED_OC_STATE_GROUPS",
    "CytokinesisProcessLike",
    "MissingCytokinesisStateInputError",
    "CytokinesisTimingError",
    "InvalidPinchedDiameterSequenceError",
    "NoCompletionTickDetectedError",
    "DuplicateCompletionTickDetectedError",
    "CompletionWithoutPrecedingOnsetError",
    "OnsetAfterCompletionTickError",
    "require_cytokinesis_state_inputs",
    "require_cytokinesis_dynamic_state_inputs",
    "find_onset_tick",
    "find_completion_tick",
    "single_fire_offset_from_sequences",
    "karr_pinched_diameter_sequence",
    "karr_single_fire_offset",
    "oc_pinched_diameter_sequence",
    "oc_single_fire_offset",
    "CytokinesisEventAdapter",
]
