from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
import l2_2_design_a_runner as runner  # noqa: E402


def test_rna_decay_duplicate_wid_round_trip_preserves_tick0_vector() -> None:
    oracle = runner_helpers.load_karr_oracle("RNADecay")
    process = runner_helpers._rna_decay_process(0)
    rna_wids = [str(x) for x in getattr(process, "gene_ids", getattr(process, "rna_wids", ()))]
    tick0_before = np.asarray(oracle["before_rnas"], dtype=np.float64)[0, 0]

    runtime_state = runner_helpers.build_state_template(process)
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="RNAs",
        vector=tick0_before,
        wids=rna_wids,
        store_path_override=runner_helpers._RNA_STORE_PATH_OVERRIDE,
    )
    runner_helpers._overlay_rna_decay_slot_counts(
        state=runtime_state,
        vector=tick0_before,
        wids=rna_wids,
    )

    projected = runner_helpers._project_rna_decay_slot_counts(
        process=process,
        state=runtime_state,
        wids=rna_wids,
        bound_enzymes_before=np.zeros(len(process.enzyme_wids), dtype=np.float64),
    )

    assert np.array_equal(projected, tick0_before)


def test_rna_decay_tick_ignores_cheated_after_payload() -> None:
    oracle = runner_helpers.load_karr_oracle("RNADecay")
    process = runner_helpers._rna_decay_process(0)
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    rna_wids = [str(x) for x in getattr(process, "gene_ids", getattr(process, "rna_wids", ()))]

    honest_state = {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "rna_wids": rna_wids,
        "oracle_before_substrates": np.asarray(oracle["before_substrates"], dtype=np.float64)[0, 0],
        "oracle_after_substrates": np.asarray(oracle["after_substrates"], dtype=np.float64)[0, 0],
        "oracle_before_enzymes": np.asarray(oracle["before_enzymes"], dtype=np.float64)[0, 0],
        "oracle_before_bound_enzymes": np.asarray(oracle["before_bound_enzymes"], dtype=np.float64)[0, 0],
        "oracle_before_rnas": np.asarray(oracle["before_rnas"], dtype=np.float64)[0, 0],
        "oracle_after_rnas": np.asarray(oracle["after_rnas"], dtype=np.float64)[0, 0],
    }
    cheated_state = dict(honest_state)
    cheated_state["oracle_after_substrates"] = np.zeros_like(
        honest_state["oracle_after_substrates"], dtype=np.float64
    )
    cheated_state["oracle_after_rnas"] = np.zeros_like(honest_state["oracle_after_rnas"], dtype=np.float64)

    runner_helpers._rna_decay_process.cache_clear()
    honest = runner_helpers._run_rna_decay_tick(0, 0, honest_state)
    runner_helpers._rna_decay_process.cache_clear()
    cheated = runner_helpers._run_rna_decay_tick(0, 0, cheated_state)

    honest_rnas = np.asarray(honest["RNAs"], dtype=np.float64)
    cheated_rnas = np.asarray(cheated["RNAs"], dtype=np.float64)
    assert np.array_equal(honest_rnas, cheated_rnas)
    assert np.count_nonzero(cheated_rnas) > 0


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
