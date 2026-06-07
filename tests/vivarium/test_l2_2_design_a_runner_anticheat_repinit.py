from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import l2_2_design_a_runner as runner  # noqa: E402


def _repinit_tick_state(*, tick: int) -> dict[str, object]:
    oracle = runner_helpers.load_karr_oracle("ReplicationInitiation")
    process = runner_helpers._replication_initiation_process(0)
    return {
        "substrate_wids": list(process.substrate_wids),
        "enzyme_wids": list(process.enzyme_wids),
        "oracle_before_substrates": np.asarray(oracle["before_substrates"], dtype=np.float64)[0, tick],
        "oracle_after_substrates": np.asarray(oracle["after_substrates"], dtype=np.float64)[0, tick],
        "oracle_before_enzymes": np.asarray(oracle["before_enzymes"], dtype=np.float64)[0, tick],
        "oracle_before_bound_enzymes": np.asarray(oracle["before_bound_enzymes"], dtype=np.float64)[0, tick],
    }


def test_repinit_primary_fixture_is_nontrivial() -> None:
    oracle = runner_helpers.load_karr_oracle("ReplicationInitiation")
    before = np.asarray(oracle["before_substrates"], dtype=np.float64)
    after = np.asarray(oracle["after_substrates"], dtype=np.float64)

    assert np.any(before != after)
    assert runner_helpers._REPLICATION_INITIATION_ORACLE_PATH.name == "ReplicationInitiation_from_trajectory.npz"


def test_repinit_tick_ignores_cheated_trace_hint_payload() -> None:
    honest_state = _repinit_tick_state(tick=0)
    cheated_state = dict(honest_state)
    cheated_state["oracle_after_substrates"] = np.zeros_like(
        np.asarray(honest_state["oracle_after_substrates"], dtype=np.float64)
    )
    cheated_state["trace_hint"] = {
        "enzymes_next": {wid: 0.0 for wid in honest_state["enzyme_wids"]},
        "boundEnzymes_next": {wid: 0.0 for wid in honest_state["enzyme_wids"]},
    }

    runner_helpers._replication_initiation_process.cache_clear()
    honest = runner_helpers._run_repinit_tick(0, 0, honest_state)
    runner_helpers._replication_initiation_process.cache_clear()
    cheated = runner_helpers._run_repinit_tick(0, 0, cheated_state)

    honest_substrates = np.asarray(honest["substrates"], dtype=np.float64)
    cheated_substrates = np.asarray(cheated["substrates"], dtype=np.float64)
    assert np.array_equal(honest_substrates, cheated_substrates)
    assert np.count_nonzero(cheated_substrates) > 0
    assert not np.array_equal(
        cheated_substrates,
        np.asarray(cheated_state["oracle_after_substrates"], dtype=np.float64),
    )


def test_repinit_constant_zero_primary_channel_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    original_run_oc_tick = runner_helpers.run_oc_tick

    def zero_primary_channel(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, object]:
        if process_name != "ReplicationInitiation":
            return original_run_oc_tick(process_name, seed, tick, state)
        return {
            "substrates": np.zeros_like(np.asarray(state["oracle_after_substrates"], dtype=np.float64)),
            "sample_seed": 0,
        }

    monkeypatch.setattr(runner_helpers, "run_oc_tick", zero_primary_channel)

    payload = runner.run_design_a(
        process="ReplicationInitiation",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "ReplicationInitiation_zero_primary",
        bootstrap_B=10,
    )

    result = payload["result"]
    assert result["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["w1_oc_vs_karr"] > 0.0
