from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers
import l2_2_design_a_runner as runner


def _fake_protein_processing_oracle(
    *,
    process_name: str,
    tick_count: int = 4,
    seed_count: int = 10,
    substrate_dim: int = 4,
    enzyme_dim: int = 2,
    monomer_dim: int = 8,
) -> dict[str, object]:
    substrate_base = np.full((seed_count, tick_count, substrate_dim), 2.0, dtype=np.float64)
    monomer_base = np.full((seed_count, tick_count, monomer_dim), 100.0, dtype=np.float64)
    return {
        "process": process_name,
        "oracle_path": Path(__file__),
        "canonical_seed_count": seed_count,
        "n_ticks_available": tick_count,
        "before_substrates": substrate_base,
        "before_enzymes": np.ones((seed_count, tick_count, enzyme_dim), dtype=np.float64),
        "before_monomers": monomer_base,
        "after_substrates": substrate_base + 3.0,
        "after_monomers": monomer_base + 3.0,
    }


def _fake_protein_processing_process(
    *,
    substrate_dim: int = 4,
    enzyme_dim: int = 2,
    monomer_dim: int = 8,
) -> SimpleNamespace:
    return SimpleNamespace(
        substrate_wids=tuple(f"S{idx}" for idx in range(substrate_dim)),
        enzyme_wids=tuple(f"E{idx}" for idx in range(enzyme_dim)),
        monomer_wids=tuple(f"M_{idx:03d}" for idx in range(monomer_dim)),
        unprocessed_monomer_wids=tuple(f"M_{idx:03d}" for idx in range(monomer_dim)),
    )


def test_protein_processing_i_tick_does_not_replay_monomer_after_hint() -> None:
    if hasattr(runner_helpers._protein_processing_i_process, "cache_clear"):
        runner_helpers._protein_processing_i_process.cache_clear()

    process = runner_helpers._protein_processing_i_process(12345)
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    monomer_wids = list(process.unprocessed_monomer_wids)

    state = {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "monomer_wids": monomer_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_monomers": np.zeros(len(monomer_wids), dtype=np.float64),
        "oracle_after_substrates": np.full(len(substrate_wids), 17.0, dtype=np.float64),
        "oracle_after_monomers": np.full(len(monomer_wids), 100.0, dtype=np.float64),
    }

    result = runner_helpers._run_protein_processing_i_tick(seed=12345, tick=0, state=state)

    assert not np.array_equal(result["substrates"], state["oracle_after_substrates"])
    assert not np.array_equal(result["monomers"], state["oracle_after_monomers"])


def test_protein_processing_ii_tick_does_not_replay_monomer_after_hint() -> None:
    if hasattr(runner_helpers._protein_processing_ii_process, "cache_clear"):
        runner_helpers._protein_processing_ii_process.cache_clear()

    process = runner_helpers._protein_processing_ii_process(23456)
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    monomer_wids = list(process.unprocessed_monomer_wids)

    state = {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "monomer_wids": monomer_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_monomers": np.zeros(len(monomer_wids), dtype=np.float64),
        "oracle_after_substrates": np.full(len(substrate_wids), 19.0, dtype=np.float64),
        "oracle_after_monomers": np.full(len(monomer_wids), 101.0, dtype=np.float64),
    }

    result = runner_helpers._run_protein_processing_ii_tick(seed=23456, tick=0, state=state)

    assert not np.array_equal(result["substrates"], state["oracle_after_substrates"])
    assert not np.array_equal(result["monomers"], state["oracle_after_monomers"])


def test_protein_processing_i_primary_monomer_distance_fails(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_protein_processing_oracle(process_name="ProteinProcessingI")
    monkeypatch.setattr(runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner_helpers,
        "_protein_processing_i_process",
        lambda seed: _fake_protein_processing_process(monomer_dim=oracle["after_monomers"].shape[2]),
    )
    monkeypatch.setattr(
        runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "monomers": np.zeros_like(np.asarray(state["oracle_after_monomers"], dtype=np.float64)),
        },
    )

    payload = runner.run_design_a(
        process="ProteinProcessingI",
        seeds=list(range(10)),
        m_ticks=4,
        out_dir=tmp_path / "ppi_distance_fail",
        thresholds_path=tmp_path / "ppi_distance_fail_thresholds.json",
        bootstrap_B=16,
    )

    assert payload["result"]["verdict"] == "FAIL"
    assert payload["result"]["channels"]["monomers"]["verdict"] == "FAIL"


def test_protein_processing_ii_primary_monomer_distance_fails(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_protein_processing_oracle(process_name="ProteinProcessingII", substrate_dim=5)
    monkeypatch.setattr(runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner_helpers,
        "_protein_processing_ii_process",
        lambda seed: _fake_protein_processing_process(
            substrate_dim=oracle["after_substrates"].shape[2],
            monomer_dim=oracle["after_monomers"].shape[2],
        ),
    )
    monkeypatch.setattr(
        runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "monomers": np.zeros_like(np.asarray(state["oracle_after_monomers"], dtype=np.float64)),
        },
    )

    payload = runner.run_design_a(
        process="ProteinProcessingII",
        seeds=list(range(10)),
        m_ticks=4,
        out_dir=tmp_path / "ppii_distance_fail",
        thresholds_path=tmp_path / "ppii_distance_fail_thresholds.json",
        bootstrap_B=16,
    )

    assert payload["result"]["verdict"] == "FAIL"
    assert payload["result"]["channels"]["monomers"]["verdict"] == "FAIL"
