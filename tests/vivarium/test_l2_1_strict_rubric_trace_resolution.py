from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import h5py
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import test_l2_1_strict_rubric as rubric  # noqa: E402

_PROCESS = "TranscriptionalRegulation"
_MANIFEST_PATH = _REPO / "docs" / "phase_f" / "l2_1" / "L21_ACTIVE_WINDOWS_MANIFEST.json"
_ACTIVE_TRACE_REL = Path(
    "data/m1_sources/karr_native/per_process_traces_v2_event_s000/"
    "TranscriptionalRegulation_4000ticks.mat"
)
_ACTIVE_TRACE_SHA256 = "73fc1d9710e2a98f61221d51a80cdbc490fb6d44db4ea95853414048c9fc7aa2"


def _write_txreg_manifest(tmp_path: Path, *, mutate) -> Path:
    payload = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    row = next(copy.deepcopy(item) for item in payload["rows"] if item["process"] == _PROCESS)
    mutate(row)
    payload["rows"] = [row]
    path = tmp_path / "txreg_active_window_manifest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_stale_canonical_trace(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.create_group("states_before")
        handle.create_group("states_after")
        for group in ("states_before", "states_after"):
            for observable in ("substrates", "enzymes", "boundEnzymes"):
                handle[group].create_dataset(observable, data=[[0]])


def test_txreg_selects_hash_bound_active_trace_with_required_fields() -> None:
    trace_path, resolution = rubric._resolve_strict_rubric_trace_path(_PROCESS)

    assert resolution is not None
    assert trace_path == (_REPO / _ACTIVE_TRACE_REL).resolve()
    assert resolution["source_recorded_sha256"] == _ACTIVE_TRACE_SHA256
    assert resolution["source_actual_sha256"] == _ACTIVE_TRACE_SHA256
    assert hashlib.sha256(trace_path.read_bytes()).hexdigest() == _ACTIVE_TRACE_SHA256

    with h5py.File(trace_path, "r") as handle:
        for group in ("states_before", "states_after"):
            assert "tfBoundPromoters" in handle[group]
            assert "boundTFs" in handle[group]


def test_stale_canonical_trace_cannot_win_over_active_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_path = tmp_path / "TranscriptionalRegulation_100ticks.mat"
    _write_stale_canonical_trace(stale_path)
    monkeypatch.setattr(rubric, "resolve_trace_path", lambda _name: stale_path)

    trace_path, resolution = rubric._resolve_strict_rubric_trace_path(_PROCESS)

    assert resolution is not None
    assert trace_path != stale_path
    assert trace_path == (_REPO / _ACTIVE_TRACE_REL).resolve()


def test_manifest_hash_drift_raises_instead_of_returning_error_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_path = tmp_path / "TranscriptionalRegulation_100ticks.mat"
    _write_stale_canonical_trace(stale_path)
    monkeypatch.setattr(rubric, "resolve_trace_path", lambda _name: stale_path)
    manifest_path = _write_txreg_manifest(
        tmp_path,
        mutate=lambda row: row["source"].update({"sha256": "0" * 64}),
    )

    with pytest.raises(rubric.StrictRubricTraceResolutionError, match="sha256 mismatch"):
        rubric._classify(_PROCESS, active_window_manifest=manifest_path)


def test_manifest_path_drift_to_stale_trace_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_path = tmp_path / "TranscriptionalRegulation_100ticks.mat"
    _write_stale_canonical_trace(stale_path)
    monkeypatch.setattr(rubric, "resolve_trace_path", lambda _name: stale_path)
    manifest_path = _write_txreg_manifest(
        tmp_path,
        mutate=lambda row: row["source"].update({"path": str(stale_path)}),
    )

    with pytest.raises(rubric.StrictRubricTraceResolutionError, match="sha256 mismatch"):
        rubric._classify(_PROCESS, active_window_manifest=manifest_path)


def test_manifest_classification_drift_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_path = tmp_path / "TranscriptionalRegulation_100ticks.mat"
    _write_stale_canonical_trace(stale_path)
    monkeypatch.setattr(rubric, "resolve_trace_path", lambda _name: stale_path)
    manifest_path = _write_txreg_manifest(
        tmp_path,
        mutate=lambda row: row.update({"classification": "CODE_GAP"}),
    )

    with pytest.raises(
        rubric.StrictRubricTraceResolutionError,
        match="not 'EXISTING_WINDOW_PASS'",
    ):
        rubric._classify(_PROCESS, active_window_manifest=manifest_path)


@pytest.mark.parametrize(
    "process_name",
    sorted(set(rubric._PROCESS_SPECS).difference({_PROCESS})),
)
def test_schema_complete_processes_keep_existing_trace_resolution(
    process_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_path = tmp_path / f"{process_name}_100ticks.mat"
    monkeypatch.setattr(rubric, "resolve_trace_path", lambda _name: canonical_path)
    monkeypatch.setattr(
        rubric,
        "_missing_required_trace_observables",
        lambda _path, _observables: (),
    )

    def fail_if_manifest_is_consulted(*_args, **_kwargs):
        raise AssertionError("schema-complete canonical traces must keep the existing resolver")

    monkeypatch.setattr(
        rubric,
        "resolve_active_window_manifest_source",
        fail_if_manifest_is_consulted,
    )

    trace_path, resolution = rubric._resolve_strict_rubric_trace_path(process_name)
    assert trace_path == canonical_path
    assert resolution is None
