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

import l2_2_design_a_runner as runner


def _fake_oracle(*, seed_count: int = 3, tick_count: int = 4, dim: int = 8) -> dict[str, object]:
    base = np.arange(seed_count * tick_count * dim, dtype=np.float64).reshape(seed_count, tick_count, dim)
    return {
        "process": "Metabolism",
        "oracle_path": runner.runner_helpers._METABOLISM_ORACLE_PATH,
        "canonical_seed_count": seed_count,
        "n_ticks_available": tick_count,
        "before_substrates": base,
        "after_substrates": base + 5.0,
        "before_enzymes": np.ones((seed_count, tick_count, 3), dtype=np.float64),
        "before_bound_enzymes": np.zeros((seed_count, tick_count, 3), dtype=np.float64),
    }


def _fake_process(dim: int = 8, enzyme_dim: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        _sub_ids=tuple(f"S{idx}" for idx in range(dim)),
        enzyme_wids=tuple(f"E{idx}" for idx in range(enzyme_dim)),
    )


def _fake_transcription_oracle(
    *,
    tick_count: int = 4,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    rna_dim: int = 8,
) -> dict[str, object]:
    substrate_base = np.arange(tick_count * substrate_dim, dtype=np.float64).reshape(1, tick_count, substrate_dim)
    bound_base = np.arange(tick_count * enzyme_dim, dtype=np.float64).reshape(1, tick_count, enzyme_dim)
    rna_base = np.arange(tick_count * rna_dim, dtype=np.float64).reshape(1, tick_count, rna_dim) + 1.0
    return {
        "process": "Transcription",
        "oracle_path": runner.runner_helpers._TRANSCRIPTION_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": tick_count,
        "before_substrates": substrate_base,
        "before_enzymes": np.ones((1, tick_count, enzyme_dim), dtype=np.float64),
        "before_bound_enzymes": bound_base,
        "before_rnas": rna_base,
        "after_substrates": substrate_base + 5.0,
        "after_bound_enzymes": bound_base + 2.0,
        "after_rnas": rna_base + 3.0,
    }


def _fake_transcription_process(
    *,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    rna_dim: int = 8,
) -> SimpleNamespace:
    return SimpleNamespace(
        substrate_wids=tuple(f"NTP{idx}" for idx in range(substrate_dim)),
        enzyme_wids=tuple(f"RNAP{idx}" for idx in range(enzyme_dim)),
        gene_ids=tuple(f"TU_{idx:03d}" for idx in range(rna_dim)),
    )


def _fake_translation_oracle(
    *,
    tick_count: int = 4,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    monomer_dim: int = 8,
) -> dict[str, object]:
    substrate_base = np.arange(tick_count * substrate_dim, dtype=np.float64).reshape(1, tick_count, substrate_dim)
    bound_base = np.arange(tick_count * enzyme_dim, dtype=np.float64).reshape(1, tick_count, enzyme_dim)
    monomer_base = np.arange(tick_count * monomer_dim, dtype=np.float64).reshape(1, tick_count, monomer_dim) + 1.0
    return {
        "process": "Translation",
        "oracle_path": runner.runner_helpers._TRANSLATION_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": tick_count,
        "before_substrates": substrate_base,
        "before_enzymes": np.ones((1, tick_count, enzyme_dim), dtype=np.float64),
        "before_bound_enzymes": bound_base,
        "before_monomers": monomer_base,
        "before_mrnas": monomer_base + 7.0,
        "after_substrates": substrate_base + 5.0,
        "after_bound_enzymes": bound_base + 2.0,
        "after_monomers": monomer_base + 3.0,
    }


def _fake_translation_process(
    *,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    monomer_dim: int = 8,
) -> SimpleNamespace:
    return SimpleNamespace(
        aa_ids=tuple(f"AA_{idx}" for idx in range(substrate_dim)),
        enzyme_wids=tuple(f"RIBO_{idx}" for idx in range(enzyme_dim)),
        protein_ids=tuple(f"PROT_{idx:03d}" for idx in range(monomer_dim)),
    )


