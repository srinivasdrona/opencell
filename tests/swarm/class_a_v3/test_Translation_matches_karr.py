"""Karr-differential canary for Translation v3 (swarm pilot Class A)."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.validation.replay import (
    assert_replay_match,
    load_per_process_fixture,
    replay_one_tick,
)
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process


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
    strict=True,
    reason=(
        "Translation fixture is currently non-replayable for one-tick differential "
        "(n_ticks=1 with no replay-ready inputs/outputs)."
    ),
)
def test_Translation_matches_karr_at_tick_N() -> None:
    fixture = load_per_process_fixture("Translation")
    proc = KarrTranslationV3Process({})
    tick_index = min(100, max(0, fixture.n_ticks - 1))

    if not fixture.inputs or not fixture.outputs:
        pytest.xfail(
            "No replay-ready Translation IO channels in fixture companion data "
            f"(inputs={len(fixture.inputs)}, outputs={len(fixture.outputs)})."
        )

    actual = replay_one_tick(proc, fixture, tick_index=tick_index)
    expected = {
        key: _tick_slice(series, tick_index, fixture.n_ticks)
        for key, series in fixture.outputs.items()
        if key in actual
    }
    if not expected:
        pytest.xfail("No overlapping output keys between Translation replay update and fixture outputs.")

    # Deterministic single-tick replay should agree up to floating-point ordering noise.
    assert_replay_match(actual, expected, keys=sorted(expected), rtol=1e-6, atol=1e-8)

