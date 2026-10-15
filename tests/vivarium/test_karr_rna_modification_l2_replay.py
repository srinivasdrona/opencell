"""Full-347-form, source-before-only RM replay; canonical no-op is N/A."""

from pathlib import Path

import h5py
import numpy as np
import pytest
from _rna_replay_inputs import (
    assert_source_family_coverage,
    prove_trace_inputs,
    replay_recorded_channels,
)
from l2_replay_common import audit_trace_mutated_ticks, resolve_trace_path

from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes", "modifiedRNAs", "unmodifiedRNAs")
_PASS_THROUGH = frozenset({"enzymes", "boundEnzymes"})
_SCRATCH_RESET = {
    "_rng": "karr-persistent",
    "_n_completed": "per-tick-scratch (production resets on every update)",
}
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
    "unmodifiedRNAs": "processed_rna_wids",
    "modifiedRNAs": "mature_rna_wids",
}


def _resolve_event_trace_path(seed):
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/RNAModification_100ticks.mat"
    )
    candidates = [_REPO_ROOT / rel, Path("E:/opencell") / rel, Path("/mnt/e/opencell") / rel]
    return next((path for path in candidates if path.exists()), candidates[0])


def _trace_path(event):
    path = _resolve_event_trace_path(0) if event else resolve_trace_path("RNAModification")
    assert path.exists(), f"required existing RM trace unavailable: {path}"
    return path


@pytest.mark.parametrize("event", [False, True], ids=["canonical", "event"])
def test_source_before_inputs_roundtrip_all_ticks(event):
    process = KarrRNAModificationProcess({"rng_seed": 0})
    with h5py.File(_trace_path(event), "r") as trace:
        prove_trace_inputs(process, trace, 100)


@pytest.mark.parametrize("event", [False, True], ids=["canonical", "event"])
def test_source_output_families_are_recorded(event):
    with h5py.File(_trace_path(event), "r") as trace:
        assert_source_family_coverage(KarrRNAModificationProcess(), trace)


def _run_replay(event):
    process = KarrRNAModificationProcess({"rng_seed": 0})
    with h5py.File(_trace_path(event), "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).item())
        assert n_ticks == 100
        assert int(np.asarray(trace["metadata/rng_seed"][()]).item()) == 0
        prove_trace_inputs(process, trace, n_ticks)
        mutated = audit_trace_mutated_ticks(
            trace, tuple(name for name in _OBSERVABLES if name not in _PASS_THROUGH), n_ticks
        )
        if not any(mutated.values()):
            pytest.skip(f"L2.1 N/A: no-op RM trace, not positive coverage: {mutated}")
        # One persistent stochastic process across all ticks; no RNG reset.
        replay_recorded_channels(process, trace, n_ticks)


def test_karr_rna_modification_l2_replay_identity_per_tick():
    _run_replay(False)


def test_karr_rna_modification_l2_event_replay():
    _run_replay(True)