def _fake_protein_decay_oracle(
    *,
    tick_count: int = 4,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    monomer_dim: int = 8,
    complex_dim: int = 5,
) -> dict[str, object]:
    substrate_base = np.arange(tick_count * substrate_dim, dtype=np.float64).reshape(1, tick_count, substrate_dim)
    monomer_base = np.arange(tick_count * monomer_dim, dtype=np.float64).reshape(1, tick_count, monomer_dim) + 1.0
    complex_base = np.zeros((1, tick_count, complex_dim), dtype=np.float64)
    return {
        "process": "ProteinDecay",
        "oracle_path": runner.runner_helpers._PROTEIN_DECAY_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": tick_count,
        "before_substrates": substrate_base,
        "before_enzymes": np.ones((1, tick_count, enzyme_dim), dtype=np.float64),
        "before_monomers": monomer_base,
        "before_complexs": complex_base,
        "after_substrates": substrate_base,
        "after_monomers": monomer_base,
        "after_complexs": complex_base,
    }


def _fake_protein_decay_process(
    *,
    substrate_dim: int = 4,
    enzyme_dim: int = 3,
    monomer_dim: int = 8,
    complex_dim: int = 5,
) -> SimpleNamespace:
    return SimpleNamespace(
        substrate_wids=tuple(f"ATP_{idx}" for idx in range(substrate_dim)),
        enzyme_wids=tuple(f"PROTEASE_{idx}" for idx in range(enzyme_dim)),
        protein_wids=tuple(f"MONO_{idx:03d}" for idx in range(monomer_dim)),
        complex_wids=tuple(f"CPLX_{idx:03d}" for idx in range(complex_dim)),
    )


def test_constant_zero_oc_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_process())
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {"substrates": np.zeros_like(state["oracle_after_substrates"])},
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path,
        thresholds_path=tmp_path / "thresholds.json",
        bootstrap_B=16,
    )

    assert payload["result"]["verdict"] == "FAIL"
    assert payload["result"]["channels"]["substrates"]["verdict"] == "FAIL"


def test_oracle_laundering_warns(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_process())
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64)
        },
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path,
        thresholds_path=tmp_path / "thresholds.json",
        bootstrap_B=16,
    )

    assert any("TRIVIAL_RNG_LEAK" in warning for warning in payload["result"]["warnings"])


def test_off_by_one_seed_caught(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_oracle(seed_count=4)
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_process())

    def _shifted_seed(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, np.ndarray]:
        next_seed = (int(seed) + 1) % state["oracle_after_all"].shape[0]
        return {
            "substrates": np.asarray(state["oracle_after_all"][next_seed, tick], dtype=np.float64),
        }

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _shifted_seed)

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path,
        thresholds_path=tmp_path / "thresholds.json",
        bootstrap_B=16,
    )

    assert payload["result"]["verdict"] == "FAIL" or any(
        "SEED_ALIGNMENT_MISMATCH" in warning for warning in payload["result"]["warnings"]
    )


