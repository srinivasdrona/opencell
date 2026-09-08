from __future__ import annotations

import math
import sys
from copy import deepcopy
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
from opencell.vivarium.karr_replication_initiation import (
    KarrReplicationInitiationProcess,
    _Mcg16807RandStream,
)


def _base_state(
    process: KarrReplicationInitiationProcess,
    *,
    free_dnaa: float,
    atp: float,
    supercoiled: bool = True,
) -> dict[str, Any]:
    return {
        "chromosome": {
            "dnaa_complex_count": {site_id: 0 for site_id in process.all_dnaa_sites},
            "replication_state": "idle",
            "supercoiled": supercoiled,
        },
        "protein": {"counts": {process.dnaa_wid: float(free_dnaa)}},
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "requests": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
        "substrates_allocated": {
            process.name: {process.atp_wid: float(atp), process.water_wid: float(atp)}
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for site_id, delta in update.get("chromosome", {}).get("dnaa_complex_count", {}).items():
        state["chromosome"]["dnaa_complex_count"][site_id] = int(
            state["chromosome"]["dnaa_complex_count"].get(site_id, 0) + int(delta)
        )
    if "replication_state" in update.get("chromosome", {}):
        state["chromosome"]["replication_state"] = str(update["chromosome"]["replication_state"])

    for wid, delta in update.get("protein", {}).get("counts", {}).items():
        current = float(state["protein"]["counts"].get(wid, 0.0))
        state["protein"]["counts"][wid] = float(current + float(delta))

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))
        state["substrates_allocated"][next(iter(state["substrates_allocated"]))][wid] = float(
            state["substrates"][wid]
        )


def _sum_oric(state: dict[str, Any], process: KarrReplicationInitiationProcess) -> int:
    return int(
        sum(
            int(state["chromosome"]["dnaa_complex_count"].get(site_id, 0))
            for site_id in process.oric_site_ids
        )
    )


