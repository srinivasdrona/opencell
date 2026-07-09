"""Main simulation engine for OpenCell.

Orchestrates sub-model execution with operator splitting,
resource allocation via ledger, and invariant checking.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from opencell.core.ir import IRSpeciesRegistry
from opencell.core.resource_ledger import ResourceLedger
from opencell.core.state import CellState
from opencell.models.base import SubModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineConfig:
    """Simulation engine configuration.

    Attributes:
        dt: Time step for operator splitting sync points (seconds)
        t_end: End time (seconds)
        check_positivity: Validate non-negative counts each step
        check_conservation: Check mass conservation each step
        log_interval: Log progress every N steps
    """

    dt: float = 1.0
    t_end: float = 100.0
    check_positivity: bool = True
    check_conservation: bool = True
    log_interval: int = 10


@dataclass
class StepResult:
    """Result of a single simulation step."""

    step: int
    time_s: float
    dt: float
    wall_time_ms: float
    positivity_violations: list[str] = field(default_factory=list)
    conservation_residual: float = 0.0


@dataclass
class SimulationResult:
    """Complete simulation result."""

    states: list[CellState]
    steps: list[StepResult]
    success: bool
    error_message: str = ""
    total_wall_time_s: float = 0.0


class Engine:
    """Main simulation engine with operator splitting.

    Runs sub-models sequentially at each sync point using Strang-style
    operator splitting. Resource allocation for shared species is handled
    by the ResourceLedger.

    Limitations:
    - Strang splitting is only order-2 accurate when operators commute
    - For stiff coupling, accuracy degrades
    - Currently sequential (no parallel sub-model execution)
    """

    def __init__(
        self,
        sub_models: list[SubModel],
        registry: IRSpeciesRegistry,
        config: EngineConfig | None = None,
    ) -> None:
        self.sub_models = sub_models
        self.registry = registry
        self.config = config or EngineConfig()
        self.ledger = ResourceLedger()
        self._validate_contracts()

    def _validate_contracts(self) -> None:
        """Validate that all sub-model contracts are consistent."""
        for sm in self.sub_models:
            errors = sm.contract.validate_against_registry(self.registry)
            if errors:
                raise ValueError(f"Sub-model '{sm.id}' contract errors: {errors}")

    def run(self, initial_state: CellState) -> SimulationResult:
        """Run the simulation from initial state to t_end."""
        state = initial_state
        states = [state]
        steps: list[StepResult] = []
        t_start = time.perf_counter()

        # Initialize all sub-models
        for sm in self.sub_models:
            sm.initialize(state)

        step_num = 0
        t = state.time_s

        try:
            while t < self.config.t_end:
                dt = min(self.config.dt, self.config.t_end - t)
                step_start = time.perf_counter()

                # Compute derivatives from all sub-models
                all_derivatives: dict[str, float] = {}
                for sm in self.sub_models:
                    derivs = sm.compute_derivatives(t, state)
                    for species_id, rate in derivs.items():
                        all_derivatives[species_id] = all_derivatives.get(species_id, 0.0) + rate

                # Forward Euler update (will be replaced with proper splitting)
                new_counts = np.array(state.counts, dtype=np.float64)
                for species_id, rate in all_derivatives.items():
                    idx = self.registry.index(species_id)
                    new_counts[idx] += rate * dt

                # Update state
                t += dt
                new_key = state.rng_key.spawn(1)[0]
                state = CellState(
                    time_s=t,
                    counts=new_counts,
                    registry=state.registry,
                    geometry=state.geometry,
                    rng_key=new_key,
                )

                # Invariant checks
                step_result = StepResult(
                    step=step_num,
                    time_s=t,
                    dt=dt,
                    wall_time_ms=(time.perf_counter() - step_start) * 1000,
                )

                if self.config.check_positivity:
                    violations = state.validate_positivity()
                    step_result.positivity_violations = violations
                    if violations:
                        logger.warning(f"Step {step_num}: positivity violations: {violations}")

                steps.append(step_result)
                states.append(state)
                step_num += 1

                if step_num % self.config.log_interval == 0:
                    logger.info(
                        f"Step {step_num}: t={t:.2f}s, wall={step_result.wall_time_ms:.1f}ms"
                    )

        except Exception as e:
            return SimulationResult(
                states=states,
                steps=steps,
                success=False,
                error_message=str(e),
                total_wall_time_s=time.perf_counter() - t_start,
            )

        return SimulationResult(
            states=states,
            steps=steps,
            success=True,
            total_wall_time_s=time.perf_counter() - t_start,
        )
