"""Tests for ASSERT_POSITIVE_COUNTS allocator guards."""

from __future__ import annotations

import pytest

from opencell.vivarium import karr_allocation_step as kas
from opencell.vivarium.karr_allocation_step import KarrAllocationStep, NegativeCountsError


def _make_step() -> KarrAllocationStep:
    return KarrAllocationStep(
        {
            "consumer_processes": [
                ("consumer_a", ["ATP"]),
                ("consumer_b", ["ATP"]),
            ],
            "substrate_wids": ["ATP"],
        }
    )


def test_allocator_guards_happy_path() -> None:
    step = _make_step()
    update = step.next_update(
        1.0,
        {
            "substrates": {"ATP": 10.0},
            "requests": {
                "consumer_a": {"ATP": 6.0},
                "consumer_b": {"ATP": 4.0},
            },
        },
    )
    assert update["substrates_allocated"]["consumer_a"]["ATP"] == 6.0
    assert update["substrates_allocated"]["consumer_b"]["ATP"] == 4.0


def test_allocator_guards_negative_request_checkpoint() -> None:
    step = _make_step()
    with pytest.raises(NegativeCountsError, match="checkpoint=request"):
        step.next_update(
            1.0,
            {
                "substrates": {"ATP": 10.0},
                "requests": {
                    "consumer_a": {"ATP": -5.0},
                    "consumer_b": {"ATP": 1.0},
                },
            },
        )


def test_allocator_guards_negative_allocation_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    original_floor = kas.np.floor

    def floor_with_negative(values):
        floored = original_floor(values)
        floored = floored.copy()
        floored[0, 0] = -1.0
        return floored

    monkeypatch.setattr(kas.np, "floor", floor_with_negative)

    step = _make_step()
    with pytest.raises(NegativeCountsError, match="checkpoint=allocation"):
        step.next_update(
            1.0,
            {
                "substrates": {"ATP": 10.0},
                "requests": {
                    "consumer_a": {"ATP": 6.0},
                    "consumer_b": {"ATP": 4.0},
                },
            },
        )


def test_allocator_guards_negative_unallocated_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    original_floor = kas.np.floor

    def floor_with_overallocation(values):
        floored = original_floor(values)
        return floored + 10.0

    monkeypatch.setattr(kas.np, "floor", floor_with_overallocation)

    step = _make_step()
    with pytest.raises(NegativeCountsError, match="checkpoint=unallocated"):
        step.next_update(
            1.0,
            {
                "substrates": {"ATP": 1.0},
                "requests": {
                    "consumer_a": {"ATP": 1.0},
                    "consumer_b": {"ATP": 0.0},
                },
            },
        )


def test_allocator_guards_flag_off_skips_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kas, "ASSERT_POSITIVE_COUNTS", False)

    step = _make_step()
    update = step.next_update(
        1.0,
        {
            "substrates": {"ATP": 10.0},
            "requests": {
                "consumer_a": {"ATP": -5.0},
                "consumer_b": {"ATP": 1.0},
            },
        },
    )

    assert update["substrates_allocated"]["consumer_a"]["ATP"] == 0.0
    assert update["substrates_allocated"]["consumer_b"]["ATP"] == 1.0
