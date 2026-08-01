"""Unit tests for `scripts/l2_event/window_loader.py` (D1 + requirement 4:
stride-1 fully enumerated window loader and its refusal gauntlet).

Uses both the real copied RibosomeAssembly seed-000 event-window MAT (if
present locally -- skipped otherwise, matching the task's "if possible"
qualifier for real-data dependent checks) and small synthetic HDF5 fixtures
written directly with h5py so every refusal branch is exercised
deterministically without depending on any raw data being present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.window_loader import (
    EventWindowRefused,
    classify_trace_dir,
    load_event_window,
)

_REAL_RA_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s000"
    / "RibosomeAssembly_100ticks.mat"
)

_REAL_STANDARD_TRACE = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s001" / "Translation_100ticks.mat"


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _write_synthetic_trace(
    path: Path,
    *,
    n_ticks: int = 3,
    tick_offset: float | None = 200.0,
    process_name: str = "SyntheticProcess",
    rng_seed: int = 0,
    observables: tuple[str, ...] = ("obsA",),
    truncated_observable: str | None = None,
    missing_observable_group: str | None = None,
    omit_states_groups: bool = False,
    stride: int | None = 1,
    tick_start: int | None = 0,
    tick_end: int | None = -1,
    window_anchor: int | None = None,
    omit_stride_contract: bool = False,
) -> Path:
    """Write a minimal synthetic HDF5 trace exercising every window_loader
    refusal branch on demand (via the keyword toggles above), without
    depending on any real Karr MAT data being present.

    By default writes a complete M4 stride/tick_start/tick_end contract
    (``stride=1``, ``tick_start=0``, ``tick_end=n_ticks - 1``) so existing
    callers that only care about the OTHER refusal branches keep getting a
    contract-complete "good" fixture under the new strict-by-default
    ``load_event_window``. Pass ``omit_stride_contract=True`` (or explicit
    ``None`` values) to exercise the M4 refusal branches themselves.
    """
    if tick_end == -1:
        tick_end = n_ticks - 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(process_name))
        metadata.create_dataset("rng_seed", data=np.array([rng_seed]))
        if tick_offset is not None:
            metadata.create_dataset("tick_offset", data=np.array([tick_offset]))
        if not omit_stride_contract:
            if stride is not None:
                metadata.create_dataset("stride", data=np.array([stride]))
            if tick_start is not None:
                metadata.create_dataset("tick_start", data=np.array([tick_start]))
            if tick_end is not None:
                metadata.create_dataset("tick_end", data=np.array([tick_end]))
            if window_anchor is not None:
                metadata.create_dataset("window_anchor", data=np.array([window_anchor]))

        if omit_states_groups:
            return path

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in observables:
            if observable == missing_observable_group:
                continue
            rows = n_ticks - 1 if observable == truncated_observable else n_ticks
            # Row-vector-per-tick shape (1, rows) so `_cell_series` treats it
            # as a plain numeric array (dtype != object).
            states_before.create_dataset(observable, data=np.zeros((1, rows)))
            states_after.create_dataset(observable, data=np.zeros((1, rows)))
    return path


def test_load_missing_file_refuses_missing_window(tmp_path):
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(tmp_path / "does_not_exist.mat", required_observables=("obsA",))
    assert exc_info.value.reason == "MISSING_WINDOW"


def test_load_trace_without_tick_offset_refuses_not_event_window_trace(tmp_path):
    trace_path = _write_synthetic_trace(tmp_path / "standard.mat", tick_offset=None)
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "NOT_EVENT_WINDOW_TRACE"


def test_load_trace_missing_metadata_group_refuses_not_event_window_trace(tmp_path):
    path = tmp_path / "no_metadata.mat"
    with h5py.File(path, "w") as handle:
        handle.create_group("states_before")
        handle.create_group("states_after")
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(path, required_observables=("obsA",))
    assert exc_info.value.reason == "NOT_EVENT_WINDOW_TRACE"


def test_load_trace_missing_observable_refuses_incomplete_window(tmp_path):
    trace_path = _write_synthetic_trace(tmp_path / "missing_obs.mat", missing_observable_group="obsA")
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"


def test_load_trace_sparse_partial_grid_refuses_incomplete_window(tmp_path):
    """A observable with fewer tick rows than the declared n_ticks (a
    sparse/partial grid) must be refused, not silently truncated or padded
    -- D1's "fully enumerated stride-1 window" requirement."""
    trace_path = _write_synthetic_trace(tmp_path / "sparse.mat", n_ticks=5, truncated_observable="obsA")
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"


def test_load_valid_synthetic_trace_succeeds(tmp_path):
    trace_path = _write_synthetic_trace(
        tmp_path / "good.mat", n_ticks=4, tick_offset=17.0, process_name="Foo", rng_seed=3, observables=("obsA", "obsB")
    )
    window = load_event_window(trace_path, required_observables=("obsA", "obsB"))
    assert window.process_name == "Foo"
    assert window.seed == 3
    assert window.n_ticks == 4
    assert window.tick_offset == 17.0
    assert window.before("obsA", 0).shape == (1,)
    assert window.after("obsB", 3).shape == (1,)
    assert window.stride_contract_ok is True
    assert window.stride_contract_problems == ()


