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
    # objective-face epsilon, see fva.py's `_FVA_OBJ_FACE_NUMERIC_EPS_ABS`)
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
        v_min=v_min_full,
        v_max=v_max_full,
        fixture=fixture,
        growth_per_s=growth_per_s,
        step_size_sec=float(fixture.step_size_sec),
        pre_state_585x3=pre_sub,
    )
    d_min_sub, d_max_sub = substrate_delta_range_from_fva(
        v_min=v_min_sub,
        v_max=v_max_sub,
        fixture=fixture,
        growth_per_s=growth_per_s,
        step_size_sec=float(fixture.step_size_sec),
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
            S,
            rhs,
            c,
            lb,
            ub,
            biomass_value_star=biomass_value_star,
            reaction_subset=reaction_subset,
        )

    def solve_2():
        return fva_range(
            S,
            rhs,
            c,
            lb,
            ub,
            biomass_value_star=biomass_value_star,
            epsilon_obj=1e-2,
            reaction_subset=reaction_subset,
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


class _FakeParm:
    """Minimal stand-in for a `glp_smcp()` struct: just an attribute bag."""


class _FakeParm2:
    tol_bnd = 1e-6


class _FakeGlp:
    """Duck-typed stand-in for the `swiglpk` module, used to deterministically
    exercise `_solve_direction_with_fallback`'s cascade-ordering/skip logic
    (C3) and telemetry (C4) without depending on a real degenerate LP (the
    historically-hard timeout case is non-reproducible on demand -- see
    benchmarks/bench_fva_fallback_cascade_telemetry.py -- so a mocked,
    fully-deterministic unit test is the only reliable way to pin this
    behavior down)."""

    GLP_ON = 1
    GLP_OFF = 0
    GLP_MSG_OFF = 0
    GLP_PT_STD = "STD"
    GLP_PT_PSE = "PSE"
    GLP_MAX = 1
    GLP_PRIMAL = "PRIMAL"

    def __init__(self) -> None:
        self.basis_calls: list[str] = []
        self._it_cnt = 0

    def glp_set_obj_dir(self, lp, direction) -> None:
        pass

    def glp_adv_basis(self, lp, flags) -> None:
        self.basis_calls.append("adv")

    def glp_std_basis(self, lp) -> None:
        self.basis_calls.append("std")

    def glp_smcp(self):
        return _FakeParm()

    def glp_init_smcp(self, parm) -> None:
        pass

    def glp_get_it_cnt(self, lp) -> int:
        return self._it_cnt


def _scripted_attempt_runner(glp_obj: _FakeGlp, script: list):
    """Returns a fake `_run_simplex_attempt(glp, lp, parm)` that yields the
    next `_SimplexAttempt` in `script`, in order, advancing `glp_obj`'s fake
    cumulative iteration counter to match (mirroring real GLPK's cumulative
    `glp_get_it_cnt` semantics)."""
    calls = iter(script)

    def _fake(glp, lp, parm):
        attempt = next(calls)
        glp_obj._it_cnt += attempt.iterations
        return attempt

    return _fake


def test_fallback_cascade_skips_same_basis_retry_after_genuine_timeout(monkeypatch) -> None:
    """C3: a GLP_ETMLIM/GLP_EITLIM (genuine timeout) failure must skip an
    immediately-following same-basis/different-pricing retry and jump
    straight to the next different-basis strategy -- since retrying only the
    pricing rule under a basis that just burned its full time/iteration
    budget risks a second full timeout, whereas a structurally different
    basis is the more likely lever to escape a genuine cycle."""
    fake_strategies = (
        ("adv_pse", "adv", 0),
        ("adv_std", "adv", 1),
        ("std_pse", "std", 0),
        ("std_std", "std", 1),
    )
    monkeypatch.setattr(fva_module, "_FVA_FALLBACK_STRATEGIES", fake_strategies)

    fake_glp = _FakeGlp()
    script = [
        fva_module._SimplexAttempt(
            ok=False, simplex_exit=9, sol_status=1, iterations=1_000_000, wall_time_s=10.0
        ),
        fva_module._SimplexAttempt(
            ok=True, simplex_exit=0, sol_status=5, iterations=10, wall_time_s=0.001
        ),
    ]
    monkeypatch.setattr(
        fva_module, "_run_simplex_attempt", _scripted_attempt_runner(fake_glp, script)
    )

    telemetry = fva_module.new_fva_solver_telemetry()
    fva_module._solve_direction_with_fallback(
        fake_glp,
        lp=None,
        base_parm=_FakeParm2(),
        j=0,
        direction=1,
        label="test",
        telemetry=telemetry,
    )

    # Only 2 attempts made: adv_pse (fails, timeout) then std_pse (succeeds).
    # adv_std must have been SKIPPED entirely (never attempted).
    assert fake_glp.basis_calls == ["adv", "std"]
    assert set(telemetry["strategies"].keys()) == {"adv_pse", "std_pse"}
    assert telemetry["strategies"]["adv_pse"]["failures"] == 1
    assert telemetry["strategies"]["std_pse"]["successes"] == 1
    assert telemetry["total_solves"] == 1
    assert telemetry["solves_needing_fallback"] == 1
    assert telemetry["max_attempts_single_solve"] == 2


def test_fallback_cascade_does_not_skip_after_fast_nofeas(monkeypatch) -> None:
    """C3: a fast GLP_NOFEAS failure (simplex_exit == 0) must NOT trigger the
    timeout skip -- the immediately-following same-basis/different-pricing
    retry is cheap and is exactly the strategy that resolves this failure
    mode (see the SECOND root-cause rationale in fva.py)."""
    fake_strategies = (
        ("adv_pse", "adv", 0),
        ("adv_std", "adv", 1),
        ("std_pse", "std", 0),
    )
    monkeypatch.setattr(fva_module, "_FVA_FALLBACK_STRATEGIES", fake_strategies)

    fake_glp = _FakeGlp()
    script = [
        fva_module._SimplexAttempt(
            ok=False, simplex_exit=0, sol_status=4, iterations=500, wall_time_s=0.01
        ),
        fva_module._SimplexAttempt(
            ok=True, simplex_exit=0, sol_status=5, iterations=20, wall_time_s=0.002
        ),
    ]
    monkeypatch.setattr(
        fva_module, "_run_simplex_attempt", _scripted_attempt_runner(fake_glp, script)
    )

    telemetry = fva_module.new_fva_solver_telemetry()
    fva_module._solve_direction_with_fallback(
        fake_glp,
        lp=None,
        base_parm=_FakeParm2(),
        j=0,
        direction=1,
        label="test",
        telemetry=telemetry,
    )

    # adv_std must NOT be skipped: both adv_pse and adv_std were attempted.
    assert fake_glp.basis_calls == ["adv", "adv"]
    assert set(telemetry["strategies"].keys()) == {"adv_pse", "adv_std"}
    assert telemetry["max_attempts_single_solve"] == 2


def test_fallback_cascade_raises_and_records_telemetry_when_all_strategies_fail(
    monkeypatch,
) -> None:
    """When every strategy fails, `_solve_direction_with_fallback` must still
    raise RuntimeError (never silently return), and telemetry must record
    every attempted (non-skipped) strategy as a failure."""
    fake_strategies = (("adv_pse", "adv", 0), ("std_pse", "std", 0))
    monkeypatch.setattr(fva_module, "_FVA_FALLBACK_STRATEGIES", fake_strategies)

    fake_glp = _FakeGlp()
    script = [
        fva_module._SimplexAttempt(
            ok=False, simplex_exit=0, sol_status=4, iterations=100, wall_time_s=0.01
        ),
        fva_module._SimplexAttempt(
            ok=False, simplex_exit=0, sol_status=4, iterations=100, wall_time_s=0.01
        ),
    ]
    monkeypatch.setattr(
        fva_module, "_run_simplex_attempt", _scripted_attempt_runner(fake_glp, script)
    )

    telemetry = fva_module.new_fva_solver_telemetry()
    with pytest.raises(RuntimeError, match=r"exhausting 2/2 applicable fallback"):
        fva_module._solve_direction_with_fallback(
            fake_glp,
            lp=None,
            base_parm=_FakeParm2(),
            j=0,
            direction=1,
            label="test",
            telemetry=telemetry,
        )
    assert telemetry["strategies"]["adv_pse"]["failures"] == 1
    assert telemetry["strategies"]["std_pse"]["failures"] == 1
    assert telemetry["total_solves"] == 1
    assert telemetry["solves_needing_fallback"] == 1


def test_fva_timeout_exit_codes_are_exactly_eitlim_and_etmlim() -> None:
    """C8: `_FVA_TIMEOUT_EXIT_CODES` must be exactly {GLP_EITLIM, GLP_ETMLIM}
    = {8, 9}, verified against the installed `swiglpk` build's own constants
    -- NOT {7, 9} (an earlier version of this module incorrectly included 7,
    which is GLP_EOBJUL/EOBJLL, "objective function limit reached", an
    unrelated simplex termination condition that never fires in this module
    since no objective-value limit is ever configured)."""
    import swiglpk as glp

    assert glp.GLP_EITLIM == 8
    assert glp.GLP_ETMLIM == 9
    assert glp.GLP_EOBJUL == 7
    expected_timeout_codes = frozenset({glp.GLP_EITLIM, glp.GLP_ETMLIM})
    assert expected_timeout_codes == fva_module._FVA_TIMEOUT_EXIT_CODES
    assert 7 not in fva_module._FVA_TIMEOUT_EXIT_CODES


def test_fallback_cascade_skips_same_basis_retry_after_eitlim_exit_8(monkeypatch) -> None:
    """C8: exit code 8 (GLP_EITLIM, iteration-limit timeout) must trigger the
    SAME same-basis-retry-skip behavior as exit code 9 (GLP_ETMLIM) --
    both are genuine "consumed the entire budget" timeouts."""
    fake_strategies = (
        ("adv_pse", "adv", 0),
        ("adv_std", "adv", 1),
        ("std_pse", "std", 0),
        ("std_std", "std", 1),
    )
    monkeypatch.setattr(fva_module, "_FVA_FALLBACK_STRATEGIES", fake_strategies)

    fake_glp = _FakeGlp()
    script = [
        fva_module._SimplexAttempt(
            ok=False, simplex_exit=8, sol_status=1, iterations=5_000_000, wall_time_s=10.0
        ),
        fva_module._SimplexAttempt(
            ok=True, simplex_exit=0, sol_status=5, iterations=10, wall_time_s=0.001
        ),
    ]
    monkeypatch.setattr(
        fva_module, "_run_simplex_attempt", _scripted_attempt_runner(fake_glp, script)
    )

    telemetry = fva_module.new_fva_solver_telemetry()
    fva_module._solve_direction_with_fallback(
        fake_glp,
        lp=None,
        base_parm=_FakeParm2(),
        j=0,
        direction=1,
        label="test",
        telemetry=telemetry,
    )

    # adv_std must have been SKIPPED (exit=8 is a timeout, same as exit=9).
    assert fake_glp.basis_calls == ["adv", "std"]
    assert set(telemetry["strategies"].keys()) == {"adv_pse", "std_pse"}


def test_fallback_cascade_does_not_skip_after_exit_code_7(monkeypatch) -> None:
    """C8: exit code 7 (GLP_EOBJUL, unrelated to timeouts) must NOT trigger
    the same-basis-retry-skip logic -- it must behave like any other
    non-timeout failure (e.g. GLP_NOFEAS) and attempt the immediately-
    following same-basis/different-pricing entry."""
    fake_strategies = (
        ("adv_pse", "adv", 0),
        ("adv_std", "adv", 1),
        ("std_pse", "std", 0),
    )
    monkeypatch.setattr(fva_module, "_FVA_FALLBACK_STRATEGIES", fake_strategies)

    fake_glp = _FakeGlp()
    script = [
        fva_module._SimplexAttempt(
            ok=False, simplex_exit=7, sol_status=4, iterations=500, wall_time_s=0.01
        ),
        fva_module._SimplexAttempt(
            ok=True, simplex_exit=0, sol_status=5, iterations=20, wall_time_s=0.002
        ),
    ]
    monkeypatch.setattr(
        fva_module, "_run_simplex_attempt", _scripted_attempt_runner(fake_glp, script)
    )

    telemetry = fva_module.new_fva_solver_telemetry()
    fva_module._solve_direction_with_fallback(
        fake_glp,
        lp=None,
        base_parm=_FakeParm2(),
        j=0,
        direction=1,
        label="test",
        telemetry=telemetry,
    )

    # adv_std must NOT be skipped: exit=7 is not a timeout code.
    assert fake_glp.basis_calls == ["adv", "adv"]
    assert set(telemetry["strategies"].keys()) == {"adv_pse", "adv_std"}


def test_new_fva_solver_telemetry_default_shape() -> None:
    telemetry = fva_module.new_fva_solver_telemetry()
    assert telemetry == {
        "total_solves": 0,
        "solves_needing_fallback": 0,
        "max_attempts_single_solve": 0,
        "total_wall_time_s": 0.0,
        "strategies": {},
    }


def test_fva_range_telemetry_matches_real_solve_and_never_changes_result() -> None:
    """Passing `telemetry=` to a real `fva_range` call must (a) populate a
    plausible aggregate record and (b) never change the returned v_min/v_max
    relative to an identical call without telemetry."""
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

    v_min_no_telemetry, v_max_no_telemetry = fva_range(
        S, rhs, c, lb, ub, biomass_value_star=biomass_value_star, reaction_subset=reaction_subset
    )
    telemetry = fva_module.new_fva_solver_telemetry()
    v_min_with_telemetry, v_max_with_telemetry = fva_range(
        S,
        rhs,
        c,
        lb,
        ub,
        biomass_value_star=biomass_value_star,
        reaction_subset=reaction_subset,
        telemetry=telemetry,
    )

    assert np.allclose(v_min_no_telemetry, v_min_with_telemetry, equal_nan=True)
    assert np.allclose(v_max_no_telemetry, v_max_with_telemetry, equal_nan=True)
    # Reactions with lb[j] == ub[j] are pinned algebraically and never reach
    # the LP solver (see the "trivial fast path" docstring on `fva_range`), so
    # the expected solve count excludes them rather than assuming every
    # reaction in `reaction_subset` is solved.
    non_fixed = int(np.count_nonzero(lb[reaction_subset] != ub[reaction_subset]))
    assert telemetry["total_solves"] == 2 * non_fixed
    assert "fva_primary_objective_value" in telemetry
    assert abs(telemetry["fva_primary_objective_value"] - biomass_value_star) < 1e-6
    assert set(telemetry["strategies"].keys()) <= {
        "adv_pse",
        "adv_std",
        "std_pse",
        "std_std",
        "adv_pse_presolve",
    }
    assert "adv_pse" in telemetry["strategies"]


def test_face_mode_fx_converges_and_stays_within_bounds() -> None:
    """C2 spot-check (see benchmarks/bench_fva_fx_vs_db_objective_face_equivalence.py
    and docs/phase_f/l2_2_design_a/evidence/fva_fx_vs_db_objective_face_equivalence_summary.json
    for the full 250-sample pre-registered measurement across ticks
    {0,1,5,9,16}, which is the actual evidence for the equivalence claim):
    on the standard regression fixture sample, exact GLP_FX
    (`_face_mode='fx'`) must converge (no RuntimeError) through the
    identical production LP-construction/fallback-cascade code path used by
    `_face_mode='db'`, and every returned value must lie within [lb, ub].

    This test deliberately does NOT assert tight pointwise v_min/v_max
    agreement between FX and DB: the 250-sample benchmark found that a
    small number of structurally degenerate reactions (near-flat objective
    coupling) can land on a different LP vertex under FX vs DB pivoting
    without any accompanying feasibility-classification (d_min/d_max) flip
    on this measured set (max v-diff ~882.6 on an outlier column at
    seed=43/tick=16, 0/394,875 flips observed -- reported as an observed
    outcome, not a magnitude-safety guarantee; see fva.py's objective-face
    comment for the corrected, honest framing). A fast unit test asserting
    raw closeness would therefore be scientifically wrong to enforce;
    convergence + bound membership is the correct fast regression guard,
    with the full flip-rate proof living in the benchmark artifact instead
    of being re-derived here on every test run.
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

    v_min_fx, v_max_fx = fva_range(
        S,
        rhs,
        c,
        lb,
        ub,
        biomass_value_star=biomass_value_star,
        reaction_subset=reaction_subset,
        _face_mode="fx",
    )

    sub = reaction_subset
    assert np.all(np.isfinite(v_min_fx[sub]))
    assert np.all(np.isfinite(v_max_fx[sub]))
    # A handful of reactions on this fixture have near-zero objective
    # coupling under the exact-equality face (multiple near-optimal
    # vertices), so v_min/v_max can disagree by up to solver-tolerance-level
    # noise (~4e-4 absolute observed) rather than exact LP-optimality
    # noise (~1e-9). 1e-3 is comfortably above that observed noise floor
    # while still catching any gross min>max regression.
    assert np.all(v_min_fx[sub] <= v_max_fx[sub] + 1e-3)
    assert np.all(v_min_fx[sub] >= lb[sub] - 1e-6)
    assert np.all(v_max_fx[sub] <= ub[sub] + 1e-6)


def test_face_mode_rejects_invalid_value() -> None:
    lb, ub, biomass_value_star = _load_sample_bounds()
    model = km.load_default()
    with pytest.raises(ValueError, match="_face_mode"):
        fva_range(
            np.asarray(model.S, dtype=np.float64),
            np.asarray(model.RHS, dtype=np.float64),
            np.asarray(model.obj, dtype=np.float64),
            lb,
            ub,
            biomass_value_star=biomass_value_star,
            _face_mode="bogus",
        )


def test_different_fallback_strategies_mostly_agree_on_identical_lp_feasibility_outcome() -> None:
    """D5: direct evidence for (bounded) cascade answer-invariance, distinct
    from (and not to be conflated with) the FX-vs-DB objective-face-
    equivalence benchmark. FX-vs-DB compares two DIFFERENT LP constructions
    (exact equality face vs windowed face); it says nothing about whether
    DIFFERENT FALLBACK STRATEGIES solving the IDENTICAL LP agree. This test
    forces each of the five distinct `_FVA_FALLBACK_STRATEGIES` entries
    (basis constructor x pricing-rule x presolve combinations) to be the
    ONLY strategy attempted (no fallback), on the IDENTICAL production LP
    construction (`_face_mode='db'`, same
    S/rhs/c/lb/ub/biomass_value_star/reaction_subset), then projects each
    strategy's v_min/v_max through the SAME `substrate_delta_range_from_fva`
    math the L2.2 gate actually uses, and compares the resulting
    per-substrate FEASIBILITY MASK across every pair of strategies that
    converged solo, at TWO tolerances: a tight diagnostic tolerance
    (`_DIAGNOSTIC_TOL = 1e-6`, ~6 orders of magnitude TIGHTER than the real
    gate) and the actual production tolerance
    (`_PRODUCTION_TOL = 2.0`, matching `_METABOLISM_FVA_TOL` in
    tests/vivarium/l2_2_design_a_runner.py).

    CORRECTED FINDING (this is why this test does NOT assert exact mask
    equality at the diagnostic tolerance): on this specific regression
    fixture (the MATLAB ground-truth sample used elsewhere in this file,
    NOT the production N50xM20 oracle grid), at the tight diagnostic
    tolerance ONLY, `adv_pse` (primary) vs `adv_pse_presolve` (last-resort)
    disagree on 2/1755 pairs -- a genuine, reproduced demonstration that LP
    strong duality guarantees only the shared OBJECTIVE VALUE across
    GLP_OPT-terminating strategies, NOT that every individual variable's
    value on a possibly-degenerate face is unique (alternate optima are a
    standard, expected LP phenomenon, not a bug; see fva.py's CASCADE
    ORDERING comment, corrected in this round). This counterexample is
    detectable ONLY because `_DIAGNOSTIC_TOL` is deliberately far tighter
    than the actual gate tolerance, purpose-built to surface genuine
    solver-level v_min/v_max disagreement that the real gate's much wider
    tolerance would otherwise absorb -- it does NOT imply the production
    gate's verdict is at risk. At `_PRODUCTION_TOL` (the tolerance the real
    gate actually uses), this exact sample and strategy pair shows ZERO
    flips, asserted below.

    The systematic, bounded, PRE-REGISTERED benchmark against the REAL
    production oracle-grid data (50 samples across ticks {0,1,5,9,16}, see
    benchmarks/bench_fva_fallback_strategy_answer_invariance.py and
    docs/phase_f/l2_2_design_a/evidence/
    fva_fallback_strategy_answer_invariance_summary.json) also uses the
    production tolerance and found ZERO flips (0/514,215 all-pairs
    comparisons) -- THAT is the actual evidence for the production metric's
    practical (not absolute) cascade invariance, not a blanket mathematical
    guarantee derived from strong duality alone.

    This test locks in both: the bounded diagnostic-tolerance counterexample
    count (useful nuance, no gate impact) and the zero-flip result at the
    real production tolerance on this fixture, as regression guards.

    Not every individual strategy necessarily converges ALONE (without the
    other fallback entries available) within the production iteration/time
    caps on every reaction -- that is precisely why the cascade exists. A
    strategy that fails to reach GLP_OPT solo on this sample (observed for
    e.g. `std_pse` alone on one column, exit=9/ETMLIM within the production
    `it_lim`) is recorded and excluded from the comparison rather than
    failing the test; the assertion requires at least two strategies to
    converge solo and compares only among those that did."""
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

    _require(_GT_SAMPLE_PATH)
    with h5py.File(_GT_SAMPLE_PATH, "r") as handle:
        pre_sub_raw = np.asarray(handle["pre_sub"], dtype=np.float64)
        post_sub_raw = np.asarray(handle["post_sub"], dtype=np.float64)
    pre_sub = pre_sub_raw if pre_sub_raw.shape == (585, 3) else pre_sub_raw.T
    post_sub = post_sub_raw if post_sub_raw.shape == (585, 3) else post_sub_raw.T
    karr_delta = post_sub - pre_sub

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
    # Deliberately ~6 orders of magnitude TIGHTER than the real gate
    # tolerance -- a diagnostic probe for genuine per-column alternate-optima
    # disagreement, NOT a claim about production behavior (see docstring).
    _DIAGNOSTIC_TOL = 1e-6
    _PRODUCTION_TOL = 2.0  # matches _METABOLISM_FVA_TOL in l2_2_design_a_runner.py

    masks_diag: dict[str, np.ndarray] = {}
    masks_prod: dict[str, np.ndarray] = {}
    v_ranges: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    skipped: dict[str, str] = {}
    for strategy in fva_module._FVA_FALLBACK_STRATEGIES:
        original_strategies = fva_module._FVA_FALLBACK_STRATEGIES
        fva_module._FVA_FALLBACK_STRATEGIES = (strategy,)
        try:
            v_min, v_max = fva_range(
                S,
                rhs,
                c,
                lb,
                ub,
                biomass_value_star=biomass_value_star,
                reaction_subset=reaction_subset,
            )
        except RuntimeError as exc:
            # This strategy alone could not certify GLP_OPT for at least one
            # relevant reaction within production caps -- exactly the case
            # the fallback cascade exists to route around. Not a violation
            # of cascade answer-invariance: excluded from comparison, not
            # asserted equal to strategies that did converge.
            skipped[strategy[0]] = str(exc)
            continue
        finally:
            fva_module._FVA_FALLBACK_STRATEGIES = original_strategies
        d_min, d_max = substrate_delta_range_from_fva(
            v_min=v_min,
            v_max=v_max,
            fixture=fixture,
            growth_per_s=growth_per_s,
            step_size_sec=float(fixture.step_size_sec),
            pre_state_585x3=pre_sub,
        )
        finite = np.isfinite(d_min) & np.isfinite(d_max)
        masks_diag[strategy[0]] = (
            finite
            & (karr_delta >= (d_min - _DIAGNOSTIC_TOL))
            & (karr_delta <= (d_max + _DIAGNOSTIC_TOL))
        )
        masks_prod[strategy[0]] = (
            finite
            & (karr_delta >= (d_min - _PRODUCTION_TOL))
            & (karr_delta <= (d_max + _PRODUCTION_TOL))
        )
        v_ranges[strategy[0]] = (v_min[reaction_subset], v_max[reaction_subset])

    assert len(masks_diag) >= 2, (
        f"need >=2 strategies to converge solo for a meaningful comparison; "
        f"converged={list(masks_diag)}, skipped(non-convergent alone)={skipped}"
    )
    names = sorted(masks_diag)

    def _max_pairwise_flips(masks: dict[str, np.ndarray]) -> int:
        max_flips = 0
        for i, name_a in enumerate(names):
            for name_b in names[i + 1 :]:
                n_diff = int(np.count_nonzero(masks[name_a] != masks[name_b]))
                max_flips = max(max_flips, n_diff)
        return max_flips

    assert int(np.count_nonzero(masks_diag[names[0]])) > 0, (
        "sanity: at least one strategy must find some feasible pairs"
    )
    # Diagnostic tolerance: locks in the known counterexample scale on THIS
    # specific fixture (see docstring) -- a small, bounded number of
    # pair-level flips is tolerated and reported at this artificially tight
    # tolerance, but a large/unbounded divergence here would indicate a real
    # regression rather than benign degenerate-face alternate optima.
    # 1755 = 585 species x 3 compartments (the full per-sample pair count).
    max_diag_flips = _max_pairwise_flips(masks_diag)
    assert max_diag_flips <= 10, (
        f"cross-strategy feasibility-mask disagreement ({max_diag_flips} pairs) at the "
        "diagnostic tolerance far exceeds the known-counterexample scale (2/1755) on "
        "this fixture; investigate before trusting the systematic 0-flip production-"
        "tolerance benchmark evidence"
    )
    # Production tolerance: this is the assertion that actually matters for
    # the L2.2 gate -- at the REAL _METABOLISM_FVA_TOL=2.0, this sample must
    # show ZERO cross-strategy flips (confirmed: the diagnostic-tolerance
    # counterexample above is fully absorbed by the much wider production
    # tolerance and has no gate impact on this sample).
    max_prod_flips = _max_pairwise_flips(masks_prod)
    assert max_prod_flips == 0, (
        f"cross-strategy feasibility-mask disagreement ({max_prod_flips} pairs) at the "
        "PRODUCTION tolerance would indicate an actual gate-impacting cascade-answer "
        "divergence, not merely a diagnostic-tolerance nuance -- investigate immediately"
    )

    # Report (not gate on) the largest raw v_min/v_max disagreement across
    # strategies, as a transparency check that it stays within the same
    # order of magnitude already documented for FX-vs-DB (~882.6 max, see
    # fva.py's objective-face comment) rather than blowing up unboundedly --
    # a much larger divergence here would suggest a real bug, not benign
    # degeneracy, even though it wouldn't necessarily flip this sample's mask.
    baseline_name = names[0]
    max_v_diff = max(
        float(np.max(np.abs(v_min_other - v_ranges[baseline_name][0])))
        if name != baseline_name
        else 0.0
        for name, (v_min_other, _v_max_other) in v_ranges.items()
    )
    assert max_v_diff < 1e4, (
        f"cross-strategy v_min divergence ({max_v_diff}) far exceeds the documented "
        "FX-vs-DB degeneracy scale (~882.6); investigate before trusting 0-flip evidence"
    )
