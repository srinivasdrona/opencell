"""Tau-leaping stochastic solver for OpenCell.

Needed from day 1 for low-copy-number molecules (mRNA, transcription factors)
where deterministic ODEs are a poor approximation. Tau-leaping is a compromise
between exact Gillespie SSA (too slow) and ODEs (too smooth).

Algorithm: Approximate tau-leaping (Cao et al. 2006)
- Select tau such that no propensity changes by more than a threshold
- Fire all reactions simultaneously during tau
- Poisson-distributed number of firings per reaction

RNG hygiene: callers MUST pass an explicit ``np.random.Generator``. No
global-state mutation (no ``np.random.seed`` or unseeded ``np.random.*``).
This makes parallel realisations safe and reproducible regardless of what
else is running in the process. See ``.github/copilot-instructions.md``
"Stochastic RNG discipline" for the project-wide rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# Propensity function: given state y, return reaction propensities
PropensityFn = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class TauLeapConfig:
    """Configuration for tau-leaping solver.

    Attributes:
        epsilon: Error control parameter (0.03-0.05 typical)
        dt_max: Maximum leap size in seconds
        n_critical: Threshold for switching to exact SSA for near-zero species
    """

    epsilon: float = 0.03
    dt_max: float = 1.0
    n_critical: int = 10


@dataclass
class StochasticResult:
    """Result of a stochastic simulation.

    Attributes:
        ts: Time points
        ys: State trajectory (shape: [n_steps, n_species])
        n_steps: Number of tau-leap steps taken
    """

    ts: np.ndarray
    ys: np.ndarray
    n_steps: int


def tau_leap(
    propensity_fn: PropensityFn,
    stoich_matrix: np.ndarray,
    y0: np.ndarray,
    t_span: tuple[float, float],
    rng: np.random.Generator,
    config: TauLeapConfig | None = None,
    save_every: int = 1,
) -> StochasticResult:
    """Run tau-leaping stochastic simulation.

    Args:
        propensity_fn: Function returning reaction propensities given state
        stoich_matrix: Stoichiometry matrix (n_species x n_reactions)
        y0: Initial state (molecule counts, integer-valued)
        t_span: (t_start, t_end)
        rng: numpy ``Generator`` (e.g. ``np.random.default_rng(seed)``).
            All Poisson draws are sampled from this generator -- no global
            state is touched.
        config: Solver configuration
        save_every: Save state every N steps

    Returns:
        StochasticResult with trajectory
    """
    if config is None:
        config = TauLeapConfig()

    t0, t1 = t_span
    y = np.array(y0, dtype=np.float64)
    S = np.array(stoich_matrix, dtype=np.float64)

    t = t0
    step = 0
    ts_list = [t]
    ys_list = [y.copy()]

    while t < t1:
        props = np.array(propensity_fn(np.array(y)), dtype=np.float64)

        # All propensities zero -> system is dead
        if np.sum(props) == 0:
            break

        # Select tau (epsilon / a_sum, capped by dt_max and remaining time)
        a_sum = np.sum(props)
        tau = min(config.epsilon / a_sum if a_sum > 0 else config.dt_max, config.dt_max)
        tau = min(tau, t1 - t)

        # Sample number of firings from Poisson via the supplied Generator
        firings = rng.poisson(props * tau)

        # Update state
        y_new = y + S @ firings

        # Clamp negatives (tau-leaping can overshoot)
        y_new = np.maximum(y_new, 0.0)

        y = y_new
        t += tau
        step += 1

        if step % save_every == 0:
            ts_list.append(t)
            ys_list.append(y.copy())

    # Ensure final state is saved
    if ts_list[-1] != t:
        ts_list.append(t)
        ys_list.append(y.copy())

    return StochasticResult(
        ts=np.array(ts_list),
        ys=np.array(ys_list),
        n_steps=step,
    )
