"""Targeted no-hint subfunction-order equivalence checks for Replication.

This file exists because the OC no-hint path still inlines/fuses several
Karr subfunctions, so the safe closure is not a hand-waved "OPEN
ordering gap" comment but a real, source-surface equivalence test on the
problematic active tick. These checks use only Karr `states_before`
inputs and compare the resulting OC output against the real `states_after`
surface; production code never reads oracle-after data.
"""

from __future__ import annotations

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import h5py
import numpy as np
from l2_replay_common import (  # noqa: E402
    assert_identity_or_tolerance,
    cell_vector,
    resolve_trace_path,
)
from test_karr_replication_runner_no_hint import _triplet_signature  # noqa: E402

from opencell.state.chromosome_store import ChromosomeStore  # noqa: E402


def _filtered_complex_bound_signature(store: ChromosomeStore, *, include_values: set[int]) -> tuple[
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
]:
    triplet = store.get_field("complexBoundSites")
    keep = np.isin(triplet.values, np.fromiter(include_values, dtype=np.int32))
    return _triplet_signature(
        type(triplet)(
            positions=triplet.positions[keep],
            strands=triplet.strands[keep],
            values=triplet.values[keep],
            shape=triplet.shape,
        )
    )


def test_seed0_tick15_no_hint_runner_matches_karr_active_order_surface() -> None:
    trace_path = resolve_trace_path("Replication")
    sample_process = runner_helpers._replication_process(0)
    substrate_wids = list(sample_process.substrate_wids)

    with h5py.File(trace_path, "r") as trace:
        result = runner_helpers._run_replication_tick(
            0,
            15,
            {
                "substrate_wids": substrate_wids,
                "enzyme_wids": list(sample_process.enzyme_wids),
                "oracle_before_substrates": np.asarray(
                    cell_vector(trace, "states_before", "substrates", 15),
                    dtype=np.float64,
                ),
                "oracle_before_enzymes": np.asarray(
                    cell_vector(trace, "states_before", "enzymes", 15),
                    dtype=np.float64,
                ),
                "oracle_before_bound_enzymes": np.asarray(
                    cell_vector(trace, "states_before", "boundEnzymes", 15),
                    dtype=np.float64,
                ),
                "oracle_before_chromosome_store": ChromosomeStore.from_trace_tick(
                    trace_path,
                    tick=15,
                    group_name="states_before",
                ),
            },
        )
        karr_after_substrates = np.asarray(
            cell_vector(trace, "states_after", "substrates", 15),
            dtype=np.float64,
        )
    assert_identity_or_tolerance(
        tick=15,
        observable="substrates",
        oc_after=np.asarray(result["substrates"], dtype=np.float64),
        karr_after=karr_after_substrates,
        process_name="Replication",
    )
    karr_after_store = ChromosomeStore.from_trace_tick(trace_path, tick=15, group_name="states_after")
    replisome_values = {
        int(sample_process.helicase_global_index),
        int(sample_process.two_core_beta_clamp_gamma_complex_primase_global_index),
        int(sample_process.core_beta_clamp_gamma_complex_global_index),
        int(sample_process.core_beta_clamp_primase_global_index),
        int(sample_process.beta_clamp_global_index),
    }
    assert _filtered_complex_bound_signature(
        result["chromosome_after_store"],
        include_values=replisome_values,
    ) == _filtered_complex_bound_signature(
        karr_after_store,
        include_values=replisome_values,
    )
