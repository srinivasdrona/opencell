from __future__ import annotations

from typing import Any

import pytest

from opencell.validation.trajectory_compare import (
    SCAFFOLD_OBSERVABLES,
    compare_full_trajectory,
)


def _make_snapshot_trajectory(
    n: int,
    *,
    scale: float = 1.0,
    drop_observable: str | None = None,
) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    for i in range(n):
        state = {
            "cell_dry_mass_g": float(scale * (1.0 + i)),
            "replication_state_code": float(i % 4),
            "fork_position_norm": float(min(1.0, i / max(n - 1, 1))),
            "mrna_total_count_estimate": float(scale * (1000.0 + 2.0 * i)),
            "protein_total_count_estimate": float(scale * (5000.0 + 3.0 * i)),
            "atp_pool": float(scale * (100.0 + i)),
            "gtp_pool": float(scale * (80.0 + i)),
            "dntp_pool_total": float(scale * (40.0 + i)),
            "division_event_timestamp_s": float(32400.0),
        }
        if drop_observable is not None:
            state.pop(drop_observable, None)
        snapshots.append({"tick": i * 100, "time_s": float(i * 100), "state": state})
    return {"snapshots": snapshots}


def test_compare_full_trajectory_identical_snapshots_pass() -> None:
    opencell = _make_snapshot_trajectory(5)
    karr = _make_snapshot_trajectory(5)

    result = compare_full_trajectory(opencell, karr)

    assert set(result) == set(SCAFFOLD_OBSERVABLES)
    for observable in SCAFFOLD_OBSERVABLES:
        assert result[observable]["status"] == "PASS"
        assert result[observable]["n_snapshots_compared"] == 5


def test_compare_full_trajectory_flags_missing_observable() -> None:
    opencell = _make_snapshot_trajectory(5)
    karr = _make_snapshot_trajectory(5, drop_observable="atp_pool")

    result = compare_full_trajectory(opencell, karr)

    assert result["atp_pool"]["status"] == "MISSING_KARR"
    assert result["atp_pool"]["n_snapshots_compared"] == 0


def test_compare_full_trajectory_aligns_by_snapshot_index() -> None:
    opencell = _make_snapshot_trajectory(3)
    karr = _make_snapshot_trajectory(7)

    result = compare_full_trajectory(opencell, karr)

    for observable in SCAFFOLD_OBSERVABLES:
        assert result[observable]["n_snapshots_compared"] == 3


def test_compare_full_trajectory_marks_fail_when_over_tolerance() -> None:
    opencell = _make_snapshot_trajectory(5, scale=2.0)
    karr = _make_snapshot_trajectory(5, scale=1.0)

    result = compare_full_trajectory(opencell, karr)

    failing = [obs for obs, metrics in result.items() if metrics["status"] == "FAIL"]
    assert failing, "Expected at least one observable to fail under 2x scale drift."


def test_compare_full_trajectory_rejects_unknown_alignment() -> None:
    with pytest.raises(ValueError, match="Unsupported alignment mode"):
        compare_full_trajectory({}, {}, alignment="time")