def test_load_trace_missing_stride_key_refuses_incomplete_window(tmp_path):
    trace_path = _write_synthetic_trace(tmp_path / "no_stride.mat", stride=None)
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"
    assert "stride" in str(exc_info.value)


def test_load_trace_missing_tick_start_key_refuses_incomplete_window(tmp_path):
    trace_path = _write_synthetic_trace(tmp_path / "no_tick_start.mat", tick_start=None)
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"
    assert "tick_start" in str(exc_info.value)


def test_load_trace_missing_both_tick_end_and_window_anchor_refuses_incomplete_window(tmp_path):
    trace_path = _write_synthetic_trace(tmp_path / "no_end_or_anchor.mat", tick_end=None, window_anchor=None)
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"
    assert "tick_end" in str(exc_info.value) and "window_anchor" in str(exc_info.value)


def test_load_trace_window_anchor_alone_satisfies_end_clause(tmp_path):
    """`window_anchor` is an acceptable substitute for `tick_end` (`(at
    least one required, 'as applicable')`) -- this must NOT refuse."""
    trace_path = _write_synthetic_trace(tmp_path / "anchor_only.mat", tick_end=None, window_anchor=250)
    window = load_event_window(trace_path, required_observables=("obsA",))
    assert window.stride_contract_ok is True


def test_load_trace_stride_not_one_refuses_incomplete_window(tmp_path):
    """D1 requires a fully-enumerated stride-1 window; stride=2 (or any
    non-1 value) must be refused, never silently accepted as a sparser
    grid."""
    trace_path = _write_synthetic_trace(tmp_path / "stride2.mat", stride=2)
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"
    assert "stride" in str(exc_info.value)


def test_load_trace_missing_stride_contract_non_fatal_when_not_required(tmp_path):
    """`require_stride_contract=False` (the structural-smoke-only escape
    hatch) must never raise for a missing contract -- it must instead
    attach the problems to the returned grid, non-fatally, so callers can
    surface (never hide) the incompleteness."""
    trace_path = _write_synthetic_trace(tmp_path / "no_contract.mat", omit_stride_contract=True)
    window = load_event_window(trace_path, required_observables=("obsA",), require_stride_contract=False)
    assert window.stride_contract_ok is False
    assert len(window.stride_contract_problems) == 3
    assert any("stride" in p for p in window.stride_contract_problems)
    assert any("tick_start" in p for p in window.stride_contract_problems)
    assert any("tick_end" in p for p in window.stride_contract_problems)


def test_classify_trace_dir_recognizes_event_window_and_standard_dirs():
    assert classify_trace_dir(Path("data/x/per_process_traces_v2_event_s000/Foo.mat")) == "event_window"
    assert classify_trace_dir(Path("data/x/per_process_traces_v2_s007/Foo.mat")) == "standard_mid_cycle"
    assert classify_trace_dir(Path("data/x/per_process_traces_v2/Foo.mat")) == "standard_mid_cycle"
    assert classify_trace_dir(Path("data/x/some_other_dir/Foo.mat")) == "unknown"


@pytest.mark.skipif(not _REAL_RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_load_real_ribosome_assembly_seed0_event_trace():
    """M4: the real seed-0 MAT predates the stride/tick_start/tick_end (or
    window_anchor) metadata contract, so this structural-smoke-style load
    must explicitly opt out of the strict default and the returned grid
    must honestly report the contract as incomplete -- it must never be
    silently treated as if it satisfied a real gate's window requirements."""
    observables = ("substrates", "enzymes", "boundEnzymes", "monomers", "complexs", "RNAs")
    window = load_event_window(_REAL_RA_TRACE, required_observables=observables, require_stride_contract=False)
    assert window.process_name == "RibosomeAssembly"
    assert window.seed == 0
    assert window.n_ticks == 100
    assert window.tick_offset == 200.0
    assert window.stride_contract_ok is False
    assert window.stride_contract_problems
    for observable in observables:
        assert window.states_before[observable].shape[0] == 100
        assert window.states_after[observable].shape[0] == 100


def test_load_real_ribosome_assembly_seed0_event_trace_strict_default_refuses_incomplete_window():
    """The flip side of the above: under the new strict-by-default M4
    contract, the same real trace must hard-refuse (never silently PASS
    or silently drop the contract check) unless the caller explicitly
    opts out via `require_stride_contract=False`."""
    if not _REAL_RA_TRACE.exists():
        pytest.skip("Real RibosomeAssembly seed-000 event-window MAT not present locally")
    observables = ("substrates", "enzymes", "boundEnzymes", "monomers", "complexs", "RNAs")
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(_REAL_RA_TRACE, required_observables=observables)
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"


@pytest.mark.skipif(not _REAL_STANDARD_TRACE.exists(), reason="Real standard mid-cycle Translation MAT not present locally")
def test_load_real_standard_mid_cycle_trace_refuses_not_event_window_trace():
    """The critical mid-cycle-trace refusal (requirement 4): a real,
    tracked, standard `per_process_traces_v2_s*` trace must be refused, not
    silently accepted as if it were an event window."""
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(_REAL_STANDARD_TRACE, required_observables=("substrates",))
    assert exc_info.value.reason == "NOT_EVENT_WINDOW_TRACE"
