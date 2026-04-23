"""Integration tests for the hybrid deterministic/stochastic coupled solver.

Validates:
  1. f_met == 1 (forced) over short horizon: hybrid gene end-state is
     within statistical uncertainty of the uncoupled deterministic Vilar
     end-state (averaged over a small ensemble).
  2. f_met == 0 (forced): no synthesis fires, MA/MR/A/R cannot grow,
     gene-copy conservation holds (DA+DAp = DR+DRp = 1).
  3. Default coupling (cglcex-driven) ensemble: end-state R is
     stochastically lower than the uncoupled-gene Vilar deterministic
     end-state (synthesis was throttled).
  4. Single-realisation determinism: same seed -> same trajectory.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from opencell.models.coupled import CoupledMetabolismTranscription
from opencell.models.transcription import TranscriptionModel
from opencell.solvers.hybrid import hybrid_ensemble, hybrid_run


@pytest.fixture(scope="module")
def coupled() -> CoupledMetabolismTranscription:
    return CoupledMetabolismTranscription.build()


def test_hybrid_seed_reproducible(coupled):
    r1 = hybrid_run(coupled, t_end_s=600.0, macro_dt_s=60.0, seed=42)
    r2 = hybrid_run(coupled, t_end_s=600.0, macro_dt_s=60.0, seed=42)
    np.testing.assert_array_equal(r1.y_gene, r2.y_gene)
    np.testing.assert_allclose(r1.y_met, r2.y_met, rtol=0, atol=0)


def test_hybrid_f_met_zero_blocks_synthesis(coupled):
    """No synthesis -> MA/MR/A/R never grow above their IC (all 0)."""
    cb_off = CoupledMetabolismTranscription.build(
        met=coupled.met, gene=coupled.gene, f_met_fn=lambda c, c0: 0.0
    )
    res = hybrid_run(cb_off, t_end_s=3600.0, macro_dt_s=60.0, seed=0)
    gidx = coupled.gene.species_index()
    for s in ("MA", "MR", "A", "R", "C"):
        traj = res.y_gene[:, gidx[s]]
        assert traj.max() == 0.0, f"{s} grew to {traj.max()} despite f_met=0"
    # Gene-copy conservation
    DA = res.y_gene[:, gidx["DA"]]
    DAp = res.y_gene[:, gidx["DAp"]]
    np.testing.assert_array_equal(DA + DAp, np.ones_like(DA))


def test_hybrid_f_met_one_matches_uncoupled_in_mean(coupled):
    """Forced f_met=1 with a small ensemble: ensemble mean of R should
    track the uncoupled deterministic Vilar trajectory order-of-magnitude.

    Loose check (small ensemble + short horizon for CI), looking only
    at end-of-run R: stochastic mean within 50% of deterministic.
    """
    cb_on = CoupledMetabolismTranscription.build(
        met=coupled.met, gene=coupled.gene, f_met_fn=lambda c, c0: 1.0
    )
    t_end = 7200.0  # 2 cellular hours
    runs = hybrid_ensemble(cb_on, t_end_s=t_end, macro_dt_s=60.0,
                           n_realisations=8, base_seed=1)
    gidx = coupled.gene.species_index()
    R_end = np.array([r.y_gene[-1, gidx["R"]] for r in runs])
    R_mean = R_end.mean()

    gene = TranscriptionModel.load()
    sol = solve_ivp(gene.rhs, (0.0, t_end / 3600.0), gene.initial_y,
                    method="LSODA", atol=1e-3, rtol=1e-6, max_step=0.05)
    R_det_end = sol.y[gidx["R"], -1]

    # R can be 0 in early oscillation phase, so use absolute tolerance for the
    # "near zero" case alongside the relative check.
    if R_det_end > 50.0:
        assert R_mean == pytest.approx(R_det_end, rel=0.5), (
            f"hybrid R_mean={R_mean} not within 50% of deterministic R={R_det_end}"
        )
    else:
        assert abs(R_mean - R_det_end) < 100.0, (
            f"hybrid R_mean={R_mean} far from deterministic R={R_det_end}"
        )


def test_hybrid_default_coupling_throttles_synthesis(coupled):
    """Default cglcex coupling over enough horizon to deplete glucose:
    ensemble-mean R must be much smaller than uncoupled deterministic R."""
    t_end = 3 * 3600.0
    runs = hybrid_ensemble(coupled, t_end_s=t_end, macro_dt_s=60.0,
                           n_realisations=2, base_seed=10)
    gidx = coupled.gene.species_index()
    R_end_mean = np.mean([r.y_gene[-1, gidx["R"]] for r in runs])

    gene = TranscriptionModel.load()
    sol = solve_ivp(gene.rhs, (0.0, t_end / 3600.0), gene.initial_y,
                    method="LSODA", atol=1e-3, rtol=1e-6, max_step=0.05)
    R_det_unc = sol.y[gidx["R"], -1]

    # Coupled should be at least 5x smaller (real value at 5h is ~1e-3 vs ~1e3)
    assert R_end_mean < R_det_unc / 5, (
        f"coupled mean R={R_end_mean} not significantly below uncoupled R={R_det_unc}"
    )

    # f_met history should show the throttle
    f_min = min(r.f_met_history.min() for r in runs)
    assert f_min < 0.1, f"f_met never dropped (min={f_min}); coupling not biting"


def test_hybrid_ensemble_shows_intrinsic_noise(coupled):
    """At fixed f_met=1, two runs with different seeds should give
    different gene trajectories (otherwise tau-leap is broken)."""
    cb_on = CoupledMetabolismTranscription.build(
        met=coupled.met, gene=coupled.gene, f_met_fn=lambda c, c0: 1.0
    )
    r1 = hybrid_run(cb_on, t_end_s=3600.0, macro_dt_s=60.0, seed=1)
    r2 = hybrid_run(cb_on, t_end_s=3600.0, macro_dt_s=60.0, seed=2)
    assert not np.allclose(r1.y_gene, r2.y_gene), (
        "two different seeds produced identical trajectories — stochasticity broken"
    )
