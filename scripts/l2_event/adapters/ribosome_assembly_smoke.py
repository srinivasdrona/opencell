"""Optional RibosomeAssembly seed-0 read-only structural smoke adapter.

This is the ONE process-specific adapter this task implements, and it is
explicitly **not** a gating adapter (``adapter_status: structural_smoke_only``
in the registry). It exists only to prove the generic loader + adapter
interface can round-trip a real Karr event-window trace and a real OC port,
per this task's scope note: "RibosomeAssembly seed0 read-only smoke if
possible."

Reuse discipline (requirement 3):

* Karr-side (:meth:`karr_observation`) reads only the window's
  ``states_before``/``states_after`` -- this is the "reference-
  normalization phase" the task permits reading Karr-after in.
* OC-side (:meth:`oc_observation`) is handed only ``state_before`` (built by
  overlaying Karr's ``states_before`` into a fresh OC state template) and
  the OC port's own ``next_update()`` result. It never sees Karr's
  ``states_after`` -- no hints leak into the SUT.
* The OC state overlay and ``next_update()`` call reuse the existing L2.2
  replay primitives in ``tests/vivarium/l2_replay_common.py``
  (``build_state_template``, ``overlay_observable_into_state``,
  ``refresh_allocator_views``) rather than reimplementing state-template
  construction, and are wrapped in the existing anti-oracle guard
  (``forbid_sut_oracle_file_io``) so the SUT cannot smuggle in file-based
  oracle access.

This module is deliberately NOT wired into ``scripts/l2_event/runner.py``'s
gate path -- see ``run_structural_smoke`` in ``runner.py`` for the one
place it is invoked, and note it always returns
``mode="structural_smoke"`` with ``verdict=None``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.l2_event.adapters.base import EventAdapter
from scripts.l2_event.schema import EventObservation
from scripts.l2_event.window_loader import WindowGrid

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VIVARIUM_TEST_DIR = _REPO_ROOT / "tests" / "vivarium"

_RA_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes", "monomers", "complexs", "RNAs")
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "gtpase_wids",
    "boundEnzymes": "gtpase_wids",
    "monomers": "monomer_subunit_wids",
    "complexs": "complex_wids",
    "RNAs": "rna_subunit_wids",
}


def _import_l2_replay_common():
    """Import the existing L2.2 replay-primitive module by inserting its
    directory onto ``sys.path``, matching the pattern every
    ``tests/vivarium/test_karr_*_l2_replay.py`` file already uses. Done
    lazily (not at module import time) so importing this adapter module
    never has a side effect unless the smoke path actually runs."""
    if str(_VIVARIUM_TEST_DIR) not in sys.path:
        sys.path.insert(0, str(_VIVARIUM_TEST_DIR))
    import l2_replay_common  # noqa: PLC0415

    return l2_replay_common


class RibosomeAssemblySmokeAdapter(EventAdapter):
    """Read-only structural smoke adapter for RibosomeAssembly. See module
    docstring -- this must never be used to compute a gate verdict."""

    adapter_id = "ribosome_assembly.smoke.v1"
    process_name = "RibosomeAssembly"
    #: Karr's `complexs` payload channel is treated as the event magnitude.
    payload_channel = "complexs"

    def karr_observation(self, window: WindowGrid, tick: int) -> EventObservation:
        before = window.before(self.payload_channel, tick)
        after = window.after(self.payload_channel, tick)
        delta = after - before
        formed = delta[delta > 0]
        fired = bool(formed.size > 0)
        payload = {f"complex_{i}": float(d) for i, d in enumerate(delta) if d > 0} if fired else {}
        return EventObservation(
            tick=tick,
            fired=fired,
            fire_count=1 if fired else 0,
            timing_tick=tick if fired else None,
            payload=payload,
        )

    def oc_observation(
        self,
        tick: int,
        state_before: dict[str, object],
        update: dict[str, object],
    ) -> EventObservation:
        # Spec §4 fact 5: an allocation-starved tick returns an empty dict
        # with no "complex" key at all; must not be a direct-key-access bug.
        del state_before
        complex_counts = update.get("complex", {}).get("counts", {}) if update else {}
        positive = {k: float(v) for k, v in complex_counts.items() if float(v) > 0}
        fired = bool(positive)
        return EventObservation(
            tick=tick,
            fired=fired,
            fire_count=1 if fired else 0,
            timing_tick=tick if fired else None,
            payload=positive,
        )


def run_ribosome_assembly_oc_tick(process, state_before_overlay: dict[str, object]):
    """Run one OC ``next_update()`` tick for RibosomeAssembly using the
    existing L2.2 anti-oracle guard. Returns the raw ``update`` dict.

    ``state_before_overlay`` must already have Karr's ``states_before``
    values overlaid into a fresh state template (see
    :func:`build_karr_conditioned_state`) -- this function performs no
    Karr-state construction itself, only the guarded ``next_update()``
    call, keeping the "no states_after into the SUT" boundary explicit at
    the call site.
    """
    l2 = _import_l2_replay_common()
    with l2.forbid_sut_oracle_file_io():
        update = process.next_update(1.0, state_before_overlay)
    return update


def build_karr_conditioned_state(process, window: WindowGrid, tick: int):
    """Build one tick's OC input state by overlaying Karr's
    ``states_before`` (only) into a fresh state template, using the
    existing L2.2 overlay/allocator-refresh primitives.

    Returns ``(state, wids_by_observable)``. Reuses
    ``build_state_template``, ``overlay_observable_into_state``,
    ``refresh_allocator_views``, and ``infer_wids_for_observable`` verbatim
    from ``tests/vivarium/l2_replay_common.py`` (requirement 3: reuse
    existing replay primitives safely).
    """
    l2 = _import_l2_replay_common()
    state = l2.build_state_template(process)
    wids_by_observable: dict[str, list[str]] = {}
    for observable in _RA_OBSERVABLES:
        vector = window.before(observable, tick)
        explicit_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable)
        wids = l2.infer_wids_for_observable(
            process, state, observable, karr_len=int(vector.shape[0]), explicit_attr=explicit_attr
        )
        wids_by_observable[observable] = wids
        l2.overlay_observable_into_state(
            process=process, state=state, observable=observable, vector=vector, wids=wids
        )
    l2.refresh_allocator_views(process, state)
    return state, wids_by_observable
