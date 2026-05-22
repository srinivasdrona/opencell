"""Phase C.4 tests: opt-in calibrated pool-replenishment source term.

Honest scope:
* Replenishment is OPT-IN (`enable_pool_replenishment=True`), so the
  pure-drain test suite from Phase B / C.1-C.3 is unchanged.
* Replenishment rate is INJECTED by the composer from the actual
  attached M2/M3 models at synth_scale=1.0; M1 does NOT compute it
  itself (would silently miss `condition` and custom-model overrides).
* Replenishment is NOT LP-derived: standard FBA enforces S@v=0 for
  internal substrates, so net production from the LP itself is always
  zero.  This is a chassis-grade source term to prevent the throttle
  loop from permanently starving when Karr's snapshot has zero pools
  for fast-turnover species (CTP, UTP).  Real LP-derived replenishment
  needs the (1686, 645) compartmented stoichiometry and is Phase D.
* Order within a tick: drain shared deltas -> solve FBA -> replenish
  -> publish m1_pools.  So `m1_pools` published this tick is
  POST-replenish; `growth_per_s` reported this tick is PRE-replenish.
"""

from __future__ import annotations

import pytest

from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import (
    build_karr_m1_m2_m3_engine,
    compute_baseline_demand_per_s,
)
from opencell.vivarium.karr_m1 import (
    _CYTOSOL_COMPARTMENT_0,
    KarrMetabolismProcess,
)


# ----------------------------------------------------------------------
# Composer wires baseline-demand correctly from the attached models
# ----------------------------------------------------------------------
def test_compute_baseline_demand_combines_m2_and_m3() -> None:
    m2 = tx.load_default()
    m3 = tl.load_default()
    bd = compute_baseline_demand_per_s(m2, m3, condition=1)

    # 4 NTPs + 20 standard AAs.
    expected_keys = set(("ATP", "CTP", "GTP", "UTP")) | set(m3.aa_wcm_ids)
    assert set(bd.keys()) == expected_keys

    ntp = tx.ntp_consumption_per_s(tx.calibrated_chassis_model(m2), condition=1)
    aa = tl.aa_consumption_per_s(m3)
    for s in ("ATP", "CTP", "GTP", "UTP"):
        assert bd[s] == pytest.approx(float(ntp[s]), rel=1e-12)
    for a in m3.aa_wcm_ids:
        assert bd[a] == pytest.approx(float(aa[a]), rel=1e-12)


def test_compute_baseline_demand_respects_condition() -> None:
    m2 = tx.load_default()
    m3 = tl.load_default()
    bd0 = compute_baseline_demand_per_s(m2, m3, condition=0)
    bd2 = compute_baseline_demand_per_s(m2, m3, condition=2)
    # Different conditions -> at least one NTP rate differs.  (AAs are
    # condition-independent in the current model.)
    assert any(bd0[s] != bd2[s] for s in ("ATP", "CTP", "GTP", "UTP"))


# ----------------------------------------------------------------------
# Process-level guards
# ----------------------------------------------------------------------
def test_replenishment_requires_dynamic_bounds() -> None:
    with pytest.raises(ValueError, match="dynamic_bounds=True"):
        KarrMetabolismProcess(
            {
                "enable_pool_replenishment": True,
                "baseline_demand_per_s": {"ATP": 1.0},
            }
        )


def test_replenishment_requires_baseline_map() -> None:
    with pytest.raises(ValueError, match="baseline_demand_per_s"):
        KarrMetabolismProcess(
            {
                "dynamic_bounds": True,
                "enable_pool_replenishment": True,
            }
        )


def test_replenishment_rejects_missing_keys() -> None:
    with pytest.raises(ValueError, match="missing demand keys"):
        KarrMetabolismProcess(
            {
                "dynamic_bounds": True,
                "enable_pool_replenishment": True,
                # Only one key -> 23 missing.
                "baseline_demand_per_s": {"ATP": 1.0},
            }
        )


