"""SciPy reference ODE solver for OpenCell.

This serves two purposes:
1. Escape hatch for stiff systems where JAX/Diffrax struggles
2. Correctness reference for differential testing (Gate G1.3)

Uses scipy.integrate.solve_ivp with BDF method for stiff systems.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

RHSFn = Callable[[float, np.ndarray], np.ndarray]


@dataclass(frozen=True)
class ScipySolverConfig:
    """Configuration for the SciPy ODE solver.

    Attributes:
        method: Solver method ("BDF", "Radau", "RK45", "LSODA")
        rtol: Relative tolerance
        atol: Absolute tolerance
        max_step: Maximum step size (0 = no limit)
    """

    method: str = "BDF"
    rtol: float = 1e-8
    atol: float = 1e-8
    max_step: float = 0.0


@dataclass
class ScipyODEResult:
    """Result of a SciPy ODE integration.

    Attributes:
        ts: Time points (shape: [n_steps])
        ys: Solution at each time point (shape: [n_species, n_steps]) — NOTE: transposed vs JAX
        success: Whether integration completed
        message: Solver status message
        n_rhs_evals: Number of RHS function evaluations
    """

    ts: np.ndarray
    ys: np.ndarray
    success: bool
    message: str
    n_rhs_evals: int


def solve_ode_scipy(
    rhs: RHSFn,
    y0: np.ndarray,
    t_span: tuple[float, float],
    config: ScipySolverConfig | None = None,
    t_eval: np.ndarray | None = None,
) -> ScipyODEResult:
    """Solve an ODE system using SciPy.

    Args:
        rhs: Right-hand-side function f(t, y) -> dy/dt
        y0: Initial state vector
        t_span: (t_start, t_end)
        config: Solver configuration
        t_eval: Specific times to evaluate solution at

    Returns:
        ScipyODEResult with time points, solution, and diagnostics
    """
    if config is None:
        config = ScipySolverConfig()

    y0 = np.asarray(y0, dtype=np.float64)

    sol = solve_ivp(
        rhs,
        t_span,
        y0,
        method=config.method,
        rtol=config.rtol,
        atol=config.atol,
        t_eval=t_eval,
        max_step=config.max_step if config.max_step > 0 else np.inf,
        dense_output=False,
    )

    return ScipyODEResult(
        ts=sol.t,
        ys=sol.y,  # shape: (n_species, n_steps)
        success=sol.success,
        message=sol.message,
        n_rhs_evals=sol.nfev,
    )
