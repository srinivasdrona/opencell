"""Cytokinesis `single_firing` normalized event adapter (D7).

Cytokinesis is a `single_firing` EVENT_CLASS process (registry:
``docs/phase_f/l2_event/event_registry.yaml``, ``event_timing_model:
single_firing``, ``magnitude_gateable: false``): a division cycle produces
**at most one** division-completion event per seed, so this adapter's job
is edge detection -- flag exactly the tick where ``division_complete``
transitions False -> True, never every subsequent tick where the
persistent flag simply stays True. Getting this wrong (treating the
persistent post-completion ``True`` as "fired" on every remaining tick in
the window) is exactly the "double OC fire" false-positive shape this
module's tests guard against.

Scope of this module (l2-event-cytokinesis case directive): adapter code
plus its own unit/integration tests only. This module does NOT:

* implement or invoke a MATLAB event-window extractor -- none exists on
  disk for Cytokinesis today (0/50 seeds under any
  ``per_process_traces_v2_event_s*`` directory, per
  ``docs/phase_f/l2_event/event_registry.yaml``'s Cytokinesis row notes);
* flip the central registry's ``adapter_status`` for Cytokinesis away from
  ``not_implemented`` -- that edit is out of this task's scope. See
  ``docs/phase_f/l2_event/PROPOSED_REGISTRY_ROW_cytokinesis.yaml`` for the
  fragment a future registry-owning task can fold in;
* modify ``opencell/vivarium/karr_cytokinesis.py`` or any existing test.

Verified OC read/write surface (Beat 2, primary-source discipline --
checked directly against the current ``opencell/vivarium/
karr_cytokinesis.py`` HEAD, not against the older narrative in
``L2_EVENT_GATE_SPEC_v4.md`` §4 fact 1; see the process report's
"Discrepancies with the v4 baseline facts" section for the full
citation-by-citation comparison):

* ``cell.ftsz_ring_complete`` -- declared in ``ports_schema()``
  (``_updater: "set"``, ``_emit: True``) but never read or assigned inside
  ``next_update()``. Vestigial from an earlier port revision superseded by
  the current explicit FtsZ-ring/geometry state machine.
* ``cell.division_progress`` / ``cell.division_complete`` -- both read
  (via ``_current_division_progress``) and written every tick.
* ``chromosome.segregation_progress`` / ``chromosome.segregated`` -- read
  via ``_segregated()`` (prefers the explicit ``segregated`` bool if
  present, else thresholds ``segregation_progress``).
* ``substrates_allocated["karr_cytokinesis"]["WATER"]`` -- the port's
  *actual* hydrolysis-limiting allocation channel today. ``GTP`` is still
  declared in ``ports_schema()``'s ``requests``/``substrates_allocated``
  groups for legacy-compatibility plumbing (confirmed by
  ``docs/phase_f/STATUS_cytokinesis_precondition.md``: "Cytokinesis DOES
  request GTP from the allocator"), but ``next_update()`` hardcodes the
  GTP *request* to ``0.0`` and never reads
  ``substrates_allocated[...]["GTP"]`` back into the division-progress
  computation.

Adapter design decision: this adapter still REQUIRES all four state
inputs named by the case directive (``cell.ftsz_ring_complete``,
``cell.division_progress``/``cell.division_complete``,
``chromosome.segregation_progress``,
``substrates_allocated.karr_cytokinesis.GTP``) to be present in the
conditioned ``state_before`` dict handed to :meth:`oc_observation`, even
though ``next_update`` does not currently read ``ftsz_ring_complete`` or
the ``GTP`` allocation value back. Both are declared, live ``ports_schema``
keys, and a harness that silently omits a declared port (rather than
letting Vivarium backfill it with its schema default and hoping that is
harmless) is exactly the "default quiet" failure mode this adapter must
refuse instead of tolerate (FIX_TEMPLATE_L2_REPLAY Rule 1). Missing any of
the four raises :class:`MissingCytokinesisStateInput` naming the exact
missing path -- never a silent ``.get(..., default)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.l2_event.schema import EventObservation
from scripts.l2_event.window_loader import WindowGrid

#: The Karr-side channel name this adapter expects a (future) event-window
#: extractor to populate: Karr's own division-completion indicator,
#: sampled every tick over the declared stride-1 window. Named to match
#: OC's own ``cell.division_complete`` field so the cross-language mapping
#: in D7's normalized-record contract is self-evident rather than an
#: arbitrary extractor-side label.
KARR_EVENT_CHANNEL = "division_complete"

#: Dotted-path manifest of the state inputs the case directive requires
#: this adapter to enforce as present (Rule 1: complete, machine-checkable
#: coverage; no observable silently treated as optional).
REQUIRED_OC_STATE_PATHS: tuple[tuple[str, ...], ...] = (
    ("cell", "ftsz_ring_complete"),
    ("cell", "division_progress"),
    ("cell", "division_complete"),
    ("chromosome", "segregation_progress"),
    ("substrates_allocated", "karr_cytokinesis", "GTP"),
)


class MissingCytokinesisStateInput(Exception):
    """Raised by :func:`require_cytokinesis_state_inputs` when the
    conditioned ``state_before`` dict is missing one of the state inputs
    the case directive requires this adapter to enforce. Distinct from a
    silent ``dict.get(..., default)`` -- a harness that cannot supply one
    of these inputs has an incomplete Cytokinesis conditioning pipeline
    and must fail loudly, not compute a fire/no-fire verdict from a
    quietly-defaulted (e.g. always-``False``/``0.0``) value."""


def require_cytokinesis_state_inputs(state_before: dict[str, Any]) -> None:
    """Raise :class:`MissingCytokinesisStateInput` naming the first missing
    dotted path in :data:`REQUIRED_OC_STATE_PATHS`. No-op (returns
    ``None``) if every required input is present."""
    for path in REQUIRED_OC_STATE_PATHS:
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


def division_relative_offset(tick: int, tick_offset: float) -> float:
    """The D2-addendum single-firing timing statistic's raw ingredient:
    ``t_fire - t_division``, where ``t_division`` is the window's own
    declared division/reference anchor
    (:attr:`~scripts.l2_event.window_loader.WindowGrid.tick_offset` --
    per that module's docstring: "float, ticks-from-division/reference
    anchor") and ``tick`` is the LOCAL (window-relative, 0-based) tick
    index at which ``fired=True``.

    This is the adapter's own single, explicit, documented anchor
    convention. No MATLAB extractor exists yet to ratify it against real
    data (spec QO1 remains open) -- any caller computing a single-firing
    offset for Cytokinesis MUST go through this function rather than
    re-deriving the arithmetic ad hoc, so a future extractor landing can
    update exactly one place if the convention needs to change.
    """
    return float(tick) - float(tick_offset)


@dataclass(frozen=True)
class CytokinesisEventAdapter:
    """D7 normalized event adapter for Cytokinesis (single-firing,
    magnitude non-gateable per D6). See module docstring for the verified
    OC read/write surface and the required-input enforcement rationale.
    """

    adapter_id: str = "cytokinesis.division_complete.v1"
    process_name: str = "Cytokinesis"
    karr_event_channel: str = KARR_EVENT_CHANNEL

    def karr_observation(self, window: WindowGrid, tick: int) -> EventObservation:
        """Rising-edge detection on the Karr-side ``division_complete``
        channel: fired only at the tick where ``states_before`` is
        not-complete and ``states_after`` is complete. Reading both sides
        of the SAME tick (never comparing across ticks) is what
        guarantees at most one fire per seed even though the underlying
        state is a persistent bool that stays ``True`` for every
        remaining tick in the window."""
        before = bool(round(float(window.before(self.karr_event_channel, tick)[0])))
        after = bool(round(float(window.after(self.karr_event_channel, tick)[0])))
        fired = (not before) and after
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
        """Rising-edge detection on OC's real ``next_update()`` output.
        ``state_before`` must be the conditioned pre-tick state actually
        handed to ``next_update`` (with every path in
        :data:`REQUIRED_OC_STATE_PATHS` present -- enforced by
        :func:`require_cytokinesis_state_inputs` before anything else runs).
        ``update`` is the raw dict ``next_update()`` returned; this method
        never calls ``next_update`` itself (that is the harness's job, per
        the shared :class:`~scripts.l2_event.adapters.base.EventAdapter`
        contract -- keeps this method a pure, replayable projection)."""
        require_cytokinesis_state_inputs(state_before)
        before_complete = bool(state_before["cell"]["division_complete"])
        cell_update = (update or {}).get("cell", {})
        # `next_update` always emits `cell.division_complete` via a `set`
        # updater every tick it runs (per module docstring); `.get(...,
        # before_complete)` is a defensive fallback for a caller that hands
        # in a partial/empty update dict, not an assumption that OC omits
        # this key in real operation.
        after_complete = bool(cell_update.get("division_complete", before_complete))
        fired = (not before_complete) and after_complete
        return EventObservation(
            tick=tick,
            fired=fired,
            fire_count=1 if fired else 0,
            timing_tick=tick if fired else None,
            payload={},
        )

    def single_fire_offset(self, window: WindowGrid, tick: int) -> float:
        """Convenience wrapper around :func:`division_relative_offset`
        using this window's own declared ``tick_offset`` anchor."""
        return division_relative_offset(tick, window.tick_offset)


__all__ = [
    "KARR_EVENT_CHANNEL",
    "REQUIRED_OC_STATE_PATHS",
    "MissingCytokinesisStateInput",
    "require_cytokinesis_state_inputs",
    "division_relative_offset",
    "CytokinesisEventAdapter",
]
