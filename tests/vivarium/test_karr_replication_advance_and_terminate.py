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
from typing import Any

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

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


class _StubDwellRNG:
    """Deterministic stand-in for `self._rng`, isolating `_rna_polymerase_
    collision_stall`'s single `.poisson(...)` dwell draw for the
    Finding-4 composition test below (`test_advance_stalls_not_crashes_
    on_transcription_produced_rna_polymerase_occupancy`) -- a real,
    independently-seeded draw would only sometimes land "dwelling" for
    any given cell (Replication.m:862's genuine per-tick stochasticity),
    so this pins the outcome to isolate whether the MECHANISM itself
    works, not RNG-stream-position luck. `.random()` delegates to a fixed
    value for Finding 3's unrelated same-tick-vs-deferred-termination coin
    (irrelevant to this test's own assertions either way)."""

    def __init__(self, dwelling: tuple[bool, bool, bool, bool]) -> None:
        self._dwelling = dwelling

    def random(self, *args: object, **kwargs: object) -> float:
        return 0.9

    def poisson(self, *args: object, **kwargs: object) -> Any:
        return np.array([0 if dwell else 1 for dwell in self._dwelling])


def _build_replication_tick_state(*, tick: int) -> tuple[KarrReplicationProcess, dict[str, Any]]:
    """Loads a REAL, fully fixture-consistent Replication oracle pre-state
    for `tick` -- the SAME no-hint "states_before"-only loader
    (`_build_tick_state`) used by
    `test_karr_replication_seed0_topology_diagnostic.py` (no trace-hint/
    oracle-after values are ever read; `forbid_sut_oracle_file_io` in that
    module enforces this for the full no-hint pipeline -- this helper
    reuses only its state-construction half, not its own oracle-file
    access, since this file's own tests never call `next_update` on trace
    data directly). Used here to seed a realistic full-genome
    `complexBoundSites`/`polymerizedRegions` baseline for the Finding-4
    RNA-polymerase composition test, rather than hand-constructing a
    synthetic full-genome state from scratch (which -- as this file's
    Okazaki-fragment-boundary scenarios already show -- requires
    reproducing many interacting mother/daughter-strand invariants that
    only real fixture data satisfies for free)."""
    from l2_replay_common import resolve_trace_path
    from test_karr_replication_seed0_topology_diagnostic import _build_tick_state

    trace_path = resolve_trace_path("Replication")
    return _build_tick_state(trace_path, tick)


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


def test_advance_multi_boundary_tick_stops_at_current_fragment_and_defers_handoff(
    process: KarrReplicationProcess,
) -> None:
    """Executable `Replication.m` schedules `unwindAndPolymerizeDNA`,
    `terminateOkazakiFragment`, and `initiateOkazakiFragment` as separate
    subfunctions. `_advance_replication_forks` therefore only advances the
    current fragment to its boundary; handoff to the next fragment and nick
    creation are deferred to the later scheduled subfunctions."""
    scenario = _advance_scenario_col0_fidx1(process, progress_before=1385 - 3, with_backup_clamp=True)

    result = process._advance_replication_forks(
        chromosome_store=scenario["store"],
        complex_bound_sites=scenario["complex_bound_sites"],
        budget_left_bp=5,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )

    assert result["actual_left_bp"] == 3
    assert result["actual_right_bp"] == 0
    new_helicase = process._helicase_positions(result["complex_bound_sites"])
    new_leading = process._leading_polymerase_positions(result["complex_bound_sites"])
    assert new_helicase[0] == scenario["helicase_pos0"] - 5  # column 0: helicase direction is -1
    assert new_leading[0] == scenario["lead_pol_pos0"] - 5
    new_fragment_index = process._okazaki_fragment_index(
        process._lagging_position(process._lagging_polymerase_positions(result["complex_bound_sites"])),
        result["polymerized"],
    )
    assert new_fragment_index[0] == 1
    lag0 = process.lagging_strand_indexs[0]
    lag_regions = sorted(r for r in result["polymerized"].to_regions() if r[1] == lag0)
    assert lag_regions == [(578691, int(lag0), 1385)]
    assert result["strand_breaks"].to_regions() == []


