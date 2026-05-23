"""Phase B integration tests: dynamic-bounds mode of KarrMetabolismProcess.

Honest scope of these tests (mirrors the implementation):
* Static mode (default) is byte-for-byte unchanged from M0.
* Dynamic mode (opt-in) reads M2/M3 demand from the shared substrates
  store into a private compartmented (585, 3) state, recomputes Karr's
  calcFluxBounds (rules 1-5) every tick, and solves with the new bounds.
* Phase C will add: rule 6, dynamic enzymes from M3, M1 mirroring its
  own production back to the shared store.  None of those are exercised
  here.
"""

from __future__ import annotations

import numpy as np
import pytest

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km
from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine
from opencell.vivarium.karr_metabolism import (
    _CYTOSOL_COMPARTMENT_0,
    _KARR_DEMAND_KEYS,
    KarrMetabolismProcess,
    build_karr_m1_engine,
)


# ----------------------------------------------------------------------
# Regression guard: dynamic_bounds=False is unchanged
# ----------------------------------------------------------------------
def test_static_mode_default_and_unchanged_schema() -> None:
    proc = KarrMetabolismProcess()
    assert proc.dynamic_bounds is False
    schema = proc.ports_schema()
    assert "m1_dynamic_diagnostics" not in schema
    assert set(schema) == {"metabolic_reaction", "substrates"}


def test_static_mode_engine_emits_no_diagnostics_port() -> None:
    eng = build_karr_m1_engine()
    eng.update(2.0)
    ts = eng.emitter.get_timeseries()
    assert "m1_dynamic_diagnostics" not in ts


def test_static_mode_two_tick_flux_unchanged() -> None:
    """Static-mode result is reproducible (no hidden state drift)."""
    eng_a = build_karr_m1_engine()
    eng_b = build_karr_m1_engine()
    eng_a.update(2.0)
    eng_b.update(2.0)
    ts_a = eng_a.emitter.get_timeseries()
    ts_b = eng_b.emitter.get_timeseries()
    assert ts_a["metabolic_reaction"]["growth_per_s"] == ts_b["metabolic_reaction"]["growth_per_s"]


# ----------------------------------------------------------------------
# Purity of compute_bounds (Phase B relies on this every tick)
# ----------------------------------------------------------------------
def test_compute_bounds_does_not_mutate_inputs() -> None:
    dyn = cfb.load_default_dynamics()
    m = km.load_default()
    sub_before = dyn.substrates_snapshot.copy()
    enz_before = dyn.enzymes_snapshot.copy()
    cat_before = m.catalysis.copy()
    eb_before = m.enz_bounds.copy()
    fbab = np.column_stack([m.lb, m.ub]).astype(float)
    fbab_before = fbab.copy()
    _ = cfb.compute_bounds(
        substrates=dyn.substrates_snapshot,
        enzymes=dyn.enzymes_snapshot,
        cell_dry_mass=dyn.cell_dry_mass,
        step_size_sec=dyn.step_size_sec,
        catalysis=m.catalysis,
        enz_bounds=m.enz_bounds,
        fba_reaction_bounds=fbab,
        dyn=dyn,
        apply_protein_bounds=False,
    )
    np.testing.assert_array_equal(dyn.substrates_snapshot, sub_before)
    np.testing.assert_array_equal(dyn.enzymes_snapshot, enz_before)
    np.testing.assert_array_equal(m.catalysis, cat_before)
    np.testing.assert_array_equal(m.enz_bounds, eb_before)
    np.testing.assert_array_equal(fbab, fbab_before)


def test_solve_fba_overrides_do_not_mutate_model() -> None:
    m = km.load_default()
    lb_before = m.lb.copy()
    ub_before = m.ub.copy()
    lb_o = m.lb.copy()
    ub_o = m.ub.copy()
    lb_o[0] = -42.0
    ub_o[0] = 42.0
    _v, _info = km.solve_fba(m, lb_override=lb_o, ub_override=ub_o)
    np.testing.assert_array_equal(m.lb, lb_before)
    np.testing.assert_array_equal(m.ub, ub_before)


# ----------------------------------------------------------------------
# Dynamic mode: schema & first-tick parity with MATLAB oracle
# ----------------------------------------------------------------------
def test_dynamic_mode_schema_includes_diagnostics() -> None:
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    assert proc.dynamic_bounds is True
    schema = proc.ports_schema()
    assert "m1_dynamic_diagnostics" in schema
    diag = schema["m1_dynamic_diagnostics"]
    assert "growth_per_s" in diag
    # All NTPs and 20 standard AAs that exist in Karr's ID space appear.
    for key in _KARR_DEMAND_KEYS:
        assert f"cyt_{key}" in diag


def test_dynamic_mode_initial_internal_state_matches_snapshot() -> None:
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    dyn = cfb.load_default_dynamics()
    np.testing.assert_array_equal(proc._sub_state, dyn.substrates_snapshot)
    np.testing.assert_array_equal(proc._enz_state, dyn.enzymes_snapshot)


