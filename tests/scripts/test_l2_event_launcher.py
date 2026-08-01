"""Unit tests for `scripts/l2_event/launcher.py` (MATLAB-free planning core
and command builder for the M4 fixed/anchor event-window extractor
contract, docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md).

No MATLAB is invoked anywhere in this file. Every trace fixture is a small
synthetic HDF5 file written directly with h5py (matching the shape
`tests/scripts/test_l2_event_window_loader.py` already exercises the
loader with), never a real Karr oracle trace read for its numeric content
-- FIX_TEMPLATE_L2_REPLAY Rule 8 (no oracle reads). Two inversions this
file specifically guards against (Slot 1 pre-mortem):

* A sparse/firing-only grid (stride != 1, or a trace with only firing-tick
  metadata) must never be silently accepted as `skip_valid` --
  `test_plan_regenerate_invalid_for_stride_not_one` and
  `test_plan_regenerate_invalid_for_pre_m4_trace_missing_stride_contract`.
* A trace produced for a *different* window_contract (or a plain standard
  mid-cycle trace) sitting at the same event-window path must never be
  silently reused as if it satisfied the newly requested extraction (the
  "duplicate existing extraction" failure mode) --
  `test_plan_regenerate_invalid_for_window_contract_kind_mismatch` and
  `test_plan_regenerate_invalid_for_standard_mid_cycle_trace_present_at_event_path`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.window_loader import load_event_window  # noqa: E402


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _write_event_window_fixture(
    path: Path,
    *,
    process_name: str,
    seed: int,
    n_ticks: int = 4,
    tick_offset: float | None = 0.0,
    stride: int | None = 1,
    tick_start: int | None = 0,
    tick_end: int | None = -1,
    window_anchor: int | None = None,
    observables: tuple[str, ...] = (),
) -> Path:
    """Write a minimal synthetic event-window trace: a `metadata` group
    plus empty `states_before`/`states_after` groups (optionally with a
    handful of plain-numeric-array observable datasets). Mirrors the shape
    `test_l2_event_window_loader.py`'s `_write_synthetic_trace` uses, kept
    local/independent here on purpose (this file's fixtures are launcher-
    planning-focused, not loader-refusal-gauntlet-focused).
    """
    if tick_end == -1:
        tick_end = n_ticks - 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(process_name))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        if tick_offset is not None:
            metadata.create_dataset("tick_offset", data=np.array([tick_offset]))
        if stride is not None:
            metadata.create_dataset("stride", data=np.array([stride]))
        if tick_start is not None:
            metadata.create_dataset("tick_start", data=np.array([tick_start]))
        if tick_end is not None:
            metadata.create_dataset("tick_end", data=np.array([tick_end]))
        if window_anchor is not None:
            metadata.create_dataset("window_anchor", data=np.array([window_anchor]))

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in observables:
            states_before.create_dataset(observable, data=np.zeros((1, n_ticks)))
            states_after.create_dataset(observable, data=np.zeros((1, n_ticks)))
    return path


# ---------------------------------------------------------------------------
# WindowSpec construction / config-time error semantics
# ---------------------------------------------------------------------------


def test_fixed_window_spec_rejects_negative_tick_offset():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=-1)


def test_fixed_window_spec_rejects_zero_n_ticks():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=0)


def test_anchor_window_spec_rejects_max_search_ticks_shorter_than_n_ticks():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(process="Cytokinesis", seed=1, n_ticks=100, max_search_ticks=10)


def test_anchor_window_spec_rejects_empty_signal_property():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher.AnchorWindowSpec(process="Cytokinesis", seed=1, signal_property="")


def test_spec_from_dict_rejects_unknown_window_contract():
    with pytest.raises(launcher.WindowContractConfigError):
        launcher._spec_from_dict({"process": "X", "seed": 1, "window_contract": "sparse"})


def test_spec_from_dict_round_trips_fixed_and_anchor():
    fixed = launcher._spec_from_dict(
        {"process": "RibosomeAssembly", "seed": 3, "window_contract": "fixed", "tick_offset": 200}
    )
    assert isinstance(fixed, launcher.FixedWindowSpec)
    assert fixed.tick_offset == 200

    anchor = launcher._spec_from_dict({"process": "Cytokinesis", "seed": 3, "window_contract": "anchor"})
    assert isinstance(anchor, launcher.AnchorWindowSpec)
    assert anchor.signal_property == launcher.DEFAULT_ANCHOR_SIGNAL_PROPERTY


# ---------------------------------------------------------------------------
# Output path / layout
# ---------------------------------------------------------------------------


def test_event_window_output_dir_uses_event_suffix(tmp_path):
    out_dir = launcher.event_window_output_dir(7, karr_native_root=tmp_path)
    assert out_dir.name == "per_process_traces_v2_event_s007"
    assert "per_process_traces_v2_event_s007" in str(out_dir)


def test_event_window_mat_path_matches_contract_layout(tmp_path):
    path = launcher.event_window_mat_path("RibosomeAssembly", 3, n_ticks=100, karr_native_root=tmp_path)
    assert path == tmp_path / "per_process_traces_v2_event_s003" / "RibosomeAssembly_100ticks.mat"


# ---------------------------------------------------------------------------
# build_matlab_command
# ---------------------------------------------------------------------------


def test_build_matlab_command_fixed_window_writes_stride1_contract_call():
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=3, tick_offset=200, n_ticks=100)
    command = launcher.build_matlab_command(spec)
    assert "per_process_traces_v2_event_s003" in command
    assert "'RibosomeAssembly'" in command
    assert "uint32(3)" in command
    assert ", 200, 'fixed');" in command
    assert "'anchor'" not in command


def test_build_matlab_command_anchor_window_never_supplies_tick_offset():
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=7, n_ticks=50)
    command = launcher.build_matlab_command(spec)
    assert "per_process_traces_v2_event_s007" in command
    assert "'Cytokinesis'" in command
    assert "uint32(7), [], 'anchor'" in command
    assert "max_search_ticks', 50000" in command
    assert "signal_property', 'geometry'" in command
    assert "signal_field', 'pinched'" in command
    assert "'fixed'" not in command


def test_build_matlab_command_is_diary_wrapped_when_log_given():
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200)
    command = launcher.build_matlab_command(spec, log_relpath="artifacts/seed001.log")
    assert "diary('artifacts/seed001.log')" in command
    assert "diary off" in command
    assert "try;" in command and "catch err;" in command


def test_build_matlab_command_custom_anchor_signal_is_reflected():
    spec = launcher.AnchorWindowSpec(
        process="FtsZPolymerization", seed=2, n_ticks=20, signal_property="ftsZRing", signal_field="numResidualBent"
    )
    command = launcher.build_matlab_command(spec)
    assert "signal_property', 'ftsZRing'" in command
    assert "signal_field', 'numResidualBent'" in command


# ---------------------------------------------------------------------------
# validate_existing_event_window / plan_event_window_extraction
# ---------------------------------------------------------------------------


def test_plan_missing_file_is_generate_missing(tmp_path):
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4)
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "generate_missing"
    assert len(plan.jobs) == 1
    assert plan.jobs[0].window_contract == "fixed"


def test_plan_skip_valid_for_contract_complete_fixed_fixture(tmp_path):
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4)
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=1,
        n_ticks=4,
        tick_offset=200.0,
        stride=1,
        tick_start=200,
        tick_end=203,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "skip_valid"
    assert plan.decisions[0].reason is None
    assert len(plan.jobs) == 0


def test_plan_skip_valid_for_contract_complete_anchor_fixture(tmp_path):
    spec = launcher.AnchorWindowSpec(process="Cytokinesis", seed=9, n_ticks=4)
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=9,
        n_ticks=4,
        tick_offset=996.0,
        stride=1,
        tick_start=996,
        tick_end=None,
        window_anchor=999,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "skip_valid"
    assert len(plan.jobs) == 0


def test_plan_regenerate_invalid_for_pre_m4_trace_missing_stride_contract(tmp_path):
    """The two real pre-M4 traces on disk today (RibosomeAssembly/RNAModification
    seed 000) carry tick_offset but no stride/tick_start/tick_end -- this must
    be `regenerate_invalid`, never `skip_valid`."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=0, tick_offset=200, n_ticks=4)
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=0,
        n_ticks=4,
        tick_offset=200.0,
        stride=None,
        tick_start=None,
        tick_end=None,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "INCOMPLETE_WINDOW" in plan.decisions[0].reason
    assert len(plan.jobs) == 1


