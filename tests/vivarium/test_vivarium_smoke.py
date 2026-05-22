"""Smoke tests for the Vivarium adapter (Phase 4 / A1).

These are deliberately lightweight: they verify the adapters expose the
expected ports, run end-to-end without raising, and produce non-trivial
coupling. Heavy numerical equivalence vs ``hybrid_run`` is the job of
the A5 diff tool; here we only check the semantics-contract guards.
"""

from __future__ import annotations

import numpy as np
import pytest

from opencell.models.coupled import CoupledMetabolismTranscription
from opencell.vivarium import (
    GeneNetworkProcess,
    MetabolismProcess,
    SignalProcess,
    build_coupled_engine,
)


@pytest.fixture(scope="module")
def coupled():
    return CoupledMetabolismTranscription.build(signal="uptake_flux")


def test_metabolism_process_ports(coupled) -> None:
    proc = MetabolismProcess({"coupled": coupled})
    schema = proc.ports_schema()
    assert "metabolites" in schema
    assert "signal" in schema
    assert "cglcex" in schema["metabolites"]
    assert schema["metabolites"]["cglcex"]["_updater"] == "set"
    assert schema["signal"]["v_pts"]["_updater"] == "set"


def test_signal_process_ports(coupled) -> None:
    proc = SignalProcess({"coupled": coupled})
    schema = proc.ports_schema()
    assert schema["signal"]["f_met"]["_updater"] == "set"
    assert schema["signal"]["f_met"]["_default"] == 1.0


def test_gene_network_requires_explicit_rng(coupled) -> None:
    with pytest.raises(ValueError, match="explicit 'rng'"):
        GeneNetworkProcess({"coupled": coupled, "rng": None})


def test_gene_network_ports(coupled) -> None:
    rng = np.random.default_rng(0)
    proc = GeneNetworkProcess({"coupled": coupled, "rng": rng})
    schema = proc.ports_schema()
    assert "gene_state" in schema
    assert schema["gene_state"]["MA"]["_updater"] == "accumulate"
    assert schema["signal"]["f_met"]["_updater"] == "set"


def test_engine_runs_short_horizon(coupled) -> None:
    eng = build_coupled_engine(coupled=coupled, macro_dt_s=60.0, seed=7)
    eng.update(120.0)
    ts = eng.emitter.get_timeseries()
    assert "metabolites" in ts and "gene_state" in ts and "signal" in ts
    assert len(ts["time"]) >= 2
    cglcex = np.asarray(ts["metabolites"]["cglcex"], dtype=np.float64)
    f_met = np.asarray(ts["signal"]["f_met"], dtype=np.float64)
    assert np.all(np.diff(cglcex) <= 1e-9)
    assert f_met.min() >= -1e-9
    assert f_met.max() <= 1.0 + 1e-9


def test_engine_couples_observably(coupled) -> None:
    """Long enough run that f_met must drop below 1 if coupling works."""
    eng = build_coupled_engine(coupled=coupled, macro_dt_s=60.0, seed=11)
    eng.update(1800.0)
    ts = eng.emitter.get_timeseries()
    f_met = np.asarray(ts["signal"]["f_met"], dtype=np.float64)
    cglcex = np.asarray(ts["metabolites"]["cglcex"], dtype=np.float64)
    assert f_met[-1] < 0.9, "f_met should have dropped — coupling broken?"
    assert cglcex[-1] < cglcex[0], "glucose should deplete"


def test_engine_rng_determinism(coupled) -> None:
    """Same seed must give identical gene trajectories."""
    e1 = build_coupled_engine(coupled=coupled, macro_dt_s=60.0, seed=1)
    e1.update(600.0)
    ma1 = np.asarray(e1.emitter.get_timeseries()["gene_state"]["MA"])
    e1b = build_coupled_engine(coupled=coupled, macro_dt_s=60.0, seed=1)
    e1b.update(600.0)
    ma1b = np.asarray(e1b.emitter.get_timeseries()["gene_state"]["MA"])
    np.testing.assert_array_equal(ma1, ma1b)


def test_topology_uses_separate_process_keys(coupled) -> None:
    """Regression: process keys must not collide with store path leaves
    (Vivarium places each process at the store path equal to its key)."""
    eng = build_coupled_engine(coupled=coupled, macro_dt_s=60.0, seed=0)
    keys = set(eng.processes.keys())
    assert "metabolism_proc" in keys
    assert "signal_proc" in keys
    assert "gene_network_proc" in keys
    assert "signal" not in keys
