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

from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.window_loader import (  # noqa: E402
    EventWindowRefused,
    _decode_char_metadata,
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

_REAL_CYTOKINESIS_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s000"
    / "Cytokinesis_4000ticks.mat"
)




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
    onset_tick: int | None = None,
    omit_stride_contract: bool = False,
    observable_values: dict[str, tuple[np.ndarray, np.ndarray]] | None = None,
    non_scalar_observable: str | None = None,
    group_ref_observable: str | None = None,
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

    ``observable_values`` lets a caller override the default all-zeros
    scalar-per-tick payload for one or more observables with explicit
    ``(before_values, after_values)`` 1-D arrays of length ``n_ticks`` --
    used to craft a NaN/non-finite numeric event-observable projection
    deliberately. ``non_scalar_observable`` writes that one observable as a
    2-wide (non-scalar) row per tick instead of a scalar, for the
    require_scalar_finite_observables non-scalar-shape refusal branch.
    ``group_ref_observable`` writes that observable the way real chromosome
    snapshots are stored: a MATLAB cell array of object references to HDF5
    groups, one group per tick.
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
            if onset_tick is not None:
                metadata.create_dataset("onset_tick", data=np.array([onset_tick]))

        if omit_states_groups:
            return path

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in observables:
            if observable == missing_observable_group:
                continue
            rows = n_ticks - 1 if observable == truncated_observable else n_ticks
            if observable_values is not None and observable in observable_values:
                before_vals, after_vals = observable_values[observable]
                states_before.create_dataset(observable, data=np.asarray(before_vals, dtype=float).reshape(1, rows))
                states_after.create_dataset(observable, data=np.asarray(after_vals, dtype=float).reshape(1, rows))
                continue
            if observable == non_scalar_observable:
                # Genuine non-scalar-per-tick data can only be represented in
                # this codebase's HDF5 layout as a MATLAB cell array of
                # object references (one per tick, each pointing at a
                # 2-element vector) -- `_cell_series`'s plain-numeric-array
                # branch always collapses a (1, rows) array to one scalar
                # per tick, so it cannot itself carry non-scalar payloads.
                for section, sink in (("states_before", states_before), ("states_after", states_after)):
                    refs = np.empty((1, rows), dtype=h5py.special_dtype(ref=h5py.Reference))
                    for tick in range(rows):
                        dset = handle.create_dataset(
                            f"__data/{section}/{observable}/{tick}", data=np.array([0.0, 1.0])
                        )
                        refs[0, tick] = dset.ref
                    sink.create_dataset(observable, data=refs, dtype=h5py.special_dtype(ref=h5py.Reference))
                continue
            if observable == group_ref_observable:
                for section, sink in (("states_before", states_before), ("states_after", states_after)):
                    refs = np.empty((1, rows), dtype=h5py.special_dtype(ref=h5py.Reference))
                    for tick in range(rows):
                        payload = handle.create_group(f"__group_payload/{section}/{observable}/{tick}")
                        payload.create_dataset("field_a", data=np.array([tick], dtype=np.int64))
                        payload.create_dataset("field_b", data=np.array([tick, tick + 1], dtype=np.int64))
                        refs[0, tick] = payload.ref
                    sink.create_dataset(observable, data=refs, dtype=h5py.special_dtype(ref=h5py.Reference))
                continue
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
    """Canary-A closeout: the real seed-0 MAT was regenerated with a
    complete M4 stride/tick_start/tick_end metadata contract (stride=1,
    tick_start=201, tick_end=300 -- absolute ticks; tick_offset=200 is the
    burn-in tick COUNT preceding capture, so the first captured tick is
    tick_offset + 1 = 201, per the M4 onset/completion split). The
    relaxed (`require_stride_contract=False`) structural-smoke-style load
    must honestly report the contract as complete now -- it must never
    silently claim completeness that isn't real, but it must also never
    keep reporting a stale incompleteness once the contract genuinely is
    satisfied."""
    observables = ("substrates", "enzymes", "boundEnzymes", "monomers", "complexs", "RNAs")
    window = load_event_window(_REAL_RA_TRACE, required_observables=observables, require_stride_contract=False)
    assert window.process_name == "RibosomeAssembly"
    assert window.seed == 0
    assert window.n_ticks == 100
    assert window.tick_offset == 200.0
    assert window.tick_start == 201
    assert window.tick_end == 300
    assert window.stride_contract_ok is True
    assert window.stride_contract_problems == ()
    for observable in observables:
        assert window.states_before[observable].shape[0] == 100
        assert window.states_after[observable].shape[0] == 100


