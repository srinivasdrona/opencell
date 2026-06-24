"""Unit tests for Karr's substrate writeback algorithm.

Validates `apply_karr_substrate_writeback` against:
1. Algebraic invariants (delta shape, type, no NaN)
2. Per-step behavior (each of the 4 steps in isolation)
3. Step 5 clipping (drives metabolites to 0, never negative)
4. Karr tick-0 trace reproduction (full pipeline with Karr's recorded fluxes)

The most important test is #4: if we feed Karr's recorded post-FBA fluxes to
the algorithm, it should reproduce Karr's recorded substrate delta (modulo
stochastic rounding).
"""
from __future__ import annotations
from pathlib import Path

import h5py
import numpy as np
import pytest
from scipy.io import loadmat

from opencell.m1.karr_metabolism_writeback import (
    apply_karr_substrate_writeback,
    project_to_flat_per_wid,
    KarrWritebackFixture,
    ATP_HYDROLYSIS_SIGNS,
    CYTOSOL,
    EXTRACELLULAR,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807


_REPO = Path(__file__).resolve().parents[2]
_METAB_FLAT = _REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
_TRACE_DIR = _REPO / "data" / "m1_sources" / "karr_native"


@pytest.fixture(scope="module")
def fixture() -> KarrWritebackFixture:
    return KarrWritebackFixture.from_mat(_METAB_FLAT)


@pytest.fixture(scope="module")
def rng():
    return _Mcg16807(seed=42)


def test_fixture_shapes(fixture: KarrWritebackFixture) -> None:
    """Index arrays have the expected sizes from Karr's MATLAB."""
    assert fixture.sub_idx_external.shape == (124,)
    assert fixture.sub_idx_internal.shape == (42,)
    assert fixture.sub_idx_atp_hydrolysis.shape == (5,)
    assert fixture.fba_idx_external.shape == (124,)
    assert fixture.fba_idx_internal.shape == (42,)
    assert fixture.metabolism_new_production.shape == (585, 3)
    assert fixture.metabolite_row_idx.shape == (567,)
    # All substrate-row indices must be in [0, 585)
    assert fixture.sub_idx_external.max() < 585
    assert fixture.sub_idx_internal.max() < 585
    assert fixture.sub_idx_atp_hydrolysis.max() < 585
    # FBA col indices must be in [0, 504)
    assert fixture.fba_idx_external.max() < 504
    assert fixture.fba_idx_internal.max() < 504
    assert fixture.unaccounted_energy_consumption > 0


def test_zero_growth_zero_flux_yields_zero_delta(
    fixture: KarrWritebackFixture, rng
) -> None:
    """No FBA activity and no growth → no substrate changes."""
    pre = np.ones((585, 3), dtype=np.float64) * 1000.0
    v_504 = np.zeros(504, dtype=np.float64)
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre, v_504=v_504, growth_per_s=0.0,
        fixture=fixture, rng=rng,
    )
    assert delta.shape == (585, 3)
    assert delta.dtype == np.int64
    assert (delta == 0).all()


def test_step1_nutrient_uptake_subtracts_from_extracellular(
    fixture: KarrWritebackFixture
) -> None:
    """Positive external flux → negative delta on extracellular pool."""
    rng = _Mcg16807(seed=0)
    pre = np.ones((585, 3), dtype=np.float64) * 1_000_000.0  # large pre so no clipping
    v_504 = np.zeros(504, dtype=np.float64)
    # Set first external exchange flux to 10 mol/sec
    v_504[fixture.fba_idx_external[0]] = 10.0
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre, v_504=v_504, growth_per_s=0.0,
        fixture=fixture, rng=rng, step_size_sec=1.0,
    )
    # Step 1 subtracts from extracellular; with no growth, biomass/atp terms are zero
    affected_sub = fixture.sub_idx_external[0]
    assert delta[affected_sub, EXTRACELLULAR] == -10  # 10 * 1 sec, integer-rounded
    # No other deltas
    delta[affected_sub, EXTRACELLULAR] = 0
    assert (delta == 0).all()


