"""Tests for the multi-level diff tool (Phase 4 / A5)."""

from __future__ import annotations

import numpy as np

from opencell.diff import DiffSpec, run_diff


def _synthetic_traj(*, cglcex_final=0.05, f_met_final=0.03, ma_final=2, n_steps=50, scale=1.0):
    times = np.linspace(0, 8 * 3600, n_steps)
    cglcex = np.linspace(2.0, cglcex_final, n_steps) * scale
    f_met = np.linspace(1.0, f_met_final, n_steps) * scale
    ma = np.round(np.linspace(0, ma_final, n_steps))
    return {
        "time": times,
        "metabolites": {"cglcex": cglcex},
        "signal": {"f_met": f_met},
        "gene_state": {"MA": ma},
    }


def _spec():
    return DiffSpec(
        engine_a_name="hybrid_run",
        engine_b_name="vivarium",
        comparable_variables={
            ("metabolites", "cglcex"): {"abs": 0.2, "rel": 0.05, "kind": "concentration"},
            ("signal", "f_met"): {"abs": 0.05, "rel": 0.10, "kind": "signal"},
            ("gene_state", "MA"): {"abs": 5, "rel": 0.5, "kind": "count"},
        },
    )


def test_identical_trajectories_pass() -> None:
    a = _synthetic_traj()
    b = _synthetic_traj()
    rep = run_diff(a, b, spec=_spec())
    assert rep.passed, rep.summary()


def test_within_tolerance_passes() -> None:
    a = _synthetic_traj(cglcex_final=0.05)
    b = _synthetic_traj(cglcex_final=0.06)  # diff 0.01 mM, within 0.2 abs tol
    rep = run_diff(a, b, spec=_spec())
    assert rep.passed


def test_outside_tolerance_fails_level3() -> None:
    a = _synthetic_traj(cglcex_final=0.05)
    # cglcex shifted scale → max abs diff > 0.2 mM trajectory tolerance.
    b = _synthetic_traj(cglcex_final=0.05, scale=1.5)
    rep = run_diff(a, b, spec=_spec())
    assert not rep.passed
    fails = [f for f in rep.level3_findings if f.severity == "fail"]
    assert len(fails) >= 1


def test_invariants_catch_negative_concentration() -> None:
    a = _synthetic_traj()
    b = _synthetic_traj()
    b["metabolites"]["cglcex"] = b["metabolites"]["cglcex"].copy()
    b["metabolites"]["cglcex"][10] = -0.5
    rep = run_diff(a, b, spec=_spec())
    assert not rep.passed
    assert rep.level2_b_invariants is not None
    assert rep.level2_b_invariants.violation_count >= 1


def test_invariants_catch_count_fractional() -> None:
    a = _synthetic_traj()
    b = _synthetic_traj()
    b["gene_state"]["MA"] = b["gene_state"]["MA"].copy()
    b["gene_state"]["MA"][20] = 2.5  # integer-valued count corrupted
    rep = run_diff(a, b, spec=_spec())
    assert rep.level2_b_invariants is not None
    assert rep.level2_b_invariants.violation_count >= 1


def test_structural_required_paths() -> None:
    a = _synthetic_traj()
    b = _synthetic_traj()
    del b["signal"]
    spec = _spec()
    spec.structural_required_paths = [("signal", "f_met")]
    rep = run_diff(a, b, spec=spec)
    fails = [f for f in rep.level1_findings if f.severity == "fail"]
    assert any("missing" in f.message for f in fails)


def test_phenotype_diff_within_loose_tol() -> None:
    a = _synthetic_traj(cglcex_final=0.05, f_met_final=0.03)
    b = _synthetic_traj(cglcex_final=0.07, f_met_final=0.035)
    rep = run_diff(a, b, spec=_spec(), phenotype_abs_tol=1e-3, phenotype_rel_tol=0.6)
    p_fails = [f for f in rep.level4_findings if f.severity == "fail"]
    assert len(p_fails) == 0, [f.message for f in p_fails]


def test_summary_renders_for_pass_and_fail() -> None:
    a = _synthetic_traj()
    b = _synthetic_traj(cglcex_final=0.05)
    rep_pass = run_diff(a, b, spec=_spec())
    assert "PASS" in rep_pass.summary()
    b_bad = _synthetic_traj(cglcex_final=0.05, scale=2.0)
    rep_fail = run_diff(a, b_bad, spec=_spec())
    assert "FAIL" in rep_fail.summary()


def test_real_engines_produce_consistent_diff() -> None:
    """Integration test: run hybrid_run + vivarium engine briefly and
    verify the diff tool correctly surfaces the known semantic
    differences from A6 (f_met-lag and LSODA-restart drift).

    This test does NOT pass — it asserts that the tool catches the
    known engine-compare deviations. If a future change makes both
    engines agree (e.g. eliminating the f_met-lag), this test should
    be updated to assert PASS instead of FAIL.
    """
    from opencell.models.coupled import (
        CoupledMetabolismTranscription,
    )
    from opencell.solvers.hybrid import hybrid_run
    from opencell.vivarium import build_coupled_engine

    coupled = CoupledMetabolismTranscription.build(signal="uptake_flux")
    rng = np.random.default_rng(99)
    eng = build_coupled_engine(coupled=coupled, macro_dt_s=60.0, rng=rng)
    eng.update(600.0)
    viv = eng.emitter.get_timeseries()

    rng2 = np.random.default_rng(99)
    hyb = hybrid_run(coupled, t_end_s=600.0, macro_dt_s=60.0, rng=rng2)

    midx = coupled.met.species_index()
    gidx = coupled.gene.species_index()
    hyb_traj = {
        "time": list(hyb.ts),
        "metabolites": {"cglcex": hyb.y_met[:, midx["cglcex"]]},
        "signal": {"f_met": hyb.f_met_history},
        "gene_state": {"MA": hyb.y_gene[:, gidx["MA"]]},
    }
    spec = DiffSpec(
        engine_a_name="hybrid_run",
        engine_b_name="vivarium",
        comparable_variables={
            ("metabolites", "cglcex"): {"abs": 0.2, "rel": 0.10, "kind": "concentration"},
            ("signal", "f_met"): {"abs": 0.1, "rel": 0.20, "kind": "signal"},
            ("gene_state", "MA"): {"abs": 10, "rel": 1.0, "kind": "count"},
        },
        scalar_phenotypes=["cglcex_final", "f_met_final", "f_met_min", "gene_final_MA"],
    )
    rep = run_diff(hyb_traj, viv, spec=spec)
    # We EXPECT this to fail at Level 3 on f_met (the f_met-lag rule)
    # and / or Level 4 on gene_final_MA (different RNG paths from
    # different f_met trajectories). The test asserts the tool surfaces
    # the documented disagreement, not that it suppresses it.
    assert not rep.passed
    l3_fails = [f for f in rep.level3_findings if f.severity == "fail"]
    l3_paths = {tuple(f.detail.get("path", [])) for f in l3_fails}
    assert ("signal", "f_met") in l3_paths, (
        "diff tool should report f_met L_inf disagreement (A6 §2.3 lag rule)"
    )
    # And invariants must pass for both engines individually.
    assert rep.level2_a_invariants is not None and rep.level2_a_invariants.passed
    assert rep.level2_b_invariants is not None and rep.level2_b_invariants.passed
