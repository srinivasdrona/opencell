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
leading strand + helicase independently, gated by the literal
Replication.m:812-818 persistent lead-gap threshold (`2 *
okazakiFragmentMeanLength`) rather than a same-tick lockstep to lagging's
achieved distance (Finding-1 fix, 2026; the prior per-tick lockstep cap
is superseded). The REPORTED `actual_left_bp`/`actual_right_bp` (drives
substrate/dNTP demand) still reflects lagging's actual achieved distance
when the column has already split -- a separate, still-adjudicated
simplification of Karr's full per-strand `limits` kinetics (Finding-2/
limits-port territory, out of scope here) -- so a helicase that
genuinely outpaces lagging under the new gate is not double-counted into
that reported figure, but also is not yet fully charged the substrate
cost of its own extra advance either; that residual gap belongs to
Finding 2, not this file.

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
    starts0 = int(a0[fidx0 - 1])
    next_start0 = int(a0[fidx0])
    # Two real, simultaneously-enforced Karr constraints bound where the
    # helicase may sit here: (a) Replication.m:812-818's lead-gap gate
    # (this file's Finding-1 port) needs the lead relative to the CURRENT
    # fragment (`starts0`) under `2 * okazakiFragmentMeanLength`; (b)
    # `terminateOkazakiFragment`'s pre-existing handoff gap_ok
    # (Replication.m's `startingOkazakiLoopLength` margin, ported at
    # `_terminate_okazaki_fragment_column`) needs the helicase already
    # past the NEXT fragment's start (`next_start0`) by more than that
    # margin. Real fixture fragment spacing (~1.6kb) comfortably fits both
    # inside the 3kb lead-gap threshold -- 500bp past `next_start0` here.
    helicase_pos0 = next_start0 - 500
    helicase_pos1 = 9000
    lead_pol_pos0 = 300000
    lead_pol_pos1 = 300001

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


