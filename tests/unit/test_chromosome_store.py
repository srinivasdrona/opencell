from __future__ import annotations

import sys
from pathlib import Path

import h5py
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

from opencell.state.chromosome_store import (
    CHROMOSOME_FIELDS,
    CHROMOSOME_HIDDEN_STATE_KEY,
    ChromosomeStore,
    SparseTriplet,
)


def _resolve_seed_trace_path() -> Path:
    rel = Path("data/m1_sources/karr_native/per_process_traces_v2_s001/DNASupercoiling_100ticks.mat")
    candidates = [
        _REPO_ROOT / rel,
        Path("/mnt/e/opencell") / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    pytest.skip(f"External chromosome v2 trace fixture unavailable: {candidates!r}")


def test_sparse_triplet_circular_normalize_wraps_and_coalesces_duplicates() -> None:
    triplet = SparseTriplet(
        positions=np.array([-1, 10, 0, 0], dtype=np.int64),
        strands=np.array([0, 0, 0, 1], dtype=np.int8),
        values=np.array([1, 2, 3, -3], dtype=np.int32),
        shape=(10, 4),
    )

    assert triplet.positions.tolist() == [0, 0, 9]
    assert triplet.strands.tolist() == [0, 1, 0]
    assert triplet.values.tolist() == [5, -3, 1]
    assert triplet.calc_num_edges() == 3


def test_chromosome_store_crud_defaults_all_11_fields() -> None:
    store = ChromosomeStore()
    assert set(store.to_state()) == set(CHROMOSOME_FIELDS)
    assert all(store.calc_num_edges(field) == 0 for field in CHROMOSOME_FIELDS)

    linking = SparseTriplet(
        positions=np.array([22, 22], dtype=np.int64),
        strands=np.array([0, 1], dtype=np.int8),
        values=np.array([51931, 51931], dtype=np.int32),
        shape=store.shape,
    )
    store.set_field("linkingNumbers", linking)
    round_trip = store.get_field("linkingNumbers")

    assert round_trip.positions.tolist() == [22, 22]
    assert round_trip.strands.tolist() == [0, 1]
    assert round_trip.values.tolist() == [51931, 51931]


def test_chromosome_store_loads_v2_trace_fixture_and_empty_fields() -> None:
    path = _resolve_seed_trace_path()
    with h5py.File(path, "r") as handle:
        dataset = handle["states_before/chromosome"]
        ref = dataset[0, 0] if dataset.shape[0] == 1 else dataset[0, 0]
        store = ChromosomeStore.from_hdf5_group(handle[ref])

    assert store.shape == (580076, 4)
    linking = store.get_field("linkingNumbers")
    assert linking.positions.tolist() == [22, 22]
    assert linking.strands.tolist() == [0, 1]
    assert linking.values.tolist() == [51931, 51931]
    assert linking.shape == (580076, 4)
    assert store.get_field("gapSites").calc_num_edges() == 0
    assert store.get_field("abasicSites").calc_num_edges() == 0


def test_chromosome_store_round_trips_hidden_trace_state() -> None:
    shape = (100, 4)
    payload = {
        "polymerizedRegions": {
            "positions": np.array([0, 0], dtype=np.int64),
            "strands": np.array([0, 1], dtype=np.int8),
            "values": np.array([100, 100], dtype=np.int32),
            "shape": shape,
        },
        CHROMOSOME_HIDDEN_STATE_KEY: {
            "doubleStrandedRegions": {
                "positions": np.array([7, 7], dtype=np.int64),
                "strands": np.array([0, 1], dtype=np.int8),
                "values": np.array([12, 12], dtype=np.int32),
                "shape": shape,
            },
            "superhelicalDensity": {
                "positions": np.array([7, 7], dtype=np.int64),
                "strands": np.array([0, 1], dtype=np.int8),
                "values": np.array([-0.06, -0.06], dtype=np.float64),
                "shape": shape,
            },
            "validated_doubleStrandedRegions": np.uint32(9),
        },
    }

    store = ChromosomeStore.from_state_mapping(payload, shape=shape)
    ds_regions = store.get_hidden_sparse_field("doubleStrandedRegions")
    sigma = store.get_hidden_sparse_field("superhelicalDensity")

    assert ds_regions.positions.tolist() == [7, 7]
    assert ds_regions.strands.tolist() == [0, 1]
    assert ds_regions.values.tolist() == [12, 12]
    assert sigma.values.tolist() == pytest.approx([-0.06, -0.06])
    assert int(store.get_hidden_scalar("validated_doubleStrandedRegions")) == 9

    round_trip = store.to_state()
    assert CHROMOSOME_HIDDEN_STATE_KEY in round_trip
    hidden = round_trip[CHROMOSOME_HIDDEN_STATE_KEY]
    assert hidden["doubleStrandedRegions"]["positions"].tolist() == [7, 7]
    assert hidden["superhelicalDensity"]["values"].tolist() == pytest.approx([-0.06, -0.06])
    assert int(hidden["validated_doubleStrandedRegions"]) == 9
