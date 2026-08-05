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

from l2_replay_common import build_state_template, resolve_trace_path

from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process


def _cell_vector(handle: h5py.File, group: str, observable: str, tick: int) -> np.ndarray:
    ds = handle[f"{group}/{observable}"]
    ref = ds[0, tick] if ds.shape[0] == 1 else ds[tick, 0]
    return np.asarray(handle[ref], dtype=np.float64).reshape(-1)


def _load_tick_vectors(tick: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    trace_path = resolve_trace_path("Translation")
    with h5py.File(trace_path, "r") as trace:
        enzymes_before = _cell_vector(trace, "states_before", "enzymes", tick)
        enzymes_after = _cell_vector(trace, "states_after", "enzymes", tick)
        bound_before = _cell_vector(trace, "states_before", "boundEnzymes", tick)
        bound_after = _cell_vector(trace, "states_after", "boundEnzymes", tick)
    return enzymes_before, enzymes_after, bound_before, bound_after


def test_compute_enzyme_transitions_from_biology_tick0_matches_karr() -> None:
    process = KarrTranslationV3Process({"rng_seed": 0})
    enzymes_before, enzymes_after, bound_before, bound_after = _load_tick_vectors(0)
    state = build_state_template(process)
    state["enzymes"] = {
        wid: float(enzymes_before[idx]) for idx, wid in enumerate(process.enzyme_wids)
    }
    state["boundEnzymes"] = {
        wid: float(bound_before[idx]) for idx, wid in enumerate(process.enzyme_wids)
    }
    process._biology_termination_override = 2
    enzymes_delta, bound_delta = process._compute_enzyme_transitions_from_biology(state, 1.0)

    enzymes_next = np.array(
        [
            float(state["enzymes"].get(wid, 0.0)) + float(enzymes_delta.get(wid, 0.0))
            for wid in process.enzyme_wids
        ],
        dtype=np.float64,
    )
    bound_next = np.array(
        [
            float(state["boundEnzymes"].get(wid, 0.0)) + float(bound_delta.get(wid, 0.0))
            for wid in process.enzyme_wids
        ],
        dtype=np.float64,
    )
    np.testing.assert_allclose(enzymes_next, enzymes_after, rtol=0.0, atol=1e-9)
    np.testing.assert_allclose(bound_next, bound_after, rtol=0.0, atol=1e-9)


def test_next_update_without_trace_hint_matches_tick0_enzyme_signature() -> None:
    process = KarrTranslationV3Process({"rng_seed": 0})
    enzymes_before, enzymes_after, bound_before, bound_after = _load_tick_vectors(0)
    expected_enzyme_delta = enzymes_after - enzymes_before
    expected_bound_delta = bound_after - bound_before

    state = build_state_template(process)
    state["enzymes"] = {
        wid: float(enzymes_before[idx]) for idx, wid in enumerate(process.enzyme_wids)
    }
    state["boundEnzymes"] = {
        wid: float(bound_before[idx]) for idx, wid in enumerate(process.enzyme_wids)
    }

    update = process.next_update(1.0, state)
    assert "enzymes" in update
    assert "boundEnzymes" in update
    for idx, wid in enumerate(process.enzyme_wids):
        got_enzyme = float(update["enzymes"].get(wid, 0.0))
        got_bound = float(update["boundEnzymes"].get(wid, 0.0))
        assert got_enzyme == float(expected_enzyme_delta[idx])
        assert got_bound == float(expected_bound_delta[idx])


def test_next_update_prefers_trace_hint_when_present() -> None:
    process = KarrTranslationV3Process({"rng_seed": 0})
    state = build_state_template(process)
    state.setdefault("enzymes", {})
    state.setdefault("boundEnzymes", {})
    state["enzymes"]["MG_196_MONOMER"] = 10.0
    state["boundEnzymes"]["MG_089_DIMER"] = 4.0
    state["trace_hint"] = {
        "enzymes_next": {"MG_196_MONOMER": 6.0},
        "boundEnzymes_next": {"MG_089_DIMER": 1.0},
    }

    update = process.next_update(1.0, state)
    assert update["enzymes"]["MG_196_MONOMER"] == -4.0
    assert update["boundEnzymes"]["MG_089_DIMER"] == -3.0
