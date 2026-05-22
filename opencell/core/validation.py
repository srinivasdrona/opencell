"""Validation harness: conservation checks, timing, solver stats, event logs.

Provides biological validators that can be attached to simulation runs.
Concrete biological validators (growth rate, essentiality) are deferred
to Phase 2 when the sub-model API is known.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result from a single validation check."""

    name: str
    passed: bool
    message: str
    value: float | None = None
    threshold: float | None = None
    severity: str = "error"  # "error", "warning", "info"


@dataclass
class ValidationReport:
    """Aggregated validation results from a simulation run."""

    results: list[ValidationResult] = field(default_factory=list)
    wall_time_s: float = 0.0
    n_steps: int = 0
    solver_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity == "error")

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def n_failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def summary(self) -> str:
        lines = [f"Validation: {self.n_passed}/{len(self.results)} passed"]
        for r in self.results:
            status = "✓" if r.passed else "✗"
            lines.append(f"  {status} {r.name}: {r.message}")
        return "\n".join(lines)


class ValidationHarness:
    """Framework for attaching validators to simulation runs."""

    def __init__(self) -> None:
        self._validators: list[tuple[str, Callable]] = []

    def add_validator(
        self,
        name: str,
        validator: Callable[[dict[str, Any]], ValidationResult],
    ) -> None:
        """Register a validator function."""
        self._validators.append((name, validator))

    def validate(self, context: dict[str, Any]) -> ValidationReport:
        """Run all validators on a simulation context."""
        report = ValidationReport()
        for name, validator in self._validators:
            try:
                result = validator(context)
                report.results.append(result)
            except Exception as e:
                report.results.append(
                    ValidationResult(
                        name=name,
                        passed=False,
                        message=f"Validator crashed: {e}",
                        severity="error",
                    )
                )
        return report


# ── Built-in validators ──


def mass_conservation_validator(
    tolerance: float = 1e-6,
) -> Callable[[dict[str, Any]], ValidationResult]:
    """Check that total mass is conserved across a simulation."""

    def validate(ctx: dict[str, Any]) -> ValidationResult:
        initial_mass = ctx.get("initial_total_mass", 0.0)
        final_mass = ctx.get("final_total_mass", 0.0)
        if initial_mass == 0:
            return ValidationResult(
                name="mass_conservation",
                passed=True,
                message="No mass to conserve (open system or zero initial)",
                severity="info",
            )
        residual = abs(final_mass - initial_mass) / initial_mass
        passed = residual < tolerance
        return ValidationResult(
            name="mass_conservation",
            passed=passed,
            message=f"Relative mass residual: {residual:.2e} (threshold: {tolerance:.2e})",
            value=residual,
            threshold=tolerance,
        )

    return validate


def positivity_validator() -> Callable[[dict[str, Any]], ValidationResult]:
    """Check that all species counts are non-negative."""

    def validate(ctx: dict[str, Any]) -> ValidationResult:
        counts = ctx.get("final_counts", {})
        negatives = {k: v for k, v in counts.items() if v < 0}
        if negatives:
            return ValidationResult(
                name="positivity",
                passed=False,
                message=f"Negative counts: {negatives}",
                severity="error",
            )
        return ValidationResult(
            name="positivity",
            passed=True,
            message="All counts non-negative",
        )

    return validate


def doubling_time_validator(
    expected_hours: float,
    tolerance_factor: float = 2.0,
) -> Callable[[dict[str, Any]], ValidationResult]:
    """Check that doubling time is within expected range.

    This is a Phase 2+ validator — needs actual growth data.
    """

    def validate(ctx: dict[str, Any]) -> ValidationResult:
        dt_hours = ctx.get("doubling_time_hours")
        if dt_hours is None:
            return ValidationResult(
                name="doubling_time",
                passed=True,
                message="No doubling time data (pre-Phase 2)",
                severity="info",
            )
        lower = expected_hours / tolerance_factor
        upper = expected_hours * tolerance_factor
        passed = lower <= dt_hours <= upper
        return ValidationResult(
            name="doubling_time",
            passed=passed,
            message=f"Doubling time: {dt_hours:.1f}h (expected: {lower:.1f}-{upper:.1f}h)",
            value=dt_hours,
            threshold=expected_hours,
        )

    return validate
