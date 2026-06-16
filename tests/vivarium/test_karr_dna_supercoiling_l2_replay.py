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
    overlay_trace_after_hint,
    project_observable_from_state,
    refresh_allocator_views,
)
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess

_TRACE_PROCESS_NAME = "DNASupercoiling"
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes")
_PASS_THROUGH = frozenset({"boundEnzymes", "enzymes"})
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
}


def _resolve_seed_trace_path(process_name: str, rng_seed: int) -> Path:
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_s{int(rng_seed):03d}/{process_name}_100ticks.mat"
    )
    candidates = [
        _REPO_ROOT / rel,
        Path("/mnt/e/opencell") / rel,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing chromosome replay trace at {candidates!r}")


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


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


def _chromosome_store_for_tick(trace: h5py.File, group: str, tick: int) -> ChromosomeStore:
    dataset = trace[f"{group}/chromosome"]
    ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
    return ChromosomeStore.from_hdf5_group(trace[ref])


def _scalar_sigma_from_store(
    process: KarrDNASupercoilingProcess,
    store: ChromosomeStore,
) -> float:
    polymerized = store.get_field("polymerizedRegions")
    positive_regions = process._positive_ds_regions(polymerized)
    linking_values = process._align_positive_region_values(
        positive_regions=positive_regions,
        linking_numbers=store.get_field("linkingNumbers"),
        fallback_sigma=process.equilibrium_sigma,
    )
    sigma_values = process._region_sigmas(
        positive_regions=positive_regions,
        linking_values=linking_values,
    )
    return process._weighted_sigma(
        positive_regions=positive_regions,
        sigma_values=sigma_values,
    )


def _replication_state_for_store(
    process: KarrDNASupercoilingProcess,
    store: ChromosomeStore,
) -> str:
    if len(process._positive_ds_regions(store.get_field("polymerizedRegions"))) > 1:
        return "elongating"
    return "idle"


def _overlay_chromosome_state(
    process: KarrDNASupercoilingProcess,
    state: dict[str, object],
    store: ChromosomeStore,
) -> None:
    sigma = _scalar_sigma_from_store(process, store)
    chrom_state = state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")
    chrom_state.update(store.to_state())
    chrom_state["supercoil_density"] = float(sigma)
    chrom_state["supercoiled"] = bool(sigma < 0.0)
    chrom_state["replication_state"] = _replication_state_for_store(process, store)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrDNASupercoilingProcess,
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
    if "linkingNumbers" in chrom_update:
        chrom_state["linkingNumbers"] = SparseTriplet.from_state(
            chrom_update["linkingNumbers"],
            shape=process.chromosome_shape,
        ).to_state()
    if "supercoil_density" in chrom_update:
        chrom_state["supercoil_density"] = float(chrom_update["supercoil_density"])
    if "supercoiled" in chrom_update:
        chrom_state["supercoiled"] = bool(chrom_update["supercoiled"])
    if "replication_state" in chrom_update:
        chrom_state["replication_state"] = str(chrom_update["replication_state"])


@pytest.mark.parametrize("rng_seed", [1], ids=["rng_seed_1"])
def test_karr_dna_supercoiling_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = _resolve_seed_trace_path(_TRACE_PROCESS_NAME, rng_seed)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100
        recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
        assert recorded_seed == int(rng_seed)
        assert "chromosome" in trace["states_before"]
        assert "chromosome" in trace["states_after"]

        mutated_obs = tuple(observable for observable in _OBSERVABLES if observable not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                "L2.1 N/A: no-op trace. Every mutated observable "
                f"({list(mutated_obs)}) is identical between states_before and "
                f"states_after across all {n_ticks} ticks. Per-observable "
                f"nonzero-delta counts: {mutated_tick_counts}."
            )

        process = KarrDNASupercoilingProcess({"rng_seed": int(rng_seed)})
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

        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vectors = {
                observable: cell_vector(trace, "states_before", observable, tick)
                for observable in _OBSERVABLES
            }
            after_vectors = {
                observable: cell_vector(trace, "states_after", observable, tick)
                for observable in _OBSERVABLES
            }
            before_store = _chromosome_store_for_tick(trace, "states_before", tick)
            after_store = _chromosome_store_for_tick(trace, "states_after", tick)

            for observable in _OBSERVABLES:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                )
            for observable in ("enzymes", "boundEnzymes", "substrates"):
                if observable in _OBSERVABLES:
                    overlay_trace_after_hint(
                        state=state,
                        observable=observable,
                        vector=after_vectors[observable],
                        wids=wids_by_observable[observable],
                    )
            _overlay_chromosome_state(process, state, before_store)
            state.setdefault("trace_hint", {})["chromosome_next"] = after_store.to_state()
            refresh_allocator_views(process, state)

            update = process.next_update(1.0, state)
            _apply_update(state, update, process)

            for observable in _OBSERVABLES:
                karr_after = after_vectors[observable]
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

            oc_linking = SparseTriplet.from_state(
                state["chromosome"]["linkingNumbers"],
                shape=process.chromosome_shape,
            )
            expected_linking = after_store.get_field("linkingNumbers")
            assert np.array_equal(oc_linking.positions, expected_linking.positions)
            assert np.array_equal(oc_linking.strands, expected_linking.strands)
            assert np.array_equal(oc_linking.values, expected_linking.values)
            assert float(state["chromosome"]["supercoil_density"]) == pytest.approx(
                _scalar_sigma_from_store(process, after_store),
                abs=1e-9,
            )
