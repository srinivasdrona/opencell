"""Cytokinesis `single_firing` normalized event adapter (D7) -- round 2.

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
contraction-onset anchor) and never from any ``window_anchor`` metadata
scalar (a *window-boundary* description per
``docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md``, a different
concept from a per-seed data-derived onset tick). If a ring becomes fully
bent and pinches to zero within the same tick ("instantaneous" case), the
onset IS that same tick (it is still the first strict decrease) and the
offset is exactly ``0``.

Round-1 also used the Karr-side channel name ``division_complete`` --
no such field exists anywhere in ``Cytokinesis.m``/``CellGeometry.m``/
``FtsZRing.m`` (an extractor-invented label). This module now projects
the one field that *does* exist on both sides: ``pinchedDiameter``
(``CellGeometry.m:100``: "m; diameter where cell is pinched the most";
``karr_cytokinesis.py`` ``ports_schema()['geometry']['pinchedDiameter']``).

Scope of this module (l2-event-cytokinesis case directive, round 2):
adapter code plus its own unit/integration tests only. Same non-goals as
round 1 (see git history for the full round-1 module docstring): no
MATLAB extraction, no ``opencell/vivarium/karr_cytokinesis.py`` edits, no
``scripts/l2_event/window_loader.py``/``runner.py``/``metrics.py``/
``base.py``/``docs/phase_f/l2_event/event_registry.yaml`` edits.

Verified OC read/write surface (re-audited against
``opencell/vivarium/karr_cytokinesis.py`` HEAD for this round -- see
:data:`REQUIRED_OC_STATE_PATHS` and
:func:`require_cytokinesis_dynamic_state_inputs` docstrings for the
line-by-line accounting): ``next_update()`` reads ``cell.division_progress``,
``chromosome.segregation_progress`` (or ``chromosome.segregated`` if
present -- an explicit, sanctioned fallback the process itself
implements, not a silently-defaulted dead port), ``geometry.width``,
``geometry.pinchedDiameter``, ``geometry.pinched``, five ``ftsZRing``
edge-count/geometry fields, the full dynamic ``enzymes``/``boundEnzymes``
count dicts (keyed by the fixture's runtime-derived FtsZ enzyme WIDs --
NOT hardcodable dotted paths), and
``substrates_allocated.karr_cytokinesis.<water_wid>`` (``water_wid`` is
itself fixture-derived, never hardcoded). ``cell.ftsz_ring_complete`` is
declared in ``ports_schema()`` but never read or assigned in
``next_update()`` -- vestigial, dropped from this adapter's required-input
manifest. ``GTP`` is declared for legacy-compatibility plumbing but
``next_update()`` hardcodes its request to ``0.0`` and never reads an
allocated ``GTP`` value back -- WATER is the process's actual
hydrolysis-limiting allocation channel; GTP is not, and is never, required
by this adapter.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

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
REQUIRED_OC_STATE_PATHS: tuple[tuple[str, ...], ...] = (
    ("cell", "division_progress"),
    ("chromosome", "segregation_progress"),
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

#: Groups that must be present as dicts, but whose exact key sets are
#: fixture/runtime-derived (enzyme WIDs, the WATER substrate WID) and so
#: CANNOT be hardcoded as dotted-path leaves here -- their membership is
#: validated by :func:`require_cytokinesis_dynamic_state_inputs` against
#: the actual `KarrCytokinesisProcess` instance instead.
REQUIRED_OC_STATE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("enzymes",),
    ("boundEnzymes",),
    ("substrates_allocated", "karr_cytokinesis"),
)


class MissingCytokinesisStateInput(Exception):
    """Raised by :func:`require_cytokinesis_state_inputs` /
    :func:`require_cytokinesis_dynamic_state_inputs` when the conditioned
    `state_before` dict (or an `update` dict this adapter must project)
    is missing a required Cytokinesis input. Distinct from a silent
    `dict.get(..., default)` -- a harness that cannot supply one of these
    inputs has an incomplete Cytokinesis conditioning pipeline and must
    fail loudly, not compute a fire/no-fire verdict from a quietly
    defaulted value."""


class CytokinesisTimingError(Exception):
    """Base class for all Cytokinesis single-firing onset/completion
    timing-derivation failures raised by this module's sequence-scanning
    helpers (:func:`find_onset_tick`, :func:`find_completion_tick`,
    :func:`single_fire_offset_from_sequences`). These are distinct from
    :class:`MissingCytokinesisStateInput` (conditioning-input coverage):
    they are raised only when an offset is computed from a *sequence* of
    ticks. `oc_observation`'s own per-tick, stateless fire projection
    never raises any of these -- only the sequence-level offset helpers
    do."""


class InvalidPinchedDiameterSequence(CytokinesisTimingError):
    """A `pinchedDiameter` before/after sequence (or a single reading) is
    non-finite, negative, non-scalar, or has mismatched before/after
    lengths -- cannot be scanned for onset/completion at all."""


class NoCompletionTickDetected(CytokinesisTimingError):
    """No tick in the sequence satisfies the completion predicate
    (`before > 0` then `after == 0`) -- an offset was requested but
    completion never occurred in this sequence. Includes the "no
    decrease ever occurs" case: a sequence with no strict decrease
    anywhere also, definitionally, never completes."""


class DuplicateCompletionTickDetected(CytokinesisTimingError):
    """More than one tick in the sequence satisfies the completion
    predicate -- violates single-firing semantics (`magnitude_gateable:
    false`; at most one completion event is possible per seed)."""


class CompletionWithoutPrecedingOnset(CytokinesisTimingError):
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


class OnsetAfterCompletionTick(CytokinesisTimingError):
    """The detected onset tick occurs strictly after the detected
    completion tick. Structurally unreachable via `find_onset_tick`/
    `find_completion_tick` on validated data (the completion tick is
    itself always a valid onset candidate, so onset can never be found
    LATER than completion) -- retained as a defensive guard against a
    future regression, exercised via a monkeypatched onset search (see
    `test_single_fire_offset_defensive_guard_onset_after_completion`)."""


def require_cytokinesis_state_inputs(state_before: dict[str, Any]) -> None:
    """Raise :class:`MissingCytokinesisStateInput` naming the first
    missing path in :data:`REQUIRED_OC_STATE_PATHS` +
    :data:`REQUIRED_OC_STATE_GROUPS`. No-op if every static/group input is
    present. Does NOT validate the fixture-derived enzyme-WID / WATER-WID
    membership inside those groups -- see
    :func:`require_cytokinesis_dynamic_state_inputs` for that (it needs
    the process instance, which this function deliberately does not
    require, so it stays a pure function of `state_before` alone)."""
    for path in REQUIRED_OC_STATE_PATHS + REQUIRED_OC_STATE_GROUPS:
        node: Any = state_before
        for key in path:
            if not isinstance(node, dict) or key not in node:
                dotted = ".".join(path)
                raise MissingCytokinesisStateInput(
                    f"state_before is missing required Cytokinesis input '{dotted}' "
                    f"(missing at key {key!r}); refusing to silently default it "
                    "(FIX_TEMPLATE_L2_REPLAY Rule 1)."
                )
            node = node[key]


def require_cytokinesis_dynamic_state_inputs(state_before: dict[str, Any], process: Any) -> None:
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
    this duck-typed contract directly.

    Raises :class:`MissingCytokinesisStateInput` naming the first missing
    WID. Requires `require_cytokinesis_state_inputs` to have already
    passed (does not re-check the static/group paths).
    """
    allocated_group = state_before.get("substrates_allocated", {}).get(process.name, {})
    if process.water_wid not in allocated_group:
        raise MissingCytokinesisStateInput(
            f"state_before is missing the allocated WATER input "
            f"'substrates_allocated.{process.name}.{process.water_wid}' -- this is the process's "
            "actual hydrolysis-limiting allocation channel (next_update() reads it back via "
            "_allocated_count); a GTP allocation alone does not satisfy this (GTP's allocated value "
            "is never read back -- see module docstring)."
        )

    enzymes_group = state_before.get("enzymes", {})
    bound_group = state_before.get("boundEnzymes", {})
    for wid in process.fixture_enzyme_wids:
        if wid not in enzymes_group:
            raise MissingCytokinesisStateInput(
                f"state_before is missing required dynamic Cytokinesis input 'enzymes.{wid}' "
                "(a fixture-derived FtsZ enzyme WID next_update() reads via _counts_from_state)."
            )
        if wid not in bound_group:
            raise MissingCytokinesisStateInput(
                f"state_before is missing required dynamic Cytokinesis input 'boundEnzymes.{wid}' "
                "(a fixture-derived FtsZ enzyme WID next_update() reads via _counts_from_state)."
            )


