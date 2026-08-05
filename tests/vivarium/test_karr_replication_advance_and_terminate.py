"""Standalone tests for the c3 (per-fragment fork advance) and termination/
handoff additions to `KarrReplicationProcess`:
`_terminate_okazaki_fragment_column`, `_bind_initial_lagging_polymerase`,
`_write_strand_break`, `_extend_polymerized_region`,
`_remove_point_complex`/`_add_point_complex`/`_move_point_complex`, and
`_advance_replication_forks`.

Literal ports of:
  * `unwindAndPolymerizeDNA` (Replication.m:692-945) -- whole-function
    elongating gate, first-fragment leading/lagging polymerase split
    bootstrap (707-727), per-column leading+helicase single-step advance
    (SSB-gated), lagging fragment-chunked advance.
  * `terminateOkazakiFragment` (Replication.m:1090-1213) -- gating
    (fragment complete + SSB sites bound + last-fragment-or-gap-and-backup-
    clamp-equality), lagging-polymerase release/rebind, backup-beta-clamp
    release/reload (non-last) or leading-strand complex identity swap
    (last), and the `strandBreaks` nick.

Per the adjudicated c3 scope: this port consumes the EXISTING, unchanged
per-tick dNTP/ATP advancement budget (`_demand_from_advances` and its
substrate-scaling caller are untouched) via Karr's literal fragment-
position/state-machine caps; it does not reimplement per-base
`polymerize()` sequence chemistry, and it does not introduce any new RNG
(initiation/termination site choice is source-deterministic).

`_advance_replication_forks` runs the lagging strand FIRST (chunked across
Okazaki-fragment boundaries, with inline termination), then advances the
leading strand + helicase capped at the ACTUAL bp lagging achieved this
tick (not the raw requested budget) -- a conservative, safe, zero-gap
stand-in for Karr's `limits`/Okazaki-loop leading-ahead-of-lagging distance
cap (whose full per-tick kinetics sub-step machinery is out of scope for
this port, adjudication #2); leading can never silently outrun lagging
within a tick, and the two are never double-counted into a single
`actual_left_bp`/`actual_right_bp` value.

All scenarios are constructed directly from the real fixture-derived
`primase_binding_locations`/footprint constants and hand-built
`complexBoundSites`/`polymerizedRegions` sparse triples -- no oracle trace
file is read anywhere in this file (adjudication #7: "no trace-after/
oracle-file access").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess, ReplicationTopologyError


@pytest.fixture(scope="module")
def process() -> KarrReplicationProcess:
    return KarrReplicationProcess({})


def _bound_sites(process: KarrReplicationProcess, entries: list[tuple[int, int, int]]) -> SparseTriplet:
    return SparseTriplet.from_regions(entries, shape=process.chromosome_shape)


def _empty_triplet(process: KarrReplicationProcess) -> SparseTriplet:
    return SparseTriplet.empty(*process.chromosome_shape)


def _ssb_positions(process: KarrReplicationProcess, lo: int, hi: int) -> list[int]:
    """Evenly-spaced SSB8mer positions filling `(lo, hi)`, spaced by the
    real fixture footprint+gap constants (matches the c1 test file's
    convention) -- enough sites to satisfy `_are_lagging_strand_ssb_sites_
    bound` for any window this file constructs."""
    step = process.ssb8mer_footprint_bp + process.ssb_complex_spacing_bp
    return list(range(lo, hi, step))


# ----------------------------------------------------------------------
# terminateOkazakiFragment: column 0, non-last fragment (fragment_index=1,
# whose lagging strand wraps past the sequence end -- Replication.m:1090-
# 1163).
# ----------------------------------------------------------------------


def _col0_nonlast_scenario(process: KarrReplicationProcess) -> dict:
    lead0, lead1 = process.leading_strand_indexs
    lag0, _lag1 = process.lagging_strand_indexs
    a0 = process.primase_binding_locations[0]
    fidx0 = 1

    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    helicase_pos0 = 570000
    helicase_pos1 = 9000
    lead_pol_pos0 = 300000
    lead_pol_pos1 = 300001

    # This fragment's lagging synthesis wraps past the chromosome's last
    # 0-based position (`sequence_len_bp - 1`) back to physical position 0;
    # `_okazaki_fragment_progress`'s `adj[0] = lagging_pos[0] + seq_len`
    # correction (triggered when `lagging_pos[0] < 0.5 * terc_position_bp`)
    # is what makes `progress == length` resolve at this physical position.
    lagging_pos0_completion = 0
    lag_raw0 = (lagging_pos0_completion - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp
    backup_clamp0 = int(a0[fidx0]) - (hol_ftpt - cor_ftpt5) + 1

    starts0_for_ssb = int(a0[fidx0 - 1])
    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lead_pol_pos0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (lead_pol_pos1, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
        (backup_clamp0, lag0, process.beta_clamp_global_index),
    ]
    for pos in _ssb_positions(process, helicase_pos0 + 5, starts0_for_ssb - 5):
        entries.append((pos, int(process.leading_strand_indexs[1]), process.ssb8mer_global_index))

    complex_bound_sites = _bound_sites(process, entries)
    polymerized = _empty_triplet(process)
    return {
        "complex_bound_sites": complex_bound_sites,
        "polymerized": polymerized,
        "backup_clamp0": backup_clamp0,
    }


def test_terminate_col0_nonlast_fragment_handoff(process: KarrReplicationProcess) -> None:
    scenario = _col0_nonlast_scenario(process)
    enzymes_next: dict = {}
    bound_next: dict = {}
    strand_breaks = _empty_triplet(process)

    new_cbs, new_strand_breaks, terminated = process._terminate_okazaki_fragment_column(
        0,
        complex_bound_sites=scenario["complex_bound_sites"],
        polymerized=scenario["polymerized"],
        strand_breaks=strand_breaks,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
    )

    assert terminated is True
    # The new lagging polymerase rebinds exactly at the released backup
    # clamp's position (Replication.m:1183-1193, non-last, column 0).
    assert process._lagging_polymerase_positions(new_cbs) == (scenario["backup_clamp0"], -1)
    # The backup beta-clamp slot is now empty (released, not replaced --
    # a fresh one is placed later by `_initiate_okazaki_fragments`).
    assert process._backup_beta_clamp_positions(new_cbs) == (-1, -1)
    # StrandBreaks nick: `fidx == 1` special case -> `sequence_len_bp - 1`.
    assert new_strand_breaks.to_regions() == [(process.sequence_len_bp - 1, 2, 1)]
    # Literal per-step pool deltas net out exactly (release lagging pol then
    # immediately rebind it: primase/core/core_beta_clamp_primase all net
    # to 0; only the backup beta-clamp's dimer->monomer release is a
    # genuine, un-paired net change). `core_beta_clamp_primase`/`beta_clamp`
    # are DNA-bound complex identities and their net deltas live on
    # `bound_next`, not `enzymes_next` (see `_terminate_okazaki_fragment_column`'s
    # docstring for the bound/free-pool ownership rule).
    assert bound_next[process.enzyme_wid_core_beta_clamp_primase] == 0.0
    assert enzymes_next[process.enzyme_wid_primase] == 0.0
    assert enzymes_next[process.enzyme_wid_core] == 0.0
    assert enzymes_next[process.enzyme_wid_beta_clamp_monomer] == 2.0
    assert bound_next[process.enzyme_wid_beta_clamp] == -1.0


def test_terminate_col0_stall_on_backup_clamp_equality_mismatch(process: KarrReplicationProcess) -> None:
    """A 1-bp-off backup-clamp position (`equality_ok` false) must be a
    legitimate stall: no mutation, `terminated=False` -- never force a
    termination the literal gate does not license."""
    lead0, lead1 = process.leading_strand_indexs
    lag0, _lag1 = process.lagging_strand_indexs
    a0 = process.primase_binding_locations[0]
    fidx0 = 1
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    helicase_pos0 = 570000
    helicase_pos1 = 9000
    lag_raw0 = (0 - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp
    wrong_backup_clamp0 = int(a0[fidx0]) - (hol_ftpt - cor_ftpt5) + 1 + 1  # off by 1 bp

    starts0_for_ssb = int(a0[fidx0 - 1])
    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (300000, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (300001, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
        (wrong_backup_clamp0, lag0, process.beta_clamp_global_index),
    ]
    for pos in _ssb_positions(process, helicase_pos0 + 5, starts0_for_ssb - 5):
        entries.append((pos, int(process.leading_strand_indexs[1]), process.ssb8mer_global_index))
    complex_bound_sites = _bound_sites(process, entries)
    polymerized = _empty_triplet(process)
    strand_breaks = _empty_triplet(process)
    enzymes_next: dict = {}

    new_cbs, new_strand_breaks, terminated = process._terminate_okazaki_fragment_column(
        0,
        complex_bound_sites=complex_bound_sites,
        polymerized=polymerized,
        strand_breaks=strand_breaks,
        enzymes_next=enzymes_next,
        bound_next={},
    )

    assert terminated is False
    assert enzymes_next == {}
    assert new_strand_breaks.to_regions() == []
    assert process._lagging_polymerase_positions(new_cbs) == process._lagging_polymerase_positions(
        complex_bound_sites
    )
    assert process._backup_beta_clamp_positions(new_cbs) == (wrong_backup_clamp0, -1)


# ----------------------------------------------------------------------
# terminateOkazakiFragment: column 1 ("region B"), non-last fragment.
# ----------------------------------------------------------------------


def test_terminate_col1_region_b_nonlast_fragment_handoff(process: KarrReplicationProcess) -> None:
    lead0, lead1 = process.leading_strand_indexs
    _lag0, lag1 = process.lagging_strand_indexs
    a1 = process.primase_binding_locations[1]
    fidx1 = 1
    cor_ftpt5 = process.core_footprint_5prime_bp
    cor_ftpt3 = process.core_footprint_3prime_bp
    helicase_pos0 = 570000
    helicase_pos1 = 9000

    # Column 1's lagging synthesis wraps past position 0 back up near the
    # sequence end (mirror image of column 0's wrap direction).
    lagging_pos1_completion = process.sequence_len_bp - 1
    lag_raw1 = (lagging_pos1_completion - cor_ftpt5) % process.sequence_len_bp
    backup_clamp1 = int(a1[fidx1]) + cor_ftpt3 + 1

    starts1_for_ssb = int(a1[fidx1 - 1])
    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (300000, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (300001, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw1, lag1, process.core_beta_clamp_primase_global_index),
        (backup_clamp1, lag1, process.beta_clamp_global_index),
    ]
    for pos in _ssb_positions(process, starts1_for_ssb + 5, helicase_pos1 - 5):
        entries.append((pos, int(process.leading_strand_indexs[0]), process.ssb8mer_global_index))
    complex_bound_sites = _bound_sites(process, entries)
    polymerized = _empty_triplet(process)
    enzymes_next: dict = {}
    bound_next: dict = {}

    new_cbs, new_strand_breaks, terminated = process._terminate_okazaki_fragment_column(
        1,
        complex_bound_sites=complex_bound_sites,
        polymerized=polymerized,
        strand_breaks=_empty_triplet(process),
        enzymes_next=enzymes_next,
        bound_next=bound_next,
    )

    assert terminated is True
    expected_new_lag1 = backup_clamp1 - process.core_footprint_bp
    assert process._lagging_polymerase_positions(new_cbs) == (-1, expected_new_lag1)
    assert process._backup_beta_clamp_positions(new_cbs) == (-1, -1)
    assert new_strand_breaks.to_regions() == [(process.sequence_len_bp - 1, 1, 1)]
    assert bound_next[process.enzyme_wid_core_beta_clamp_primase] == 0.0
    assert bound_next[process.enzyme_wid_beta_clamp] == -1.0


# ----------------------------------------------------------------------
# terminateOkazakiFragment: last fragment (both columns' final Okazaki
# fragment) -- leading-strand complex identity swap
# (Replication.m:1198-1212).
# ----------------------------------------------------------------------


def test_terminate_col0_last_fragment_leading_identity_swap(process: KarrReplicationProcess) -> None:
    lead0, lead1 = process.leading_strand_indexs
    lag0, _lag1 = process.lagging_strand_indexs
    a0 = process.primase_binding_locations[0]
    fidx0 = int(a0.size)  # the last fragment for column 0
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    helicase_pos0 = 289000
    helicase_pos1 = 9000
    lead_pol_pos0 = 291000

    starts0 = int(a0[fidx0 - 1])
    ends0 = int(a0[fidx0 - 2]) - 1
    length0 = abs(ends0 - starts0) + 1
    lagging_pos0_completion = starts0 + length0
    lag_raw0 = (lagging_pos0_completion - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp

    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lead_pol_pos0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (300001, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
        # No backup beta-clamp: the last fragment has nothing left to reload.
    ]
    for pos in _ssb_positions(process, helicase_pos0 + 5, starts0 - 5):
        entries.append((pos, int(process.leading_strand_indexs[1]), process.ssb8mer_global_index))
    complex_bound_sites = _bound_sites(process, entries)
    # `_okazaki_fragment_index`'s `correction` term disambiguates the
    # boundary case where the completion position numerically coincides
    # with the *next-older* fragment's own start: it consults whether the
    # lagging strand's polymerized history already covers that position.
    polymerized = SparseTriplet.from_regions([(starts0, lag0, length0)], shape=process.chromosome_shape)
    enzymes_next: dict = {}
    bound_next: dict = {}

    new_cbs, new_strand_breaks, terminated = process._terminate_okazaki_fragment_column(
        0,
        complex_bound_sites=complex_bound_sites,
        polymerized=polymerized,
        strand_breaks=_empty_triplet(process),
        enzymes_next=enzymes_next,
        bound_next=bound_next,
    )

    assert terminated is True
    assert process._lagging_polymerase_positions(new_cbs) == (-1, -1)
    identity = new_cbs.values[(new_cbs.positions == lead_pol_pos0) & (new_cbs.strands == lead0)]
    assert identity.tolist() == [process.two_core_beta_clamp_gamma_complex_primase_global_index]
    assert new_strand_breaks.to_regions() == [(ends0, 2, 1)]
    # Fully-expanded literal per-step deltas (release-lagging-pol +
    # leading-identity-swap), not the algebraically-netted shortcut.
    # `core_beta_clamp_primase`/`core_beta_clamp_gamma_complex`/
    # `2core_beta_clamp_gamma_complex_primase` are DNA-bound complex
    # identities and live on `bound_next`.
    assert bound_next[process.enzyme_wid_core_beta_clamp_primase] == -1.0
    assert bound_next[process.enzyme_wid_core_beta_clamp_gamma_complex] == -1.0
    assert bound_next[process.enzyme_wid_2core_beta_clamp_gamma_complex_primase] == 1.0
    assert enzymes_next[process.enzyme_wid_core] == 0.0
    assert enzymes_next[process.enzyme_wid_beta_clamp_monomer] == 2.0
    assert enzymes_next[process.enzyme_wid_gamma_complex] == 0.0


# ----------------------------------------------------------------------
# _advance_replication_forks
# ----------------------------------------------------------------------


def _advance_scenario_col0_fidx1(
    process: KarrReplicationProcess, *, progress_before: int, with_backup_clamp: bool
) -> dict:
    lead0, lead1 = process.leading_strand_indexs
    lag0, _lag1 = process.lagging_strand_indexs
    a0 = process.primase_binding_locations[0]
    fidx0 = 1
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    helicase_pos0 = 570000
    helicase_pos1 = 9000
    lead_pol_pos0 = 300000
    lead_pol_pos1 = 300001

    starts0 = int(a0[fidx0 - 1])
    lagging_pos0_before = starts0 + progress_before
    lag_raw0 = (lagging_pos0_before - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp

    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lead_pol_pos0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (lead_pol_pos1, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
    ]
    if with_backup_clamp:
        backup_clamp0 = int(a0[fidx0]) - (hol_ftpt - cor_ftpt5) + 1
        entries.append((backup_clamp0, lag0, process.beta_clamp_global_index))
    for pos in _ssb_positions(process, helicase_pos0 + 5, starts0 - 5):
        entries.append((pos, int(process.leading_strand_indexs[1]), process.ssb8mer_global_index))

    complex_bound_sites = _bound_sites(process, entries)
    store = ChromosomeStore(shape=process.chromosome_shape)
    leading_position0 = lead_pol_pos0 + cor_ftpt5
    # Region B (`lagging_strand_indexs[1]`, the fixed `_set_region_unwound`
    # mother-shrink target -- see `_unwind_window`): must cover the
    # helicase-footprint-anchored unwind window
    # `[helicase_pos0 - budget + hel_ftpt5 + 1 - budget, helicase_pos0 +
    # hel_ftpt5 + 1)` these column-0 scenarios exercise (budgets used across
    # this file's tests are all <= 5 bp), well clear of the `lag0`/`lead0`
    # entries above (a different strand axis -- no coverage interaction).
    lag1 = int(process.lagging_strand_indexs[1])
    store.set_field(
        "polymerizedRegions",
        SparseTriplet.from_regions(
            [
                (leading_position0, lead0, 10000),
                (starts0, lag0, progress_before),
                (helicase_pos0 - 100, lag1, 200),
            ],
            shape=process.chromosome_shape,
        ),
    )
    return {
        "complex_bound_sites": complex_bound_sites,
        "store": store,
        "helicase_pos0": helicase_pos0,
        "lead_pol_pos0": lead_pol_pos0,
        "entries": entries,
    }


def test_advance_multi_boundary_tick_crosses_fragment_completion(process: KarrReplicationProcess) -> None:
    """Budget spans exactly 1 fragment completion: 3 bp finish fragment
    index 1, then 2 leftover bp begin fragment index 2 -- both leading and
    lagging must end up advanced by the SAME total (5), never double-
    counted, and the two fragments' `polymerizedRegions` entries must stay
    genuinely discontinuous (not merged) since real, unsynthesized DNA
    separates them."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=1385 - 3, with_backup_clamp=True)

    result = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=5,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    assert result["actual_left_bp"] == 5
    assert result["actual_right_bp"] == 0
    new_helicase = process._helicase_positions(result["complex_bound_sites"])
    new_leading = process._leading_polymerase_positions(result["complex_bound_sites"])
    assert new_helicase[0] == scenario["helicase_pos0"] - 5  # column 0: helicase direction is -1
    assert new_leading[0] == scenario["lead_pol_pos0"] - 5
    new_fragment_index = process._okazaki_fragment_index(
        process._lagging_position(process._lagging_polymerase_positions(result["complex_bound_sites"])),
        result["polymerized"],
    )
    assert new_fragment_index[0] == 2  # advanced into the NEXT fragment
    lag0 = process.lagging_strand_indexs[0]
    lag_regions = sorted(r for r in result["polymerized"].to_regions() if r[1] == lag0)
    assert len(lag_regions) == 2  # genuinely discontinuous, not merged
    (pos_a, _strand_a, len_a), (pos_b, _strand_b, len_b) = lag_regions
    assert pos_a + len_a < pos_b  # a real gap remains between the 2 fragments
    assert new_strand_break_recorded(process, result)