def test_plan_regenerate_invalid_for_stride_not_one(tmp_path):
    """Inversion guard: a sparse (stride=2) grid must never be silently
    accepted as satisfying a stride-1 fixed-window request."""
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=2, tick_offset=200, n_ticks=4)
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=2,
        n_ticks=4,
        tick_offset=200.0,
        stride=2,
        tick_start=200,
        tick_end=203,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "stride" in plan.decisions[0].reason


def test_plan_regenerate_invalid_for_window_contract_kind_mismatch(tmp_path):
    """Inversion guard ('duplicate existing extraction'): an on-disk trace
    produced as an 'anchor' window (carries window_anchor, no tick_end) must
    not be silently reused when the caller now requests a 'fixed' window at
    the same (process, seed) path, and vice versa."""
    spec = launcher.FixedWindowSpec(process="Cytokinesis", seed=5, tick_offset=950, n_ticks=4)
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=5,
        n_ticks=4,
        tick_offset=950.0,
        stride=1,
        tick_start=950,
        tick_end=None,
        window_anchor=953,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "window kind" in plan.decisions[0].reason


def test_plan_regenerate_invalid_for_standard_mid_cycle_trace_present_at_event_path(tmp_path):
    """Inversion guard: a plain standard mid-cycle trace (no tick_offset at
    all -- window_loader's NOT_EVENT_WINDOW_TRACE case) sitting at the
    event-window path must never be treated as satisfying an event-window
    request."""
    spec = launcher.FixedWindowSpec(process="Translation", seed=1, tick_offset=0, n_ticks=4)
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path,
        process_name="Translation",
        seed=1,
        n_ticks=4,
        tick_offset=None,
        stride=None,
        tick_start=None,
        tick_end=None,
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path)
    assert plan.decisions[0].action == "regenerate_invalid"
    assert "NOT_EVENT_WINDOW_TRACE" in plan.decisions[0].reason


