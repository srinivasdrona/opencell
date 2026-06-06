from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import l2_2_design_a_runner as runner  # noqa: E402


def test_rna_decay_oracle_laundering_flips_primary_channel(
    monkeypatch,
    tmp_path: Path,
) -> None:
    original_run_oc_tick = runner_helpers.run_oc_tick

    def launder_primary_channel(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, object]:
        result = original_run_oc_tick(process_name, seed, tick, state)
        if process_name == "RNADecay":
            result["RNAs"] = np.asarray(state["oracle_after_rnas"], dtype=np.float64)
        return result

    monkeypatch.setattr(runner_helpers, "run_oc_tick", launder_primary_channel)

    payload = runner.run_design_a(
        process="RNADecay",
        seeds=[0, 1, 2],
        m_ticks=5,
        out_dir=tmp_path / "RNADecay_oracle_laundering",
        bootstrap_B=10,
    )

    result = payload["result"]
    assert result["verdict"] == "FAIL"
    assert result["channels"]["RNAs"]["verdict"] == "FAIL"
    assert result["channels"]["RNAs"]["w1_oc_vs_karr"] == 0.0
    assert any("PRIMARY_CHANNEL_ORACLE_LAUNDERING" in warning for warning in result["warnings"])
