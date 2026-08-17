from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import macromol_active_windows as mae  # noqa: E402
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


def _write_active_window(path: Path, *, seed: int, trigger_indices_0b: tuple[int, ...] = (22,)) -> Path:
    n_ticks = maw.REQUIRED_M_TICKS
    tick_offset = 8385 + seed
    tick_start = tick_offset + 1
    tick_end = tick_start + n_ticks - 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata(maw.PROCESS_NAME))
        metadata.create_dataset("rng_seed", data=np.array([seed]))
        metadata.create_dataset("tick_offset", data=np.array([float(tick_offset)]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("tick_end", data=np.array([tick_end]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("active_window_rule", data=_encode_char_metadata(maw.ACTIVE_WINDOW_RULE))
        metadata.create_dataset("active_window_rule_version", data=np.array([maw.ACTIVE_WINDOW_RULE_VERSION]))
        metadata.create_dataset("active_window_trigger_tick", data=np.array([tick_start]))
        metadata.create_dataset(
            "active_window_trigger_complex_indices_0b",
            data=np.array(trigger_indices_0b, dtype=np.int32).reshape(1, -1),
        )
        metadata.create_dataset("active_window_search_max_ticks", data=np.array([maw.SEARCH_MAX_TICKS]))
        metadata.create_dataset(
            "active_window_search_stop_reason",
            data=_encode_char_metadata("first_network2_positive_delta"),
        )
        metadata.create_dataset(
            "active_window_detection_mechanism",
            data=_encode_char_metadata("synthetic unit-test fixture"),
        )
        metadata.create_dataset(
            "active_window_capture_mode",
            data=_encode_char_metadata(maw.ACTIVE_WINDOW_CAPTURE_MODE),
        )
        metadata.create_dataset("mnrnd_provider_kind", data=_encode_char_metadata("statistics_toolbox"))
        metadata.create_dataset("mnrnd_provider_matlab_release", data=_encode_char_metadata("R2026a"))
        metadata.create_dataset("mnrnd_provider_toolbox_version", data=_encode_char_metadata("26.1"))
        metadata.create_dataset(
            "mnrnd_provider_path_relative_to_matlabroot",
            data=_encode_char_metadata("toolbox/stats/stats/mnrnd.m"),
        )
        metadata.create_dataset("mnrnd_provider_sha256", data=_encode_char_metadata("provider-sha"))
        metadata.create_dataset(
            "statistics_rng_provider_identity_json",
            data=_encode_char_metadata('{"kind":"statistics_toolbox"}'),
        )
        metadata.create_dataset(
            "active_window_driver_relpath",
            data=_encode_char_metadata(maw._relative_to_repo(maw.MATLAB_DRIVER)),  # noqa: SLF001
        )
        metadata.create_dataset(
            "active_window_driver_sha256_lf_normalized",
            data=_encode_char_metadata(maw._sha256_lf_normalized(maw.MATLAB_DRIVER)),  # noqa: SLF001
        )
        metadata.create_dataset(
            "active_window_fixture_relpath",
            data=_encode_char_metadata(maw._relative_to_repo(maw.FIXTURE_PATH)),  # noqa: SLF001
        )
        metadata.create_dataset("active_window_fixture_sha256", data=_encode_char_metadata(maw.sha256_file(maw.FIXTURE_PATH)))
        metadata.create_dataset(
            "active_window_vendored_source_relpath",
            data=_encode_char_metadata(maw._relative_to_repo(maw.VENDORED_SOURCE_PATH)),  # noqa: SLF001
        )
        metadata.create_dataset(
            "active_window_vendored_source_sha256_lf_normalized",
            data=_encode_char_metadata(maw._sha256_lf_normalized(maw.VENDORED_SOURCE_PATH)),  # noqa: SLF001
        )
        metadata.create_dataset("active_window_first_e1_nonzero_tick", data=np.array([tick_start - 4]))
        metadata.create_dataset("timestamp", data=_encode_char_metadata("2026-08-18 00:00:00"))

        before_complexs = np.zeros((n_ticks, 24), dtype=np.float64)
        after_complexs = before_complexs.copy()
        for idx in trigger_indices_0b:
            after_complexs[0, idx] = 1.0

        before_substrates = np.zeros((n_ticks, 4), dtype=np.float64)
        after_substrates = before_substrates.copy()

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        _write_cell_series(handle, states_before, "substrates", before_substrates)
        _write_cell_series(handle, states_after, "substrates", after_substrates)
        _write_cell_series(handle, states_before, "complexs", before_complexs)
        _write_cell_series(handle, states_after, "complexs", after_complexs)
    return path


def _write_minimal_runner_outputs(out_dir: Path, *, verdict: str = "PASS") -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "process": mae.PROCESS,
        "verdict": verdict,
        "allocator_inputs_ref": str(out_dir / "allocator_inputs.json"),
        "provenance_ref": str(out_dir / "provenance.json"),
        "channels": {"complexs": {"verdict": "SEED_NOISE", "w1_oc_vs_karr": 0.0}},
    }
    summary = {
        "processes": {mae.PROCESS: {"verdict": verdict}},
        "schema_version": "1.4",
    }
    thresholds = {"process": mae.PROCESS, "channels": {"complexs": {"threshold": 1.0}}}
    null_calibration = {"process": mae.PROCESS, "channels": {"complexs": {"q95_null": 0.1}}}
    analytical_check = {"applicable": False, "reason": "synthetic test"}
    manifest = {
        "inputs": [
            {"path": str(out_dir / "synthetic_oracle.mat"), "sha256": "abc"},
            {"path": str(REPO_ROOT / mae.RUNNER_SOURCE_PATH), "sha256": mae._sha256_file(REPO_ROOT / mae.RUNNER_SOURCE_PATH)},
        ],
        "resolved_seeds": list(range(maw.REQUIRED_N_SEEDS)),
        "m_ticks": maw.REQUIRED_M_TICKS,
    }
    provenance = {
        "oracle_path": str(out_dir / "synthetic_oracle.mat"),
        "harness_version": "design_a_v1_3",
    }
    allocator_inputs = {"records": []}

    (out_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (out_dir / "SUMMARY.json").write_text(json.dumps(summary), encoding="utf-8")
    (out_dir / "thresholds.json").write_text(json.dumps(thresholds), encoding="utf-8")
    (out_dir / "null_calibration.json").write_text(json.dumps(null_calibration), encoding="utf-8")
    (out_dir / "analytical_check.json").write_text(json.dumps(analytical_check), encoding="utf-8")
    (out_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (out_dir / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    (out_dir / "allocator_inputs.json").write_text(json.dumps(allocator_inputs), encoding="utf-8")
    return {
        "result": result,
        "summary": summary,
        "thresholds": thresholds,
        "null_calibration": null_calibration,
    }


def test_process_local_oracle_root_routes_only_macromol(tmp_path: Path) -> None:
    original_other = mae.runner_helpers._v2_seed_mat_path("RNADecay", 1)  # noqa: SLF001

    with mae.process_local_oracle_root(tmp_path):
        assert mae.runner_helpers._v2_seed_mat_path(mae.PROCESS, 0) == maw._seed_trace_path(0, tmp_path)  # noqa: SLF001
        assert mae.runner_helpers._v2_seed_mat_path(mae.PROCESS, 3) == maw._seed_trace_path(3, tmp_path)  # noqa: SLF001
        assert mae.runner_helpers._v2_seed_mat_path("RNADecay", 1) == original_other  # noqa: SLF001


def test_build_process_local_artifact_embeds_runner_verdict(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "macromol_active_window"
    run_root = tmp_path / "run_output"

    monkeypatch.setattr(maw, "REQUIRED_N_SEEDS", 2)
    for seed in range(maw.REQUIRED_N_SEEDS):
        _write_active_window(maw._seed_trace_path(seed, data_root), seed=seed)  # noqa: SLF001

    def fake_run_design_a(*, process: str, seeds: list[int], m_ticks: int, out_dir: Path, bootstrap_B: int) -> dict[str, Any]:
        assert process == mae.PROCESS
        assert seeds == [0, 1]
        assert m_ticks == maw.REQUIRED_M_TICKS
        return _write_minimal_runner_outputs(out_dir)

    monkeypatch.setattr(mae.runner, "run_design_a", fake_run_design_a)

    artifact = mae.build_process_local_artifact(data_root=data_root, run_output_dir=run_root)

    assert artifact["artifact_kind"] == mae.ARTIFACT_KIND
    assert artifact["audit"]["status"] == "SUFFICIENT_ENSEMBLE"
    assert artifact["ordinary_design_a"]["result"]["verdict"] == "PASS"
    assert set(artifact["seed_trace_sha256"]) == {"0", "1"}
    assert mae.validate_process_local_artifact(artifact, repo_root=REPO_ROOT) is None
