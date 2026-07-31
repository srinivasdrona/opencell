"""Unit tests for `scripts/l2_event/adapters/` (D7 adapter interface,
fakes, adapter-mismatch refusal, anti-laundering signature discipline, and
the RibosomeAssembly seed-0 structural smoke adapter). Requirement 6:
adapter mismatch, anti-laundering, RA seed0 structural loader smoke."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.adapters.base import (
    AdapterProcessMismatch,
    EventAdapter,
    assert_adapter_matches_process,
)
from scripts.l2_event.adapters.fakes import SyntheticFireCountAdapter, WrongProcessAdapter
from scripts.l2_event.window_loader import WindowGrid

_RA_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s000"
    / "RibosomeAssembly_100ticks.mat"
)


def _synthetic_window(fire_counts: list[float]) -> WindowGrid:
    n = len(fire_counts)
    arr = np.array(fire_counts, dtype=float).reshape(n, 1)
    return WindowGrid(
        process_name="SyntheticTestProcess",
        seed=0,
        n_ticks=n,
        tick_offset=0.0,
        trace_path=Path("synthetic.mat"),
        observables=("event_fire_count",),
        states_before={"event_fire_count": arr},
        states_after={"event_fire_count": arr},
    )


def test_synthetic_fire_count_adapter_isinstance_of_event_adapter_protocol():
    adapter = SyntheticFireCountAdapter()
    assert isinstance(adapter, EventAdapter)


def test_synthetic_fire_count_adapter_karr_observation_reads_fire_count():
    window = _synthetic_window([0.0, 1.0, 0.0, 2.0])
    adapter = SyntheticFireCountAdapter()
    obs0 = adapter.karr_observation(window, 0)
    assert obs0.fired is False
    obs1 = adapter.karr_observation(window, 1)
    assert obs1.fired is True
    assert obs1.fire_count == 1
    obs3 = adapter.karr_observation(window, 3)
    assert obs3.fire_count == 2


def test_synthetic_fire_count_adapter_oc_observation_reads_update_dict():
    adapter = SyntheticFireCountAdapter()
    obs = adapter.oc_observation(5, state_before={}, update={"fire_count": 3, "payload": {"x": 1.0}})
    assert obs.fired is True
    assert obs.fire_count == 3
    assert obs.payload == {"x": 1.0}

    obs_quiet = adapter.oc_observation(6, state_before={}, update={})
    assert obs_quiet.fired is False
    assert obs_quiet.fire_count == 0


def test_assert_adapter_matches_process_raises_on_mismatch():
    adapter = WrongProcessAdapter()
    with pytest.raises(AdapterProcessMismatch):
        assert_adapter_matches_process(adapter, "SyntheticTestProcess")


def test_assert_adapter_matches_process_passes_for_matching_process():
    adapter = SyntheticFireCountAdapter()
    assert_adapter_matches_process(adapter, "SyntheticTestProcess")  # must not raise


def test_karr_observation_signature_never_accepts_oc_side_arguments():
    """Anti-laundering (requirement 3): the Karr-side method's signature
    must only ever be able to see the window grid + tick -- it must have
    no parameter through which an OC `update`/`state_before` value could
    be passed in, which would let an adapter launder OC data into what is
    supposed to be a Karr-only observation."""
    sig = inspect.signature(SyntheticFireCountAdapter.karr_observation)
    params = list(sig.parameters)
    assert params == ["self", "window", "tick"]


def test_oc_observation_signature_never_accepts_a_window_grid_argument():
    """Anti-laundering (requirement 3): the OC-side method's signature
    must only ever see `tick`, `state_before`, `update` -- never a
    `WindowGrid`/Karr-trace object, so it cannot read Karr's
    `states_after` (or `states_before`, beyond what was already legitimately
    overlaid into `state_before`) directly."""
    sig = inspect.signature(SyntheticFireCountAdapter.oc_observation)
    params = list(sig.parameters)
    assert params == ["self", "tick", "state_before", "update"]
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = str(param.annotation)
        assert "WindowGrid" not in annotation, (
            f"oc_observation parameter '{name}' must never be annotated to accept a WindowGrid"
        )


# ---------------------------------------------------------------------------
# RibosomeAssembly seed-0 structural smoke adapter (real data, optional)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_ribosome_assembly_smoke_adapter_karr_observation_matches_real_trace_events():
    """Structural loader smoke only (task requirement): confirms the
    adapter can read real Karr complex-count deltas and correctly derive
    fired/fire_count/payload -- this is NOT a gate verdict and must never
    be interpreted as one."""
    from scripts.l2_event.adapters.ribosome_assembly_smoke import (
        _RA_OBSERVABLES,
        RibosomeAssemblySmokeAdapter,
    )
    from scripts.l2_event.window_loader import load_event_window

    window = load_event_window(_RA_TRACE, required_observables=_RA_OBSERVABLES)
    adapter = RibosomeAssemblySmokeAdapter()
    assert adapter.process_name == "RibosomeAssembly"

    total_fires = sum(adapter.karr_observation(window, tick).fire_count for tick in range(window.n_ticks))
    # Ground-truth audit already established: 2 real complex-formation
    # events in this seed-0 window.
    assert total_fires == 2


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_ribosome_assembly_oc_observation_handles_empty_update_dict_without_keyerror():
    """Spec §4 fact 5: an allocation-starved OC tick can return an empty
    dict entirely (no 'complex' key). The adapter must use .get(), not
    direct key access, or this raises a KeyError instead of a clean
    not-fired observation."""
    from scripts.l2_event.adapters.ribosome_assembly_smoke import RibosomeAssemblySmokeAdapter

    adapter = RibosomeAssemblySmokeAdapter()
    obs = adapter.oc_observation(0, state_before={}, update={})
    assert obs.fired is False
    assert obs.fire_count == 0


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_run_structural_smoke_end_to_end_against_real_seed0_never_returns_a_gate_verdict():
    """The full RA seed-0 structural smoke (loader + real OC port replay):
    must succeed structurally (Karr fires == OC fires, matching the
    ground-truth audit of 2/2) but its return shape has no `verdict` key
    at all -- proving by construction that this code path cannot be
    mistaken for a gate PASS/FAIL."""
    from scripts.l2_event.runner import run_structural_smoke

    result = run_structural_smoke(
        process="RibosomeAssembly",
        seed=0,
        trace_path=_RA_TRACE,
        registry_entry=None,
        registry=None,
    )
    assert "verdict" not in result
    assert result["n_ticks"] == 100
    assert result["tick_offset"] == 200.0
    assert result["karr_total_fires"] == 2
    assert result["oc_total_fires"] == 2
