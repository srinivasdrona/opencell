"""Regression checks for the Replication no-hint Design-A runner helper."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from l2_replay_common import (  # noqa: E402
    assert_identity_or_tolerance,
    cell_vector,
    resolve_trace_path,
)
from opencell.state.chromosome_store import ChromosomeStore  # noqa: E402


def _triplet_signature(triplet: Any) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    return (
        tuple(int(x) for x in triplet.positions.tolist()),
        tuple(int(x) for x in triplet.strands.tolist()),
        tuple(int(x) for x in triplet.values.tolist()),
    )


def test_seed0_tick0_no_hint_runner_matches_karr_initiation_substrates_and_topology() -> None:
    trace_path = resolve_trace_path("Replication")
    sample_process = runner_helpers._replication_process(0)
    substrate_wids = list(sample_process.substrate_wids)
    enzyme_wids = list(sample_process.enzyme_wids)

    with h5py.File(trace_path, "r") as trace:
        result = runner_helpers._run_replication_tick(
            0,
            0,
            {
                "substrate_wids": substrate_wids,
                "enzyme_wids": enzyme_wids,
                "oracle_before_substrates": np.asarray(
                    cell_vector(trace, "states_before", "substrates", 0),
                    dtype=np.float64,
                ),
                "oracle_before_enzymes": np.asarray(
                    cell_vector(trace, "states_before", "enzymes", 0),
                    dtype=np.float64,
                ),
                "oracle_before_bound_enzymes": np.asarray(
                    cell_vector(trace, "states_before", "boundEnzymes", 0),
                    dtype=np.float64,
                ),
                "oracle_before_chromosome_store": ChromosomeStore.from_trace_tick(
                    trace_path,
                    tick=0,
                    group_name="states_before",
                ),
            },
        )
        karr_after_substrates = np.asarray(
            cell_vector(trace, "states_after", "substrates", 0),
            dtype=np.float64,
        )
    assert_identity_or_tolerance(
        tick=0,
        observable="substrates",
        oc_after=np.asarray(result["substrates"], dtype=np.float64),
        karr_after=karr_after_substrates,
        process_name="Replication",
    )
    karr_after_store = ChromosomeStore.from_trace_tick(trace_path, tick=0, group_name="states_after")
    assert _triplet_signature(result["chromosome_after_store"].get_field("polymerizedRegions")) == _triplet_signature(
        karr_after_store.get_field("polymerizedRegions")
    )