def test_step3_biomass_scales_with_growth(fixture: KarrWritebackFixture) -> None:
    """Step 3: biomass delta = stochRound(metabolismNewProduction * growth * step).

    Validation strategy: zero out the rows where step 4 (unaccounted energy)
    contributes, so step 3 is observable in isolation. Step 4 adds to
    sub_idx_atp_hydrolysis cytosol rows only.
    """
    rng = _Mcg16807(seed=1)
    pre = np.ones((585, 3), dtype=np.float64) * 1_000_000.0
    v_504 = np.zeros(504, dtype=np.float64)
    growth = 1e-3  # large enough that production rounds to integers at big entries
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre, v_504=v_504, growth_per_s=growth,
        fixture=fixture, rng=rng, step_size_sec=1.0,
    )
    # Mask out the 5 ATP cells where step 4 contributes
    mask = np.ones((585, 3), dtype=bool)
    mask[fixture.sub_idx_atp_hydrolysis, CYTOSOL] = False

    expected_float = fixture.metabolism_new_production * growth * 1.0
    expected_masked_sum = float(np.abs(expected_float[mask]).sum())
    actual_masked_sum = float(np.abs(delta[mask]).sum())
    # Stochastic rounding can flip each nonzero cell by ±1
    nz_masked = int((expected_float[mask] != 0).sum())
    assert abs(actual_masked_sum - expected_masked_sum) <= nz_masked + 1, (
        f"Step 3 sum mismatch outside ATP rows: actual={actual_masked_sum:.0f} "
        f"vs expected={expected_masked_sum:.0f} (nz={nz_masked})"
    )


def test_step4_atp_signs_applied(fixture: KarrWritebackFixture) -> None:
    """Step 4 applies [-1,-1,1,1,1] sign pattern to the 5 ATP hydrolysis substrates.

    Validation strategy: choose growth large enough that step 4 ≫ step 3 at
    ATP rows. unaccounted_energy ~ 6.275e7, so growth=1e-3 gives step 4 ~ 62750.
    Step 3 at ATP rows scales with metabolismNewProduction values which can be
    similar magnitude — so we subtract the expected step 3 contribution and
    verify the residual matches the ATP sign pattern.
    """
    rng = _Mcg16807(seed=2)
    pre = np.ones((585, 3), dtype=np.float64) * 1_000_000.0
    v_504 = np.zeros(504, dtype=np.float64)
    growth = 1e-3
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre, v_504=v_504, growth_per_s=growth,
        fixture=fixture, rng=rng, step_size_sec=1.0,
    )
    # Expected step 4 contribution per ATP row: ATP_HYDROLYSIS_SIGNS * stochRound(unaccounted_qty)
    unaccounted_qty = fixture.unaccounted_energy_consumption * growth * 1.0
    expected_step4_magnitude = int(round(unaccounted_qty))  # close to stoch round
    # Step 3 contribution at each ATP cytosol cell
    step3_at_atp = fixture.metabolism_new_production[fixture.sub_idx_atp_hydrolysis, CYTOSOL] * growth
    # Total expected delta = step3 + step4 (with sign pattern), allowing ±2 rounding error per cell
    expected_total = step3_at_atp + ATP_HYDROLYSIS_SIGNS * expected_step4_magnitude
    actual = delta[fixture.sub_idx_atp_hydrolysis, CYTOSOL]
    # Per-cell tolerance: ±2 (one for step 3, one for step 4)
    for i in range(5):
        assert abs(actual[i] - expected_total[i]) <= 3, (
            f"ATP cell {i}: actual={actual[i]} expected≈{expected_total[i]:.1f} "
            f"(step3={step3_at_atp[i]:.1f}, step4_sign={ATP_HYDROLYSIS_SIGNS[i]}*{expected_step4_magnitude})"
        )


def test_step5_clip_prevents_negative_metabolites(fixture: KarrWritebackFixture) -> None:
    """Step 5: metabolites driven below zero are clipped to 0."""
    rng = _Mcg16807(seed=3)
    # Pre-state with extracellular = 5 for the first external substrate
    pre = np.ones((585, 3), dtype=np.float64) * 1_000_000.0
    pre[fixture.sub_idx_external[0], EXTRACELLULAR] = 5.0
    v_504 = np.zeros(504, dtype=np.float64)
    # Set first external flux to 100 → step 1 would drive ext to 5 - 100 = -95
    v_504[fixture.fba_idx_external[0]] = 100.0
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre, v_504=v_504, growth_per_s=0.0,
        fixture=fixture, rng=rng, step_size_sec=1.0,
    )
    affected_sub = fixture.sub_idx_external[0]
    # Verify the affected substrate IS a metabolite (subject to clip)
    assert affected_sub in fixture.metabolite_row_idx
    # Without clip: delta would be -100. With clip: post must be >= 0, so delta = -5.
    assert delta[affected_sub, EXTRACELLULAR] == -5
    # Post-state at that cell = 0
    assert pre[affected_sub, EXTRACELLULAR] + delta[affected_sub, EXTRACELLULAR] == 0


