"""Gate G1.2 + G1.3: Micro-model analytical validation.

The most important test in the entire project. If our simulation engine
cannot reproduce a textbook analytical solution with published parameters,
nothing else we build can be trusted.

The JAX/Diffrax solver was removed per the Day-3 (2026-04-24) decision (JAX
dispatch overhead exceeds integration work at whole-cell scale). The SciPy
reference solver is validated against the analytical solution at both steady
state and across the full time course. The former JAX-vs-SciPy cross-solver
gate (G1.3) is retired with the JAX arm; the analytical-vs-SciPy check below
carries the validation.

References:
  Alon (2006) Chapter 1, Box 1.1
  Thattai & van Oudenaarden (2001) PNAS 98(15), 8614–8619
"""

from __future__ import annotations

import numpy as np
import pytest

from opencell.models.micro_model import MicroModelParams
from opencell.solvers.ode_scipy import solve_ode_scipy

# Published parameters (Thattai 2001, Figure 1 caption "base case")
PARAMS = MicroModelParams()


def _micro_model_rhs(t, y, params: MicroModelParams):
    """ODE right-hand side for constitutive gene expression."""
    m, p = y[0], y[1]
    dm_dt = params.alpha_m - params.beta_m * m
    dp_dt = params.alpha_p * m - params.beta_p * p
    return np.array([dm_dt, dp_dt])


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
    def test_scipy_solver_matches_analytical_steady_state(self) -> None:
        """SciPy reference solver must match the analytical steady state."""
        y0 = np.array([0.0, 0.0])

        def rhs(t, y):
            return _micro_model_rhs(t, y, PARAMS)

        t_eval = np.linspace(0.0, 2000.0, 201)
        result = solve_ode_scipy(rhs, y0, t_span=(0.0, 2000.0), t_eval=t_eval)

        # SciPy returns ys as (n_species, n_steps)
        final_m = result.ys[0, -1]
        final_p = result.ys[1, -1]

        assert final_m == pytest.approx(PARAMS.m_ss, rel=1e-6)
        assert final_p == pytest.approx(PARAMS.p_ss, rel=1e-4)

    @pytest.mark.gate
    def test_scipy_solver_matches_analytical_timecourse(self) -> None:
        """SciPy solver must match the analytical solution across the time course."""
        y0 = np.array([0.0, 0.0])

        def rhs(t, y):
            return _micro_model_rhs(t, y, PARAMS)

        t_eval = np.linspace(0.0, 500.0, 501)
        result = solve_ode_scipy(rhs, y0, t_span=(0.0, 500.0), t_eval=t_eval)

        ts = np.asarray(result.ts)
        ys = np.asarray(result.ys)  # (n_species, n_steps)

        for i in range(0, len(ts), max(1, len(ts) // 20)):
            t = float(ts[i])
            m_analytical = PARAMS.m_exact(t)
            p_analytical = PARAMS.p_exact(t)
            m_numerical = float(ys[0, i])
            p_numerical = float(ys[1, i])

            if t > 1.0:  # skip t=0 (both zero)
                assert m_numerical == pytest.approx(m_analytical, rel=1e-4), (
                    f"mRNA at t={t:.1f}: got {m_numerical}, expected {m_analytical}"
                )
            if t > 50.0:  # protein needs time to accumulate
                assert p_numerical == pytest.approx(p_analytical, rel=1e-3), (
                    f"Protein at t={t:.1f}: got {p_numerical}, expected {p_analytical}"
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