def test_load_real_ribosome_assembly_seed0_event_trace_strict_default_now_succeeds():
    """Canary-A closeout, flip side of the above: under the strict-by-
    default M4 contract, the regenerated real trace must now load
    successfully (never hard-refuse) -- proving the M4 gap that used to
    force every real-data caller through `require_stride_contract=False`
    is closed for this file. This does NOT make the file gate-eligible:
    it is still only 1 of the registry's required 50 ensemble seeds (see
    `tests/scripts/test_l2_event_ribosome_assembly_gate.py::
    test_gate_adapter_cannot_reach_a_computed_verdict_on_real_seed0`,
    which proves the strict load succeeding on this file and the
    ensemble-size refusal are two independent facts). Synthetic
    fixtures elsewhere in this file (`omit_stride_contract=True` and the
    other M4-refusal branches above) retain full, real-data-independent
    coverage of the strict-refusal path itself -- that refusal behavior
    is unchanged and is not what this test is about."""
    if not _REAL_RA_TRACE.exists():
        pytest.skip("Real RibosomeAssembly seed-000 event-window MAT not present locally")
    observables = ("substrates", "enzymes", "boundEnzymes", "monomers", "complexs", "RNAs")
    window = load_event_window(_REAL_RA_TRACE, required_observables=observables)
    assert window.stride_contract_ok is True
    assert window.tick_start == 201
    assert window.tick_end == 300


@pytest.mark.skipif(not _REAL_STANDARD_TRACE.exists(), reason="Real standard mid-cycle Translation MAT not present locally")
def test_load_real_standard_mid_cycle_trace_refuses_not_event_window_trace():
    """The critical mid-cycle-trace refusal (requirement 4): a real,
    tracked, standard `per_process_traces_v2_s*` trace must be refused, not
    silently accepted as if it were an event window."""
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(_REAL_STANDARD_TRACE, required_observables=("substrates",))
    assert exc_info.value.reason == "NOT_EVENT_WINDOW_TRACE"


@pytest.mark.skipif(not _REAL_CYTOKINESIS_TRACE.exists(), reason="Real Cytokinesis seed-000 event-window MAT not present locally")
def test_load_real_cytokinesis_seed0_event_trace_anchor_completeness():
    """Canary D closeout: the real seed-0 anchor-mode MAT produced after the
    mnrnd shim repair must satisfy the full M4 contract under the STRICT
    default (`require_stride_contract` defaults to True) -- stride=1, an
    absolute `tick_start`, a `window_anchor` (completion/capture boundary),
    and an `onset_tick` (contraction-onset timing anchor) with
    `tick_start <= onset_tick < window_anchor`, per the ratified onset =
    first strict `pinchedDiameter` decrease / completion = first
    positive->zero transition definition. Must never pass on a truncated or
    synthetically-flagged-complete search.

    NOTE on n_ticks=4000 (not the catalog's `M_ticks: 100` default): the
    first Canary D retry (n_ticks=100, matching the catalog default) failed
    closed -- the real seed-0 trajectory's onset-to-completion span is
    ~3872 ticks, far longer than a 100-tick capture buffer can hold. This
    is a real finding (the catalog's `M_ticks: 100` "default" rationale is
    not big enough to contain a real single-firing Cytokinesis anchor
    window), not a threshold relaxation: n_ticks is a capture-buffer size,
    the onset/completion detection and the `onset_tick >= tick_start`
    refusal are completely unchanged and remained fail-closed throughout."""
    observables = (
        "substrates",
        "enzymes",
        "boundEnzymes",
        "pinchedDiameter",
        "ftsZRing_numEdgesOneStraight",
        "ftsZRing_numEdgesTwoStraight",
        "ftsZRing_numEdgesTwoBent",
        "ftsZRing_numResidualBent",
        "chromosome_segregated",
    )
    window = load_event_window(_REAL_CYTOKINESIS_TRACE, required_observables=observables)
    assert window.process_name == "Cytokinesis"
    assert window.seed == 0
    assert window.n_ticks == 4000
    assert window.stride_contract_ok is True
    assert window.stride_contract_problems == ()
    assert window.window_anchor is not None
    assert window.onset_tick is not None
    assert window.tick_start <= window.onset_tick < window.window_anchor
    for observable in observables:
        assert window.states_before[observable].shape[0] == 4000
        assert window.states_after[observable].shape[0] == 4000



