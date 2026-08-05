"""Standalone tests for `merge_adjacent_regions`.

Exercises the touching-merge / overlap-fatal invariant in isolation from
any Replication process logic, per the staged implementation plan (stage
1 of 5: region-merge primitive before any enzyme/fixture-driven code).
Mirrors Karr's `Chromosome.mergeAdjacentRegions` /
`mergeOwnAdjacentRegions` (`Chromosome.m:~2536-2567`): touching same-strand
runs collapse into one entry; overlapping runs are a fatal corruption,
never silently resolved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.state.chromosome_store import SparseTriplet, merge_adjacent_regions

_SHAPE = (1000, 4)


def _triplet(regions: list[tuple[int, int, int]]) -> SparseTriplet:
    """Build a triplet directly (bypassing `from_regions`' zero-length
    filtering / `SparseTriplet.__post_init__`'s duplicate-summing
    canonicalization) so overlapping/duplicate test inputs survive
    unmodified into `merge_adjacent_regions` itself."""
    positions = np.asarray([r[0] for r in regions], dtype=np.int64)
    strands = np.asarray([r[1] for r in regions], dtype=np.int64)
    values = np.asarray([r[2] for r in regions], dtype=np.int64)
    obj = object.__new__(SparseTriplet)
    object.__setattr__(obj, "positions", positions)
    object.__setattr__(obj, "strands", strands)
    object.__setattr__(obj, "values", values)
    object.__setattr__(obj, "shape", _SHAPE)
    return obj


def test_touching_regions_merge_into_one() -> None:
    triplet = _triplet([(100, 0, 50), (150, 0, 30)])
    merged = merge_adjacent_regions(triplet)
    assert merged.to_regions() == [(100, 0, 80)]


def test_touching_regions_merge_regardless_of_input_order() -> None:
    triplet = _triplet([(150, 0, 30), (100, 0, 50)])
    merged = merge_adjacent_regions(triplet)
    assert merged.to_regions() == [(100, 0, 80)]


def test_non_touching_regions_are_preserved_distinct() -> None:
    triplet = _triplet([(100, 0, 50), (151, 0, 30)])
    merged = merge_adjacent_regions(triplet)
    assert merged.to_regions() == [(100, 0, 50), (151, 0, 30)]


def test_chain_of_three_touching_regions_merges_into_one() -> None:
    triplet = _triplet([(0, 1, 100), (100, 1, 200), (300, 1, 50)])
    merged = merge_adjacent_regions(triplet)
    assert merged.to_regions() == [(0, 1, 350)]


def test_overlap_raises_corrupt_error() -> None:
    triplet = _triplet([(100, 0, 60), (150, 0, 30)])  # 100..160 overlaps 150..180
    with pytest.raises(ValueError, match="corrupt"):
        merge_adjacent_regions(triplet)


def test_exact_duplicate_region_raises_corrupt_error() -> None:
    triplet = _triplet([(100, 0, 50), (100, 0, 50)])
    with pytest.raises(ValueError, match="corrupt"):
        merge_adjacent_regions(triplet)


def test_different_strands_never_merge_even_when_numerically_touching() -> None:
    triplet = _triplet([(100, 0, 50), (150, 1, 30)])
    merged = merge_adjacent_regions(triplet)
    assert sorted(merged.to_regions()) == sorted([(100, 0, 50), (150, 1, 30)])


def test_multiple_independent_merges_across_strands_in_one_call() -> None:
    triplet = _triplet(
        [
            (0, 0, 100),
            (100, 0, 50),  # merges with prior on strand 0 -> (0, 0, 150)
            (500, 2, 20),
            (520, 2, 10),  # merges with prior on strand 2 -> (500, 2, 30)
            (900, 3, 5),  # untouched singleton on strand 3
        ]
    )
    merged = merge_adjacent_regions(triplet)
    assert sorted(merged.to_regions()) == sorted([(0, 0, 150), (500, 2, 30), (900, 3, 5)])


def test_region_exceeding_chromosome_length_is_rejected_not_wrapped() -> None:
    # position + value > shape[0]: Karr's own CircularSparseMat representation
    # never stores a single entry that wraps past the origin (confirmed
    # against the real seed-0 oracle trace, where an origin-straddling bubble
    # is always two separate entries) -- so this must fail closed, not be
    # silently reinterpreted as a wrap.
    triplet = _triplet([(990, 0, 20)])  # 990 + 20 = 1010 > shape[0]=1000
    with pytest.raises(ValueError, match="corrupt"):
        merge_adjacent_regions(triplet)


def test_non_positive_length_is_rejected() -> None:
    triplet = _triplet([(100, 0, 0)])
    with pytest.raises(ValueError, match="corrupt"):
        merge_adjacent_regions(triplet)


def test_empty_triplet_merges_to_empty() -> None:
    triplet = SparseTriplet.empty(*_SHAPE)
    merged = merge_adjacent_regions(triplet)
    assert merged.to_regions() == []


def test_two_entries_straddling_origin_are_not_merged_across_the_wrap() -> None:
    # Matches the real seed-0 trace: an origin-centered bubble is stored as
    # two entries, one ending exactly at shape[0], one starting at 0 -- these
    # are logically adjacent through the circular origin but must NOT be
    # collapsed into a single wrapping entry (Karr's own representation never
    # does this either).
    triplet = _triplet([(990, 0, 10), (0, 0, 5)])  # 990..1000 and 0..5
    merged = merge_adjacent_regions(triplet)
    assert sorted(merged.to_regions()) == sorted([(990, 0, 10), (0, 0, 5)])


def test_merge_result_is_itself_a_valid_sparse_triplet() -> None:
    triplet = _triplet([(100, 0, 50), (150, 0, 30)])
    merged = merge_adjacent_regions(triplet)
    assert isinstance(merged, SparseTriplet)
    assert merged.shape == _SHAPE
    # Round-trips through the canonicalizing constructor without complaint.
    round_trip = SparseTriplet.from_state(merged.to_state(), shape=_SHAPE)
    assert round_trip.to_regions() == merged.to_regions()