class _FixedCoin:
    """Deterministic stand-in for `np.random.default_rng` exposing only the
    single no-arg `.random()` call `_advance_replication_forks` draws for
    Finding-3's per-tick advance-vs-terminate ordering coin. Direct calls to
    `_advance_replication_forks` (as these tests make, bypassing
    `_apply_ssb_cycle`/`next_update`) never reach any OTHER RNG-consuming
    helper (`free_and_bind_ssbs`, `dissociate_free_ssb_complexes`,
    `_stochastic_round`), so this narrow stub is sufficient and does not
    risk masking an unexpected additional draw elsewhere."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self, *args: object, **kwargs: object) -> float:
        return self._value


def test_finding3_terminate_ordering_coin_same_tick_vs_deferred_no_hint_trajectory(
    process: KarrReplicationProcess,
) -> None:
    """Finding 3 (Replication.m:604-607): Karr's `evolveState` draws a fresh
    `randStream.randperm` every tick, so whether `terminateOkazakiFragment`
    runs before or after `unwindAndPolymerizeDNA` in a tick where THIS
    tick's own advance is what completes a fragment is genuinely a per-tick
    coin flip (P=1/2 for any 2 elements of a uniform random permutation,
    Replication.m:1097-1099's `this.okazakiFragmentProgress` read is live
    mutable state). This is a CONTINUOUS 2-tick trajectory regression (not
    the single-tick-isolated-oracle-probe style used by
    `test_karr_replication_seed0_topology_diagnostic.py`, which structurally
    cannot observe a deferred completion since it re-seeds a brand new
    process from oracle-supplied per-tick state every tick with no
    carry-over): it proves the SAME underlying scenario is handled
    correctly under EITHER coin outcome, and that a deferred completion is
    genuinely picked up the very next tick, not silently lost.
    """
    scenario_kwargs = dict(progress_before=1385 - 3, with_backup_clamp=True)

    # --- coin lands "after" (>= 0.5): terminate observes this tick's own
    # freshly-completed fragment and fires in the SAME tick's call.
    same_tick_process = KarrReplicationProcess({})
    same_tick_process._rng = _FixedCoin(0.9)
    scenario = _advance_scenario_col0_fidx1(same_tick_process, **scenario_kwargs)
    result = same_tick_process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=5,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )
    same_tick_fragment_index = same_tick_process._okazaki_fragment_index(
        same_tick_process._lagging_position(
            same_tick_process._lagging_polymerase_positions(result["complex_bound_sites"])
        ),
        result["polymerized"],
    )
    assert same_tick_fragment_index[0] == 2  # handed off to the NEXT fragment already
    assert result["strand_breaks"].to_regions() != []  # nick recorded THIS tick

    # --- coin lands "before" (< 0.5): terminate would have run BEFORE this
    # tick's own advance and so cannot observe this tick's completion --
    # deferred to the NEXT tick's unconditional stall-retry check instead
    # of firing now. Position/polymerized-region bookkeeping for the
    # completed step itself is UNCHANGED either way (only the termination
    # side-effect -- handoff/nick -- is deferred).
    deferred_process = KarrReplicationProcess({})
    deferred_process._rng = _FixedCoin(0.1)
    scenario2 = _advance_scenario_col0_fidx1(deferred_process, **scenario_kwargs)
    tick1_result = deferred_process._advance_replication_forks(
        chromosome_store=scenario2["store"],
        complex_bound_sites=scenario2["complex_bound_sites"],
        budget_left_bp=5,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )
    # The fragment-boundary POSITION already moved this tick regardless of
    # termination timing (movement is not coin-gated, only the
    # `terminateOkazakiFragment` side effects are) -- `_okazaki_fragment_index`
    # is a pure position/`primaseBindingLocations` geometry lookup, so it is
    # NOT diagnostic of whether termination itself fired. The genuinely
    # diagnostic side effects are the `strandBreaks` nick and the backup-
    # beta-clamp release/rebind handoff, both performed only inside
    # `_terminate_okazaki_fragment_column`.
    assert tick1_result["strand_breaks"].to_regions() == []  # no nick yet: deferred

    # NEXT tick: zero further budget, but the pending completed-and-
    # unterminated fragment is retried unconditionally (the top-of-loop
    # stall-retry branch, never coin-gated) and now DOES fire -- proving
    # the deferral is genuinely a 1-tick delay, not data loss. A fresh coin
    # draw this second tick (still 0.1, "before") is irrelevant here since
    # this path is the unconditional retry, not the coin-gated branch.
    tick2_store = ChromosomeStore(shape=deferred_process.chromosome_shape)
    tick2_store.set_field("polymerizedRegions", tick1_result["polymerized"])
    tick2_store.set_field("strandBreaks", tick1_result["strand_breaks"])
    tick2_result = deferred_process._advance_replication_forks(
        chromosome_store=tick2_store,
        complex_bound_sites=tick1_result["complex_bound_sites"],
        budget_left_bp=0,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )
    tick2_fragment_index = deferred_process._okazaki_fragment_index(
        deferred_process._lagging_position(
            deferred_process._lagging_polymerase_positions(tick2_result["complex_bound_sites"])
        ),
        tick2_result["polymerized"],
    )
    assert tick2_fragment_index[0] == 2  # handed off now, one tick later
    assert tick2_result["strand_breaks"].to_regions() != []  # nick recorded on the retry


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
    stalls (2 bp of the 5-bp budget left unconsumed). The REPORTED
    `actual_left_bp` (drives substrate/dNTP demand, Finding-2/limits-port
    territory, unchanged here) still reflects lagging's actual achieved
    distance (3), not the raw requested budget (5) -- that bookkeeping
    choice is what prevents the original double-count bug this test is
    named for. But the leading strand/helicase itself is NOT lockstep-
    capped to that same figure (Replication.m:773's `limits(1,:)` never
    depends on `laggingPos` -- see Finding-1 fix): it advances by the
    FULL requested budget (5), independently, since the persistent
    Replication.m:812-818 lead-gap (a ~500bp gap here, far under the
    ~3000bp `2 * okazakiFragmentMeanLength` threshold) does not block it.
    This is the corrected, literal-Karr counterpart of the old (pre-
    Finding-1) same-tick lockstep this test used to assert."""
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
    assert new_helicase[0] == scenario["helicase_pos0"] - 5
    assert new_leading[0] == scenario["lead_pol_pos0"] - 5


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


# ----------------------------------------------------------------------
# Finding-1 continuous no-hint trajectory regression (Opus review, 2026-
# 06): proves the ported Replication.m:812-818 lead-gap gate is a real,
# multi-tick, RECOVERABLE constraint -- not the pre-fix same-tick
# `leading_advance = ... else lagging_actual` lockstep, under which the
# leading strand could never grow independently of lagging's own
# progress at all (a degenerate "lead permanently ~0" trajectory, only
# trivially "non-collapsing" because it never moved in the first place).
# ----------------------------------------------------------------------


