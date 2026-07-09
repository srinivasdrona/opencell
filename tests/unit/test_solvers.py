"""Tests for solvers — SciPy ODE and stochastic tau-leaping.

The JAX/Diffrax ODE solver was removed per the Day-3 (2026-04-24) decision that
JAX dispatch overhead exceeds the integration work at whole-cell scale. The
SciPy solver is validated against the analytical exponential-decay solution in
``TestScipySolver``; the former JAX-vs-SciPy cross-validation is retired with
the JAX arm.
"""

import numpy as np

from opencell.solvers.ode_scipy import ScipySolverConfig, solve_ode_scipy
from opencell.solvers.stochastic import tau_leap


def decay_rhs_scipy(t: float, y: np.ndarray) -> np.ndarray:
    k = 0.1
    return -k * y


class TestScipySolver:
    def test_exponential_decay(self) -> None:
        y0 = np.array([100.0])
        t_eval = np.linspace(0.0, 10.0, 50)

        result = solve_ode_scipy(
            decay_rhs_scipy,
            y0,
            (0.0, 10.0),
            t_eval=t_eval,
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


class TestTauLeaping:
    def test_decay_mean(self) -> None:
        """Stochastic decay should match deterministic mean approximately."""

        def propensity_fn(y):
            return np.array([0.01 * y[0]])  # decay with rate 0.01

        S = np.array([[-1]])  # one species, one reaction (consumes 1)
        y0 = np.array([1000.0])  # start with 1000 molecules

        rng = np.random.default_rng(42)
        result = tau_leap(propensity_fn, S, y0, (0.0, 100.0), rng)

        # After t=100 with k=0.01: expected = 1000*exp(-1) ≈ 368
        final = result.ys[-1, 0]
        expected = 1000 * np.exp(-1.0)
        # Stochastic: allow 20% relative error
        assert abs(final - expected) / expected < 0.2, f"Final: {final}, expected: {expected}"

    def test_counts_non_negative(self) -> None:
        """Tau-leaping must never produce negative counts."""

        def propensity_fn(y):
            return np.array([0.1 * y[0]])

        S = np.array([[-1]])
        y0 = np.array([10.0])  # low count — tests clamping

        rng = np.random.default_rng(123)
        result = tau_leap(propensity_fn, S, y0, (0.0, 200.0), rng)

        assert np.all(result.ys >= 0), "Negative counts detected!"

    def test_birth_death(self) -> None:
        """Birth-death process: production + degradation."""

        def propensity_fn(y):
            return np.array([10.0, 0.1 * y[0]])  # birth rate 10, death rate 0.1*n

        S = np.array([[1, -1]])  # species gains from rxn0, loses from rxn1
        y0 = np.array([0.0])  # start empty

        rng = np.random.default_rng(7)
        result = tau_leap(propensity_fn, S, y0, (0.0, 200.0), rng)

        # Steady state: birth/death = 10/0.1 = 100
        final = result.ys[-1, 0]
        assert 30 < final < 300, f"Expected ~100, got {final}"
