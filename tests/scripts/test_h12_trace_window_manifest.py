"""Tests for the opt-in per-seed trace-window manifest support in
`scripts/l22_evidence/h12.py`.

These use small synthetic HDF5 traces written directly with `h5py` so the
manifest-backed slice loader, `run_h12` integration, and CLI plumbing are
verified without depending on any real MATLAB/Karr trace population being
present in the current worktree.
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

from scripts.l22_evidence import h12  # noqa: E402


def _write_trace(path: Path, *, before_values: list[float], after_values: list[float], seed: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_ticks = len(before_values)
    assert len(after_values) == n_ticks
    with h5py.File(path, "w") as handle:
        for section, values in (("states_before", before_values), ("states_after", after_values)):
            group = handle.create_group(section)
            refs = np.empty((1, n_ticks), dtype=h5py.special_dtype(ref=h5py.Reference))
            for tick, value in enumerate(values):
                dset = handle.create_dataset(f"__data/{section}/channel_a/{tick}", data=np.array([value], dtype=float))
                refs[0, tick] = dset.ref
            group.create_dataset("channel_a", data=refs, dtype=h5py.special_dtype(ref=h5py.Reference))
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks], dtype=np.float64))
        metadata.create_dataset("rng_seed", data=np.array([seed], dtype=np.float64))
    return path


def _write_manifest(
    path: Path,
    *,
    process: str,
    window_length_ticks: int,
    entries: dict[str, dict],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": h12.TRACE_WINDOW_MANIFEST_SCHEMA_VERSION,
                "process": process,
                "window_length_ticks": window_length_ticks,
                "entries": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_load_trace_window_manifest_resolves_relative_paths_and_loads_exact_slice(tmp_path):
    trace_path = _write_trace(
        tmp_path / "trace.mat",
        before_values=[10.0, 20.0, 30.0, 40.0, 50.0],
        after_values=[11.0, 21.0, 31.0, 41.0, 51.0],
        seed=0,
    )
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        process="FakeProcess",
        window_length_ticks=2,
        entries={
            "0": {
                "seed": 0,
                "process": "FakeProcess",
                "trace_path": trace_path.name,
                "trace_sha256": h12._sha256_file(trace_path),
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 5,
                "window_tick_start": 3,
                "window_tick_end": 4,
                "window_length_ticks": 2,
            }
        },
    )

    entries, payload = h12.load_trace_window_manifest(
        manifest_path,
        expected_process="FakeProcess",
        expected_window_ticks=2,
    )

    assert payload["process"] == "FakeProcess"
    entry = entries[0]
    assert entry.trace_path == trace_path.resolve()
    before, after, sha = h12.load_oracle_seed("FakeProcess", 0, 2, trace_window=entry)
    assert sha == h12._sha256_file(trace_path)
    np.testing.assert_array_equal(before["channel_a"].ravel(), np.array([30.0, 40.0]))
    np.testing.assert_array_equal(after["channel_a"].ravel(), np.array([31.0, 41.0]))


def test_load_trace_window_manifest_rejects_out_of_bounds_window(tmp_path):
    trace_path = _write_trace(
        tmp_path / "trace.mat",
        before_values=[1.0, 2.0, 3.0],
        after_values=[2.0, 3.0, 4.0],
        seed=0,
    )
    manifest_path = _write_manifest(
        tmp_path / "bad_manifest.json",
        process="FakeProcess",
        window_length_ticks=2,
        entries={
            "0": {
                "seed": 0,
                "process": "FakeProcess",
                "trace_path": str(trace_path),
                "trace_sha256": h12._sha256_file(trace_path),
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 3,
                "window_tick_start": 3,
                "window_tick_end": 4,
                "window_length_ticks": 2,
            }
        },
    )
    with pytest.raises(ValueError, match="outside source trace"):
        h12.load_trace_window_manifest(
            manifest_path,
            expected_process="FakeProcess",
            expected_window_ticks=2,
        )


def test_run_h12_uses_trace_window_manifest_and_records_manifest_ref(tmp_path, monkeypatch):
    trace0 = _write_trace(
        tmp_path / "seed0.mat",
        before_values=[0.0, 10.0, 20.0, 30.0],
        after_values=[1.0, 11.0, 21.0, 31.0],
        seed=0,
    )
    trace1 = _write_trace(
        tmp_path / "seed1.mat",
        before_values=[100.0, 110.0, 120.0, 130.0],
        after_values=[101.0, 111.0, 121.0, 131.0],
        seed=1,
    )
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        process="FakeProcess",
        window_length_ticks=2,
        entries={
            "0": {
                "seed": 0,
                "process": "FakeProcess",
                "trace_path": str(trace0),
                "trace_sha256": h12._sha256_file(trace0),
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 4,
                "window_tick_start": 2,
                "window_tick_end": 3,
                "window_length_ticks": 2,
            },
            "1": {
                "seed": 1,
                "process": "FakeProcess",
                "trace_path": str(trace1),
                "trace_sha256": h12._sha256_file(trace1),
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 4,
                "window_tick_start": 1,
                "window_tick_end": 2,
                "window_length_ticks": 2,
            },
        },
    )

    def _predict(seed: int, before: dict, fixture: dict) -> list[h12.UnitPrediction]:
        del fixture
        return [
            h12.UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="synthetic_match",
                nontrivial=True,
                predicted_delta={"channel_a": np.array([1.0], dtype=float)},
                branch_tags=frozenset({"branch_a"}),
            )
            for tick in range(before["channel_a"].shape[0])
        ]

    monkeypatch.setattr(
        h12,
        "load_fixture",
        lambda process: {"__fixture_path__": "fake_fixture.mat", "__fixture_sha256__": "f" * 64},
    )
    monkeypatch.setattr(
        h12,
        "karr_source_citation",
        lambda process: {
            "vendored_path": "fake_source.m",
            "vendored_sha256_lf_normalized": "e" * 64,
            "upstream_repo": "fake_repo",
            "upstream_commit": "fake_commit",
            "upstream_original_path": "fake_source.m",
            "line_ranges": [[1, 2]],
            "symbols": ["fake_symbol"],
        },
    )
    monkeypatch.setattr(h12, "PREDICTORS", {**h12.PREDICTORS, "FakeProcess": _predict})
    monkeypatch.setattr(h12, "CATALOG_N_M", {**h12.CATALOG_N_M, "FakeProcess": (2, 2)})
    monkeypatch.setattr(h12, "REQUIRED_BRANCHES", {**h12.REQUIRED_BRANCHES, "FakeProcess": frozenset({"branch_a"})})

    artifact = h12.run_h12("FakeProcess", 2, 2, trace_window_manifest_path=manifest_path)

    assert artifact["verdict"] == "H12_CONFIRMED"
    assert artifact["nontrivial_sample_count"] == 4
    assert artifact["exact_match_count"] == 4
    assert artifact["oracle_manifest_cross_check"] == {"0": "match", "1": "match"}
    assert artifact["branches_confirmed"] == ["branch_a"]
    assert artifact["oracle_trace_window_manifest_ref"] == {
        "path": manifest_path.resolve().as_posix(),
        "sha256_lf_normalized": h12._sha256_lf_normalized(manifest_path),
        "schema_version": h12.TRACE_WINDOW_MANIFEST_SCHEMA_VERSION,
    }


def test_main_forwards_trace_window_manifest_argument(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    recorded: dict[str, object] = {}

    def _fake_run(process: str, n_seeds: int, m_ticks: int, *, trace_window_manifest_path: Path | None = None) -> dict:
        recorded["process"] = process
        recorded["n_seeds"] = n_seeds
        recorded["m_ticks"] = m_ticks
        recorded["trace_window_manifest_path"] = trace_window_manifest_path
        return {
            "process": process,
            "verdict": "H12_CONFIRMED",
            "nontrivial_sample_count": 1,
            "exact_match_rate": 1.0,
        }

    monkeypatch.setattr(h12, "run_h12", _fake_run)
    monkeypatch.setattr(h12, "write_artifact", lambda artifact, out_dir=h12.OUT_ROOT: tmp_path / "out.json")
    monkeypatch.setattr(h12, "PREDICTORS", {**h12.PREDICTORS, "FakeProcess": lambda seed, before, fixture: []})
    monkeypatch.setattr(h12, "CATALOG_N_M", {**h12.CATALOG_N_M, "FakeProcess": (2, 2)})

    h12.main(
        [
            "FakeProcess",
            "--n-seeds",
            "2",
            "--m-ticks",
            "2",
            "--trace-window-manifest",
            str(manifest_path),
        ]
    )

    assert recorded == {
        "process": "FakeProcess",
        "n_seeds": 2,
        "m_ticks": 2,
        "trace_window_manifest_path": manifest_path,
    }
