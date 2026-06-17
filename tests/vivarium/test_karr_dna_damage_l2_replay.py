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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (
    apply_count_update,
    assert_delta_integral as _assert_delta_integral_shared,
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
    audit_trace_mutated_ticks as _audit_trace_mutated_ticks_shared,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
    resolve_trace_path,
)
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess

_TRACE_PROCESS_NAME = "DNADamage"
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes")
_SPARSE_FIELDS = (
    "damagedBases",
    "strandBreaks",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "intrastrandCrossLinks",
)
_MAPPED_FIELDS = ("intrastrandCrossLinks", "damagedBases", "abasicSites")

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({"boundEnzymes", "enzymes"})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
}


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _chromosome_store_for_tick(trace: h5py.File, group: str, tick: int) -> ChromosomeStore:
    dataset = trace[f"{group}/chromosome"]
    ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
    return ChromosomeStore.from_hdf5_group(trace[ref])


def _overlay_chromosome_state(state: dict[str, object], store: ChromosomeStore) -> None:
    chrom_state = state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")
    chrom_state.update(store.to_state())


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrDNADamageProcess,
) -> None:
    for label, deltas in collect_count_delta_dicts(update):
        _assert_delta_integral(label, deltas)
    apply_count_update(state, update)

    chrom_update = update.get("chromosome", {})
    if not isinstance(chrom_update, dict):
        return
    chrom_state = state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")

    if "damage_events_cumulative" in chrom_update:
        existing = chrom_state.get("damage_events_cumulative", [])
        if not isinstance(existing, list):
            existing = []
        existing.extend(list(chrom_update["damage_events_cumulative"]))
        chrom_state["damage_events_cumulative"] = existing
    if "repair_events_cumulative" in chrom_update:
        existing = chrom_state.get("repair_events_cumulative", [])
        if not isinstance(existing, list):
            existing = []
        existing.extend(list(chrom_update["repair_events_cumulative"]))
        chrom_state["repair_events_cumulative"] = existing
    if "replication_stall_flag" in chrom_update:
        chrom_state["replication_stall_flag"] = float(
            float(chrom_state.get("replication_stall_flag", 0.0))
            + float(chrom_update["replication_stall_flag"])
        )
    if "replication_state" in chrom_update:
        chrom_state["replication_state"] = str(chrom_update["replication_state"])
    if "fork_position_bp" in chrom_update:
        chrom_state["fork_position_bp"] = dict(chrom_update["fork_position_bp"])
    for field in _SPARSE_FIELDS:
        if field in chrom_update:
            chrom_state[field] = SparseTriplet.from_state(
                chrom_update[field],
                shape=process.chromosome_shape,
            ).to_state()


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
    _assert_identity_or_tolerance_shared(
        tick=tick,
        observable=observable,
        oc_after=oc_after,
        karr_after=karr_after,
    )


def _assert_sparse_field_valid(triplet: SparseTriplet, shape: tuple[int, int], *, tick: int, field: str) -> None:
    assert triplet.shape == shape, f"tick={tick} field={field} unexpected sparse shape {triplet.shape!r}"
    assert triplet.positions.size == triplet.strands.size == triplet.values.size
    if triplet.positions.size <= 0:
        return
    assert int(np.min(triplet.positions)) >= 0, f"tick={tick} field={field} has negative positions"
    assert int(np.max(triplet.positions)) < shape[0], f"tick={tick} field={field} out-of-bounds positions"
    assert int(np.min(triplet.strands)) >= 0, f"tick={tick} field={field} has negative strands"
    assert int(np.max(triplet.strands)) < shape[1], f"tick={tick} field={field} out-of-bounds strands"
    assert np.all(triplet.values >= 0), f"tick={tick} field={field} has negative values"


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_dna_damage_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        # Quiet-process guard: do not skip. Karr trace may be no-op across all
        # mutated observables, but we still want to assert OC's next_update is
        # also no-op (else OC silently drifting would never be caught).
        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        _ = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)

        has_chromosome_trace = (
            "chromosome" in trace.get("states_before", {})
            and "chromosome" in trace.get("states_after", {})
        )

        process = KarrDNADamageProcess({"rng_seed": int(rng_seed)})
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
            )

        oc_delta_totals = {field: 0 for field in _MAPPED_FIELDS}
        karr_delta_totals = {field: 0 for field in _MAPPED_FIELDS}

        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vectors = {
                observable: cell_vector(trace, "states_before", observable, tick)
                for observable in _OBSERVABLES
            }

            for observable in _OBSERVABLES:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                )
            if has_chromosome_trace:
                before_store = _chromosome_store_for_tick(trace, "states_before", tick)
                _overlay_chromosome_state(state, before_store)
            refresh_allocator_views(process, state)

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

                oc_after = project_observable_from_state(
                    process=process,
                    state=state,
                    observable=observable,
                    wids=wids_by_observable[observable],
                    bound_enzymes_before=before_vectors.get("boundEnzymes"),
                )
                _assert_identity_or_tolerance(
                    tick=tick,
                    observable=observable,
                    oc_after=oc_after,
                    karr_after=karr_after,
                )

            if has_chromosome_trace:
                before_store = _chromosome_store_for_tick(trace, "states_before", tick)
                after_store = _chromosome_store_for_tick(trace, "states_after", tick)
                oc_store = ChromosomeStore.from_state_mapping(
                    state.get("chromosome", {}),
                    shape=process.chromosome_shape,
                )
                for field in _MAPPED_FIELDS:
                    _assert_sparse_field_valid(
                        oc_store.get_field(field),
                        process.chromosome_shape,
                        tick=tick,
                        field=field,
                    )
                    _assert_sparse_field_valid(
                        after_store.get_field(field),
                        process.chromosome_shape,
                        tick=tick,
                        field=f"karr::{field}",
                    )
                    oc_delta = oc_store.calc_num_edges(field) - before_store.calc_num_edges(field)
                    karr_delta = after_store.calc_num_edges(field) - before_store.calc_num_edges(field)
                    assert oc_delta >= 0, f"tick={tick} field={field} unexpectedly removed damage in OC"
                    assert karr_delta >= 0, f"tick={tick} field={field} oracle removed damage unexpectedly"
                    oc_delta_totals[field] += int(oc_delta)
                    karr_delta_totals[field] += int(karr_delta)

        if has_chromosome_trace:
            for field in _MAPPED_FIELDS:
                if karr_delta_totals[field] > 0:
                    assert (
                        oc_delta_totals[field] > 0
                    ), f"no OC sparse mutations recorded for mapped field {field}"

