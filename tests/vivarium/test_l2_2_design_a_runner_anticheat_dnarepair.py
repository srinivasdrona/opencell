from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import l2_2_design_a_runner as runner  # noqa: E402


def _dnarepair_tick_state(*, tick: int) -> dict[str, object]:
    oracle = runner_helpers.load_karr_oracle("DNARepair")
    process = runner_helpers._dnarepair_process(0)
    return {
        "substrate_wids": list(process.tracked_substrates),
        "enzyme_wids": list(process.enzyme_wids),
        "monomer_wids": list(process.protein_enzyme_wids),
        "complex_wids": list(process.complex_enzyme_wids),
        "oracle_before_substrates": np.asarray(oracle["before_substrates"], dtype=np.float64)[0, tick],
        "oracle_after_substrates": np.asarray(oracle["after_substrates"], dtype=np.float64)[0, tick],
        "oracle_before_enzymes": np.asarray(oracle["before_enzymes"], dtype=np.float64)[0, tick],
        "oracle_before_bound_enzymes": np.asarray(
            oracle["before_bound_enzymes"], dtype=np.float64
        )[0, tick],
        "oracle_before_monomers": np.asarray(oracle["before_monomers"], dtype=np.float64)[0, tick],
        "oracle_before_complexs": np.asarray(oracle["before_complexs"], dtype=np.float64)[0, tick],
    }


def test_dnarepair_primary_fixture_is_legitimate_noop() -> None:
    oracle = runner_helpers.load_karr_oracle("DNARepair")
    before = np.asarray(oracle["before_substrates"], dtype=np.float64)
    after = np.asarray(oracle["after_substrates"], dtype=np.float64)

    assert np.array_equal(before, after)
    assert runner_helpers._DNAREPAIR_ORACLE_PATH.name == "DNARepair.npz"


# DNARepair has no _maybe_replay_from_hint / trace_hint replay branch, so the
# Replication bypass test is intentionally omitted here.


def test_dnarepair_constant_zero_primary_channel_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    original_run_oc_tick = runner_helpers.run_oc_tick

    def zero_primary_channel(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, object]:
        if process_name != "DNARepair":
            return original_run_oc_tick(process_name, seed, tick, state)
        return {
            "substrates": np.zeros_like(np.asarray(state["oracle_after_substrates"], dtype=np.float64)),
            "sample_seed": 0,
        }

    monkeypatch.setattr(runner_helpers, "run_oc_tick", zero_primary_channel)

    payload = runner.run_design_a(
        process="DNARepair",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "DNARepair_zero_primary",
        bootstrap_B=10,
    )

    result = payload["result"]
    assert result["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["verdict"] == "FAIL"
    assert result["channels"]["substrates"]["w1_oc_vs_karr"] > 0.0


def test_dnarepair_primary_exact_match_is_legitimate_noop(tmp_path: Path) -> None:
    payload = runner.run_design_a(
        process="DNARepair",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "DNARepair_legitimate_noop",
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
