from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.state.chromosome_store import SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess, ReplicationTopologyError


def _base_state(
    process: KarrReplicationProcess,
    *,
    replication_state: str = "idle",
    initial_substrate: float = 0.0,
    allocated_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    request_wids = [*process.dntp_wids, process.atp_wid, process.h2o_wid]
    chromosome = process.build_default_chromosome_state(replication_state=replication_state)
    return {
        "chromosome": chromosome,
        "substrates": {wid: float(initial_substrate) for wid in process.substrate_wids},
        "requests": {process.name: {wid: 0.0 for wid in request_wids}},
        "substrates_allocated": {
            process.name: {
                wid: float((allocated_override or {}).get(wid, 0.0)) for wid in request_wids
            }
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any], process: KarrReplicationProcess) -> None:
    chrom_update = update.get("chromosome", {})
    if "polymerizedRegions" in chrom_update:
        state["chromosome"]["polymerizedRegions"] = SparseTriplet.from_state(
            chrom_update["polymerizedRegions"],
            shape=process.chromosome_shape,
        ).to_state()
    if "complexBoundSites" in chrom_update:
        state["chromosome"]["complexBoundSites"] = SparseTriplet.from_state(
            chrom_update["complexBoundSites"],
            shape=process.chromosome_shape,
        ).to_state()
    if "strandBreaks" in chrom_update:
        state["chromosome"]["strandBreaks"] = SparseTriplet.from_state(
            chrom_update["strandBreaks"],
            shape=process.chromosome_shape,
        ).to_state()
    if "replication_state" in chrom_update:
        state["chromosome"]["replication_state"] = str(chrom_update["replication_state"])

    for side, delta in chrom_update.get("fork_position_bp", {}).items():
        state["chromosome"]["fork_position_bp"][side] = float(
            state["chromosome"]["fork_position_bp"].get(side, 0.0) + float(delta)
        )

    for key, delta in chrom_update.get("events", {}).items():
        state["chromosome"]["events"][key] = float(
            state["chromosome"]["events"].get(key, 0.0) + float(delta)
        )

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))

    if "requests" in update and process.name in update["requests"]:
        state["requests"][process.name].update(
            {wid: float(v) for wid, v in update["requests"][process.name].items()}
        )


def _polymerized_triplet(state: dict[str, Any], process: KarrReplicationProcess) -> SparseTriplet:
    return SparseTriplet.from_state(state["chromosome"]["polymerizedRegions"], shape=process.chromosome_shape)


def _complex_bound_sites_with_values(
    process: KarrReplicationProcess, global_values: list[int]
) -> dict[str, Any]:
    """Build a `complexBoundSites` sparse-triple payload with one entry per
    enzyme global index in `global_values`, at distinct arbitrary positions
    on strand 0 -- sufficient for the `isAnyHelicaseBound`-style
    "is this enzyme bound anywhere" check, which does not care about the
    specific position/strand of the match."""
    regions = [(100 * (i + 1), 0, value) for i, value in enumerate(global_values)]
    return SparseTriplet.from_regions(regions, shape=process.chromosome_shape).to_state()


def _complement_intervals(exclusions: list[tuple[int, int]], total_len: int) -> list[tuple[int, int]]:
    """Given a list of (possibly overlapping/unsorted) `[lo, hi)` exclusion
    spans within `[0, total_len)`, return the sorted list of `(lo, hi)`
    sub-intervals of `[0, total_len)` NOT covered by any exclusion.

    Generic interval-complement helper (no fixture-specific assumptions):
    used to build a "full genome minus known holes" `polymerizedRegions`
    placeholder for a strand that is mostly-still-unwound except for a
    handful of explicitly-tracked already-relabeled/already-occupied
    spans -- avoids having to hand-verify exact non-overlap between the
    mother-remaining placeholder and any other real, separately-tracked
    region (e.g. an in-progress lagging Okazaki fragment sharing the same
    strand index -- "region B", see `_active_replisome_chromosome_substate`
    below)."""
    if not exclusions:
        return [(0, total_len)]
    merged: list[list[int]] = []
    for lo, hi in sorted(exclusions):
        lo = max(0, lo)
        hi = min(total_len, hi)
        if lo >= hi:
            continue
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    result: list[tuple[int, int]] = []
    cursor = 0
    for lo, hi in merged:
        if cursor < lo:
            result.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < total_len:
        result.append((cursor, total_len))
    return result


