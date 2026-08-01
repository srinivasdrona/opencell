"""Candidate gating-ready RibosomeAssembly event adapter (unregistered).

**Status:** this adapter is NOT the registry's current
``ribosome_assembly.smoke.v1`` (``adapter_status: structural_smoke_only``
in ``docs/phase_f/l2_event/event_registry.yaml``, per this task's
authoritative catalog/registry row -- unchanged by this task). This module
is a *second*, independently versioned adapter (``ribosome_assembly.gate.v1``)
that implements the full D7 normalized-record contract well enough to be
run through ``scripts.l2_event.runner.evaluate_gate`` -- i.e. it is
"gating-ready" as an *implementation*. It is deliberately **not** wired
into the real registry/CLI dispatch (no catalog/event_registry/
evidence_index edits per this task's scope): see
``docs/phase_f/l2_event/RIBOSOME_ASSEMBLY_GATE_ADAPTER_REPORT.md`` for the
proposed registry-row patch (a separate fragment, never applied to the
central YAML by this task) and for why a 50-seed real event-window
ensemble does not exist yet to actually flip the registry's
``adapter_status`` to ``gating_ready``.

Difference from :mod:`scripts.l2_event.adapters.ribosome_assembly_smoke`:

* The smoke adapter infers its Karr-index -> OC-wid payload mapping at
  runtime from ``build_karr_conditioned_state``'s wid inference (needed
  because that helper's job is to prove the *generic* loader/overlay
  machinery works, without hardcoding any process-specific wid identity).
  This adapter instead declares the mapping as a **fixed module-level
  constant** (:data:`_COMPLEX_INDEX_BY_WID`), because
  ``KarrRibosomeAssemblyProcess.complex_wids`` is a stable,
  seed-independent, trace-independent ordering
  (``["RIBOSOME_30S", "RIBOSOME_50S"]`` -- verified directly against the
  live process object, not merely asserted) and Karr's own ``complexs``
  trace channel is written in that same fixed order (per the same
  ``getGtpPerComplex``/``complexWholeCellModelIDs`` ordering the SUT-parity
  audit at ``docs/phase_f/sut_audits/ribosome_assembly_oc_vs_karr.md``
  already cites). A gating adapter meant to run unattended over a 50-seed
  ensemble should not have to rebuild an OC process/state template per
  seed just to learn a mapping that never changes.
* ``required_payload_components`` is therefore never ``None`` here (unlike
  the smoke adapter's optional/fallback-to-placeholder-keys behavior) --
  this adapter always declares its exact 2-WID keyspace, so
  ``metrics.payload_gate`` enforces it unconditionally.

Reuse discipline (FIX_TEMPLATE_L2_REPLAY.md Rule 7): this module computes
no deltas, mutates no process state, and calls no private helper on the
delta path. ``oc_observation`` only ever inspects an already-produced
``update`` dict via ``.get(...)`` -- it never calls ``next_update`` itself
(callers do that, exactly like the smoke adapter's
``run_ribosome_assembly_oc_tick`` does). ``karr_observation`` only ever
reads the window grid's own ``complexs`` channel -- no OC-side input, no
file I/O beyond what the caller-supplied :class:`WindowGrid` already
loaded (Rule 8: no trace-cribbing -- this module itself never opens a
trace file).
"""

from __future__ import annotations

from scripts.l2_event.schema import EventObservation
from scripts.l2_event.window_loader import WindowGrid

#: Karr's `complexs` channel positional order for RibosomeAssembly, fixed
#: and seed-/trace-independent. Verified directly against
#: ``KarrRibosomeAssemblyProcess({"rng_seed": 0}).complex_wids`` ==
#: ``["RIBOSOME_30S", "RIBOSOME_50S"]`` (index 0 -> 30S, index 1 -> 50S) --
#: this is also the same order the Karr `.m` source's
#: `complexIndexs_30S_ribosome`/`complexIndexs_50S_ribosome` fixture
#: scalars declare (1-based MATLAB 1/2 == 0-based Python 0/1). NOT derived
#: from any per-run wid inference: this is a declared, stable adapter
#: constant, exactly matching this task's contract ("new versioned gating
#: adapter normalizes Karr event tick incidence and payload to WIDs
#: RIBOSOME_30S/RIBOSOME_50S").
_COMPLEX_INDEX_BY_WID: dict[int, str] = {0: "RIBOSOME_30S", 1: "RIBOSOME_50S"}

#: Karr's per-tick state-vector channel this adapter treats as the event
#: magnitude/incidence source (states_before/after group name in the
#: event-window trace). Distinct from OC's `complex.counts` update key --
#: see spec §4 fact 6.
_PAYLOAD_CHANNEL = "complexs"