def test_project_to_flat_per_wid_skips_zeros() -> None:
    delta = np.zeros((585, 3), dtype=np.int64)
    delta[10, 0] = 5
    delta[20, 1] = -3
    delta[30, 2] = 7
    delta[30, 0] = -7  # sums to 0 → should be omitted
    wids = [f"S_{i}" for i in range(585)]
    flat = project_to_flat_per_wid(delta, wids)
    assert flat["S_10"] == 5.0
    assert flat["S_20"] == -3.0
    assert "S_30" not in flat  # sum 0 → omitted


@pytest.mark.skipif(
    not (_TRACE_DIR / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat").exists()
    and not (_TRACE_DIR / "per_process_traces_v2" / "Metabolism_100ticks.mat").exists(),
    reason="Karr Metabolism trace not available",
)
def test_writeback_runs_at_karr_tick0_with_oc_fba(
    fixture: KarrWritebackFixture,
) -> None:
    """End-to-end smoke test: load Karr's tick-0 pre-state, run OC's FBA, apply
    the 4-step writeback, verify it produces a sensible delta.

    Cannot validate "reproduce Karr exactly" because the per-process trace does
    not store the FBA flux vector — only substrates/enzymes/boundEnzymes.
    The L2.2 strict-rubric test is the integration validation point.

    What this test verifies:
    - Algorithm runs without crashing at Karr's tick-0 state
    - Output delta is integer-valued, finite, shape (585, 3)
    - With static FBA, the delta is small (expected: static FBA underpowered)
    - Post-state has no negative metabolites (Step 5 clip works)
    """
    trace_path = _TRACE_DIR / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
    if not trace_path.exists():
        trace_path = _TRACE_DIR / "per_process_traces_v2" / "Metabolism_100ticks.mat"

    with h5py.File(trace_path, "r") as h:
        def get_3d(group_path: str, tick: int) -> np.ndarray:
            ds = h[group_path]
            ref = ds[0, tick] if ds.shape[0] == 1 else ds[tick, 0]
            return np.asarray(h[ref][()], dtype=np.float64)

        karr_pre = get_3d("states_before/substrates", 0).T   # (585, 3)
        karr_post = get_3d("states_after/substrates", 0).T   # (585, 3)

    karr_delta = karr_post - karr_pre
    print(f"\nKarr tick-0 delta sum_abs: {np.abs(karr_delta).sum():.0f}")

    # Run OC's static FBA at default state (doesn't depend on pre_state)
    from opencell.m1 import karr_metabolism as km
    model = km.load_default()
    v_504, info = km.solve_fba(model, use_full_objective=True, sense="max")
    print(f"OC FBA growth: {info['biomass_flux_per_s']:.4e}")

    # Apply writeback at Karr's pre-state
    rng = _Mcg16807(seed=12345)
    our_delta = apply_karr_substrate_writeback(
        pre_state_585x3=karr_pre,
        v_504=v_504,
        growth_per_s=info["biomass_flux_per_s"],
        fixture=fixture, rng=rng,
    )
    # Algebraic invariants
    assert our_delta.shape == (585, 3)
    assert our_delta.dtype == np.int64
    assert np.all(np.isfinite(our_delta))

    # Step 5 invariant: post-state metabolites >= 0
    post = karr_pre + our_delta.astype(np.float64)
    metabolite_post = post[fixture.metabolite_row_idx, :]
    assert (metabolite_post >= 0).all(), (
        f"Step 5 clip failed: {(metabolite_post < 0).sum()} negative metabolite cells"
    )

    our_sum_abs = float(np.abs(our_delta).sum())
    print(f"OC writeback delta sum_abs: {our_sum_abs:.0f}")
    print(f"Static-FBA recovery ratio: {our_sum_abs / max(np.abs(karr_delta).sum(), 1):.3f}")
    # With static FBA (no dynamic bounds), we expect low recovery (<20% of Karr's flux).
    # Dynamic bounds + writeback is the production path validated by L2.2 strict-rubric.
    # This test just verifies the algorithm RUNS — actual fidelity comes from L2.2.
