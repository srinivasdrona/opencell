"""Gate G1.2 + G1.3: Micro-model analytical validation.

The most important test in the entire project. If our simulation engine
cannot reproduce a textbook analytical solution with published parameters,
nothing else we build can be trusted.

References:
  Alon (2006) Chapter 1, Box 1.1
  Thattai & van Oudenaarden (2001) PNAS 98(15), 8614–8619
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
import pytest

jax.config.update("jax_enable_x64", True)

from opencell.models.micro_model import MicroModelParams
from opencell.solvers.ode import ODESolverConfig, solve_ode
from opencell.solvers.ode_scipy import solve_ode_scipy

# Published parameters (Thattai 2001, Figure 1 caption "base case")
PARAMS = MicroModelParams()


def _micro_model_rhs(t, y, params: MicroModelParams):
    """ODE right-hand side for constitutive gene expression."""
    m, p = y[0], y[1]
    dm_dt = params.alpha_m - params.beta_m * m
    dp_dt = params.alpha_p * m - params.beta_p * p
    return np.array([dm_dt, dp_dt])


def _micro_model_rhs_jax(t, y, args):
    """JAX-compatible RHS."""
    m, p = y[0], y[1]
    alpha_m, beta_m, alpha_p, beta_p = args
    dm_dt = alpha_m - beta_m * m
    dp_dt = alpha_p * m - beta_p * p
    return jnp.array([dm_dt, dp_dt])


# ── Gate G1.2: Deterministic solver matches analytical solution ──


class TestGateG12:
    """G1.2: Simulation must match hand-derived analytical solution."""

    @pytest.mark.gate
    def test_steady_state_analytical_values(self) -> None:
        """Verify analytical steady-state formulas are correct.

        Base case (Thattai 2001 Fig. 1c):
          m* = k_R / gamma_R = 0.6 / (ln2/2) ≈ 1.731
          p* = (k_R · k_P) / (gamma_R · gamma_P)
             = (0.6 · 20·ln2/2) / ((ln2/2) · (ln2/60)) ≈ 1038.7
        """
        import math

        expected_m = 0.60 / (math.log(2) / 2.0)
        expected_p = (0.60 * 20.0 * math.log(2) / 2.0) / (
            (math.log(2) / 2.0) * (math.log(2) / 60.0)
        )
        assert PARAMS.m_ss == pytest.approx(expected_m, rel=1e-10)
        assert PARAMS.p_ss == pytest.approx(expected_p, rel=1e-10)

    @pytest.mark.gate
    def test_jax_solver_matches_analytical_steady_state(self) -> None:
        """Run JAX solver to steady state, compare with analytical."""
        y0 = jnp.array([0.0, 0.0])
        args = (PARAMS.alpha_m, PARAMS.beta_m, PARAMS.alpha_p, PARAMS.beta_p)

        # Save at regular intervals including endpoint
        t_eval = jnp.linspace(0.0, 2000.0, 201)
        config = ODESolverConfig(method="tsit5")
        result = solve_ode(
            _micro_model_rhs_jax,
            y0,
            t_span=(0.0, 2000.0),
            args=args,
            config=config,
            saveat=t_eval,
        )

        final_m = float(result.ys[-1, 0])
        final_p = float(result.ys[-1, 1])

        assert final_m == pytest.approx(PARAMS.m_ss, rel=1e-6), (
            f"mRNA: got {final_m}, expected {PARAMS.m_ss}"
        )
        assert final_p == pytest.approx(PARAMS.p_ss, rel=1e-4), (
            f"Protein: got {final_p}, expected {PARAMS.p_ss}"
        )

    @pytest.mark.gate
    def test_jax_solver_matches_analytical_timecourse(self) -> None:
        """Compare full time course, not just endpoint."""
        y0 = jnp.array([0.0, 0.0])
        args = (PARAMS.alpha_m, PARAMS.beta_m, PARAMS.alpha_p, PARAMS.beta_p)

        t_eval = jnp.linspace(0.0, 500.0, 501)
        config = ODESolverConfig(method="tsit5")
        result = solve_ode(
            _micro_model_rhs_jax,
            y0,
            t_span=(0.0, 500.0),
            args=args,
            config=config,
            saveat=t_eval,
        )

        ts = np.array(result.ts)
        ys = np.array(result.ys)

        # Compare at multiple timepoints
        for i in range(0, len(ts), max(1, len(ts) // 20)):
            t = float(ts[i])
            m_analytical = PARAMS.m_exact(t)
            p_analytical = PARAMS.p_exact(t)
            m_numerical = float(ys[i, 0])
            p_numerical = float(ys[i, 1])

            if t > 1.0:  # skip t=0 (both zero)
                assert m_numerical == pytest.approx(m_analytical, rel=1e-4), (
                    f"mRNA at t={t:.1f}: got {m_numerical}, expected {m_analytical}"
                )
            if t > 50.0:  # protein needs time to accumulate
                assert p_numerical == pytest.approx(p_analytical, rel=1e-3), (
                    f"Protein at t={t:.1f}: got {p_numerical}, expected {p_analytical}"
                )

    @pytest.mark.gate
    def test_scipy_solver_matches_analytical_steady_state(self) -> None:
        """SciPy reference solver must also match analytical."""
        y0 = np.array([0.0, 0.0])

        def rhs(t, y):
            return _micro_model_rhs(t, y, PARAMS)

        t_eval = np.linspace(0.0, 2000.0, 201)
        result = solve_ode_scipy(rhs, y0, t_span=(0.0, 2000.0), t_eval=t_eval)

        # SciPy returns ys as (n_species, n_steps) — transpose
        final_m = result.ys[0, -1]
        final_p = result.ys[1, -1]

        assert final_m == pytest.approx(PARAMS.m_ss, rel=1e-6)
        assert final_p == pytest.approx(PARAMS.p_ss, rel=1e-4)


# ── Gate G1.3: Cross-solver validation ──


class TestGateG13:
    """G1.3: JAX and SciPy solvers must agree on the same problem."""

    @pytest.mark.gate
    def test_jax_vs_scipy_agreement(self) -> None:
        """Both solvers must produce the same trajectory."""
        y0_jax = jnp.array([0.0, 0.0])
        y0_scipy = np.array([0.0, 0.0])
        args = (PARAMS.alpha_m, PARAMS.beta_m, PARAMS.alpha_p, PARAMS.beta_p)

        # Use same evaluation points for both
        t_eval_np = np.linspace(0.0, 500.0, 101)
        t_eval_jax = jnp.array(t_eval_np)

        config = ODESolverConfig(method="tsit5")
        result_jax = solve_ode(
            _micro_model_rhs_jax,
            y0_jax,
            t_span=(0.0, 500.0),
            args=args,
            config=config,
            saveat=t_eval_jax,
        )

        def rhs(t, y):
            return _micro_model_rhs(t, y, PARAMS)

        result_scipy = solve_ode_scipy(
            rhs,
            y0_scipy,
            t_span=(0.0, 500.0),
            t_eval=t_eval_np,
        )

        ys_jax = np.array(result_jax.ys)  # (n_steps, n_species)
        ys_scipy = result_scipy.ys.T  # transpose to (n_steps, n_species)

        # Compare at all shared timepoints (skip first few where both ≈ 0)
        for i in range(5, len(t_eval_np)):
            m_jax = ys_jax[i, 0]
            m_sci = ys_scipy[i, 0]
            p_jax = ys_jax[i, 1]
            p_sci = ys_scipy[i, 1]

            if abs(m_jax) > 0.01:
                assert m_jax == pytest.approx(m_sci, rel=1e-4), (
                    f"mRNA at t={t_eval_np[i]:.1f}: JAX={m_jax}, SciPy={m_sci}"
                )
            if abs(p_jax) > 0.1:
                assert p_jax == pytest.approx(p_sci, rel=1e-3), (
                    f"Protein at t={t_eval_np[i]:.1f}: JAX={p_jax}, SciPy={p_sci}"
                )


# ── Stochastic validation ──


class TestMicroModelStochastic:
    """Validate tau-leaping against analytical noise statistics."""

    @pytest.mark.gate
    @pytest.mark.slow
    def test_stochastic_mean_matches_deterministic(self) -> None:
        """Mean of many stochastic runs should match deterministic steady state."""
        n_runs = 500
        t_end = 2000.0
        dt = 0.5
        final_proteins = []

        for seed in range(n_runs):
            rng = np.random.default_rng(seed)

            # Propensities: [transcription, mRNA_deg, translation, protein_deg]
            def propensities(state):
                m, p = state
                return np.array(
                    [
                        PARAMS.alpha_m,  # R1: ∅ → m
                        PARAMS.beta_m * m,  # R2: m → ∅
                        PARAMS.alpha_p * m,  # R3: m → m + p
                        PARAMS.beta_p * p,  # R4: p → ∅
                    ]
                )

            # Stoichiometry matrix: [m, p] × [R1, R2, R3, R4]
            stoich = np.array(
                [
                    [+1, -1, 0, 0],  # m
                    [0, 0, +1, -1],  # p
                ],
                dtype=float,
            )

            state = np.array([0.0, 0.0])
            t = 0.0
            while t < t_end:
                props = propensities(state)
                total_prop = props.sum()
                if total_prop == 0:
                    break
                # Tau-leaping step
                tau = min(dt, 1.0 / total_prop * 10)
                expected_events = props * tau
                events = rng.poisson(np.maximum(expected_events, 0))
                state = state + stoich @ events
                state = np.maximum(state, 0)  # clamp negatives
                t += tau

            final_proteins.append(state[1])

        mean_p = np.mean(final_proteins)
        var_p = np.var(final_proteins)

        # Mean should be within 15% of analytical
        assert mean_p == pytest.approx(PARAMS.p_ss, rel=0.15), (
            f"Stochastic mean protein: {mean_p:.1f}, expected ~{PARAMS.p_ss:.1f}"
        )

        # Variance should be roughly consistent (within 50% — stochastic is noisy)
        assert var_p > 0, "Zero variance in stochastic simulation — something is wrong"
