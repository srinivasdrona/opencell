"""Tests for invariants module (Phase 4 / A7)."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.invariants import (
    InvariantSuite,
    check_bounded,
    check_conservation,
    check_count_integrality,
    check_non_negativity,
)


def test_non_negativity_passes_for_clean_trajectory() -> None:
    times = np.linspace(0, 10, 50)
    values = {"x": np.linspace(2.0, 0.1, 50)}
    rep = check_non_negativity(times=times, values=values)
    assert rep.passed
    assert rep.violations == []


def test_non_negativity_flags_negative() -> None:
    times = np.linspace(0, 10, 50)
    traj = np.linspace(2.0, -0.5, 50)
    rep = check_non_negativity(times=times, values={"x": traj})
    assert not rep.passed
    assert len(rep.violations) == 1
    v = rep.violations[0]
    assert v.variable == "x"
    assert v.measured == pytest.approx(-0.5, rel=1e-9)


def test_non_negativity_tolerates_floating_noise() -> None:
    times = np.linspace(0, 1, 5)
    rep = check_non_negativity(
        times=times,
        values={"x": np.array([0.0, 0.0, -1e-12, 0.0, 1.0])},
        abs_tol=1e-9,
    )
    assert rep.passed


def test_bounded_flags_breach() -> None:
    times = np.linspace(0, 1, 10)
    rep = check_bounded(
        times=times,
        values={"f": np.array([0.5, 0.6, 1.5, 0.7, -0.1, 0.4, 0.5, 0.5, 0.5, 0.5])},
        bounds={"f": (0.0, 1.0)},
    )
    assert not rep.passed
    # Two breaches: one above (1.5), one below (-0.1)
    assert len(rep.violations) == 2


def test_conservation_passes_for_constant_sum() -> None:
    times = np.linspace(0, 1, 20)
    a = np.linspace(0.5, 0.1, 20)
    b = np.linspace(0.0, 0.4, 20)
    c = np.full(20, 0.5)  # a + b + c = 1.0 throughout
    rep = check_conservation(
        times=times,
        values={"a": a, "b": b, "c": c},
        groups={"abc_total": ["a", "b", "c"]},
    )
    assert rep.passed


def test_conservation_flags_drift() -> None:
    times = np.linspace(0, 1, 5)
    a = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
    b = np.array([0.5, 0.4, 0.3, 0.2, 0.1])  # b drains, total drifts
    rep = check_conservation(
        times=times,
        values={"a": a, "b": b},
        groups={"ab_total": ["a", "b"]},
        abs_tol=0.01,
        rel_tol=0.01,
    )
    assert not rep.passed
    assert len(rep.violations) == 1


def test_count_integrality_flags_fractional() -> None:
    times = np.linspace(0, 1, 5)
    rep = check_count_integrality(
        times=times,
        values={"MA": np.array([0.0, 1.0, 2.0, 2.5, 3.0])},
    )
    assert not rep.passed
    assert rep.violations[0].variable == "MA"


def test_suite_aggregates() -> None:
    times = np.linspace(0, 1, 5)
    suite = InvariantSuite(name="test_suite")
    suite.add(
        lambda: check_non_negativity(
            times=times,
            values={"x": np.array([1.0, 1.0, 1.0, 1.0, 1.0])},
        )
    )
    suite.add(
        lambda: check_count_integrality(
            times=times,
            values={"MA": np.array([0, 1, 2, 3, 4], dtype=float)},
        )
    )
    rep = suite.run()
    assert rep.passed
    assert len(rep.reports) == 2
    assert "PASS" in rep.summary()


def test_suite_reports_summary_on_fail() -> None:
    times = np.linspace(0, 1, 5)
    suite = InvariantSuite(name="test_suite")
    suite.add(
        lambda: check_non_negativity(
            times=times,
            values={"x": np.array([1.0, -1.0, 1.0, 1.0, 1.0])},
        )
    )
    rep = suite.run()
    assert not rep.passed
    assert "FAIL" in rep.summary()
    assert rep.violation_count == 1
