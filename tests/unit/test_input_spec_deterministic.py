from __future__ import annotations

from pathlib import Path

from scripts.derive_input_spec import REPO_ROOT, derive_input_specs


def test_input_spec_rederivation_is_byte_identical(tmp_path: Path) -> None:
    summary = derive_input_specs(output_dir=tmp_path, process_names=("DNARepair",))

    assert summary["missing_fixtures"] == []
    assert summary["produced_processes"] == ["DNARepair"]
    assert summary["substrate_vocab_counts"]["DNARepair"]["matches_fixture"] is True

    committed_yaml = (REPO_ROOT / "data" / "karr_input_spec" / "DNARepair.yaml").read_bytes()
    regenerated_yaml = (tmp_path / "DNARepair.yaml").read_bytes()

    assert regenerated_yaml == committed_yaml