@pytest.mark.skipif(not _REAL_CYTOKINESIS_TRACE.exists(), reason="Real Cytokinesis seed-000 event-window MAT not present locally")
def test_load_real_cytokinesis_seed0_event_trace_bound_to_genuine_mnrnd_provider():
    """A regenerated trace must bind the genuine local MathWorks provider."""
    with h5py.File(_REAL_CYTOKINESIS_TRACE, "r") as handle:
        metadata = handle["metadata"]
        if "mnrnd_provider_kind" not in metadata:
            pytest.skip("local Cytokinesis trace is legacy shim-bound and awaits regeneration")
        provider_kind = _decode_char_metadata(np.asarray(metadata["mnrnd_provider_kind"][()]))
        provider_release = _decode_char_metadata(np.asarray(metadata["mnrnd_provider_matlab_release"][()]))
        provider_version = _decode_char_metadata(np.asarray(metadata["mnrnd_provider_toolbox_version"][()]))
        provider_path = _decode_char_metadata(
            np.asarray(metadata["mnrnd_provider_path_relative_to_matlabroot"][()])
        )
        provider_sha256 = _decode_char_metadata(np.asarray(metadata["mnrnd_provider_sha256"][()]))
        projection_version = int(np.asarray(metadata["event_observable_projection_version"][()]).reshape(-1)[0])
    expected = launcher.current_genuine_mnrnd_provider()
    assert provider_kind == expected["kind"]
    assert provider_release == expected["matlab_release"]
    assert provider_version == expected["toolbox_version"]
    assert provider_path == expected["provider_path_relative_to_matlabroot"]
    assert provider_sha256 == expected["sha256_lf_normalized"]
    assert projection_version == 2


# ---------------------------------------------------------------------------
# M4 correction: onset_tick (timing anchor) vs window_anchor (capture
# boundary), single absolute tick coordinate system, and the numeric
# event-observable projection's scalar/finite guarantee.
# ---------------------------------------------------------------------------


def test_window_grid_exposes_tick_bounds_and_onset_tick(tmp_path):
    trace_path = _write_synthetic_trace(
        tmp_path / "anchor_full.mat",
        n_ticks=4,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=997,
    )
    window = load_event_window(trace_path, required_observables=("obsA",))
    assert window.tick_start == 996
    assert window.window_anchor == 999
    assert window.onset_tick == 997
    assert window.completion_tick == 999  # derived alias, not a second persisted key
    assert window.absolute_tick(0) == 996
    assert window.absolute_tick(3) == 999


def test_window_grid_absolute_tick_raises_without_tick_start(tmp_path):
    trace_path = _write_synthetic_trace(tmp_path / "pre_m4.mat", omit_stride_contract=True)
    window = load_event_window(trace_path, required_observables=("obsA",), require_stride_contract=False)
    assert window.tick_start is None
    with pytest.raises(ValueError):
        window.absolute_tick(0)


