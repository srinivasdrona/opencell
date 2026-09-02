"""Unit tests for scripts/l2_event/analyze_cytokinesis_randstream_probe.py.

Uses purely synthetic randStream.state sequences (never the real MATLAB
probe output, which requires a licensed MATLAB host) to validate the
Lehmer-recurrence step-counting logic itself is correct, independent of
whether/when the real probe has completed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l2_event.analyze_cytokinesis_randstream_probe import (  # noqa: E402
    _MOD,
    _MUL,
    analyze,
    scalar_state,
    steps_between,
)


def _advance(state: int, n: int) -> int:
    for _ in range(n):
        state = (_MUL * state) % _MOD
    return state


def test_scalar_state_accepts_bare_number_and_one_element_list() -> None:
    assert scalar_state(42) == 42
    assert scalar_state([42]) == 42
    assert scalar_state(42.0) == 42


def test_scalar_state_rejects_multi_element_list() -> None:
    with pytest.raises(ValueError):
        scalar_state([1, 2])


def test_steps_between_zero_when_states_equal() -> None:
    assert steps_between(12345, 12345) == 0


def test_steps_between_matches_known_advance_count() -> None:
    start = 1
    for n in (1, 5, 45, 13, 3, 1000):
        end = _advance(start, n)
        assert steps_between(start, end) == n


def test_steps_between_raises_if_unreachable_within_cap() -> None:
    # A state that can only be reached after > max_steps forward
    # iterations must raise, never silently report a wrong/capped count.
    start = 1
    far = _advance(start, 50)
    with pytest.raises(ValueError):
        steps_between(start, far, max_steps=10)


def test_analyze_reports_draws_and_zero_gap_for_contiguous_ticks() -> None:
    # Simulates the accepted trace's real tick226/227/228 draw counts
    # (45, 13, 3) as a synthetic randStream.state sequence, to validate
    # the report's arithmetic end to end without needing the real probe.
    virgin = 1
    s226_exit = _advance(virgin, 45)
    s227_exit = _advance(s226_exit, 13)
    s228_exit = _advance(s227_exit, 3)

    captures = [
        {
            "local_tick": 226,
            "absolute_tick": 27273,
            "entry_state": virgin,
            "exit_state": s226_exit,
            "chromosome_segregated_before": False,
            "chromosome_segregated_after": True,
        },
        {
            "local_tick": 227,
            "absolute_tick": 27274,
            "entry_state": s226_exit,
            "exit_state": s227_exit,
            "chromosome_segregated_before": True,
            "chromosome_segregated_after": True,
        },
        {
            "local_tick": 228,
            "absolute_tick": 27275,
            "entry_state": s227_exit,
            "exit_state": s228_exit,
            "chromosome_segregated_before": True,
            "chromosome_segregated_after": True,
        },
    ]

    rows = analyze(captures)
    assert [r["draws_this_tick"] for r in rows] == [45, 13, 3]
    # First row has no predecessor capture -> no gap computed.
    assert rows[0]["gap_steps_from_prev_exit"] is None
    # Contiguous local ticks with entry == prev exit -> gap must be 0.
    assert rows[1]["gap_steps_from_prev_exit"] == 0
    assert rows[2]["gap_steps_from_prev_exit"] == 0


def test_analyze_flags_unexpected_nonzero_gap_between_contiguous_ticks() -> None:
    # If a capture's entry_state does not equal the PREVIOUS capture's
    # exit_state despite being the immediately-next local tick, that is
    # exactly the kind of "extra/missing draw between ticks" this probe
    # exists to catch -- must be flagged, never silently reported as 0.
    virgin = 1
    s_a_exit = _advance(virgin, 45)
    # Simulate an extra, unaccounted draw between tick A's exit and tick
    # B's entry (as if some other code path consumed one draw in between).
    s_b_entry = _advance(s_a_exit, 1)
    s_b_exit = _advance(s_b_entry, 13)

    captures = [
        {
            "local_tick": 226,
            "absolute_tick": 27273,
            "entry_state": virgin,
            "exit_state": s_a_exit,
            "chromosome_segregated_before": False,
            "chromosome_segregated_after": True,
        },
        {
            "local_tick": 227,
            "absolute_tick": 27274,
            "entry_state": s_b_entry,
            "exit_state": s_b_exit,
            "chromosome_segregated_before": True,
            "chromosome_segregated_after": True,
        },
    ]

    rows = analyze(captures)
    gap = rows[1]["gap_steps_from_prev_exit"]
    assert isinstance(gap, str) and gap.startswith("UNEXPECTED_NONZERO_GAP")