def _normalize_for_compare(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _normalize_for_compare(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_for_compare(item) for item in value]
    return value


def _ticks_to_initiation(
    process: KarrReplicationInitiationProcess,
    state: dict[str, Any],
    *,
    max_ticks: int = 200,
) -> int | None:
    for tick in range(1, max_ticks + 1):
        update = process.next_update(1.0, state)
        _apply_update(state, update)
        if state["chromosome"]["replication_state"] == "initiating":
            return tick
    return None


def test_fixture_loads() -> None:
    p = KarrReplicationInitiationProcess({})
    assert p.name == "karr_replication_initiation"
    assert p.dnaa_wid == "MG_469_MONOMER"
    assert len(p.all_dnaa_sites) >= 2_000
    assert p.oric_site_ids == ["R1", "R2", "R3", "R4", "R5"]
    assert p.kb_atp > p.kb_adp > 0
    assert p.kd_atp > 0
    assert p.k_regen > 0


def test_mcg16807_rand_matches_primary_source_seed0_and_seed1() -> None:
    seed0 = _Mcg16807RandStream(0)
    seed1 = _Mcg16807RandStream(1)

    np.testing.assert_allclose(
        np.asarray(seed0.random(6), dtype=np.float64),
        np.array(
            [
                0.21895918632809036,
                0.047044616214486128,
                0.67886471686831895,
                0.67929640583661222,
                0.93469289594082761,
                0.38350207748985948,
            ],
            dtype=np.float64,
        ),
        rtol=0.0,
        atol=1.0e-15,
    )
    np.testing.assert_allclose(
        np.asarray(seed1.random(6), dtype=np.float64),
        np.array(
            [
                0.51290893578571684,
                0.46048375054285107,
                0.35039537369757673,
                0.09504573517248302,
                0.43367104392204014,
                0.70923519772907495,
            ],
            dtype=np.float64,
        ),
        rtol=0.0,
        atol=1.0e-15,
    )


def test_mcg16807_postrand_full_randperm_matches_primary_source() -> None:
    seed0 = _Mcg16807RandStream(0)
    seed1 = _Mcg16807RandStream(1)
    _ = seed0.random(5)
    _ = seed1.random(5)

    np.testing.assert_array_equal(
        seed0.randperm(9) + 1,
        np.array([8, 4, 5, 9, 1, 2, 6, 7, 3], dtype=np.int64),
    )
    np.testing.assert_array_equal(
        seed1.randperm(9) + 1,
        np.array([5, 3, 2, 8, 6, 4, 7, 1, 9], dtype=np.int64),
    )


def test_mcg16807_postrand_randsample_without_replacement_matches_karr_randstream() -> None:
    seed0 = _Mcg16807RandStream(0)
    seed1 = _Mcg16807RandStream(1)
    _ = seed0.random(5)
    _ = seed1.random(5)

    np.testing.assert_array_equal(
        seed0.randsample(9, 5, replacement=False, weights=None) + 1,
        np.array([8, 4, 5, 9, 1], dtype=np.int64),
    )
    np.testing.assert_array_equal(
        seed1.randsample(9, 5, replacement=False, weights=None) + 1,
        np.array([5, 3, 2, 8, 6], dtype=np.int64),
    )

    weights = np.array([1, 1, 1, 1, 2, 2, 2, 2, 2], dtype=np.float64)
    np.testing.assert_array_equal(
        seed0.randsample(9, 5, replacement=False, weights=weights) + 1,
        np.array([1, 5, 7, 9, 8], dtype=np.int64),
    )
    np.testing.assert_array_equal(
        seed1.randsample(9, 5, replacement=False, weights=weights) + 1,
        np.array([7, 6, 5, 4, 2], dtype=np.int64),
    )


def test_zero_free_dnaa_no_activity() -> None:
    p = KarrReplicationInitiationProcess({"rng_seed": 7})
    state = _base_state(p, free_dnaa=0.0, atp=10_000.0, supercoiled=True)
    update = p.next_update(1.0, state)
    assert update.get("chromosome", {}).get("dnaa_complex_count", {}) == {}
    assert p.atp_wid not in update.get("substrates", {})


def test_sync_internal_state_accepts_chromosome_bound_state() -> None:
    p = KarrReplicationInitiationProcess({})

    bound_atp = np.zeros((p.n_sites, 2), dtype=np.int64)
    bound_adp = np.zeros((p.n_sites, 2), dtype=np.int64)
    blocked_sites = np.zeros((p.n_sites, 2), dtype=bool)
    bound_atp[p.r5_index, 0] = 2
    bound_adp[p.r1234_indices[0], 1] = 1
    blocked_sites[p.r1234_indices[1], 1] = True

    p._sync_internal_state(
        free_dnaa=9,
        bound_atp=bound_atp,
        bound_adp=bound_adp,
        blocked_sites=blocked_sites,
    )

    assert p._initialized is True
    assert p._free_dnaa_adp == 9
    assert p._free_dnaa_atp == 0
    assert np.array_equal(p._bound_atp, bound_atp)
    assert np.array_equal(p._bound_adp, bound_adp)
    assert np.array_equal(p._blocked_sites, blocked_sites)


def test_resolve_bound_state_reads_second_copy_and_writeback_preserves_both_copies() -> None:
    p = KarrReplicationInitiationProcess({})
    first_global = int(p.enzyme_global_indexs[p.enzyme_index_dnaa_1mer_atp])
    second_global = int(p.enzyme_global_indexs[p.enzyme_indexs_dnaa_nmer_atp[-1]])
    foreign_global = int(first_global + 5_000)
    site_first = int(p.r5_index)
    site_second = int(p.r1234_indices[0])
    triplet = SparseTriplet(
        positions=np.asarray(
            [
                int(p._dnaa_box_positions[site_first]),
                int(p._dnaa_box_positions[site_second]),
                int(p._dnaa_box_positions[p.r1234_indices[1]]),
            ],
            dtype=np.int64,
        ),
        strands=np.asarray([0, 2, 2], dtype=np.int64),
        values=np.asarray([first_global, second_global, foreign_global], dtype=np.int64),
        shape=p.chromosome_shape,
    )

    bound_atp, bound_adp, blocked_sites = p._resolve_bound_state_from_chromosome(
        complex_bound_sites=triplet,
        legacy_counts={},
    )

    assert bound_atp[site_first, 0] == 1
    assert bound_atp[site_second, 1] == 7
    assert bound_adp[site_second, 1] == 0
    assert blocked_sites[p.r1234_indices[1], 1]

    p._bound_atp = bound_atp.copy()
    p._bound_adp = bound_adp.copy()
    p._blocked_sites = blocked_sites.copy()
    encoded = p._encode_complex_bound_sites(base_triplet=triplet, blocked_sites=blocked_sites)
    encoded_rows = {
        (int(position), int(strand)): int(value)
        for position, strand, value in zip(
            encoded.positions.tolist(),
            encoded.strands.tolist(),
            encoded.values.tolist(),
            strict=False,
        )
    }

    assert encoded_rows[(int(p._dnaa_box_positions[site_first]), 0)] == first_global
    assert encoded_rows[(int(p._dnaa_box_positions[site_second]), 2)] == second_global
    assert encoded_rows[(int(p._dnaa_box_positions[p.r1234_indices[1]]), 2)] == foreign_global


def test_activation_consumes_atp() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 1,
            "binding_rate_scale": 1.0e12,
            "polymerization_rate_scale": 1.0e12,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=8.0, atp=100.0, supercoiled=False)
    update = p.next_update(1.0, state)
    assert update["substrates"][p.atp_wid] == pytest.approx(-8.0)


