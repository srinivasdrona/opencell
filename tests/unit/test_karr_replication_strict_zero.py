from __future__ import annotations

from typing import Any, Iterable

from opencell.vivarium.karr_replication import KarrReplicationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: Iterable[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_replication_strict_zero_no_global_fallback() -> None:
    process = KarrReplicationProcess({})
    blocked_wids = [*process.dntp_wids, process.atp_wid]

    substrate_values = {wid: 1.0e9 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    state = {
        "chromosome": {
            "replication_state": "elongating",
            "fork_position_bp": {"left": 0.0, "right": 0.0},
            "events": {"replication_complete": 0.0},
        },
        "substrates": guarded_substrates,
        "requests": {process.name: {wid: 0.0 for wid in blocked_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in blocked_wids}},
    }

    update = process.next_update(1.0, state)

    fork_delta = update.get("chromosome", {}).get("fork_position_bp", {})
    assert abs(float(fork_delta.get("left", 0.0))) <= 1.0e-12
    assert abs(float(fork_delta.get("right", 0.0))) <= 1.0e-12

    substrate_delta = update.get("substrates", {})
    for wid in blocked_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
