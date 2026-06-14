from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


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

import l2_2_design_a_runner as runner  # noqa: E402


def _fake_metabolism_oracle(*, tick_count: int = 2, dim: int = 4) -> dict[str, object]:
    base = np.arange(tick_count * dim, dtype=np.float64).reshape(1, tick_count, dim)
    return {
        "process": "Metabolism",
        "oracle_path": runner.runner_helpers._METABOLISM_ORACLE_PATH,
        "canonical_seed_count": 1,
        "n_ticks_available": tick_count,
        "before_substrates": base,
        "after_substrates": base + 1.0,
        "before_enzymes": np.ones((1, tick_count, 2), dtype=np.float64),
        "before_bound_enzymes": np.zeros((1, tick_count, 2), dtype=np.float64),
    }


def _fake_metabolism_process(dim: int = 4) -> SimpleNamespace:
    return SimpleNamespace(
        _sub_ids=tuple(f"S{idx}" for idx in range(dim)),
        enzyme_wids=tuple("E0 E1".split()),
    )


def _projection_tick_result(
    *,
    substrate_vector: np.ndarray,
    oc_fork_delta: float,
    karr_fork_delta: float,
    oc_ber_delta: float,
    karr_ber_delta: float,
    oc_ner_delta: float = 0.0,
    karr_ner_delta: float = 0.0,
    oc_event: bool = False,
    karr_event: bool = False,
) -> dict[str, object]:
    return {
        "substrates": np.asarray(substrate_vector, dtype=np.float64),
        "projection_state": {
            "before": {
                "chromosome": {
                    "fork_position_bp": {"left": 0.0},
                    "repair_events_cumulative": [],
                    "repair_count_by_pathway": {"ber": 0.0, "ner": 0.0},
                }
            },
            "after": {
                "chromosome": {
                    "fork_position_bp": {"left": float(oc_fork_delta)},
                    "repair_events_cumulative": ([{"id": "oc"}] if oc_event else []),
                    "repair_count_by_pathway": {"ber": float(oc_ber_delta), "ner": float(oc_ner_delta)},
                }
            },
        },
        "karr_projection_state": {
            "before": {
                "chromosome": {
                    "fork_position_bp": {"left": 0.0},
                    "repair_events_cumulative": [],
                    "repair_count_by_pathway": {"ber": 0.0, "ner": 0.0},
                }
            },
            "after": {
                "chromosome": {
                    "fork_position_bp": {"left": float(karr_fork_delta)},
                    "repair_events_cumulative": ([{"id": "karr"}] if karr_event else []),
                    "repair_count_by_pathway": {"ber": float(karr_ber_delta), "ner": float(karr_ner_delta)},
                }
            },
        },
    }


def test_load_catalog_filters_to_in_scope_and_normalizes_channels(tmp_path: Path) -> None:
    catalog_path = tmp_path / "PROCESS_CATALOG.yaml"
    catalog_path.write_text(
        """
schema_version: 1
buckets:
  ALGORITHMIC_SHALLOW:
    rationale: "distributional surface present"
  DETERMINISTIC:
    rationale: "no RNG"
processes:
  - name: RNADecay
    bucket: ALGORITHMIC_SHALLOW
    in_scope_L2_2: true
    output_channels: [substrates, rnas]
    primary_channel: rnas
  - name: ChromosomeCondensation
    bucket: DETERMINISTIC
    in_scope_L2_2: false
    output_channels: []
    primary_channel: null
""".strip(),
        encoding="utf-8",
    )

    runner._load_catalog.cache_clear()
    runner._load_catalog_all.cache_clear()
    runner._load_catalog_document.cache_clear()
    try:
        catalog = runner._load_catalog(catalog_path)
        assert set(catalog) == {"RNADecay"}
        assert catalog["RNADecay"]["output_channels"] == ("substrates", "RNAs")
        assert catalog["RNADecay"]["primary_channel"] == "RNAs"
    finally:
        runner._load_catalog.cache_clear()
        runner._load_catalog_all.cache_clear()
        runner._load_catalog_document.cache_clear()