def test_polymer_growth_at_oric() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 3,
            "binding_rate_scale": 1.0e10,
            "polymerization_rate_scale": 150.0,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=180.0, atp=5_000.0, supercoiled=True)
    start_oric = _sum_oric(state, p)
    for _ in range(8):
        _apply_update(state, p.next_update(1.0, state))
    end_oric = _sum_oric(state, p)
    assert end_oric > start_oric
    assert any(state["chromosome"]["dnaa_complex_count"][sid] > 0 for sid in p.r1234_site_ids)


def test_initiation_trigger_fires() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 11,
            "binding_rate_scale": 1.0e10,
            "polymerization_rate_scale": 90.0,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
            "r5_binding_boost": 100.0,
        }
    )
    state = _base_state(p, free_dnaa=260.0, atp=10_000.0, supercoiled=True)
    ticks = _ticks_to_initiation(p, state, max_ticks=50)
    assert ticks is not None
    assert state["chromosome"]["replication_state"] == "initiating"
    assert all(
        state["chromosome"]["dnaa_complex_count"][sid] >= int(p.parameters["r1234_threshold"])
        for sid in p.r1234_site_ids
    )
    assert state["chromosome"]["dnaa_complex_count"]["R5"] >= int(p.parameters["r5_threshold"])


def test_titration_effect() -> None:
    params = {
        "rng_seed": 13,
        "binding_rate_scale": 22_000.0,
        "polymerization_rate_scale": 220.0,
        "release_rate_scale": 1.0e12,
        "inactivation_rate_scale": 1.0e24,
        "regen_rate_scale": 1.0e12,
        "r5_binding_boost": 70.0,
    }
    p_lo = KarrReplicationInitiationProcess(params)
    p_hi = KarrReplicationInitiationProcess(params)

    low_titration = _base_state(p_lo, free_dnaa=260.0, atp=10_000.0, supercoiled=True)
    high_titration = _base_state(p_hi, free_dnaa=20.0, atp=10_000.0, supercoiled=True)
    for site_id in p_hi.non_oric_site_ids[:300]:
        high_titration["chromosome"]["dnaa_complex_count"][site_id] = 1

    ticks_low = _ticks_to_initiation(p_lo, low_titration, max_ticks=120)
    ticks_high = _ticks_to_initiation(p_hi, high_titration, max_ticks=120)
    assert ticks_low is not None
    assert ticks_high is None or ticks_high > ticks_low


def test_no_supercoil_no_polymerization() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 21,
            "binding_rate_scale": 1.0e12,
            "polymerization_rate_scale": 5.0,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=240.0, atp=5_000.0, supercoiled=False)
    for _ in range(10):
        _apply_update(state, p.next_update(1.0, state))
    assert all(state["chromosome"]["dnaa_complex_count"][sid] == 0 for sid in p.r1234_site_ids)


