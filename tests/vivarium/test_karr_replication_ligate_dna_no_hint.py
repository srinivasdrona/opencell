"""Finding 5 (2026-08-05): focused tests for the no-hint substrate/
byproduct/ligation port -- `_ligate_dna_no_hint` (Replication.m:1220-1248)
plus the unwinding/polymerization byproduct credits (water demand,
ADP/phosphate/hydrogen unwinding byproducts, diphosphate polymerization
byproduct, Replication.m:875-946) that `next_update`'s real no-hint path
now applies. Every scenario below is seeded ONLY from hand-built
pre-state/fixture-derived constants -- no trace_hint, no oracle-after
data, no tick-targeted branches, no global RNG (any stochastic draw goes
through the process's own seeded `self._rng`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from test_karr_replication import (  # noqa: E402
    _active_replisome_base_state,
    _apply_update,
)

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess


def _strand_breaks_at(process: KarrReplicationProcess, positions_strands: list[tuple[int, int]]) -> SparseTriplet:
    return SparseTriplet(
        positions=np.asarray([p for p, _ in positions_strands], dtype=np.int64),
        strands=np.asarray([s for _, s in positions_strands], dtype=np.int64),
        values=np.asarray([1] * len(positions_strands), dtype=np.int64),
        shape=process.chromosome_shape,
    )


def test_ligate_dna_no_hint_noop_when_no_nicks() -> None:
    p = KarrReplicationProcess({})
    store = ChromosomeStore.from_state_mapping(
        {
            "polymerizedRegions": SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state(),
            "complexBoundSites": SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state(),
            "strandBreaks": SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state(),
        },
        shape=p.chromosome_shape,
    )
    enzymes_next = {p.enzyme_wid_ligase: 1000.0}
    substrates_next = {p.nad_wid: 1000.0}
    update: dict[str, Any] = {}
    p._ligate_dna_no_hint(
        chromosome_store=store,
        dt=1.0,
        enzymes_next=enzymes_next,
        substrates_next=substrates_next,
        update=update,
    )
    assert substrates_next[p.nad_wid] == 1000.0
    assert "chromosome" not in update


def test_ligate_dna_no_hint_nad_limited_rng_selection_is_insertion_order_invariant() -> None:
    """3 existing nicks, abundant ligase capacity, NAD=1 -- Karr's own
    `numReactions = min(numStrandBreaks, ligaseCapacity, nadAvailable)`
    (Replication.m:1227-1231) caps sealing at exactly 1. OC canonicalizes
    the candidate nick identities by `(strand, position)` and then uses
    the process RNG to choose which one to seal, so two sparse-triplet
    insertion orders with the same seed must seal the SAME physical nick."""
    nicks_a = [(5000, 1), (1000, 0), (3000, 1)]
    nicks_b = list(reversed(nicks_a))
    remaining_sets: list[list[tuple[int, int]]] = []

    for nicks in (nicks_a, nicks_b):
        p = KarrReplicationProcess({"rng_seed": 7})
        p.ligase_rate_per_s = 1000.0
        store = ChromosomeStore.from_state_mapping(
            {
                "polymerizedRegions": SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state(),
                "complexBoundSites": SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state(),
                "strandBreaks": _strand_breaks_at(p, nicks).to_state(),
            },
            shape=p.chromosome_shape,
        )
        enzymes_next = {p.enzyme_wid_ligase: 1000.0}
        substrates_next = {p.nad_wid: 1.0, p.nmn_wid: 0.0, p.amp_wid: 0.0, p.h_wid: 0.0}
        update: dict[str, Any] = {}
        p._ligate_dna_no_hint(
            chromosome_store=store,
            dt=1.0,
            enzymes_next=enzymes_next,
            substrates_next=substrates_next,
            update=update,
        )
        assert substrates_next[p.nad_wid] == 0.0
        assert substrates_next[p.nmn_wid] == 1.0
        assert substrates_next[p.amp_wid] == 1.0
        assert substrates_next[p.h_wid] == 1.0

        remaining = store.get_field("strandBreaks")
        remaining_positions_strands = sorted(
            zip(remaining.strands.tolist(), remaining.positions.tolist(), strict=True)
        )
        remaining_sets.append(remaining_positions_strands)
        assert update["chromosome"]["strandBreaks"]["positions"].tolist() == remaining.positions.tolist()
        assert update["chromosome"]["strandBreaks"]["strands"].tolist() == remaining.strands.tolist()

    assert remaining_sets[0] == remaining_sets[1]


def test_ligate_dna_no_hint_ligase_capacity_limited() -> None:
    """3 existing nicks, abundant NAD, ligase capacity exactly 1 (no
    fractional `stochasticRound` draw needed since `ligase_available *
    dt * ligase_rate_per_s` is chosen to be an exact integer) -- caps
    sealing at exactly 1 nick regardless of NAD/nick-count headroom."""
    p = KarrReplicationProcess({})
    p.ligase_rate_per_s = 1.0
    nicks = [(5000, 1), (1000, 0), (3000, 1)]
    store = ChromosomeStore.from_state_mapping(
        {
            "polymerizedRegions": SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state(),
            "complexBoundSites": SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state(),
            "strandBreaks": _strand_breaks_at(p, nicks).to_state(),
        },
        shape=p.chromosome_shape,
    )
    enzymes_next = {p.enzyme_wid_ligase: 1.0}
    substrates_next = {p.nad_wid: 1000.0, p.nmn_wid: 0.0, p.amp_wid: 0.0, p.h_wid: 0.0}
    update: dict[str, Any] = {}
    p._ligate_dna_no_hint(
        chromosome_store=store,
        dt=1.0,
        enzymes_next=enzymes_next,
        substrates_next=substrates_next,
        update=update,
    )
    assert substrates_next[p.nad_wid] == 999.0
    assert substrates_next[p.nmn_wid] == 1.0
    remaining = store.get_field("strandBreaks")
    assert remaining.values.size == 2


def test_no_hint_advance_credits_unwinding_and_polymerization_byproducts() -> None:
    """Full no-hint `next_update` path, real fixture-consistent active
    replisome: after one 1s tick at the default 100bp/s/column rate (200bp
    total advanced, 400 nt polymerized across both strands/columns), the
    ADP/phosphate/hydrogen unwinding byproducts must be exactly
    `total_advanced_bp` (matching the same `n` just consumed from
    ATP/water, Replication.m:925-930) and the diphosphate (PPi)
    polymerization byproduct must be exactly `total_polymerized_nt`
    (Replication.m:944-945) -- with abundant allocation so no scarcity
    scaling is in play."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p, replication_state="elongating", initial_substrate=1e9, allocated_override=alloc
    )
    update = p.next_update(1.0, state)

    total_advanced_bp = update["chromosome"]["fork_position_bp"]["left"] + update["chromosome"]["fork_position_bp"]["right"]
    assert total_advanced_bp == 200.0
    total_polymerized_nt = 2.0 * total_advanced_bp

    substrate_delta = update["substrates"]
    assert substrate_delta[p.atp_wid] == -total_advanced_bp
    assert substrate_delta[p.h2o_wid] == -total_advanced_bp
    assert substrate_delta[p.adp_wid] == total_advanced_bp
    assert substrate_delta[p.pi_wid] == total_advanced_bp
    assert substrate_delta[p.h_wid] == total_advanced_bp
    assert substrate_delta[p.ppi_wid] == total_polymerized_nt


