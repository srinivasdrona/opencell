from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TESTS_DIR = _REPO_ROOT / "tests" / "vivarium"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from _l2_2_design_a_runner_helpers import (  # noqa: E402
    _run_replication_initiation_tick,  # type: ignore
)
from l2_replay_common import (  # type: ignore  # noqa: E402
    apply_count_update,
    build_state_template,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
)
from l21_active_window_audit import (  # type: ignore  # noqa: E402
    _apply_non_count_updates,
    _build_context,
    _honest_replay,
    _inject_hidden_read_surface,
    _project_trace_vector,
    _recursive_update_nontrivial,
    _trace_activity_detail,
)

from opencell.state.chromosome_store import ChromosomeStore  # noqa: E402


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
        if math.isfinite(value):
            return value
        return str(value)
    return value


def _observable_delta_summary(before: np.ndarray, after: np.ndarray) -> dict[str, Any]:
    delta = after.astype(np.int64) - before.astype(np.int64)
    nz = np.flatnonzero(delta)
    preview = []
    for idx in nz[:8]:
        preview.append(
            {
                "index": int(idx),
                "before": int(before[idx]),
                "after": int(after[idx]),
                "delta": int(delta[idx]),
            }
        )
    return {
        "nonzero_count": int(nz.size),
        "delta_abs_sum": int(np.abs(delta).sum()),
        "preview": preview,
    }


def _mapping_subset(mapping: dict[str, Any], keys: list[str]) -> dict[str, float]:
    return {key: float(mapping.get(key, 0.0)) for key in keys}


def _dnaa_triplet_preview(process: Any, triplet: Any, limit: int = 20) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for entry_idx, (position, strand, value) in enumerate(
        zip(
            triplet.positions.tolist(),
            triplet.strands.tolist(),
            triplet.values.tolist(),
            strict=False,
        )
    ):
        counts = getattr(process, "_dnaa_counts_by_global_index", {}).get(int(value))
        if counts is None:
            continue
        site_idx = process._site_index_by_position.get(int(position))
        preview.append(
            {
                "entry_index": int(entry_idx),
                "position": int(position),
                "strand": int(strand),
                "value": int(value),
                "site_idx": None if site_idx is None else int(site_idx),
                "site_id": None if site_idx is None else str(process.index_to_site_id[int(site_idx)]),
                "counts": [int(counts[0]), int(counts[1])],
            }
        )
        if len(preview) >= limit:
            break
    return preview


def _dnaa_site_count_delta(
    process: Any,
    before_triplet: Any,
    after_triplet: Any,
) -> dict[str, int]:
    before_atp, before_adp, _ = process._resolve_bound_state_from_chromosome(
        complex_bound_sites=before_triplet,
        legacy_counts={},
    )
    after_atp, after_adp, _ = process._resolve_bound_state_from_chromosome(
        complex_bound_sites=after_triplet,
        legacy_counts={},
    )
    delta = np.sum((after_atp + after_adp) - (before_atp + before_adp), axis=1)
    return {
        str(process.index_to_site_id[int(idx)]): int(delta[int(idx)])
        for idx in np.flatnonzero(delta)
    }


def _release_order_site_id(process: Any, candidate_id: int) -> str:
    site_idx, copy_idx = process._decode_candidate_id(int(candidate_id))
    label = str(process.index_to_site_id[int(site_idx)])
    return f"{label}@copy{int(copy_idx) + 1}"