def test_catalog_backed_process_tables_match_real_catalog() -> None:
    catalog = runner._load_catalog()

    assert runner._PROCESS_BUCKET["Metabolism"] == catalog["Metabolism"]["bucket"]
    assert runner._PROCESS_OUTPUT_CHANNELS["Transcription"] == tuple(catalog["Transcription"]["output_channels"])
    assert runner._PROCESS_PRIMARY_CHANNEL["RNADecay"] == catalog["RNADecay"]["primary_channel"]
    assert {
        "Metabolism",
        "Translation",
        "Transcription",
        "RNADecay",
        "RNAProcessing",
        "RNAModification",
        "tRNAAminoacylation",
        "ProteinModification",
        "ProteinFolding",
        "ProteinTranslocation",
        "ProteinDecay",
        "RibosomeAssembly",
        "MacromolecularComplexation",
    }.issubset(runner.SUPPORTED_PROCESSES)


def test_macromol_sample_process_and_observable_wids_are_wired() -> None:
    process = runner._process_sample_process("MacromolecularComplexation")
    wids = runner._observable_wids("MacromolecularComplexation", process)

    assert process.__class__.__name__ == "MacromolecularComplexationProcess"
    assert len(wids["substrates"]) == 210
    assert len(wids["monomers"]) == 208
    assert len(wids["complexs"]) == 147


def test_metabolism_sample_process_and_observable_wids_are_wired() -> None:
    process = runner._process_sample_process("Metabolism")
    wids = runner._observable_wids("Metabolism", process)

    assert process.__class__.__name__ == "KarrMetabolismProcess"
    assert len(wids["substrates"]) == 585
    assert len(wids["enzymes"]) == 104
    assert wids["boundEnzymes"] == wids["enzymes"]


def test_rna_primary_sample_processes_expose_combined_rna_wids() -> None:
    expected_lengths = {
        "RNAProcessing": 693,
        "RNAModification": 694,
        "tRNAAminoacylation": 74,
    }

    for process_name, expected_len in expected_lengths.items():
        process = runner._process_sample_process(process_name)
        wids = runner._observable_wids(process_name, process)

        assert "RNAs" in wids
        assert len(wids["RNAs"]) == expected_len


def test_batch_c_monomer_sample_processes_expose_monomer_wids() -> None:
    expected_lengths = {
        "ProteinModification": 40,
        "ProteinFolding": 964,
        "ProteinTranslocation": 482,
    }

    for process_name, expected_len in expected_lengths.items():
        process = runner._process_sample_process(process_name)
        wids = runner._observable_wids(process_name, process)

        assert "monomers" in wids
        assert len(wids["monomers"]) == expected_len


def test_ribosome_assembly_sample_process_exposes_complex_and_rna_wids() -> None:
    process = runner._process_sample_process("RibosomeAssembly")
    wids = runner._observable_wids("RibosomeAssembly", process)

    assert process.__class__.__name__ == "KarrRibosomeAssemblyProcess"
    assert wids["complexs"] == ["RIBOSOME_30S", "RIBOSOME_50S"]
    assert len(wids["monomers"]) > 0
    assert len(wids["RNAs"]) == 3


def test_run_design_a_rejects_out_of_scope_process_with_bucket_rationale(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"out of L2\.2 scope: bucket=DETERMINISTIC; rationale=.*no RNG"):
        runner.run_design_a(
            process="ChromosomeCondensation",
            seeds=[0],
            m_ticks=1,
            out_dir=tmp_path,
            bootstrap_B=1,
        )


def test_run_design_a_rejects_in_scope_process_without_runner_implementation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"in scope in PROCESS_CATALOG\.yaml \(bucket=ALGORITHMIC_DEEP\)"):
        runner.run_design_a(
            process="DNARepair",
            seeds=[0],
            m_ticks=1,
            out_dir=tmp_path,
            bootstrap_B=1,
        )


