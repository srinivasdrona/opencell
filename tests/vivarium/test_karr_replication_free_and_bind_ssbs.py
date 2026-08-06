"""Opus G1 item 5: standalone tests for `free_and_bind_ssbs`'s candidate-
binding-site scoping fix (the c1/`_num_lagging_template_bound_ssbs`-
matching fork-window rewrite -- see the method's own docstring/comments
for the full Karr citation chain: `freeAndBindSSBs`, Replication.m:958-
1013; `getAccessibleRegions`/`calcSingleStrandedRegions`, Chromosome.m:
1608-1657/3133-3178).

These tests prove two things the prior (`_unpolymerized_regions_for_strand`
-over-all-4-strands) implementation got wrong:
  1. Candidate SSB sites must NEVER appear on the Okazaki-fragment daughter
     strands (`lagging_strand_indexs`, 0-based {1,2}) -- there is no
     physical ssDNA there, only "not yet synthesized" DNA.
  2. Candidate SSB sites on the leading template strands ({0,3}) must be
     confined to the real fork ssDNA window (helicase <-> lagging-fragment
     boundary, pulled in by the leading/lagging complex footprint margins)
     -- not the whole-genome complement of `polymerizedRegions`.

The real-oracle-state regression test (`test_no_ssb_sites_ever_bind_daughter_
strands_across_oracle_ticks`) drives `free_and_bind_ssbs` against the SAME
real, hash-pinned seed0 `states_before` snapshots the seed0 topology
diagnostic uses, at the tick set Opus specifically named (22, 31, 52, 76,
91, 92) -- reusing `_build_tick_state` from
`test_karr_replication_seed0_topology_diagnostic.py` rather than
duplicating the trace-loading plumbing. No `trace_hint`/oracle-after value
is ever read (adjudication #7).
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

from l2_replay_common import forbid_sut_oracle_file_io, resolve_trace_path
from test_karr_replication_seed0_topology_diagnostic import _build_tick_state

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess


@pytest.fixture(scope="module")
def process() -> KarrReplicationProcess:
    return KarrReplicationProcess({"rng_seed": 0})


def _bound_sites(process: KarrReplicationProcess, entries: list[tuple[int, int, int]]) -> SparseTriplet:
    return SparseTriplet.from_regions(entries, shape=process.chromosome_shape)


def _empty_store(process: KarrReplicationProcess, complex_bound_sites: SparseTriplet) -> ChromosomeStore:
    store = ChromosomeStore(shape=process.chromosome_shape)
    store.set_field("complexBoundSites", complex_bound_sites)
    store.set_field("polymerizedRegions", SparseTriplet.empty(*process.chromosome_shape))
    store.set_field("strandBreaks", SparseTriplet.empty(*process.chromosome_shape))
    return store


def _daughter_strands(process: KarrReplicationProcess) -> set[int]:
    return {int(process.lagging_strand_indexs[0]), int(process.lagging_strand_indexs[1])}


def _template_strands(process: KarrReplicationProcess) -> set[int]:
    return {int(process.leading_strand_indexs[0]), int(process.leading_strand_indexs[1])}


# ----------------------------------------------------------------------
# Hand-built scenario: both forks active, generous SSB4mer supply so every
# candidate window is fully saturated (deterministic branch -- `n_bindings
# >= len(candidate_positions)` skips `self._rng.choice` entirely).
# ----------------------------------------------------------------------


def _both_forks_scenario(process: KarrReplicationProcess) -> dict:
    lead0, lead1 = process.leading_strand_indexs
    a0 = process.primase_binding_locations[0]
    a1 = process.primase_binding_locations[1]
    fidx0 = 1
    starts0 = int(a0[fidx0 - 1])
    starts1 = int(a1[fidx0 - 1])
    lead_ftpt = process.polymerase_holoenzyme_footprint_bp
    lag_ftpt = int(process.enzyme_dna_footprints[process.enzyme_index_core_beta_clamp_primase])
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    lag0, lag1 = process.lagging_strand_indexs

    # Wide windows: column 0 helicase far below starts0; column 1 helicase
    # far above starts1.
    helicase_pos0 = starts0 - 5000
    helicase_pos1 = starts1 + 5000
    # Lagging polymerase bound exactly at each column's fragment-1 start
    # (progress == 0), matching `_advance_scenario_col0_fidx1`'s reverse-
    # lookup convention (`_lagging_position`, Replication.m:1483) -- without
    # this, `_okazaki_fragment_index` reads `lagging_pos == -1` and falls
    # back to the chromosome-end/oriC boundary instead of `starts0`/
    # `starts1`, understating the true fork window.
    lag_raw0 = (starts0 - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp
    lag_raw1 = (starts1 - cor_ftpt5) % process.sequence_len_bp

    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
        (lag_raw1, lag1, process.core_beta_clamp_primase_global_index),
    ]
    complex_bound_sites = _bound_sites(process, entries)
    store = _empty_store(process, complex_bound_sites)
    return {
        "store": store,
        "helicase_pos0": helicase_pos0,
        "helicase_pos1": helicase_pos1,
        "starts0": starts0,
        "starts1": starts1,
        "lead_ftpt": lead_ftpt,
        "lag_ftpt": lag_ftpt,
    }


def test_saturated_binding_never_lands_on_daughter_strands(
    process: KarrReplicationProcess,
) -> None:
    scenario = _both_forks_scenario(process)
    enzymes_next = {process.enzyme_wid_ssb4mer: 1e6}
    bound_next: dict = {}

    result = process.free_and_bind_ssbs(
        dt=0.0,
        chromosome_store=scenario["store"],
        enzymes_next=enzymes_next,
        bound_next=bound_next,
    )

    ssb_mask = result.values == int(process.ssb8mer_global_index)
    assert ssb_mask.any()
    daughter = _daughter_strands(process)
    ssb_strands = set(result.strands[ssb_mask].tolist())
    assert not (ssb_strands & daughter), (
        "SSB sites bound on the Okazaki-fragment daughter strands -- these "
        "are not-yet-synthesized DNA, not physical ssDNA."
    )
    assert ssb_strands <= _template_strands(process)


def test_saturated_binding_confined_to_fork_window_margins(
    process: KarrReplicationProcess,
) -> None:
    scenario = _both_forks_scenario(process)
    enzymes_next = {process.enzyme_wid_ssb4mer: 1e6}
    bound_next: dict = {}

    result = process.free_and_bind_ssbs(
        dt=0.0,
        chromosome_store=scenario["store"],
        enzymes_next=enzymes_next,
        bound_next=bound_next,
    )

    lead0, lead1 = process.leading_strand_indexs
    ssb_mask = result.values == int(process.ssb8mer_global_index)
    col0_positions = result.positions[ssb_mask & (result.strands == int(lead1))]
    col1_positions = result.positions[ssb_mask & (result.strands == int(lead0))]
    assert col0_positions.size > 0
    assert col1_positions.size > 0
    lo0 = scenario["helicase_pos0"] + scenario["lead_ftpt"] + 1
    hi0 = scenario["starts0"] - scenario["lag_ftpt"]
    assert np.all(col0_positions >= lo0)
    assert np.all(col0_positions < hi0)
    lo1 = scenario["starts1"] + scenario["lag_ftpt"] + 1
    hi1 = scenario["helicase_pos1"] - scenario["lead_ftpt"]
    assert np.all(col1_positions >= lo1)
    assert np.all(col1_positions < hi1)


def test_no_binding_capacity_leaves_sites_unchanged(process: KarrReplicationProcess) -> None:
    """`n_possible_ssb8mers < 1` (no free SSB4mer stock) must return the
    input triplet unchanged (no NEW ssb8mer sites fabricated) -- the
    pre-existing helicase entries the scenario seeds are untouched, but no
    ssb8mer entry may appear."""
    scenario = _both_forks_scenario(process)
    result = process.free_and_bind_ssbs(
        dt=0.0,
        chromosome_store=scenario["store"],
        enzymes_next={process.enzyme_wid_ssb4mer: 0.0},
        bound_next={},
    )
    assert int(np.count_nonzero(result.values == int(process.ssb8mer_global_index))) == 0



def test_zero_dt_no_dissociation_preserves_gate_satisfying_occupancy(
    process: KarrReplicationProcess,
) -> None:
    """With `dt=0` (`dissociation_p == 0` deterministically, regardless of
    RNG draws -- `random() < 0.0` is always false) and zero free SSB4mer
    stock (no new binding), an already gate-satisfying SSB occupancy must
    survive one `free_and_bind_ssbs` cycle completely unchanged: the
    bind/release cycle must never silently drain a satisfied gate below
    its threshold."""
    lead1 = int(process.leading_strand_indexs[1])
    a0 = process.primase_binding_locations[0]
    starts0 = int(a0[0])
    # 2-site, exactly-at-threshold window (matches the c1 test file's own
    # `_window_width_for_threshold(2)` convention: leadFtpt=lagFtpt=49,
    # ssbFtpt=145, ssbSpcg=30 -> floor((width-98)/175 - 2) == 2 for
    # width == 798).
    width = 798
    helicase0 = starts0 - width
    entries = [
        (helicase0, process.leading_strand_indexs[0], process.helicase_global_index),
        (helicase0 + 100, lead1, process.ssb8mer_global_index),
        (helicase0 + 300, lead1, process.ssb8mer_global_index),
    ]
    complex_bound_sites = _bound_sites(process, entries)
    store = _empty_store(process, complex_bound_sites)

    before_gate = process._are_lagging_strand_ssb_sites_bound(
        complex_bound_sites,
        helicase_pos=(helicase0, -1),
        fragment_index=(1, 0),
    )
    assert before_gate[0] is True

    result = process.free_and_bind_ssbs(
        dt=0.0,
        chromosome_store=store,
        enzymes_next={process.enzyme_wid_ssb4mer: 0.0},
        bound_next={},
    )

    after_gate = process._are_lagging_strand_ssb_sites_bound(
        result,
        helicase_pos=(helicase0, -1),
        fragment_index=(1, 0),
    )
    assert after_gate[0] is True
    ssb_mask = result.values == int(process.ssb8mer_global_index)
    assert int(np.count_nonzero(ssb_mask)) == 2


# ----------------------------------------------------------------------
# Real-oracle-state regression: the tick set Opus specifically named.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("tick", [22, 31, 52, 76, 91, 92])
def test_no_ssb_sites_ever_bind_daughter_strands_across_oracle_ticks(tick: int) -> None:
    """At each of Karr's real seed0 event ticks, feed the oracle's own
    `states_before` snapshot straight into `free_and_bind_ssbs` (via the
    same `_build_tick_state` helper the seed0 topology diagnostic uses)
    and assert every SSB site bound this call lands on a template strand
    ({0,3}), never a daughter strand ({1,2}) -- proving the scoping fix
    holds against real, non-synthetic replisome/fragment configurations,
    not just the hand-built scenarios above."""
    trace_path = resolve_trace_path("Replication")
    process, state = _build_tick_state(trace_path, tick)
    store = ChromosomeStore.from_state_mapping(state["chromosome"])
    enzymes_next = dict(state.get("enzymes", {}))
    bound_next: dict = {}

    with forbid_sut_oracle_file_io():
        result = process.free_and_bind_ssbs(
            dt=1.0,
            chromosome_store=store,
            enzymes_next=enzymes_next,
            bound_next=bound_next,
        )

    daughter = _daughter_strands(process)
    ssb_mask = result.values == int(process.ssb8mer_global_index)
    bound_strands = set(result.strands[ssb_mask].tolist())
    assert not (bound_strands & daughter), (
        f"tick {tick}: SSB sites bound on daughter strand(s) "
        f"{sorted(bound_strands & daughter)}"
    )
