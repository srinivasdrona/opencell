from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import l2_2_design_a_runner as runner  # noqa: E402


def _macromol_state(tick: int = 0) -> dict[str, object]:
    oracle = runner_helpers.load_karr_oracle("MacromolecularComplexation")
    process = runner_helpers._macromol_process(0)
    return {
        "substrate_wids": list(process.substrate_wids),
        "enzyme_wids": list(process.enzyme_wids),
        "complex_wids": list(process.complex_wids),
        "oracle_before_substrates": np.asarray(oracle["before_substrates"], dtype=np.float64)[0, tick],
        "oracle_before_enzymes": np.asarray(oracle["before_enzymes"], dtype=np.float64)[0, tick],
        "oracle_before_complexs": np.asarray(oracle["before_complexs"], dtype=np.float64)[0, tick],
        "oracle_after_substrates": np.asarray(oracle["after_substrates"], dtype=np.float64)[0, tick],
        "oracle_after_complexs": np.asarray(oracle["after_complexs"], dtype=np.float64)[0, tick],
    }


def test_macromol_tick_ignores_cheated_after_payload() -> None:
    honest_state = _macromol_state()
    cheated_state = dict(honest_state)
    cheated_state["oracle_after_substrates"] = np.zeros_like(
        honest_state["oracle_after_substrates"], dtype=np.float64
    )
    cheated_state["oracle_after_complexs"] = np.zeros_like(
        honest_state["oracle_after_complexs"], dtype=np.float64
    )

    runner_helpers._macromol_process.cache_clear()
    honest = runner_helpers._run_macromol_tick(0, 0, honest_state)
    runner_helpers._macromol_process.cache_clear()
    cheated = runner_helpers._run_macromol_tick(0, 0, cheated_state)

    honest_complexs = np.asarray(honest["complexs"], dtype=np.float64)
    cheated_complexs = np.asarray(cheated["complexs"], dtype=np.float64)
    honest_substrates = np.asarray(honest["substrates"], dtype=np.float64)
    cheated_substrates = np.asarray(cheated["substrates"], dtype=np.float64)

    assert np.array_equal(honest_complexs, cheated_complexs)
    assert np.array_equal(honest_substrates, cheated_substrates)
    assert np.count_nonzero(cheated_substrates) > 0


def test_macromol_constant_zero_primary_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.zeros_like(np.asarray(state["oracle_after_substrates"], dtype=np.float64)),
            "complexs": np.zeros_like(np.asarray(state["oracle_after_complexs"], dtype=np.float64)),
        },
    )

    payload = runner.run_design_a(
        process="MacromolecularComplexation",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "MacromolecularComplexation_zero_primary",
        bootstrap_B=10,
    )

    result = payload["result"]
    assert result["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["w1_oc_vs_karr"] > 0.0


def test_macromol_primary_exact_match_is_legitimate_noop(tmp_path: Path) -> None:
    payload = runner.run_design_a(
        process="MacromolecularComplexation",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "MacromolecularComplexation_legitimate_noop",
        bootstrap_B=10,
    )

    result = payload["result"]
    assert result["verdict"] == "PASS"
    assert result["channels"]["substrates"]["is_primary"] is True
    assert result["channels"]["substrates"]["w1_oc_vs_karr"] == 0.0
    assert any(
        "PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE" in warning
        for warning in result["warnings"]
    )