def test_no_hint_advance_scales_down_when_water_is_the_scarce_resource() -> None:
    """Replication.m:944: `unwindLimits = min(unwinds, floor(unwinds /
    sum(unwinds) * min(atp, water)))` -- water genuinely gates the
    unwind/advance extent identically to ATP, not merely an unconditional
    post-hoc subtraction. Here ATP/dNTP allocation is abundant but water
    allocation is deliberately scarce (half of what an unconstrained
    200bp/tick advance would need) -- the real advance must come out
    proportionally smaller, exactly mirroring the existing ATP-scarcity
    test (`test_limited_allocation_scales_progress_proportionally`)."""
    p = KarrReplicationProcess({})
    desired = p._demand_from_advances(100, 100)
    scarce_water = float(desired[p.h2o_wid]) * 0.5
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    alloc[p.h2o_wid] = scarce_water
    state = _active_replisome_base_state(
        p, replication_state="elongating", initial_substrate=1e9, allocated_override=alloc
    )
    update = p.next_update(1.0, state)

    total_advanced_bp = (
        update["chromosome"]["fork_position_bp"]["left"] + update["chromosome"]["fork_position_bp"]["right"]
    )
    assert 0.0 < total_advanced_bp < 200.0
    # The reconciled real water demand must never exceed what was allocated.
    assert -update["substrates"][p.h2o_wid] <= scarce_water


def test_no_hint_advance_seals_preexisting_nick_and_never_loses_it_on_early_return() -> None:
    """End-to-end no-hint composition: a pre-existing single-strand nick
    (standing in for a PRIOR tick's own `terminateOkazakiFragment`
    hand-off, matching Karr's fixed-list ordering where `ligateDNA` only
    ever sees nicks from before this tick) is sealed by the real
    `next_update` path -- proving the ligation port is genuinely wired
    into the production no-hint path, not just unit-testable in
    isolation."""
    p = KarrReplicationProcess({})
    p.ligase_rate_per_s = 1000.0
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p, replication_state="elongating", initial_substrate=1e9, allocated_override=alloc
    )
    state["enzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["enzymes"][p.enzyme_wid_ligase] = 1000.0
    state["chromosome"]["strandBreaks"] = _strand_breaks_at(p, [(123456, 0)]).to_state()

    update = p.next_update(1.0, state)
    _apply_update(state, update, p)

    remaining = SparseTriplet.from_state(state["chromosome"]["strandBreaks"], shape=p.chromosome_shape)
    assert remaining.values.size == 0
    assert state["substrates"][p.nad_wid] == 1e9 - 1.0
    assert state["substrates"][p.nmn_wid] == 1e9 + 1.0
    assert state["substrates"][p.amp_wid] == 1e9 + 1.0
