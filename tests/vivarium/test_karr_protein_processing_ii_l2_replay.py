from __future__ import annotations

import sys
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
from scipy.io import loadmat

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
    apply_count_update,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    refresh_allocator_views,
    resolve_trace_path,
)
from l2_replay_common import (
    assert_delta_integral as _assert_delta_integral_shared,
)
from l2_replay_common import (
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
)
from l2_replay_common import (
    audit_trace_mutated_ticks as _audit_trace_mutated_ticks_shared,
)

from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.protein_state import COMPARTMENTS, MIGRATED_WIDS

_TRACE_PROCESS_NAME = "ProteinProcessingII"
_OBSERVABLES = (
    "substrates", "enzymes", "boundEnzymes", "processedMonomers",
    "unprocessedMonomers", "signalSequenceMonomers",
)
_SOURCE_MUTATED_OBSERVABLES = frozenset({
    "substrates", "processedMonomers", "unprocessedMonomers", "signalSequenceMonomers",
})

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({'boundEnzymes', 'enzymes'})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {"_rng": "karr-persistent"}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
    "processedMonomers": "processed_monomer_wids",
    "unprocessedMonomers": "unprocessed_monomer_wids",
    "signalSequenceMonomers": "signal_sequence_monomer_wids",
}


@cache
def _ppii_fixture() -> Any:
    return loadmat(
        _REPO_ROOT / "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture


def _ppii_locations(observable: str) -> list[tuple[str, tuple[str, ...]]]:
    """PP2-only copyFromState/copyToState projection, never an evolution helper.

    ProteinProcessingII.m:199-268 owns processed-I/II at monomerCompartments
    and signal sequences in cytosol. Process.m:611-670 owns mature/bound
    enzymes at enzymeMonomerCompartmentIndexs. For nonmigrated WIDs, PP1's
    processed_counts is processed-I; Folding's unfolded_counts is processed-II.
    Neither aliases the mature counts pool or migrates chassis state.
    """
    fixture = _ppii_fixture()
    if observable == "substrates":
        return [
            (str(wid), ("substrates", str(wid)))
            for wid in fixture.substrateWholeCellModelIDs
        ]
    if observable in {"enzymes", "boundEnzymes"}:
        form = "mature" if observable == "enzymes" else "bound"
        return [
            (str(wid), ("protein", "compartment_counts", form, str(wid),
                        COMPARTMENTS[int(comp) - 1]))
            for wid, comp in zip(
                fixture.enzymeWholeCellModelIDs, fixture.enzymeMonomerCompartmentIndexs,
                strict=True,
            )
        ]
    form, legacy, field = {
        "unprocessedMonomers": ("processed_i", "processed_counts", "unprocessedMonomerWholeCellModelIDs"),
        "processedMonomers": ("processed_ii", "unfolded_counts", "processedMonomerWholeCellModelIDs"),
        "signalSequenceMonomers": (
            "signal_sequence", "signal_sequence_counts", "signalSequenceMonomerWholeCellModelIDs",
        ),
    }[observable]
    locations = []
    for index, raw_wid in enumerate(getattr(fixture, field)):
        wid = str(raw_wid)
        if wid in MIGRATED_WIDS:
            compartment = "c" if form == "signal_sequence" else (
                COMPARTMENTS[int(fixture.monomerCompartments[index]) - 1]
            )
            path = ("protein", "compartment_counts", form, wid, compartment)
        else:
            path = ("protein", legacy, wid)
        locations.append((wid, path))
    return locations


def _ppii_state_from_before(
    process: KarrProteinProcessingIIProcess,
    before_vectors: dict[str, np.ndarray],
    wids_by_observable: dict[str, list[str]],
) -> dict[str, Any]:
    """Overlay only captured inputs, without filling migrated compatibility shadows."""
    state = build_state_template(process)
    for observable, vector in before_vectors.items():
        locations = _ppii_locations(observable)
        assert wids_by_observable[observable] == [wid for wid, _ in locations], (
            f"PP2 fixture WID-order mismatch: {observable}"
        )
        assert np.asarray(vector).shape == (len(locations),), (
            f"PP2 captured input length mismatch: {observable}"
        )
        for (_, path), value in zip(locations, vector, strict=True):
            node = state
            for key in path[:-1]:
                node = node.setdefault(key, {})
            node[path[-1]] = float(value)
    refresh_allocator_views(process, state)
    return state


def _project_ppii_observable(
    process: KarrProteinProcessingIIProcess, state: dict[str, Any], observable: str,
) -> np.ndarray:
    if observable in {"unprocessedMonomers", "enzymes"}:
        precursors, enzymes = process.read_processing_inputs(state)
        return precursors if observable == "unprocessedMonomers" else enzymes
    values = []
    for _, path in _ppii_locations(observable):
        node: Any = state
        for key in path:
            node = node.get(key, 0.0) if isinstance(node, dict) else 0.0
        values.append(float(node))
    return np.asarray(values, dtype=np.float64)


def test_ppii_captured_before_projection_matches_production_source_reader() -> None:
    process = KarrProteinProcessingIIProcess({"rng_seed": 0})
    rng_before = deepcopy(process._rng.bit_generator.state)
    wids = {obs: [wid for wid, _ in _ppii_locations(obs)] for obs in _OBSERVABLES}
    migrated_indices = [
        i for i, wid in enumerate(process.unprocessed_monomer_wids) if wid in MIGRATED_WIDS
    ]
    active_migrated_ticks = 0
    with h5py.File(resolve_trace_path(_TRACE_PROCESS_NAME), "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        for tick in range(n_ticks):
            before = {obs: cell_vector(trace, "states_before", obs, tick) for obs in _OBSERVABLES}
            state = _ppii_state_from_before(process, before, wids)
            # This is the actual reader called by both calculate_request and next_update.
            precursors, enzymes = process.read_processing_inputs(state)
            np.testing.assert_array_equal(
                precursors, before["unprocessedMonomers"], err_msg=f"PP2 precursor input tick={tick}"
            )
            np.testing.assert_array_equal(
                enzymes, before["enzymes"], err_msg=f"PP2 live enzyme input tick={tick}"
            )
            for obs in _OBSERVABLES:
                np.testing.assert_array_equal(
                    _project_ppii_observable(process, state, obs), before[obs],
                    err_msg=f"PP2 source input tick={tick}, observable={obs}",
                )
            for branch in ("counts", "processed_counts", "unprocessed_counts"):
                assert not set(state["protein"].get(branch, {})) & set(MIGRATED_WIDS)
            assert all(value == 0 for value in state["protein"]["enzyme_counts"].values())
            active_migrated_ticks += bool(np.any(precursors[migrated_indices] > 0))
    assert active_migrated_ticks > 0, "input regression must exercise migrated precursors"
    assert process._rng.bit_generator.state == rng_before, "input projection must not consume RNG"


def test_ppii_projection_preserves_absent_and_nonmigrated_input_contracts() -> None:
    process = KarrProteinProcessingIIProcess({"rng_seed": 0})
    state = _ppii_state_from_before(process, {}, {})
    state["protein"]["enzyme_counts"] = dict(
        zip(process.enzyme_wids, np.asarray(_ppii_fixture().enzymes).reshape(-1), strict=True)
    )
    precursors, enzymes = process.read_processing_inputs(state)
    np.testing.assert_array_equal(precursors, np.zeros(len(process.unprocessed_monomer_wids)))
    np.testing.assert_array_equal(enzymes, np.zeros(len(process.enzyme_wids)))

    # Synthetic precursor at the existing PP1-owned processed-I queue, not mature counts.
    before = np.zeros(len(process.unprocessed_monomer_wids))
    index = next(i for i, wid in enumerate(process.unprocessed_monomer_wids) if wid not in MIGRATED_WIDS)
    before[index] = 1
    state = _ppii_state_from_before(
        process, {"unprocessedMonomers": before},
        {"unprocessedMonomers": process.unprocessed_monomer_wids},
    )
    actual, _ = process.read_processing_inputs(state)
    np.testing.assert_array_equal(actual, before)
    wid = process.unprocessed_monomer_wids[index]
    assert state["protein"]["processed_counts"][wid] == 1
    assert wid not in state["protein"].get("counts", {})
    assert wid not in state["protein"]["compartment_counts"]["processed_i"]


def _assert_ppii_coverage(trace: h5py.File, observables: tuple[str, ...]) -> None:
    observed = set(observables)
    before = set(trace["states_before"])
    after = set(trace["states_after"])
    missing_before = _SOURCE_MUTATED_OBSERVABLES - before
    missing_after = _SOURCE_MUTATED_OBSERVABLES - after
    assert not missing_before and not missing_after, (
        "MISSING_EVIDENCE: canonical PP2 oracle lacks source output families; "
        f"states_before missing={sorted(missing_before)}, states_after missing={sorted(missing_after)}. "
        "Signal conservation unit tests are not captured signal-sequence replay evidence. "
        "No alternate cohort selected or expected signal counts fabricated."
    )
    assert len(observables) == len(observed)
    assert observed == before == after, (
        "PP2 replay observation set must equal captured before/after families; "
        f"observed={sorted(observed)}, before={sorted(before)}, after={sorted(after)}"
    )
    assert observed >= _SOURCE_MUTATED_OBSERVABLES
    assert observed >= _PASS_THROUGH


def test_ppii_canonical_oracle_covers_all_source_output_families() -> None:
    with h5py.File(resolve_trace_path(_TRACE_PROCESS_NAME), "r") as trace:
        _assert_ppii_coverage(trace, _OBSERVABLES)


@pytest.mark.parametrize("omitted", ["signalSequenceMonomers", "boundEnzymes"])
def test_ppii_coverage_rejects_six_channel_file_with_five_channel_loop(omitted: str) -> None:
    observed = tuple(obs for obs in _OBSERVABLES if obs != omitted)
    with (
        h5py.File(resolve_trace_path(_TRACE_PROCESS_NAME), "r") as trace,
        pytest.raises(AssertionError, match="observation set"),
    ):
        _assert_ppii_coverage(trace, observed)


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrProteinProcessingIIProcess,
) -> None:
    del process  # state is rebuilt per tick; only delta application is needed here.
    for label, deltas in collect_count_delta_dicts(update):
        _assert_delta_integral(label, deltas)
    apply_count_update(state, update)


def _audit_trace_mutated_ticks(
    trace: h5py.File,
    observables: tuple[str, ...],
    n_ticks: int,
) -> dict[str, int]:
    return _audit_trace_mutated_ticks_shared(trace, observables, n_ticks)


def _assert_identity_or_tolerance(
    *,
    tick: int,
    observable: str,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
) -> None:
    for label, values in (("oracle", karr_after), ("oc", oc_after)):
        if not np.array_equal(values, np.rint(values)):
            index = int(np.flatnonzero(values != np.rint(values))[0])
            pytest.fail(
                f"L2a {label} non-integral: tick={tick}, observable={observable}, "
                f"index={index}, value={values[index]}"
            )
    _assert_identity_or_tolerance_shared(
        tick=tick,
        observable=observable,
        oc_after=oc_after,
        karr_after=karr_after,
    )
    # The shared helper's optional calibrated mode cannot relax this exact replay.
    np.testing.assert_array_equal(oc_after, karr_after)


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_protein_processing_ii_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        _assert_ppii_coverage(trace, _OBSERVABLES)
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                "L2.1 N/A: no-op trace. Every mutated observable "
                f"({list(mutated_obs)}) is identical between states_before and "
                f"states_after across all {n_ticks} ticks. Per-observable "
                f"nonzero-delta counts: {mutated_tick_counts}."
            )

        process = KarrProteinProcessingIIProcess({"rng_seed": int(rng_seed)})
        state_template = build_state_template(process)
        emitted_tick_counts = {obs: 0 for obs in mutated_obs}
        signal_emissions = 0.0

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
            )

        for tick in range(n_ticks):
            before_vectors = {
                observable: cell_vector(trace, "states_before", observable, tick)
                for observable in _OBSERVABLES
            }

            state = _ppii_state_from_before(process, before_vectors, wids_by_observable)

            update = process.next_update(1.0, state)
            _apply_update(state, update, process)

            for observable in _OBSERVABLES:
                karr_after = cell_vector(trace, "states_after", observable, tick)
                expected_len = len(wids_by_observable[observable])
                if karr_after.shape[0] != expected_len:
                    mapped_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable, "<heuristic>")
                    pytest.fail(
                        "L2a wid-length drift: "
                        f"tick={tick}, observable={observable}, "
                        f"karr_len={karr_after.shape[0]}, "
                        f"mapped_len={expected_len}, mapped_attr={mapped_attr}"
                    )

                oc_after = _project_ppii_observable(process, state, observable)
                _assert_identity_or_tolerance(
                    tick=tick,
                    observable=observable,
                    oc_after=oc_after,
                    karr_after=karr_after,
                )
                if observable in emitted_tick_counts:
                    delta = oc_after - before_vectors[observable]
                    emitted_tick_counts[observable] += bool(np.any(delta != 0))
                    if observable == "signalSequenceMonomers":
                        signal_emissions += float(delta.sum())
        assert all(count > 0 for count in emitted_tick_counts.values()), emitted_tick_counts
        assert signal_emissions > 0, "replay must exercise actual nonzero signal emission"
        print(f"PP2 executed mutation ticks={emitted_tick_counts}; signal emissions={signal_emissions}")
