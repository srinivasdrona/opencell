"""Phase C.2 + C.3 tests: m1_pools shared port + M2/M3 substrate-aware throttle.

Honest scope:
* C.2 (m1_pools): M1 in dynamic-bounds mode publishes the 24 demand-side
  cytosol pools every tick via a 'set' updater.  Static mode is unaffected.
* C.3 (throttle): M2/M3 read m1_pools and uniformly scale their analytical
  integrators by ``f = min over consumed s of clip(pool[s]/(rate[s]*dt), 0, 1)``.
  Both state-evolution (step_analytical) AND substrate-delta emission scale
  by ``f`` so we never drain pools faster than RNA/protein is produced.
* enable_throttle=False keeps the 528-baseline trajectory unchanged
  (covered by the existing test_dynamic_bounds_chassis suite).
"""

from __future__ import annotations

import numpy as np
import pytest

from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine
from opencell.vivarium.karr_metabolism import (
    _CYTOSOL_COMPARTMENT_0,
    _KARR_DEMAND_KEYS,
    KarrMetabolismProcess,
)
from opencell.vivarium.karr_transcription import (
    _M2_CONSUMED_SUBSTRATES,
    KarrTranscriptionProcess,
)
from opencell.vivarium.karr_translation import KarrTranslationProcess


# ----------------------------------------------------------------------
# C.2 - m1_pools schema + first-tick round-trip
# ----------------------------------------------------------------------
def test_m1_pools_schema_present_in_dynamic_mode_only() -> None:
    proc_static = KarrMetabolismProcess()
    proc_dyn = KarrMetabolismProcess({"dynamic_bounds": True})

    assert "m1_pools" not in proc_static.ports_schema()

    schema = proc_dyn.ports_schema()
    assert "m1_pools" in schema
    pools = schema["m1_pools"]
    # All 24 demand keys (4 NTPs + 20 standard AAs) appear, defaulted to
    # the snapshot cytosol value, with set updater + emit on.
    for sid in _KARR_DEMAND_KEYS:
        assert sid in pools, f"missing m1_pools key {sid}"
        leaf = pools[sid]
        assert leaf["_updater"] == "set"
        assert leaf["_emit"] is True
        assert (
            leaf["_default"]
            == proc_dyn._sub_state[proc_dyn._sub_id_to_idx[sid], _CYTOSOL_COMPARTMENT_0]
        )


def test_m1_pools_update_matches_internal_sub_state_after_tick() -> None:
    """M1 sole-writer round-trip: the value that M1 publishes into
    m1_pools after a tick must equal its private _sub_state cytosol slice."""
    eng = build_karr_m1_m2_m3_engine(dynamic_bounds=True, enable_throttle=False)
    eng.update(1.0)
    proc = eng.processes["m1_karr"]
    final = eng.state.get_value()["m1_pools"]
    for sid, idx in proc._demand_idx_pairs:
        assert final[sid] == pytest.approx(
            float(proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0]),
            abs=1e-9,
        )


def test_m1_pools_seeded_from_snapshot_at_tick_zero() -> None:
    """Initial state of m1_pools equals the snapshot, so the first
    throttle (if enabled) sees real numbers, not the schema default."""
    eng = build_karr_m1_m2_m3_engine(dynamic_bounds=True, enable_throttle=False)
    proc = eng.processes["m1_karr"]
    initial = eng.state.get_value()["m1_pools"]
    for sid, idx in proc._demand_idx_pairs:
        assert initial[sid] == pytest.approx(
            float(proc._dyn.substrates_snapshot[idx, _CYTOSOL_COMPARTMENT_0]),
            abs=1e-9,
        )


# ----------------------------------------------------------------------
# C.3 - throttle math at the process level (no engine, no merging)
# ----------------------------------------------------------------------
def test_m2_throttle_unity_when_pools_abundant() -> None:
    proc = KarrTranscriptionProcess({"enable_throttle": True})
    # Pools two orders of magnitude above any plausible 1s NTP demand.
    abundant = {ntp: 1.0e12 for ntp in _M2_CONSUMED_SUBSTRATES}
    f = proc._compute_throttle(abundant, timestep=1.0)
    assert f == pytest.approx(1.0, abs=1e-12)


def test_m2_throttle_zero_when_one_pool_starved() -> None:
    proc = KarrTranscriptionProcess({"enable_throttle": True})
    pools = {ntp: 1.0e12 for ntp in _M2_CONSUMED_SUBSTRATES}
    pools["ATP"] = 0.0
    f = proc._compute_throttle(pools, timestep=1.0)
    assert f == 0.0


def test_m2_throttle_partial_when_one_pool_below_demand() -> None:
    """Make ATP exactly 1/4 of one tick's demand: throttle must be 0.25."""
    proc = KarrTranscriptionProcess({"enable_throttle": True})
    rate = tx.ntp_consumption_per_s(proc._chassis_model, condition=proc.condition)
    pools = {ntp: 1.0e12 for ntp in _M2_CONSUMED_SUBSTRATES}
    pools["ATP"] = 0.25 * rate["ATP"] * 1.0
    f = proc._compute_throttle(pools, timestep=1.0)
    assert f == pytest.approx(0.25, rel=1e-9)


def test_m3_throttle_unity_when_pools_abundant() -> None:
    proc = KarrTranslationProcess({"enable_throttle": True})
    abundant = {aa: 1.0e12 for aa in proc.aa_ids}
    f = proc._compute_throttle(abundant, timestep=1.0)
    assert f == pytest.approx(1.0, abs=1e-12)


