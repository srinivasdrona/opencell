"""RNA-only source-before projection shared by replay and Design-A adapters.

Inputs and outputs have separate entry points. No trace path or after-vector is
accepted by the input builder. Global intergenic row identity stays in the
existing RNA authority; the 38-active standalone RM API is not a full replay.
"""

import pickle

import numpy as np
from l2_replay_common import (
    apply_count_update,
    assert_delta_integral,
    cell_vector,
    collect_count_delta_dicts,
    forbid_sut_oracle_file_io,
)


def observable_keys(process):
    keys = {
        "substrates": list(process.substrate_wids),
        "enzymes": list(process.enzyme_wids),
        "boundEnzymes": list(process.enzyme_wids),
    }
    if process.name == "karr_rna_modification":
        keys.update(
            unmodifiedRNAs=list(process.processed_rna_wids),
            modifiedRNAs=list(process.mature_rna_wids),
        )
    else:
        assert process.name == "karr_rna_processing"
        keys.update(
            unprocessedRNAs=list(process.unprocessed_rna_wids),
            processedRNAs=list(process.processed_rna_wids),
            intergenicRNAs=list(process.intergenic_rna_keys),
        )
    return keys


def _counts(keys, values):
    values = np.asarray(values, dtype=float).reshape(-1)
    assert len(values) == len(keys), f"RNA input length drift: {len(values)} != {len(keys)}"
    assert len(set(keys)) == len(keys), "RNA projection collapses distinct source rows"
    return dict(zip(keys, map(float, values), strict=True))


def source_before_state(process, before):
    """Project captured-before values into actual source RNA/live-enzyme stores."""
    keys = observable_keys(process)
    state = {
        "substrates": _counts(keys["substrates"], before["substrates"]),
        "protein": {"counts": {}},
        "complex": {"counts": {}},
        "rna": {"counts": {}},
        "boundEnzymes": _counts(keys["boundEnzymes"], before["boundEnzymes"]),
    }
    enzymes = _counts(keys["enzymes"], before["enzymes"])
    for store, ids in (
        ("protein", process.monomer_enzyme_wids),
        ("complex", process.complex_enzyme_wids),
    ):
        state[store]["counts"].update({wid: enzymes[wid] for wid in ids})
    # Source snapshots already hold this isolated process's post-allocation share.
    state["substrates_allocated"] = {process.name: dict(state["substrates"])}
    if process.name == "karr_rna_modification":
        state["rna"]["counts"] = _counts(keys["unmodifiedRNAs"], before["unmodifiedRNAs"])
        state["rna"]["modified_counts"] = _counts(keys["modifiedRNAs"], before["modifiedRNAs"])
    else:
        for observable in ("unprocessedRNAs", "processedRNAs"):
            state["rna"]["counts"].update(_counts(keys[observable], before[observable]))
        # Absence is NOT treated as evidence for zero initial fragments: the
        # separate mandatory family-coverage test rejects such stale traces.
        if "intergenicRNAs" in before:
            state["rna"]["counts"].update(_counts(keys["intergenicRNAs"], before["intergenicRNAs"]))
    return state


def project_source_state(process, state):
    keys = observable_keys(process)
    rnas, enzymes = process._input_vectors(state)  # actual production read-only input path
    result = {
        "substrates": np.array([state["substrates"][wid] for wid in keys["substrates"]]),
        "enzymes": enzymes,
        "boundEnzymes": np.array([state["boundEnzymes"][wid] for wid in keys["boundEnzymes"]]),
    }
    if process.name == "karr_rna_modification":
        result["unmodifiedRNAs"] = rnas
        result["modifiedRNAs"] = np.array(
            [state["rna"]["modified_counts"].get(wid, 0) for wid in keys["modifiedRNAs"]]
        )
    else:
        result["unprocessedRNAs"] = rnas
        for observable in ("processedRNAs", "intergenicRNAs"):
            result[observable] = np.array(
                [state["rna"]["counts"].get(wid, 0) for wid in keys[observable]]
            )
    return result


def assert_source_inputs(process, state, before):
    projected = project_source_state(process, state)
    for observable, expected in before.items():
        np.testing.assert_array_equal(
            projected[observable], expected, err_msg=f"source-before roundtrip: {observable}"
        )
    np.testing.assert_array_equal(
        [state["substrates_allocated"][process.name][wid] for wid in process.substrate_wids],
        before["substrates"],
        err_msg="source-before full grant",
    )
    assert "trace_hint" not in state
    assert "enzymes" not in state, "legacy enzymes must not replace live split stores"


def trace_before(process, trace, tick):
    return {
        observable: cell_vector(trace, "states_before", observable, tick)
        for observable in observable_keys(process)
        if observable in trace["states_before"]
    }


def prove_trace_inputs(process, trace, n_ticks):
    rng_before = pickle.dumps(process._rng)
    for tick in range(n_ticks):
        before = trace_before(process, trace, tick)
        state = source_before_state(process, before)
        assert_source_inputs(process, state, before)
    assert pickle.dumps(process._rng) == rng_before, "source input proof consumed RNG"


def execute_rna_update(process, state):
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, state)
    for label, deltas in collect_count_delta_dicts(update):
        assert_delta_integral(label, deltas)
    apply_count_update(state, update)
    return update


def assert_exact_replay(tick, observable, actual, expected):
    assert actual.shape == expected.shape, f"RNA replay shape drift: {observable}"
    assert np.array_equal(expected, np.rint(expected)), f"oracle non-integral: {observable}"
    assert np.array_equal(actual, np.rint(actual)), f"OC non-integral: {observable}"
    mismatch = np.flatnonzero(actual != expected)
    assert not len(mismatch), (
        f"L2a mismatch record: tick={tick}, observable={observable}, index={mismatch[0]}, "
        f"oc_val={actual[mismatch[0]]}, karr_val={expected[mismatch[0]]}, "
        f"diff={actual[mismatch[0]] - expected[mismatch[0]]}"
    )


def replay_recorded_channels(process, trace, n_ticks):
    # Prove ALL inputs before a first output mismatch can stop exact comparison.
    prove_trace_inputs(process, trace, n_ticks)
    for tick in range(n_ticks):
        before = trace_before(process, trace, tick)
        state = source_before_state(process, before)
        execute_rna_update(process, state)
        actual = project_source_state(process, state)
        for observable in observable_keys(process):
            if observable in trace["states_after"]:
                assert_exact_replay(
                    tick,
                    observable,
                    actual[observable],
                    cell_vector(trace, "states_after", observable, tick),
                )


def assert_source_family_coverage(process, trace):
    required = set(observable_keys(process))
    missing = {
        group: sorted(required - set(trace[group]))
        for group in ("states_before", "states_after")
        if required - set(trace[group])
    }
    assert not missing, f"{process.name} source families missing: {missing}"
