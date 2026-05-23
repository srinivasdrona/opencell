"""Helpers for read-only derived chromosome views."""

from __future__ import annotations

from typing import Any


def _event_id(event: object, *, fallback_index: int) -> str:
    if isinstance(event, dict):
        for key in ("id", "site_id", "event_id"):
            value = event.get(key)
            if value not in (None, ""):
                return str(value)
        if "position" in event:
            kind = str(event.get("kind", event.get("damage_type", "unknown")))
            return f"{kind}@{event.get('position')}"
    return f"event#{fallback_index}"


def current_damage_sites(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unresolved damage events from cumulative damage and repair streams."""
    chromosome = state.get("chromosome", {})
    damage_events = chromosome.get("damage_events_cumulative", [])
    repair_events = chromosome.get("repair_events_cumulative", [])

    if not isinstance(damage_events, list):
        damage_events = []
    if not isinstance(repair_events, list):
        repair_events = []

    repaired_ids = {
        _event_id(event, fallback_index=idx)
        for idx, event in enumerate(repair_events)
    }
    unresolved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, event in enumerate(damage_events):
        if not isinstance(event, dict):
            continue
        event_id = _event_id(event, fallback_index=idx)
        if event_id in repaired_ids or event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        normalized = dict(event)
        normalized.setdefault("id", event_id)
        normalized.setdefault("site_id", event_id)
        unresolved.append(normalized)
    return unresolved


__all__ = ["current_damage_sites"]
