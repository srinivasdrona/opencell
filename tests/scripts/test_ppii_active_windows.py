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
from scripts.l22_evidence import ppii_active_windows as paw  # noqa: E402


def _write_trace(path: Path, *, seed: int, n_ticks: int = 20) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        for section in ("states_before", "states_after"):
            group = handle.create_group(section)
            refs = np.empty((1, n_ticks), dtype=h5py.special_dtype(ref=h5py.Reference))
            for tick in range(n_ticks):
                value = float(tick) if section == "states_before" else float(tick + 1)
                dset = handle.create_dataset(f"__data/{section}/channel_a/{tick}", data=np.array([value], dtype=float))
                refs[0, tick] = dset.ref
            group.create_dataset("channel_a", data=refs, dtype=h5py.special_dtype(ref=h5py.Reference))
        metadata = handle.create_group("metadata")
        metadata.create_dataset("process_name", data=np.array([ord(c) for c in paw.PROCESS], dtype=np.uint16).reshape(-1, 1))
        metadata.create_dataset("n_ticks", data=np.array([n_ticks], dtype=np.float64))
        metadata.create_dataset("rng_seed", data=np.array([seed], dtype=np.float64))
        metadata.create_dataset("tick_offset", data=np.array([0.0], dtype=np.float64))
        metadata.create_dataset("timestamp", data=np.array([ord(c) for c in "2026-08-12 00:00:00"], dtype=np.uint16).reshape(-1, 1))
    return path


def _write_manifest(path: Path, *, entries: dict[str, dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": paw.MANIFEST_SCHEMA_VERSION,
                "process": paw.PROCESS,
                "window_length_ticks": h12.CATALOG_N_M[paw.PROCESS][1],
                "coverage_status": "synthetic_test_fixture",
                "covered_seed_count": len(entries),
                "uncovered_seed_count": h12.CATALOG_N_M[paw.PROCESS][0] - len(entries),
                "entries": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _fake_predict(seed: int, before: dict, fixture: dict) -> list[h12.UnitPrediction]:
    del fixture
    branch_by_tick = {
        0: frozenset({"passthrough_fires"}),
        1: frozenset({"peptidase_fires"}),
        2: frozenset({"transferase_fires"}),
    }
    out: list[h12.UnitPrediction] = []
    for tick in range(before["channel_a"].shape[0]):
        out.append(
            h12.UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="synthetic_match",
                nontrivial=True,
                predicted_delta={"channel_a": np.array([1.0], dtype=float)},
                branch_tags=branch_by_tick.get(tick, frozenset({"transferase_fires"})),
            )
        )
    return out


def test_build_active_window_validation_artifact_uses_shared_h12_predictor_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    trace0 = _write_trace(tmp_path / "seed0.mat", seed=0)
    trace1 = _write_trace(tmp_path / "seed1.mat", seed=1)
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        entries={
            "0": {
                "seed": 0,
                "process": paw.PROCESS,
                "trace_path": str(trace0),
                "trace_sha256": h12._sha256_file(trace0),  # noqa: SLF001
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 20,
                "window_tick_start": 1,
                "window_tick_end": 20,
                "window_length_ticks": 20,
                "first_regime_valid_transferase_tick": 3,
                "window_selection": "whole_trace_for_test",
            },
            "1": {
                "seed": 1,
                "process": paw.PROCESS,
                "trace_path": str(trace1),
                "trace_sha256": h12._sha256_file(trace1),  # noqa: SLF001
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 20,
                "window_tick_start": 1,
                "window_tick_end": 20,
                "window_length_ticks": 20,
                "first_regime_valid_transferase_tick": 3,
                "window_selection": "whole_trace_for_test",
            },
        },
    )

    monkeypatch.setitem(h12.PREDICTORS, paw.PROCESS, _fake_predict)

    artifact = paw.build_active_window_validation_artifact(manifest_path)

    assert artifact["manifest_seed_count"] == 2
    assert artifact["window_verdict"] == "H12_CONFIRMED"
    assert artifact["branches_confirmed"] == sorted(h12.REQUIRED_BRANCHES[paw.PROCESS])
    assert artifact["shared_h12_promotion_ready"] is False
    assert artifact["missing_catalog_seeds"][0] == 2
    assert artifact["seed_windows_verified"]["0"]["window_contains_confirmed_transferase_fires"] is True
    assert artifact["seed_windows_verified"]["0"]["oracle_manifest_cross_check"] == "accepted_external_fixture"
    assert paw.validate_active_window_artifact(artifact) is None


def test_cli_writes_non_gating_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    trace = _write_trace(tmp_path / "seed0.mat", seed=0)
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        entries={
            "0": {
                "seed": 0,
                "process": paw.PROCESS,
                "trace_path": str(trace),
                "trace_sha256": h12._sha256_file(trace),  # noqa: SLF001
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 20,
                "window_tick_start": 1,
                "window_tick_end": 20,
                "window_length_ticks": 20,
                "first_regime_valid_transferase_tick": 3,
            }
        },
    )
    out_path = tmp_path / "report.json"

    monkeypatch.setitem(h12.PREDICTORS, paw.PROCESS, _fake_predict)

    exit_code = paw.main(["--manifest", str(manifest_path), "--out", str(out_path)])

    assert exit_code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["classification"] == paw.CLASSIFICATION
    assert payload["window_verdict"] == "H12_CONFIRMED"
    assert payload["shared_h12_promotion_ready"] is False


def test_tampered_trace_hash_fails_closed(tmp_path: Path):
    trace = _write_trace(tmp_path / "seed0.mat", seed=0)
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        entries={
            "0": {
                "seed": 0,
                "process": paw.PROCESS,
                "trace_path": str(trace),
                "trace_sha256": "0" * 64,
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 20,
                "window_tick_start": 1,
                "window_tick_end": 20,
                "window_length_ticks": 20,
                "first_regime_valid_transferase_tick": 3,
            }
        },
    )

    entries, _payload = paw.load_trace_window_manifest(manifest_path)
    with pytest.raises(ValueError, match="source hash mismatch"):
        paw.load_seed_window(entries[0])


def test_validator_rejects_stale_shared_h12_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    trace = _write_trace(tmp_path / "seed0.mat", seed=0)
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        entries={
            "0": {
                "seed": 0,
                "process": paw.PROCESS,
                "trace_path": str(trace),
                "trace_sha256": h12._sha256_file(trace),  # noqa: SLF001
                "trace_schema": "synthetic_trace_v1",
                "trace_tick_start": 1,
                "trace_tick_end": 20,
                "window_tick_start": 1,
                "window_tick_end": 20,
                "window_length_ticks": 20,
                "first_regime_valid_transferase_tick": 3,
            }
        },
    )

    monkeypatch.setitem(h12.PREDICTORS, paw.PROCESS, _fake_predict)

    artifact = paw.build_active_window_validation_artifact(manifest_path)
    artifact["shared_h12_predictor_source_sha256_lf_normalized"] = "0" * 64

    reason = paw.validate_active_window_artifact(artifact)
    assert reason is not None
    assert "shared_h12_predictor_source_sha256_lf_normalized" in reason


def test_shared_canonical_h12_source_hash_remains_fresh():
    payload = json.loads(
        (REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "ProteinProcessingII_h12.json").read_text(
            encoding="utf-8"
        )
    )
    expected_hash = h12._sha256_lf_normalized(REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH)  # noqa: SLF001

    assert payload["predictor_source_path"] == h12.EXPECTED_PREDICTOR_SOURCE_PATH
    assert payload["predictor_source_sha256_lf_normalized"] == expected_hash