def new_strand_break_recorded(process: KarrReplicationProcess, result: dict) -> bool:
    return result["strand_breaks"].to_regions() == [(process.sequence_len_bp - 1, 2, 1)]


def test_advance_zero_budget_still_terminates_pending_complete_fragment(
    process: KarrReplicationProcess,
) -> None:
    """Opus G1 item 2 regression test: a fragment that is ALREADY fully
    polymerized (e.g. it completed on an earlier tick but was gated -- SSB
    not yet satisfied, or a stalled backup-clamp mismatch -- and the gate
    has since cleared) must still terminate on a tick where BOTH columns'
    advance budget is genuinely zero. Karr's `terminateOkazakiFragment` is
    re-evaluated fresh every tick regardless of whether
    `unwindAndPolymerizeDNA` made any new progress that same tick
    (Replication.m:599-602's fixed subfunction call order); only actual
    MOVEMENT is gated on budget, never the termination retry itself."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=1385, with_backup_clamp=True)

    result = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=0,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    # No movement at all: both budgets were zero.
    assert result["actual_left_bp"] == 0
    assert result["actual_right_bp"] == 0
    # But termination still fired: the lagging polymerase handed off to
    # fragment index 2 (not left dangling at the completed fragment 1),
    # and a strand break was recorded at the completed fragment's end.
    new_fragment_index = process._okazaki_fragment_index(
        process._lagging_position(process._lagging_polymerase_positions(result["complex_bound_sites"])),
        result["polymerized"],
    )
    assert new_fragment_index[0] == 2
    assert result["strand_breaks"].to_regions() != []


def test_advance_stalls_leave_leftover_budget_unconsumed_no_double_count(
    process: KarrReplicationProcess,
) -> None:
    """Without the backup clamp, the fragment-1 termination gate cannot be
    satisfied: lagging completes fragment 1's remaining 3 bp then legitimately
    stalls (2 bp of the 5-bp budget left unconsumed). Leading must be capped
    to lagging's ACTUAL achieved distance (3), not the raw requested budget
    (5) -- this is the regression case for the leading/lagging double-count
    bug caught during development of this port."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=1385 - 3, with_backup_clamp=False)

    result = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=5,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    assert result["actual_left_bp"] == 3
    new_helicase = process._helicase_positions(result["complex_bound_sites"])
    new_leading = process._leading_polymerase_positions(result["complex_bound_sites"])
    assert new_helicase[0] == scenario["helicase_pos0"] - 3
    assert new_leading[0] == scenario["lead_pol_pos0"] - 3


