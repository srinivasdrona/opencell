from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import l2_2_design_a_runner as runner  # noqa: E402


def _cytokinesis_state(*, tick: int = 0) -> dict[str, object]:
    oracle = runner_helpers.load_karr_oracle("Cytokinesis")
    return {
        "substrate_wids": list(runner_helpers.load_fixture_channel_wids("Cytokinesis", "substrates")),
        "enzyme_wids": list(runner_helpers.load_fixture_channel_wids("Cytokinesis", "enzymes")),
        "oracle_before_substrates": np.asarray(oracle["before_substrates"], dtype=np.float64)[0, tick],
        "oracle_after_substrates": np.asarray(oracle["after_substrates"], dtype=np.float64)[0, tick],
        "oracle_before_enzymes": np.asarray(oracle["before_enzymes"], dtype=np.float64)[0, tick],
        "oracle_before_bound_enzymes": np.asarray(oracle["before_bound_enzymes"], dtype=np.float64)[0, tick],
    }


def test_cytokinesis_primary_fixture_is_legitimate_noop() -> None:
    oracle = runner_helpers.load_karr_oracle("Cytokinesis")
    before = np.asarray(oracle["before_substrates"], dtype=np.float64)
    after = np.asarray(oracle["after_substrates"], dtype=np.float64)

    assert np.array_equal(before, after)
    assert runner_helpers._CYTOKINESIS_ORACLE_PATH.name == "Cytokinesis.npz"


def test_cytokinesis_tick_ignores_cheated_after_payload() -> None:
    honest_state = _cytokinesis_state()
    cheated_state = dict(honest_state)
    cheated_state["oracle_after_substrates"] = np.zeros_like(
        honest_state["oracle_after_substrates"], dtype=np.float64
    )

    runner_helpers._cytokinesis_process.cache_clear()
    honest = runner_helpers._run_cytokinesis_tick(0, 0, honest_state)
    runner_helpers._cytokinesis_process.cache_clear()
    cheated = runner_helpers._run_cytokinesis_tick(0, 0, cheated_state)

    honest_substrates = np.asarray(honest["substrates"], dtype=np.float64)
    cheated_substrates = np.asarray(cheated["substrates"], dtype=np.float64)
    assert np.array_equal(honest_substrates, cheated_substrates)
    assert np.count_nonzero(cheated_substrates) > 0
    assert not np.array_equal(
        cheated_substrates,
        np.asarray(cheated_state["oracle_after_substrates"], dtype=np.float64),
    )


def test_cytokinesis_constant_zero_primary_channel_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.zeros_like(np.asarray(state["oracle_after_substrates"], dtype=np.float64)),
            "sample_seed": 0,
        },
    )

    payload = runner.run_design_a(
        process="Cytokinesis",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "Cytokinesis_zero_primary",
        bootstrap_B=10,
    )

    result = payload["result"]
    assert result["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["w1_oc_vs_karr"] > 0.0


def test_cytokinesis_primary_exact_match_is_legitimate_noop(tmp_path: Path) -> None:
    payload = runner.run_design_a(
        process="Cytokinesis",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "Cytokinesis_legitimate_noop",
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
