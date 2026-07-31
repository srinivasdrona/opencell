"""Normalized event-adapter interface (D7).

An adapter is the only place where a process-specific event predicate is
allowed to exist. It converts native per-tick state (Karr window-grid rows,
or an OC ``next_update()`` result) into the shared
:class:`scripts.l2_event.schema.EventObservation` record shape. Nothing
downstream (metrics, runner, evidence) ever inspects process-specific
fields directly.

This module intentionally ships **no** concrete process wiring beyond:

* :mod:`scripts.l2_event.adapters.fakes` -- synthetic adapters used only by
  this package's own unit tests.
* :mod:`scripts.l2_event.adapters.ribosome_assembly_smoke` -- one optional,
  explicitly-labeled read-only structural smoke adapter for RibosomeAssembly
  seed 0, per this task's scope.

Any other process (Cytokinesis, DNADamage, FtsZPolymerization) is a
registry entry with ``adapter_status: not_implemented`` and no adapter class
-- implementing them is out of scope for this task.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from scripts.l2_event.schema import EventObservation
from scripts.l2_event.window_loader import WindowGrid


@runtime_checkable
class EventAdapter(Protocol):
    """Cross-language-mirrored adapter contract (D7, surfaces S6/S7).

    Implementations must be pure functions of their inputs: no file I/O, no
    global state, no reading of the *other* side's data (anti-laundering --
    the Karr-side method may only read the window grid's Karr channels; the
    OC-side method may only read the OC process's own runtime state/update).
    """

    #: Stable identifier cross-checked against the event registry
    #: (docs/phase_f/l2_event/event_registry.yaml) and against the
    #: process's ``event_adapter_id`` catalog field (once patched).
    adapter_id: str

    #: Canonical Karr process name this adapter is valid for (must match
    #: ``PROCESS_CATALOG.yaml`` process ``name`` exactly).
    process_name: str

    def karr_observation(self, window: WindowGrid, tick: int) -> EventObservation:
        """Normalize Karr's states_before/after at ``tick`` into an
        :class:`EventObservation`. May read ``states_after`` (reference-
        normalization phase only, per requirement 3) but must not require
        any OC-side input."""
        ...

    def oc_observation(
        self,
        tick: int,
        state_before: dict[str, object],
        update: dict[str, object],
    ) -> EventObservation:
        """Normalize an OC ``next_update()`` result (plus the pre-tick state
        it was computed from) into an :class:`EventObservation`. Must not
        read Karr's ``states_after`` -- OC is judged only on what its own
        update produced from a Karr-state-conditioned input (requirement 3).
        """
        ...


class AdapterProcessMismatch(Exception):
    """Raised when a caller invokes an adapter against a window/process it
    was not registered for (requirement 4: "refuse ... wrong adapter")."""


def assert_adapter_matches_process(adapter: EventAdapter, process_name: str) -> None:
    if adapter.process_name != process_name:
        raise AdapterProcessMismatch(
            f"Adapter '{adapter.adapter_id}' is registered for process "
            f"'{adapter.process_name}', not '{process_name}'."
        )