def test_dynamic_mode_first_tick_bounds_match_matlab_oracle() -> None:
    """At t=0, with snapshot state and no demand drained yet, the bounds
    that the chassis derives must equal MATLAB's bounds_dynamic_no_protein.
    This is the only way Phase B can be trusted: the in-process bound
    derivation is the same one Phase A validated bit-for-bit."""
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    dyn = proc._dyn
    fbab = proc._fba_reaction_bounds
    bounds = cfb.compute_bounds(
        substrates=proc._sub_state,
        enzymes=proc._enz_state,
        cell_dry_mass=dyn.cell_dry_mass,
        step_size_sec=dyn.step_size_sec,
        catalysis=proc.model.catalysis,
        enz_bounds=proc.model.enz_bounds,
        fba_reaction_bounds=fbab,
        dyn=dyn,
        apply_protein_bounds=False,
    )
    np.testing.assert_allclose(
        bounds,
        dyn.bounds_dynamic_no_protein_oracle,
        atol=0,
        rtol=0,
    )


# ----------------------------------------------------------------------
# Demand coupling: shared-store deltas drain internal cytosol pools
# ----------------------------------------------------------------------
def test_dynamic_mode_drains_cytosol_from_shared_store_delta() -> None:
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    proc.ports_schema()  # initialise prev_shared on first tick path

    atp_idx = proc._sub_id_to_idx["ATP"]
    atp0 = float(proc._sub_state[atp_idx, _CYTOSOL_COMPARTMENT_0])

    # Shared store appearance: M2 has accumulated -100 ATP demand since
    # init.  Initial shared default was 1.0 across the board.
    fake_shared = {sid: 1.0 for sid in proc._sub_ids}
    fake_shared["ATP"] = 1.0 - 100.0

    out = proc.next_update(
        timestep=1.0,
        states={"substrates": fake_shared, "metabolic_reaction": {}},
    )
    atp_after = float(proc._sub_state[atp_idx, _CYTOSOL_COMPARTMENT_0])
    assert atp_after == pytest.approx(atp0 - 100.0, abs=1e-9)
    assert out["m1_dynamic_diagnostics"]["cyt_ATP"] == pytest.approx(atp_after)


def test_dynamic_mode_clamps_cytosol_at_zero() -> None:
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    atp_idx = proc._sub_id_to_idx["ATP"]
    atp0 = float(proc._sub_state[atp_idx, _CYTOSOL_COMPARTMENT_0])

    fake_shared = {sid: 1.0 for sid in proc._sub_ids}
    # Drain twice the initial pool: should clamp at 0.
    fake_shared["ATP"] = 1.0 - 10 * atp0

    proc.next_update(
        timestep=1.0,
        states={"substrates": fake_shared, "metabolic_reaction": {}},
    )
    assert proc._sub_state[atp_idx, _CYTOSOL_COMPARTMENT_0] == 0.0


def test_dynamic_mode_isolated_from_shared_store_for_non_demand_keys() -> None:
    """Mutations to substrates that are NOT NTPs/AAs must not touch M1's
    internal compartmented state.  This guards against accidental Phase C
    over-reach."""
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    other_id = next(s for s in proc._sub_ids if s not in _KARR_DEMAND_KEYS)
    idx = proc._sub_id_to_idx[other_id]
    before = proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0]

    fake_shared = {sid: 1.0 for sid in proc._sub_ids}
    fake_shared[other_id] = 1.0 - 5e6  # huge fake delta

    proc.next_update(
        timestep=1.0,
        states={"substrates": fake_shared, "metabolic_reaction": {}},
    )
    assert proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0] == before


# ----------------------------------------------------------------------
# End-to-end: M1+M2+M3 with dynamic bounds for 60 simulated seconds
# ----------------------------------------------------------------------
def test_dynamic_mode_end_to_end_60s_growth_positive() -> None:
    eng = build_karr_m1_m2_m3_engine(dynamic_bounds=True)
    eng.update(60.0)
    ts = eng.emitter.get_timeseries()
    assert "m1_dynamic_diagnostics" in ts
    growth = np.asarray(ts["m1_dynamic_diagnostics"]["growth_per_s"])
    assert growth.size >= 60
    assert np.all(np.isfinite(growth))
    # Skip the initial-state emit at t=0 (default 0.0 from initial_state);
    # all post-tick values must be > 0 in this Phase B run (Phase B does
    # not yet model nutrient exhaustion that could drive growth to zero).
    assert np.all(growth[1:] > 0.0)


def test_dynamic_mode_end_to_end_atp_drains_under_m2_demand() -> None:
    """Over 30 s the cytosol ATP tracked by M1 must monotonically
    decrease as M2 transcription writes negative ATP deltas.  This is
    the demand-coupling ground truth: M1 sees M2's draw."""
    eng = build_karr_m1_m2_m3_engine(dynamic_bounds=True)
    eng.update(30.0)
    ts = eng.emitter.get_timeseries()
    cyt_atp = np.asarray(ts["m1_dynamic_diagnostics"]["cyt_ATP"])
    # First emitted value is the t=0 default (0.0 from initial_state) which
    # we ignore; from the first M1 tick onwards values are real.
    real = cyt_atp[1:]
    assert real.size >= 29
    # Strictly non-increasing within numerical tolerance.
    diffs = np.diff(real)
    assert np.all(diffs <= 1e-6), (
        f"cyt_ATP not non-increasing under M2 demand: max diff {diffs.max()}"
    )
    # And at least some draw happened.
    assert real[-1] < real[0]