def test_load_trace_onset_tick_without_window_anchor_refuses_incomplete_window(tmp_path):
    """onset_tick (TIMING anchor) with no window_anchor/completion (CAPTURE
    boundary) at all is not a valid anchor window -- the pairing is
    mandatory."""
    trace_path = _write_synthetic_trace(
        tmp_path / "onset_no_anchor.mat", tick_end=None, window_anchor=None, onset_tick=5
    )
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"


def test_load_trace_onset_tick_before_tick_start_refuses_incomplete_window(tmp_path):
    """onset_tick must fall inside the captured window: onset < tick_start
    (an onset the extraction never actually captured) must be refused."""
    trace_path = _write_synthetic_trace(
        tmp_path / "onset_before_start.mat",
        n_ticks=4,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=990,
    )
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"
    assert "onset_tick" in str(exc_info.value)


def test_load_trace_onset_tick_at_or_after_completion_refuses_incomplete_window(tmp_path):
    """A fabricated/immediate anchor -- onset at or after the completion
    tick -- is never a real observed transition-then-completion interval
    and must be refused."""
    trace_path = _write_synthetic_trace(
        tmp_path / "onset_after_completion.mat",
        n_ticks=4,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
        onset_tick=999,
    )
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("obsA",))
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"
    assert "onset_tick" in str(exc_info.value)


def test_load_trace_scalar_finite_observable_ok(tmp_path):
    trace_path = _write_synthetic_trace(
        tmp_path / "scalar_ok.mat",
        n_ticks=3,
        observables=("pinchedDiameter",),
        observable_values={"pinchedDiameter": ([2.0, 1.0, 0.0], [1.0, 0.0, 0.0])},
    )
    window = load_event_window(
        trace_path,
        required_observables=("pinchedDiameter",),
        require_scalar_finite_observables=("pinchedDiameter",),
    )
    assert window.before("pinchedDiameter", 0).shape == (1,)


def test_load_trace_non_scalar_required_finite_observable_refuses_incomplete_window(tmp_path):
    trace_path = _write_synthetic_trace(
        tmp_path / "non_scalar.mat",
        n_ticks=3,
        observables=("pinchedDiameter",),
        non_scalar_observable="pinchedDiameter",
    )
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(
            trace_path,
            required_observables=("pinchedDiameter",),
            require_scalar_finite_observables=("pinchedDiameter",),
        )
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"


def test_load_trace_nan_required_finite_observable_refuses_incomplete_window(tmp_path):
    """A NaN in a numeric event-observable projection field must be
    refused -- a non-finite value can never support an onset/completion
    timing claim."""
    trace_path = _write_synthetic_trace(
        tmp_path / "nan_obs.mat",
        n_ticks=3,
        observables=("pinchedDiameter",),
        observable_values={"pinchedDiameter": ([2.0, float("nan"), 0.0], [1.0, 0.0, 0.0])},
    )
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(
            trace_path,
            required_observables=("pinchedDiameter",),
            require_scalar_finite_observables=("pinchedDiameter",),
        )
    assert exc_info.value.reason == "INCOMPLETE_WINDOW"


def test_load_event_window_rejects_scalar_finite_observables_not_subset_of_required():
    with pytest.raises(ValueError):
        load_event_window(
            Path("does_not_matter.mat"),
            required_observables=("obsA",),
            require_scalar_finite_observables=("obsB",),
        )