def test_run_design_a_emits_per_component_block_for_primary_projection_distance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_metabolism_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_metabolism_process())
    monkeypatch.setattr(runner, "_process_primary_distance", lambda process: "per_component_scaled")
    monkeypatch.setattr(
        runner,
        "_process_primary_projection",
        lambda process: ("delta_fork_position_bp.left", "repair_count_by_pathway.ber_delta"),
    )
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: _projection_tick_result(
            substrate_vector=np.zeros_like(np.asarray(state["oracle_after_substrates"], dtype=np.float64)),
            oc_fork_delta=10.0 + tick,
            karr_fork_delta=5.0 + tick,
            oc_ber_delta=2.0,
            karr_ber_delta=1.0,
        ),
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0],
        m_ticks=2,
        out_dir=tmp_path / "per_component",
        bootstrap_B=4,
    )

    primary = payload["result"]["channels"]["substrates"]
    assert primary["aggregation"] == "per_component_scaled"
    assert "per_component" in primary
    assert primary["per_component"]["joint_verdict"] in {"PASS", "FAIL"}
    assert set(primary["per_component"]["component_verdicts"]) == {
        "delta_fork_position_bp.left",
        "repair_count_by_pathway.ber_delta",
    }


def test_run_design_a_emits_hurdle_block_for_primary_projection_distance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_metabolism_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_metabolism_process())
    monkeypatch.setattr(
        runner,
        "_process_primary_distance",
        lambda process: "hurdle_event_rate_plus_conditional_scaled_distance",
    )
    monkeypatch.setattr(
        runner,
        "_process_primary_projection",
        lambda process: (
            "repair_event_present",
            "repair_count_by_pathway.ber_delta",
            "repair_count_by_pathway.ner_delta",
        ),
    )
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: _projection_tick_result(
            substrate_vector=np.zeros_like(np.asarray(state["oracle_after_substrates"], dtype=np.float64)),
            oc_fork_delta=0.0,
            karr_fork_delta=0.0,
            oc_ber_delta=4.0 if tick == 0 else 0.0,
            karr_ber_delta=2.0 if tick == 0 else 0.0,
            oc_ner_delta=1.0 if tick == 0 else 0.0,
            karr_ner_delta=1.0 if tick == 0 else 0.0,
            oc_event=(tick == 0),
            karr_event=(tick == 0),
        ),
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0],
        m_ticks=2,
        out_dir=tmp_path / "hurdle",
        bootstrap_B=4,
    )

    primary = payload["result"]["channels"]["substrates"]
    assert primary["aggregation"] == "hurdle_event_rate_plus_conditional_scaled_distance"
    assert "hurdle" in primary
    assert primary["hurdle"]["event_rate_diff"] == pytest.approx(0.0)
    assert "component_1" in primary["hurdle"]["conditional_w1_per_component"]


def test_event_channels_are_deferred_from_normal_gating(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: _fake_metabolism_oracle())
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_metabolism_process())
    monkeypatch.setattr(runner, "_process_event_channels", lambda process: ("substrates",))
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64)
        },
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0],
        m_ticks=2,
        out_dir=tmp_path / "event_deferred",
        bootstrap_B=4,
    )

    primary = payload["result"]["channels"]["substrates"]
    assert primary["is_event_channel"] is True
    assert primary["verdict"] == "EVENT_CHANNEL_DEFERRED"
    assert payload["summary"]["processes"]["Metabolism"]["n_event_deferred"] == 1


def test_run_design_a_merges_loader_warnings_into_result(monkeypatch, tmp_path: Path) -> None:
    oracle = _fake_metabolism_oracle(tick_count=1, dim=2)
    oracle["warnings"] = ["KARR_LEGACY_SINGLE_SEED_FALLBACK: synthetic test warning"]
    monkeypatch.setattr(runner.runner_helpers, "load_karr_oracle", lambda process: oracle)
    monkeypatch.setattr(runner.runner_helpers, "_metabolism_process", lambda seed: _fake_metabolism_process(dim=2))
    monkeypatch.setattr(
        runner.runner_helpers,
        "run_oc_tick",
        lambda process_name, seed, tick, state: {
            "substrates": np.asarray(state["oracle_after_substrates"], dtype=np.float64)
        },
    )

    payload = runner.run_design_a(
        process="Metabolism",
        seeds=[0],
        m_ticks=1,
        out_dir=tmp_path / "loader_warning_merge",
        bootstrap_B=4,
    )

    assert any(
        "KARR_LEGACY_SINGLE_SEED_FALLBACK" in warning
        for warning in payload["result"]["warnings"]
    )
    assert payload["result"]["canonical_seed_count"] == 1