def test_deterministic_with_seed() -> None:
    params = {
        "rng_seed": 99,
        "binding_rate_scale": 40_000.0,
        "polymerization_rate_scale": 180.0,
        "release_rate_scale": 3_000.0,
        "inactivation_rate_scale": 5.0e15,
        "regen_rate_scale": 2_000.0,
    }
    p1 = KarrReplicationInitiationProcess(params)
    p2 = KarrReplicationInitiationProcess(params)
    s1 = _base_state(p1, free_dnaa=190.0, atp=8_000.0, supercoiled=True)
    s2 = deepcopy(s1)

    updates_1: list[dict[str, Any]] = []
    updates_2: list[dict[str, Any]] = []
    for _ in range(20):
        u1 = p1.next_update(1.0, s1)
        u2 = p2.next_update(1.0, s2)
        updates_1.append(u1)
        updates_2.append(u2)
        _apply_update(s1, u1)
        _apply_update(s2, u2)

    assert [_normalize_for_compare(update) for update in updates_1] == [
        _normalize_for_compare(update) for update in updates_2
    ]
    assert s1 == s2


def test_release_kinetics() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 5,
            "binding_rate_scale": 1.0e12,
            "polymerization_rate_scale": 1.0e12,
            "release_rate_scale": 8.0,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=0.0, atp=0.0, supercoiled=True)
    seeded_sites = ["R1", "R2", "R3", "R4", "R5"] + p.non_oric_site_ids[:15]
    for site_id in seeded_sites:
        state["chromosome"]["dnaa_complex_count"][site_id] = 4

    start_bound = sum(state["chromosome"]["dnaa_complex_count"][sid] for sid in seeded_sites)
    update = p.next_update(1.0, state)
    _apply_update(state, update)
    end_bound = sum(state["chromosome"]["dnaa_complex_count"][sid] for sid in seeded_sites)
    free_after = state["protein"]["counts"][p.dnaa_wid]

    assert end_bound < start_bound
    assert free_after > 0


# --- Explicit-enzyme-pool (source-faithful aggregate bind/polymerize/release) coverage ---
#
# The 14 tests above all drive the process through _base_state(), which only ever
# populates protein.counts[dnaa_wid] (the aggregate "MG_469_MONOMER" precursor form)
# and never any of the individual MG_469_*MER_ATP/ADP enzyme pool wids. That means
# has_enzyme_pools is always False for those tests, so none of them ever exercise
# _initialize_state_based_on_final_conditions, _bind_and_polymerize_dnaa_atp/adp, or
# _release_dnaa_axp -- the exact functions targeted by this session's source-fidelity
# RNG-consumption fixes. The tests below construct explicit MG_469_1MER_ATP/ADP pool
# states to engage has_enzyme_pools=True and directly regression-test the fixed paths.


def _empty_triplet(process: KarrReplicationInitiationProcess) -> SparseTriplet:
    return SparseTriplet(
        positions=np.zeros(0, dtype=np.int64),
        strands=np.zeros(0, dtype=np.int8),
        values=np.zeros(0, dtype=np.int32),
        shape=process.chromosome_shape,
    )


def test_explicit_enzyme_pool_state_engages_source_faithful_path_and_conserves_dnaa() -> None:
    """A real MG_469_1MER_ATP/ADP pool (not the legacy dnaa_wid-only state) must
    route through the aggregate bind/polymerize/release helpers, and total DnaA
    monomer-equivalents (free + polymer + bound) must be conserved over one tick
    since no dnaa_wid precursor is supplied to activateFreeDnaA."""
    p = KarrReplicationInitiationProcess({"rng_seed": 23})
    state = {
        "chromosome": {
            "dnaa_complex_count": {site_id: 0 for site_id in p.all_dnaa_sites},
            "replication_state": "idle",
            "supercoiled": True,
        },
        "protein": {"counts": {"MG_469_1MER_ATP": 80.0, "MG_469_1MER_ADP": 20.0}},
        "enzymes": {},
        "substrates": {wid: 0.0 for wid in p.substrate_wids},
        "requests": {p.name: {p.atp_wid: 0.0, p.water_wid: 0.0}},
        "substrates_allocated": {p.name: {p.atp_wid: 0.0, p.water_wid: 0.0}},
    }
    initial_total = 100

    update = p.next_update(1.0, state)

    assert p._using_explicit_enzyme_pools is True
    assert isinstance(update, dict)
    post_total = p._total_dnaa_monomer_equivalents(
        free_counts=p._free_enzyme_counts,
        bound_atp=p._bound_atp,
        bound_adp=p._bound_adp,
    )
    assert post_total == initial_total


