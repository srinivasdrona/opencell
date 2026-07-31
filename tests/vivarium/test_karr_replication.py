from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

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
from opencell.vivarium.karr_replication import KarrReplicationProcess


def _base_state(
    process: KarrReplicationProcess,
    *,
    replication_state: str = "idle",
    initial_substrate: float = 0.0,
    allocated_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    request_wids = [*process.dntp_wids, process.atp_wid]
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
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
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
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
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
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
        p,
        replication_state="idle",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["boundEnzymes"][p.enzyme_wid_helicase] = 2.0
    _set_pre_split_polymerase_composition(state, p)
    helicase_global_index = int(p.enzyme_global_indexs[p.enzyme_index_helicase])
    state["chromosome"]["complexBoundSites"] = _complex_bound_sites_with_values(p, [helicase_global_index])

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
    must still promote."""
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
        p,
        replication_state="idle",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["boundEnzymes"] = {wid: 0.0 for wid in p.enzyme_wids}
    state["boundEnzymes"][p.enzyme_wid_helicase] = 1.0
    _set_post_split_polymerase_composition(state, p)
    helicase_global_index = int(p.enzyme_global_indexs[p.enzyme_index_helicase])
    state["chromosome"]["complexBoundSites"] = _complex_bound_sites_with_values(p, [helicase_global_index])

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
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
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
    helicase_global_index = int(p.enzyme_global_indexs[p.enzyme_index_helicase])
    state["chromosome"]["complexBoundSites"] = _complex_bound_sites_with_values(p, [helicase_global_index])

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
        allocated_override={wid: 1e6 for wid in [*p.dntp_wids, p.atp_wid]},
    )
    update = p.next_update(1.0, state)
    assert update["chromosome"]["replication_state"] == "elongating"
    assert update.get("chromosome", {}).get("fork_position_bp", {}) == {}
    seeded = SparseTriplet.from_state(update["chromosome"]["polymerizedRegions"], shape=p.chromosome_shape)
    assert seeded.positions.tolist() == [0, 22, 580054]
    assert seeded.strands.tolist() == [0, 1, 3]
    assert seeded.values.tolist() == [580076, 580032, 22]
    assert all(v == 0.0 for v in update["requests"][p.name].values())


def test_elongation_advances_and_consumes_dntps() -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
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
    p = KarrReplicationProcess({})
    alloc = {wid: 1e9 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override=alloc,
    )
    state["chromosome"]["fork_position_bp"]["left"] = float(p.terc_position_bp - 10)
    state["chromosome"]["fork_position_bp"]["right"] = float(p.terc_position_bp - 10)

    update1 = p.next_update(1.0, state)
    _apply_update(state, update1, p)
    assert state["chromosome"]["replication_state"] == "complete"
    assert state["chromosome"]["events"]["replication_complete"] == 1.0

    update2 = p.next_update(1.0, state)
    _apply_update(state, update2, p)
    assert state["chromosome"]["events"]["replication_complete"] == 1.0


def test_limited_allocation_scales_progress_proportionally() -> None:
    p = KarrReplicationProcess({})
    desired = p._demand_from_advances(100, 100)
    alloc = {wid: math.floor(val * 0.25) for wid, val in desired.items()}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e9,
        allocated_override={wid: float(alloc[wid]) for wid in alloc},
    )

    update = p.next_update(1.0, state)
    fork_delta = update["chromosome"]["fork_position_bp"]
    scale = min(float(alloc[wid]) / float(desired[wid]) for wid in desired if desired[wid] > 0)
    expected_per_fork = float(math.floor(100.0 * scale))
    assert fork_delta["left"] == expected_per_fork
    assert fork_delta["right"] == expected_per_fork
    assert update["requests"][p.name][p.atp_wid] == float(desired[p.atp_wid])


def test_long_partial_run_monotonic_no_nan_mass_closes() -> None:
    p = KarrReplicationProcess({})
    alloc = {wid: 1e12 for wid in [*p.dntp_wids, p.atp_wid]}
    state = _base_state(
        p,
        replication_state="elongating",
        initial_substrate=1e12,
        allocated_override=alloc,
    )

    prev_left = 0.0
    prev_right = 0.0
    ticks = 1000
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

    total_advance_bp = int(
        state["chromosome"]["fork_position_bp"]["left"] + state["chromosome"]["fork_position_bp"]["right"]
    )
    consumed_datp = int(round(1e12 - state["substrates"]["DATP"]))
    consumed_dctp = int(round(1e12 - state["substrates"]["DCTP"]))
    consumed_dgtp = int(round(1e12 - state["substrates"]["DGTP"]))
    consumed_dttp = int(round(1e12 - state["substrates"]["DTTP"]))
    consumed_atp = int(round(1e12 - state["substrates"]["ATP"]))

    assert consumed_datp >= 0
    assert consumed_dctp >= 0
    assert consumed_dgtp >= 0
    assert consumed_dttp >= 0
    assert consumed_atp >= 0

    # DNA synthesis consumes 2 nucleotides per bp advanced across both forks.
    assert consumed_datp + consumed_dctp + consumed_dgtp + consumed_dttp == 2 * total_advance_bp
    assert consumed_atp == total_advance_bp