def test_transcription_oracle_laundering_flips_primary_channel(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_transcription_oracle()
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner.runner_helpers,
        "_transcription_process",
        lambda seed: _fake_transcription_process(rna_dim=oracle["after_rnas"].shape[2]),
    )

    def _honest_tick(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, np.ndarray]:
        assert process_name == "Transcription"
        return {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "RNAs": np.zeros_like(np.asarray(state["oracle_after_rnas"], dtype=np.float64)),
            "boundEnzymes": np.asarray(state["oracle_after_bound_enzymes"], dtype=np.float64),
        }

    def _cheat_tick(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, np.ndarray]:
        assert process_name == "Transcription"
        return {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "RNAs": np.asarray(state["oracle_after_rnas"], dtype=np.float64),
            "boundEnzymes": np.asarray(state["oracle_after_bound_enzymes"], dtype=np.float64),
        }

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _honest_tick)
    honest_payload = runner.run_design_a(
        process="Transcription",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / "honest",
        thresholds_path=tmp_path / "honest_thresholds.json",
        bootstrap_B=16,
    )

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _cheat_tick)
    cheated_payload = runner.run_design_a(
        process="Transcription",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / "cheated",
        thresholds_path=tmp_path / "cheated_thresholds.json",
        bootstrap_B=16,
    )

    assert honest_payload["result"]["verdict"] == "FAIL"
    assert honest_payload["result"]["channels"]["RNAs"]["verdict"] == "FAIL"
    # C5 added PRIMARY_CHANNEL_ORACLE_LAUNDERING detection that flips the
    # primary channel verdict to FAIL when OC exactly matches the oracle on
    # an RNAs primary channel for Transcription/RNADecay. Previously the
    # cheat surfaced only as a KARR_SINGLE_SEED_REUSED warning with PASS.
    assert cheated_payload["result"]["verdict"] == "FAIL"
    assert cheated_payload["result"]["channels"]["RNAs"]["verdict"] == "FAIL"
    assert any(
        "PRIMARY_CHANNEL_ORACLE_LAUNDERING" in warning
        for warning in cheated_payload["result"]["warnings"]
    )
    assert any(
        "KARR_SINGLE_SEED_REUSED" in warning for warning in cheated_payload["result"]["warnings"]
    )


def test_translation_oracle_laundering_flips_primary_channel(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_translation_oracle()
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner.runner_helpers,
        "_translation_process",
        lambda seed: _fake_translation_process(monomer_dim=oracle["after_monomers"].shape[2]),
    )

    def _honest_tick(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, np.ndarray]:
        assert process_name == "Translation"
        return {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "monomers": np.zeros_like(np.asarray(state["oracle_after_monomers"], dtype=np.float64)),
            "boundEnzymes": np.asarray(state["oracle_after_bound_enzymes"], dtype=np.float64),
        }

    def _cheat_tick(process_name: str, seed: int, tick: int, state: dict[str, object]) -> dict[str, np.ndarray]:
        assert process_name == "Translation"
        return {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "monomers": np.asarray(state["oracle_after_monomers"], dtype=np.float64),
            "boundEnzymes": np.asarray(state["oracle_after_bound_enzymes"], dtype=np.float64),
        }

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _honest_tick)
    honest_payload = runner.run_design_a(
        process="Translation",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / "honest",
        thresholds_path=tmp_path / "honest_thresholds.json",
        bootstrap_B=16,
    )

    monkeypatch.setattr(runner.runner_helpers, "run_oc_tick", _cheat_tick)
    cheated_payload = runner.run_design_a(
        process="Translation",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / "cheated",
        thresholds_path=tmp_path / "cheated_thresholds.json",
        bootstrap_B=16,
    )

    assert honest_payload["result"]["verdict"] == "FAIL"
    assert honest_payload["result"]["channels"]["monomers"]["verdict"] == "FAIL"
    assert cheated_payload["result"]["verdict"] == "PASS"
    assert cheated_payload["result"]["channels"]["monomers"]["verdict"] in {"SEED_NOISE", "PASS"}
    assert any(
        "KARR_SINGLE_SEED_REUSED" in warning for warning in cheated_payload["result"]["warnings"]
    )


def test_protein_decay_primary_exact_zero_can_be_marked_legitimate_noop(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_protein_decay_oracle()
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(
        runner.runner_helpers,
        "_protein_decay_process",
        lambda seed: _fake_protein_decay_process(
            monomer_dim=oracle["after_monomers"].shape[2],
            complex_dim=oracle["after_complexs"].shape[2],
        ),
    )
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64),
            "monomers": np.asarray(state["oracle_after_monomers"], dtype=np.float64),
            "complexs": np.asarray(state["oracle_after_complexs"], dtype=np.float64),
        },
    )

    payload = runner.run_design_a(
        process="ProteinDecay",
        seeds=[0, 1, 2],
        m_ticks=4,
        out_dir=tmp_path / "protein_decay",
        thresholds_path=tmp_path / "protein_decay_thresholds.json",
        bootstrap_B=16,
    )

    assert payload["result"]["verdict"] == "PASS"
    assert any(
        "PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE" in warning
        for warning in payload["result"]["warnings"]
    )
