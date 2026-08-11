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

from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _write_cell_series(handle: h5py.File, group: h5py.Group, name: str, rows: np.ndarray) -> None:
    n_ticks = rows.shape[0]
    refs = np.empty((1, n_ticks), dtype=h5py.special_dtype(ref=h5py.Reference))
    for tick in range(n_ticks):
        dset = handle.create_dataset(f"__data/{group.name.lstrip('/')}/{name}/{tick}", data=rows[tick])
        refs[0, tick] = dset.ref
    group.create_dataset(name, data=refs, dtype=h5py.special_dtype(ref=h5py.Reference))


def _trace_path(root: Path, seed: int) -> Path:
    return maw._seed_trace_path(seed, root)  # noqa: SLF001


def _write_active_window(
    path: Path,
    *,
    seed: int,
    n_ticks: int = maw.REQUIRED_M_TICKS,
    tick_offset: int = 8385,
    trigger_indices_0b: tuple[int, ...] = (22,),
    first_e1_nonzero_tick: int | None = 8264,
    process_name: str = maw.PROCESS_NAME,
    search_max_ticks: int = maw.SEARCH_MAX_TICKS,
    active_window_rule: str = maw.ACTIVE_WINDOW_RULE,
    active_window_rule_version: int = maw.ACTIVE_WINDOW_RULE_VERSION,
) -> Path:
    tick_start = tick_offset + 1
    tick_end = tick_start + n_ticks - 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(process_name))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        metadata.create_dataset("tick_offset", data=np.array([float(tick_offset)]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("tick_end", data=np.array([tick_end]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("active_window_rule", data=_encode_char_metadata(active_window_rule))
        metadata.create_dataset("active_window_rule_version", data=np.array([active_window_rule_version]))
        metadata.create_dataset("active_window_trigger_tick", data=np.array([tick_start]))
        metadata.create_dataset(
            "active_window_trigger_complex_indices_0b",
            data=np.array(trigger_indices_0b, dtype=np.int32).reshape(1, -1),
        )
        metadata.create_dataset("active_window_search_max_ticks", data=np.array([search_max_ticks]))
        metadata.create_dataset(
            "active_window_search_stop_reason",
            data=_encode_char_metadata("first_network2_positive_delta"),
        )
        metadata.create_dataset(
            "active_window_detection_mechanism",
            data=_encode_char_metadata("synthetic unit-test fixture"),
        )
        if first_e1_nonzero_tick is not None:
            metadata.create_dataset("active_window_first_e1_nonzero_tick", data=np.array([first_e1_nonzero_tick]))
        metadata.create_dataset("timestamp", data=_encode_char_metadata("2026-08-12 00:00:00"))

        before_complexs = np.zeros((n_ticks, 24), dtype=np.float64)
        after_complexs = before_complexs.copy()
        for idx in trigger_indices_0b:
            after_complexs[0, idx] = 1.0

        before_substrates = np.zeros((n_ticks, 4), dtype=np.float64)
        after_substrates = before_substrates.copy()
        before_monomers = np.zeros((n_ticks, 3), dtype=np.float64)
        after_monomers = before_monomers.copy()

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        _write_cell_series(handle, states_before, "substrates", before_substrates)
        _write_cell_series(handle, states_after, "substrates", after_substrates)
        _write_cell_series(handle, states_before, "monomers", before_monomers)
        _write_cell_series(handle, states_after, "monomers", after_monomers)
        _write_cell_series(handle, states_before, "complexs", before_complexs)
        _write_cell_series(handle, states_after, "complexs", after_complexs)
    return path


def test_validate_seed_window_accepts_well_formed_active_window(tmp_path: Path) -> None:
    trace_path = _write_active_window(_trace_path(tmp_path, 7), seed=7)

    window = maw.validate_seed_window(7, trace_path)

    assert window.process_name == maw.PROCESS_NAME
    assert window.seed == 7
    assert window.tick_offset == 8385
    assert window.tick_start == 8386
    assert window.trigger_tick == 8386
    assert window.trigger_complex_indices_0b == (22,)


def test_validate_seed_window_rejects_wrong_trigger_metadata(tmp_path: Path) -> None:
    trace_path = _write_active_window(_trace_path(tmp_path, 4), seed=4, trigger_indices_0b=(22,))
    with h5py.File(trace_path, "a") as handle:
        handle["metadata"]["active_window_trigger_complex_indices_0b"][...] = np.array([[23]], dtype=np.int32)

    with pytest.raises(maw.MacromolActiveWindowError, match="does not match the first tick's positive network2 deltas"):
        maw.validate_seed_window(4, trace_path)


def test_validate_seed_window_rejects_non_active_first_tick(tmp_path: Path) -> None:
    trace_path = _write_active_window(_trace_path(tmp_path, 5), seed=5, trigger_indices_0b=(22,))
    with h5py.File(trace_path, "a") as handle:
        ref = handle["states_after/complexs"][0, 0]
        handle[ref][...] = np.zeros((24,), dtype=np.float64)

    with pytest.raises(maw.MacromolActiveWindowError, match="first captured tick does not contain a positive network2 complex delta"):
        maw.validate_seed_window(5, trace_path)


def test_audit_active_window_evidence_flags_duplicates_and_invalid_windows(tmp_path: Path) -> None:
    valid_path = _write_active_window(_trace_path(tmp_path, 0), seed=0, trigger_indices_0b=(22,))
    duplicate_path = _trace_path(tmp_path, 1)
    duplicate_path.parent.mkdir(parents=True, exist_ok=True)
    duplicate_path.write_bytes(valid_path.read_bytes())
    invalid_path = _write_active_window(_trace_path(tmp_path, 2), seed=2, trigger_indices_0b=(22,))
    with h5py.File(invalid_path, "a") as handle:
        handle["metadata"]["active_window_trigger_complex_indices_0b"][...] = np.array([[24]], dtype=np.int32)

    report = maw.audit_active_window_evidence(data_roots=(tmp_path,))

    assert report.status == "INSUFFICIENT_ENSEMBLE"
    assert report.found_seeds == [0]
    assert report.invalid_seeds == [1, 2]
    assert report.missing_seeds[0] == 3
    assert report.deficit == maw.REQUIRED_N_SEEDS - 1
    assert report.duplicate_seeds[0]["seed"] == 1
    assert "extract_macromol_active_window_seeds(1, 49, [1 2]);" in report.resumable_extraction_command
    assert report.cohort_summary is not None
    assert report.cohort_summary["trigger_complex_counts_0b"]["22"] == 1
    assert report.cohort_summary["trigger_complex_counts_0b"]["23"] == 0


def test_cli_writes_json_and_exits_nonzero_for_insufficient_cohort(tmp_path: Path) -> None:
    _write_active_window(_trace_path(tmp_path, 0), seed=0, trigger_indices_0b=(22,))
    out_path = tmp_path / "audit.json"

    code = maw.main(["--data-root", str(tmp_path), "--out", str(out_path)])

    assert code == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["process"] == maw.PROCESS_NAME
    assert payload["status"] == "INSUFFICIENT_ENSEMBLE"
