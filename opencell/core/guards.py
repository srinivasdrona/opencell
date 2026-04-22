"""Runtime invariant guards for OpenCell.

Catches fundamental violations immediately rather than letting them
propagate through the simulation. On first violation: logs detailed
diagnostic info (variable name, module, step, residual size).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class GuardViolation:
    """Record of a guard violation."""

    guard_name: str
    species_id: str
    value: float
    bound: str
    step: int
    time_s: float
    module: str = ""

    def __str__(self) -> str:
        return (
            f"[{self.guard_name}] {self.species_id}={self.value:.6e} "
            f"violates {self.bound} at step={self.step}, t={self.time_s:.4f}s"
            f"{f', module={self.module}' if self.module else ''}"
        )


class Guards:
    """Runtime invariant monitors.

    Checks:
    - Concentrations/counts ≥ 0
    - Occupancies/fractions in [0, 1]
    - Conserved moieties within tolerance
    - Stoichiometry net mass residual near zero
    """

    def __init__(self, tolerance: float = 1e-8) -> None:
        self.tolerance = tolerance
        self.violations: list[GuardViolation] = []

    def check_positivity(
        self,
        counts: dict[str, float],
        step: int,
        time_s: float,
        module: str = "",
    ) -> list[GuardViolation]:
        """Check that all counts are non-negative."""
        new_violations = []
        for species_id, value in counts.items():
            if value < -self.tolerance:
                v = GuardViolation(
                    guard_name="positivity",
                    species_id=species_id,
                    value=value,
                    bound="≥ 0",
                    step=step,
                    time_s=time_s,
                    module=module,
                )
                new_violations.append(v)
                logger.error(str(v))
        self.violations.extend(new_violations)
        return new_violations

    def check_fraction_bounds(
        self,
        fractions: dict[str, float],
        step: int,
        time_s: float,
        module: str = "",
    ) -> list[GuardViolation]:
        """Check that fractions/occupancies are in [0, 1]."""
        new_violations = []
        for species_id, value in fractions.items():
            if value < -self.tolerance or value > 1.0 + self.tolerance:
                v = GuardViolation(
                    guard_name="fraction_bounds",
                    species_id=species_id,
                    value=value,
                    bound="[0, 1]",
                    step=step,
                    time_s=time_s,
                    module=module,
                )
                new_violations.append(v)
                logger.error(str(v))
        self.violations.extend(new_violations)
        return new_violations

    def check_conservation(
        self,
        pre_total: float,
        post_total: float,
        conserved_name: str,
        step: int,
        time_s: float,
    ) -> list[GuardViolation]:
        """Check that a conserved quantity is maintained within tolerance."""
        residual = abs(post_total - pre_total)
        new_violations = []
        if residual > self.tolerance:
            v = GuardViolation(
                guard_name="conservation",
                species_id=conserved_name,
                value=residual,
                bound=f"residual < {self.tolerance}",
                step=step,
                time_s=time_s,
            )
            new_violations.append(v)
            logger.error(str(v))
        self.violations.extend(new_violations)
        return new_violations

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0

    def summary(self) -> str:
        """Human-readable summary of all violations."""
        if not self.violations:
            return "No guard violations."
        lines = [f"Guard violations ({len(self.violations)}):"]
        for v in self.violations[:20]:  # cap at 20
            lines.append(f"  {v}")
        if len(self.violations) > 20:
            lines.append(f"  ... and {len(self.violations) - 20} more")
        return "\n".join(lines)
