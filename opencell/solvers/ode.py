"""JAX-based ODE integrator for OpenCell.

Uses Diffrax for adaptive-step ODE solving with JAX backend.
Supports both non-stiff (Dopri5/Tsit5) and stiff (Kvaerno5/implicit) methods.
Always uses float64 for numerical stability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import diffrax
import jax
import jax.numpy as jnp
from jax.typing import ArrayLike

jax.config.update("jax_enable_x64", True)

# Type alias for ODE right-hand-side function: f(t, y, args) -> dy/dt
RHSFn = Callable[[float, ArrayLike, Any], ArrayLike]


@dataclass(frozen=True)
class ODESolverConfig:
    """Configuration for the JAX ODE solver.

    Attributes:
        method: Solver method ("tsit5", "dopri5", "kvaerno5")
        rtol: Relative tolerance
        atol: Absolute tolerance
        max_steps: Maximum number of solver steps
        dt0: Initial step size (None = auto)
    """

    method: str = "tsit5"
    rtol: float = 1e-8
    atol: float = 1e-8
    max_steps: int = 100_000
    dt0: float | None = None


def _get_solver(method: str) -> diffrax.AbstractSolver:
    """Map method name to Diffrax solver."""
    solvers = {
        "tsit5": diffrax.Tsit5(),
        "dopri5": diffrax.Dopri5(),
        "kvaerno5": diffrax.Kvaerno5(),
        "euler": diffrax.Euler(),
    }
    if method not in solvers:
        raise ValueError(f"Unknown solver method: {method}. Choose from {list(solvers.keys())}")
    return solvers[method]


@dataclass
class ODEResult:
    """Result of an ODE integration.

    Attributes:
        ts: Time points (shape: [n_steps])
        ys: Solution at each time point (shape: [n_steps, n_species])
        stats: Solver statistics (steps accepted, rejected, etc.)
        success: Whether integration completed without error
    """

    ts: jax.Array
    ys: jax.Array
    stats: dict[str, Any]
    success: bool


def solve_ode(
    rhs: RHSFn,
    y0: ArrayLike,
    t_span: tuple[float, float],
    args: Any = None,
    config: ODESolverConfig | None = None,
    saveat: ArrayLike | None = None,
) -> ODEResult:
    """Solve an ODE system using Diffrax/JAX.

    Args:
        rhs: Right-hand-side function f(t, y, args) -> dy/dt
        y0: Initial state vector
        t_span: (t_start, t_end)
        args: Additional arguments passed to rhs
        config: Solver configuration
        saveat: Specific times to save solution at (None = save at solver steps)

    Returns:
        ODEResult with time points, solution, and stats
    """
    if config is None:
        config = ODESolverConfig()

    y0 = jnp.asarray(y0, dtype=jnp.float64)
    solver = _get_solver(config.method)
    stepsize_controller = diffrax.PIDController(
        rtol=config.rtol,
        atol=config.atol,
    )

    t0, t1 = t_span
    dt0 = config.dt0 if config.dt0 is not None else (t1 - t0) / 1000

    term = diffrax.ODETerm(rhs)

    if saveat is not None:
        save = diffrax.SaveAt(ts=jnp.asarray(saveat, dtype=jnp.float64))
    else:
        save = diffrax.SaveAt(t1=True)

    sol = diffrax.diffeqsolve(
        term,
        solver,
        t0=t0,
        t1=t1,
        dt0=dt0,
        y0=y0,
        args=args,
        stepsize_controller=stepsize_controller,
        max_steps=config.max_steps,
        saveat=save,
    )

    return ODEResult(
        ts=sol.ts,
        ys=sol.ys,
        stats={"num_steps": sol.stats.get("num_steps", -1)} if hasattr(sol, "stats") else {},
        success=True,
    )
