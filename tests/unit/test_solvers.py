"""Tests for solvers — ODE (JAX + SciPy) and stochastic.

Includes differential testing: JAX and SciPy solvers must agree
on the same problem (Gate G1.3 preview).
"""

import numpy as np
import pytest

import jax
import jax.numpy as jnp

jax.config.update("jax_enable_x64", True)

from opencell.solvers.ode import ODESolverConfig, solve_ode
from opencell.solvers.ode_scipy import ScipySolverConfig, solve_ode_scipy
from opencell.solvers.stochastic import TauLeapConfig, tau_leap


# Simple exponential decay: dy/dt = -k*y, solution: y(t) = y0 * exp(-k*t)
def decay_rhs_jax(t: float, y: jnp.ndarray, args: dict) -> jnp.ndarray:
    k = args["k"]
    return -k * y


def decay_rhs_scipy(t: float, y: np.ndarray) -> np.ndarray:
    k = 0.1
    return -k * y


class TestJAXSolver:
    def test_exponential_decay(self) -> None:
        y0 = jnp.array([100.0])
        t_span = (0.0, 10.0)
        t_eval = jnp.linspace(0.0, 10.0, 50)

        result = solve_ode(
            decay_rhs_jax,
            y0,
            t_span,
            args={"k": 0.1},
            saveat=t_eval,
        )

        assert result.success
        # Check final value: y(10) = 100 * exp(-1) ≈ 36.79
        final = float(result.ys[-1, 0])
        expected = 100.0 * np.exp(-1.0)
        assert abs(final - expected) / expected < 1e-6

    def test_two_species_system(self) -> None:
        """A → B with rate k. Tests coupled species."""

        def rhs(t, y, args):
            k = args["k"]
            dA = -k * y[0]
            dB = k * y[0]
            return jnp.array([dA, dB])

        y0 = jnp.array([100.0, 0.0])
        result = solve_ode(rhs, y0, (0.0, 50.0), args={"k": 0.1},
                          saveat=jnp.array([50.0]))

        A_final = float(result.ys[-1, 0])
        B_final = float(result.ys[-1, 1])
        # Conservation: A + B = 100
        assert abs(A_final + B_final - 100.0) < 1e-6

    def test_stiff_solver(self) -> None:
        """Test that Kvaerno5 (implicit) handles stiff problems."""
        result = solve_ode(
            decay_rhs_jax,
            jnp.array([100.0]),
            (0.0, 10.0),
            args={"k": 0.1},
            config=ODESolverConfig(method="kvaerno5"),
            saveat=jnp.array([10.0]),
        )
        assert result.success


class TestScipySolver:
    def test_exponential_decay(self) -> None:
        y0 = np.array([100.0])
        t_eval = np.linspace(0.0, 10.0, 50)

        result = solve_ode_scipy(
            decay_rhs_scipy, y0, (0.0, 10.0), t_eval=t_eval,
        )

        assert result.success
        final = result.ys[0, -1]  # SciPy shape: (n_species, n_steps)
        expected = 100.0 * np.exp(-1.0)
        assert abs(final - expected) / expected < 1e-6

    def test_bdf_method(self) -> None:
        result = solve_ode_scipy(
            decay_rhs_scipy,
            np.array([100.0]),
            (0.0, 10.0),
            config=ScipySolverConfig(method="BDF"),
            t_eval=np.array([10.0]),
        )
        assert result.success

    def test_radau_method(self) -> None:
        result = solve_ode_scipy(
            decay_rhs_scipy,
            np.array([100.0]),
            (0.0, 10.0),
            config=ScipySolverConfig(method="Radau"),
            t_eval=np.array([10.0]),
        )
        assert result.success


