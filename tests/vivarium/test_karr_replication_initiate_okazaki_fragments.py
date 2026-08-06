"""Standalone tests for `KarrReplicationProcess._initiate_okazaki_fragments`.

Literal port of `Replication.m`'s `initiateOkazakiFragment` (~line 1063):
binds a beta-clamp at the start of the next not-yet-bound Okazaki fragment on
each lagging-strand column, gated by helicase/leading-polymerase activity,
backup-clamp reload timing, footprint clearance ahead of the helicase,
absence of an already-bound backup clamp at the exact target site, and the
strand not already being fully polymerized (`strandPolymerized`).

All scenarios are constructed directly from the real fixture-derived
`primase_binding_locations`/footprint constants and hand-built
`complexBoundSites`/`polymerizedRegions` sparse triples -- no oracle trace
file is read (adjudication #7: "no trace-after/oracle-file access").
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.state.chromosome_store import SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess, ReplicationTopologyError


@pytest.fixture(scope="module")
def process() -> KarrReplicationProcess:
    return KarrReplicationProcess({})


def _bound_sites(process: KarrReplicationProcess, entries: list[tuple[int, int, int]]) -> SparseTriplet:
    return SparseTriplet.from_regions(entries, shape=process.chromosome_shape)


def _empty_triplet(process: KarrReplicationProcess) -> SparseTriplet:
    return SparseTriplet.empty(*process.chromosome_shape)


def _lagging_pol_pos_for_target(
    process: KarrReplicationProcess, lagging_pos: int, column: int
) -> int:
    """Invert `_lagging_position` to find the raw core/beta-clamp/primase
    complex position that produces the desired derived `laggingPosition`
    value on the given column (0 or 1)."""
    seq_len = process.sequence_len_bp
    hol_ftpt = process.polymerase_holoenzyme_footprint_bp
    cor_ftpt5 = process.core_footprint_5prime_bp
    if column == 0:
        return (lagging_pos - hol_ftpt + cor_ftpt5 + 1) % seq_len
    return (lagging_pos - cor_ftpt5) % seq_len


def _base_resources(process: KarrReplicationProcess) -> tuple[dict, dict, dict]:
    enzymes_next = {process.enzyme_wid_beta_clamp_monomer: 100.0}
    bound_next: dict = {}
    substrates_next = {
        process.atp_wid: 100.0,
        process.h2o_wid: 100.0,
        process.adp_wid: 0.0,
        process.pi_wid: 0.0,
        process.h_wid: 0.0,
    }
    return enzymes_next, bound_next, substrates_next


def _full_replisome_sites(
    process: KarrReplicationProcess,
    *,
    helicase_pos0: int,
    helicase_pos1: int,
    lagging_pol_pos: dict[int, int] | None = None,
) -> list[tuple[int, int, int]]:
    lead0, lead1 = process.leading_strand_indexs
    # Leading-polymerase positions are fixed, arbitrary, and deliberately far
    # from every helicase/target position used across this file's scenarios
    # so they never collide with a helicase entry on the same strand (a
    # real chromosome position+strand can only hold one bound complex; a
    # same-site collision would otherwise get silently summed together by
    # `SparseTriplet`'s region-style value-reduction, corrupting the global
    # index -- polymerase position itself is never read by
    # `_initiate_okazaki_fragments`, only its "bound" sentinel).
    lead_pol_pos0 = 300000
    lead_pol_pos1 = 300001
    entries = [
        (helicase_pos0, lead0, process.helicase_global_index),
        (helicase_pos1, lead1, process.helicase_global_index),
        (lead_pol_pos0, lead0, process.core_beta_clamp_gamma_complex_global_index),
        (lead_pol_pos1, lead1, process.core_beta_clamp_gamma_complex_global_index),
    ]
    lag0, lag1 = process.lagging_strand_indexs
    lagging_pol_pos = lagging_pol_pos or {}
    if 0 in lagging_pol_pos:
        entries.append((lagging_pol_pos[0], lag0, process.core_beta_clamp_primase_global_index))
    if 1 in lagging_pol_pos:
        entries.append((lagging_pol_pos[1], lag1, process.core_beta_clamp_primase_global_index))
    return entries


def test_no_helicase_bound_does_nothing(process: KarrReplicationProcess) -> None:
    sites = _empty_triplet(process)
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    assert result.values.size == 0
    assert bound_next == {}


def test_leading_strand_not_elongating_does_nothing(process: KarrReplicationProcess) -> None:
    lead0, lead1 = process.leading_strand_indexs
    # Helicase bound on both columns, but no leading polymerase anywhere.
    sites = _bound_sites(
        process,
        [
            (500000, lead0, process.helicase_global_index),
            (5000, lead1, process.helicase_global_index),
        ],
    )
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    assert result.values.size == sites.values.size
    assert bound_next == {}


def test_column0_first_fragment_binds_at_computed_site(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    target0 = int(array0[0]) - process.core_footprint_3prime_bp - process.beta_clamp_footprint_bp
    # Helicase well upstream of target0 (small position value): satisfies
    # `helPos(1) + helFtpt5 + 1 < target0`. Column 1's helicase is placed
    # right at 0 so its own condition (`helPos(2)+helFtpt3 > target1`) is
    # false, isolating this test to a single column-0 candidate.
    sites = _bound_sites(
        process,
        _full_replisome_sites(process, helicase_pos0=100, helicase_pos1=0),
    )
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    lag0 = process.lagging_strand_indexs[0]
    mask = (result.strands == lag0) & (result.values == process.beta_clamp_global_index)
    assert result.positions[mask].tolist() == [target0]
    assert bound_next[process.enzyme_wid_beta_clamp] == 1.0
    assert enzymes_next[process.enzyme_wid_beta_clamp_monomer] == 98.0
    assert substrates_next[process.atp_wid] == 99.0
    assert substrates_next[process.h2o_wid] == 99.0
    assert substrates_next[process.adp_wid] == 1.0
    assert substrates_next[process.pi_wid] == 1.0
    assert substrates_next[process.h_wid] == 1.0


def test_column1_region_b_first_fragment_binds_at_computed_site(process: KarrReplicationProcess) -> None:
    array1 = process.primase_binding_locations[1]
    # Replication.m:1062-1064: the helicase-clearance *gate* threshold is
    # padded by the full beta-clamp footprint (`+bClmpFtpt`), but the
    # actual beta-clamp bind *position* (`posStrnds`) omits that padding --
    # these are two literally different MATLAB expressions for column 1.
    bind_position1 = int(array1[0]) + process.core_footprint_3prime_bp + 1
    gate_threshold1 = bind_position1 + process.beta_clamp_footprint_bp
    # Column 0's helicase placed far downstream (large position) so its own
    # condition (`helPos(1)+helFtpt5+1 < target0`) is false; column 1's
    # helicase placed well past gate_threshold1 to satisfy
    # `helPos(2)+helFtpt3 > gate_threshold1`.
    sites = _bound_sites(
        process,
        _full_replisome_sites(
            process,
            helicase_pos0=process.sequence_len_bp - 1,
            helicase_pos1=gate_threshold1 + process.helicase_footprint_3prime_bp + 100,
        ),
    )
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    lag1 = process.lagging_strand_indexs[1]
    mask = (result.strands == lag1) & (result.values == process.beta_clamp_global_index)
    assert result.positions[mask].tolist() == [bind_position1]
    assert bound_next[process.enzyme_wid_beta_clamp] == 1.0


def test_both_columns_bind_when_both_gates_pass(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    array1 = process.primase_binding_locations[1]
    target0 = int(array0[0]) - process.core_footprint_3prime_bp - process.beta_clamp_footprint_bp
    bind_position1 = int(array1[0]) + process.core_footprint_3prime_bp + 1
    gate_threshold1 = bind_position1 + process.beta_clamp_footprint_bp
    sites = _bound_sites(
        process,
        _full_replisome_sites(
            process,
            helicase_pos0=100,
            helicase_pos1=gate_threshold1 + process.helicase_footprint_3prime_bp + 100,
        ),
    )
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    assert bound_next[process.enzyme_wid_beta_clamp] == 2.0
    beta_clamp_positions = sorted(result.positions[result.values == process.beta_clamp_global_index].tolist())
    assert beta_clamp_positions == sorted([target0, bind_position1])


def test_resource_limited_binds_column0_first_deterministically(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    array1 = process.primase_binding_locations[1]
    bind_position1 = int(array1[0]) + process.core_footprint_3prime_bp + 1
    gate_threshold1 = bind_position1 + process.beta_clamp_footprint_bp
    sites = _bound_sites(
        process,
        _full_replisome_sites(
            process,
            helicase_pos0=100,
            helicase_pos1=gate_threshold1 + process.helicase_footprint_3prime_bp + 100,
        ),
    )
    enzymes_next = {process.enzyme_wid_beta_clamp_monomer: 2.0}  # exactly 1 binding's worth
    bound_next: dict = {}
    substrates_next = {
        process.atp_wid: 100.0,
        process.h2o_wid: 100.0,
        process.adp_wid: 0.0,
        process.pi_wid: 0.0,
        process.h_wid: 0.0,
    }
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    assert bound_next[process.enzyme_wid_beta_clamp] == 1.0
    target0 = int(array0[0]) - process.core_footprint_3prime_bp - process.beta_clamp_footprint_bp
    assert result.positions[result.values == process.beta_clamp_global_index].tolist() == [target0]


def test_existing_backup_clamp_at_target_blocks_initiation(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    target0 = int(array0[0]) - process.core_footprint_3prime_bp - process.beta_clamp_footprint_bp
    lag0 = process.lagging_strand_indexs[0]
    entries = _full_replisome_sites(process, helicase_pos0=100, helicase_pos1=0)
    entries.append((target0, lag0, process.beta_clamp_global_index))
    sites = _bound_sites(process, entries)
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    assert result.values.size == sites.values.size
    assert bound_next == {}


def test_reload_length_not_yet_met_blocks_initiation(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    # fIdx[0] == 1, progress == 0 < laggingBackupClampReloadingLength.
    lagging_pos0 = int(array0[0])
    lag_pol_pos0 = _lagging_pol_pos_for_target(process, lagging_pos0, column=0)
    sites = _bound_sites(
        process,
        _full_replisome_sites(
            process, helicase_pos0=100, helicase_pos1=0, lagging_pol_pos={0: lag_pol_pos0}
        ),
    )
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=_empty_triplet(process),
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    assert not np.any(result.values == process.beta_clamp_global_index)
    assert bound_next == {}


def test_strand_fully_polymerized_blocks_initiation(process: KarrReplicationProcess) -> None:
    seq_len = process.sequence_len_bp
    # All 4 strands fully polymerized from position 0 to sequence end ->
    # `_strand_polymerized` reports both columns True -> both blocked.
    polymerized = _bound_sites(process, [(0, strand, seq_len) for strand in range(4)])
    sites = _bound_sites(
        process,
        _full_replisome_sites(process, helicase_pos0=100, helicase_pos1=0),
    )
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    result = process._initiate_okazaki_fragments(
        polymerized=polymerized,
        complex_bound_sites=sites,
        enzymes_next=enzymes_next,
        bound_next=bound_next,
        substrates_next=substrates_next,
    )
    assert not np.any(result.values == process.beta_clamp_global_index)
    assert bound_next == {}


def test_foreign_complex_at_target_site_fails_closed(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    target0 = int(array0[0]) - process.core_footprint_3prime_bp - process.beta_clamp_footprint_bp
    lag0 = process.lagging_strand_indexs[0]
    # A foreign (non-backup-clamp) complex sitting exactly at the target
    # site: the literal MATLAB gating (`bClmpPos(1) ~= target`) does not
    # catch this -- generic footprint-conflict machinery
    # (`isRegionAccessible`) is deferred (adjudication #2), so this must
    # fail closed rather than silently double-bind.
    entries = _full_replisome_sites(process, helicase_pos0=100, helicase_pos1=0)
    entries.append((target0, lag0, process.core_global_index))
    sites = _bound_sites(process, entries)
    enzymes_next, bound_next, substrates_next = _base_resources(process)
    with pytest.raises(ReplicationTopologyError):
        process._initiate_okazaki_fragments(
            polymerized=_empty_triplet(process),
            complex_bound_sites=sites,
            enzymes_next=enzymes_next,
            bound_next=bound_next,
            substrates_next=substrates_next,
        )


def test_deterministic_no_rng_usage(process: KarrReplicationProcess) -> None:
    # Adjudication #3: initiation site choice must be deterministic (no RNG
    # draw). Running twice from identical inputs must give identical output.
    sites = _bound_sites(
        process,
        _full_replisome_sites(process, helicase_pos0=100, helicase_pos1=0),
    )
    results = []
    for _ in range(2):
        enzymes_next, bound_next, substrates_next = _base_resources(process)
        result = process._initiate_okazaki_fragments(
            polymerized=_empty_triplet(process),
            complex_bound_sites=sites,
            enzymes_next=enzymes_next,
            bound_next=bound_next,
            substrates_next=substrates_next,
        )
        results.append(result.positions.tolist())
    assert results[0] == results[1]
