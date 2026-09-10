"""Focused DNAS tick-5 major-region activity ledger for the linking off-by-one."""

from __future__ import annotations

import argparse
import json
import math
import sys
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
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess  # noqa: E402
from scripts.l22_dnas_followup7_ledger import (  # noqa: E402
    MatlabCompatRng,
    _resolve_trace_root,
    _seed_paths,
    sibling_trace_root,
)

PROCESS = "DNASupercoiling"
DEFAULT_OUT = REPO_ROOT / "tmp" / "l22_dnas_linking_offbyone_current_seed0_tick5.json"


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


def _load_seed_context(*, trace_root: Path, seed: int) -> dict[str, Any]:
    seed_paths = _seed_paths(trace_root, [int(seed)])
    with sibling_trace_root(trace_root):
        before_channels, after_channels, n_ticks = helpers._load_seeded_mat_channels(  # noqa: SLF001
            seed_paths,
            process_name=PROCESS,
        )
        chromosome_oracle = helpers.load_chromosome_oracle_for_process(PROCESS, [int(seed)], n_ticks)
    return {
        "before_channels": before_channels,
        "after_channels": after_channels,
        "before_stores": chromosome_oracle["before_stores"][0],
        "after_stores": chromosome_oracle["after_stores"][0],
    }


def _build_runtime_state(
    *,
    process: KarrDNASupercoilingProcess,
    before_channels: dict[str, np.ndarray],
    tick: int,
    before_store: ChromosomeStore,
) -> dict[str, Any]:
    runtime_state = build_state_template(process)
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(before_channels["substrates"][0, int(tick)], dtype=np.float64),
        wids=list(process.substrate_wids),
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=np.asarray(before_channels["enzymes"][0, int(tick)], dtype=np.float64),
        wids=list(process.enzyme_wids),
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="boundEnzymes",
        vector=np.asarray(before_channels["boundEnzymes"][0, int(tick)], dtype=np.float64),
        wids=list(process.enzyme_wids),
    )
    runtime_state.setdefault("chromosome", {}).update(before_store.to_state())
    refresh_allocator_views(process, runtime_state)
    return runtime_state


def _tracked_substrates(process: KarrDNASupercoilingProcess, state: dict[str, Any]) -> dict[str, float]:
    substrates = state.get("substrates", {})
    if not isinstance(substrates, dict):
        raise TypeError("state['substrates'] must be a dict")
    out = {
        process.atp_wid: float(substrates.get(process.atp_wid, 0.0)),
        process.h2o_wid: float(substrates.get(process.h2o_wid, 0.0)),
        process.adp_wid: float(substrates.get(process.adp_wid, 0.0)),
        process.pi_wid: float(substrates.get(process.pi_wid, 0.0)),
    }
    if process.h_wid is not None:
        out[process.h_wid] = float(substrates.get(process.h_wid, 0.0))
    return out


def _positive_region_state(
    process: KarrDNASupercoilingProcess,
    *,
    store: ChromosomeStore,
    state: dict[str, Any],
) -> tuple[list[tuple[int, int, int]], np.ndarray, np.ndarray, np.ndarray]:
    polymerized = process._ensure_polymerized_regions(store.get_field("polymerizedRegions"))  # noqa: SLF001
    positive_regions = process._positive_regions_from_store(  # noqa: SLF001
        store=store,
        polymerized=polymerized,
    )
    sigma_fallback = float(state.get("chromosome", {}).get("supercoil_density", process.equilibrium_sigma))
    linking_numbers = store.get_field("linkingNumbers")
    positive_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=linking_numbers,
        fallback_sigma=sigma_fallback,
    )
    sigma_values = process._positive_region_sigmas_from_store(  # noqa: SLF001
        store=store,
        positive_regions=positive_regions,
        linking_numbers=linking_numbers,
        fallback_sigma=sigma_fallback,
    )
    legal = np.zeros((len(positive_regions), len(process.enzyme_wids)), dtype=bool)
    if sigma_values.size:
        legal[:, process.gyrase_idx] = sigma_values > process.gyrase_sigma_limit
        legal[:, process.topoiv_idx] = sigma_values > process.topoiv_sigma_limit
        legal[:, process.topoi_idx] = sigma_values < process.topoi_sigma_limit
    return positive_regions, positive_values, sigma_values, legal