def test_advance_ssb_gate_false_zeroes_leading_lagging_still_proceeds(
    process: KarrReplicationProcess,
) -> None:
    """No SSB sites bound -> `areLaggingStrandSSBSitesBound` is False ->
    leading polymerase + helicase must not move at all this tick, while the
    lagging strand (gated independently, by fragment progress only) still
    advances by the full requested budget."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=1385 - 3, with_backup_clamp=True)
    # Rebuild without the SSB entries this helper added.
    no_ssb_entries = [
        e for e in scenario["entries"] if e[2] != process.ssb8mer_global_index
    ]
    no_ssb = _bound_sites(process, no_ssb_entries)

    result = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=no_ssb,
        budget_left_bp=2,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    assert result["actual_left_bp"] == 2  # lagging still advances
    new_helicase = process._helicase_positions(result["complex_bound_sites"])
    new_leading = process._leading_polymerase_positions(result["complex_bound_sites"])
    assert new_helicase[0] == scenario["helicase_pos0"]  # leading strand untouched
    assert new_leading[0] == scenario["lead_pol_pos0"]


def test_advance_foreign_occlusion_in_leading_window_fails_closed(
    process: KarrReplicationProcess,
) -> None:
    """A foreign (unmanaged) complex sitting in the leading strand's
    advance window must hard-fail rather than silently skip past it --
    the generic `isRegionAccessible` machinery this stands in for is out
    of scope for this port (adjudication #2)."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=1385 - 3, with_backup_clamp=True)
    lead0 = process.leading_strand_indexs[0]
    foreign_global_index = 999_999
    cor_ftpt5 = process.core_footprint_5prime_bp
    # The leading advance window is `[leading_position - advance, leading_
    # position)` where `leading_position = lead_pol_pos0 + core_footprint_
    # 5prime_bp` (`_leading_position`, column 0) -- place the foreign
    # complex squarely inside it.
    foreign_position = scenario["lead_pol_pos0"] + cor_ftpt5 - 2
    occluded = _bound_sites(
        process,
        [*scenario["entries"], (foreign_position, lead0, foreign_global_index)],
    )

    with pytest.raises(ReplicationTopologyError, match="foreign complex"):
        process._advance_replication_forks(
            chromosome_store=scenario["store"],
            complex_bound_sites=occluded,
            budget_left_bp=5,
            budget_right_bp=0,
            enzymes_next={},
            bound_next={},
        )


def test_advance_is_deterministic_no_rng(process: KarrReplicationProcess) -> None:
    """Same inputs must produce byte-identical outputs across repeated
    calls -- initiation/termination/advance are all source-deterministic
    (adjudication: 'do not introduce stochastic choices that MATLAB does
    not make')."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=1385 - 3, with_backup_clamp=True)

    result_a = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=5,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )
    result_b = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=5,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    assert result_a["actual_left_bp"] == result_b["actual_left_bp"]
    assert result_a["complex_bound_sites"].to_regions() == result_b["complex_bound_sites"].to_regions()
    assert result_a["polymerized"].to_regions() == result_b["polymerized"].to_regions()
    assert result_a["strand_breaks"].to_regions() == result_b["strand_breaks"].to_regions()
