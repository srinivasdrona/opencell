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
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_karr_vector,
    project_observable_from_state,
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

from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess

_TRACE_PROCESS_NAME = "ProteinTranslocation"
_OBSERVABLES = ('substrates', 'enzymes', 'boundEnzymes', 'monomers')

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({'boundEnzymes', 'enzymes'})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {'substrates': 'substrate_wids', 'enzymes': 'enzyme_wids', 'boundEnzymes': 'enzyme_wids', 'monomers': 'monomer_wids'}


_CANONICAL_WIDS: dict[str, list[str]] = {}
_STORE_PATH_OVERRIDE: dict[str, tuple[str, ...]] = {
    'monomers': ('protein', 'compartment_counts', 'processed_i')
}
_INDEX_PROJECTION_ATTR: dict[str, str] = {}
_INDEX_PROJECTION_LITERAL = {'monomers': np.arange(2892)}
_COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrProteinTranslocationProcess,
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
    _assert_identity_or_tolerance_shared(
        tick=tick,
        observable=observable,
        oc_after=oc_after,
        karr_after=karr_after,
    )


def _snap_integral_counts(*, tick: int, observable: str, label: str, values: np.ndarray) -> np.ndarray:
    rounded = np.rint(values)
    if np.array_equal(rounded, values):
        return rounded.astype(np.float64)
    frac = np.abs(values - rounded)
    if np.all(frac < 1e-9):
        return rounded.astype(np.float64)
    bad = int(np.flatnonzero(frac >= 1e-9)[0])
    pytest.fail(
        "L2a non-integral count: "
        f"tick={tick}, observable={observable}, source={label}, "
        f"index={bad}, value={float(values[bad])}"
    )


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_protein_translocation_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.fail(
                "L2.1 failure: no-op trace. Claimed active F trace produced zero mutated ticks "
                f"across all {n_ticks} ticks: {mutated_tick_counts}."
            )

        process = KarrProteinTranslocationProcess({"rng_seed": int(rng_seed)})
        state_template = build_state_template(process)

        canonical_wids = dict(_CANONICAL_WIDS)
        canonical_wids["monomers"] = [
            f"{wid}[{comp}]" for comp in _COMPARTMENTS for wid in process.monomer_wids
        ]

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
                canonical_wids_override=canonical_wids,
            )

        mismatch_ticks: set[int] = set()
        karr_active_ticks: list[int] = []
        total_oc_c_leave = 0
        total_oc_e_arrive = 0
        total_oc_m_arrive = 0
        total_karr_c_leave = 0
        total_karr_e_arrive = 0
        total_karr_m_arrive = 0

        for tick in range(n_ticks):
            state = build_state_template(process)
            # Ensure processed_i compartment counts container exists
            comp_store = state.setdefault("protein", {}).setdefault("compartment_counts", {}).setdefault("processed_i", {})
            for wid in getattr(process, "translocatable_wids", []):
                if wid not in comp_store:
                    comp_store[wid] = {c: 0.0 for c in _COMPARTMENTS}

            before_vectors = {
                observable: project_karr_vector(
                    process,
                    observable,
                    cell_vector(trace, "states_before", observable, tick),
                    index_projection_attr=_INDEX_PROJECTION_ATTR,
                    index_projection_literal=_INDEX_PROJECTION_LITERAL,
                )
                for observable in _OBSERVABLES
            }

            for observable in _OBSERVABLES:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                    store_path_override=_STORE_PATH_OVERRIDE,
                )
            refresh_allocator_views(process, state)

            update = process.next_update(1.0, state)

            before_monomers = _snap_integral_counts(
                tick=tick,
                observable="monomers",
                label="before",
                values=before_vectors["monomers"],
            )

            # Check Karr active ticks and conservation
            karr_monomers_after = project_karr_vector(
                process,
                "monomers",
                cell_vector(trace, "states_after", "monomers", tick),
                index_projection_attr=_INDEX_PROJECTION_ATTR,
                index_projection_literal=_INDEX_PROJECTION_LITERAL,
            )
            karr_diff = karr_monomers_after - before_monomers
            if np.any(karr_diff != 0):
                karr_active_ticks.append(tick)
                assert bool(update), f"Active tick {tick} in Karr trace produced empty update from OC process"
                assert int(round(float(np.sum(karr_diff)))) == 0, f"Tick {tick}: Karr total monomers not conserved"
                n_monomers = len(process.monomer_wids)
                total_karr_c_leave += int(round(float(np.sum(karr_diff[0 * n_monomers : 1 * n_monomers]))))
                total_karr_e_arrive += int(round(float(np.sum(karr_diff[2 * n_monomers : 3 * n_monomers]))))
                total_karr_m_arrive += int(round(float(np.sum(karr_diff[3 * n_monomers : 4 * n_monomers]))))

            _apply_update(state, update, process)

            for observable in _OBSERVABLES:
                karr_after = project_karr_vector(
                    process,
                    observable,
                    cell_vector(trace, "states_after", observable, tick),
                    index_projection_attr=_INDEX_PROJECTION_ATTR,
                    index_projection_literal=_INDEX_PROJECTION_LITERAL,
                )
                expected_len = len(wids_by_observable[observable])
                if karr_after.shape[0] != expected_len:
                    mapped_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable, "<heuristic>")
                    pytest.fail(
                        "L2a wid-length drift: "
                        f"tick={tick}, observable={observable}, "
                        f"karr_len={karr_after.shape[0]}, "
                        f"mapped_len={expected_len}, mapped_attr={mapped_attr}"
                    )

                oc_after_raw = project_observable_from_state(
                    process=process,
                    state=state,
                    observable=observable,
                    wids=wids_by_observable[observable],
                    bound_enzymes_before=before_vectors.get("boundEnzymes"),
                    store_path_override=_STORE_PATH_OVERRIDE,
                )
                oc_after = _snap_integral_counts(
                    tick=tick,
                    observable=observable,
                    label="oc_after",
                    values=oc_after_raw,
                )
                karr_after = _snap_integral_counts(
                    tick=tick,
                    observable=observable,
                    label="karr_after",
                    values=karr_after,
                )

                if observable in _PASS_THROUGH:
                    _assert_identity_or_tolerance(
                        tick=tick,
                        observable=observable,
                        oc_after=oc_after,
                        karr_after=karr_after,
                    )
                    continue

                if not np.array_equal(oc_after, karr_after):
                    mismatch_ticks.add(tick)
                if observable == "monomers":
                    oc_diff = oc_after - before_monomers
                    assert int(round(float(np.sum(oc_diff)))) == 0, f"Tick {tick}: OC total monomers not conserved"
                    n_monomers = len(process.monomer_wids)
                    total_oc_c_leave += int(round(float(np.sum(oc_diff[0 * n_monomers : 1 * n_monomers]))))
                    total_oc_e_arrive += int(round(float(np.sum(oc_diff[2 * n_monomers : 3 * n_monomers]))))
                    total_oc_m_arrive += int(round(float(np.sum(oc_diff[3 * n_monomers : 4 * n_monomers]))))

        assert len(karr_active_ticks) == 13, (
            f"Expected 13 active ticks in Karr trace, got {len(karr_active_ticks)}: {karr_active_ticks}"
        )
        assert total_karr_c_leave == -17, f"Expected -17 Karr cytosol departures, got {total_karr_c_leave}"
        assert total_karr_e_arrive == 4, f"Expected +4 Karr extracellular arrivals, got {total_karr_e_arrive}"
        assert total_karr_m_arrive == 13, f"Expected +13 Karr membrane arrivals, got {total_karr_m_arrive}"

        assert total_oc_c_leave == -17, f"Expected -17 OC cytosol departures, got {total_oc_c_leave}"
        assert total_oc_e_arrive == 4, f"Expected +4 OC extracellular arrivals, got {total_oc_e_arrive}"
        assert total_oc_m_arrive == 13, f"Expected +13 OC membrane arrivals, got {total_oc_m_arrive}"

        assert len(mismatch_ticks) == 0, (
            f"ProteinTranslocation replay drift on ticks: {sorted(mismatch_ticks)}"
        )
