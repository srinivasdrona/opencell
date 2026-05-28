from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.validation.replay import (
    assert_replay_match,
    load_per_process_fixture,
    replay_one_tick,
)
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess


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
        "Known gap: Cytokinesis replay fixtures capture full state snapshots "
        "(boundEnzymes/enzymes/substrates), but the Vivarium process emits only "
        "request deltas; output-key overlap is empty. "
        "See docs/phase_e/karr_fidelity_known_gaps.md."
    ),
)
def test_replay_smoke_cytokinesis_one_tick() -> None:
    process = KarrCytokinesisProcess({})
    fixture = load_per_process_fixture("Cytokinesis")

    tick_index = min(100, max(0, fixture.n_ticks - 1))
    actual = replay_one_tick(process, fixture, tick_index)

    assert fixture.inputs, "expected resolved fixture inputs"
    assert fixture.outputs, "expected resolved fixture outputs"

    expected = {
        key: _tick_slice(series, tick_index, fixture.n_ticks)
        for key, series in fixture.outputs.items()
        if key in actual
    }
    assert expected, "No overlapping output keys between replay update and fixture output channels."

    assert_replay_match(actual, expected, keys=sorted(expected), rtol=1e-5, atol=0.0)