class UnmappedComplexIndexError(ValueError):
    """Raised when the Karr `complexs` channel's positional width does not
    exactly equal the number of WIDs :data:`_COMPLEX_INDEX_BY_WID` (or a
    caller-supplied override) declares. This is a *hard* width check, run
    before any per-index mapping: a channel with width 1 or width 3 is
    refused even if the extra/missing index's delta happens to be exactly
    zero on this particular tick, because a trace/adapter whose declared
    keyspace cardinality silently drifts from the real channel width is a
    coverage-completeness bug (Rule 1) regardless of whether any single
    tick's data would have papered over it. Silently dropping (or
    zero-filling) an out-of-range index's delta would let a real, nonzero
    magnitude on some *other* tick pass through unmapped and unnoticed.
    """


class RibosomeAssemblyGateAdapter:
    """Gating-ready (implementation-complete, registry-unregistered)
    RibosomeAssembly event adapter.

    ``fire_count`` semantics (identical convention to the smoke adapter,
    restated here because this adapter is the one meant to actually be
    run through :func:`scripts.l2_event.runner.evaluate_gate`'s count/
    timing gates): both :meth:`karr_observation` and :meth:`oc_observation`
    report **tick incidence** -- ``1`` if the tick shows any net-positive
    complex-count delta (Karr) / any positive `complex.counts` entry (OC),
    ``0`` otherwise. This is never a particle/molecule count; a tick where
    only RIBOSOME_30S forms and a tick where both RIBOSOME_30S AND
    RIBOSOME_50S form in the same tick (D2's "repeated-firing, all-or-
    nothing per tick" model does not preclude two particles forming
    together) both report ``fire_count=1``. Magnitude for each named
    complex lives in ``payload`` only, gated separately by
    ``metrics.payload_gate``.
    """

    adapter_id = "ribosome_assembly.gate.v1"
    process_name = "RibosomeAssembly"
    payload_channel = _PAYLOAD_CHANNEL

    def __init__(self, complex_index_by_wid: dict[int, str] | None = None):
        """Defaults to the real, fixed :data:`_COMPLEX_INDEX_BY_WID`
        mapping. A caller may override it only for adversarial unit tests
        that need to exercise :class:`UnmappedComplexIndexError` or a
        deliberately wrong/partial mapping -- production use (and the
        real-seed0 structural round-trip) always uses the default.
        """
        self.complex_index_by_wid: dict[int, str] = dict(
            complex_index_by_wid if complex_index_by_wid is not None else _COMPLEX_INDEX_BY_WID
        )

    @property
    def required_payload_components(self) -> frozenset[str]:
        """Unlike the smoke adapter (whose equivalent property returns
        ``None`` when unmapped), this is always the declared 2-WID
        keyspace: ``metrics.payload_gate`` must always enforce it for this
        adapter, never fall back to the generic union/NO_OC_COMPONENT-only
        check.

        Note (verdict, not refusal): when the observed Karr+OC payload
        keyspace union does not exactly equal this declared set -- an
        extra/bogus OC key, or this set's required component absent from
        the observed union entirely -- ``metrics.payload_gate`` reports a
        hard **FAIL** ``ChannelVerdict`` for the payload channel (which
        rolls up into an overall process ``FAIL``). This is a computed
        gate verdict, not a :class:`~scripts.l2_event.runner.RunnerRefusal`
        (the refusal gauntlet only ever concerns whether a verdict can be
        computed at all -- adapter identity, ensemble size, empty support,
        cohort consistency -- never the payload keyspace itself). See
        ``tests/scripts/test_l2_event_ribosome_assembly_gate.py::
        test_evaluate_gate_fails_when_oc_reports_a_spurious_extra_component``.
        """
        return frozenset(self.complex_index_by_wid.values())

    def karr_observation(self, window: WindowGrid, tick: int) -> EventObservation:
        before = window.before(self.payload_channel, tick)
        after = window.after(self.payload_channel, tick)
        delta = after - before
        expected_width = len(self.complex_index_by_wid)
        if delta.shape[0] != expected_width:
            raise UnmappedComplexIndexError(
                f"RibosomeAssembly `{self.payload_channel}` channel width "
                f"{delta.shape[0]} does not exactly match this adapter's declared "
                f"mapping width {expected_width} "
                f"(complex_index_by_wid={self.complex_index_by_wid!r}); refusing "
                "rather than assuming an extra/missing index is always zero."
            )
        payload: dict[str, float] = {}
        for i, d in enumerate(delta):
            if d <= 0:
                continue
            key = self.complex_index_by_wid.get(i)
            if key is None:
                # Defensive: reachable only if complex_index_by_wid has the
                # right cardinality but non-dense keys (e.g. {0: ..., 5:
                # ...}) -- the width check above only guards cardinality,
                # not key coverage over range(expected_width).
                raise UnmappedComplexIndexError(
                    f"RibosomeAssembly `{self.payload_channel}` channel index {i} has no "
                    f"declared WID mapping in complex_index_by_wid={self.complex_index_by_wid!r}."
                )
            payload[key] = float(d)
        fired = bool(payload)
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
        # with no "complex" key at all; `.get(...)` (never direct
        # subscripting) is mandatory here, exactly per this task's
        # contract.
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