def test_replenishment_rejects_negative_rate() -> None:
    bd = compute_baseline_demand_per_s(
        tx.load_default(),
        tl.load_default(),
        condition=1,
    )
    bd["ATP"] = -1.0
    with pytest.raises(ValueError, match="must be"):
        KarrMetabolismProcess(
            {
                "dynamic_bounds": True,
                "enable_pool_replenishment": True,
                "baseline_demand_per_s": bd,
            }
        )


def test_composer_rejects_replenishment_without_dynamic_bounds() -> None:
    with pytest.raises(ValueError, match="dynamic_bounds=True"):
        build_karr_m1_m2_m3_engine(
            dynamic_bounds=False,
            enable_pool_replenishment=True,
        )


# ----------------------------------------------------------------------
# Replenishment behaviour - end to end
# ----------------------------------------------------------------------
def test_replenishment_off_baseline_unchanged() -> None:
    """Default off keeps the pre-C.4 trajectory intact (covered by the
    existing 543-test baseline; this test just guards the entry point)."""
    eng = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=False,
        enable_pool_replenishment=False,
    )
    eng.update(2.0)
    state = eng.state.get_value()
    assert "m1_pools" in state


def test_replenishment_balances_baseline_drain_to_within_one_tick_offset() -> None:
    """Throttle off (M2/M3 demand at baseline) + replenishment on:
    pool stays at snapshot to within ONE TICK of replenishment offset.

    The offset is a known semantic of the start-up: at tick 0 M1
    replenishes but has not yet observed a drain (``_prev_shared`` is
    initialised to the schema default 1.0 which equals the actual
    initial state, so first-tick delta is zero).  After tick 0 every
    subsequent tick has drain == replenish exactly.  We therefore
    require the long-run drift to be bounded by ``baseline_per_s * dt``
    times a small constant (1.5 to absorb numerical noise), NOT to
    grow proportionally with the number of ticks.
    """
    eng = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=False,
        enable_pool_replenishment=True,
    )
    proc = eng.processes["m1_karr"]
    baseline = proc._baseline_demand_per_s
    snap = {
        sid: float(proc._dyn.substrates_snapshot[idx, _CYTOSOL_COMPARTMENT_0])
        for sid, idx in proc._demand_idx_pairs
    }
    eng.update(5.0)
    after_5 = dict(eng.state.get_value()["m1_pools"])
    eng.update(15.0)  # 20 total
    after_20 = dict(eng.state.get_value()["m1_pools"])

    # Drift after 5 ticks ~= drift after 20 ticks (offset is bounded,
    # not growing).  Guard generously.
    for sid in ("ATP", "GTP"):
        if snap[sid] <= 0.0:
            continue
        drift_5 = after_5[sid] - snap[sid]
        drift_20 = after_20[sid] - snap[sid]
        per_tick = baseline[sid] * 1.0
        # Drift must be bounded by ~1 tick of replenishment.
        assert abs(drift_20) < 1.5 * per_tick, (
            f"{sid}: drift_20={drift_20} > 1.5 * per_tick {per_tick}"
        )
        # And NOT growing proportionally with ticks (4x more ticks
        # should not produce 4x more drift).
        assert abs(drift_20) < 4.0 * abs(drift_5) + 1e-6, (
            f"{sid}: drift growing with ticks - drift_5={drift_5} drift_20={drift_20}"
        )