def _finite_nonnegative_scalar(value: Any, *, context: str) -> float:
    """Coerce `value` to a python float, raising
    :class:`InvalidPinchedDiameterSequence` if it is not a scalar (or a
    size-1 array-like), not finite, or negative. `pinchedDiameter` is a
    physical diameter (m); Karr/OC never produce a negative value, and a
    NaN/Inf reading cannot be scanned for a strict decrease."""
    try:
        arr = np.asarray(value)
    except Exception as exc:  # pragma: no cover - defensive, numpy is a hard dependency elsewhere
        raise InvalidPinchedDiameterSequence(f"{context}: could not interpret {value!r} as a scalar: {exc}") from exc
    if arr.ndim != 0 and arr.size != 1:
        raise InvalidPinchedDiameterSequence(f"{context}: not a scalar pinchedDiameter reading (shape {arr.shape}).")
    result = float(arr.reshape(()))
    if not math.isfinite(result):
        raise InvalidPinchedDiameterSequence(f"{context}: non-finite pinchedDiameter reading ({result!r}).")
    if result < 0.0:
        raise InvalidPinchedDiameterSequence(f"{context}: negative pinchedDiameter reading ({result!r}).")
    return result


def _validate_diameter_sequence(values: Sequence[Any], *, label: str) -> tuple[float, ...]:
    if len(values) == 0:
        raise InvalidPinchedDiameterSequence(f"{label} sequence is empty; cannot scan for onset/completion.")
    return tuple(_finite_nonnegative_scalar(v, context=f"{label}[{i}]") for i, v in enumerate(values))


