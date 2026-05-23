"""Skeleton tests for the future 28-process chassis_v6."""

from __future__ import annotations

import pytest

from opencell.vivarium.karr_composite_v6_skeleton import (
    CHASSIS_V6_EXPECTED_PROCESS_KEYS,
    build_karr_chassis_v6,
)


def test_chassis_v6_builds() -> None:
    """Builds chassis_v6 and includes all 28 Karr process keys."""
    pytest.skip("waits on pc-final v5 + pd-t1")

    engine = build_karr_chassis_v6()
    process_keys = tuple(sorted(engine.processes.keys()))
    assert len(process_keys) == 28
    for key in CHASSIS_V6_EXPECTED_PROCESS_KEYS:
        assert key in process_keys


def test_full_cell_cycle_completes() -> None:
    """Runs 32400 ticks and observes a division event."""
    pytest.skip("waits on pc-final v5 + pd-t1")

    engine = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=60.0)
    engine.update(32400)
    raise AssertionError("skeleton: assert division event path once event schema is finalized")


def test_28_karr_phenotypes_extractable() -> None:
    """Scorecard skeleton: all 28 phenotype extractors can read v6 stores."""
    pytest.skip("waits on pc-final v5 + pd-t1")

    engine = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=60.0)
    _ = engine.emitter.get_data()
    raise AssertionError("skeleton: wire KP01..KP28 extractor coverage checks")


def test_no_regression_vs_chassis_v5() -> None:
    """v6 should preserve v5 behavior for shared observables (except host stores)."""
    pytest.skip("waits on pc-final v5 + pd-t1")

    raise AssertionError("skeleton: compare v5 vs v6 trajectory slices once v5 builder is merged")
