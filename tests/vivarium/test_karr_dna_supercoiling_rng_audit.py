from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import build_state_template
from opencell.util.matlab_rng import MatlabRandStream
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess


class _LoggingMatlabRandStream:
    def __init__(self, seed: int) -> None:
        self._stream = MatlabRandStream(seed)
        self.calls: list[tuple[tuple[int, ...], np.ndarray]] = []

    def rand(self, *shape: int) -> np.ndarray:
        out = self._stream.rand(*shape)
        normalized_shape = tuple(int(dim) for dim in shape)
        self.calls.append((normalized_shape, np.asarray(out, dtype=np.float64).copy()))
        return out


def _build_replay_state(
    process: KarrDNASupercoilingProcess,
    *,
    bound_now_topoiv: float,
    bound_next_topoiv: float,
    bound_now_gyrase: float = 2.0,
    bound_next_gyrase: float = 2.0,
) -> dict[str, Any]:
    state = build_state_template(process)
    state["chromosome"]["supercoil_density"] = 0.02
    state["chromosome"]["replication_state"] = "idle"

    for wid in process.enzyme_wids:
        if process.enzyme_store_by_wid[wid] == "complex":
            state["complex"]["counts"][wid] = 10.0
        else:
            state["protein"]["counts"][wid] = 10.0

    state["boundEnzymes"][process.gyrase_wid] = float(bound_now_gyrase)
    state["boundEnzymes"][process.topoiv_wid] = float(bound_now_topoiv)
    state["trace_hint"] = {
        "boundEnzymes_next": {
            process.gyrase_wid: float(bound_next_gyrase),
            process.topoiv_wid: float(bound_next_topoiv),
        },
        "enzymes_next": {},
    }
    state["substrates_allocated"][process.name][process.atp_wid] = 1_000_000.0
    state["substrates_allocated"][process.name][process.h2o_wid] = 1_000_000.0
    return state


def test_dna_supercoiling_replay_rng_matches_matlab_stream_call_pattern_seed0() -> None:
    process = KarrDNASupercoilingProcess({"rng_seed": 0, "replay_rng_warmup_draws": 4})
    logging_rng = _LoggingMatlabRandStream(seed=0)
    process._rng = logging_rng

    calls_by_tick: list[list[tuple[tuple[int, ...], np.ndarray]]] = []

    tick0_state = _build_replay_state(
        process,
        bound_now_topoiv=2.0,
        bound_next_topoiv=1.0,
    )
    start = len(logging_rng.calls)
    process.next_update(1.0, tick0_state)
    calls_by_tick.append(logging_rng.calls[start:])

    tick1_state = _build_replay_state(
        process,
        bound_now_topoiv=1.0,
        bound_next_topoiv=1.0,
    )
    start = len(logging_rng.calls)
    process.next_update(1.0, tick1_state)
    calls_by_tick.append(logging_rng.calls[start:])

    expected_shapes_by_tick: list[list[tuple[int, ...]]] = [
        [(4,), (1,), (), ()],
        [(), ()],
    ]
    for tick, expected_shapes in enumerate(expected_shapes_by_tick):
        actual_shapes = [shape for shape, _ in calls_by_tick[tick]]
        assert actual_shapes == expected_shapes, (
            f"tick={tick} RNG call-shape drift: actual={actual_shapes}, expected={expected_shapes}"
        )

    expected_stream = MatlabRandStream(0)
    expected_calls: list[tuple[tuple[int, ...], np.ndarray]] = [
        ((4,), np.asarray(expected_stream.rand(4), dtype=np.float64)),
        ((1,), np.asarray(expected_stream.rand(1), dtype=np.float64)),
        ((), np.asarray(expected_stream.rand(), dtype=np.float64)),
        ((), np.asarray(expected_stream.rand(), dtype=np.float64)),
        ((), np.asarray(expected_stream.rand(), dtype=np.float64)),
        ((), np.asarray(expected_stream.rand(), dtype=np.float64)),
    ]

    actual_calls = [call for tick_calls in calls_by_tick for call in tick_calls]
    assert len(actual_calls) == len(expected_calls)
    for idx, (actual, expected) in enumerate(zip(actual_calls, expected_calls)):
        actual_shape, actual_values = actual
        expected_shape, expected_values = expected
        assert actual_shape == expected_shape, (
            f"call={idx} shape drift: actual={actual_shape}, expected={expected_shape}"
        )
        np.testing.assert_array_equal(actual_values, expected_values)