def _active_replisome_chromosome_substate(
    process: KarrReplicationProcess,
    *,
    fragment_index: tuple[int, int] = (100, 100),
    lagging_progress_bp: tuple[int, int] = (500, 500),
    fork_gap_bp: int = 50,
    leading_region_len_bp: int = 20000,
) -> dict[str, Any]:
    """Builds a minimal, source-faithful, internally-consistent "actively
    elongating both forks, generic mid-fragment" chromosome sub-state: real
    position-resolved helicase + leading-strand polymerase
    (`core_beta_clamp_gamma_complex`) + lagging-strand polymerase
    (`core_beta_clamp_primase`) `complexBoundSites` entries for BOTH fork
    columns, a modest scattering of lagging-strand-template SSBs in the
    helicase-to-fragment-start gap (satisfying
    `_are_lagging_strand_ssb_sites_bound`), and `polymerizedRegions`
    consistent with Karr's real strand semantics (Chromosome.m:120-130,
    448-473, 1855-1957):

    * `leading_strand_indexs[0]` (strand 0) is the PERMANENT, full-length
      mother-template placeholder from t=0 (`strandIndexs_ch1`,
      Chromosome.m:472) -- never touched by `setRegionUnwound`/
      `_set_region_unwound`, so it stays whole here too.
    * `leading_strand_indexs[1]` (strand 3) is the growing daughter strand
      `setRegionUnwound` extends for BOTH fork columns (its fixed
      `newStrd`) -- given two already-grown chunks, one per column.
    * `lagging_strand_indexs[1]` (strand 1, "region B") is the SAME fixed
      `oldStrd` `setRegionUnwound` shrinks for BOTH columns *and*,
      independently, the real strand column 1's own lagging-strand
      Okazaki synthesis writes new polymerization onto (Replication.m:
      935-936's second `setRegionPolymerized` call, `nonTemplate` for
      templateArg=1). Built here as "full genome minus the two
      already-unwound daughter-strand-3 holes minus the in-progress
      lagging fragment's own span" via `_complement_intervals`, so the
      fixture never has to hand-prove those three spans don't collide.
    * `lagging_strand_indexs[0]` (strand 2, "region A") only ever receives
      column 0's own lagging-strand Okazaki synthesis -- unaffected by
      `setRegionUnwound` -- so it is left as the single in-progress
      fragment region, as before.

    Column 0's fork travels in the decreasing-position direction and
    column 1's in the increasing-position direction (matching
    `_advance_replication_forks`'s own `direction`/`lag_direction`
    conventions); `leading_pos{0,1}_target` are placed *ahead of* (not
    inside) each column's own lagging-fragment span so that region B's
    shrink window and its own Okazaki-fragment-growth span never
    spatially overlap. Positions are derived directly from the real
    fixture-loaded `primase_binding_locations`/footprint getters -- no
    fabricated numbers, no oracle trace file read anywhere."""
    lead0, lead1 = process.leading_strand_indexs
    lag0, lag1 = process.lagging_strand_indexs
    a0 = process.primase_binding_locations[0]
    a1 = process.primase_binding_locations[1]
    cor_ftpt5 = process.core_footprint_5prime_bp
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp

    fidx0, fidx1 = fragment_index
    progress0, progress1 = lagging_progress_bp
    starts0_t = int(a0[fidx0 - 1])
    starts1_t = int(a1[fidx1 - 1])

    lagging_pos0_target = starts0_t + progress0
    lagging_pos1_target = starts1_t - progress1
    lag_raw0 = (lagging_pos0_target - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp
    lag_raw1 = (lagging_pos1_target - cor_ftpt5) % process.sequence_len_bp
    # Leading/helicase positions placed ahead of (not inside) each
    # column's own lagging-fragment span: column 0's fork moves toward
    # decreasing positions (already past/below `starts0_t`), column 1's
    # toward increasing positions (already past/above `starts1_t`).
    leading_pos0_target = starts0_t - fork_gap_bp
    leading_pos1_target = starts1_t + fork_gap_bp
    lead_raw0 = (leading_pos0_target - cor_ftpt5) % process.sequence_len_bp
    lead_raw1 = (leading_pos1_target - hol_ftpt + cor_ftpt5 + 1) % process.sequence_len_bp
    helicase_pos0_t = leading_pos0_target - fork_gap_bp
    helicase_pos1_t = leading_pos1_target + fork_gap_bp

    def _ssb_positions(lo: int, hi: int) -> list[int]:
        ftpt = process.ssb8mer_footprint_bp
        spcg = process.ssb_complex_spacing_bp
        step = ftpt + spcg
        pts = []
        pos = lo + 5
        while pos + ftpt < hi - 5:
            pts.append(pos)
            pos += step
        return pts

    entries: list[tuple[int, int, int]] = [
        (helicase_pos0_t, lead0, process.helicase_global_index),
        (helicase_pos1_t, lead1, process.helicase_global_index),
        (lead_raw0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (lead_raw1, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
        (lag_raw1, lag1, process.core_beta_clamp_primase_global_index),
    ]
    for pos in _ssb_positions(helicase_pos0_t, starts0_t):
        entries.append((pos, lead1, process.ssb8mer_global_index))
    for pos in _ssb_positions(starts1_t, helicase_pos1_t):
        entries.append((pos, lead0, process.ssb8mer_global_index))

    complex_bound_sites = SparseTriplet.from_regions(entries, shape=process.chromosome_shape)

    # `setRegionUnwound`'s fixed (oldStrd, newStrd) pair: strand 1 shrinks,
    # strand 3 grows, for BOTH fork columns (see docstring above). The
    # near-fork edge of each column's accumulated "already unwound"
    # history MUST be anchored on the exact same formula
    # `_unwind_window` (Replication.m:904-905) uses for THIS tick's fresh
    # shrink/grow call -- helicase position + footprint offset, NOT the
    # leading polymerase's position -- so that this tick's fresh
    # `_set_region_unwound` call touches (rather than overlaps or leaves a
    # gap against) the pre-existing accumulated history. Using
    # `leading_pos{0,1}_target` here instead (an earlier, less precise
    # version of this fixture's choice) leaves the genuine
    # `[helicase_pos+footprint, leading_pos)` gap uncovered by anything,
    # which the (still-mother) `region_b_pieces` complement below would
    # then incorrectly still claim as "untouched mother" -- exactly the
    # gap this tick's fresh shrink call legitimately consumes, so no
    # conflict; but confirmed to matter now that the cross-daughter write
    # below (anchored on the leading position, not helicase) also lands in
    # that same neighbourhood.
    hel_ftpt5 = process.helicase_footprint_5prime_bp
    hel_ftpt_total = process.helicase_footprint_bp
    unwind_hi0 = helicase_pos0_t + hel_ftpt5 + 1
    unwind_lo1 = helicase_pos1_t + hel_ftpt_total - hel_ftpt5 - 1
    hole0 = (unwind_hi0, unwind_hi0 + leading_region_len_bp)
    hole1 = (unwind_lo1 - leading_region_len_bp, unwind_lo1)
    # Column 1's own already-polymerized span on strand 1 (region B):
    # `_okazaki_fragment_progress`'s `progress[1] = starts1_t - anchor`
    # (`anchor = lagging_pos1_target = starts1_t - progress1`, the CURRENT,
    # not-yet-synthesized lagging-polymerase tip) means the fragment's
    # growth-so-far occupies `starts1_t` itself (inclusive, the fragment's
    # first-synthesized bp) down to, but not including, `anchor` -- i.e.
    # `[anchor + 1, starts1_t + 1)`, matching `_growth_window`'s own
    # `direction=-1` convention (anchor is the inclusive high edge of the
    # NEXT span to be written, so the span already written stops 1bp above
    # it) and the real seed-0 tick-75 oracle region `[50, 2061)` for
    # `anchor=49, starts1_t=2060`.
    region_b_own_span = (starts1_t - progress1 + 1, starts1_t + 1)

    # Cross-column leading-strand-synthesis daughter contribution onto
    # strand 1 (`lag1`) -- Replication.m:935's `setRegionPolymerized(
    # [leadingPos;1 2]', [-1;1].*polLimits(1,:)')`, whose row-1 (column 0)
    # write lands on `strandIndexs_nonTemplate(1)=2` == MATLAB strand 2 ==
    # `lag1` (see `_set_region_unwound`'s docstring for the full
    # `Chromosome.m:1996-1997` value-lookup derivation), and whose row-2
    # (column 1) write lands on strand 3 == `lag0`. Every PRIOR tick that
    # advanced a column's leading strand deposited both (a) the
    # `setRegionUnwound` mother-shrink/daughter-grow pair on
    # `(lag1, lead1)` (modeled by `hole0`/`hole1` above, anchored on the
    # HELICASE-linked `_unwind_window`) and (b) this SEPARATE
    # `setRegionPolymerized` cross-daughter write on
    # `lagging_strand_indexs[1 - column]`, anchored on the LEADING-
    # POLYMERASE-linked `_growth_window` -- a DIFFERENT, non-identical
    # window (leading polymerase trails helicase by a footprint clearance
    # gap), so `cross0`/`cross1` must be excluded from `region_b_pieces`'
    # complement SEPARATELY from `hole0`/`hole1`, not assumed to coincide
    # with them.
    #
    # Boundary note: `_growth_window`'s `direction=-1` convention treats
    # its anchor (here `leading_pos0_target`, column 0) as the INCLUSIVE
    # high edge of the NEXT span to be written this tick (see
    # `_growth_window`'s own docstring) -- so column 0's cross-daughter
    # history must stop 1bp ABOVE that anchor (`leading_pos0_target + 1`),
    # leaving exactly the 1bp this tick's fresh write will supply, so the
    # two touch rather than overlap. Column 1's `direction=+1` convention
    # already treats its anchor (`leading_pos1_target`) as the EXCLUSIVE
    # low edge of the next span (`_growth_window`'s `direction>=0` branch
    # returns `anchor, anchor + step` unmodified) -- no +1 adjustment
    # needed there.
    cross0 = (leading_pos0_target + 1, leading_pos0_target + 1 + leading_region_len_bp)
    cross1 = (leading_pos1_target - leading_region_len_bp, leading_pos1_target)
    region_b_pieces = _complement_intervals(
        [hole0, hole1, cross0, region_b_own_span], process.sequence_len_bp
    )
    polymerized = SparseTriplet.from_regions(
        [
            (0, lead0, process.sequence_len_bp),
            (hole0[0], lead1, hole0[1] - hole0[0]),
            (hole1[0], lead1, hole1[1] - hole1[0]),
            (starts0_t, lag0, progress0),
            (cross1[0], lag0, cross1[1] - cross1[0]),
            (region_b_own_span[0], lag1, progress1),
            (cross0[0], lag1, cross0[1] - cross0[0]),
            *[(lo, lag1, hi - lo) for lo, hi in region_b_pieces],
        ],
        shape=process.chromosome_shape,
    )

    return {
        "polymerizedRegions": polymerized.to_state(),
        "complexBoundSites": complex_bound_sites.to_state(),
        "strandBreaks": SparseTriplet.from_regions([], shape=process.chromosome_shape).to_state(),
    }


def _active_replisome_base_state(
    process: KarrReplicationProcess,
    *,
    replication_state: str = "elongating",
    initial_substrate: float = 1e9,
    allocated_override: dict[str, float] | None = None,
    **scenario_kwargs: Any,
) -> dict[str, Any]:
    """`_base_state` plus a real, position-resolved active-replisome
    chromosome sub-state (see `_active_replisome_chromosome_substate`)
    overlaid in place of the stale monolithic seed, for tests that need
    the topology pipeline to genuinely advance rather than honestly
    no-op/fail-closed on inconsistent state."""
    state = _base_state(
        process,
        replication_state=replication_state,
        initial_substrate=initial_substrate,
        allocated_override=allocated_override,
    )
    state["chromosome"].update(_active_replisome_chromosome_substate(process, **scenario_kwargs))
    return state


def _completion_adjacent_chromosome_substate(process: KarrReplicationProcess) -> dict[str, Any]:
    """Builds a chromosome sub-state that is genuinely one real,
    position-resolved tick away from total-genome completion: real
    `complexBoundSites` for both fork columns with helicase/leading/
    lagging polymerase positions already at (or immediately adjacent to)
    `terc_position_bp` -- so the real remaining-distance-to-terC budget
    (`leading_position - terc_position_bp`) is already 0 for both columns
    -- combined with `polymerizedRegions` already at
    `_completed_polymerized_regions()`. This directly exercises the real
    completion-detection branch (`next_update`'s
    `desired_left_bp <= 0 and desired_right_bp <= 0` early-exit, which
    re-checks `_strand_polymerized` on the existing regions before
    no-op'ing) without needing to hand-simulate the many thousands of
    real ticks a full genome traversal would take -- that full-traversal
    exercise is what the seed0/100-tick oracle-replay diagnostic and any
    future N=50 run are for, not a synthetic unit test. Verified
    empirically against the real implementation (see
    `probe_strand_polymerized.py`/`probe_completion.py` scratch
    derivation; not fabricated)."""
    lead0, lead1 = process.leading_strand_indexs
    lag0, lag1 = process.lagging_strand_indexs
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    terc = process.terc_position_bp
    seq_len = process.sequence_len_bp

    lead_raw0 = (terc - cor_ftpt5) % seq_len
    lead_raw1 = (terc - hol_ftpt + cor_ftpt5 + 1) % seq_len
    lag_raw0 = (terc - hol_ftpt + cor_ftpt5 + 1) % seq_len
    lag_raw1 = (terc - cor_ftpt5) % seq_len
    helicase_pos0 = terc + 200
    helicase_pos1 = terc - 200

    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lead_raw0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (lead_raw1, lead1, process.core_beta_clamp_gamma_complex_global_index),
        (lag_raw0, lag0, process.core_beta_clamp_primase_global_index),
        (lag_raw1, lag1, process.core_beta_clamp_primase_global_index),
    ]
    complex_bound_sites = SparseTriplet.from_regions(entries, shape=process.chromosome_shape)
    polymerized = process._completed_polymerized_regions()
    return {
        "polymerizedRegions": polymerized.to_state(),
        "complexBoundSites": complex_bound_sites.to_state(),
        "strandBreaks": SparseTriplet.from_regions([], shape=process.chromosome_shape).to_state(),
    }


def _set_pre_split_polymerase_composition(state: dict[str, Any], process: KarrReplicationProcess) -> None:
    """Both replisomes' leading-strand polymerase still in the combined
    pre-split holoenzyme form (`_is_pre_split_replisome_state`)."""
    state["boundEnzymes"][process.enzyme_wid_2core_beta_clamp_gamma_complex_primase] = 2.0
    state["boundEnzymes"][process.enzyme_wid_core_beta_clamp_gamma_complex] = 0.0
    state["boundEnzymes"][process.enzyme_wid_core_beta_clamp_primase] = 0.0


def _set_post_split_polymerase_composition(state: dict[str, Any], process: KarrReplicationProcess) -> None:
    """Replisomes have physically diverged into separate per-fork
    complexes (`_is_post_split_replisome_state`)."""
    state["boundEnzymes"][process.enzyme_wid_2core_beta_clamp_gamma_complex_primase] = 1.0
    state["boundEnzymes"][process.enzyme_wid_core_beta_clamp_gamma_complex] = 1.0
    state["boundEnzymes"][process.enzyme_wid_core_beta_clamp_primase] = 1.0


def test_process_instantiates() -> None:
    p = KarrReplicationProcess({})
    assert p.name == "karr_replication"
    assert p.dna_polymerase_elongation_rate_bp_per_s == 100.0
    assert p.fork_polymerization_rate_bp_per_s == 100.0
    assert p.terc_position_bp == 290038
    assert p.dntp_wids == ["DATP", "DCTP", "DGTP", "DTTP"]
    assert p.atp_wid == "ATP"
    assert p.leading_strand_indexs == [0, 3]
    assert p.lagging_strand_indexs == [2, 1]


def test_idle_state_no_progress_no_request() -> None:
    p = KarrReplicationProcess({})
    state = _base_state(p, replication_state="idle", initial_substrate=1e6)
    update = p.next_update(1.0, state)
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    assert "polymerizedRegions" not in update.get("chromosome", {})
    assert all(v == 0.0 for v in update["requests"][p.name].values())
    assert "substrates" not in update
    assert "enzymes" not in update
    assert "boundEnzymes" not in update


def test_genuinely_idle_state_still_no_ops_with_boundenzymes_present() -> None:
    """Negative control for the L2.2 root-cause fix below: with the
    ``boundEnzymes``/``enzymes`` ports actually present (as the L2.1/L2.2
    oracle-replay harness always provides them) but showing no bound
    helicase and no fork progress, ``next_update`` must remain a true
    no-op -- the idle-gate fallback must not fire on a genuinely idle
    chromosome. (This mirrors `test_idle_state_no_progress_no_request`
    without its unrelated, pre-existing `"substrates" not in update`
    assertion, which fails on `main` independent of this change.)"""
    p = KarrReplicationProcess({})
    state = _base_state(p, replication_state="idle", initial_substrate=1e6)
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["enzymes"] = {}
    update = p.next_update(1.0, state)
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    assert "polymerizedRegions" not in update.get("chromosome", {})
    assert all(v == 0.0 for v in update["requests"][p.name].values())


def test_idle_state_with_non_helicase_enzyme_bound_stays_idle() -> None:
    """Specificity check (adversarial #5, "non-helicase inert"): a
    non-helicase enzyme bound both in `boundEnzymes` and in
    `complexBoundSites` must not satisfy Karr's `isAnyHelicaseBound`
    (Replication.m:1301), so the idle tick must not be promoted."""
    p = KarrReplicationProcess({})
    other_enzyme_wids = [wid for wid in p.enzyme_wids if wid != p.enzyme_wid_helicase]
    assert other_enzyme_wids, "expected at least one non-helicase enzyme_wid"
    other_wid = other_enzyme_wids[0]
    other_global_index = int(p.enzyme_global_indexs[p.enzyme_wids.index(other_wid)])
    state = _base_state(p, replication_state="idle", initial_substrate=1e6)
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["boundEnzymes"][other_wid] = 2.0
    state["chromosome"]["complexBoundSites"] = _complex_bound_sites_with_values(p, [other_global_index])
    update = p.next_update(1.0, state)
    assert "polymerizedRegions" not in update.get("chromosome", {})
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}


def test_idle_state_with_helicase_bound_but_no_leading_polymerase_stays_idle() -> None:
    """Adversarial #2, "helicase without leading polymerases inert": a
    helicase bound (`isAnyHelicaseBound` true, Replication.m:1301) with no
    leading-strand polymerase composition present (neither
    `_is_pre_split_replisome_state` nor `_is_post_split_replisome_state`,
    mirroring `leadingStrandElongating`/`all(...)`, Replication.m:1314,596)
    must NOT promote -- Karr's own gate is an AND of both conditions, with
    no OR-shortcut on a partial signal."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _base_state(p, replication_state="idle", initial_substrate=1e9, allocated_override=alloc)
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["boundEnzymes"][p.enzyme_wid_helicase] = 2.0
    helicase_global_index = int(p.enzyme_global_indexs[p.enzyme_index_helicase])
    state["chromosome"]["complexBoundSites"] = _complex_bound_sites_with_values(p, [helicase_global_index])

    update = p.next_update(1.0, state)

    assert "polymerizedRegions" not in update.get("chromosome", {})
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    assert all(v == 0.0 for v in update["requests"][p.name].values())


def test_idle_state_with_fork_progress_but_no_bound_enzymes_stays_idle() -> None:
    """Adversarial #3, "fork progress without helicase inert": the
    overlaid `polymerizedRegions` already shows fork progress beyond the
    unreplicated mother baseline, but no helicase/polymerase is actually
    bound this tick. This is precisely the OR-shortcut that used to exist
    (stale region data alone used to be sufficient to promote); Karr's
    gate depends only on live `complexBoundSites`
    (`isAnyHelicaseBound && all(leadingStrandElongating)`,
    Replication.m:596), never on region layout, so this must stay idle."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _base_state(p, replication_state="idle", initial_substrate=1e9, allocated_override=alloc)
    state["chromosome"]["polymerizedRegions"] = p._build_polymerized_regions(
        left_progress_bp=500,
        right_progress_bp=500,
    ).to_state()
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}

    update = p.next_update(1.0, state)

    assert "polymerizedRegions" not in update.get("chromosome", {})
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    assert all(v == 0.0 for v in update["requests"][p.name].values())