def _tick_diagnostic(process_name: str, trace_path: Path, target_tick: int) -> dict[str, Any]:
    with h5py.File(trace_path, "r") as handle:
        metadata = handle["metadata"]
        rng_seed_raw = np.asarray(metadata["rng_seed"][()]).reshape(-1)
        rng_seed = int(rng_seed_raw[0]) if rng_seed_raw.size else 0
        ctx = _build_context(name=process_name, rng_seed=rng_seed, handle=handle)
        process = ctx.process
        spec = ctx.spec

        state = build_state_template(process)
        before_vectors: dict[str, np.ndarray] = {}
        after_vectors: dict[str, np.ndarray] = {}
        for observable in spec.observables:
            before = _project_trace_vector(ctx, "states_before", observable, target_tick)
            after = _project_trace_vector(ctx, "states_after", observable, target_tick)
            before_vectors[observable] = before
            after_vectors[observable] = after
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=before,
                wids=ctx.wids_by_observable[observable],
                store_path_override=spec.store_path_override,
            )

        _inject_hidden_read_surface(ctx=ctx, state=state, tick=target_tick)
        refresh_allocator_views(process, state)
        trace_before_chromosome = ChromosomeStore.from_hdf5_group(
            handle[handle["states_before/chromosome"][0, target_tick]]
        )
        trace_after_chromosome = ChromosomeStore.from_hdf5_group(
            handle[handle["states_after/chromosome"][0, target_tick]]
        )

        substrate_keys = list(process.substrate_wids[:5])
        enzyme_keys = list(process.enzyme_wids[:4])
        dnaa_count_keys = ["R1", "R2", "R3", "R4", "R5"]
        chromosome_state = state.get("chromosome", {})
        dnaa_counts = chromosome_state.get("dnaa_complex_count", {})
        state_before_call = {
            "substrates": _mapping_subset(state.get("substrates", {}), substrate_keys),
            "enzymes": _mapping_subset(state.get("enzymes", {}), enzyme_keys),
            "boundEnzymes": _mapping_subset(state.get("boundEnzymes", {}), enzyme_keys),
            "protein_counts": _mapping_subset(state.get("protein", {}).get("counts", {}), enzyme_keys),
            "requests": _jsonable(state.get("requests", {})),
            "substrates_allocated": _jsonable(state.get("substrates_allocated", {})),
            "chromosome": {
                "replication_state": chromosome_state.get("replication_state"),
                "supercoiled": chromosome_state.get("supercoiled"),
                "dnaa_complex_count": {key: int(dnaa_counts.get(key, 0)) for key in dnaa_count_keys},
            },
        }
        update = process.next_update(1.0, state)
        active = _recursive_update_nontrivial(update)
        apply_count_update(state, update)
        _apply_non_count_updates(state, update)

        projected_after = {
            observable: project_observable_from_state(
                process=process,
                state=state,
                observable=observable,
                wids=ctx.wids_by_observable[observable],
                bound_enzymes_before=before_vectors.get("boundEnzymes"),
                store_path_override=spec.store_path_override,
            )
            for observable in spec.observables
        }

        observable_deltas = {
            observable: {
                "karr": _observable_delta_summary(before_vectors[observable], after_vectors[observable]),
                "oc": _observable_delta_summary(before_vectors[observable], projected_after[observable]),
            }
            for observable in spec.observables
        }

        process_state = {
            "free_dnaa_adp": int(getattr(process, "_free_dnaa_adp", 0)),
            "free_dnaa_atp": int(getattr(process, "_free_dnaa_atp", 0)),
            "bound_adp_sum": int(np.sum(getattr(process, "_bound_adp", np.zeros(0, dtype=np.int64)))),
            "bound_atp_sum": int(np.sum(getattr(process, "_bound_atp", np.zeros(0, dtype=np.int64)))),
        }

        return {
            "process_name": process_name,
            "trace_path": trace_path.as_posix(),
            "tick": int(target_tick),
            "karr_activity_detail": _jsonable(_trace_activity_detail(process_name, ctx, target_tick)),
            "oc_update_nontrivial": bool(active),
            "update": _jsonable(update),
            "state_before_call": state_before_call,
            "process_state_after_call": process_state,
            "trace_dnaa_site_delta": _jsonable(
                _dnaa_site_count_delta(
                    process,
                    trace_before_chromosome.get_field("complexBoundSites"),
                    trace_after_chromosome.get_field("complexBoundSites"),
                )
            ),
            "observable_deltas": observable_deltas,
        }


