"""FOLLOWUP7 DNAS branch-ledger audit for the frozen N=200 checkpoint.

This script keeps Design-A's per-tick state isolation intact: every replayed
tick is rebuilt from the Karr `states_before` snapshot while only the
process-local RNG stream persists within each biological seed.

The output ledger focuses on each seed's first sparse-support divergence and
records the OC branch activity that produced it alongside the event counts that
are directly inferable from Karr `states_before` / `states_after`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

import _l2_2_design_a_runner_helpers as helpers  # noqa: E402
from l2_replay_common import (  # noqa: E402
    apply_count_update,
    build_state_template,
    overlay_observable_into_state,
    refresh_allocator_views,
)
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.util.matlab_rng import MatlabRandStream  # noqa: E402
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess  # noqa: E402
from scripts.l22_dnas_rare_event.evaluate_checkpoint import _load_tensor_checkpoint  # noqa: E402
from scripts.l22_dnas_rare_event.sparse_gate import support_counts  # noqa: E402

PROCESS = "DNASupercoiling"
DEFAULT_CHECKPOINT = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "evidence_bundle"
    / "DNASupercoiling"
    / "diagnostic_n200_followup"
    / "post_sigma_fix_rerun"
    / "raw_captured_tensors_checkpoint.npz"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "evidence_bundle"
    / "DNASupercoiling"
    / "diagnostic_n200_followup"
    / "post_sigma_fix_rerun"
    / "FOLLOWUP7_LEDGER.json"
)

TRACKED_WIDS = ("ATP", "ADP", "PI", "H2O", "H")
RNG_PROBE_SEED = 0
RNG_PROBE_TICK = 5


def _coerce_cli_path(raw: str | Path) -> Path:
    text = str(raw)
    if len(text) >= 3 and text[1:3] in {":/", ":\\"}:
        win = PureWindowsPath(text)
        drive = str(win.drive).rstrip(":").lower()
        tail = Path(*win.parts[1:])
        return Path("/mnt") / drive / tail
    return Path(text)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _projection(before: ChromosomeStore, after: ChromosomeStore) -> dict[str, float]:
    return {
        "linkingNumbers.delta_value_sum": float(
            helpers._chromosome_projection_component(  # noqa: SLF001
                "linkingNumbers.delta_value_sum", before, after
            )
        ),
        "linkingNumbers.delta_nnz": float(
            helpers._chromosome_projection_component(  # noqa: SLF001
                "linkingNumbers.delta_nnz", before, after
            )
        ),
    }


def _enzyme_names(process: KarrDNASupercoilingProcess) -> tuple[str, ...]:
    return tuple(str(wid) for wid in process.enzyme_wids)


def _tracked_substrate_indexes(process: KarrDNASupercoilingProcess) -> dict[str, int]:
    indexes = {
        process.atp_wid: int(process.substrate_index_atp),
        process.adp_wid: int(process.substrate_index_adp),
        process.pi_wid: int(process.substrate_index_pi),
        process.h2o_wid: int(process.substrate_index_h2o),
    }
    if process.h_wid is not None:
        indexes[process.h_wid] = int(process.substrate_wids.index(process.h_wid))
    return indexes


def _substrate_snapshot(
    process: KarrDNASupercoilingProcess,
    vector: np.ndarray,
) -> dict[str, float]:
    flat = np.asarray(vector, dtype=np.float64).reshape(-1)
    indexes = _tracked_substrate_indexes(process)
    return {
        wid: float(flat[idx])
        for wid, idx in indexes.items()
        if wid in TRACKED_WIDS and 0 <= idx < flat.size
    }


def _substrate_delta(
    process: KarrDNASupercoilingProcess,
    before: np.ndarray,
    after: np.ndarray,
) -> dict[str, float]:
    before_snapshot = _substrate_snapshot(process, before)
    after_snapshot = _substrate_snapshot(process, after)
    return {
        wid: float(after_snapshot.get(wid, 0.0) - before_snapshot.get(wid, 0.0))
        for wid in sorted(set(before_snapshot) | set(after_snapshot))
    }


def _enzyme_vector_snapshot(
    process: KarrDNASupercoilingProcess,
    vector: np.ndarray,
) -> dict[str, float]:
    flat = np.asarray(vector, dtype=np.float64).reshape(-1)
    return {
        str(wid): float(flat[idx])
        for idx, wid in enumerate(process.enzyme_wids)
        if idx < flat.size
    }


def _bound_site_counts_by_enzyme(
    process: KarrDNASupercoilingProcess,
    store: ChromosomeStore,
) -> dict[str, int]:
    counts = {wid: 0 for wid in process.enzyme_wids}
    for enzyme_idx, wid in enumerate(process.enzyme_wids):
        field_name = process._bound_site_field_name(enzyme_idx)  # noqa: SLF001
        triplet = store.get_field(field_name)
        if triplet.positions.size == 0:
            continue
        enzyme_global_idx = int(process.enzyme_global_indices[enzyme_idx])
        counts[str(wid)] = int(
            np.count_nonzero(triplet.values.astype(np.int64, copy=False) == enzyme_global_idx)
        )
    return counts


def _stable_binding_count_map(
    process: KarrDNASupercoilingProcess,
    ledger: dict[str, Any],
) -> dict[str, int]:
    counts = {wid: 0 for wid in process.enzyme_wids}
    for wid, payload in ledger.get("stable_binding_by_enzyme", {}).items():
        counts[str(wid)] = int(payload.get("n_bound", 0))
    return counts


def classify_branch_mismatch(
    *,
    oc_ledger: dict[str, Any],
    karr_ledger: dict[str, Any],
) -> str:
    oc_proj = oc_ledger["delta_projection"]
    karr_proj = karr_ledger["delta_projection"]
    if (
        float(oc_proj["linkingNumbers.delta_value_sum"])
        == float(karr_proj["linkingNumbers.delta_value_sum"])
        and float(oc_proj["linkingNumbers.delta_nnz"])
        != float(karr_proj["linkingNumbers.delta_nnz"])
    ):
        return "projection_structure_only"

    oc_stable = oc_ledger.get("stable_binding_by_enzyme", {}).get("MG_203_204_TETRAMER", {})
    if int(oc_stable.get("n_bound", 0)) > 0:
        karr_before_topoiv = int(
            karr_ledger["bound_site_counts_before"].get("MG_203_204_TETRAMER", 0)
        )
        karr_after_topoiv = int(
            karr_ledger["bound_site_counts_after"].get("MG_203_204_TETRAMER", 0)
        )
        if karr_before_topoiv == 0 and karr_after_topoiv == 0:
            return "candidate_count_or_binding_occupancy_topoiv"

    oc_release = oc_ledger.get("release_counts_by_enzyme", {})
    if float(oc_release.get("DNA_GYRASE", 0.0)) > 0.0 or float(
        oc_release.get("MG_203_204_TETRAMER", 0.0)
    ) > 0.0:
        return "enzyme_release_or_ownership"

    oc_activity = oc_ledger.get("activity_events_total_by_enzyme", {})
    karr_delta = karr_ledger.get("substrate_delta", {})
    if any(int(value) > 0 for value in oc_activity.values()) and float(
        karr_delta.get("ATP", 0.0)
    ) != 0.0:
        return "source_probabilities_or_rng"

    return "unclassified_sparse_branch"


class RecordingRng:
    """Wrap an RNG object and record per-tick draw calls without changing state."""

    def __init__(self, base: Any, *, include_results: bool = False) -> None:
        self.base = base
        self.include_results = bool(include_results)
        self.calls: list[dict[str, Any]] = []

    def random(self, size: int | tuple[int, ...] | None = None) -> Any:
        result = self.base.random(size)
        self.calls.append(
            {
                "kind": "random",
                "size": None if size is None else _json_default(np.asarray(size)),
                "result_size": int(np.asarray(result).size),
            }
        )
        return result

    def permutation(self, n: int) -> np.ndarray:
        result = np.asarray(self.base.permutation(int(n)), dtype=np.int64)
        payload = {
            "kind": "permutation",
            "n": int(n),
            "result_size": int(result.size),
            "result_head": result[: min(8, result.size)].tolist(),
        }
        if self.include_results:
            payload["result"] = result.tolist()
        self.calls.append(payload)
        return result

    def choice(self, a: int, p: np.ndarray | None = None) -> int:
        result = int(self.base.choice(a, p=p))
        payload: dict[str, Any] = {
            "kind": "choice",
            "a": int(a),
            "result": int(result),
        }
        if p is None:
            payload["weights"] = None
        else:
            probs = np.asarray(p, dtype=np.float64)
            payload["weights_size"] = int(probs.size)
            payload["weights_nonzero"] = int(np.count_nonzero(probs))
            payload["weights_head"] = probs[: min(8, probs.size)].round(12).tolist()
            if self.include_results:
                payload["weights"] = probs.round(12).tolist()
        self.calls.append(
            payload
        )
        return result

    def poisson(self, lam: float) -> int:
        result = int(self.base.poisson(float(lam)))
        self.calls.append(
            {
                "kind": "poisson",
                "lam": float(lam),
                "result": int(result),
            }
        )
        return result


class MatlabCompatRng:
    """Minimal MATLAB-stream adapter for focused branch probes."""

    def __init__(self, seed: int) -> None:
        self._stream = MatlabRandStream(int(seed))

    def random(self, size: int | tuple[int, ...] | None = None) -> Any:
        if size is None:
            return float(self._stream.rand())
        if isinstance(size, tuple):
            return np.asarray(self._stream.rand(*size), dtype=np.float64)
        return np.asarray(self._stream.rand(int(size)), dtype=np.float64)

    def permutation(self, n: int) -> np.ndarray:
        return np.asarray(self._stream.randperm(int(n)), dtype=np.int64) - 1

    def choice(self, a: int, p: np.ndarray | None = None) -> int:
        if p is None:
            return int(math.floor(float(self._stream.rand()) * int(a)))
        probs = np.asarray(p, dtype=np.float64)
        total = float(probs.sum())
        if total <= 0.0:
            raise ValueError("choice probabilities must sum to a positive value")
        probs = probs / total
        draw = float(self._stream.rand())
        idx = int(np.searchsorted(np.cumsum(probs), draw, side="right"))
        return min(idx, len(probs) - 1)

    def poisson(self, lam: float) -> int:
        lam_f = float(lam)
        if lam_f <= 0.0:
            return 0
        stop = math.exp(-lam_f)
        k = 0
        prod = 1.0
        while prod > stop:
            k += 1
            prod *= float(self._stream.rand())
        return k - 1


@contextmanager
def sibling_trace_root(trace_root: Path):
    """Temporarily redirect helper seed-path resolution to a sibling trace root."""

    original_root = helpers._karr_native_root  # noqa: SLF001
    original_candidate_roots = helpers._karr_native_candidate_roots  # noqa: SLF001

    def _root() -> Path:
        return trace_root

    def _candidate_roots(process_name: str) -> tuple[Path, ...]:
        del process_name
        return (trace_root,)

    helpers._karr_native_root = _root  # type: ignore[assignment]  # noqa: SLF001
    helpers._karr_native_candidate_roots = _candidate_roots  # type: ignore[assignment]  # noqa: SLF001
    try:
        yield
    finally:
        helpers._karr_native_root = original_root  # type: ignore[assignment]  # noqa: SLF001
        helpers._karr_native_candidate_roots = original_candidate_roots  # type: ignore[assignment]  # noqa: SLF001


def _resolve_trace_root(candidate: Path | None) -> Path:
    if candidate is not None:
        resolved = _coerce_cli_path(candidate).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Trace root does not exist: {resolved}")
        return resolved

    probes = [
        REPO_ROOT / "data" / "m1_sources" / "karr_native",
        Path("/mnt/e/opencell-worktrees/l22-dnas-closure-20260805/data/m1_sources/karr_native"),
        Path("/mnt/e/opencell-worktrees/l22-depth200/data/m1_sources/karr_native"),
    ]
    for probe in probes:
        if probe.exists():
            return probe
    raise FileNotFoundError("Could not resolve a DNAS trace root from the default candidates.")


def _seed_paths(trace_root: Path, seeds: list[int]) -> list[Path]:
    with sibling_trace_root(trace_root):
        return [helpers._v2_seed_mat_path(PROCESS, int(seed)) for seed in seeds]  # noqa: SLF001


def _seed_summary_from_checkpoint(
    oc_tensor: np.ndarray,
    karr_tensor: np.ndarray,
    seed: int,
) -> dict[str, Any]:
    oc_seed = np.asarray(oc_tensor[seed], dtype=np.float64)
    karr_seed = np.asarray(karr_tensor[seed], dtype=np.float64)
    diff_mask = np.any(~np.isclose(oc_seed, karr_seed, atol=0.0, rtol=0.0), axis=1)
    sparse_diff_mask = ~np.isclose(oc_seed[:, 1], karr_seed[:, 1], atol=0.0, rtol=0.0)
    event_ticks_oc = [int(t) for t in np.flatnonzero(oc_seed[:, 1] != 0)]
    event_ticks_karr = [int(t) for t in np.flatnonzero(karr_seed[:, 1] != 0)]
    first_div_tick = int(np.flatnonzero(diff_mask)[0]) if np.any(diff_mask) else None
    first_sparse_div_tick = int(np.flatnonzero(sparse_diff_mask)[0]) if np.any(sparse_diff_mask) else None
    return {
        "seed": int(seed),
        "oc_nonzero_ticks": event_ticks_oc,
        "karr_nonzero_ticks": event_ticks_karr,
        "oc_event_count": int(len(event_ticks_oc)),
        "karr_event_count": int(len(event_ticks_karr)),
        "first_divergence_tick": first_div_tick,
        "first_sparse_divergence_tick": first_sparse_div_tick,
        "first_divergence_projection_oc": oc_seed[first_div_tick].tolist() if first_div_tick is not None else None,
        "first_divergence_projection_karr": (
            karr_seed[first_div_tick].tolist() if first_div_tick is not None else None
        ),
        "first_sparse_divergence_projection_oc": (
            oc_seed[first_sparse_div_tick].tolist() if first_sparse_div_tick is not None else None
        ),
        "first_sparse_divergence_projection_karr": (
            karr_seed[first_sparse_div_tick].tolist() if first_sparse_div_tick is not None else None
        ),
    }


def _apply_chromosome_update(
    before: ChromosomeStore,
    chrom_update: dict[str, Any] | None,
) -> ChromosomeStore:
    new_state = before.to_state()
    if isinstance(chrom_update, dict):
        for field_name, value in chrom_update.items():
            if field_name not in new_state:
                continue
            if isinstance(value, dict) and "positions" in value:
                new_state[field_name] = SparseTriplet.from_state(value, shape=before.shape).to_state()
    return ChromosomeStore.from_state_mapping(new_state, shape=before.shape)


def _overlay_chromosome(runtime_state: dict[str, Any], store: ChromosomeStore) -> None:
    chrom_state = runtime_state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be a dict")
    chrom_state.update(store.to_state())


def _positive_region_ledger(
    process: KarrDNASupercoilingProcess,
    store: ChromosomeStore,
    state: dict[str, Any],
) -> tuple[list[tuple[int, int, int]], np.ndarray, np.ndarray, np.ndarray]:
    polymerized = process._ensure_polymerized_regions(store.get_field("polymerizedRegions"))  # noqa: SLF001
    positive_regions = process._positive_ds_regions(polymerized)  # noqa: SLF001
    sigma_fallback = float(state.get("chromosome", {}).get("supercoil_density", process.equilibrium_sigma))
    linking_numbers = store.get_field("linkingNumbers")
    positive_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=linking_numbers,
        fallback_sigma=sigma_fallback,
    )
    sigma_values = process._region_sigmas(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_values=positive_values,
    )
    legal = np.zeros((len(positive_regions), len(process.enzyme_wids)), dtype=bool)
    if sigma_values.size:
        legal[:, process.gyrase_idx] = sigma_values > process.gyrase_sigma_limit
        legal[:, process.topoiv_idx] = sigma_values > process.topoiv_sigma_limit
        legal[:, process.topoi_idx] = sigma_values < process.topoi_sigma_limit
    return positive_regions, positive_values, sigma_values, legal


def _sample_state(
    *,
    process: KarrDNASupercoilingProcess,
    before_channels: dict[str, np.ndarray],
    seed_index: int,
    tick: int,
    chrom_before: ChromosomeStore,
) -> dict[str, Any]:
    return {
        "substrate_wids": list(process.substrate_wids),
        "enzyme_wids": list(process.enzyme_wids),
        "oracle_before_substrates": np.asarray(
            before_channels["substrates"][seed_index, tick], dtype=np.float64
        ),
        "oracle_before_enzymes": np.asarray(
            before_channels["enzymes"][seed_index, tick], dtype=np.float64
        ),
        "oracle_before_bound_enzymes": np.asarray(
            before_channels["boundEnzymes"][seed_index, tick], dtype=np.float64
        ),
        "oracle_before_chromosome_store": chrom_before,
    }


def _record_tick_ledger(
    *,
    process: KarrDNASupercoilingProcess,
    sample_state: dict[str, Any],
    rng_variant: str,
    record_rng_results: bool = False,
) -> dict[str, Any]:
    runtime_state = build_state_template(process)
    substrate_wids = list(sample_state["substrate_wids"])
    enzyme_wids = list(sample_state["enzyme_wids"])
    before_substrates = np.asarray(sample_state["oracle_before_substrates"], dtype=np.float64)
    before_enzymes = np.asarray(sample_state["oracle_before_enzymes"], dtype=np.float64)
    before_bound_enzymes = np.asarray(sample_state["oracle_before_bound_enzymes"], dtype=np.float64)
    chrom_store_before: ChromosomeStore = sample_state["oracle_before_chromosome_store"]

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=before_substrates,
        wids=substrate_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=before_enzymes,
        wids=enzyme_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="boundEnzymes",
        vector=before_bound_enzymes,
        wids=enzyme_wids,
    )
    _overlay_chromosome(runtime_state, chrom_store_before)
    refresh_allocator_views(process, runtime_state)

    positive_regions, positive_values, sigma_values, legal = _positive_region_ledger(
        process,
        chrom_store_before,
        runtime_state,
    )

    base_rng = getattr(process, "_rng")
    if isinstance(base_rng, RecordingRng):
        base_rng = base_rng.base
    recording_rng = RecordingRng(base_rng, include_results=record_rng_results)
    process._rng = recording_rng  # type: ignore[assignment]  # noqa: SLF001

    ledger: dict[str, Any] = {
        "rng_variant": str(rng_variant),
        "incoming_free_pools": _enzyme_vector_snapshot(process, before_enzymes),
        "incoming_bound_pools": _enzyme_vector_snapshot(process, before_bound_enzymes),
        "incoming_bound_site_counts": _bound_site_counts_by_enzyme(process, chrom_store_before),
        "substrates_before": _substrate_snapshot(process, before_substrates),
        "positive_regions": [
            {"start": int(start), "strand": int(strand), "length": int(length)}
            for start, strand, length in positive_regions
        ],
        "positive_linking_values_before": np.asarray(positive_values, dtype=np.int64).tolist(),
        "sigma_values_before": np.asarray(sigma_values, dtype=np.float64).tolist(),
        "legal_region_counts_by_enzyme": {
            str(wid): int(np.count_nonzero(legal[:, enzyme_idx]))
            for enzyme_idx, wid in enumerate(process.enzyme_wids)
        },
        "release_counts_by_enzyme": {},
        "transient_binding_by_enzyme": {},
        "stable_binding_by_enzyme": {},
    }

    original_release = process._release_bound_enzyme_from_chromosome  # noqa: SLF001
    original_transient = process._calculate_transient_binding  # noqa: SLF001
    original_stable = process._bind_protein_to_chromosome_stochastically  # noqa: SLF001
    original_activity = process._sample_activity_events_by_region  # noqa: SLF001

    def _wrapped_release(*, store: ChromosomeStore, enzyme_idx: int, release_rate: float, dt: float, protected_regions: list[tuple[int, int, int]]) -> tuple[ChromosomeStore, float]:
        store_next, released = original_release(
            store=store,
            enzyme_idx=enzyme_idx,
            release_rate=release_rate,
            dt=dt,
            protected_regions=protected_regions,
        )
        ledger["release_counts_by_enzyme"][str(process.enzyme_wids[enzyme_idx])] = float(released)
        return store_next, released

    def _wrapped_transient(*, store: ChromosomeStore, enzyme_idx: int, positive_regions: list[tuple[int, int, int]], legal_mask: np.ndarray, available_count: float) -> np.ndarray:
        result = np.asarray(
            original_transient(
                store=store,
                enzyme_idx=enzyme_idx,
                positive_regions=positive_regions,
                legal_mask=legal_mask,
                available_count=available_count,
            ),
            dtype=np.float64,
        )
        ledger["transient_binding_by_enzyme"][str(process.enzyme_wids[enzyme_idx])] = {
            "available_count": float(available_count),
            "binding_by_region": result.tolist(),
        }
        return result

    def _wrapped_stable(*, store: ChromosomeStore, enzyme_idx: int, available_count: float, positive_regions: list[tuple[int, int, int]]) -> tuple[ChromosomeStore, Any]:
        accessible = process._accessible_binding_regions(  # noqa: SLF001
            store=store,
            enzyme_idx=enzyme_idx,
            positive_regions=positive_regions,
        )
        footprint = int(process._enzyme_footprint(enzyme_idx))  # noqa: SLF001
        candidate_sites = int(
            sum(max(0, int(length) - footprint + 1) for _, _, length in accessible)
        )
        store_next, binding_result = original_stable(
            store=store,
            enzyme_idx=enzyme_idx,
            available_count=available_count,
            positive_regions=positive_regions,
        )
        ledger["stable_binding_by_enzyme"][str(process.enzyme_wids[enzyme_idx])] = {
            "available_count": float(available_count),
            "candidate_sites": int(candidate_sites),
            "legal_regions": [
                {"start": int(start), "strand": int(strand), "length": int(length)}
                for start, strand, length in positive_regions
            ],
            "accessible_regions": [
                {"start": int(start), "strand": int(strand), "length": int(length)}
                for start, strand, length in accessible
            ],
            "n_bound": int(binding_result.n_bound),
            "released_monomers": np.asarray(binding_result.released_monomers, dtype=np.int64).tolist(),
            "released_complexes": np.asarray(binding_result.released_complexes, dtype=np.int64).tolist(),
            "side_effects": [
                {
                    "molecule_kind": effect.molecule_kind,
                    "global_index": int(effect.global_index),
                    "mature_delta": int(effect.mature_delta),
                    "bound_delta": int(effect.bound_delta),
                }
                for effect in binding_result.side_effects
            ],
        }
        return store_next, binding_result

    def _wrapped_activity(*, store: ChromosomeStore, positive_regions: list[tuple[int, int, int]], sigma_values: np.ndarray, legal: np.ndarray, topoi_transient: np.ndarray, available_atp: float, available_h2o: float, dt: float) -> tuple[np.ndarray, float]:
        events, atp_used = original_activity(
            store=store,
            positive_regions=positive_regions,
            sigma_values=sigma_values,
            legal=legal,
            topoi_transient=topoi_transient,
            available_atp=available_atp,
            available_h2o=available_h2o,
            dt=dt,
        )
        event_matrix = np.asarray(events, dtype=np.int64)
        ledger["activity_events_by_region_enzyme"] = [
            {
                "region_index": int(region_idx),
                "start": int(start),
                "strand": int(strand),
                "length": int(length),
                "sigma": float(sigma_values[region_idx]),
                "events_by_enzyme": {
                    str(wid): int(event_matrix[region_idx, enzyme_idx])
                    for enzyme_idx, wid in enumerate(process.enzyme_wids)
                },
            }
            for region_idx, (start, strand, length) in enumerate(positive_regions)
        ]
        ledger["activity_events_total_by_enzyme"] = {
            str(wid): int(event_matrix[:, enzyme_idx].sum())
            for enzyme_idx, wid in enumerate(process.enzyme_wids)
        }
        ledger["activity_atp_h2o_used"] = float(atp_used)
        return events, atp_used

    process._release_bound_enzyme_from_chromosome = _wrapped_release  # type: ignore[assignment]  # noqa: SLF001
    process._calculate_transient_binding = _wrapped_transient  # type: ignore[assignment]  # noqa: SLF001
    process._bind_protein_to_chromosome_stochastically = _wrapped_stable  # type: ignore[assignment]  # noqa: SLF001
    process._sample_activity_events_by_region = _wrapped_activity  # type: ignore[assignment]  # noqa: SLF001

    try:
        update = process.next_update(1.0, runtime_state)
    finally:
        process._release_bound_enzyme_from_chromosome = original_release  # type: ignore[assignment]  # noqa: SLF001
        process._calculate_transient_binding = original_transient  # type: ignore[assignment]  # noqa: SLF001
        process._bind_protein_to_chromosome_stochastically = original_stable  # type: ignore[assignment]  # noqa: SLF001
        process._sample_activity_events_by_region = original_activity  # type: ignore[assignment]  # noqa: SLF001
        process._rng = recording_rng.base  # type: ignore[assignment]  # noqa: SLF001

    apply_count_update(runtime_state, update)
    chrom_after_store = _apply_chromosome_update(
        chrom_store_before,
        update.get("chromosome", {}) if isinstance(update, dict) else {},
    )
    ledger["rng_calls"] = recording_rng.calls
    ledger["outgoing_free_pools"] = {
        wid: float(runtime_state.get("enzymes", {}).get(wid, 0.0))
        for wid in enzyme_wids
    }
    ledger["outgoing_bound_pools"] = {
        wid: float(runtime_state.get("boundEnzymes", {}).get(wid, 0.0))
        for wid in enzyme_wids
    }
    ledger["outgoing_bound_site_counts"] = _bound_site_counts_by_enzyme(process, chrom_after_store)
    ledger["substrate_delta_emitted"] = {
        wid: float(update.get("substrates", {}).get(wid, 0.0))
        for wid in sorted(update.get("substrates", {}))
    }
    ledger["substrates_after"] = {
        wid: float(runtime_state.get("substrates", {}).get(wid, 0.0))
        for wid in TRACKED_WIDS
        if wid in runtime_state.get("substrates", {})
    }
    ledger["delta_projection"] = _projection(chrom_store_before, chrom_after_store)
    return ledger


def _karr_tick_ledger(
    *,
    process: KarrDNASupercoilingProcess,
    before_channels: dict[str, np.ndarray],
    after_channels: dict[str, np.ndarray],
    seed_index: int,
    tick: int,
    before_store: ChromosomeStore,
    after_store: ChromosomeStore,
) -> dict[str, Any]:
    before_substrates = np.asarray(before_channels["substrates"][seed_index, tick], dtype=np.float64)
    after_substrates = np.asarray(after_channels["substrates"][seed_index, tick], dtype=np.float64)
    ledger: dict[str, Any] = {
        "free_pools_before": _enzyme_vector_snapshot(process, before_channels["enzymes"][seed_index, tick]),
        "bound_pools_before": _enzyme_vector_snapshot(
            process, before_channels["boundEnzymes"][seed_index, tick]
        ),
        "bound_site_counts_before": _bound_site_counts_by_enzyme(process, before_store),
        "bound_site_counts_after": _bound_site_counts_by_enzyme(process, after_store),
        "substrates_before": _substrate_snapshot(process, before_substrates),
        "substrates_after": _substrate_snapshot(process, after_substrates),
        "substrate_delta": _substrate_delta(process, before_substrates, after_substrates),
        "delta_projection": _projection(before_store, after_store),
    }
    if "enzymes" in after_channels:
        ledger["free_pools_after"] = _enzyme_vector_snapshot(process, after_channels["enzymes"][seed_index, tick])
    if "boundEnzymes" in after_channels:
        ledger["bound_pools_after"] = _enzyme_vector_snapshot(
            process, after_channels["boundEnzymes"][seed_index, tick]
        )
    return ledger


def _first_sparse_rows(
    *,
    loaded_checkpoint: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    oc_tensor = np.asarray(loaded_checkpoint["oc_tensor"], dtype=np.float64)
    karr_tensor = np.asarray(loaded_checkpoint["karr_tensor"], dtype=np.float64)
    per_seed = [
        _seed_summary_from_checkpoint(oc_tensor, karr_tensor, int(seed))
        for seed in range(int(oc_tensor.shape[0]))
    ]
    same_delta = 0
    different_delta = 0
    for seed_idx in range(int(oc_tensor.shape[0])):
        for tick in range(int(oc_tensor.shape[1])):
            if float(oc_tensor[seed_idx, tick, 1]) == float(karr_tensor[seed_idx, tick, 1]):
                continue
            if float(oc_tensor[seed_idx, tick, 0]) == float(karr_tensor[seed_idx, tick, 0]):
                same_delta += 1
            else:
                different_delta += 1
    return per_seed, int(same_delta), int(different_delta)


def _probe_matlab_rng(
    *,
    before_channels: dict[str, np.ndarray],
    chrom_before_by_seed: dict[int, list[ChromosomeStore]],
) -> dict[str, Any]:
    process_current = KarrDNASupercoilingProcess({"rng_seed": int(RNG_PROBE_SEED)})
    process_matlab = KarrDNASupercoilingProcess({"rng_seed": int(RNG_PROBE_SEED)})
    process_matlab._rng = MatlabCompatRng(int(RNG_PROBE_SEED))  # type: ignore[assignment]  # noqa: SLF001

    target_tick = int(RNG_PROBE_TICK)
    current_ledger: dict[str, Any] | None = None
    matlab_ledger: dict[str, Any] | None = None
    stores = chrom_before_by_seed[int(RNG_PROBE_SEED)]
    for tick in range(target_tick + 1):
        state_current = _sample_state(
            process=process_current,
            before_channels=before_channels,
            seed_index=int(RNG_PROBE_SEED),
            tick=tick,
            chrom_before=stores[tick],
        )
        state_matlab = _sample_state(
            process=process_matlab,
            before_channels=before_channels,
            seed_index=int(RNG_PROBE_SEED),
            tick=tick,
            chrom_before=stores[tick],
        )
        current_ledger = _record_tick_ledger(
            process=process_current,
            sample_state=state_current,
            rng_variant="current",
        )
        matlab_ledger = _record_tick_ledger(
            process=process_matlab,
            sample_state=state_matlab,
            rng_variant="matlab_probe",
        )
    assert current_ledger is not None
    assert matlab_ledger is not None
    return {
        "seed": int(RNG_PROBE_SEED),
        "tick": int(target_tick),
        "current_topoiv_n_bound": int(
            current_ledger["stable_binding_by_enzyme"]
            .get("MG_203_204_TETRAMER", {})
            .get("n_bound", 0)
        ),
        "matlab_topoiv_n_bound": int(
            matlab_ledger["stable_binding_by_enzyme"]
            .get("MG_203_204_TETRAMER", {})
            .get("n_bound", 0)
        ),
        "current_projection": current_ledger["delta_projection"],
        "matlab_projection": matlab_ledger["delta_projection"],
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--trace-root", default=None)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--seeds",
        default=None,
        help="Comma-separated seed indexes to audit. Default: all checkpoint seeds.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=10,
        help="Print progress after every N audited seeds. Default: 10.",
    )
    return parser.parse_args(argv)


def _parse_seed_filter(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    entries = [part.strip() for part in str(raw).split(",")]
    seeds = [int(part) for part in entries if part]
    if not seeds:
        raise ValueError("--seeds must contain at least one integer seed index")
    return seeds


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    checkpoint_path = _coerce_cli_path(args.checkpoint).resolve()
    trace_root = _resolve_trace_root(None if args.trace_root is None else Path(args.trace_root))
    out_path = _coerce_cli_path(args.out).resolve()
    selected_seeds = _parse_seed_filter(args.seeds)

    loaded_checkpoint = _load_tensor_checkpoint(checkpoint_path)
    oc_tensor = np.asarray(loaded_checkpoint["oc_tensor"], dtype=np.float64)
    karr_tensor = np.asarray(loaded_checkpoint["karr_tensor"], dtype=np.float64)
    if oc_tensor.shape != karr_tensor.shape:
        raise ValueError(f"OC/Karr tensor shape mismatch: {oc_tensor.shape} vs {karr_tensor.shape}")
    if oc_tensor.ndim != 3 or oc_tensor.shape[2] != 2:
        raise ValueError(f"Expected (seed, tick, 2) tensor, got {oc_tensor.shape}")

    per_seed, same_delta_count, different_delta_count = _first_sparse_rows(
        loaded_checkpoint=loaded_checkpoint
    )
    if selected_seeds is not None:
        selected = set(selected_seeds)
        per_seed = [row for row in per_seed if int(row["seed"]) in selected]
    seeds = [int(row["seed"]) for row in per_seed]
    if not seeds:
        raise ValueError("No seeds selected for FOLLOWUP7 ledger audit.")
    seed_paths = _seed_paths(trace_root, seeds)
    with sibling_trace_root(trace_root):
        before_channels, after_channels, n_ticks = helpers._load_seeded_mat_channels(  # noqa: SLF001
            seed_paths,
            process_name=PROCESS,
        )
        chromosome_oracle = helpers.load_chromosome_oracle_for_process(PROCESS, seeds, n_ticks)

    sample_process = KarrDNASupercoilingProcess({"rng_seed": 0})
    chrom_before_by_seed = {
        int(seed): chromosome_oracle["before_stores"][seed_idx]
        for seed_idx, seed in enumerate(seeds)
    }
    chrom_after_by_seed = {
        int(seed): chromosome_oracle["after_stores"][seed_idx]
        for seed_idx, seed in enumerate(seeds)
    }

    classification_counts: dict[str, int] = {}
    hypothesis_counts = {
        "candidate_count_or_binding_occupancy": 0,
        "projection_structure_only": 0,
        "enzyme_release_or_ownership": 0,
        "source_probabilities_or_rng": 0,
        "unclassified_sparse_branch": 0,
    }
    enriched_rows: list[dict[str, Any]] = []
    for seed_pos, seed_row in enumerate(per_seed, start=1):
        seed = int(seed_row["seed"])
        tick = seed_row["first_sparse_divergence_tick"]
        if tick is None:
            enriched_rows.append(seed_row)
            continue

        process = KarrDNASupercoilingProcess({"rng_seed": int(seed)})
        oc_ledger: dict[str, Any] | None = None
        for replay_tick in range(int(tick) + 1):
            sample_state = _sample_state(
                process=process,
                before_channels=before_channels,
                seed_index=seed,
                tick=replay_tick,
                chrom_before=chrom_before_by_seed[seed][replay_tick],
            )
            oc_ledger = _record_tick_ledger(
                process=process,
                sample_state=sample_state,
                rng_variant="current",
                record_rng_results=(
                    seed == int(RNG_PROBE_SEED) and replay_tick == int(RNG_PROBE_TICK)
                ),
            )
        assert oc_ledger is not None

        karr_ledger = _karr_tick_ledger(
            process=sample_process,
            before_channels=before_channels,
            after_channels=after_channels,
            seed_index=seed,
            tick=int(tick),
            before_store=chrom_before_by_seed[seed][int(tick)],
            after_store=chrom_after_by_seed[seed][int(tick)],
        )
        classification = classify_branch_mismatch(
            oc_ledger=oc_ledger,
            karr_ledger=karr_ledger,
        )
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        if classification in hypothesis_counts:
            hypothesis_counts[classification] += 1

        enriched = dict(seed_row)
        enriched["first_sparse_divergence_tick"] = int(tick)
        enriched["oc_first_sparse_ledger"] = oc_ledger
        enriched["karr_first_sparse_ledger"] = karr_ledger
        enriched["first_sparse_divergence_classification"] = classification
        enriched_rows.append(enriched)
        if int(args.log_every) > 0 and seed_pos % int(args.log_every) == 0:
            print(
                "[l22_dnas_followup7_ledger] progress "
                f"{seed_pos}/{len(per_seed)} seeds audited; latest seed={seed} "
                f"class={classification} tick={tick}"
            )

    oc_sparse = support_counts(oc_tensor[:, :, 1])
    karr_sparse = support_counts(karr_tensor[:, :, 1])
    matlab_rng_probe = None
    if int(RNG_PROBE_SEED) in chrom_before_by_seed:
        matlab_rng_probe = _probe_matlab_rng(
            before_channels=before_channels,
            chrom_before_by_seed=chrom_before_by_seed,
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "process": PROCESS,
        "checkpoint_path": str(checkpoint_path),
        "trace_root": str(trace_root),
        "tensor_shape": list(oc_tensor.shape),
        "component_scales": loaded_checkpoint["component_scales"],
        "sparse_support": {
            "oc": {
                "pooled_nonzero_ticks": int(oc_sparse.pooled_nonzero_ticks),
                "active_seeds": int(oc_sparse.active_seeds),
                "clustered_seeds": int(oc_sparse.clustered_seeds),
            },
            "karr": {
                "pooled_nonzero_ticks": int(karr_sparse.pooled_nonzero_ticks),
                "active_seeds": int(karr_sparse.active_seeds),
                "clustered_seeds": int(karr_sparse.clustered_seeds),
            },
        },
        "sparse_diff_breakdown": {
            "delta_nnz_diff_same_delta_value_sum": int(same_delta_count),
            "delta_nnz_diff_different_delta_value_sum": int(different_delta_count),
        },
        "source_parameter_snapshot": {
            "gyrase_activity_rate": float(sample_process.gyrase_activity_rate),
            "topoiv_activity_rate": float(sample_process.topoiv_activity_rate),
            "topoi_activity_rate": float(sample_process.topoi_activity_rate),
            "gyrase_sigma_limit": float(sample_process.gyrase_sigma_limit),
            "topoiv_sigma_limit": float(sample_process.topoiv_sigma_limit),
            "topoi_sigma_limit": float(sample_process.topoi_sigma_limit),
            "gyrase_atp_cost": float(sample_process.gyrase_atp_cost),
            "topoiv_atp_cost": float(sample_process.topoiv_atp_cost),
            "topoi_atp_cost": float(sample_process.topoi_atp_cost),
        },
        "matlab_rng_probe": matlab_rng_probe,
        "first_sparse_divergence_classification_counts": classification_counts,
        "hypothesis_counts": hypothesis_counts,
        "per_seed": enriched_rows,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    print(f"[l22_dnas_followup7_ledger] wrote {out_path}")
    print(
        "[l22_dnas_followup7_ledger] sparse-support "
        f"oc(active={oc_sparse.active_seeds}, pooled={oc_sparse.pooled_nonzero_ticks}, clustered={oc_sparse.clustered_seeds}) "
        f"karr(active={karr_sparse.active_seeds}, pooled={karr_sparse.pooled_nonzero_ticks}, clustered={karr_sparse.clustered_seeds})"
    )
    print(
        "[l22_dnas_followup7_ledger] first-sparse classes "
        + ", ".join(f"{key}={value}" for key, value in sorted(classification_counts.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
