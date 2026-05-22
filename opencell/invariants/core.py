"""Karr-independent simulation invariants (Phase 4 / A7 v0.1).

These checks are biology-agnostic in form (they don't know about specific
metabolites or genes) but biology-aware in content (they understand that
concentrations are non-negative, counts are integer-valued, conservation
laws constrain reaction networks). They are the "physics check" that A5
Level-2 consumes.

Each invariant is a callable taking ``(state, context)`` and returning an
``InvariantReport`` with structured findings. Multiple invariants are
composed via ``InvariantSuite.run(...)``. A clean run produces a report
with zero violations; a dirty run lists every violation timestep,
variable, and quantity by which the invariant was breached.

Design rules:

* Invariants never silently pass. They either record OK with a non-empty
  ``checks`` list, or record violations with structured detail.
* Invariants never raise on violation. They report; the caller decides
  whether to fail. (A5 diff tool wraps these to surface them as
  Level-2 findings.)
* Tolerances are explicit, not inferred. A6 §5.1 is the tolerance source
  of truth for default values.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np


@dataclass
class InvariantViolation:
    """Single violation found by an invariant check."""

    invariant: str
    variable: str
    timestep_index: int
    time_value: float
    measured: float
    bound: float
    detail: str = ""


@dataclass
class InvariantReport:
    """Report from one invariant run.

    ``checks`` enumerates what was actually checked (for audit). Empty
    ``checks`` is an error — an invariant must run on something or
    declare it has nothing to check.
    """

    invariant: str
    checks: list[str] = field(default_factory=list)
    violations: list[InvariantViolation] = field(default_factory=list)
    notes: str = ""

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0 and len(self.checks) > 0


@dataclass
class InvariantSuiteReport:
    """Aggregated report across multiple invariants."""

    suite_name: str
    reports: list[InvariantReport] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.reports)

    @property
    def violation_count(self) -> int:
        return sum(len(r.violations) for r in self.reports)

    def summary(self) -> str:
        lines = [
            f"InvariantSuite '{self.suite_name}': "
            f"{'PASS' if self.passed else 'FAIL'} "
            f"({self.violation_count} violations across "
            f"{len(self.reports)} checks)"
        ]
        for r in self.reports:
            status = "ok" if r.passed else f"{len(r.violations)} violations"
            lines.append(f"  - {r.invariant}: {status}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Concrete invariants
# ---------------------------------------------------------------------------


def check_non_negativity(
    *,
    times: np.ndarray,
    values: dict[str, np.ndarray],
    abs_tol: float = 1e-9,
    name: str = "non_negativity",
) -> InvariantReport:
    """All declared variables must be >= -abs_tol at every timestep.

    Floating-point ODE solvers can produce tiny negatives near zero;
    ``abs_tol`` (default 1e-9) absorbs those. Larger negatives are real
    violations and reported with the worst-case offender per variable.
    """
    report = InvariantReport(invariant=name)
    for var, traj in values.items():
        traj = np.asarray(traj, dtype=np.float64)
        report.checks.append(f"variable '{var}' across {len(traj)} steps")
        worst = traj.min()
        if worst < -abs_tol:
            idx = int(np.argmin(traj))
            report.violations.append(
                InvariantViolation(
                    invariant=name,
                    variable=var,
                    timestep_index=idx,
                    time_value=float(times[idx]),
                    measured=float(worst),
                    bound=-abs_tol,
                    detail=f"min value {worst:.3e} below -abs_tol={abs_tol}",
                )
            )
    return report


def check_bounded(
    *,
    times: np.ndarray,
    values: dict[str, np.ndarray],
    bounds: dict[str, tuple[float, float]],
    abs_tol: float = 1e-9,
    name: str = "bounded",
) -> InvariantReport:
    """Each declared variable must lie within its [lo, hi] bound."""
    report = InvariantReport(invariant=name)
    for var, (lo, hi) in bounds.items():
        if var not in values:
            continue
        traj = np.asarray(values[var], dtype=np.float64)
        report.checks.append(f"variable '{var}' in [{lo}, {hi}]")
        if traj.min() < lo - abs_tol:
            idx = int(np.argmin(traj))
            report.violations.append(
                InvariantViolation(
                    invariant=name,
                    variable=var,
                    timestep_index=idx,
                    time_value=float(times[idx]),
                    measured=float(traj[idx]),
                    bound=lo,
                    detail=f"below lower bound by {lo - traj[idx]:.3e}",
                )
            )
        if traj.max() > hi + abs_tol:
            idx = int(np.argmax(traj))
            report.violations.append(
                InvariantViolation(
                    invariant=name,
                    variable=var,
                    timestep_index=idx,
                    time_value=float(times[idx]),
                    measured=float(traj[idx]),
                    bound=hi,
                    detail=f"above upper bound by {traj[idx] - hi:.3e}",
                )
            )
    return report


def check_conservation(
    *,
    times: np.ndarray,
    values: dict[str, np.ndarray],
    groups: dict[str, Sequence[str]],
    abs_tol: float = 1e-6,
    rel_tol: float = 1e-4,
    name: str = "conservation",
) -> InvariantReport:
    """For each named group, the sum of group members must be constant.

    Useful for moiety-conservation checks (e.g. total adenine pool =
    ATP + ADP + AMP). Reports the worst per-step deviation from the
    initial sum for each group.
    """
    report = InvariantReport(invariant=name)
    for group_name, members in groups.items():
        present = [m for m in members if m in values]
        if not present:
            continue
        report.checks.append(f"group '{group_name}' = sum({', '.join(present)})")
        stacked = np.array([np.asarray(values[m], dtype=np.float64) for m in present])
        totals = stacked.sum(axis=0)
        ref = totals[0]
        deviations = totals - ref
        worst = float(np.max(np.abs(deviations)))
        threshold = max(abs_tol, abs(ref) * rel_tol)
        if worst > threshold:
            idx = int(np.argmax(np.abs(deviations)))
            report.violations.append(
                InvariantViolation(
                    invariant=name,
                    variable=group_name,
                    timestep_index=idx,
                    time_value=float(times[idx]),
                    measured=float(totals[idx]),
                    bound=float(ref),
                    detail=(
                        f"sum drifted by {deviations[idx]:.3e} "
                        f"(threshold {threshold:.3e}, members={present})"
                    ),
                )
            )
    return report


def check_count_integrality(
    *,
    times: np.ndarray,
    values: dict[str, np.ndarray],
    abs_tol: float = 1e-9,
    name: str = "count_integrality",
) -> InvariantReport:
    """Stochastic count variables must remain integer-valued.

    Tau-leap and SSA preserve integrality; if a coupled engine drifts
    here it almost always means a deterministic update was applied to
    a count port (wrong updater).
    """
    report = InvariantReport(invariant=name)
    for var, traj in values.items():
        traj = np.asarray(traj, dtype=np.float64)
        report.checks.append(f"variable '{var}' integer-valued")
        residual = np.abs(traj - np.round(traj))
        worst = float(residual.max())
        if worst > abs_tol:
            idx = int(np.argmax(residual))
            report.violations.append(
                InvariantViolation(
                    invariant=name,
                    variable=var,
                    timestep_index=idx,
                    time_value=float(times[idx]),
                    measured=float(traj[idx]),
                    bound=float(np.round(traj[idx])),
                    detail=f"non-integer residual {worst:.3e}",
                )
            )
    return report


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------


@dataclass
class InvariantSuite:
    """Compose multiple invariant checks under one name.

    Each entry is a callable returning an ``InvariantReport``. The suite
    runs them in order and aggregates results.
    """

    name: str
    checks: list[Callable[[], InvariantReport]] = field(default_factory=list)

    def add(self, fn: Callable[[], InvariantReport]) -> InvariantSuite:
        self.checks.append(fn)
        return self

    def run(self) -> InvariantSuiteReport:
        suite = InvariantSuiteReport(suite_name=self.name)
        for fn in self.checks:
            suite.reports.append(fn())
        return suite
