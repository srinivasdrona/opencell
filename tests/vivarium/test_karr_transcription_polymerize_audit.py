from __future__ import annotations

import sys
from pathlib import Path

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

from opencell.vivarium.karr_transcription import KarrTranscriptionProcess


def test_calculate_polymerize_limits_identifies_frontier_and_limiting_bases() -> None:
    proc = KarrTranscriptionProcess({"rng_seed": 0})

    # Three active sequences, all starting with A; second base has simultaneous
    # G/U scarcity, so elongation is one base and limiting bases are G and U.
    sequences = ["AC", "AG", "AU"]
    base_amounts = np.asarray([3, 1, 0, 0], dtype=np.int64)  # A C G U

    elongation, base_usage, limiting_bases = proc._calculate_polymerize_limits(
        sequences, base_amounts
    )

    assert elongation == 1
    np.testing.assert_array_equal(base_usage, np.asarray([3, 0, 0, 0], dtype=np.int64))
    np.testing.assert_array_equal(limiting_bases, np.asarray([2, 3], dtype=np.int64))


def test_limiting_base_cull_consumes_only_available_front_edge_bases() -> None:
    proc = KarrTranscriptionProcess({"rng_seed": 0})

    sequences = ["AG", "AU", "CG", "CU"]
    initial_bases = np.asarray([1, 1, 0, 0], dtype=np.int64)  # A C G U

    progress, remaining = proc._polymerize_limiting_base_cull(sequences, initial_bases)
    consumed = initial_bases - remaining

    np.testing.assert_array_equal(consumed, np.asarray([1, 1, 0, 0], dtype=np.int64))
    assert np.count_nonzero(progress == 1) == 2
    assert np.count_nonzero(progress == 0) == 2


def test_simulate_polymerization_substrates_uses_limiting_base_cull() -> None:
    proc = KarrTranscriptionProcess({"rng_seed": 0})
    proc._active_rnap_fraction = 1.0
    proc._tu_sequences = ("AG", "AU", "CG", "CU")
    proc._polymerase_slots = [
        {"active": True, "tu_idx": 0, "position": 1, "chromosome_pos": 10},
        {"active": True, "tu_idx": 1, "position": 1, "chromosome_pos": 20},
        {"active": True, "tu_idx": 2, "position": 1, "chromosome_pos": 30},
        {"active": True, "tu_idx": 3, "position": 1, "chromosome_pos": 40},
    ]

    deltas = proc._simulate_polymerization_substrate_deltas(
        timestep=1.0,
        states={"substrates": {"ATP": 1.0, "CTP": 1.0, "GTP": 0.0, "UTP": 0.0}},
        effective_bound_counts={"RNA_POLYMERASE": 4, "RNA_POLYMERASE_HOLOENZYME": 0},
    )

    assert deltas == {"ATP": -1.0, "CTP": -1.0}
    positions = sorted(int(slot["position"]) for slot in proc._polymerase_slots)
    assert positions == [1, 1, 2, 2]
