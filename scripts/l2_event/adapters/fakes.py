"""Synthetic adapters used only by this package's own unit tests.

These are deliberately trivial and process-agnostic: they read a
pre-baked ``event_fire_count`` (and optional ``event_payload``) channel
straight out of a synthetic :class:`~scripts.l2_event.window_loader.WindowGrid`
for the Karr side, and a plain ``dict`` (shaped like an OC
``next_update()`` result) for the OC side. This lets the metrics/runner
tests exercise every gating path (single-fire, repeated-fire, spurious
OC-only fires, count/timing/payload divergence, empty support) without
depending on any real biology port or real MAT trace file.

None of these are registered in ``docs/phase_f/l2_event/event_registry.yaml``
and the runner refuses to use them outside test mode (``adapter_id`` does
not match any real process's registry entry).
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.l2_event.schema import EventObservation
from scripts.l2_event.window_loader import WindowGrid


@dataclass(frozen=True)
class SyntheticFireCountAdapter:
    """Reads ``fire_count`` per tick straight out of the window's
    ``event_fire_count`` observable (Karr side) and out of
    ``update["fire_count"]`` (OC side)."""

    adapter_id: str = "test.synthetic_fire_count.v1"
    process_name: str = "SyntheticTestProcess"
    payload_channels: tuple[str, ...] = ()

    def karr_observation(self, window: WindowGrid, tick: int) -> EventObservation:
        fire_count = int(round(float(window.after("event_fire_count", tick)[0])))
        payload = {
            channel: float(window.after(channel, tick)[0])
            for channel in self.payload_channels
        }
        return EventObservation(
            tick=tick,
            fired=fire_count > 0,
            fire_count=fire_count,
            timing_tick=tick if fire_count > 0 else None,
            payload=payload if fire_count > 0 else {},
        )

    def oc_observation(
        self,
        tick: int,
        state_before: dict[str, object],
        update: dict[str, object],
    ) -> EventObservation:
        del state_before  # unused by this synthetic adapter
        fire_count = int(update.get("fire_count", 0))
        payload_raw = update.get("payload", {})
        payload = {k: float(v) for k, v in dict(payload_raw).items()} if fire_count > 0 else {}
        return EventObservation(
            tick=tick,
            fired=fire_count > 0,
            fire_count=fire_count,
            timing_tick=tick if fire_count > 0 else None,
            payload=payload,
        )


@dataclass(frozen=True)
class WrongProcessAdapter(SyntheticFireCountAdapter):
    """Same behavior as :class:`SyntheticFireCountAdapter` but registered
    under a different ``process_name`` -- used to test the
    ``ADAPTER_PROCESS_MISMATCH`` refusal path."""

    adapter_id: str = "test.wrong_process.v1"
    process_name: str = "SomeOtherProcess"
