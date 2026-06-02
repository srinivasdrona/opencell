from __future__ import annotations

import sys
from pathlib import Path

import h5py
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

from l2_replay_common import (
    build_state_template,
    cell_vector,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_karr_vector,
    refresh_allocator_views,
    resolve_trace_path,
)
from opencell.util.matlab_rng import MatlabRandStream
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess

_TRACE_PROCESS_NAME = "ProteinModification"
_OBSERVABLES = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "modifiedMonomers",
    "unmodifiedMonomers",
)
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
    "modifiedMonomers": "modified_monomer_wids",
    "unmodifiedMonomers": "unmodified_monomer_wids",
}
_STORE_PATH_OVERRIDE = {
    "modifiedMonomers": ("protein", "modified_counts"),
    "unmodifiedMonomers": ("protein", "unmodified_counts"),
}
_INDEX_PROJECTION_ATTR = {
    "modifiedMonomers": "active_protein_indices",
    "unmodifiedMonomers": "active_protein_indices",
}


class _LoggingMatlabRandStream:
    def __init__(self, seed: int) -> None:
        self._stream = MatlabRandStream(seed)
        self.calls: list[tuple[tuple[int, ...], np.ndarray]] = []

    def rand(self, *shape: int) -> np.ndarray:
        out = self._stream.rand(*shape)
        normalized_shape = tuple(int(dim) for dim in shape)
        self.calls.append((normalized_shape, np.asarray(out, dtype=np.float64).copy()))
        return out


def _collect_calls_by_tick(n_ticks: int) -> list[list[tuple[tuple[int, ...], np.ndarray]]]:
    process = KarrProteinModificationProcess({"rng_seed": 0})
    logging_rng = _LoggingMatlabRandStream(seed=0)
    process._rng = logging_rng

    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        available_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert available_ticks >= n_ticks

        state_template = build_state_template(process)
        wids_by_observable: dict[str, list[str]] = {}
        for observable in _OBSERVABLES:
            karr_before = cell_vector(trace, "states_before", observable, 0)
            explicit_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable)
            wids_by_observable[observable] = infer_wids_for_observable(
                process,
                state_template,
                observable,
                karr_len=int(karr_before.shape[0]),
                explicit_attr=explicit_attr,
                canonical_wids_override={},
            )

        calls_by_tick: list[list[tuple[tuple[int, ...], np.ndarray]]] = []
        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vectors = {
                observable: project_karr_vector(
                    process,
                    observable,
                    cell_vector(trace, "states_before", observable, tick),
                    index_projection_attr=_INDEX_PROJECTION_ATTR,
                )
                for observable in _OBSERVABLES
            }
            for observable in _OBSERVABLES:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                    store_path_override=_STORE_PATH_OVERRIDE,
                )
            refresh_allocator_views(process, state)

            start = len(logging_rng.calls)
            process.next_update(1.0, state)
            calls_by_tick.append(logging_rng.calls[start:])

    return calls_by_tick


def test_protein_modification_replay_rng_matches_matlab_stream_call_pattern_seed0() -> None:
    n_ticks = 25
    calls_run_a = _collect_calls_by_tick(n_ticks=n_ticks)
    calls_run_b = _collect_calls_by_tick(n_ticks=n_ticks)

    counts_run_a = [len(tick_calls) for tick_calls in calls_run_a]
    counts_run_b = [len(tick_calls) for tick_calls in calls_run_b]
    assert counts_run_a == counts_run_b

    shapes_run_a = [[shape for shape, _ in tick_calls] for tick_calls in calls_run_a]
    shapes_run_b = [[shape for shape, _ in tick_calls] for tick_calls in calls_run_b]
    assert shapes_run_a == shapes_run_b

    expected_stream = MatlabRandStream(0)
    for call_idx, (shape, values) in enumerate(calls_run_a[0]):
        expected = expected_stream.rand(*shape)
        expected_values = np.asarray(expected, dtype=np.float64)
        np.testing.assert_array_equal(
            values,
            expected_values,
            err_msg=f"tick0 call={call_idx} rand values drift for shape={shape}",
        )
