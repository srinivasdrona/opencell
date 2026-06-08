from __future__ import annotations

import sys
from pathlib import Path

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
        "ProteinDecay",
    }.issubset(runner.SUPPORTED_PROCESSES)


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