def _apply_chromosome_update(before: ChromosomeStore, chrom_update: dict[str, Any] | None) -> ChromosomeStore:
    new_state = before.to_state()
    if isinstance(chrom_update, dict):
        for field_name, value in chrom_update.items():
            if field_name not in new_state:
                continue
            if isinstance(value, dict) and "positions" in value:
                new_state[field_name] = SparseTriplet.from_state(value, shape=before.shape).to_state()
    return ChromosomeStore.from_state_mapping(new_state, shape=before.shape)


def _triplet_value(triplet: SparseTriplet, *, position: int, strand: int) -> int:
    mask = (
        (triplet.positions.astype(np.int64, copy=False) == int(position))
        & (triplet.strands.astype(np.int64, copy=False) == int(strand))
    )
    idxs = np.flatnonzero(mask)
    if idxs.size == 0:
        raise KeyError(f"Missing triplet entry at position={position} strand={strand}")
    return int(triplet.values.astype(np.int64, copy=False)[idxs[0]])


def build_seed_tick_ledger(
    *,
    trace_root: Path,
    seed: int,
    tick: int,
    rng_variant: str = "current",
) -> dict[str, Any]:
    context = _load_seed_context(trace_root=trace_root, seed=int(seed))
    before_channels = context["before_channels"]
    before_stores: list[ChromosomeStore] = context["before_stores"]
    after_store: ChromosomeStore = context["after_stores"][int(tick)]

    process = KarrDNASupercoilingProcess({"rng_seed": int(seed)})
    if rng_variant == "matlab":
        process._rng = MatlabCompatRng(int(seed))  # type: ignore[assignment]  # noqa: SLF001
    elif rng_variant != "current":
        raise ValueError(f"Unknown rng_variant: {rng_variant!r}")

    captured: dict[str, Any] = {}
    original_activity = process._sample_activity_events_by_region  # noqa: SLF001

    for replay_tick in range(int(tick) + 1):
        before_store = before_stores[int(replay_tick)]
        runtime_state = _build_runtime_state(
            process=process,
            before_channels=before_channels,
            tick=int(replay_tick),
            before_store=before_store,
        )
        positive_regions, positive_values, sigma_values, legal = _positive_region_state(
            process,
            store=before_store,
            state=runtime_state,
        )

        def _wrapped_activity(
            *,
            store: ChromosomeStore,
            positive_regions: list[tuple[int, int, int]],
            sigma_values: np.ndarray,
            legal: np.ndarray,
            topoi_transient: np.ndarray,
            available_atp: float,
            available_h2o: float,
            dt: float,
        ) -> tuple[np.ndarray, float]:
            events = np.zeros((len(positive_regions), len(process.enzyme_wids)), dtype=np.int32)
            if not positive_regions or sigma_values.size == 0 or dt <= 0.0:
                return events, 0.0

            activity_order = process._rng.permutation(len(process.enzyme_wids)).tolist()  # noqa: SLF001
            remaining_atp = max(0.0, float(available_atp))
            remaining_h2o = max(0.0, float(available_h2o))
            atp_used = 0.0
            substrate_seed = _tracked_substrates(process, runtime_state)

            def _local_substrates_snapshot() -> dict[str, float]:
                out = dict(substrate_seed)
                out[process.atp_wid] = float(remaining_atp)
                out[process.h2o_wid] = float(remaining_h2o)
                out[process.adp_wid] = float(substrate_seed.get(process.adp_wid, 0.0) + atp_used)
                out[process.pi_wid] = float(substrate_seed.get(process.pi_wid, 0.0) + atp_used)
                if process.h_wid is not None:
                    out[process.h_wid] = float(substrate_seed.get(process.h_wid, 0.0) + atp_used)
                return out

            major_region_idx = max(
                range(len(positive_regions)),
                key=lambda idx: int(positive_regions[idx][2]),
            )
            major_linking = float(positive_values[major_region_idx])
            steps: list[dict[str, Any]] = []

            for region_index, (start, strand, length) in enumerate(positive_regions):
                for order_position, enzyme_idx in enumerate(activity_order, start=1):
                    legal_tf = enzyme_idx < legal.shape[1] and bool(legal[region_index, enzyme_idx])
                    step: dict[str, Any] | None = None
                    if region_index == major_region_idx:
                        step = {
                            "order_position": int(order_position),
                            "enzyme_index_zero_based": int(enzyme_idx),
                            "enzyme_index_matlab_one_based": int(enzyme_idx + 1),
                            "enzyme_wid": str(process.enzyme_wids[enzyme_idx]),
                            "legal": bool(legal_tf),
                            "linking_before": float(major_linking),
                            "substrates_before": _local_substrates_snapshot(),
                        }

                    if not legal_tf:
                        if step is not None:
                            step.update(
                                {
                                    "nBound": 0.0,
                                    "probOfActivity": 0.0,
                                    "expected_activity": 0.0,
                                    "stochastic_round_result": 0,
                                    "atp_event_caps": [0, 0],
                                    "nStrandPassingEvents": 0,
                                    "deltaLK_per_event": float(process.enzyme_delta_lks[enzyme_idx]),
                                    "delta_linking_number": 0.0,
                                    "linking_after": float(major_linking),
                                    "substrates_after": _local_substrates_snapshot(),
                                }
                            )
                            steps.append(step)
                        continue

                    activity_rate = float(process.enzyme_activity_rates[enzyme_idx])
                    if activity_rate <= 0.0:
                        if step is not None:
                            step.update(
                                {
                                    "nBound": 0.0,
                                    "probOfActivity": 0.0,
                                    "expected_activity": 0.0,
                                    "stochastic_round_result": 0,
                                    "atp_event_caps": [0, 0],
                                    "nStrandPassingEvents": 0,
                                    "deltaLK_per_event": float(process.enzyme_delta_lks[enzyme_idx]),
                                    "delta_linking_number": 0.0,
                                    "linking_after": float(major_linking),
                                    "substrates_after": _local_substrates_snapshot(),
                                }
                            )
                            steps.append(step)
                        continue

                    if float(process.enzyme_mean_dwell_times[enzyme_idx]) == 0.0:
                        n_bound = float(topoi_transient[region_index])
                    else:
                        n_bound = float(
                            process._count_bound_proteins_in_region(  # noqa: SLF001
                                store=store,
                                position=int(start),
                                strand=int(strand),
                                region_length=int(length),
                                enzyme_idx=enzyme_idx,
                            )
                        )
                    if n_bound <= 0.0:
                        if step is not None:
                            step.update(
                                {
                                    "nBound": float(n_bound),
                                    "probOfActivity": 0.0,
                                    "expected_activity": 0.0,
                                    "stochastic_round_result": 0,
                                    "atp_event_caps": [0, 0],
                                    "nStrandPassingEvents": 0,
                                    "deltaLK_per_event": float(process.enzyme_delta_lks[enzyme_idx]),
                                    "delta_linking_number": 0.0,
                                    "linking_after": float(major_linking),
                                    "substrates_after": _local_substrates_snapshot(),
                                }
                            )
                            steps.append(step)
                        continue

                    probability = process._enzyme_activity_probability_for_sigma(  # noqa: SLF001
                        enzyme_idx=enzyme_idx,
                        sigma=float(sigma_values[region_index]),
                    )
                    if probability <= 0.0:
                        if step is not None:
                            step.update(
                                {
                                    "nBound": float(n_bound),
                                    "probOfActivity": float(probability),
                                    "expected_activity": 0.0,
                                    "stochastic_round_result": 0,
                                    "atp_event_caps": [0, 0],
                                    "nStrandPassingEvents": 0,
                                    "deltaLK_per_event": float(process.enzyme_delta_lks[enzyme_idx]),
                                    "delta_linking_number": 0.0,
                                    "linking_after": float(major_linking),
                                    "substrates_after": _local_substrates_snapshot(),
                                }
                            )
                            steps.append(step)
                        continue

                    expected = max(0.0, n_bound * activity_rate * probability * float(dt))
                    if expected <= 0.0:
                        stochastic_round_draw = None
                        stochastic_round_fraction = 0.0
                        stochastic_round_result = 0
                    else:
                        base = int(math.floor(expected))
                        stochastic_round_fraction = float(expected - base)
                        if stochastic_round_fraction <= 0.0:
                            stochastic_round_draw = None
                            stochastic_round_result = int(base)
                        else:
                            stochastic_round_draw = float(process._rng.random())  # noqa: SLF001
                            stochastic_round_result = int(base + int(stochastic_round_draw < stochastic_round_fraction))
                    n_events = int(stochastic_round_result)
                    atp_caps: list[int | None]
                    atp_cost = float(process.enzyme_atp_costs[enzyme_idx])
                    if atp_cost > 0.0:
                        atp_cap = int(math.floor(remaining_atp / atp_cost))
                        h2o_cap = int(math.floor(remaining_h2o / atp_cost))
                        atp_caps = [int(atp_cap), int(h2o_cap)]
                        max_events = min(atp_cap, h2o_cap)
                        if max_events <= 0:
                            n_events = 0
                        else:
                            n_events = min(n_events, max_events)
                            n_atp = float(n_events) * atp_cost
                            remaining_atp = max(0.0, remaining_atp - n_atp)
                            remaining_h2o = max(0.0, remaining_h2o - n_atp)
                            atp_used += n_atp
                    else:
                        atp_caps = [None, None]

                    events[region_index, enzyme_idx] = int(n_events)
                    delta_linking = float(process.enzyme_delta_lks[enzyme_idx]) * float(n_events)
                    if region_index == major_region_idx:
                        major_linking += delta_linking
                        assert step is not None
                        step.update(
                            {
                                "nBound": float(n_bound),
                                "probOfActivity": float(probability),
                                "expected_activity": float(expected),
                                "stochastic_round_draw": stochastic_round_draw,
                                "stochastic_round_fraction": float(stochastic_round_fraction),
                                "stochastic_round_result": int(stochastic_round_result),
                                "atp_event_caps": atp_caps,
                                "nStrandPassingEvents": int(n_events),
                                "deltaLK_per_event": float(process.enzyme_delta_lks[enzyme_idx]),
                                "delta_linking_number": float(delta_linking),
                                "linking_after": float(major_linking),
                                "substrates_after": _local_substrates_snapshot(),
                            }
                        )
                        steps.append(step)

            if replay_tick == int(tick):
                captured.update(
                    {
                        "rng_variant": str(rng_variant),
                        "seed": int(seed),
                        "tick": int(tick),
                        "region_index_zero_based": int(major_region_idx),
                        "region_index_matlab_one_based": int(major_region_idx + 1),
                        "region_start_zero_based": int(positive_regions[major_region_idx][0]),
                        "region_start_matlab_one_based": int(positive_regions[major_region_idx][0] + 1),
                        "region_strand_zero_based": int(positive_regions[major_region_idx][1]),
                        "region_strand_matlab_one_based": int(positive_regions[major_region_idx][1] + 1),
                        "region_length": int(positive_regions[major_region_idx][2]),
                        "sigma_before": float(sigma_values[major_region_idx]),
                        "linking_before": float(positive_values[major_region_idx]),
                        "activity_order_zero_based": [int(idx) for idx in activity_order],
                        "activity_order_matlab_one_based": [int(idx + 1) for idx in activity_order],
                        "activity_order_wids": [str(process.enzyme_wids[idx]) for idx in activity_order],
                        "substrates_before": dict(substrate_seed),
                        "steps": steps,
                        "final_writeback_value": float(major_linking),
                        "substrates_after": _local_substrates_snapshot(),
                    }
                )
            return events, atp_used

        process._sample_activity_events_by_region = _wrapped_activity  # type: ignore[assignment]  # noqa: SLF001
        try:
            update = process.next_update(1.0, runtime_state)
        finally:
            process._sample_activity_events_by_region = original_activity  # type: ignore[assignment]  # noqa: SLF001

        apply_count_update(runtime_state, update)
        if replay_tick == int(tick):
            chrom_after_store = _apply_chromosome_update(
                before_store,
                update.get("chromosome", {}) if isinstance(update, dict) else {},
            )
            linking_after = chrom_after_store.get_field("linkingNumbers")
            captured["python_major_region_linking_after"] = int(
                _triplet_value(
                    linking_after,
                    position=int(positive_regions[captured["region_index_zero_based"]][0]),
                    strand=int(positive_regions[captured["region_index_zero_based"]][1]),
                )
            )
            trace_linking_after = after_store.get_field("linkingNumbers")
            captured["karr_major_region_linking_after"] = int(
                _triplet_value(
                    trace_linking_after,
                    position=int(positive_regions[captured["region_index_zero_based"]][0]),
                    strand=int(positive_regions[captured["region_index_zero_based"]][1]),
                )
            )

    if not captured:
        raise RuntimeError(f"Failed to capture seed={seed} tick={tick} major-region ledger")
    return captured


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--tick", type=int, default=5)
    parser.add_argument("--rng-variant", choices=("current", "matlab"), default="current")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    trace_root = _resolve_trace_root(None if args.trace_root is None else _coerce_cli_path(args.trace_root))
    out_path = _coerce_cli_path(args.out).resolve()
    payload = build_seed_tick_ledger(
        trace_root=trace_root,
        seed=int(args.seed),
        tick=int(args.tick),
        rng_variant=str(args.rng_variant),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    print(f"[l22_dnas_linking_offbyone_ledger] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
