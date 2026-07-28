"""Regression tests for the L2.2 FVA performance fix (2026-07-29).

Covers the equivalence/safety properties required before the mechanical
reaction-subset reduction and solver-robustness changes in
``opencell/m1/fva.py`` can replace the full-504-reaction FVA sweep in the
production L2.2 gate:

1. ``reaction_subset`` gives bit-for-bit-equivalent (within solver noise)
   results to the full sweep for every reaction actually read downstream.
2. The runner's subset (union of ``fba_idx_external``/``fba_idx_internal``)
   omits no reaction that ``substrate_delta_range_from_fva`` reads.
3. Repeated/reordered ``fva_range`` calls do not leak state between samples
   (each call constructs and destroys its own GLPK problem instance).
4. ``_solve_checked`` still fails loudly (``RuntimeError``) rather than
   hanging or silently returning wrong values when a solve genuinely cannot
   reach ``GLP_OPT`` within the configured caps.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from opencell.m1 import fva as fva_module
from opencell.m1 import karr_metabolism as km
from opencell.m1.fva import fva_range, substrate_delta_range_from_fva
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

_REPO = Path(__file__).resolve().parents[2]
_GT_SAMPLE_PATH = (
    _REPO
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
_WRITEBACK_FIXTURE_MAT = _REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
_BIG = 1e6


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Missing fixture: {path}")


def _load_sample_bounds() -> tuple[np.ndarray, np.ndarray, float]:
    """Same ground-truth sample (seed 0, tick 1) used by tests/m1/test_fva.py."""
    _require(_GT_SAMPLE_PATH)
    model = km.load_default()
    with h5py.File(_GT_SAMPLE_PATH, "r") as handle:
        bounds = np.asarray(handle["bounds"], dtype=np.float64)
    lb = np.clip(bounds[0], -_BIG, _BIG)
    ub = np.clip(bounds[1], -_BIG, _BIG)
    _v_star, info = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=_BIG,
        lb_override=lb,
        ub_override=ub,
        solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])
    return lb, ub, biomass_value_star


def _fixture() -> KarrWritebackFixture:
    _require(_WRITEBACK_FIXTURE_MAT)
    return KarrWritebackFixture.from_mat(_WRITEBACK_FIXTURE_MAT)


def test_reaction_subset_matches_full_sweep_on_relevant_reactions() -> None:
    """v_min/v_max for every reaction in the subset must match the full-504 sweep."""
    lb, ub, biomass_value_star = _load_sample_bounds()
    model = km.load_default()
    fixture = _fixture()
    reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )

    v_min_full, v_max_full = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb,
        ub,
        biomass_value_star=biomass_value_star,
    )
    v_min_sub, v_max_sub = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb,
        ub,
        biomass_value_star=biomass_value_star,
        reaction_subset=reaction_subset,
    )

    # Every reaction outside the subset must be left as NaN by the subset call
    # (never solved) but IS solved by the default full call.
    outside = np.setdiff1d(np.arange(v_min_full.size), reaction_subset)
    assert np.all(np.isnan(v_min_sub[outside]))
    assert np.all(np.isnan(v_max_sub[outside]))
    assert not np.any(np.isnan(v_min_full[outside]))
    assert not np.any(np.isnan(v_max_full[outside]))

    # Every reaction inside the subset must numerically agree between the two
    # sweeps. Tolerance is far above solver floating-point noise (~1e-9
    # objective-face epsilon, see fva.py's `_FVA_OBJ_FACE_NUMERIC_EPS_REL`)
    # but far below any scientific/feasibility tolerance used downstream.
    tol = 1e-5 * np.maximum(1.0, np.abs(v_min_full[reaction_subset]))
    assert np.all(np.abs(v_min_sub[reaction_subset] - v_min_full[reaction_subset]) <= tol)
    tol = 1e-5 * np.maximum(1.0, np.abs(v_max_full[reaction_subset]))
    assert np.all(np.abs(v_max_sub[reaction_subset] - v_max_full[reaction_subset]) <= tol)


def test_reaction_subset_produces_identical_substrate_deltas() -> None:
    """End-to-end: the reduced subset must yield identical d_min/d_max to the
    full sweep once projected through substrate_delta_range_from_fva -- the
    actual consumer used by the L2.2 gate."""
    lb, ub, biomass_value_star = _load_sample_bounds()
    model = km.load_default()
    fixture = _fixture()
    reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )

    _v_star, info = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=_BIG,
        lb_override=lb,
        ub_override=ub,
        solver="glpk",
    )
    growth_per_s = float(info["biomass_flux_per_s"])

    with h5py.File(_GT_SAMPLE_PATH, "r") as handle:
        pre_sub_raw = np.asarray(handle["pre_sub"], dtype=np.float64)
    pre_sub = pre_sub_raw if pre_sub_raw.shape == (585, 3) else pre_sub_raw.T

    v_min_full, v_max_full = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb,
        ub,
        biomass_value_star=biomass_value_star,
    )
    v_min_sub, v_max_sub = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb,
        ub,
        biomass_value_star=biomass_value_star,
        reaction_subset=reaction_subset,
    )

    d_min_full, d_max_full = substrate_delta_range_from_fva(
        v_min=v_min_full, v_max=v_max_full, fixture=fixture,
        growth_per_s=growth_per_s, step_size_sec=float(fixture.step_size_sec),
        pre_state_585x3=pre_sub,
    )
    d_min_sub, d_max_sub = substrate_delta_range_from_fva(
        v_min=v_min_sub, v_max=v_max_sub, fixture=fixture,
        growth_per_s=growth_per_s, step_size_sec=float(fixture.step_size_sec),
        pre_state_585x3=pre_sub,
    )

    assert np.allclose(d_min_full, d_min_sub, atol=1e-5, rtol=1e-5, equal_nan=True)
    assert np.allclose(d_max_full, d_max_sub, atol=1e-5, rtol=1e-5, equal_nan=True)


def test_runner_subset_omits_no_relevant_reaction() -> None:
    """The union subset used by tests/vivarium/l2_2_design_a_runner.py must
    contain every reaction index substrate_delta_range_from_fva reads."""
    fixture = _fixture()
    reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )
    external = np.asarray(fixture.fba_idx_external, dtype=np.int64)
    internal = np.asarray(fixture.fba_idx_internal, dtype=np.int64)
    assert np.all(np.isin(external, reaction_subset))
    assert np.all(np.isin(internal, reaction_subset))
    # These two index sets are disjoint by construction of the writeback
    # fixture (external exchange vs. internal recycle reactions never
    # overlap); the union is exactly their concatenation with no dedup loss.
    assert np.intersect1d(external, internal).size == 0
    assert reaction_subset.size == external.size + internal.size


def test_fva_range_calls_do_not_leak_state_across_samples() -> None:
    """Two fva_range calls with different objective-face targets must each
    produce results depending only on their own arguments (each call builds
    and tears down its own GLPK problem instance -- no persistent template or
    shared basis object across calls).

    Uses the production reaction_subset (validated safe/fast across 13
    diverse samples in benchmarks/bench_fva_full_pipeline.py) rather than
    arbitrary bound perturbations: randomly perturbing bounds risks
    manufacturing brand-new degenerate vertices unrelated to what this test
    is checking (state leakage), as found empirically when this test
    originally used `rng.uniform` bound jitter and hit an unrelated
    full-504, off-subset pathological column. `epsilon_obj` gives a second,
    genuinely different (wider) but still well-posed LP on the SAME bounds.
    """
    lb, ub, biomass_value_star = _load_sample_bounds()
    model = km.load_default()
    fixture = _fixture()
    reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )
    S = np.asarray(model.S, dtype=np.float64)
    rhs = np.asarray(model.RHS, dtype=np.float64)
    c = np.asarray(model.obj, dtype=np.float64)

    def solve_1():
        return fva_range(
            S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
            reaction_subset=reaction_subset,
        )

    def solve_2():
        return fva_range(
            S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
            epsilon_obj=1e-2, reaction_subset=reaction_subset,
        )

    # Order A: sample1, then sample2.
    v_min_1a, v_max_1a = solve_1()
    v_min_2a, v_max_2a = solve_2()

    # Order B: sample2, then sample1 (reversed order).
    v_min_2b, v_max_2b = solve_2()
    v_min_1b, v_max_1b = solve_1()

    assert np.allclose(v_min_1a, v_min_1b, atol=1e-6, rtol=1e-6, equal_nan=True)
    assert np.allclose(v_max_1a, v_max_1b, atol=1e-6, rtol=1e-6, equal_nan=True)
    assert np.allclose(v_min_2a, v_min_2b, atol=1e-6, rtol=1e-6, equal_nan=True)
    assert np.allclose(v_max_2a, v_max_2b, atol=1e-6, rtol=1e-6, equal_nan=True)


def test_solve_checked_raises_runtime_error_on_non_convergence(monkeypatch) -> None:
    """With the iteration cap forced to (near) zero, a genuine solve must
    fail loudly with RuntimeError, not hang or silently return a wrong
    value."""
    lb, ub, biomass_value_star = _load_sample_bounds()
    model = km.load_default()

    monkeypatch.setattr(fva_module, "_FVA_IT_LIM", 0)

    with pytest.raises(RuntimeError, match="failed"):
        fva_range(
            np.asarray(model.S, dtype=np.float64),
            np.asarray(model.RHS, dtype=np.float64),
            np.asarray(model.obj, dtype=np.float64),
            lb,
            ub,
            biomass_value_star=biomass_value_star,
        )
