"""Targeted tests for scripts/l22_dnas_power/build_report.py's orchestration
logic. `validate_extension_seeds` and `diagnostic_runner.run_seed_config`
(the two pieces that would otherwise require real Karr trace data / a real
OC simulation run) are monkeypatched at the point of use inside
`build_report` (same convention as `tests/scripts/test_l22_report_final.py`),
so this file only exercises `build_report`'s own wiring: validation
short-circuiting, loader-count short-circuiting, and the power-decision /
rate-projection / half-split-stability assembly given canned per-component
results.

Run via `bin\\oc-pytest tests/scripts/test_l22_dnas_power_build_report.py -v`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.l22_dnas_power.build_report as build_report_mod  # noqa: E402


def _per_component(n_oc: dict[str, int], n_karr: dict[str, int], raw_w1: dict[str, float]) -> dict[str, Any]:
    components = list(n_oc)
    verdicts = {c: ("PASS" if raw_w1[c] <= 1.0 else "FAIL") for c in components}
    return {
        "component_n_nonzero_oc": dict(n_oc),
        "component_n_nonzero_karr": dict(n_karr),
        "component_raw_w1": dict(raw_w1),
        "component_scales": {c: 1.0 for c in components},
        "component_verdicts": verdicts,
        "joint_verdict": "PASS" if all(v == "PASS" for v in verdicts.values()) else "FAIL",
        "scaled_distance_threshold": 1.0,
    }


def _fake_payload(channel_verdict: str, per_component: dict[str, Any]) -> dict[str, Any]:
    return {"result": {"channels": {"chromosome": {"verdict": channel_verdict, "per_component": per_component}}}}


def _install_loader_count(monkeypatch, count: int) -> None:
    fake = types.ModuleType("_l2_2_design_a_runner_helpers")
    fake._load_v2_ensemble = lambda process, max_seeds=50: {"canonical_seed_count": count}
    monkeypatch.setitem(sys.modules, "_l2_2_design_a_runner_helpers", fake)


def test_build_report_short_circuits_on_validation_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        build_report_mod,
        "validate_extension_seeds",
        lambda seeds: {"result": "BLOCKED", "blockers": ["seed 50: structural validation failed"]},
    )
    report = build_report_mod.build_report(out_root=tmp_path)
    assert report["result"] == "BLOCKED_ON_VALIDATION"
    assert "n100_combined" not in report


def test_build_report_short_circuits_on_wrong_loader_count(monkeypatch, tmp_path):
    monkeypatch.setattr(build_report_mod, "validate_extension_seeds", lambda seeds: {"result": "PASS"})
    _install_loader_count(monkeypatch, 87)
    report = build_report_mod.build_report(out_root=tmp_path)
    assert report["result"] == "BLOCKED_ON_LOADER_COUNT"
    assert report["loader_diagnostic_count"] == 87


def test_build_report_powered_path_evaluates_metric_and_reports_stability(monkeypatch, tmp_path):
    monkeypatch.setattr(build_report_mod, "validate_extension_seeds", lambda seeds: {"result": "PASS"})
    _install_loader_count(monkeypatch, 100)

    n50_payload = _fake_payload(
        "PASS",
        _per_component(
            n_oc={"linkingNumbers.delta_value_sum": 2462, "linkingNumbers.delta_nnz": 17},
            n_karr={"linkingNumbers.delta_value_sum": 2480, "linkingNumbers.delta_nnz": 24},
            raw_w1={"linkingNumbers.delta_value_sum": 50.0, "linkingNumbers.delta_nnz": 0.01},
        ),
    )
    n100_payload = _fake_payload(
        "PASS",
        _per_component(
            n_oc={"linkingNumbers.delta_value_sum": 4924, "linkingNumbers.delta_nnz": 34},
            n_karr={"linkingNumbers.delta_value_sum": 4961, "linkingNumbers.delta_nnz": 48},
            raw_w1={"linkingNumbers.delta_value_sum": 50.4, "linkingNumbers.delta_nnz": 0.01},
        ),
    )
    half_b_payload = _fake_payload(
        "PASS",
        _per_component(
            n_oc={"linkingNumbers.delta_value_sum": 2462, "linkingNumbers.delta_nnz": 17},
            n_karr={"linkingNumbers.delta_value_sum": 2481, "linkingNumbers.delta_nnz": 24},
            raw_w1={"linkingNumbers.delta_value_sum": 50.8, "linkingNumbers.delta_nnz": 0.012},
        ),
    )

    def _fake_run_seed_config(*, seeds, out_dir, max_seeds_override):
        if seeds == build_report_mod.BASELINE_SEEDS:
            return n50_payload
        if seeds == build_report_mod.COMBINED_SEEDS:
            return n100_payload
        if seeds == build_report_mod.EXTENSION_SEEDS:
            return half_b_payload
        raise AssertionError(f"unexpected seeds {seeds}")

    monkeypatch.setattr(build_report_mod.diagnostic_runner, "run_seed_config", _fake_run_seed_config)

    report = build_report_mod.build_report(out_root=tmp_path)

    assert report["result"] == "COMPLETE"
    assert report["decision"] == "POWERED_AT_N100"
    assert report["power_decision"]["linkingNumbers.delta_nnz"]["powered"] is True
    assert report["power_decision"]["linkingNumbers.delta_nnz"]["n_nonzero_oc"] == 34
    assert report["power_decision"]["linkingNumbers.delta_nnz"]["n_nonzero_karr"] == 48
    stability = report["seed_half_split_stability"]["linkingNumbers.delta_nnz"]
    assert stability["half_a_n_nonzero_oc"] == 17
    assert stability["half_b_n_nonzero_oc"] == 17


def test_build_report_underpowered_path_does_not_evaluate_metric(monkeypatch, tmp_path):
    monkeypatch.setattr(build_report_mod, "validate_extension_seeds", lambda seeds: {"result": "PASS"})
    _install_loader_count(monkeypatch, 100)

    still_low_payload = _fake_payload(
        "PRIMARY_INSUFFICIENT_SAMPLES",
        _per_component(
            n_oc={"linkingNumbers.delta_value_sum": 4924, "linkingNumbers.delta_nnz": 25},
            n_karr={"linkingNumbers.delta_value_sum": 4961, "linkingNumbers.delta_nnz": 28},
            raw_w1={"linkingNumbers.delta_value_sum": 50.4, "linkingNumbers.delta_nnz": 0.01},
        ),
    )
    n50_payload = _fake_payload(
        "PRIMARY_INSUFFICIENT_SAMPLES",
        _per_component(
            n_oc={"linkingNumbers.delta_value_sum": 2462, "linkingNumbers.delta_nnz": 17},
            n_karr={"linkingNumbers.delta_value_sum": 2480, "linkingNumbers.delta_nnz": 24},
            raw_w1={"linkingNumbers.delta_value_sum": 50.0, "linkingNumbers.delta_nnz": 0.01},
        ),
    )

    def _fake_run_seed_config(*, seeds, out_dir, max_seeds_override):
        if seeds == build_report_mod.COMBINED_SEEDS:
            return still_low_payload
        return n50_payload

    monkeypatch.setattr(build_report_mod.diagnostic_runner, "run_seed_config", _fake_run_seed_config)

    report = build_report_mod.build_report(out_root=tmp_path)

    assert report["result"] == "COMPLETE"
    assert report["decision"] == "STILL_UNDERPOWERED_AT_N100"
    assert "mechanical_metric_verdict" not in report
    assert report["power_decision"]["linkingNumbers.delta_nnz"]["powered"] is False