def test_idle_state_with_fully_composed_pre_split_replisome_promotes_to_elongating_root_cause_fix() -> None:
    """Root-cause regression for the L2.2 Replication port gap (adversarial
    #4, "fully composed replisome promotes"): OC's
    ``chromosome.replication_state`` flag is an OC-only coordination flag
    with no Karr counterpart (Karr's ``evolveState``/``initiateReplication``
    recompute "is a replisome active" fresh every tick from live
    `complexBoundSites` -- `isAnyHelicaseBound`, Replication.m:1301;
    `leadingStrandElongating`, Replication.m:1314; gate, Replication.m:596).
    The isolated per-process L2.1/L2.2 oracle-replay harness overlays
    Karr's real chromosome/boundEnzymes/complexBoundSites each tick but
    runs no `KarrReplicationInitiationProcess` coordinator, so this flag
    was stuck at its schema default "idle" forever and `next_update`
    silently returned a no-op on every sampled tick -- even while the
    overlaid state showed a fully-composed, actively-elongating replisome
    (helicase bound + both leading-strand polymerases still in their
    combined pre-split holoenzyme form). This test reproduces exactly that
    shape and asserts the process now advances the fork instead of
    no-op'ing."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="idle",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["boundEnzymes"][p.enzyme_wid_helicase] = 2.0
    _set_pre_split_polymerase_composition(state, p)

    update = p.next_update(1.0, state)

    fork_delta = update.get("chromosome", {}).get("fork_position_bp", {})
    assert fork_delta.get("left", 0.0) == 100.0
    assert fork_delta.get("right", 0.0) == 100.0
    assert "polymerizedRegions" in update["chromosome"]
    advanced = SparseTriplet.from_state(update["chromosome"]["polymerizedRegions"], shape=p.chromosome_shape)
    assert advanced.calc_num_edges() > 0
    assert any(v > 0.0 for v in update["requests"][p.name].values())


def test_idle_state_with_single_helicase_post_split_replisome_promotes_to_elongating() -> None:
    """Variant of the root-cause fix covering the "1 helicase" case
    Karr's own gate handles source-faithfully: `isAnyHelicaseBound` is an
    `any(...)` over `complexBoundSites` (Replication.m:1301), not a
    count==2 check, so a single remaining bound helicase (e.g. one fork's
    helicase already displaced near terC) combined with a post-split
    per-fork polymerase composition (`_is_post_split_replisome_state`)
    must still promote. Note: `boundEnzymes[helicase]` is a coarse,
    aggregate scalar never consulted by the position-resolved gate itself
    (`replisome_helicase_present` reads real `complexBoundSites` values
    directly via `np.any(...)`) -- it is set to 1.0 here purely to
    document that the promotion decision does not depend on this
    aggregate count either, matching Karr's real `any(...)` semantics."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="idle",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["boundEnzymes"][p.enzyme_wid_helicase] = 1.0
    _set_post_split_polymerase_composition(state, p)

    update = p.next_update(1.0, state)

    fork_delta = update.get("chromosome", {}).get("fork_position_bp", {})
    assert fork_delta.get("left", 0.0) == 100.0
    assert fork_delta.get("right", 0.0) == 100.0
    assert "polymerizedRegions" in update["chromosome"]