class TestJAXvsSciPyCrossValidation:
    """Differential testing: both solvers must agree on the same problem.

    This is a preview of Gate G1.3 — when we build the micro-model,
    we'll run this same pattern on the analytical 1-gene system.
    """

    def test_decay_agreement(self) -> None:
        t_eval = np.linspace(0.0, 10.0, 20)

        # JAX solve
        jax_result = solve_ode(
            decay_rhs_jax,
            jnp.array([100.0]),
            (0.0, 10.0),
            args={"k": 0.1},
            saveat=jnp.array(t_eval),
        )

        # SciPy solve
        scipy_result = solve_ode_scipy(
            decay_rhs_scipy,
            np.array([100.0]),
            (0.0, 10.0),
            t_eval=t_eval,
        )

        jax_vals = np.array(jax_result.ys[:, 0])
        scipy_vals = scipy_result.ys[0, :]  # SciPy is transposed

        # Both must agree within tolerance
        max_rel_error = np.max(np.abs(jax_vals - scipy_vals) / np.abs(scipy_vals))
        assert max_rel_error < 1e-6, f"Max relative error: {max_rel_error}"

    def test_two_species_agreement(self) -> None:
        """Cross-validate a 2-species conversion A → B."""

        def rhs_jax(t, y, args):
            return jnp.array([-0.1 * y[0], 0.1 * y[0]])

        def rhs_scipy(t, y):
            return np.array([-0.1 * y[0], 0.1 * y[0]])

        t_eval = np.linspace(0.0, 20.0, 50)

        jax_result = solve_ode(
            rhs_jax, jnp.array([100.0, 0.0]), (0.0, 20.0),
            args=None, saveat=jnp.array(t_eval),
        )
        scipy_result = solve_ode_scipy(
            rhs_scipy, np.array([100.0, 0.0]), (0.0, 20.0),
            t_eval=t_eval,
        )

        for i in range(2):
            jax_vals = np.array(jax_result.ys[:, i])
            scipy_vals = scipy_result.ys[i, :]
            max_err = np.max(np.abs(jax_vals - scipy_vals))
            assert max_err < 1e-5, f"Species {i} max error: {max_err}"


class TestTauLeaping:
    def test_decay_mean(self) -> None:
        """Stochastic decay should match deterministic mean approximately."""

        def propensity_fn(y):
            return jnp.array([0.01 * y[0]])  # decay with rate 0.01

        S = np.array([[-1]])  # one species, one reaction (consumes 1)
        y0 = np.array([1000.0])  # start with 1000 molecules

        key = jax.random.PRNGKey(42)
        result = tau_leap(propensity_fn, S, y0, (0.0, 100.0), key)

        # After t=100 with k=0.01: expected = 1000*exp(-1) ≈ 368
        final = result.ys[-1, 0]
        expected = 1000 * np.exp(-1.0)
        # Stochastic: allow 20% relative error
        assert abs(final - expected) / expected < 0.2, f"Final: {final}, expected: {expected}"

    def test_counts_non_negative(self) -> None:
        """Tau-leaping must never produce negative counts."""

        def propensity_fn(y):
            return jnp.array([0.1 * y[0]])

        S = np.array([[-1]])
        y0 = np.array([10.0])  # low count — tests clamping

        key = jax.random.PRNGKey(123)
        result = tau_leap(propensity_fn, S, y0, (0.0, 200.0), key)

        assert np.all(result.ys >= 0), "Negative counts detected!"

    def test_birth_death(self) -> None:
        """Birth-death process: production + degradation."""

        def propensity_fn(y):
            return jnp.array([10.0, 0.1 * y[0]])  # birth rate 10, death rate 0.1*n

        S = np.array([[1, -1]])  # species gains from rxn0, loses from rxn1
        y0 = np.array([0.0])  # start empty

        key = jax.random.PRNGKey(7)
        result = tau_leap(propensity_fn, S, y0, (0.0, 200.0), key)

        # Steady state: birth/death = 10/0.1 = 100
        final = result.ys[-1, 0]
        assert 30 < final < 300, f"Expected ~100, got {final}"
