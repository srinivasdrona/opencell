"""Design-only test skeletons for the v5 chassis integration handoff."""

from __future__ import annotations

import pytest

from opencell.vivarium.karr_composite_v5_skeleton import build_karr_chassis_v5


def test_chassis_v5_builds() -> None:
    pytest.skip("waits on pc-t2..t10")
    engine = build_karr_chassis_v5(time_step_s=1.0, emit_step_s=1.0)
    assert engine is not None
    assert len(engine.processes) == 27


def test_10000_tick_partial_cycle() -> None:
    pytest.skip("waits on pc-t2..t10")
    engine = build_karr_chassis_v5(time_step_s=1.0, emit_step_s=1.0)
    engine.update(10_000.0)
    timeseries = engine.emitter.get_timeseries()
    assert timeseries["chromosome"]["replication_state"][-1] in {"elongating", "complete", "dividing"}


def test_replication_dntp_demand_matches_karr_trace() -> None:
    pytest.skip("waits on pc-t2..t10")
    engine = build_karr_chassis_v5(time_step_s=1.0, emit_step_s=1.0)
    engine.update(10_000.0)
    timeseries = engine.emitter.get_timeseries()
    assert "dATP" in timeseries["substrates"]


def test_division_event_fires_once_around_tick_9000() -> None:
    pytest.skip("waits on pc-t2..t10")
    engine = build_karr_chassis_v5(time_step_s=1.0, emit_step_s=1.0)
    engine.update(10_000.0)
    timeseries = engine.emitter.get_timeseries()
    assert timeseries["cell"]["division_event_count"][-1] == pytest.approx(1.0)


def test_no_regression_vs_chassis_v4() -> None:
    pytest.skip("waits on pc-t2..t10")
    # Placeholder assertion contract:
    # - run the 10 v4 integration tests unchanged
    # - require zero behavior regressions before deprecating v4
    assert True