def test_idle_state_with_fully_split_steady_state_replisome_promotes_to_elongating() -> None:
    """Direct regression for the under-firing bug found while validating the
    gate against the real Karr seed-0 trace: the bulk of a real elongating
    replisome's lifetime (observed ticks ~20-99 of
    `data/m1_sources/karr_native/per_process_traces_v2/Replication_100ticks.mat`)
    sits in the fully-split steady state -- 2 `coreBetaClampGammaComplex` +
    2 `coreBetaClampPrimase` (one leading + one lagging complex per fork),
    `2coreBetaClampGammaComplexPrimase == 0` -- which satisfies neither
    `_is_pre_split_replisome_state` nor `_is_post_split_replisome_state`
    (each recognizes only one narrow transitional snapshot). An earlier
    gate implementation that OR'd those two narrow helpers under-fired to
    a ~23% rate against this trace instead of the near-total activity Karr
    actually shows; `_is_replisome_polymerase_capacity_present`'s
    Karr-sync-check-invariant formula (Replication.m:566-578) must
    recognize this composition and promote."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="idle",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["boundEnzymes"][p.enzyme_wid_helicase] = 2.0
    state["boundEnzymes"][p.enzyme_wid_2core_beta_clamp_gamma_complex_primase] = 0.0
    state["boundEnzymes"][p.enzyme_wid_core_beta_clamp_gamma_complex] = 2.0
    state["boundEnzymes"][p.enzyme_wid_core_beta_clamp_primase] = 2.0

    update = p.next_update(1.0, state)

    fork_delta = update.get("chromosome", {}).get("fork_position_bp", {})
    assert fork_delta.get("left", 0.0) == 100.0
    assert fork_delta.get("right", 0.0) == 100.0
    assert "polymerizedRegions" in update["chromosome"]


def test_complete_regions_with_stale_idle_flag_stays_inert_no_repeated_event() -> None:
    """Adversarial #1, "complete regions idle inert / no repeated event":
    a chromosome that is genuinely fully replicated (`polymerizedRegions`
    already at the completed layout) but whose `replication_state` flag
    was simply never advanced past its schema default "idle" (no
    coordinator, same shape as the root-cause bug) must NOT be promoted --
    there is no live helicase/polymerase bound, so Karr's own gate is
    false and the tick must stay a true no-op every time it is called,
    never emitting `replication_complete` (which would be a repeat, since
    a real coordinator would already have transitioned this chromosome to
    "complete" long before)."""
    p = KarrReplicationProcess({})
    state = _base_state(p, replication_state="idle", initial_substrate=1e6)
    state["chromosome"]["polymerizedRegions"] = p._completed_polymerized_regions().to_state()
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}

    for _ in range(3):
        update = p.next_update(1.0, state)
        assert "polymerizedRegions" not in update.get("chromosome", {})
        assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
        assert update.get("chromosome", {}).get("events", {}) == {}
        assert all(v == 0.0 for v in update["requests"][p.name].values())


def test_initiating_transitions_to_elongating_and_seeds_polymerized_regions() -> None:
    p = KarrReplicationProcess({})
    state = _base_state(
        p,
        replication_state="initiating",
        initial_substrate=1e6,
        allocated_override={wid: 1e6 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]},
    )
    update = p.next_update(1.0, state)
    assert update["chromosome"]["replication_state"] == "elongating"
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    seeded = SparseTriplet.from_state(update["chromosome"]["polymerizedRegions"], shape=p.chromosome_shape)
    assert seeded.positions.tolist() == [0, 0, 22, 580054]
    assert seeded.strands.tolist() == [0, 3, 1, 3]
    assert seeded.values.tolist() == [580076, 22, 580032, 22]
    expected_hydrolysis = float(p._initiation_hydrolysis_cost())
    assert update["requests"][p.name][p.atp_wid] == expected_hydrolysis
    assert update["requests"][p.name][p.h2o_wid] == expected_hydrolysis
    assert update["substrates"][p.atp_wid] == -expected_hydrolysis
    assert update["substrates"][p.h2o_wid] == -expected_hydrolysis
    assert update["substrates"][p.adp_wid] == expected_hydrolysis
    assert update["substrates"][p.pi_wid] == expected_hydrolysis
    assert update["substrates"][p.h_wid] == expected_hydrolysis


def test_initiating_hydrolysis_is_capped_by_allocated_atp_and_water() -> None:
    p = KarrReplicationProcess({})
    desired = float(p._initiation_hydrolysis_cost())
    capped = desired - 5.0
    state = _base_state(
        p,
        replication_state="initiating",
        initial_substrate=1e6,
        allocated_override={
            **{wid: 1e6 for wid in p.dntp_wids},
            p.atp_wid: desired,
            p.h2o_wid: capped,
        },
    )

    update = p.next_update(1.0, state)

    assert update["chromosome"]["replication_state"] == "elongating"
    assert update["requests"][p.name][p.atp_wid] == desired
    assert update["requests"][p.name][p.h2o_wid] == desired
    assert update["substrates"][p.atp_wid] == -capped
    assert update["substrates"][p.h2o_wid] == -capped
    assert update["substrates"][p.adp_wid] == capped
    assert update["substrates"][p.pi_wid] == capped
    assert update["substrates"][p.h_wid] == capped


def test_elongation_advances_and_consumes_dntps() -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    ticks = 5
    for _ in range(ticks):
        update = p.next_update(1.0, state)
        _apply_update(state, update, p)

    assert state["chromosome"]["fork_position_bp"]["left"] == float(ticks * 100)
    assert state["chromosome"]["fork_position_bp"]["right"] == float(ticks * 100)
    assert state["substrates"]["DATP"] < 1e9
    assert state["substrates"]["DCTP"] < 1e9
    assert state["substrates"]["DGTP"] < 1e9
    assert state["substrates"]["DTTP"] < 1e9


def test_completion_sets_state_and_emits_event_once() -> None:
    """`terminateReplication` is now a separately scheduled no-hint
    subfunction, matching executable `Replication.m:599-602,1253-1273`.
    Same-tick completion therefore requires a state that already has no
    lagging polymerases bound; merely placing lagging cores at terC is not
    enough. This fixture seeds the real "leading machinery only, genome
    fully polymerized" pre-state so `next_update`'s scheduled
    `terminateReplication` branch can flip the state to `"complete"` and
    emit the one-shot event exactly once."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["chromosome"].update(_completion_adjacent_chromosome_substate(p))
    complete_cbs = SparseTriplet.from_state(state["chromosome"]["complexBoundSites"], shape=p.chromosome_shape)
    normalized_values = complete_cbs.values.copy()
    normalized_values[
        normalized_values == p.core_beta_clamp_gamma_complex_global_index
    ] = p.two_core_beta_clamp_gamma_complex_primase_global_index
    keep = normalized_values != p.core_beta_clamp_primase_global_index
    state["chromosome"]["complexBoundSites"] = SparseTriplet(
        positions=complete_cbs.positions[keep],
        strands=complete_cbs.strands[keep],
        values=normalized_values[keep],
        shape=complete_cbs.shape,
    ).to_state()
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    _set_pre_split_polymerase_composition(state, p)

    update1 = p.next_update(1.0, state)
    _apply_update(state, update1, p)
    assert state["chromosome"]["replication_state"] == "complete"
    assert state["chromosome"]["events"]["replication_complete"] == 1.0

    update2 = p.next_update(1.0, state)
    _apply_update(state, update2, p)
    assert state["chromosome"]["events"]["replication_complete"] == 1.0