class _FixedCoin:
    """Deterministic stand-in for `np.random.default_rng`."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self, *args: object, **kwargs: object) -> float:
        return self._value


def test_advance_helper_is_invariant_to_termination_order_coin_stub(
    process: KarrReplicationProcess,
) -> None:
    """`_advance_replication_forks` is now just the
    `unwindAndPolymerizeDNA` subfunction. Any terminate-vs-advance
    ordering randomness lives in `next_update`'s outer `randperm`, not
    inside this helper, so patching a no-arg `.random()` coin stub must
    not change the helper's direct output."""
    scenario_kwargs = dict(progress_before=1385 - 3, with_backup_clamp=True)
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

    assert result["actual_left_bp"] == tick1_result["actual_left_bp"]
    assert result["actual_right_bp"] == tick1_result["actual_right_bp"]
    assert result["complex_bound_sites"].to_regions() == tick1_result["complex_bound_sites"].to_regions()
    assert result["polymerized"].to_regions() == tick1_result["polymerized"].to_regions()
    assert result["strand_breaks"].to_regions() == tick1_result["strand_breaks"].to_regions()


def test_advance_zero_budget_leaves_pending_fragment_for_later_termination_subfunction(
    process: KarrReplicationProcess,
) -> None:
    """Direct calls to `_advance_replication_forks` with zero budget must
    remain a pure `unwindAndPolymerizeDNA` no-op. Any pending completed
    fragment is handled later by the separately scheduled
    `terminateOkazakiFragment` subfunction in `next_update`, not here."""
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
    new_fragment_index = process._okazaki_fragment_index(
        process._lagging_position(process._lagging_polymerase_positions(result["complex_bound_sites"])),
        result["polymerized"],
    )
    assert new_fragment_index[0] == 1
    assert result["strand_breaks"].to_regions() == []


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