def test_replenishment_unfreezes_throttled_starvation_after_one_tick_lag() -> None:
    """Phase C.4 raison d'etre: with throttle on and CTP/UTP=0 in the
    snapshot, M2 freezes on tick 0 (f=0).  Replenishment on top
    increases m1_pools[CTP], m1_pools[UTP] by `baseline_demand * dt`
    per tick.  After enough ticks the pools rise above the per-tick
    demand and M2 unfreezes.

    With timestep=1.0, replenish per tick == required per tick exactly,
    so M2 transitions from f=0 to f=1.0 on the FIRST POST-REPLENISH
    tick (one tick lag is intrinsic to vivarium - M1's tick-0 write
    is visible to M2 on tick 1).
    """
    eng = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=True,
        enable_pool_replenishment=True,
    )
    rna_t0 = dict(eng.state.get_value()["rna"]["counts"])

    # Tick 0: M2 reads m1_pools (CTP/UTP = 0 from snapshot) -> f=0 ->
    # RNA only decays.  M1 publishes post-replenish pools at end of tick.
    eng.update(1.0)
    rna_t1 = dict(eng.state.get_value()["rna"]["counts"])

    # Tick 1: M2 reads m1_pools (CTP/UTP = baseline_demand * 1s after
    # tick-0 replenish) -> f=1 -> RNA evolves toward SS.  Should NOT
    # be a pure decay tick.
    eng.update(1.0)
    rna_t2 = dict(eng.state.get_value()["rna"]["counts"])

    # Sample some genes whose SS expression > 0 (so SS != 0 and any
    # non-zero synthesis would create a different trajectory than pure
    # decay).
    sample_genes = [g for g, c in rna_t0.items() if c > 1.0][:20]
    assert len(sample_genes) >= 5

    # Across the sample: tick-0->tick-1 transition was pure decay
    # (f=0).  Tick-1->tick-2 transition includes synthesis (f>0), so
    # the integration step is qualitatively different.  Strict signal:
    # at least ONE gene moved in the OPPOSITE direction across the
    # two transitions (decayed in step 1, grew in step 2, or vice
    # versa).  Pure decay can't do that.
    opposite_direction = 0
    for g in sample_genes:
        d1 = rna_t1[g] - rna_t0[g]
        d2 = rna_t2[g] - rna_t1[g]
        if d1 * d2 < 0:
            opposite_direction += 1
    assert opposite_direction >= 1, (
        "no gene reversed direction across ticks - throttle did not unfreeze"
    )


def test_replenishment_under_no_demand_grows_at_baseline_rate() -> None:
    """With M2/M3 demand-write disabled and replenishment on, the pool
    grows at exactly baseline_demand_per_s * t (no drain on the input
    side, full replenish on the output side)."""
    m1_proc = KarrMetabolismProcess(
        {
            "dynamic_bounds": True,
            "enable_pool_replenishment": True,
            "baseline_demand_per_s": compute_baseline_demand_per_s(
                tx.load_default(),
                tl.load_default(),
                condition=1,
            ),
        }
    )
    atp_idx = m1_proc._sub_id_to_idx["ATP"]
    atp_baseline = m1_proc._baseline_demand_per_s["ATP"]
    atp_t0 = float(m1_proc._sub_state[atp_idx, _CYTOSOL_COMPARTMENT_0])

    # No demand: shared store equals schema default everywhere.
    fake_shared = {sid: 1.0 for sid in m1_proc._sub_ids}
    m1_proc.next_update(
        timestep=1.0,
        states={"substrates": fake_shared, "metabolic_reaction": {}},
    )
    atp_t1 = float(m1_proc._sub_state[atp_idx, _CYTOSOL_COMPARTMENT_0])

    assert atp_t1 == pytest.approx(atp_t0 + atp_baseline, rel=1e-9)


def test_replenishment_emits_post_replenish_pools_in_m1_pools() -> None:
    """Document semantics: m1_pools published this tick reflects the
    POST-replenish state, while growth_per_s reflects PRE-replenish FBA.
    """
    eng = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=False,
        enable_pool_replenishment=True,
    )
    proc = eng.processes["m1_karr"]
    eng.update(1.0)
    pools_after = eng.state.get_value()["m1_pools"]
    # m1_pools must equal _sub_state cytosol after replenish.
    for sid, idx in proc._demand_idx_pairs:
        assert pools_after[sid] == pytest.approx(
            float(proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0]),
            abs=1e-9,
        )