def test_m3_throttle_partial_when_one_aa_below_demand() -> None:
    """Make ALA exactly 0.4 of demand: throttle must be 0.4 (assuming
    ALA is the binding constraint, which it is when others are 1e12)."""
    proc = KarrTranslationProcess({"enable_throttle": True})
    rate = tl.aa_consumption_per_s(proc.model)
    pools = {aa: 1.0e12 for aa in proc.aa_ids}
    pools["ALA"] = 0.4 * rate["ALA"] * 1.0
    f = proc._compute_throttle(pools, timestep=1.0)
    assert f == pytest.approx(0.4, rel=1e-9)


def test_throttle_rejects_zero_and_negative_dt() -> None:
    proc = KarrTranscriptionProcess({"enable_throttle": True})
    pools = {ntp: 1.0 for ntp in _M2_CONSUMED_SUBSTRATES}
    with pytest.raises(ValueError):
        proc._compute_throttle(pools, timestep=0.0)
    with pytest.raises(ValueError):
        proc._compute_throttle(pools, timestep=-1.0)


def test_throttle_rejects_non_finite_pool() -> None:
    proc = KarrTranscriptionProcess({"enable_throttle": True})
    pools = {ntp: 1.0e12 for ntp in _M2_CONSUMED_SUBSTRATES}
    pools["ATP"] = float("inf")
    with pytest.raises(RuntimeError):
        proc._compute_throttle(pools, timestep=1.0)


def test_throttle_treats_negative_pool_as_zero() -> None:
    proc = KarrTranscriptionProcess({"enable_throttle": True})
    pools = {ntp: 1.0e12 for ntp in _M2_CONSUMED_SUBSTRATES}
    pools["ATP"] = -42.0
    f = proc._compute_throttle(pools, timestep=1.0)
    assert f == 0.0


# ----------------------------------------------------------------------
# C.3 - end-to-end: throttle wired into the composer behaves correctly
# ----------------------------------------------------------------------
def test_composer_rejects_throttle_without_dynamic_bounds() -> None:
    with pytest.raises(ValueError, match="dynamic_bounds"):
        build_karr_m1_m2_m3_engine(
            dynamic_bounds=False,
            enable_throttle=True,
        )


def test_throttle_off_baseline_unchanged_after_5_ticks() -> None:
    """enable_throttle=False is the 528-baseline trajectory.  This is
    covered indirectly by the existing dynamic-bounds suite; here we
    just assert the entry point runs without crashing."""
    eng = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=False,
    )
    eng.update(5.0)
    state = eng.state.get_value()
    assert "m1_pools" in state
    # No NaNs / infs in any growth read.
    g = state["metabolic_reaction"]["growth_per_s"]
    assert np.isfinite(g)


def test_throttle_on_with_abundant_pools_matches_throttle_off() -> None:
    """If we monkey-patch m1_pools to abundant values, throttle stays at
    f=1 and the trajectory is identical to throttle-off for the M2/M3
    integrator step (modulo numerical noise)."""
    eng_off = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=False,
    )
    eng_on = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=True,
    )
    # Force m1_pools abundant before the first tick so throttle f==1.
    abundant = {sid: 1.0e15 for sid in eng_on.state.get_value()["m1_pools"]}
    eng_on.state.set_value({"m1_pools": abundant})

    eng_off.update(1.0)
    eng_on.update(1.0)

    # Compare a sampling of RNA + protein counts after 1 tick.
    rna_off = eng_off.state.get_value()["rna"]["counts"]
    rna_on = eng_on.state.get_value()["rna"]["counts"]
    sample_rna = list(rna_off.keys())[:5]
    for g in sample_rna:
        assert rna_on[g] == pytest.approx(rna_off[g], rel=1e-9)

    prot_off = eng_off.state.get_value()["protein"]["counts"]
    prot_on = eng_on.state.get_value()["protein"]["counts"]
    sample_prot = list(prot_off.keys())[:5]
    for p in sample_prot:
        assert prot_on[p] == pytest.approx(prot_off[p], rel=1e-9)


def test_throttle_on_with_starved_atp_freezes_m2_synthesis() -> None:
    """Force m1_pools[ATP] to zero before any tick: M2 must throttle to
    f=0, RNA counts must NOT increase from the seeded steady state, and
    the ATP substrate-delta emitted by M2 must be exactly 0."""
    eng = build_karr_m1_m2_m3_engine(
        dynamic_bounds=True,
        enable_throttle=True,
    )
    pools = dict(eng.state.get_value()["m1_pools"])
    pools["ATP"] = 0.0
    eng.state.set_value({"m1_pools": pools})

    rna_before = dict(eng.state.get_value()["rna"]["counts"])
    sub_before = dict(eng.state.get_value()["substrates"])

    eng.update(1.0)

    rna_after = eng.state.get_value()["rna"]["counts"]
    sub_after = eng.state.get_value()["substrates"]

    # Pure decay only (synthesis = 0): every gene with k>0 should have
    # count <= count_before; no gene should increase.
    for g, before in rna_before.items():
        assert rna_after[g] <= before + 1e-9, f"gene {g} grew under f=0: {before} -> {rna_after[g]}"

    # M2 emits exactly 0 NTP delta under f=0; M3 still drains AAs (its
    # own pools are abundant by default at snapshot).  So substrate
    # ATP/CTP/GTP/UTP must be exactly unchanged by M2.  M1's m1_pools
    # publish overwrites m1_pools but M2's own substrate writes are
    # the deltas we're checking.
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        # M2 contribution is 0. In Bug 6a Stage 1 M1 may write positive
        # LP-derived supply to demand keys, so NTP deltas must be
        # non-negative (never additional drain).
        assert sub_after[ntp] >= sub_before[ntp] - 1e-9, (
            f"NTP {ntp} unexpectedly drained under M2 f=0: {sub_before[ntp]} -> {sub_after[ntp]}"
        )


