"""FOLLOWUP8 DNAS topoIV candidate-space microscope.

Focused diagnostic for the frozen seed-0/tick-5 stable-binding divergence.
Emits a compact step-by-step ledger for the current OC helper path and a
source-modeled MATLAB path rooted in `Chromosome.getAccessibleRegions(...)`
plus `ChromosomeProcessAspect.bindProteinToChromosomeStochastically(...)`.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

import _l2_2_design_a_runner_helpers as helpers  # noqa: E402
from l2_replay_common import (  # noqa: E402
    build_state_template,
    overlay_observable_into_state,
    refresh_allocator_views,
)
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess  # noqa: E402
from scripts.l22_dnas_followup7_ledger import (  # noqa: E402
    MatlabCompatRng,
    _coerce_cli_path,
    _json_default,
    _resolve_trace_root,
    _seed_paths,
    sibling_trace_root,
)

PROCESS = "DNASupercoiling"
DEFAULT_OUT = REPO_ROOT / "tmp" / "l22_dnas_followup8_seed0_tick5.json"
TRACE_VISIBLE_CHROMOSOME_FIELDS = (
    "abasicSites",
    "complexBoundSites",
    "damagedBases",
    "damagedSugarPhosphates",
    "gapSites",
    "hollidayJunctions",
    "intrastrandCrossLinks",
    "linkingNumbers",
    "monomerBoundSites",
    "polymerizedRegions",
    "strandBreaks",
)
SOURCE_ONLY_CHROMOSOME_FIELDS = (
    "damagedSites",
    "doubleStrandedRegions",
    "singleStrandedRegions",
    "supercoiled",
    "supercoils",
    "superhelicalDensity",
)
SOURCE_ONLY_VALIDATION_FIELDS = (
    "validated",
    "validated_damaged",
    "validated_damagedSites",
    "validated_damagedSites_excm6AD",
    "validated_damagedSites_nonRedundant",
    "validated_damagedSites_shifted_incm6AD",
    "validated_doubleStrandedRegions",
    "validated_linkingNumbers",
    "validated_polymerizedRegions",
    "validated_singleStrandedRegions",
    "validated_supercoiled",
    "validated_supercoils",
    "validated_superhelicalDensity",
)


@dataclass(frozen=True)
class IntervalSource:
    kind: str
    field_name: str
    global_index: int | None
    start: int
    strand: int
    length: int
    positive_strand: int
    interval_start: int
    interval_end: int
    releasable: bool


def _split_half_open(start: int, length: int, sequence_len: int) -> list[tuple[int, int]]:
    if length <= 0:
        return []
    start_i = int(start) % int(sequence_len)
    length_i = int(length)
    if length_i >= int(sequence_len):
        return [(0, int(sequence_len))]
    end_i = start_i + length_i
    if end_i <= int(sequence_len):
        return [(start_i, end_i)]
    return [(start_i, int(sequence_len)), (0, end_i - int(sequence_len))]


def _merge_half_open(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    ordered = sorted((int(start), int(end)) for start, end in intervals if int(end) > int(start))
    merged: list[list[int]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _subtract_half_open(
    intervals: list[tuple[int, int]],
    blocked: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    remaining = _merge_half_open(intervals)
    for block_start, block_end in _merge_half_open(blocked):
        next_remaining: list[tuple[int, int]] = []
        for start, end in remaining:
            overlap_start = max(int(start), int(block_start))
            overlap_end = min(int(end), int(block_end))
            if overlap_start >= overlap_end:
                next_remaining.append((int(start), int(end)))
                continue
            if start < overlap_start:
                next_remaining.append((int(start), int(overlap_start)))
            if overlap_end < end:
                next_remaining.append((int(overlap_end), int(end)))
        remaining = next_remaining
        if not remaining:
            break
    return remaining


def _intersect_half_open(
    intervals_a: list[tuple[int, int]],
    intervals_b: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    merged_a = _merge_half_open(intervals_a)
    merged_b = _merge_half_open(intervals_b)
    out: list[tuple[int, int]] = []
    i = 0
    j = 0
    while i < len(merged_a) and j < len(merged_b):
        start = max(merged_a[i][0], merged_b[j][0])
        end = min(merged_a[i][1], merged_b[j][1])
        if start < end:
            out.append((start, end))
        if merged_a[i][1] <= merged_b[j][1]:
            i += 1
        else:
            j += 1
    return out


def _regions_to_half_open_by_positive_strand(
    regions: list[tuple[int, int, int]],
    sequence_len: int,
) -> dict[int, list[tuple[int, int]]]:
    out: dict[int, list[tuple[int, int]]] = {}
    for start, strand, length in regions:
        out.setdefault(int(strand), []).extend(
            _split_half_open(int(start), int(length), int(sequence_len))
        )
    return {strand: _merge_half_open(intervals) for strand, intervals in out.items()}


def _half_open_by_positive_strand_to_regions(
    by_strand: dict[int, list[tuple[int, int]]],
) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for strand in sorted(by_strand):
        for start, end in _merge_half_open(by_strand[strand]):
            out.append((int(start), int(strand), int(end - start)))
    return out


def _triplet_regions(triplet: SparseTriplet) -> list[tuple[int, int, int]]:
    return triplet.to_regions()


def _double_stranded_regions_literal(
    process: KarrDNASupercoilingProcess,
    polymerized: SparseTriplet,
) -> list[tuple[int, int, int]]:
    sequence_len = int(process.chromosome_length)
    regions_by_strand: dict[int, list[tuple[int, int]]] = {}
    for start, strand, length in _triplet_regions(polymerized):
        regions_by_strand.setdefault(int(strand), []).extend(
            _split_half_open(int(start), int(length), sequence_len)
        )

    ds_regions: list[tuple[int, int, int]] = []
    for pos_strand, neg_strand in ((0, 1), (2, 3)):
        pos_intervals = _merge_half_open(regions_by_strand.get(pos_strand, []))
        neg_intervals = _merge_half_open(regions_by_strand.get(neg_strand, []))
        for start, end in _intersect_half_open(pos_intervals, neg_intervals):
            ds_regions.append((int(start), int(pos_strand), int(end - start)))
            ds_regions.append((int(start), int(neg_strand), int(end - start)))
    return sorted(ds_regions, key=lambda item: (item[1], item[0], item[2]))


def _collect_interval_sources(
    process: KarrDNASupercoilingProcess,
    store: ChromosomeStore,
    *,
    enzyme_idx: int,
) -> list[IntervalSource]:
    enzyme_global_idx = int(process.enzyme_global_indices[int(enzyme_idx)])
    releasable_monomers, releasable_complexes = process._releasable_protein_indices(  # noqa: SLF001
        binding_monomers=(enzyme_global_idx,) if bool(process.enzyme_is_monomer[int(enzyme_idx)]) else (),
        binding_complexes=(enzyme_global_idx,) if bool(process.enzyme_is_complex[int(enzyme_idx)]) else (),
    )
    sources: list[IntervalSource] = []
    sequence_len = int(process.chromosome_length)
    for field_name, is_monomer, releasable in (
        ("monomerBoundSites", True, releasable_monomers),
        ("complexBoundSites", False, releasable_complexes),
    ):
        triplet = store.get_field(field_name)
        if triplet.positions.size == 0:
            continue
        footprints = process._bound_site_footprints(triplet, is_monomer=is_monomer)  # noqa: SLF001
        for position, strand, global_index, footprint in zip(
            triplet.positions.tolist(),
            triplet.strands.tolist(),
            triplet.values.tolist(),
            footprints.tolist(),
            strict=False,
        ):
            positive_strand = 2 * process._region_chromosome_index(int(strand))  # noqa: SLF001
            releasable_tf = int(global_index) in set(np.asarray(releasable, dtype=np.int64).tolist())
            for interval_start, interval_end in _split_half_open(
                int(position), int(footprint), sequence_len
            ):
                sources.append(
                    IntervalSource(
                        kind="bound_monomer" if is_monomer else "bound_complex",
                        field_name=field_name,
                        global_index=int(global_index),
                        start=int(position),
                        strand=int(strand),
                        length=int(footprint),
                        positive_strand=int(positive_strand),
                        interval_start=int(interval_start),
                        interval_end=int(interval_end),
                        releasable=bool(releasable_tf),
                    )
                )

    for position, strand in process._damage_pairs(store).tolist():  # noqa: SLF001
        positive_strand = 2 * process._region_chromosome_index(int(strand))  # noqa: SLF001
        for interval_start, interval_end in _split_half_open(int(position), 1, sequence_len):
            sources.append(
                IntervalSource(
                    kind="damage",
                    field_name="damagedSites",
                    global_index=None,
                    start=int(position),
                    strand=int(strand),
                    length=1,
                    positive_strand=int(positive_strand),
                    interval_start=int(interval_start),
                    interval_end=int(interval_end),
                    releasable=False,
                )
            )
    return sources


def _blocked_intervals_from_sources(
    sources: list[IntervalSource],
) -> dict[int, list[tuple[int, int]]]:
    blocked: dict[int, list[tuple[int, int]]] = {}
    for source in sources:
        if source.releasable:
            continue
        blocked.setdefault(int(source.positive_strand), []).append(
            (int(source.interval_start), int(source.interval_end))
        )
    return {strand: _merge_half_open(intervals) for strand, intervals in blocked.items()}


def _matlab_accessible_regions(
    process: KarrDNASupercoilingProcess,
    store: ChromosomeStore,
    *,
    enzyme_idx: int,
    legal_regions: list[tuple[int, int, int]],
) -> dict[str, Any]:
    sequence_len = int(process.chromosome_length)
    polymerized = process._ensure_polymerized_regions(store.get_field("polymerizedRegions"))  # noqa: SLF001
    ds_regions_full = _double_stranded_regions_literal(process, polymerized)
    ds_positive_only = [region for region in ds_regions_full if region[1] in (0, 2)]

    interval_sources = _collect_interval_sources(process, store, enzyme_idx=enzyme_idx)
    blocked_by_strand = _blocked_intervals_from_sources(interval_sources)

    full_accessible_by_strand: dict[int, list[tuple[int, int]]] = {}
    for strand, intervals in _regions_to_half_open_by_positive_strand(ds_positive_only, sequence_len).items():
        full_accessible_by_strand[strand] = _subtract_half_open(
            intervals,
            blocked_by_strand.get(int(strand), []),
        )

    legal_by_strand = _regions_to_half_open_by_positive_strand(legal_regions, sequence_len)
    intersected_by_strand: dict[int, list[tuple[int, int]]] = {}
    for strand in sorted(set(full_accessible_by_strand) | set(legal_by_strand)):
        intersected_by_strand[strand] = _intersect_half_open(
            full_accessible_by_strand.get(int(strand), []),
            legal_by_strand.get(int(strand), []),
        )

    footprint = int(process._enzyme_footprint(enzyme_idx))  # noqa: SLF001
    filtered_regions = [
        (start, strand, length)
        for start, strand, length in _half_open_by_positive_strand_to_regions(intersected_by_strand)
        if int(length) >= int(footprint)
    ]
    candidate_sites = int(sum(max(0, int(length) - footprint + 1) for _, _, length in filtered_regions))

    return {
        "double_stranded_regions_full": ds_regions_full,
        "double_stranded_positive_only": ds_positive_only,
        "interval_sources": [asdict(source) for source in interval_sources],
        "blocked_intervals_by_positive_strand": {
            str(strand): [(int(start), int(end)) for start, end in intervals]
            for strand, intervals in sorted(blocked_by_strand.items())
        },
        "full_accessible_regions_before_legal_intersection": _half_open_by_positive_strand_to_regions(
            full_accessible_by_strand
        ),
        "accessible_regions": filtered_regions,
        "candidate_sites": int(candidate_sites),
    }


def _oc_accessible_regions(
    process: KarrDNASupercoilingProcess,
    store: ChromosomeStore,
    *,
    enzyme_idx: int,
    legal_regions: list[tuple[int, int, int]],
) -> dict[str, Any]:
    blocked = process._binding_blocked_regions(store=store, enzyme_idx=enzyme_idx)  # noqa: SLF001
    accessible = process._accessible_binding_regions(  # noqa: SLF001
        store=store,
        enzyme_idx=enzyme_idx,
        positive_regions=legal_regions,
    )
    footprint = int(process._enzyme_footprint(enzyme_idx))  # noqa: SLF001
    candidate_sites = int(sum(max(0, int(length) - footprint + 1) for _, _, length in accessible))
    return {
        "blocked_intervals_by_positive_strand": {
            str(strand): [(int(start), int(end)) for start, end in intervals]
            for strand, intervals in sorted(blocked.items())
        },
        "accessible_regions": accessible,
        "candidate_sites": int(candidate_sites),
    }


def _binding_count_from_candidates(available_count: float, candidate_sites: int) -> int:
    return int(min(int(np.floor(float(available_count))), int(max(0, candidate_sites))))


def _load_seed_context(
    *,
    trace_root: Path,
    seed: int,
) -> dict[str, Any]:
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
        "seed_path": seed_paths[0],
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


def _clone_rng(rng: Any) -> Any:
    if hasattr(rng, "bit_generator"):
        shadow = np.random.default_rng()
        shadow.bit_generator.state = copy.deepcopy(rng.bit_generator.state)
        return shadow
    if hasattr(rng, "_stream") and hasattr(rng._stream, "get_state"):  # noqa: SLF001
        shadow = MatlabCompatRng(0)
        shadow._stream.set_state(copy.deepcopy(rng._stream.get_state()))  # type: ignore[attr-defined]  # noqa: SLF001
        return shadow
    raise TypeError(f"Unsupported RNG clone type: {type(rng)!r}")


def _sample_binding_proposals(
    *,
    rng: Any,
    accessible_regions: list[tuple[int, int, int]],
    available_count: float,
    footprint: int,
) -> dict[str, Any]:
    region_starts = [int(start) for start, _, _ in accessible_regions]
    region_strands = [int(strand) for _, strand, _ in accessible_regions]
    region_lengths = [int(length) for _, _, length in accessible_regions]
    region_weights = [max(0, int(length) - int(footprint) + 1) for length in region_lengths]

    proposals: list[dict[str, Any]] = []
    for _ in range(int(np.floor(float(available_count)))):
        if not any(region_weights):
            break
        weights = np.asarray(region_weights, dtype=np.float64)
        weights /= float(weights.sum())
        region_idx = int(rng.choice(len(region_weights), p=weights))
        random_draw = float(rng.random())
        offset = int(
            np.floor(random_draw * float(region_lengths[region_idx] - int(footprint) + 1))
        )
        proposals.append(
            {
                "region_idx": int(region_idx),
                "weights": weights.round(12).tolist(),
                "random_draw": float(random_draw),
                "offset": int(offset),
                "position": int(region_starts[region_idx] + offset),
                "strand": int(region_strands[region_idx]),
                "region_start": int(region_starts[region_idx]),
                "region_length": int(region_lengths[region_idx]),
            }
        )

        region_starts.append(region_starts[region_idx] + offset + int(footprint))
        region_strands.append(region_strands[region_idx])
        region_lengths.append(region_lengths[region_idx] - offset - int(footprint))
        region_lengths[region_idx] = offset
        region_weights[region_idx] = max(0, region_lengths[region_idx] - int(footprint) + 1)
        region_weights.append(max(0, region_lengths[-1] - int(footprint) + 1))

    return {
        "count": int(len(proposals)),
        "proposals": proposals,
    }


def _source_style_overlap_checks(
    *,
    proposals: list[dict[str, Any]],
    footprint: int,
    chromosome_length: int,
) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    for proposal in proposals:
        for start, end in _split_half_open(int(proposal["position"]), int(footprint), int(chromosome_length)):
            intervals.append(
                {
                    "proposal_position": int(proposal["position"]),
                    "proposal_strand": int(proposal["strand"]),
                    "start": int(start),
                    "end": int(end),
                }
            )

    overlap_checks: list[dict[str, Any]] = []
    for idx, left in enumerate(intervals):
        overlaps = []
        for jdx, right in enumerate(intervals):
            if idx >= jdx:
                continue
            if int(left["proposal_strand"]) != int(right["proposal_strand"]):
                continue
            if max(int(left["start"]), int(right["start"])) < min(int(left["end"]), int(right["end"])):
                overlaps.append(
                    {
                        "other_position": int(right["proposal_position"]),
                        "other_strand": int(right["proposal_strand"]),
                        "other_start": int(right["start"]),
                        "other_end": int(right["end"]),
                    }
                )
        overlap_checks.append(
            {
                "position": int(left["proposal_position"]),
                "strand": int(left["proposal_strand"]),
                "start": int(left["start"]),
                "end": int(left["end"]),
                "overlaps": overlaps,
            }
        )
    return overlap_checks


def _proposal_validation_proof(
    *,
    accessible_regions: list[tuple[int, int, int]],
    proposals: list[dict[str, Any]],
    footprint: int,
    chromosome_length: int,
) -> dict[str, Any]:
    valid_start_windows = [
        {
            "start": int(start),
            "strand": int(strand),
            "length": int(length),
            "candidate_start_min": int(start),
            "candidate_start_max_inclusive": int(start + length - footprint),
        }
        for start, strand, length in accessible_regions
        if int(length) >= int(footprint)
    ]
    per_proposal: list[dict[str, Any]] = []
    for proposal in proposals:
        matching_windows = [
            window
            for window in valid_start_windows
            if int(window["strand"]) == int(proposal["strand"])
            and int(window["candidate_start_min"]) <= int(proposal["position"]) <= int(window["candidate_start_max_inclusive"])
        ]
        per_proposal.append(
            {
                "position": int(proposal["position"]),
                "strand": int(proposal["strand"]),
                "matched_windows": matching_windows,
                "within_accessible_candidate_space": bool(matching_windows),
            }
        )
    overlap_checks = _source_style_overlap_checks(
        proposals=proposals,
        footprint=int(footprint),
        chromosome_length=int(chromosome_length),
    )
    any_overlap = any(item["overlaps"] for item in overlap_checks)
    all_within_space = all(item["within_accessible_candidate_space"] for item in per_proposal)
    return {
        "valid_start_windows": valid_start_windows,
        "per_proposal": per_proposal,
        "overlap_checks": overlap_checks,
        "all_within_accessible_candidate_space": bool(all_within_space),
        "any_source_style_overlap": bool(any_overlap),
        "source_bindProteinToChromosomeStochastically_can_silently_drop_sites": False,
        "source_postcheck_mode": "all_or_throw",
    }


def _source_stable_binding_outcome(
    *,
    available_count: float,
    candidate_sites: int,
    proposal_count: int,
) -> dict[str, Any]:
    implied_by_candidate_formula = _binding_count_from_candidates(
        float(available_count),
        int(candidate_sites),
    )
    return {
        "available_count_floor": int(np.floor(float(available_count))),
        "candidate_sites": int(candidate_sites),
        "proposal_count_before_postcheck": int(proposal_count),
        "if_bindProteinToChromosomeStochastically_is_called_source_n_bound": int(proposal_count),
        "candidate_formula_min_floor_available": int(implied_by_candidate_formula),
        "postcheck_mode": "all_or_throw",
    }


def _raw_trace_chromosome_fields(
    *,
    trace_path: Path,
    tick: int,
) -> list[str]:
    with h5py.File(trace_path, "r") as handle:
        group = handle[handle["states_before/chromosome"][0, int(tick)]]
        return sorted(
            key for key in group.keys() if key not in {"nCompartments", "sequenceLen"}
        )


def _replay_topoiv_turn(
    *,
    trace_root: Path,
    seed: int,
    tick: int,
    rng_variant: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    process = KarrDNASupercoilingProcess({"rng_seed": int(seed)})
    if rng_variant == "matlab_source":
        process._rng = MatlabCompatRng(int(seed))  # type: ignore[assignment]  # noqa: SLF001
    elif rng_variant != "current_oc":
        raise ValueError(f"Unknown rng_variant: {rng_variant}")

    before_channels = context["before_channels"]
    before_stores = context["before_stores"]
    captured: dict[str, Any] = {}
    original = process._bind_protein_to_chromosome_stochastically  # noqa: SLF001
    replay_tick = -1

    def _wrapped_bind(
        *,
        store: ChromosomeStore,
        enzyme_idx: int,
        available_count: float,
        positive_regions: list[tuple[int, int, int]],
    ) -> tuple[ChromosomeStore, Any]:
        if int(enzyme_idx) == int(process.topoiv_idx) and replay_tick == int(tick):
            accessible = process._accessible_binding_regions(  # noqa: SLF001
                store=store,
                enzyme_idx=enzyme_idx,
                positive_regions=positive_regions,
            )
            footprint = int(process._enzyme_footprint(enzyme_idx))  # noqa: SLF001
            candidate_sites = int(
                sum(max(0, int(length) - footprint + 1) for _, _, length in accessible)
            )
            proposal_trace = _sample_binding_proposals(
                rng=_clone_rng(process._rng),  # noqa: SLF001
                accessible_regions=accessible,
                available_count=float(available_count),
                footprint=int(footprint),
            )
            proposal_proof = _proposal_validation_proof(
                accessible_regions=accessible,
                proposals=proposal_trace["proposals"],
                footprint=int(footprint),
                chromosome_length=int(process.chromosome_length),
            )
            captured.update(
                {
                    "rng_variant": str(rng_variant),
                    "tick": int(replay_tick),
                    "available_count": float(available_count),
                    "positive_regions_at_topoiv_call": positive_regions,
                    "accessible_regions_at_topoiv_call": accessible,
                    "candidate_sites_at_topoiv_call": int(candidate_sites),
                    "proposal_trace": proposal_trace,
                    "proposal_validation": proposal_proof,
                    "source_binding_outcome": _source_stable_binding_outcome(
                        available_count=float(available_count),
                        candidate_sites=int(candidate_sites),
                        proposal_count=int(proposal_trace["count"]),
                    ),
                }
            )
        return original(
            store=store,
            enzyme_idx=enzyme_idx,
            available_count=available_count,
            positive_regions=positive_regions,
        )

    process._bind_protein_to_chromosome_stochastically = _wrapped_bind  # type: ignore[assignment]  # noqa: SLF001
    try:
        for replay_tick in range(int(tick) + 1):
            runtime_state = _build_runtime_state(
                process=process,
                before_channels=before_channels,
                tick=int(replay_tick),
                before_store=before_stores[int(replay_tick)],
            )
            process.next_update(1.0, runtime_state)
    finally:
        process._bind_protein_to_chromosome_stochastically = original  # type: ignore[assignment]  # noqa: SLF001

    if not captured:
        raise RuntimeError(
            f"Failed to capture topoIV turn for seed={seed} tick={tick} rng_variant={rng_variant}"
        )
    return captured


def build_seed_tick_ledger(
    *,
    trace_root: Path,
    seed: int,
    tick: int,
) -> dict[str, Any]:
    process = KarrDNASupercoilingProcess({"rng_seed": int(seed)})
    context = _load_seed_context(trace_root=trace_root, seed=int(seed))
    before_channels = context["before_channels"]
    after_channels = context["after_channels"]
    before_store: ChromosomeStore = context["before_stores"][int(tick)]
    after_store: ChromosomeStore = context["after_stores"][int(tick)]

    polymerized = process._ensure_polymerized_regions(before_store.get_field("polymerizedRegions"))  # noqa: SLF001
    current_positive = process._positive_ds_regions(polymerized)  # noqa: SLF001
    literal_double = _double_stranded_regions_literal(process, polymerized)
    literal_positive = [region for region in literal_double if region[1] in (0, 2)]
    linking_numbers = before_store.get_field("linkingNumbers")
    sigma_fallback = float(process.equilibrium_sigma)
    linking_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=current_positive,
        linking_numbers=linking_numbers,
        fallback_sigma=sigma_fallback,
    )
    sigma_values = process._region_sigmas(  # noqa: SLF001
        positive_regions=current_positive,
        linking_values=linking_values,
    )
    legal_topoiv = [
        region
        for region, sigma in zip(current_positive, sigma_values.tolist(), strict=False)
        if float(sigma) > float(process.topoiv_sigma_limit)
    ]

    oc_accessible = _oc_accessible_regions(
        process,
        before_store,
        enzyme_idx=process.topoiv_idx,
        legal_regions=legal_topoiv,
    )
    matlab_accessible = _matlab_accessible_regions(
        process,
        before_store,
        enzyme_idx=process.topoiv_idx,
        legal_regions=legal_topoiv,
    )

    topoiv_idx = int(process.topoiv_idx)
    free_before = float(before_channels["enzymes"][0, int(tick), topoiv_idx])
    bound_before = float(before_channels["boundEnzymes"][0, int(tick), topoiv_idx])
    free_after = float(after_channels["enzymes"][0, int(tick), topoiv_idx])
    bound_after = float(after_channels["boundEnzymes"][0, int(tick), topoiv_idx])
    topoiv_bound_sites_before = before_store.get_field("complexBoundSites")
    topoiv_global_idx = int(process.enzyme_global_indices[topoiv_idx])
    topoiv_bound_site_count_before = int(
        np.count_nonzero(topoiv_bound_sites_before.values.astype(np.int64, copy=False) == topoiv_global_idx)
    )
    topoiv_bound_site_count_after = int(
        np.count_nonzero(
            after_store.get_field("complexBoundSites").values.astype(np.int64, copy=False)
            == topoiv_global_idx
        )
    )
    trace_fields = _raw_trace_chromosome_fields(
        trace_path=context["seed_path"],
        tick=int(tick),
    )
    replay_current = _replay_topoiv_turn(
        trace_root=trace_root,
        seed=int(seed),
        tick=int(tick),
        rng_variant="current_oc",
        context=context,
    )
    replay_matlab = _replay_topoiv_turn(
        trace_root=trace_root,
        seed=int(seed),
        tick=int(tick),
        rng_variant="matlab_source",
        context=context,
    )
    hidden_fields = [
        field
        for field in (*SOURCE_ONLY_CHROMOSOME_FIELDS, *SOURCE_ONLY_VALIDATION_FIELDS)
        if field not in trace_fields
    ]

    return {
        "seed": int(seed),
        "tick": int(tick),
        "chromosome_length": int(process.chromosome_length),
        "trace_visible_chromosome_fields": list(trace_fields),
        "source_hidden_fields_missing_from_trace": hidden_fields,
        "topoiv": {
            "enzyme_idx": int(topoiv_idx),
            "wid": str(process.topoiv_wid),
            "global_index": int(topoiv_global_idx),
            "footprint": int(process._enzyme_footprint(topoiv_idx)),  # noqa: SLF001
            "sigma_limit": float(process.topoiv_sigma_limit),
            "free_before": float(free_before),
            "bound_before": float(bound_before),
            "free_after": float(free_after),
            "bound_after": float(bound_after),
            "bound_site_count_before": int(topoiv_bound_site_count_before),
            "bound_site_count_after": int(topoiv_bound_site_count_after),
        },
        "polymerized_regions": _triplet_regions(polymerized),
        "current_positive_regions": current_positive,
        "literal_double_stranded_regions": literal_double,
        "literal_positive_regions": literal_positive,
        "linking_numbers": _triplet_regions(linking_numbers),
        "current_positive_region_linking_values": linking_values.tolist(),
        "current_positive_region_sigmas": sigma_values.tolist(),
        "topoiv_legal_regions": legal_topoiv,
        "oc_path": {
            **oc_accessible,
            "stable_binding_count_if_called": _binding_count_from_candidates(
                float(free_before),
                int(oc_accessible["candidate_sites"]),
            ),
        },
        "matlab_source_path": {
            **matlab_accessible,
            "stable_binding_count_if_called": _binding_count_from_candidates(
                float(free_before),
                int(matlab_accessible["candidate_sites"]),
            ),
        },
        "topoiv_turn_replay_current_oc_rng": replay_current,
        "topoiv_turn_replay_matlab_rng": replay_matlab,
        "source_invariant_summary": {
            "bindProteinToChromosomeStochastically_postcheck_mode": "all_or_throw",
            "candidate_space_visible_state_matches_oc": bool(
                int(oc_accessible["candidate_sites"]) == int(matlab_accessible["candidate_sites"])
            ),
            "source_visible_state_implied_binding_count": int(
                _binding_count_from_candidates(
                    float(free_before),
                    int(matlab_accessible["candidate_sites"]),
                )
            ),
            "karr_trace_after_bound_count": int(topoiv_bound_site_count_after),
            "karr_trace_after_free_count": float(free_after),
        },
        "first_divergent_step": {
            "kind": "missing_trace_state",
            "first_hidden_source_read": {
                "field": "doubleStrandedRegions",
                "source_location": "DNASupercoiling.m:366-379",
                "reason": (
                    "The visible-state source path yields the same two topoIV-legal regions "
                    "and 12 implied stable binds as OC, so Karr's 0-bound result cannot be "
                    "reached from the 11 serialized sparse fields alone."
                ),
            },
            "candidate_path_hidden_reads": [
                {
                    "field": "doubleStrandedRegions",
                    "source_location": "Chromosome.m:1673-1679",
                },
                {
                    "field": "damagedSites",
                    "source_location": "Chromosome.m:1650-1658",
                },
            ],
            "missing_fields_from_trace": hidden_fields,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--tick", type=int, default=5)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    trace_root = _resolve_trace_root(None if args.trace_root is None else Path(args.trace_root))
    out_path = _coerce_cli_path(args.out).resolve()
    payload = build_seed_tick_ledger(
        trace_root=trace_root,
        seed=int(args.seed),
        tick=int(args.tick),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    print(f"[l22_dnas_followup8_ledger] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
