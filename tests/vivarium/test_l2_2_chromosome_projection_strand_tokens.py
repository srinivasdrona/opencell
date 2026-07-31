"""Sanity tests for `_chromosome_projection_component`'s `strand_<N>` tokens.

PROCESS_CATALOG.yaml's Replication row declares a 5-component primary
projection: `polymerizedRegions.delta_value_sum_strand_1..4` plus
`polymerizedRegions.delta_nnz`. The catalog's `strand_1..strand_4` naming
follows MATLAB's 1-based strand numbering (Replication.m uses
`leadingStrandIndexs`/`laggingStrandIndexs` as 1-based indices into the
4-strand chromosome), but `ChromosomeStore`/`SparseTriplet` always store
0-based strand indices (opencell/state/chromosome_store.py:226-231 subtracts
1 from every MATLAB-sourced `strands` array; karr_replication.py:385-386
does the same for the strand index fixtures). `_chromosome_projection_component`
must convert the 1-based catalog token to 0-based before comparing against
`SparseTriplet.strands`, or every token silently reads the wrong strand and
`strand_4` (0-based index 4) is permanently out of range and dead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


_SHAPE = (100, 4)


def _store_with_polymerized(regions: list[tuple[int, int, int]]) -> ChromosomeStore:
    """Build a ChromosomeStore with `polymerizedRegions` set from
    (position, 0-based strand, value) tuples."""
    store = ChromosomeStore(shape=_SHAPE)
    store.set_field(
        "polymerizedRegions",
        SparseTriplet.from_regions(
            [(pos, strand, val) for pos, strand, val in regions],
            shape=_SHAPE,
        ),
    )
    return store


def test_strand_1_token_reads_0_based_strand_0_not_strand_1() -> None:
    """Catalog token `strand_1` (MATLAB strand 1) must read 0-based strand 0."""
    before = _store_with_polymerized([])
    after = _store_with_polymerized([(0, 0, 10)])  # 0-based strand 0 only

    strand_1 = runner_helpers._chromosome_projection_component(
        "polymerizedRegions.delta_value_sum_strand_1", before, after
    )
    strand_2 = runner_helpers._chromosome_projection_component(
        "polymerizedRegions.delta_value_sum_strand_2", before, after
    )
    assert strand_1 == pytest.approx(10.0)
    assert strand_2 == pytest.approx(0.0)


@pytest.mark.parametrize("matlab_strand,zero_based_strand", [(1, 0), (2, 1), (3, 2), (4, 3)])
def test_each_catalog_strand_token_maps_to_its_0_based_index(
    matlab_strand: int, zero_based_strand: int
) -> None:
    before = _store_with_polymerized([])
    after = _store_with_polymerized([(0, zero_based_strand, 7)])

    value = runner_helpers._chromosome_projection_component(
        f"polymerizedRegions.delta_value_sum_strand_{matlab_strand}", before, after
    )
    assert value == pytest.approx(7.0), (
        f"catalog token strand_{matlab_strand} should read 0-based strand "
        f"{zero_based_strand}, got delta {value} instead of 7.0"
    )


def test_all_four_strands_map_exactly_once_no_dead_strand_4() -> None:
    """Every one of the 4 real strands must be reachable by exactly one of
    the catalog's strand_1..strand_4 tokens -- in particular strand_4 (the
    highest-numbered catalog token) must NOT be permanently dead (mapping to
    an out-of-range 0-based index 4, which never matches anything)."""
    before = _store_with_polymerized([])
    after = _store_with_polymerized(
        [(0, 0, 10), (0, 1, 20), (0, 2, 30), (0, 3, 40)]
    )

    seen_totals: dict[int, float] = {}
    for matlab_strand in (1, 2, 3, 4):
        value = runner_helpers._chromosome_projection_component(
            f"polymerizedRegions.delta_value_sum_strand_{matlab_strand}", before, after
        )
        seen_totals[matlab_strand] = value

    assert seen_totals == {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0}
    # Strand 4 (0-based index 3, the last valid strand) must show real,
    # nonzero activity -- it must not be a structurally dead component.
    assert seen_totals[4] != 0.0


def test_catalog_component_identically_zero_on_both_sides_is_detectable() -> None:
    """Anti-cheat / sanity check: if a catalog component is genuinely zero on
    BOTH the OC and Karr side across a full run, that must be distinguishable
    from a component that is only zero because of a strand-mapping bug (this
    test simulates the "component genuinely inactive" case directly so a
    caller comparing OC vs Karr nonzero-counts can tell the two apart)."""
    before = _store_with_polymerized([])
    # Only strands 0-2 (catalog strand_1..3) show activity; strand 3
    # (catalog strand_4) is genuinely never touched by either side.
    after = _store_with_polymerized([(0, 0, 5), (0, 1, 5), (0, 2, 5)])

    oc_component_4 = runner_helpers._chromosome_projection_component(
        "polymerizedRegions.delta_value_sum_strand_4", before, after
    )
    karr_component_4 = runner_helpers._chromosome_projection_component(
        "polymerizedRegions.delta_value_sum_strand_4", before, after
    )
    # Both genuinely zero: this is the symmetric "component inactive on both
    # sides" case that PRIMARY_ACTIVITY_MISSING gating must NOT flag (it only
    # fires on the asymmetric case, n_oc == 0 and n_karr > 0).
    assert oc_component_4 == 0.0
    assert karr_component_4 == 0.0
    # But strand_1..3 on the same before/after ARE active -- proving this
    # component's zero is a genuine biological zero, not a mapping bug that
    # silently zeroes every strand.
    for matlab_strand in (1, 2, 3):
        active = runner_helpers._chromosome_projection_component(
            f"polymerizedRegions.delta_value_sum_strand_{matlab_strand}", before, after
        )
        assert active != 0.0


def test_delta_nnz_and_delta_value_sum_unaffected_by_strand_fix() -> None:
    """The strand-index fix must not perturb the other projection ops."""
    before = _store_with_polymerized([(0, 0, 10)])
    after = _store_with_polymerized([(0, 0, 10), (5, 1, 3)])

    nnz = runner_helpers._chromosome_projection_component(
        "polymerizedRegions.delta_nnz", before, after
    )
    value_sum = runner_helpers._chromosome_projection_component(
        "polymerizedRegions.delta_value_sum", before, after
    )
    assert nnz == pytest.approx(1.0)
    assert value_sum == pytest.approx(3.0)


def test_repair_event_present_token_unaffected_by_strand_fix() -> None:
    """Non-strand meta-token must still work exactly as before."""
    before = ChromosomeStore(shape=_SHAPE)
    after = ChromosomeStore(shape=_SHAPE)
    after.set_field(
        "strandBreaks",
        SparseTriplet.from_regions([(0, 0, 1)], shape=_SHAPE),
    )
    value = runner_helpers._chromosome_projection_component(
        "repair_event_present", before, after
    )
    assert value == 1.0


def test_out_of_range_strand_token_beyond_catalog_range_reads_zero() -> None:
    """A hypothetical strand_5 token (0-based index 4) is genuinely out of
    range for a 4-strand chromosome and must read zero without raising --
    this documents the boundary the fix must respect (only strand_1..4 are
    valid catalog tokens; PROCESS_CATALOG.yaml never emits strand_5+)."""
    before = _store_with_polymerized([])
    after = _store_with_polymerized([(0, 0, 10), (0, 1, 20), (0, 2, 30), (0, 3, 40)])
    value = runner_helpers._chromosome_projection_component(
        "polymerizedRegions.delta_value_sum_strand_5", before, after
    )
    assert value == 0.0