def _validate_matched_sequences(
    before: Sequence[Any], after: Sequence[Any]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    before_v = _validate_diameter_sequence(before, label="pinchedDiameter before")
    after_v = _validate_diameter_sequence(after, label="pinchedDiameter after")
    if len(before_v) != len(after_v):
        raise InvalidPinchedDiameterSequence(
            f"before/after pinchedDiameter sequences have mismatched lengths "
            f"({len(before_v)} vs {len(after_v)})."
        )
    return before_v, after_v


def find_onset_tick(before: Sequence[Any], after: Sequence[Any]) -> int | None:
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


def find_completion_tick(before: Sequence[Any], after: Sequence[Any]) -> int | None:
    """Scan a COMPLETE per-seed/per-run `pinchedDiameter` before/after
    sequence for the single tick where `before > 0` and `after == 0`
    (geometry-pinch completion, mechanically derived from the diameter
    itself -- never from an extractor-invented `division_complete`-style
    label). Returns ``None`` if no such tick exists (a valid, non-firing
    outcome). Raises :class:`DuplicateCompletionTickDetected` if MORE
    THAN ONE tick satisfies the predicate -- `single_firing`/
    `magnitude_gateable: false` semantics permit at most one completion
    event per seed."""
    before_v, after_v = _validate_matched_sequences(before, after)
    completions = [t for t, (b, a) in enumerate(zip(before_v, after_v, strict=True)) if b > 0.0 and a == 0.0]
    if len(completions) > 1:
        raise DuplicateCompletionTickDetected(
            f"{len(completions)} ticks satisfy the completion predicate (before>0, after==0) at local "
            f"ticks {completions}; single_firing semantics permit at most one completion event per seed."
        )
    return completions[0] if completions else None


def single_fire_offset_from_sequences(before: Sequence[Any], after: Sequence[Any]) -> float:
    """The ONLY place `t_completion - t_onset` arithmetic happens for
    Cytokinesis. Deliberately takes no `tick_offset`/`window_anchor`
    argument -- per the ratified 2026-08-02 timing decision, the
    process-local interval is gated from contraction onset (first strict
    `pinchedDiameter` decrease) to geometry-pinch completion
    (`pinchedDiameter` positive -> zero), both derived purely from the
    sequence itself. Raises:

    * :class:`NoCompletionTickDetected` -- no completion in this sequence
      (including the "no decrease ever occurs" case).
    * :class:`DuplicateCompletionTickDetected` -- more than one completion
      tick (propagated from `find_completion_tick`).
    * :class:`CompletionWithoutPrecedingOnset` -- completion found but no
      strict decrease anywhere (structurally unreachable on real data;
      defensive guard).
    * :class:`OnsetAfterCompletionTick` -- onset found strictly after
      completion (structurally unreachable on real data; defensive
      guard).
    """
    completion_tick = find_completion_tick(before, after)
    if completion_tick is None:
        raise NoCompletionTickDetected(
            "No completion tick (pinchedDiameter before>0, after==0) found in this sequence; an offset "
            "cannot be computed for a sequence that never completes."
        )
    onset_tick = find_onset_tick(before, after)
    if onset_tick is None:
        raise CompletionWithoutPrecedingOnset(
            f"Completion detected at local tick {completion_tick}, but no tick anywhere in the sequence "
            "shows a strict pinchedDiameter decrease; completion without a preceding contraction-onset "
            "event is not a valid single Cytokinesis cycle."
        )
    if onset_tick > completion_tick:
        raise OnsetAfterCompletionTick(
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
    rows: Iterable[tuple[dict[str, Any], dict[str, Any]]],
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
        geometry_before = state_before.get("geometry", {}) if isinstance(state_before, dict) else {}
        if not isinstance(geometry_before, dict) or "pinchedDiameter" not in geometry_before:
            raise MissingCytokinesisStateInput(
                f"row {idx}: state_before is missing required 'geometry.pinchedDiameter'."
            )
        geometry_update = (update or {}).get("geometry", {}) if isinstance(update, dict) else {}
        if not isinstance(geometry_update, dict) or "pinchedDiameter" not in geometry_update:
            raise MissingCytokinesisStateInput(
                f"row {idx}: update is missing 'geometry.pinchedDiameter' -- next_update() always emits "
                "this key every tick it runs (see opencell/vivarium/karr_cytokinesis.py's next_update); a "
                "caller handing in a partial/empty update dict cannot be scanned for onset/completion."
            )
        before.append(_finite_nonnegative_scalar(geometry_before["pinchedDiameter"], context=f"row {idx} state_before.geometry.pinchedDiameter"))
        after.append(_finite_nonnegative_scalar(geometry_update["pinchedDiameter"], context=f"row {idx} update.geometry.pinchedDiameter"))
    return tuple(before), tuple(after)


def oc_single_fire_offset(rows: Iterable[tuple[dict[str, Any], dict[str, Any]]]) -> float:
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
    """

    adapter_id: str = "cytokinesis.pinched_diameter_completion.v1"
    process_name: str = "Cytokinesis"
    karr_event_channel: str = KARR_EVENT_CHANNEL

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

    def oc_observation(
        self,
        tick: int,
        state_before: dict[str, Any],
        update: dict[str, Any],
    ) -> EventObservation:
        """Stateless per-tick completion projection on OC's real
        `next_update()` output. `state_before` must be the conditioned
        pre-tick state actually handed to `next_update` (with every path
        in :data:`REQUIRED_OC_STATE_PATHS`/:data:`REQUIRED_OC_STATE_GROUPS`
        present -- enforced by :func:`require_cytokinesis_state_inputs`
        before anything else runs). `update` is the raw dict
        `next_update()` returned; this method never calls `next_update`
        itself (that is the harness's job) and never reads Karr data --
        pure per-tick projection, no mutable carryover, matches
        `karr_observation`'s `pinchedDiameter` predicate exactly (before
        > 0, after == 0), not `cell.division_complete`."""
        require_cytokinesis_state_inputs(state_before)
        before_diameter = _finite_nonnegative_scalar(
            state_before["geometry"]["pinchedDiameter"], context="state_before.geometry.pinchedDiameter"
        )
        geometry_update = (update or {}).get("geometry", {})
        if not isinstance(geometry_update, dict) or "pinchedDiameter" not in geometry_update:
            # `next_update()` always emits `geometry.pinchedDiameter` via a
            # `set` updater every tick it runs (module docstring); this is a
            # defensive fallback for a caller that hands in a partial/empty
            # update dict, not an assumption that OC omits this key in real
            # operation.
            return EventObservation(tick=tick, fired=False, fire_count=0, timing_tick=None, payload={})
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
    "REQUIRED_OC_STATE_GROUPS",
    "MissingCytokinesisStateInput",
    "CytokinesisTimingError",
    "InvalidPinchedDiameterSequence",
    "NoCompletionTickDetected",
    "DuplicateCompletionTickDetected",
    "CompletionWithoutPrecedingOnset",
    "OnsetAfterCompletionTick",
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