def test_leading_strand_lead_gap_grows_stalls_and_recovers_no_hint_trajectory(
    process: KarrReplicationProcess,
) -> None:
    """A genuinely CONTINUOUS (not per-tick-reset) trajectory: real state
    (`complexBoundSites`/`polymerizedRegions`) is carried forward tick to
    tick, feeding each tick's own `_advance_replication_forks` OUTPUT
    directly into the next tick's INPUT -- no oracle trace/`trace_hint`
    is ever read anywhere in this test.

    Column 0's lagging strand is placed 50bp from completing fragment
    index 1 WITHOUT a backup beta-clamp bound (the same real, admissible
    termination-gate-stall condition `test_advance_stalls_leave_leftover_
    budget_unconsumed_no_double_count` exercises for 1 tick, Replication.m
    :1090-1213's `equality_ok`), so lagging legitimately stalls at that
    boundary for many ticks running. Meanwhile the helicase/leading
    strand, no longer lockstep-capped to lagging's per-tick achieved
    distance, is fed a full, unchanging 100bp/tick budget every tick.

    Expected (and asserted) phases, matching Replication.m:812-818's
    literal `2 * okazakiFragmentMeanLength` persistent gap gate:
      1. GROWS: for ~29 ticks, while lagging is stalled at 0 bp/tick, the
         helicase keeps moving -- proving leading is genuinely decoupled
         from lagging's per-tick actual, not locked to it.
      2. STALLS (does not just keep growing forever): once the gap
         reaches the `2 * okazakiFragmentMeanLength` threshold, the
         helicase position becomes CONSTANT for several further ticks in
         a row -- proving the gate is a real, binding constraint, not a
         no-op.
      3. RECOVERS: once the stalled lagging strand's blocking condition
         is lifted (the backup beta-clamp finally binds -- a real,
         already-admissible state transition per `with_backup_clamp=True`
         elsewhere in this file, not fabricated to force an answer, and
         not derived from any oracle read), lagging's termination
         succeeds, the persistent gap is recomputed against the new
         (closer) current fragment, and the helicase resumes moving on
         later ticks -- proving the cap is genuinely recoverable, not a
         permanent one-way collapse/deadlock.
    """
    lead0, lead1 = process.leading_strand_indexs
    lag0, _lag1 = process.lagging_strand_indexs
    lag1_strand = int(process.lagging_strand_indexs[1])
    a0 = process.primase_binding_locations[0]
    fidx0 = 1
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    mean_len = process.okazaki_fragment_mean_length_bp
    threshold = 2 * mean_len
    budget = 100

    starts0 = int(a0[fidx0 - 1])
    length0 = process._okazaki_fragment_length((fidx0, 0))[0]
    progress0 = length0 - 50  # 50bp of headroom: reaches the boundary on tick 0

    helicase_pos0 = starts0 - 50  # lead ~= 30bp at t0, comfortably under threshold
    helicase_pos1 = 9000
    lead_pol_pos0 = 300000
    lead_pol_pos1 = 300001

    lagging_pos0 = starts0 + progress0
    lag_raw0 = (lagging_pos0 - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp

    ssb_step = process.ssb8mer_footprint_bp + process.ssb_complex_spacing_bp
    # Cover the FULL range the helicase could ever traverse across this
    # whole trajectory (up to `threshold` + margin behind its start) once,
    # generously, up front -- so SSB starvation is never the confound
    # this test is isolating (that is a separately-scoped, genuinely
    # stochastic mechanism -- `_apply_ssb_cycle` -- not exercised here).
    ssb_lo = helicase_pos0 - threshold - 200
    ssb_hi = starts0 - 5
    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lead_pol_pos0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (lead_pol_pos1, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
    ]
    for pos in range(ssb_lo, ssb_hi, ssb_step):
        entries.append((pos, lead1, process.ssb8mer_global_index))
    complex_bound_sites = _bound_sites(process, entries)

    store = ChromosomeStore(shape=process.chromosome_shape)
    leading_position0 = lead_pol_pos0 + cor_ftpt5
    store.set_field(
        "polymerizedRegions",
        SparseTriplet.from_regions(
            [
                (leading_position0, lead0, 10000),
                (starts0, lag0, progress0),
                # Region B (the fixed `_set_region_unwound` mother-shrink
                # target on `lagging_strand_indexs[1]`, see
                # `_advance_scenario_col0_fidx1`) must cover the ENTIRE
                # span the helicase traverses over this whole multi-tick
                # trajectory, not just 1 tick's worth.
                (helicase_pos0 - threshold - 2000, lag1_strand, threshold + 2200),
            ],
            shape=process.chromosome_shape,
        ),
    )

    helicase_history: list[int] = []
    lagging_actual_history: list[int] = []
    backup_clamp_added = False
    ticks = 45
    for tick in range(ticks):
        if tick == 40 and not backup_clamp_added:
            # The backup clamp finally binds -- lifting the termination
            # stall (see docstring). A fixed, test-authored tick chosen
            # only after confirming (via the phase assertions below) the
            # gate has already plateaued well before it; NOT derived from
            # any oracle/trace read, and not tuned to any tick-specific
            # expected numeric result (Finding-1's "no tick-targeted
            # branches" rule concerns the PRODUCTION code path, which
            # contains no tick number anywhere -- this is test-harness
            # scripting of a real admissible state transition).
            backup_clamp0 = int(a0[fidx0]) - (hol_ftpt - cor_ftpt5) + 1
            complex_bound_sites = process._add_point_complex(
                complex_bound_sites,
                strand=lag0,
                position=backup_clamp0,
                value=process.beta_clamp_global_index,
                context="trajectory test: backup clamp binds",
            )
            backup_clamp_added = True

        result = process._advance_replication_forks(
            chromosome_store=store,
            complex_bound_sites=complex_bound_sites,
            budget_left_bp=budget,
            budget_right_bp=0,
            enzymes_next={},
            bound_next={},
        )
        complex_bound_sites = result["complex_bound_sites"]
        store.set_field("polymerizedRegions", result["polymerized"])

        helicase_history.append(int(process._helicase_positions(complex_bound_sites)[0]))
        lagging_actual_history.append(int(result["actual_left_bp"]))

    # --- Phase 1: GROWS. Lagging is stalled (0 actual bp) for the entire
    # pre-recovery window, yet the helicase keeps moving every tick until
    # it hits the gap threshold -- direct proof leading is decoupled from
    # lagging's per-tick actual (refutes the old lockstep).
    assert all(a == 0 for a in lagging_actual_history[1:30]), (
        "lagging must be genuinely stalled (0 actual bp) throughout the growth window"
    )
    assert all(
        helicase_history[i + 1] < helicase_history[i] for i in range(0, 29)
    ), "helicase must keep moving independently every tick while lagging is stalled (no lockstep)"

    # --- Phase 2: STALLS. Once the persistent gap reaches the threshold,
    # the helicase position must become and STAY constant for several
    # ticks in a row -- a real, binding gate, not a one-tick fluke.
    plateau = helicase_history[35]
    assert helicase_history[30:40] == [plateau] * 10, (
        "helicase must plateau (stop moving) once the lead-gap threshold is reached"
    )
    gap_at_plateau = starts0 - plateau - process.helicase_footprint_bp
    assert threshold <= gap_at_plateau < threshold + budget, (
        f"plateau gap {gap_at_plateau} must sit just at/above the {threshold}bp threshold, "
        "not far past it (else the gate isn't actually being checked every tick)"
    )

    # --- Phase 3: RECOVERS. After the backup clamp binds (tick 40),
    # lagging's termination succeeds and the helicase resumes moving on
    # a later tick -- the cap is a recoverable stall, never a permanent
    # collapse/deadlock.
    assert any(a > 0 for a in lagging_actual_history[40:]), "lagging must resume once unblocked"
    assert helicase_history[-1] != plateau, "helicase must resume moving after lagging catches up"
    assert helicase_history[-1] < plateau, "helicase's resumed movement must still be in the same (col0, -1) direction"


# ----------------------------------------------------------------------
# Finding 2: Replication.m:768-775 primase-kinetics `limits` primer-length
# cap, replacing a fixed `floor(rate*dt)` budget. `_primer_length_capped_
# step`/`_leading_strand_distance_since_origin` are pure functions;
# `_advance_replication_forks` integration coverage below (lagging strand)
# proves the cap actually constrains a real, returned advance, not just
# the helper in isolation.
# ----------------------------------------------------------------------


def test_primer_length_capped_step_caps_when_distance_below_primer_length(
    process: KarrReplicationProcess,
) -> None:
    """Literal port of Replication.m:768-775's raw `primerLength -
    distance` term when it is still positive (i.e. the strand has not yet
    traveled a full primer length since its own start): the returned step
    must be the SMALLER of the requested step and the remaining primer
    residual, never the full requested step."""
    assert process.primer_length == 11  # real fixture value asserted so this test fails loudly if the fixture ever changes
    # distance=0 (fragment/fork just started): residual == primer_length itself.
    assert process._primer_length_capped_step(0, 100) == 11
    # distance=5: residual == 11-5 == 6.
    assert process._primer_length_capped_step(5, 100) == 6
    # requested step already below the residual: no cap needed, returned unchanged.
    assert process._primer_length_capped_step(0, 3) == 3


def test_primer_length_capped_step_falls_back_to_full_rate_once_past_primer_length(
    process: KarrReplicationProcess,
) -> None:
    """Literal port of Replication.m:775's `limits(limits <= 0) =
    dnaPolymeraseElongationRate` fallback: once distance-since-start
    reaches (or exceeds) `primerLength`, the raw primase-kinetics term is
    <= 0 and Karr reverts to the flat elongation-rate budget -- here,
    the already-computed `proposed_step` passed in is returned completely
    UNCHANGED (no cap at all), proving this is a genuine no-op past the
    threshold, not a permanently-binding constraint."""
    assert process._primer_length_capped_step(11, 100) == 100  # distance == primerLength exactly: residual == 0
    assert process._primer_length_capped_step(12, 100) == 100  # distance past primerLength
    assert process._primer_length_capped_step(10_000, 5) == 5  # deep steady-state elongation, small requested step


def test_leading_strand_distance_since_origin_matches_literal_matlab_formula(
    process: KarrReplicationProcess,
) -> None:
    """Replication.m:769-770: `primerLength - (chrLen - leadingPos(1))` /
    `primerLength - (leadingPos(2) - 1)`, i.e. distance-since-origin ==
    `chrLen - leadingPos(1)` (col 0) / `leadingPos(2) - 1` (col 1) in
    Karr's 1-based terms. Translated to OC's 0-based `leading_pos` (OC ==
    MATLAB - 1, a shift-invariant difference): column 0's origin boundary
    is `sequence_len_bp - 1` (distance 0 there); column 1's origin
    boundary is `0` (distance == the raw 0-based position itself)."""
    seq_len = process.sequence_len_bp
    # Column 0: right at the origin boundary -> distance 0.
    assert process._leading_strand_distance_since_origin((seq_len - 1, 0), 0) == 0
    # Column 0: 100bp already traveled from the origin boundary.
    assert process._leading_strand_distance_since_origin((seq_len - 101, 0), 0) == 100
    # Column 1: right at the origin boundary -> distance 0.
    assert process._leading_strand_distance_since_origin((0, 0), 1) == 0
    # Column 1: 100bp already traveled from the origin boundary.
    assert process._leading_strand_distance_since_origin((0, 100), 1) == 100


def test_lagging_strand_primer_length_caps_first_tick_advance_after_fragment_start(
    process: KarrReplicationProcess,
) -> None:
    """Integration-level proof (via the real `_advance_replication_forks`
    entry point, not just the pure helper) that Replication.m:768-775's
    primase-kinetics cap genuinely constrains a returned advance: a
    lagging strand with `progress_before=0` (fragment just initiated, 0bp
    of its own progress yet) requesting a 50bp budget must advance only
    11bp (`primer_length`) this tick -- NOT the full 50bp a flat
    `floor(rate*dt)` budget alone would have granted before this port."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=0, with_backup_clamp=True)

    result = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=50,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    assert result["actual_left_bp"] == process.primer_length == 11


def test_lagging_strand_primer_length_cap_lifted_once_progress_reaches_primer_length(
    process: KarrReplicationProcess,
) -> None:
    """Companion to the test above: once `progress_before` already equals
    `primer_length` (the fragment has already traveled a full primer
    length), the raw primase-kinetics term is <= 0 and Karr's own fallback
    to the flat elongation-rate budget applies -- the requested 50bp
    budget must be granted in FULL this tick (modulo the fragment's own
    remaining length, which at `progress_before=11` is still far greater
    than 50), proving the cap is a genuine one-tick-window transient, not
    a permanent throttle."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=process.primer_length, with_backup_clamp=True)

    result = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=50,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    assert result["actual_left_bp"] == 50