def _stateful_tick_diagnostic(process_name: str, trace_path: Path, target_tick: int) -> dict[str, Any]:
    with h5py.File(trace_path, "r") as handle:
        metadata = handle["metadata"]
        rng_seed_raw = np.asarray(metadata["rng_seed"][()]).reshape(-1)
        rng_seed = int(rng_seed_raw[0]) if rng_seed_raw.size else 0
        ctx = _build_context(name=process_name, rng_seed=rng_seed, handle=handle)
        process = ctx.process
        spec = ctx.spec
        rng_counters: dict[str, Any] = {
            "advance_count": 0,
            "stochastic_round_inputs": [],
            "weighted_samples": [],
        }

        original_advance = process._rng._advance

        def _counted_advance() -> float:
            rng_counters["advance_count"] += 1
            return original_advance()

        process._rng._advance = _counted_advance  # type: ignore[method-assign]

        original_stochastic_round = process._stochastic_round

        def _counted_stochastic_round(value: float) -> int:
            result = original_stochastic_round(value)
            rng_counters["stochastic_round_inputs"].append(
                {"value": float(value), "result": int(result)}
            )
            return result

        process._stochastic_round = _counted_stochastic_round  # type: ignore[method-assign]

        original_weighted_sample = process._weighted_sample_without_replacement

        def _counted_weighted_sample(indices: np.ndarray, weights: np.ndarray, n: int) -> np.ndarray:
            sample = original_weighted_sample(indices, weights, n)
            flat_weights = np.asarray(weights, dtype=np.float64).reshape(-1)
            rng_counters["weighted_samples"].append(
                {
                    "candidate_count": int(np.asarray(indices).size),
                    "n": int(n),
                    "all_equal": bool(flat_weights.size > 0 and np.all(flat_weights == flat_weights[0])),
                    "any_inf": bool(flat_weights.size > 0 and np.any(flat_weights >= np.finfo(np.float64).max)),
                    "sampled_indices": np.asarray(sample, dtype=np.int64).tolist(),
                }
            )
            return sample

        process._weighted_sample_without_replacement = _counted_weighted_sample  # type: ignore[method-assign]

        history: list[dict[str, Any]] = []
        target_payload: dict[str, Any] | None = None

        for tick in range(target_tick + 1):
            state = build_state_template(process)
            before_vectors: dict[str, np.ndarray] = {}
            after_vectors: dict[str, np.ndarray] = {}
            for observable in spec.observables:
                before = _project_trace_vector(ctx, "states_before", observable, tick)
                after = _project_trace_vector(ctx, "states_after", observable, tick)
                before_vectors[observable] = before
                after_vectors[observable] = after
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before,
                    wids=ctx.wids_by_observable[observable],
                    store_path_override=spec.store_path_override,
                )

            _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
            refresh_allocator_views(process, state)

            chromosome_store = process._resolve_chromosome_store(state.get("chromosome", {}))
            complex_bound_before = chromosome_store.get_field("complexBoundSites")
            bound_atp, bound_adp, blocked_sites = process._resolve_bound_state_from_chromosome(
                complex_bound_sites=complex_bound_before,
                legacy_counts=state.get("chromosome", {}).get("dnaa_complex_count", {}),
            )
            process._bound_atp = bound_atp.copy()
            process._bound_adp = bound_adp.copy()
            process._blocked_sites = blocked_sites.copy()
            release_order = process._matlab_find_order_dnaa_site_indices(complex_bound_before)
            tick_advance_before = int(rng_counters["advance_count"])
            tick_round_before = len(rng_counters["stochastic_round_inputs"])
            tick_sample_before = len(rng_counters["weighted_samples"])
            rng_state_before = int(getattr(process._rng, "_state", 0))
            update = process.next_update(1.0, state)
            rng_state_after = int(getattr(process._rng, "_state", 0))
            oc_active = bool(_recursive_update_nontrivial(update))
            karr_detail = _trace_activity_detail(process_name, ctx, tick)

            tick_summary = {
                "tick": int(tick),
                "rng_state_before": rng_state_before,
                "rng_state_after": rng_state_after,
                "rng_advances": int(rng_counters["advance_count"] - tick_advance_before),
                "oc_active": oc_active,
                "karr_active": bool(karr_detail is not None),
                "stochastic_rounds": _jsonable(
                    rng_counters["stochastic_round_inputs"][tick_round_before:]
                ),
                "weighted_samples": _jsonable(rng_counters["weighted_samples"][tick_sample_before:]),
                "release_order_site_ids": [
                    _release_order_site_id(process, int(candidate_id))
                    for candidate_id in np.asarray(release_order[:12], dtype=np.int64).tolist()
                ],
                "release_order_size": int(release_order.size),
            }
            history.append(tick_summary)

            if tick == target_tick:
                target_payload = {
                    "tick": int(tick),
                    "stateful_history": history,
                    "karr_activity_detail": _jsonable(karr_detail),
                    "oc_update_nontrivial": oc_active,
                    "update": _jsonable(update),
                    "dnaa_triplet_preview": _dnaa_triplet_preview(process, complex_bound_before),
                    "release_order_site_ids": tick_summary["release_order_site_ids"],
                    "release_order_size": tick_summary["release_order_size"],
                }

            apply_count_update(state, update)
            _apply_non_count_updates(state, update)

        if target_payload is None:
            raise ValueError(f"Failed to capture stateful tick payload for tick {target_tick}")
        return target_payload