def test_leading_strand_lead_gap_grows_and_stalls_under_unwind_only_trajectory(
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
      3. STAYS STALLED under this helper alone: even after a backup clamp
         is authored into the carried-forward state, lagging does not
         resume because `_advance_replication_forks` still does not run the
         separately scheduled `terminateOkazakiFragment` /
         `initiateOkazakiFragment` handoff path.
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

    # --- Phase 3: direct unwind-only calls stay stalled even after the
    # backup clamp appears, because the handoff subfunctions are not being
    # run in this helper-only trajectory.
    assert lagging_actual_history[40:] == [0] * (ticks - 40)
    assert helicase_history[40:] == [plateau] * (ticks - 40)


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


# ----------------------------------------------------------------------
# Finding 4 (2026-08-05, five-gap follow-up item #4): composition-facing
# tests proving the two literal Karr stall mechanisms that REPLACED the
# prior fail-closed `ReplicationTopologyError` raises
# (`_rna_polymerase_collision_stall`/`_terc_linking_stall`, both already
# unit-tested directly in `test_karr_replication_ssb_gate_and_occlusion.py`
# against hand-derived formula inputs) also integrate correctly through
# the FULL `_advance_replication_forks` production entry point when
# exercised against realistic OTHER-process-produced chromosome
# occupancy/state -- i.e. Replication genuinely STALLS, not crashes, when
# Transcription has bound an RNA polymerase on the chromosome, or
# DNASupercoiling has left a nonzero linking number at the terC boundary.
# ----------------------------------------------------------------------


def test_advance_stalls_not_crashes_on_transcription_produced_rna_polymerase_occupancy(
    process: KarrReplicationProcess,
) -> None:
    """Composition-facing (Finding 4, item #4): starts from a REAL, fully
    fixture-consistent tick-1 pre-state of the Replication oracle trace
    (`_build_tick_state`, the same no-hint "states_before" loader used by
    `test_karr_replication_seed0_topology_diagnostic.py` -- no trace-hint/
    oracle-after values), then adds exactly ONE synthetic bound complex
    with the real `rna_polymerase_global_index` -- standing in for state
    Transcription's own process would leave on `complexBoundSites` after
    binding an RNA polymerase -- positioned in column 0's own quadrant
    (`lagging_strand_indexs[0]`), `rna_pol_footprint` + 2bp ahead of the
    real helicase position in its direction of travel (matching
    `_rna_polymerase_collision_stall`'s own cap formula, Replication.m:
    855: `helicasePos(1) - (positions + rnaPolFtpt)`). With the Poisson
    dwell draw stubbed "dwelling" for this one cell (isolating the
    mechanism itself, not RNG-stream-position luck -- a real,
    independently-seeded draw would only sometimes land here, matching
    Replication.m:862's genuine per-tick stochasticity), the SAME 5bp
    budget that advances the helicase in FULL without the RNAP present
    (baseline) is capped to exactly 2bp with it present -- proving the
    full production path stalls gracefully instead of raising, using only
    real oracle pre-state plus one realistic synthetic occupant (no
    fabricated genome-wide state)."""
    process_baseline, state = _build_replication_tick_state(tick=1)
    store = ChromosomeStore.from_state_mapping(state["chromosome"], shape=process_baseline.chromosome_shape)
    complex_bound_sites = store.get_field("complexBoundSites")
    helicase_pos = process_baseline._helicase_positions(complex_bound_sites)
    assert helicase_pos[0] != -1  # tick 1 has an active, bound helicase (verified via probe)

    process_baseline._rng = _StubDwellRNG(dwelling=(False, False, False, False))
    baseline = process_baseline._advance_replication_forks(
        chromosome_store=store,
        complex_bound_sites=complex_bound_sites,
        budget_left_bp=5,
        budget_right_bp=5,
        enzymes_next={},
        bound_next={},
    )
    baseline_helicase = process_baseline._helicase_positions(baseline["complex_bound_sites"])
    assert baseline_helicase[0] == helicase_pos[0] - 5  # unobstructed: full budget consumed

    process_occluded, state2 = _build_replication_tick_state(tick=1)
    rna_pol_footprint = process_occluded._foreign_dna_footprint_by_global_index[
        process_occluded.rna_polymerase_global_index
    ]
    rnap_pos = helicase_pos[0] - rna_pol_footprint - 2
    strand = int(process_occluded.lagging_strand_indexs[0])
    entries = [*complex_bound_sites.to_regions(), (rnap_pos, strand, process_occluded.rna_polymerase_global_index)]
    occupied = SparseTriplet.from_regions(entries, shape=process_occluded.chromosome_shape)

    process_occluded._rng = _StubDwellRNG(dwelling=(True, False, False, False))
    stalled = process_occluded._advance_replication_forks(
        chromosome_store=store,
        complex_bound_sites=occupied,
        budget_left_bp=5,
        budget_right_bp=5,
        enzymes_next={},
        bound_next={},
    )
    stalled_helicase = process_occluded._helicase_positions(stalled["complex_bound_sites"])
    # Capped to stop exactly short of the synthetic RNA polymerase's own
    # footprint -- helicase_pos[0] - (rnap_pos + rna_pol_footprint) == 2 --
    # not raised, not silently ignored.
    assert stalled_helicase[0] == helicase_pos[0] - 2
    assert stalled_helicase[1] == baseline_helicase[1]  # column 1 (uninvolved) unaffected


def test_advance_stalls_not_crashes_on_dna_supercoiling_produced_terc_linking_number(
    process: KarrReplicationProcess,
) -> None:
    """Composition-facing (Finding 4, item #4): constructs column 0's REAL
    LAST Okazaki fragment before terC (`fidx0 = len(primase_binding_
    locations[0]) - 1`, whose fragment start `a0[fidx0-1]` and terminal
    boundary `a0[fidx0] == process.terc_position_bp` are both real fixture
    values, not fabricated) with the helicase positioned so this tick's
    unconstrained 5bp leading advance would cross terC by exactly 1bp
    (`_terc_linking_stall`'s own "crosses this tick" predicate). A
    nonzero `linkingNumbers` entry at the EXACT position
    `_terc_linking_stall` itself reads (Replication.m:824's
    `linkingNumbers([min(c.terCPosition+1, helicasePos(2)+helFtpt5-1) 1])`
    -- standing in for whatever state DNASupercoiling's own process would
    leave there) makes column 0's advance zero (branch 2: the daughter
    strand at terC is not yet polymerized) -- the helicase genuinely
    stalls at its pre-tick position rather than crossing, while the SAME
    scenario with that linking number absent (baseline) crosses in full.
    Both runs go through the complete `_advance_replication_forks` entry
    point with no crash, only a graceful cap -- proving Karr's real
    stall semantics, not the prior fail-closed raise."""
    lead0, lead1 = process.leading_strand_indexs
    lag0, _lag1 = process.lagging_strand_indexs
    lag1 = int(process.lagging_strand_indexs[1])
    a0 = process.primase_binding_locations[0]
    fidx0 = len(a0) - 1
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    hel_ftpt5 = process.helicase_footprint_5prime_bp
    terc = process.terc_position_bp

    starts0 = int(a0[fidx0 - 1])
    lead_bp = 4  # helicase is 4bp short of terC before this tick
    advance_requested = lead_bp + 1  # 5bp requested budget crosses by exactly 1bp
    helicase_pos0 = terc + 1 + lead_bp - hel_ftpt5
    helicase_pos1 = 9000  # far below terC: `_far_from_terc_helicase`-style inert column 1
    lead_pol_pos0 = 300000  # decoupled from helicase_pos0 (matches _advance_scenario_col0_fidx1 convention)
    lead_pol_pos1 = 300001

    progress_before = 200
    lagging_pos0_before = starts0 - progress_before
    lag_raw0 = (lagging_pos0_before - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp
    backup_clamp0 = int(a0[fidx0]) - (hol_ftpt - cor_ftpt5) + 1

    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lead_pol_pos0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (lead_pol_pos1, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
        (backup_clamp0, lag0, process.beta_clamp_global_index),
    ]
    for pos in _ssb_positions(process, helicase_pos0 + 5, starts0 - 5):
        entries.append((pos, int(process.leading_strand_indexs[1]), process.ssb8mer_global_index))
    complex_bound_sites = _bound_sites(process, entries)

    store = ChromosomeStore(shape=process.chromosome_shape)
    leading_position0 = lead_pol_pos0 + cor_ftpt5
    # `_set_region_unwound`'s own mother-shrink window for this tick's
    # UNCONSTRAINED (baseline, no-veto) advance -- exactly
    # `[helicase_pos0 + hel_ftpt5 - advance_requested + 1, ... +
    # advance_requested)` (see `_unwind_window`, column 0) -- narrowly
    # placed to cover ONLY that window and deliberately NOT
    # `terc_position_0based` (`terc - 1`, 2bp below this window's own
    # lower edge), which must remain UNPOLYMERIZED for branch 2's "not
    # already polymerized" veto condition to hold.
    unwind_lo = helicase_pos0 + hel_ftpt5 - advance_requested + 1
    store.set_field(
        "polymerizedRegions",
        SparseTriplet.from_regions(
            [
                (leading_position0, lead0, 10000),
                (lagging_pos0_before, lag0, progress_before),
                (unwind_lo, lag1, advance_requested),
            ],
            shape=process.chromosome_shape,
        ),
    )

    # --- Baseline: no linking-number entry recorded anywhere -> crosses terC in full.
    baseline = process._advance_replication_forks(
        chromosome_store=store,
        complex_bound_sites=complex_bound_sites,
        budget_left_bp=advance_requested,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )
    baseline_helicase = process._helicase_positions(baseline["complex_bound_sites"])
    assert baseline_helicase[0] == helicase_pos0 - advance_requested

    # --- Same scenario, but DNASupercoiling has left a nonzero linking
    # number at the exact position Replication.m:824 itself reads.
    check_pos_0based = min(terc + 1, helicase_pos1 + hel_ftpt5 - 1) - 1
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions([(check_pos_0based, lead0, 1)], shape=process.chromosome_shape),
    )
    stalled = process._advance_replication_forks(
        chromosome_store=store,
        complex_bound_sites=complex_bound_sites,
        budget_left_bp=advance_requested,
        budget_right_bp=0,
        enzymes_next={},
        bound_next={},
    )
    stalled_helicase = process._helicase_positions(stalled["complex_bound_sites"])
    assert stalled_helicase[0] == helicase_pos0  # genuinely stalled at terC, not crossed, not crashed
    assert stalled_helicase[1] == baseline_helicase[1] == helicase_pos1  # column 1 (uninvolved) unaffected
