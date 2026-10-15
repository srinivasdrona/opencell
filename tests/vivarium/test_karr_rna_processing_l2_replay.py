"""Source-before-only RP replay, with a separate mandatory output-family gate."""

import h5py
import numpy as np
from _rna_replay_inputs import (
    assert_source_family_coverage,
    prove_trace_inputs,
    replay_recorded_channels,
)
from l2_replay_common import audit_trace_mutated_ticks, resolve_trace_path

from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess

_OBSERVABLES = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "processedRNAs",
    "unprocessedRNAs",
    "intergenicRNAs",
)
_PASS_THROUGH = frozenset({"enzymes", "boundEnzymes"})
_SCRATCH_RESET = {"_rng": "karr-persistent"}
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
    "unprocessedRNAs": "unprocessed_rna_wids",
    "processedRNAs": "processed_rna_wids",
    "intergenicRNAs": "intergenic_rna_keys",
}


def test_source_before_inputs_roundtrip_all_ticks():
    process = KarrRNAProcessingProcess({"rng_seed": 0})
    with h5py.File(resolve_trace_path("RNAProcessing"), "r") as trace:
        prove_trace_inputs(process, trace, 100)


def test_source_output_families_are_recorded():
    with h5py.File(resolve_trace_path("RNAProcessing"), "r") as trace:
        assert_source_family_coverage(KarrRNAProcessingProcess(), trace)


def test_karr_rna_processing_l2_replay_identity_per_tick():
    process = KarrRNAProcessingProcess({"rng_seed": 0})
    with h5py.File(resolve_trace_path("RNAProcessing"), "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).item())
        assert n_ticks == 100
        assert int(np.asarray(trace["metadata/rng_seed"][()]).item()) == 0
        mutated = tuple(
            name
            for name in _OBSERVABLES
            if name not in _PASS_THROUGH and name in trace["states_after"]
        )
        assert any(audit_trace_mutated_ticks(trace, mutated, n_ticks).values())
        # Diagnostic identity comparison is limited to recorded channels. A
        # missing intergenic family fails the separate completeness gate above.
        replay_recorded_channels(process, trace, n_ticks)