def test_initialize_state_based_on_final_conditions_below_47_consumes_stochastic_round() -> None:
    """Regression test for the fixed RNG-consumption gap: MATLAB's
    `(DnaA_total >= 50) || stochasticRound(0.5 * (DnaA_total >= 47))` only
    short-circuits when DnaA_total>=50; for DnaA_total<47 the RHS
    stochasticRound(0) is still evaluated (and must still be called here),
    even though the Python if/elif previously had no else branch at all."""
    p = KarrReplicationInitiationProcess({"rng_seed": 29})
    calls: list[float] = []
    original = p._stochastic_round

    def recording(value: float) -> int | float:
        calls.append(float(value))
        return original(value)

    p._stochastic_round = recording  # type: ignore[method-assign]
    empty = _empty_triplet(p)
    blocked = np.zeros((p.n_sites, 2), dtype=bool)

    p._initialize_state_based_on_final_conditions(
        total_dnaa=10,
        monomer_bound_sites=empty,
        complex_bound_sites=empty,
        blocked_sites=blocked,
    )

    assert 0.0 in calls, (
        "expected an explicit stochasticRound(0.0) call for DnaA_total<47 "
        f"(recorded calls: {calls})"
    )


def test_bind_and_polymerize_dnaa_atp_zero_rate_denominator_consumes_stochastic_round() -> None:
    """Regression test for the fixed RNG-consumption gap: MATLAB calls
    stochasticRound(numFreeDnaAATP*totBindingRate/(totBindingRate+totPolRate))
    unconditionally; when the denominator is 0 (no accessible binding sites and
    no existing polymer), MATLAB's 0/0 NaN still consumes a draw via
    min(maxBinding, NaN). The Python port previously skipped both the call and
    the draw behind an `if denom > 0` guard."""
    p = KarrReplicationInitiationProcess({"rng_seed": 31})
    p.kb_atp = 0.0
    p.kb2_atp = 0.0
    p._using_explicit_enzyme_pools = True
    p._free_enzyme_counts = np.zeros(len(p.enzyme_wids), dtype=np.int64)
    p._free_enzyme_counts[p.enzyme_index_dnaa_1mer_atp] = 5
    p._free_dnaa_atp = 5
    p._bound_atp = np.zeros((p.n_sites, 2), dtype=np.int64)
    p._bound_adp = np.zeros((p.n_sites, 2), dtype=np.int64)
    p._blocked_sites = np.zeros((p.n_sites, 2), dtype=bool)
    p._initialized = True

    calls: list[float] = []
    original = p._stochastic_round

    def recording(value: float) -> int | float:
        calls.append(float(value))
        return original(value)

    p._stochastic_round = recording  # type: ignore[method-assign]
    empty = _empty_triplet(p)

    p._bind_and_polymerize_dnaa_atp(
        dt=1.0,
        monomer_bound_sites=empty,
        complex_bound_sites=empty,
        polymerized_regions=empty,
    )

    assert any(math.isnan(value) for value in calls), (
        "expected an explicit stochasticRound(NaN) call when the bind+poly rate "
        f"denominator is exactly 0 (recorded calls: {calls})"
    )


def test_stochastic_round_nan_consumes_draw_and_returns_nan() -> None:
    """Direct unit test for the fixed _Mcg16807RandStream.stochastic_round: it
    must always consume exactly one rand() draw, even for NaN input, and must
    return NaN rather than raising (previously int(nan) would crash)."""
    stream = _Mcg16807RandStream(0)
    state_before = stream._state
    result = stream.stochastic_round(float("nan"))
    assert math.isnan(result)
    assert stream._state != state_before


