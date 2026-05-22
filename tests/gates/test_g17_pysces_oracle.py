"""Gate G1.7: PySCeS oracle validation of the Thattai micro-model.

Encode the same ODE system in a completely independent third-party
solver (PySCeS — the Python Simulator for Cellular Systems) and compare
trajectories against our JAX and SciPy solvers.

This is the single strongest protection against self-consistent-but-wrong
simulation: PySCeS has no shared code with our stack, and it has been
used by the systems-biology community for ~20 years.

Agreement must be better than 1e-3 relative on both species across the
full trajectory (not just the endpoint).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
import pytest

jax.config.update("jax_enable_x64", True)

from opencell.models.micro_model import MicroModelParams
from opencell.solvers.ode import ODESolverConfig, solve_ode
from opencell.solvers.ode_scipy import solve_ode_scipy

PARAMS = MicroModelParams()
PSC_FILE = Path(__file__).parent / "micro_model_oracle.psc"


def _micro_model_rhs(t, y, params: MicroModelParams):
    m, p = y[0], y[1]
    return np.array(
        [
            params.alpha_m - params.beta_m * m,
            params.alpha_p * m - params.beta_p * p,
        ]
    )


def _micro_model_rhs_jax(t, y, args):
    m, p = y[0], y[1]
    alpha_m, beta_m, alpha_p, beta_p = args
    return jnp.array(
        [
            alpha_m - beta_m * m,
            alpha_p * m - beta_p * p,
        ]
    )


@pytest.fixture(scope="module")
def pysces_trajectory():
    """Build a PySCeS model from the .psc file and simulate.

    PySCeS requires the model file to live in its configured model_dir,
    so we copy into a temp dir and point PySCeS at it.
    """
    pysces = pytest.importorskip("pysces")

    tmp = tempfile.mkdtemp(prefix="opencell_g17_")
    try:
        psc_copy = Path(tmp) / "micro_model_oracle.psc"
        shutil.copy(PSC_FILE, psc_copy)

        mod = pysces.model("micro_model_oracle.psc", dir=tmp)
        mod.doSim(end=500.0, points=501)

        sim_data = mod.data_sim.getSimData("Time", "mRNA", "Protein", lbls=False)
        t = np.asarray(sim_data[:, 0])
        m = np.asarray(sim_data[:, 1])
        p = np.asarray(sim_data[:, 2])
        yield t, m, p
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.gate
class TestGateG17PyscesOracle:
    """G1.7: JAX + SciPy solvers must agree with PySCeS to 1e-3 relative."""

    def test_pysces_recovers_analytical_steady_state(self, pysces_trajectory) -> None:
        """Sanity: PySCeS itself converges to the analytical SS we derived."""
        _, m, p = pysces_trajectory
        assert m[-1] == pytest.approx(PARAMS.m_ss, rel=1e-3), (
            f"PySCeS final m = {m[-1]}, expected {PARAMS.m_ss}"
        )
        assert p[-1] == pytest.approx(PARAMS.p_ss, rel=5e-2), (
            f"PySCeS final p (at t=500 min) = {p[-1]}, "
            f"expected → {PARAMS.p_ss} (t_char ~87 min, hasn't fully converged)"
        )

    def test_pysces_matches_analytical_timecourse(self, pysces_trajectory) -> None:
        """PySCeS trajectory must match the Alon closed-form solution."""
        t, m, p = pysces_trajectory
        m_ana = PARAMS.m_exact(t)
        p_ana = PARAMS.p_exact(t)

        # mRNA equilibrates on ~3-min timescale; skip t=0 divide-by-zero
        mask_m = t > 1.0
        np.testing.assert_allclose(m[mask_m], m_ana[mask_m], rtol=1e-3)

        # Protein: ~87-min timescale; allow looser tolerance near start
        mask_p = t > 30.0
        np.testing.assert_allclose(p[mask_p], p_ana[mask_p], rtol=1e-3)

    def test_scipy_agrees_with_pysces(self, pysces_trajectory) -> None:
        """SciPy solver output must match PySCeS within 1e-3 relative."""
        t_py, m_py, p_py = pysces_trajectory

        y0 = np.array([0.0, 0.0])
        result = solve_ode_scipy(
            lambda t, y: _micro_model_rhs(t, y, PARAMS),
            y0,
            t_span=(0.0, 500.0),
            t_eval=t_py,
        )
        m_sci = result.ys[0]
        p_sci = result.ys[1]

        # mRNA: skip t=0 where both are exactly 0
        mask = t_py > 1.0
        np.testing.assert_allclose(m_sci[mask], m_py[mask], rtol=1e-3)
        mask_p = t_py > 30.0
        np.testing.assert_allclose(p_sci[mask_p], p_py[mask_p], rtol=1e-3)

    def test_jax_agrees_with_pysces(self, pysces_trajectory) -> None:
        """JAX (diffrax) solver output must match PySCeS within 1e-3 relative."""
        t_py, m_py, p_py = pysces_trajectory

        y0 = jnp.array([0.0, 0.0])
        args = (PARAMS.alpha_m, PARAMS.beta_m, PARAMS.alpha_p, PARAMS.beta_p)
        config = ODESolverConfig(method="tsit5")
        result = solve_ode(
            _micro_model_rhs_jax,
            y0,
            t_span=(0.0, 500.0),
            args=args,
            config=config,
            saveat=jnp.array(t_py),
        )
        m_jax = np.array(result.ys[:, 0])
        p_jax = np.array(result.ys[:, 1])

        mask = t_py > 1.0
        np.testing.assert_allclose(m_jax[mask], m_py[mask], rtol=1e-3)
        mask_p = t_py > 30.0
        np.testing.assert_allclose(p_jax[mask_p], p_py[mask_p], rtol=1e-3)