def test_limited_allocation_scales_progress_proportionally() -> None:
    p = KarrReplicationProcess({})
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
    )
    store = p._resolve_chromosome_store(state["chromosome"], trust_regions=True)
    complex_bound_sites = store.get_field("complexBoundSites")
    leading_positions = p._leading_position(p._leading_polymerase_positions(complex_bound_sites))
    lagging_positions = p._lagging_position(p._lagging_polymerase_positions(complex_bound_sites))
    desired = p._demand_from_progression(
        leading_positions=leading_positions,
        lagging_positions=lagging_positions,
        leading_bp_by_column=(100, 100),
        lagging_bp_by_column=(100, 100),
    )
    alloc = {wid: math.floor(val * 0.25) for wid, val in desired.items()}
    state["substrates_allocated"][p.name] = {wid: float(alloc[wid]) for wid in alloc}

    update = p.next_update(1.0, state)
    fork_delta = update["chromosome"]["fork_position_bp"]
    actual_step = int(fork_delta["left"])
    assert actual_step == int(fork_delta["right"])
    actual_demand = p._demand_from_progression(
        leading_positions=leading_positions,
        lagging_positions=lagging_positions,
        leading_bp_by_column=(actual_step, actual_step),
        lagging_bp_by_column=(actual_step, actual_step),
    )
    assert all(actual_demand[wid] <= alloc[wid] for wid in desired)
    next_step = actual_step + 1
    larger_demand = p._demand_from_progression(
        leading_positions=leading_positions,
        lagging_positions=lagging_positions,
        leading_bp_by_column=(next_step, next_step),
        lagging_bp_by_column=(next_step, next_step),
    )
    assert any(larger_demand[wid] > alloc[wid] for wid in desired)
    assert update["requests"][p.name][p.atp_wid] == float(desired[p.atp_wid])


