"""Build a 200-seed DNAS follow-up audit artifact from frozen tensors + traces.

This script is diagnostic-only. It does not edit shared Design-A code, does not
perform new extraction, and does not change the frozen N=200 gate. It uses the
already-frozen checkpoint tensors to locate each seed's first OC-vs-Karr sparse
(`delta_nnz`) divergence, then replays only that seed/tick against the frozen
per-process traces to attach source-branch clues from the current OC
implementation and the authoritative MATLAB control flow.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from types import MethodType
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

import _l2_2_design_a_runner_helpers as helpers  # noqa: E402
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess  # noqa: E402
from scripts.l22_dnas_rare_event.evaluate_checkpoint import _load_tensor_checkpoint  # noqa: E402
from scripts.l22_dnas_rare_event.sparse_gate import support_counts  # noqa: E402
from l2_replay_common import (  # noqa: E402
    apply_count_update,
    build_state_template,
    overlay_observable_into_state,
    refresh_allocator_views,
)

PROCESS = "DNASupercoiling"
DEFAULT_TRACE_ROOT = Path(
    "E:/opencell-worktrees/l22-dnas-closure-20260805/data/m1_sources/karr_native"
)
DEFAULT_CHECKPOINT = Path(
    "E:/opencell-worktrees/l22-dnas-closure-20260805/"
    "docs/phase_f/l2_2_design_a/evidence_bundle/DNASupercoiling/"
    "diagnostic_n200/raw_captured_tensors_checkpoint.npz"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "evidence_bundle"
    / "DNASupercoiling"
    / "diagnostic_n200_followup"
    / "SEED_BRANCH_AUDIT.json"
)


def _coerce_cli_path(raw: str | Path) -> Path:
    text = str(raw)
    if len(text) >= 3 and text[1:3] == ":/":
        win = PureWindowsPath(text)
        drive = str(win.drive).rstrip(":").lower()
        tail = Path(*win.parts[1:])
        return Path("/mnt") / drive / tail
    if len(text) >= 3 and text[1:3] == ":\\":
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


@contextmanager
def sibling_trace_root(trace_root: Path):
    """Temporarily redirect helper seed-path resolution to the frozen sibling root."""

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


def _projection(before: ChromosomeStore, after: ChromosomeStore) -> tuple[float, float]:
    return (
        float(
            helpers._chromosome_projection_component(  # noqa: SLF001
                "linkingNumbers.delta_value_sum", before, after
            )
        ),
        float(
            helpers._chromosome_projection_component(  # noqa: SLF001
                "linkingNumbers.delta_nnz", before, after
            )
        ),
    )


def _component_vector_dict(values: np.ndarray) -> dict[str, float]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    return {
        "linkingNumbers.delta_value_sum": float(flat[0]),
        "linkingNumbers.delta_nnz": float(flat[1]),
    }


def _seed_summary_from_checkpoint(oc_tensor: np.ndarray, karr_tensor: np.ndarray, seed: int) -> dict[str, Any]:
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
        "first_divergence_projection_oc": (
            _component_vector_dict(oc_seed[first_div_tick]) if first_div_tick is not None else None
        ),
        "first_divergence_projection_karr": (
            _component_vector_dict(karr_seed[first_div_tick]) if first_div_tick is not None else None
        ),
        "first_sparse_divergence_projection_oc": (
            _component_vector_dict(oc_seed[first_sparse_div_tick]) if first_sparse_div_tick is not None else None
        ),
        "first_sparse_divergence_projection_karr": (
            _component_vector_dict(karr_seed[first_sparse_div_tick]) if first_sparse_div_tick is not None else None
        ),
    }


def _region_case(process: KarrDNASupercoilingProcess, positive_regions: list[tuple[int, int, int]]) -> str:
    if len(positive_regions) == 1 and positive_regions[0][2] == process.chromosome_length:
        return "single_full_length_region"
    if (
        len(positive_regions) == 2
        and all(int(length) == process.chromosome_length for _, _, length in positive_regions)
    ):
        return "two_full_length_regions_half_split_branch"
    return "general_space_weighted_branch"


def _build_sample_state(
    *,
    oracle: dict[str, Any],
    chromosome_before: ChromosomeStore,
    seed: int,
    tick: int,
    substrate_wids: list[str],
    enzyme_wids: list[str],
) -> dict[str, Any]:
    return {
        "substrate_wids": list(substrate_wids),
        "enzyme_wids": list(enzyme_wids),
        "oracle_before_substrates": np.asarray(
            oracle["before_substrates"][seed, tick], dtype=np.float64
        ),
        "oracle_before_enzymes": np.asarray(
            oracle["before_enzymes"][seed, tick], dtype=np.float64
        ),
        "oracle_before_bound_enzymes": np.asarray(
            oracle["before_bound_enzymes"][seed, tick], dtype=np.float64
        ),
        "oracle_before_chromosome_store": chromosome_before,
    }


def _overlay_chromosome(runtime_state: dict[str, Any], store: ChromosomeStore) -> None:
    chrom_state = runtime_state.setdefault("chromosome", {})
    if not isinstance(chrom_state, dict):
        raise TypeError("state['chromosome'] must be dict")
    chrom_state.update(store.to_state())


def _apply_chromosome_update(before: ChromosomeStore, update: dict[str, Any] | None) -> ChromosomeStore:
    new_state = before.to_state()
    if isinstance(update, dict):
        for field_name, value in update.items():
            if field_name not in new_state:
                continue
            if isinstance(value, dict) and "positions" in value:
                new_state[field_name] = SparseTriplet.from_state(value, shape=before.shape).to_state()
    return ChromosomeStore.from_state_mapping(new_state, shape=before.shape)


def _debug_oc_tick(
    *,
    seed: int,
    tick: int,
    sample_state: dict[str, Any],
) -> dict[str, Any]:
    sample_seed = helpers._sample_seed(seed, tick)  # noqa: SLF001
    process = KarrDNASupercoilingProcess({"rng_seed": int(sample_seed)})
    runtime_state = build_state_template(process)
    substrate_wids = list(sample_state["substrate_wids"])
    enzyme_wids = list(sample_state["enzyme_wids"])

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(sample_state["oracle_before_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=np.asarray(sample_state["oracle_before_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="boundEnzymes",
        vector=np.asarray(sample_state["oracle_before_bound_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    chrom_store_before: ChromosomeStore = sample_state["oracle_before_chromosome_store"]
    _overlay_chromosome(runtime_state, chrom_store_before)

    debug: dict[str, Any] = {
        "sample_seed": int(sample_seed),
        "sample_region_events": [],
    }

    original_sample_region_events = process._sample_region_events
    original_limit_events_by_atp = process._limit_events_by_atp
    original_replication_supercoil_load_events = process._replication_supercoil_load_events

    def _wrapped_sample_region_events(self, **kwargs):
        result = np.asarray(original_sample_region_events(**kwargs), dtype=np.int32)
        debug["sample_region_events"].append(
            {
                "allowed_when": str(kwargs["allowed_when"]),
                "total_count": float(kwargs["total_count"]),
                "activity_rate": float(kwargs["activity_rate"]),
                "sigma_limit": float(kwargs["sigma_limit"]),
                "force_prob_one": bool(kwargs.get("force_prob_one", False)),
                "sigma_values": np.asarray(kwargs["sigma_values"], dtype=np.float64).tolist(),
                "region_lengths": np.asarray(kwargs["region_lengths"], dtype=np.float64).tolist(),
                "events": result.tolist(),
                "sum": int(result.sum()),
            }
        )
        return result

    def _wrapped_limit_events_by_atp(self, **kwargs):
        result = original_limit_events_by_atp(**kwargs)
        debug["limit_events_by_atp"] = {
            "gyrase_events_in": int(kwargs["gyrase_events"]),
            "topoiv_events_in": int(kwargs["topoiv_events"]),
            "available_atp": float(kwargs["available_atp"]),
            "mode": str(kwargs["mode"]),
            "gyrase_events_kept": int(result[0]),
            "topoiv_events_kept": int(result[1]),
        }
        return result

    def _wrapped_replication_supercoil_load_events(self, replication_state: str, dt: float):
        result = int(original_replication_supercoil_load_events(replication_state, dt))
        debug["replication_supercoil_load_events"] = {
            "replication_state": str(replication_state),
            "dt": float(dt),
            "events": int(result),
        }
        return result

    process._sample_region_events = MethodType(_wrapped_sample_region_events, process)
    process._limit_events_by_atp = MethodType(_wrapped_limit_events_by_atp, process)
    process._replication_supercoil_load_events = MethodType(
        _wrapped_replication_supercoil_load_events, process
    )

    refresh_allocator_views(process, runtime_state)
    update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)

    after_store = _apply_chromosome_update(
        chrom_store_before,
        update.get("chromosome", {}) if isinstance(update, dict) else {},
    )

    polymerized = process._ensure_polymerized_regions(chrom_store_before.get_field("polymerizedRegions"))
    positive_regions = process._positive_ds_regions(polymerized)
    linking_numbers = chrom_store_before.get_field("linkingNumbers")
    positive_values = process._align_positive_region_values(
        positive_regions=positive_regions,
        linking_numbers=linking_numbers,
        fallback_sigma=float(runtime_state["chromosome"].get("supercoil_density", process.equilibrium_sigma)),
    )
    sigma_values = process._region_sigmas(positive_regions=positive_regions, linking_values=positive_values)
    before_enzymes = {
        wid: float(np.asarray(sample_state["oracle_before_enzymes"], dtype=np.float64)[idx])
        for idx, wid in enumerate(enzyme_wids)
    }
    before_bound = {
        wid: float(np.asarray(sample_state["oracle_before_bound_enzymes"], dtype=np.float64)[idx])
        for idx, wid in enumerate(enzyme_wids)
    }
    tracked_substrate_wids = {process.atp_wid, process.h2o_wid, process.adp_wid, process.pi_wid}
    if process.h_wid is not None:
        tracked_substrate_wids.add(process.h_wid)

    debug.update(
        {
            "region_case": _region_case(process, positive_regions),
            "positive_region_count": int(len(positive_regions)),
            "positive_regions": [
                {"start": int(start), "strand": int(strand), "length": int(length)}
                for start, strand, length in positive_regions
            ],
            "positive_linking_values_before": positive_values.tolist(),
            "sigma_values_before": np.asarray(sigma_values, dtype=np.float64).tolist(),
            "gyrase_sigma_limit": float(process.gyrase_sigma_limit),
            "topoiv_sigma_limit": float(process.topoiv_sigma_limit),
            "topoi_sigma_limit": float(process.topoi_sigma_limit),
            "n_legal_gyrase_regions": int(np.count_nonzero(sigma_values > process.gyrase_sigma_limit)),
            "n_legal_topoiv_regions": int(np.count_nonzero(sigma_values > process.topoiv_sigma_limit)),
            "n_legal_topoi_regions": int(np.count_nonzero(sigma_values < process.topoi_sigma_limit)),
            "before_free_enzymes": before_enzymes,
            "before_bound_enzymes": before_bound,
            "substrates_before": {
                wid: float(np.asarray(sample_state["oracle_before_substrates"], dtype=np.float64)[idx])
                for idx, wid in enumerate(substrate_wids)
                if wid in tracked_substrate_wids
            },
            "oc_projection": _component_vector_dict(np.asarray(_projection(chrom_store_before, after_store))),
            "oc_after_bound_enzymes": {
                wid: float(runtime_state.get("boundEnzymes", {}).get(wid, 0.0)) for wid in enzyme_wids
            },
            "oc_after_free_enzymes": {
                wid: float(runtime_state.get("enzymes", {}).get(wid, 0.0)) for wid in enzyme_wids
            },
            "allocator_row_after_refresh": {
                wid: float(
                    runtime_state.get("substrates_allocated", {})
                    .get(process.name, {})
                    .get(wid, 0.0)
                )
                for wid in (process.atp_wid, process.h2o_wid)
            },
            "requests_emitted": {
                wid: float(update.get("requests", {}).get(process.name, {}).get(wid, 0.0))
                for wid in (process.atp_wid, process.h2o_wid)
            },
            "substrate_delta_emitted": {
                wid: float(update.get("substrates", {}).get(wid, 0.0))
                for wid in update.get("substrates", {})
            },
        }
    )
    return debug


def _classify_divergence(
    *,
    first_div_oc: dict[str, float] | None,
    first_div_karr: dict[str, float] | None,
    debug: dict[str, Any] | None,
) -> str:
    if first_div_oc is None or first_div_karr is None:
        return "no_divergence"
    oc_value = float(first_div_oc["linkingNumbers.delta_value_sum"])
    oc_nnz = float(first_div_oc["linkingNumbers.delta_nnz"])
    karr_value = float(first_div_karr["linkingNumbers.delta_value_sum"])
    karr_nnz = float(first_div_karr["linkingNumbers.delta_nnz"])
    if oc_value == karr_value and oc_nnz != karr_nnz:
        return "linkingNumbers_writeback_sparse_triplet_rebuild"
    if debug is None:
        return "divergence_without_debug_context"
    if float(debug["before_bound_enzymes"].get("MG_203_204_TETRAMER", 0.0)) > 0.0 and (
        int(debug["n_legal_topoiv_regions"]) < int(debug["positive_region_count"])
    ):
        return "matlab_topoiv_release_branch_381_385"
    if float(debug["before_bound_enzymes"].get("DNA_GYRASE", 0.0)) > 0.0:
        return "matlab_gyrase_probabilistic_release_branch_388"
    if debug["region_case"] == "two_full_length_regions_half_split_branch" and (
        int(debug["n_legal_topoi_regions"]) > 0
        or int(debug["n_legal_gyrase_regions"]) > 0
        or int(debug["n_legal_topoiv_regions"]) > 0
    ):
        return "matlab_half_up_half_down_binding_branch_401_420"
    if debug["region_case"] == "single_full_length_region" and int(debug["n_legal_topoi_regions"]) > 0:
        return "matlab_single_full_length_transient_binding_branch_395_400"
    if int(debug["n_legal_topoi_regions"]) > 0:
        return "matlab_general_transient_binding_branch_421_446"
    if (
        int(debug["n_legal_gyrase_regions"]) > 0
        or int(debug["n_legal_topoiv_regions"]) > 0
        or any(int(call["sum"]) > 0 for call in debug.get("sample_region_events", ()))
    ):
        return "matlab_randperm_activity_order_branch_470_499"
    return "unclassified_non_source_faithful_branch"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--trace-root", default=str(DEFAULT_TRACE_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    checkpoint_path = _coerce_cli_path(args.checkpoint).resolve()
    trace_root = _coerce_cli_path(args.trace_root).resolve()
    out_path = _coerce_cli_path(args.out).resolve()

    loaded = _load_tensor_checkpoint(checkpoint_path)
    oc_tensor = np.asarray(loaded["oc_tensor"], dtype=np.float64)
    karr_tensor = np.asarray(loaded["karr_tensor"], dtype=np.float64)
    if oc_tensor.shape != karr_tensor.shape:
        raise ValueError(f"OC/Karr tensor shape mismatch: {oc_tensor.shape} vs {karr_tensor.shape}")
    if oc_tensor.ndim != 3 or oc_tensor.shape[2] != 2:
        raise ValueError(f"Expected (seed, tick, 2) tensor, got {oc_tensor.shape}")

    n_seeds, m_ticks, _ = oc_tensor.shape
    seeds = list(range(int(n_seeds)))
    per_seed = [_seed_summary_from_checkpoint(oc_tensor, karr_tensor, seed) for seed in seeds]
    diverged_seeds = [row["seed"] for row in per_seed if row["first_sparse_divergence_tick"] is not None]

    with sibling_trace_root(trace_root):
        oracle = helpers._load_v2_ensemble(PROCESS, max_seeds=n_seeds)  # noqa: SLF001
        if oracle is None:
            raise FileNotFoundError(f"Could not load {PROCESS} oracle from {trace_root}")
        chromosome_oracle = helpers.load_chromosome_oracle_for_process(PROCESS, diverged_seeds, m_ticks)

    sample_process = KarrDNASupercoilingProcess({"rng_seed": 0})
    substrate_wids = list(sample_process.substrate_wids)
    enzyme_wids = list(sample_process.enzyme_wids)
    seed_to_chrom_idx = {seed: idx for idx, seed in enumerate(diverged_seeds)}

    classification_counts: dict[str, int] = {}
    for row in per_seed:
        seed = int(row["seed"])
        div_tick = row["first_sparse_divergence_tick"]
        debug = None
        if div_tick is not None:
            chrom_idx = seed_to_chrom_idx[seed]
            before_store = chromosome_oracle["before_stores"][chrom_idx][div_tick]
            after_store = chromosome_oracle["after_stores"][chrom_idx][div_tick]
            sample_state = _build_sample_state(
                oracle=oracle,
                chromosome_before=before_store,
                seed=seed,
                tick=div_tick,
                substrate_wids=substrate_wids,
                enzyme_wids=enzyme_wids,
            )
            debug = _debug_oc_tick(seed=seed, tick=div_tick, sample_state=sample_state)
            debug["karr_projection"] = _component_vector_dict(np.asarray(_projection(before_store, after_store)))
            row["first_sparse_divergence_debug"] = debug
        classification = _classify_divergence(
            first_div_oc=row["first_sparse_divergence_projection_oc"],
            first_div_karr=row["first_sparse_divergence_projection_karr"],
            debug=debug,
        )
        if row["first_sparse_divergence_tick"] is None and row["first_divergence_tick"] is not None:
            classification = "dense_only_divergence_not_sparse_gate_driver"
        row["first_sparse_divergence_classification"] = classification
        classification_counts[classification] = classification_counts.get(classification, 0) + 1

    oc_sparse = support_counts(oc_tensor[:, :, 1])
    karr_sparse = support_counts(karr_tensor[:, :, 1])
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "process": PROCESS,
        "checkpoint_path": str(checkpoint_path),
        "trace_root": str(trace_root),
        "tensor_shape": list(oc_tensor.shape),
        "component_scales": loaded["component_scales"],
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
        "first_sparse_divergence_classification_counts": classification_counts,
        "per_seed": per_seed,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    print(f"[l22_dnas_followup_audit] wrote {out_path}")
    print(
        "[l22_dnas_followup_audit] sparse-support "
        f"oc(active={oc_sparse.active_seeds}, pooled={oc_sparse.pooled_nonzero_ticks}, clustered={oc_sparse.clustered_seeds}) "
        f"karr(active={karr_sparse.active_seeds}, pooled={karr_sparse.pooled_nonzero_ticks}, clustered={karr_sparse.clustered_seeds})"
    )
    print(
        "[l22_dnas_followup_audit] first-sparse-divergence classes "
        + ", ".join(f"{key}={value}" for key, value in sorted(classification_counts.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