def test_plan_no_validate_mode_skips_without_checking_content(tmp_path):
    spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4)
    path = launcher.mat_path_for(spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        path, process_name="WRONG", seed=99, n_ticks=4, stride=None, tick_start=None, tick_end=None
    )
    plan = launcher.plan_event_window_extraction([spec], karr_native_root=tmp_path, validate_existing=False)
    assert plan.decisions[0].action == "skip_valid"
    assert len(plan.jobs) == 0


def test_apply_invalidations_deletes_only_regenerate_invalid_files(tmp_path):
    bad_spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=2, tick_offset=200, n_ticks=4)
    bad_path = launcher.mat_path_for(bad_spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        bad_path, process_name="RibosomeAssembly", seed=2, n_ticks=4, tick_offset=200.0, stride=2, tick_start=200, tick_end=203
    )

    good_spec = launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4)
    good_path = launcher.mat_path_for(good_spec, karr_native_root=tmp_path)
    _write_event_window_fixture(
        good_path, process_name="RibosomeAssembly", seed=1, n_ticks=4, tick_offset=200.0, stride=1, tick_start=200, tick_end=203
    )

    plan = launcher.plan_event_window_extraction([bad_spec, good_spec], karr_native_root=tmp_path)
    deleted = launcher.apply_invalidations(plan)

    assert deleted == [str(bad_path)]
    assert not bad_path.exists()
    assert good_path.exists()


def test_plan_to_dict_is_json_serializable(tmp_path):
    specs = [
        launcher.FixedWindowSpec(process="RibosomeAssembly", seed=1, tick_offset=200, n_ticks=4),
        launcher.AnchorWindowSpec(process="Cytokinesis", seed=1, n_ticks=4),
    ]
    plan = launcher.plan_event_window_extraction(specs, karr_native_root=tmp_path)
    payload = json.dumps(plan.to_dict())
    reloaded = json.loads(payload)
    assert len(reloaded["jobs"]) == 2
    assert len(reloaded["decisions"]) == 2


# ---------------------------------------------------------------------------
# Round-trip: the extractor's designed metadata shape is loader-compliant
# ---------------------------------------------------------------------------


def test_fixed_window_extractor_metadata_shape_is_accepted_by_loader_strict_default(tmp_path):
    """Proves (without running MATLAB) that the metadata
    `extract_per_process_traces_v2.m`'s window_contract='fixed' branch is
    designed to write -- stride=1, tick_start=tick_offset,
    tick_end=tick_offset+n_ticks-1 -- satisfies window_loader's default
    require_stride_contract=True gauntlet."""
    path = tmp_path / "per_process_traces_v2_event_s003" / "RibosomeAssembly_100ticks.mat"
    tick_offset = 200
    n_ticks = 100
    _write_event_window_fixture(
        path,
        process_name="RibosomeAssembly",
        seed=3,
        n_ticks=n_ticks,
        tick_offset=float(tick_offset),
        stride=1,
        tick_start=tick_offset,
        tick_end=tick_offset + n_ticks - 1,
        observables=("substrates",),
    )
    window = load_event_window(path, required_observables=("substrates",))
    assert window.stride_contract_ok is True
    assert window.n_ticks == n_ticks
    assert window.tick_offset == tick_offset


def test_anchor_window_extractor_metadata_shape_is_accepted_by_loader_strict_default(tmp_path):
    """Same proof for window_contract='anchor': stride=1,
    tick_start=discovered anchor - n_ticks + 1, window_anchor=discovered
    anchor tick (no tick_end)."""
    path = tmp_path / "per_process_traces_v2_event_s009" / "Cytokinesis_50ticks.mat"
    n_ticks = 50
    anchor_tick = 27_483
    tick_start = anchor_tick - n_ticks + 1
    _write_event_window_fixture(
        path,
        process_name="Cytokinesis",
        seed=9,
        n_ticks=n_ticks,
        tick_offset=float(tick_start),
        stride=1,
        tick_start=tick_start,
        tick_end=None,
        window_anchor=anchor_tick,
        observables=("chromosome",),
    )
    window = load_event_window(path, required_observables=("chromosome",))
    assert window.stride_contract_ok is True
    assert window.n_ticks == n_ticks
    assert window.tick_offset == tick_start


# ---------------------------------------------------------------------------
# CLI (public path)
# ---------------------------------------------------------------------------


def test_cli_plan_subcommand_writes_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(
        json.dumps(
            [
                {"process": "RibosomeAssembly", "seed": 1, "window_contract": "fixed", "tick_offset": 200, "n_ticks": 4},
                {"process": "Cytokinesis", "seed": 1, "window_contract": "anchor", "n_ticks": 4},
            ]
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "plan.json"
    rc = launcher.main(["plan", "--specs", str(specs_path), "--out", str(out_path)])
    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(payload["jobs"]) == 2
    assert payload["deleted_invalid_files"] == []