def test_load_trace_group_ref_observable_round_trip(tmp_path):
    """Real chromosome snapshots are cell entries that point at HDF5 groups,
    not numeric datasets. The loader must materialize those payloads before
    closing the file so validation callers can safely require
    ``required_observables=('chromosome', ...)`` on real traces."""
    trace_path = _write_synthetic_trace(
        tmp_path / "group_ref.mat",
        observables=("chromosome", "obsA"),
        group_ref_observable="chromosome",
    )
    window = load_event_window(trace_path, required_observables=("chromosome", "obsA"))
    assert window.states_before["chromosome"].shape == (3, 1)
    assert window.states_after["chromosome"].shape == (3, 1)
    before_tick0 = window.before("chromosome", 0)[0]
    after_tick2 = window.after("chromosome", 2)[0]
    assert isinstance(before_tick0, dict)
    assert before_tick0["field_a"].reshape(-1).tolist() == [0]
    assert before_tick0["field_b"].reshape(-1).tolist() == [0, 1]
    assert isinstance(after_tick2, dict)
    assert after_tick2["field_a"].reshape(-1).tolist() == [2]
    assert after_tick2["field_b"].reshape(-1).tolist() == [2, 3]


def test_load_trace_chromosome_segregated_boolean_observable_round_trip(tmp_path):
    """MATLAB-free synthetic HDF5 round-trip (performance/sufficiency patch):
    ``chromosome_segregated`` is a flattened `logical` scalar (`Chromosome.
    segregated`, the exact -- and only -- chromosome-state field
    Cytokinesis.evolveState() itself reads), not a numeric diameter/ring
    witness, but window_loader's require_scalar_finite_observables gauntlet
    must accept it exactly like any other scalar-per-tick observable: a
    false->true transition encoded as 0.0/1.0 (MATLAB `logical` values
    materialize as a 0/1-valued numeric HDF5 dataset, same as any other
    scalar-per-tick projection field) is present, scalar-shaped, and finite
    for every tick."""
    trace_path = _write_synthetic_trace(
        tmp_path / "chromosome_segregated_ok.mat",
        n_ticks=3,
        observables=("chromosome_segregated",),
        observable_values={"chromosome_segregated": ([0.0, 0.0, 1.0], [0.0, 1.0, 1.0])},
    )
    window = load_event_window(
        trace_path,
        required_observables=("chromosome_segregated",),
        require_scalar_finite_observables=("chromosome_segregated",),
    )
    assert window.before("chromosome_segregated", 0).shape == (1,)
    before_series = np.array([window.before("chromosome_segregated", t)[0] for t in range(3)])
    after_series = np.array([window.after("chromosome_segregated", t)[0] for t in range(3)])
    np.testing.assert_array_equal(before_series, [0.0, 0.0, 1.0])
    np.testing.assert_array_equal(after_series, [0.0, 1.0, 1.0])


def test_load_trace_cytokinesis_diameter_anchor_shaped_round_trip(tmp_path):
    """MATLAB-free synthetic HDF5 round-trip exercising the FULL
    signal_kind='diameter_decrease' flattened observable set together
    (pinchedDiameter + the four FtsZRing witnesses + chromosome_segregated),
    proving the loader accepts the exact shape
    ``merge_event_observables()``/CYTOKINESIS_SCALAR_FINITE_OBSERVABLES now
    produce/require -- never the full sparse `chromosome` object (which
    this fixture never writes at all)."""
    observables = (
        "pinchedDiameter",
        "ftsZRing_numEdgesOneStraight",
        "ftsZRing_numEdgesTwoStraight",
        "ftsZRing_numEdgesTwoBent",
        "ftsZRing_numResidualBent",
        "chromosome_segregated",
    )
    trace_path = _write_synthetic_trace(
        tmp_path / "cytokinesis_anchor_ok.mat",
        n_ticks=3,
        observables=observables,
        observable_values={obs: ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]) for obs in observables},
    )
    window = load_event_window(
        trace_path,
        required_observables=observables,
        require_scalar_finite_observables=observables,
    )
    for obs in observables:
        assert window.before(obs, 0).shape == (1,)
    # The full sparse chromosome object was never written to this
    # MATLAB-free fixture at all -- confirms a loader that only ever reads
    # required_observables never needs it, chromosome_segregated is enough.
    with h5py.File(trace_path, "r") as handle:
        assert "chromosome" not in handle["states_before"]
        assert "chromosome" not in handle["states_after"]
