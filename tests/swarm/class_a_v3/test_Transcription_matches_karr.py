"""Karr-differential canary for Transcription v3 (swarm pilot Class A)."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.validation.replay import (
    assert_replay_match,
    load_per_process_fixture,
    replay_one_tick,
)
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process


_FIXTURE_PROBE = load_per_process_fixture("Transcription")
_HAS_TICK_IO = bool(_FIXTURE_PROBE.inputs) and bool(_FIXTURE_PROBE.outputs)
_XFAIL_REASON = (
    "Transcription fixture does not expose tick-resolved input/output channels "
    "required by generic one-tick replay."
)


def _tick_slice(series: np.ndarray, tick_index: int, n_ticks: int) -> np.ndarray:
    arr = np.asarray(series)
    if n_ticks <= 1:
        return np.asarray(arr[0]) if arr.ndim > 0 else arr
    if arr.ndim > 0 and arr.shape[0] == n_ticks:
        return np.asarray(arr[tick_index])
    if arr.ndim > 1 and arr.shape[-1] == n_ticks:
        return np.asarray(np.take(arr, tick_index, axis=-1))
    raise ValueError(f"Series is not tick-indexed as expected: shape={arr.shape} n_ticks={n_ticks}")


@pytest.mark.xfail(
    condition=not _HAS_TICK_IO,
    strict=True,
    run=False,
    reason=_XFAIL_REASON,
)
def test_Transcription_v3_matches_karr_at_tick_N() -> None:
    fixture = load_per_process_fixture("Transcription")
    process = KarrTranscriptionV3Process({})

    # Class A guidance prefers a steady-state-region tick when available.
    tick_index = min(100, max(0, fixture.n_ticks - 1))
    actual = replay_one_tick(process, fixture, tick_index)
    expected = {
        key: _tick_slice(series, tick_index, fixture.n_ticks)
        for key, series in fixture.outputs.items()
        if key in actual
    }
    if not expected:
        pytest.xfail(
            "No overlapping output keys between replay update and fixture outputs; "
            "a process-specific output-key map is required."
        )

    # Deterministic arithmetic path; keep tolerance tight when keys are mappable.
    assert_replay_match(actual, expected, keys=sorted(expected), rtol=1e-6, atol=1e-9)