def test_partial_run_monotonic_no_nan_mass_closes_within_fragment() -> None:
    """Reduced-scope, source-faithful successor to the old 1000-tick
    monolithic-advance smoke test: with real, position-resolved
    `complexBoundSites`/`polymerizedRegions` (the same generic
    mid-fragment scenario used elsewhere in this file), a single
    hand-built Okazaki fragment only has ~1000-1500bp of headroom before
    hitting its own fragment boundary (median/max spacing verified
    against the real fixture-derived `primase_binding_locations` arrays;
    see `docs`/commit history for the derivation) -- continuing
    monotonic full-rate advance past that boundary would require this
    synthetic fixture to also model the NEXT fragment's initiation/SSB
    window, which is out of scope for a hand-built unit fixture (that
    full many-fragment-boundary exercise is exactly what the hash-pinned
    seed0/100-tick oracle-replay diagnostic, using REAL oracle
    `complexBoundSites`, is for). This test is deliberately bounded to
    `ticks=8`, safely inside the confirmed full-rate-advance window
    (`starts0 + 500` progress into a fragment with >=1000bp of remaining
    room), and still asserts monotonic non-NaN progress plus exact
    dNTP/ATP mass-conservation identical to the unchanged pre-topology
    substrate-accounting formula."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e12 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e12,
        allocated_override=alloc,
    )

    prev_left = 0.0
    prev_right = 0.0
    ticks = 8
    for _ in range(ticks):
        update = p.next_update(1.0, state)
        _apply_update(state, update, p)
        left = state["chromosome"]["fork_position_bp"]["left"]
        right = state["chromosome"]["fork_position_bp"]["right"]
        assert left >= prev_left
        assert right >= prev_right
        assert np.isfinite(left)
        assert np.isfinite(right)
        prev_left = left
        prev_right = right

    assert state["chromosome"]["fork_position_bp"]["left"] == float(ticks * 100)
    assert state["chromosome"]["fork_position_bp"]["right"] == float(ticks * 100)

    total_advance_bp = int(
        state["chromosome"]["fork_position_bp"]["left"] + state["chromosome"]["fork_position_bp"]["right"]
    )
    consumed_datp = int(round(1e12 - state["substrates"]["DATP"]))
    consumed_dctp = int(round(1e12 - state["substrates"]["DCTP"]))
    consumed_dgtp = int(round(1e12 - state["substrates"]["DGTP"]))
    consumed_dttp = int(round(1e12 - state["substrates"]["DTTP"]))
    consumed_atp = int(round(1e12 - state["substrates"]["ATP"]))
    produced_adp = int(round(state["substrates"]["ADP"] - 1e12))
    produced_pi = int(round(state["substrates"]["PI"] - 1e12))
    produced_h = int(round(state["substrates"]["H"] - 1e12))
    produced_ppi = int(round(state["substrates"]["PPI"] - 1e12))

    assert consumed_datp >= 0
    assert consumed_dctp >= 0
    assert consumed_dgtp >= 0
    assert consumed_dttp >= 0
    assert consumed_atp >= 0

    # Sequence-exact dNTP demand is no longer a fixed `2 * total_advance_bp`
    # identity on this synthetic fixture; assert the actual no-hint
    # bookkeeping invariants instead.
    assert consumed_datp + consumed_dctp + consumed_dgtp + consumed_dttp == produced_ppi
    assert consumed_atp == produced_adp
    assert consumed_atp == produced_pi
    assert consumed_atp == produced_h


# --- `_shrink_polymerized_region` / `_set_region_unwound` standalone
# --- tests -----------------------------------------------------------
#
# Literal-port tests for `Chromosome.setRegionUnwound`
# (Chromosome.m:1855-1957) as implemented by
# `KarrReplicationProcess._shrink_polymerized_region`/`_set_region_unwound`:
# normal shrink (splitting a region into 0/1/2 surviving pieces),
# wrap/boundary behaviour at position 0 and at `sequence_len_bp`, the
# touching-merge invariant on the growing (daughter) strand, overlap/
# corruption fail-closed behaviour, and mass/topology conservation
# (exactly what is removed from the old strand is added to the new
# strand, nothing else changes). These operate directly on `SparseTriplet`
# fixtures, independent of any `complexBoundSites`/enzyme state -- no
# oracle trace, no hints, no fabricated numbers (arbitrary but internally
# consistent positions on the real fixture-loaded chromosome shape).


def _shape(process: KarrReplicationProcess) -> tuple[int, int]:
    return process.chromosome_shape


def test_shrink_polymerized_region_splits_middle_span_into_two_pieces() -> None:
    """Removing a `[lo, hi)` span from the *middle* of one existing region
    must leave exactly the two surviving before/after pieces (Chromosome.m:
    1934,1949's "unwind starts mid-region" case)."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(1000, strand, 1000)], shape=_shape(p))

    shrunk = p._shrink_polymerized_region(polymerized, strand=strand, lo=1200, hi=1400)

    regions = sorted(shrunk.to_regions())
    assert regions == [(1000, strand, 200), (1400, strand, 600)]
    # Mass conservation: total remaining length == original - removed span.
    assert sum(v for _, s, v in regions if s == strand) == 1000 - 200


def test_shrink_polymerized_region_from_left_edge_leaves_one_piece() -> None:
    """Removing a span flush with the region's own left edge leaves only
    the trailing piece (0 leading pieces -- Chromosome.m:1934's `if` not
    taken)."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(1000, strand, 1000)], shape=_shape(p))

    shrunk = p._shrink_polymerized_region(polymerized, strand=strand, lo=1000, hi=1200)

    assert shrunk.to_regions() == [(1200, strand, 800)]


def test_shrink_polymerized_region_from_right_edge_leaves_one_piece() -> None:
    """Removing a span flush with the region's own right edge leaves only
    the leading piece (0 trailing pieces -- Chromosome.m:1949's `if` not
    taken)."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(1000, strand, 1000)], shape=_shape(p))

    shrunk = p._shrink_polymerized_region(polymerized, strand=strand, lo=1800, hi=2000)

    assert shrunk.to_regions() == [(1000, strand, 800)]


def test_shrink_polymerized_region_exact_full_span_removes_region_entirely() -> None:
    """Removing exactly the whole region leaves 0 surviving pieces on that
    strand."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    other_strand = int(p.leading_strand_indexs[0])
    polymerized = SparseTriplet.from_regions(
        [(1000, strand, 1000), (0, other_strand, 500)], shape=_shape(p)
    )

    shrunk = p._shrink_polymerized_region(polymerized, strand=strand, lo=1000, hi=2000)

    assert shrunk.to_regions() == [(0, other_strand, 500)]


def test_shrink_polymerized_region_boundary_at_position_zero() -> None:
    """Wrap/boundary case: a region starting exactly at position 0 (the
    chromosome origin) shrinks correctly with no implicit wraparound
    (Karr's real `CircularSparseMat` always splits origin-crossing regions
    into two explicit entries -- never silently wraps)."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(0, strand, 1000)], shape=_shape(p))

    shrunk = p._shrink_polymerized_region(polymerized, strand=strand, lo=0, hi=100)

    assert shrunk.to_regions() == [(100, strand, 900)]


def test_shrink_polymerized_region_boundary_at_sequence_end() -> None:
    """Wrap/boundary case: a region ending exactly at `sequence_len_bp`
    (the chromosome's last valid position) shrinks correctly."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    seq_len = p.sequence_len_bp
    polymerized = SparseTriplet.from_regions([(seq_len - 1000, strand, 1000)], shape=_shape(p))

    shrunk = p._shrink_polymerized_region(polymerized, strand=strand, lo=seq_len - 100, hi=seq_len)

    assert shrunk.to_regions() == [(seq_len - 1000, strand, 900)]


def test_shrink_polymerized_region_noop_on_empty_span() -> None:
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(1000, strand, 1000)], shape=_shape(p))

    shrunk = p._shrink_polymerized_region(polymerized, strand=strand, lo=1500, hi=1500)

    assert shrunk.to_regions() == polymerized.to_regions()


def test_shrink_polymerized_region_raises_when_span_not_covered() -> None:
    """Fail-closed: no existing region on `strand` covers the requested
    span at all -- an unsupported/inconsistent state, not a silent no-op."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(1000, strand, 1000)], shape=_shape(p))

    with pytest.raises(ReplicationTopologyError):
        p._shrink_polymerized_region(polymerized, strand=strand, lo=5000, hi=5100)


def test_shrink_polymerized_region_raises_when_span_partially_uncovered() -> None:
    """Fail-closed: the span straddles the region's own boundary (only
    partially covered) -- Chromosome.m's 'regions must be double-stranded'
    precondition (~line 1888) is violated."""
    p = KarrReplicationProcess({})
    strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(1000, strand, 500)], shape=_shape(p))

    with pytest.raises(ReplicationTopologyError):
        p._shrink_polymerized_region(polymerized, strand=strand, lo=1400, hi=1600)


def test_set_region_unwound_shrinks_old_strand_and_grows_new_strand() -> None:
    """The literal `setRegionUnwound` fixed-pair port: `[lo, hi)` is
    removed from `lagging_strand_indexs[1]` (`oldStrd`) and added to
    `leading_strand_indexs[1]` (`newStrd`), regardless of which fork
    column it came from."""
    p = KarrReplicationProcess({})
    old_strand = int(p.lagging_strand_indexs[1])
    new_strand = int(p.leading_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(0, old_strand, p.sequence_len_bp)], shape=_shape(p))

    result = p._set_region_unwound(polymerized, lo=10000, hi=10500)

    regions = sorted(result.to_regions())
    assert regions == [
        (0, old_strand, 10000),
        (10000, new_strand, 500),
        (10500, old_strand, p.sequence_len_bp - 10500),
    ]


