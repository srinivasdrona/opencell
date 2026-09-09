from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_dnas_rare_event import capture  # noqa: E402


def _fake_runner_module(*, return_value: dict | None = None):
    module = types.SimpleNamespace()

    def _real_per_component_scaled_distance(oc_projection_vectors, karr_projection_vectors, component_scales):
        return return_value if return_value is not None else {"joint_verdict": "PASS"}

    module.per_component_scaled_distance = _real_per_component_scaled_distance
    return module


def test_capture_projection_tensors_records_call_arguments():
    runner = _fake_runner_module(return_value={"joint_verdict": "FAIL"})
    oc = np.array([[[1.0]]])
    karr = np.array([[[2.0]]])
    scales = {"linkingNumbers.delta_nnz": 2.0}

    with capture.capture_projection_tensors(runner) as captured:
        result = runner.per_component_scaled_distance(oc, karr, scales)

    assert result == {"joint_verdict": "FAIL"}
    assert np.array_equal(captured["oc"], oc)
    assert np.array_equal(captured["karr"], karr)
    assert captured["component_scales"] == scales


def test_capture_projection_tensors_stores_a_copy_not_a_view():
    runner = _fake_runner_module()
    oc = np.array([[[1.0]]])
    karr = np.array([[[2.0]]])

    with capture.capture_projection_tensors(runner) as captured:
        runner.per_component_scaled_distance(oc, karr, {})
        oc[0, 0, 0] = 999.0

    assert captured["oc"][0, 0, 0] == 1.0


def test_capture_projection_tensors_restores_original_after_exit():
    runner = _fake_runner_module()
    original = runner.per_component_scaled_distance
    with capture.capture_projection_tensors(runner):
        pass
    assert runner.per_component_scaled_distance is original


def test_capture_projection_tensors_restores_original_even_on_exception():
    runner = _fake_runner_module()
    original = runner.per_component_scaled_distance
    with pytest.raises(RuntimeError), capture.capture_projection_tensors(runner):
        raise RuntimeError("boom")
    assert runner.per_component_scaled_distance is original


def test_run_and_capture_raises_if_capture_never_observed_a_call(tmp_path, monkeypatch):
    fake_runner = _fake_runner_module()
    monkeypatch.setitem(sys.modules, "l2_2_design_a_runner", fake_runner)

    def _fake_run_seed_config(*, seeds, out_dir, max_seeds_override, m_ticks=100, bootstrap_B=1000):
        return {"result": {}}

    monkeypatch.setattr(capture.diagnostic_runner, "run_seed_config", _fake_run_seed_config)

    with pytest.raises(RuntimeError, match="per_component_scaled_distance"):
        capture.run_and_capture(seeds=[0, 1], out_dir=tmp_path, max_seeds_override=10)


def test_run_and_capture_returns_captured_tensors_alongside_payload(tmp_path, monkeypatch):
    oc = np.zeros((2, 3, 1))
    karr = np.ones((2, 3, 1))
    scales = {"linkingNumbers.delta_nnz": 2.0}
    fake_runner = _fake_runner_module()
    monkeypatch.setitem(sys.modules, "l2_2_design_a_runner", fake_runner)

    def _fake_run_seed_config(*, seeds, out_dir, max_seeds_override, m_ticks=100, bootstrap_B=1000):
        fake_runner.per_component_scaled_distance(oc, karr, scales)
        return {"result": {"sentinel": True}}

    monkeypatch.setattr(capture.diagnostic_runner, "run_seed_config", _fake_run_seed_config)

    captured = capture.run_and_capture(seeds=[0, 1], out_dir=tmp_path, max_seeds_override=10)
    assert captured["payload"] == {"result": {"sentinel": True}}
    assert np.array_equal(captured["oc_tensor"], oc)
    assert np.array_equal(captured["karr_tensor"], karr)
    assert captured["component_scales"] == scales