def test_next_update_skips_reinitialize_when_bound_sites_already_present() -> None:
    """Regression test for the removed erroneous _maybe_prewarm_initialized_rng
    call (this session's fix). MATLAB's evolveState() (ReplicationInitiation.m:
    506-529) never calls initializeStateBasedOnFinalConditions() -- only the
    separate initializeState() lifecycle method does (ReplicationInitiation.m:
    365-390), which the per-process trace extraction harness that produced
    ReplicationInitiation_100ticks.mat never calls either (only evolveState()
    every tick). A real MATLAB call-by-call RNG ledger (seed=0, ticks 0-4,
    docs/phase_f/probes/repinit_rng_ledger/matlab_rng_ledger_ticks0-4.jsonl)
    proved real tick 0 consumes exactly 26 raw draws; the removed
    _maybe_prewarm_initialized_rng call (fired whenever bound sites were
    already non-zero -- exactly the `elif has_enzyme_pools:` branch below)
    consumed 106 EXTRA draws with no MATLAB counterpart, and its only side
    effect was immediately overwritten by the unconditional
    _sync_internal_state() call anyway. This is a regression test for the bug
    CLASS (an OC-invented lifecycle-method call inside the per-tick
    evolveState()-equivalent path with no MATLAB source counterpart), not
    just this one call site: it asserts the removed helpers/flag no longer
    exist, and that next_update(), when bound sites are already present, never
    invokes _initialize_state_based_on_final_conditions at all."""
    p = KarrReplicationInitiationProcess({"rng_seed": 41})
    assert not hasattr(p, "_maybe_prewarm_initialized_rng")
    assert not hasattr(p, "_prewarm_rng_from_initialize_state")
    assert not hasattr(p, "_rng_prewarmed")

    chrom_state = p.build_default_chromosome_state(replication_state="idle", supercoiled=True)
    global_atp_1mer = int(p.enzyme_global_indexs[p.enzyme_index_dnaa_1mer_atp])
    site_idx = p.r5_index
    complex_bound = SparseTriplet(
        positions=np.asarray([int(p._dnaa_box_positions[site_idx])], dtype=np.int64),
        strands=np.asarray([0], dtype=np.int64),
        values=np.asarray([global_atp_1mer], dtype=np.int64),
        shape=p.chromosome_shape,
    )
    chrom_state["complexBoundSites"] = complex_bound.to_state()

    state = {
        "chromosome": chrom_state,
        "protein": {"counts": {"MG_469_1MER_ATP": 5.0, "MG_469_1MER_ADP": 0.0}},
        "enzymes": {},
        "substrates": {wid: 0.0 for wid in p.substrate_wids},
        "requests": {p.name: {p.atp_wid: 0.0, p.water_wid: 0.0}},
        "substrates_allocated": {p.name: {p.atp_wid: 0.0, p.water_wid: 0.0}},
    }

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "_initialize_state_based_on_final_conditions must not be invoked "
            "by next_update() when bound sites are already present (the "
            "has_enzyme_pools elif branch) -- MATLAB's evolveState() never "
            "calls this method."
        )

    p._initialize_state_based_on_final_conditions = _raise  # type: ignore[method-assign]
    update = p.next_update(1.0, state)
    assert isinstance(update, dict)