def _scan_ticks(process_name: str, trace_path: Path) -> dict[str, Any]:
    with h5py.File(trace_path, "r") as handle:
        metadata = handle["metadata"]
        rng_seed_raw = np.asarray(metadata["rng_seed"][()]).reshape(-1)
        rng_seed = int(rng_seed_raw[0]) if rng_seed_raw.size else 0
        n_ticks_raw = np.asarray(metadata["n_ticks"][()]).reshape(-1)
        n_ticks = int(n_ticks_raw[0]) if n_ticks_raw.size else 0
        ctx = _build_context(name=process_name, rng_seed=rng_seed, handle=handle)
        process = ctx.process
        spec = ctx.spec

        first_silent_active_tick = None
        first_oc_active_tick = None
        karr_active_ticks = 0
        oc_active_ticks = 0
        oc_active_on_karr_active_ticks = 0
        tick_rows: list[dict[str, Any]] = []

        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vectors: dict[str, np.ndarray] = {}
            for observable in spec.observables:
                before = _project_trace_vector(ctx, "states_before", observable, tick)
                before_vectors[observable] = before
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before,
                    wids=ctx.wids_by_observable[observable],
                    store_path_override=spec.store_path_override,
                )
            _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
            refresh_allocator_views(process, state)

            update = process.next_update(1.0, state)
            oc_active = _recursive_update_nontrivial(update)
            if oc_active:
                oc_active_ticks += 1
                if first_oc_active_tick is None:
                    first_oc_active_tick = tick

            karr_detail = _trace_activity_detail(process_name, ctx, tick)
            karr_active = karr_detail is not None
            if karr_active:
                karr_active_ticks += 1
                if oc_active:
                    oc_active_on_karr_active_ticks += 1
                elif first_silent_active_tick is None:
                    first_silent_active_tick = tick

            if karr_active or oc_active:
                tick_rows.append(
                    {
                        "tick": int(tick),
                        "karr_active": bool(karr_active),
                        "oc_active": bool(oc_active),
                        "karr_detail": _jsonable(karr_detail),
                    }
                )

            apply_count_update(state, update)
            _apply_non_count_updates(state, update)

        return {
            "process_name": process_name,
            "trace_path": trace_path.as_posix(),
            "n_ticks": n_ticks,
            "karr_active_ticks": karr_active_ticks,
            "oc_active_ticks": oc_active_ticks,
            "oc_active_on_karr_active_ticks": oc_active_on_karr_active_ticks,
            "first_oc_active_tick": first_oc_active_tick,
            "first_silent_active_tick": first_silent_active_tick,
            "tick_rows": tick_rows,
        }


def _replay_summary(process_name: str, trace_path: Path, *, disable_chromosome_rand_stream_ledger: bool = False) -> dict[str, Any]:
    bit_result, honest_result = _honest_replay(
        process_name=process_name,
        trace_path=trace_path,
        disable_chromosome_rand_stream_ledger=disable_chromosome_rand_stream_ledger,
    )
    return {
        "disable_chromosome_rand_stream_ledger": disable_chromosome_rand_stream_ledger,
        "bit_identity_pass": bool(bit_result.pass_all_compared_ticks),
        "compared_tick_count": int(bit_result.compared_tick_count),
        "first_mismatch_tick": bit_result.first_mismatch_tick,
        "first_mismatch_observable": bit_result.first_mismatch_observable,
        "first_mismatch_index": bit_result.first_mismatch_index,
        "first_mismatch_oc_val": bit_result.first_mismatch_oc_val,
        "first_mismatch_karr_val": bit_result.first_mismatch_karr_val,
        "karr_active_ticks": int(honest_result.karr_active_ticks),
        "oc_active_ticks": int(honest_result.oc_active_ticks),
        "oc_active_on_karr_active_ticks": int(honest_result.oc_active_on_karr_active_ticks),
        "first_karr_active_tick": honest_result.first_karr_active_tick,
        "first_karr_active_detail": _jsonable(honest_result.first_karr_active_detail),
        "first_oc_active_tick": honest_result.first_oc_active_tick,
        "first_measured_mismatch": _jsonable(honest_result.first_measured_mismatch),
    }