def test_set_region_unwound_merges_touching_new_strand_fragment() -> None:
    """The daughter strand (`newStrd`) already has an adjacent (touching)
    fragment from a prior tick's unwinding -- growth must MERGE into one
    contiguous entry (Chromosome.m:1954 `mergeOwnAdjacentRegions`), not
    leave two separate touching entries."""
    p = KarrReplicationProcess({})
    old_strand = int(p.lagging_strand_indexs[1])
    new_strand = int(p.leading_strand_indexs[1])
    polymerized = SparseTriplet.from_regions(
        [(0, old_strand, p.sequence_len_bp), (10500, new_strand, 300)], shape=_shape(p)
    )

    result = p._set_region_unwound(polymerized, lo=10000, hi=10500)

    regions = sorted(result.to_regions())
    assert regions == [
        (0, old_strand, 10000),
        (10000, new_strand, 800),
        (10500, old_strand, p.sequence_len_bp - 10500),
    ]


def test_set_region_unwound_raises_on_overlap_with_existing_new_strand_region() -> None:
    """Fail-closed: the daughter strand already has a region genuinely
    OVERLAPPING (not just touching) the newly-unwound span -- corrupt
    state, must raise rather than silently resolve (mirrors
    `merge_adjacent_regions`'s own overlap-fatal invariant)."""
    p = KarrReplicationProcess({})
    old_strand = int(p.lagging_strand_indexs[1])
    new_strand = int(p.leading_strand_indexs[1])
    polymerized = SparseTriplet.from_regions(
        [(0, old_strand, p.sequence_len_bp), (10200, new_strand, 100)], shape=_shape(p)
    )

    with pytest.raises(ValueError, match="corrupt"):
        p._set_region_unwound(polymerized, lo=10000, hi=10500)


def test_set_region_unwound_conserves_total_span_across_both_strands() -> None:
    """Mass/topology conservation: the exact amount removed from the old
    strand equals the exact amount added to the new strand -- no bp is
    fabricated or lost, and no other strand's total is touched."""
    p = KarrReplicationProcess({})
    old_strand = int(p.lagging_strand_indexs[1])
    new_strand = int(p.leading_strand_indexs[1])
    other_strand = int(p.lagging_strand_indexs[0])
    polymerized = SparseTriplet.from_regions(
        [(0, old_strand, p.sequence_len_bp), (200000, other_strand, 4000)], shape=_shape(p)
    )
    old_total_before = int(polymerized.values[polymerized.strands == old_strand].sum())
    new_total_before = int(polymerized.values[polymerized.strands == new_strand].sum())
    other_total_before = int(polymerized.values[polymerized.strands == other_strand].sum())

    result = p._set_region_unwound(polymerized, lo=50000, hi=57500)

    old_total_after = int(result.values[result.strands == old_strand].sum())
    new_total_after = int(result.values[result.strands == new_strand].sum())
    other_total_after = int(result.values[result.strands == other_strand].sum())

    assert old_total_before - old_total_after == 7500
    assert new_total_after - new_total_before == 7500
    assert other_total_after == other_total_before


def test_set_region_unwound_noop_on_empty_span() -> None:
    p = KarrReplicationProcess({})
    old_strand = int(p.lagging_strand_indexs[1])
    polymerized = SparseTriplet.from_regions([(0, old_strand, p.sequence_len_bp)], shape=_shape(p))

    result = p._set_region_unwound(polymerized, lo=5000, hi=5000)

    assert result.to_regions() == polymerized.to_regions()


# --- Direct wiring-proof tests -----------------------------------------
#
# These prove `next_update`'s active-topology branch genuinely INVOKES the
# staged literal Okazaki-fragment pipeline (`_initiate_okazaki_fragments`,
# `_advance_replication_forks`) rather than merely having them defined as
# dead, uncalled helpers, and that the OLD monolithic
# `_build_polymerized_regions` path is NOT reachable from an active
# elongating tick anymore (adjudication: "dead helpers cannot be
# integrated" / "assert the old monolithic builder is not called in
# active topology mode").


def test_next_update_invokes_initiate_and_advance_helpers(monkeypatch: Any) -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    initiate_calls: list[int] = []
    advance_calls: list[int] = []
    orig_initiate = KarrReplicationProcess._initiate_okazaki_fragments
    orig_advance = KarrReplicationProcess._advance_replication_forks

    def _spy_initiate(self: KarrReplicationProcess, **kwargs: Any) -> Any:
        initiate_calls.append(1)
        return orig_initiate(self, **kwargs)

    def _spy_advance(self: KarrReplicationProcess, **kwargs: Any) -> Any:
        advance_calls.append(1)
        return orig_advance(self, **kwargs)

    monkeypatch.setattr(KarrReplicationProcess, "_initiate_okazaki_fragments", _spy_initiate)
    monkeypatch.setattr(KarrReplicationProcess, "_advance_replication_forks", _spy_advance)

    update = p.next_update(1.0, state)

    assert initiate_calls, "next_update must invoke _initiate_okazaki_fragments on an active elongating tick"
    assert advance_calls, "next_update must invoke _advance_replication_forks on an active elongating tick"
    assert update["chromosome"]["fork_position_bp"]["left"] == 100.0
    assert update["chromosome"]["fork_position_bp"]["right"] == 100.0


def test_next_update_fails_if_initiate_helper_deleted(monkeypatch: Any) -> None:
    """Monkeypatching out the new helper must change/fail the result --
    otherwise the wiring test above could pass on dead code that is never
    actually on the call path (no dead-code false coverage)."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    def _broken_initiate(self: KarrReplicationProcess, **kwargs: Any) -> Any:
        raise RuntimeError("_initiate_okazaki_fragments must be on next_update's active call path")

    monkeypatch.setattr(KarrReplicationProcess, "_initiate_okazaki_fragments", _broken_initiate)

    with pytest.raises(RuntimeError, match="_initiate_okazaki_fragments must be on next_update"):
        p.next_update(1.0, state)


def test_next_update_fails_if_advance_helper_deleted(monkeypatch: Any) -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    def _broken_advance(self: KarrReplicationProcess, **kwargs: Any) -> Any:
        raise RuntimeError("_advance_replication_forks must be on next_update's active call path")

    monkeypatch.setattr(KarrReplicationProcess, "_advance_replication_forks", _broken_advance)

    with pytest.raises(RuntimeError, match="_advance_replication_forks must be on next_update"):
        p.next_update(1.0, state)


def test_next_update_invokes_set_region_unwound_on_active_leading_advance(monkeypatch: Any) -> None:
    """Direct live-path proof that the corrected `polymerizedRegions`
    mutation (`_set_region_unwound`, the literal `setRegionUnwound`
    fixed-pair port) -- not the old buggy per-column
    `_extend_polymerized_region(strand=leading_strand, ...)` call -- is
    genuinely on `next_update`'s active leading-strand-advance call path,
    for a real generic active-elongating tick."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    calls: list[tuple[int, int]] = []
    orig = KarrReplicationProcess._set_region_unwound

    def _spy(self: KarrReplicationProcess, polymerized: Any, *, lo: int, hi: int) -> Any:
        calls.append((lo, hi))
        return orig(self, polymerized, lo=lo, hi=hi)

    monkeypatch.setattr(KarrReplicationProcess, "_set_region_unwound", _spy)

    p.next_update(1.0, state)

    assert calls, "next_update's active leading-strand advance must call _set_region_unwound"
    assert all(hi > lo for lo, hi in calls)