def test_inactivate_free_dnaa_atp_fully_dissociates_polymer_when_water_sufficient() -> None:
    """Regression test for the fixed conservation bug in
    _inactivate_free_dnaa_atp (this session's fix). MATLAB's
    inactivateFreeDnaAATP (ReplicationInitiation.m:560-578) initializes
    `nDissociatingPolymers` to the FULL current free polymer-ATP counts and,
    whenever water is sufficient (the common case -- confirmed via the real
    MATLAB RNG ledger showing zero draws consumed here across ticks 0-19),
    unconditionally subtracts that full amount at the end: `this.enzymes(...)
    = this.enzymes(...) - nDissociatingPolymers`, i.e. every free ATP n-mer
    complex fully dissociates into monomers whenever this function runs and
    water suffices. The previous Python port instead computed `removed =
    <original free_enzyme_counts> - <final polymer_counts>`; since
    polymer_counts starts as a literal copy of that same free_enzyme_counts
    slice and is only ever decremented in the (rare) water-scarce branch,
    `removed` was always exactly 0 in the water-sufficient case, silently
    skipping the deduction entirely while still crediting the resulting free
    ADP monomers below -- a real conservation violation with no MATLAB
    counterpart, found via cross-checking a real MATLAB RNG ledger against
    OC's own draw log at tick 13 of the honest 200-tick stateful replay."""
    p = KarrReplicationInitiationProcess({"rng_seed": 43})
    p._free_enzyme_counts = np.zeros(len(p.enzyme_wids), dtype=np.int64)
    p._free_enzyme_counts[p.enzyme_indexs_dnaa_nmer_atp[-1]] = 2  # 2 free 7mer-ATP complexes
    p._free_dnaa_adp = 0
    p._free_dnaa_atp = 0

    substrate_delta: dict[str, int] = {}
    p._inactivate_free_dnaa_atp(dt=1.0, available_water=1_000_000.0, substrate_delta=substrate_delta)

    assert int(p._free_enzyme_counts[p.enzyme_indexs_dnaa_nmer_atp[-1]]) == 0, (
        "free 7mer-ATP pool must be fully dissociated (to 0) when water is abundant, "
        "matching MATLAB's unconditional `enzymes(...) = enzymes(...) - nDissociatingPolymers`"
    )
    assert int(p._free_enzyme_counts[p.enzyme_index_dnaa_1mer_adp]) == 14, (
        "dissociating 2 free 7mer complexes must credit 2*7=14 free DnaA-ADP monomers"
    )
    assert substrate_delta.get(p.water_wid, 0) == -14
    assert substrate_delta.get(p.pi_wid, 0) == 14


def test_chromosome_site_selection_uses_separate_stream_from_process_rng() -> None:
    """Regression test for the fixed RNG-stream conflation bug (this session's
    fix). MATLAB's bindDnaAATP/bindDnaAADP (ReplicationInitiation.m:765-789)
    select actual chromosome binding-site positions via
    this.bindProteinToChromosome(...) -> Chromosome.setSiteProteinBound
    (+state/Chromosome.m:503's `this.randStream.randsample(...)`, where
    `this` there is the CHROMOSOME state object's OWN randStream property --
    a stream instance separate from ReplicationInitiation's own
    `this.randStream`). polymerizeDnaAATP/ADP and releaseDnaAAxP, by
    contrast, call `this.randStream` (ReplicationInitiation's own stream)
    directly. A real MATLAB call-by-call RNG ledger (seed=0, ticks 0-19,
    docs/phase_f/probes/repinit_rng_ledger/matlab_rng_ledger_ticks0-19.jsonl)
    proved self._rng must draw ZERO values for chromosome-level site
    selection to stay in bit-identical lockstep with MATLAB's this.randStream
    (verified exactly matching, value-for-value, across 689 consecutive
    draws). Before this fix, _sample_binding_sites drew from self._rng
    directly, desyncing it from MATLAB's this.randStream by exactly the
    number of site-selection draws consumed. This test asserts
    _sample_binding_sites consumes zero draws from self._rng (a dedicated
    _chromosome_rng stream must exist and be used instead)."""
    p = KarrReplicationInitiationProcess({"rng_seed": 47})
    assert hasattr(p, "_chromosome_rng")
    assert p._chromosome_rng is not p._rng

    candidate_ids = np.arange(10, dtype=np.int64)
    weights = np.ones(10, dtype=np.float64)
    empty = _empty_triplet(p)

    rng_state_before = p._rng._state
    chromosome_rng_state_before = p._chromosome_rng._state

    chosen = p._sample_binding_sites(
        candidate_ids,
        weights,
        5,
        monomer_bound_sites=empty,
        complex_bound_sites=empty,
        binding_complex_global_index=int(p.enzyme_global_indexs[p.enzyme_index_dnaa_1mer_atp]),
    )

    assert chosen.size > 0
    assert p._rng._state == rng_state_before, (
        "_sample_binding_sites must not consume any draws from self._rng "
        "(ReplicationInitiation's own process-private stream) -- it must "
        "draw exclusively from the separate _chromosome_rng stream"
    )
    assert p._chromosome_rng._state != chromosome_rng_state_before