def _isolated_tick_summary(process_name: str, trace_path: Path) -> dict[str, Any]:
    if process_name != "ReplicationInitiation":
        return {}

    with h5py.File(trace_path, "r") as handle:
        metadata = handle["metadata"]
        n_ticks_raw = np.asarray(metadata["n_ticks"][()]).reshape(-1)
        n_ticks = int(n_ticks_raw[0]) if n_ticks_raw.size else 0
        rng_seed_raw = np.asarray(metadata["rng_seed"][()]).reshape(-1)
        seed = int(rng_seed_raw[0]) if rng_seed_raw.size else 0
        ctx = _build_context(name=process_name, rng_seed=seed, handle=handle)

        karr_active_ticks = 0
        oc_any_active_ticks = 0
        oc_primary_active_ticks = 0
        oc_any_on_karr_active_ticks = 0
        oc_primary_on_karr_active_ticks = 0
        first_primary_silent_active_tick = None

        for tick in range(n_ticks):
            before_substrates = _project_trace_vector(ctx, "states_before", "substrates", tick)
            before_enzymes = _project_trace_vector(ctx, "states_before", "enzymes", tick)
            before_bound = _project_trace_vector(ctx, "states_before", "boundEnzymes", tick)

            chromosome_store = ChromosomeStore.from_hdf5_group(
                handle[handle["states_before/chromosome"][0, tick]]
            )
            payload = _run_replication_initiation_tick(
                seed=seed,
                tick=tick,
                state={
                    "substrate_wids": list(ctx.wids_by_observable["substrates"]),
                    "enzyme_wids": list(ctx.wids_by_observable["enzymes"]),
                    "oracle_before_substrates": before_substrates,
                    "oracle_before_enzymes": before_enzymes,
                    "oracle_before_bound_enzymes": before_bound,
                    "oracle_before_chromosome_store": chromosome_store,
                },
            )

            karr_active = _trace_activity_detail(process_name, ctx, tick) is not None
            any_active = bool(
                np.any(np.asarray(payload["substrates"], dtype=np.float64) != before_substrates)
                or np.any(np.asarray(payload["boundEnzymes"], dtype=np.float64) != before_bound)
            )
            primary_active = bool(np.any(np.asarray(payload["boundEnzymes"], dtype=np.float64) != before_bound))

            if karr_active:
                karr_active_ticks += 1
                if any_active:
                    oc_any_on_karr_active_ticks += 1
                if primary_active:
                    oc_primary_on_karr_active_ticks += 1
                if not primary_active and first_primary_silent_active_tick is None:
                    first_primary_silent_active_tick = tick
            if any_active:
                oc_any_active_ticks += 1
            if primary_active:
                oc_primary_active_ticks += 1

        return {
            "karr_active_ticks": karr_active_ticks,
            "oc_any_active_ticks": oc_any_active_ticks,
            "oc_primary_active_ticks": oc_primary_active_ticks,
            "oc_any_on_karr_active_ticks": oc_any_on_karr_active_ticks,
            "oc_primary_on_karr_active_ticks": oc_primary_on_karr_active_ticks,
            "first_primary_silent_active_tick": first_primary_silent_active_tick,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--process", default="ReplicationInitiation")
    parser.add_argument("--tick", type=int, default=None)
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help=(
            "Explicit, honest non-ledger diagnostic: never load the companion "
            ".chromosome_rand_stream_ledger.json sidecar even if present next to "
            "--trace, so the replay genuinely exercises the pre-existing "
            "freshly-seeded stand-in chromosome-stream, not a silently-loaded "
            "ledger (see STATUS_L21_REPINIT_SEPT2.md 'Session N+5' -- default "
            "behavior without this flag auto-loads an adjacent sidecar and is "
            "ledger-restored, NOT an independent non-ledger confirmation, and "
            "must not be reported as one)."
        ),
    )
    args = parser.parse_args()

    scan = _scan_ticks(args.process, args.trace)
    payload: dict[str, Any] = {
        "replay_summary": _replay_summary(
            args.process, args.trace, disable_chromosome_rand_stream_ledger=args.no_ledger
        ),
        "isolated_tick_summary": _isolated_tick_summary(args.process, args.trace),
        "scan": scan,
    }
    if args.tick is not None:
        payload["tick_diagnostic"] = _tick_diagnostic(args.process, args.trace, args.tick)
        payload["stateful_tick_diagnostic"] = _stateful_tick_diagnostic(
            args.process,
            args.trace,
            args.tick,
        )
    elif scan["first_silent_active_tick"] is not None:
        payload["tick_diagnostic"] = _tick_diagnostic(
            args.process,
            args.trace,
            int(scan["first_silent_active_tick"]),
        )

    print(json.dumps(_jsonable(payload), indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