def test_next_update_fails_if_set_region_unwound_helper_deleted(monkeypatch: Any) -> None:
    """No dead-code false coverage: breaking `_set_region_unwound` must
    change/fail the result of a real active tick."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    def _broken(self: KarrReplicationProcess, polymerized: Any, *, lo: int, hi: int) -> Any:
        raise RuntimeError("_set_region_unwound must be on next_update's active call path")

    monkeypatch.setattr(KarrReplicationProcess, "_set_region_unwound", _broken)

    with pytest.raises(RuntimeError, match="_set_region_unwound must be on next_update"):
        p.next_update(1.0, state)


def test_next_update_does_not_call_legacy_monolithic_builder_in_active_topology_mode(
    monkeypatch: Any,
) -> None:
    """The OLD monolithic scalar-progress `_build_polymerized_regions`
    path must NOT be reachable anymore once a tick is genuinely active
    (real helicase + leading-strand-elongating gate true) -- the literal
    per-fragment pipeline is the only path to a `polymerizedRegions`
    update in that case."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _active_replisome_base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )

    def _forbidden_build(self: KarrReplicationProcess, **kwargs: Any) -> Any:
        raise AssertionError(
            "_build_polymerized_regions (legacy monolithic scheme) must not be "
            "called from next_update's active elongating branch"
        )

    monkeypatch.setattr(KarrReplicationProcess, "_build_polymerized_regions", _forbidden_build)

    update = p.next_update(1.0, state)

    assert update["chromosome"]["fork_position_bp"]["left"] == 100.0
    assert update["chromosome"]["fork_position_bp"]["right"] == 100.0


def test_next_update_raises_when_active_but_no_lagging_polymerase_and_no_bootstrap() -> None:
    """Direction #2's fail-closed mandate: if activity is true (real
    helicase + leading-strand-elongating both columns) but the required
    position-resolved lagging-polymerase/backup-beta-clamp state is
    absent or inconsistent, `next_update` must raise a specific
    unsupported/incomplete-state error rather than silently falling back
    to scalar/monolithic topology. Reusing the "generic active" scenario's
    real helicase+leading complexBoundSites, but omitting the lagging
    polymerase entries and any legitimate first-fragment-split backup
    clamp, reproduces exactly that unsupported state."""
    p = KarrReplicationProcess({})
    lead0, lead1 = p.leading_strand_indexs
    a0 = p.primase_binding_locations[0]
    a1 = p.primase_binding_locations[1]
    starts0_t = int(a0[99])
    starts1_t = int(a1[99])
    leading_pos0_target = starts0_t - 50
    leading_pos1_target = starts1_t + 50
    cor_ftpt5 = p.core_footprint_5prime_bp
    lead_raw0 = (leading_pos0_target - cor_ftpt5) % p.sequence_len_bp
    hol_ftpt = p.polymerase_holoenzyme_footprint_bp
    lead_raw1 = (leading_pos1_target - hol_ftpt + cor_ftpt5 + 1) % p.sequence_len_bp
    helicase_pos0_t = leading_pos0_target - 50
    helicase_pos1_t = leading_pos1_target + 50

    entries = [
        (helicase_pos0_t, lead0, p.helicase_global_index),
        (helicase_pos1_t, lead1, p.helicase_global_index),
        (lead_raw0, lead0, p.core_beta_clamp_gamma_complex_global_index),
        (lead_raw1, lead1, p.core_beta_clamp_gamma_complex_global_index),
        # Deliberately no lagging polymerase / backup-clamp entries.
    ]
    complex_bound_sites = SparseTriplet.from_regions(entries, shape=p.chromosome_shape)
    polymerized = SparseTriplet.from_regions(
        [
            (leading_pos0_target, lead0, 20000),
            (leading_pos1_target - 20000, lead1, 20000),
        ],
        shape=p.chromosome_shape,
    )

    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["chromosome"]["polymerizedRegions"] = polymerized.to_state()
    state["chromosome"]["complexBoundSites"] = complex_bound_sites.to_state()
    state["chromosome"]["strandBreaks"] = SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state()

    with pytest.raises(ReplicationTopologyError):
        p.next_update(1.0, state)


def test_next_update_benign_skip_when_leading_still_combined_and_no_lagging_yet() -> None:
    """Replication.m:707-727 `tfs`-false case (the literal tick-1 source
    state): both fork columns have a real, active helicase + leading
    polymerase, but the leading position still holds the PRE-split
    COMBINED replisome complex (`two_core_beta_clamp_gamma_complex_
    primase`, MATLAB's `leadPolGblIdx(1)`) and no backup beta-clamp has
    reached the first-Okazaki-fragment site yet (indeed no backup clamp is
    bound anywhere) -- i.e. `laggingBackupBetaClampPosition==
    firstBetaClampPos` is false, so `tfs` is false and MATLAB's own
    `unwindAndPolymerizeDNA` legitimately does NOT split/bind a lagging
    polymerase this tick. This is otherwise position-identical to
    `test_next_update_raises_when_active_but_no_lagging_polymerase_and_no_
    bootstrap` above -- only the leading-position enzyme value differs
    (combined vs. already-split-alone) -- proving the fix distinguishes
    the two cases on that one condition, exactly mirroring MATLAB's own
    third `tfs` conjunct, rather than on any fabricated heuristic.

    Expected: no exception, no lagging polymerase materializes this tick,
    a `_bootstrap_not_ready_census` telemetry entry is recorded for both
    columns, and ordinary non-topology update/request behavior (dNTP/ATP
    requests, no crash) still occurs -- matching Karr's "skip this
    column's lagging-specific bookkeeping, but otherwise proceed" (not
    "blanket no-op the whole tick") semantics.
    """
    p = KarrReplicationProcess({})
    lead0, lead1 = p.leading_strand_indexs
    a0 = p.primase_binding_locations[0]
    a1 = p.primase_binding_locations[1]
    starts0_t = int(a0[99])
    starts1_t = int(a1[99])
    leading_pos0_target = starts0_t - 50
    leading_pos1_target = starts1_t + 50
    cor_ftpt5 = p.core_footprint_5prime_bp
    lead_raw0 = (leading_pos0_target - cor_ftpt5) % p.sequence_len_bp
    hol_ftpt = p.polymerase_holoenzyme_footprint_bp
    lead_raw1 = (leading_pos1_target - hol_ftpt + cor_ftpt5 + 1) % p.sequence_len_bp
    helicase_pos0_t = leading_pos0_target - 50
    helicase_pos1_t = leading_pos1_target + 50

    entries = [
        (helicase_pos0_t, lead0, p.helicase_global_index),
        (helicase_pos1_t, lead1, p.helicase_global_index),
        # The pre-split COMBINED complex -- the one difference from the
        # negative (still-raises) test above.
        (lead_raw0, lead0, p.two_core_beta_clamp_gamma_complex_primase_global_index),
        (lead_raw1, lead1, p.two_core_beta_clamp_gamma_complex_primase_global_index),
        # Deliberately no lagging polymerase / backup-clamp entries.
    ]
    complex_bound_sites = SparseTriplet.from_regions(entries, shape=p.chromosome_shape)
    polymerized = SparseTriplet.from_regions(
        [
            (leading_pos0_target, lead0, 20000),
            (leading_pos1_target - 20000, lead1, 20000),
        ],
        shape=p.chromosome_shape,
    )

    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid, p.h2o_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["chromosome"]["polymerizedRegions"] = polymerized.to_state()
    state["chromosome"]["complexBoundSites"] = complex_bound_sites.to_state()
    state["chromosome"]["strandBreaks"] = SparseTriplet.from_regions([], shape=p.chromosome_shape).to_state()

    assert p._bootstrap_not_ready_census == {0: 0, 1: 0}

    update = p.next_update(1.0, state)  # must not raise

    assert p._bootstrap_not_ready_census == {0: 1, 1: 1}

    out_sites = SparseTriplet.from_state(
        update["chromosome"]["complexBoundSites"], shape=p.chromosome_shape
    )
    assert p._lagging_polymerase_positions(out_sites) == (-1, -1)

    # Ordinary non-topology update/request behavior still happens: real
    # dNTP/ATP demand is (or may legitimately be) requested for the
    # leading-only advance, and enzyme/boundEnzyme bookkeeping keys exist,
    # matching every other active-elongating tick -- this is not a
    # blanket "do nothing" skip.
    assert p.name in update["requests"]
    assert set(update["requests"][p.name]) == {*p.dntp_wids, p.atp_wid, p.h2o_wid}
