from __future__ import annotations

from pathlib import Path

import yaml

from scripts.derive_input_spec import REPO_ROOT, derive_input_specs


def test_input_spec_rederivation_is_byte_identical(tmp_path: Path) -> None:
    summary = derive_input_specs(output_dir=tmp_path, process_names=("DNARepair",))

    assert summary["missing_fixtures"] == []
    assert summary["produced_processes"] == ["DNARepair"]
    assert summary["substrate_vocab_counts"]["DNARepair"]["matches_fixture"] is True

    committed_yaml = (REPO_ROOT / "data" / "karr_input_spec" / "DNARepair.yaml").read_bytes()
    regenerated_yaml = (tmp_path / "DNARepair.yaml").read_bytes()

    assert regenerated_yaml == committed_yaml


def test_input_spec_annotations_capture_stoich_provenance_and_local_resolution(tmp_path: Path) -> None:
    derive_input_specs(output_dir=tmp_path, process_names=("DNARepair",))

    payload = yaml.safe_load((tmp_path / "DNARepair.yaml").read_text(encoding="utf-8"))
    stoichiometry = payload["stoichiometry"]

    assert stoichiometry["reactions_source_field"] == "reactionStoichiometryMatrix"
    assert stoichiometry["reactions_small_molecule_source_field"] == "reactionSmallMoleculeStoichiometryMatrix"
    assert "reactionWholeCellModelIDs" not in stoichiometry
    assert stoichiometry["reactions"]["AP_endonuclease"] == {
        "consume": {
            "H2O": 1,
            "dRibose5P_dRibose5P": 1,
        },
        "produce": {
            "DR5P": 2,
            "H": 1,
        },
    }
    assert stoichiometry["reactions_small_molecule"]["AP_endonuclease"] == {
        "consume": {
            "H2O": 1,
        },
        "produce": {
            "H": 1,
        },
    }

    substrate_local = payload["role_groups"]["substrateMetaboliteLocalIndexs"]
    assert substrate_local["wids"] == payload["vocabularies"]["substrateWholeCellModelIDs"]
    assert substrate_local["identity_over_vocab"] is True


def test_input_spec_sentinel_index_fields_move_to_params(tmp_path: Path) -> None:
    derive_input_specs(output_dir=tmp_path, process_names=("ReplicationInitiation",))

    payload = yaml.safe_load((tmp_path / "ReplicationInitiation.yaml").read_text(encoding="utf-8"))

    assert payload["params"]["dnaARelease_remainingDnaAIndexs"] == [0, 0, 2, 2, 4, 4, 6, 6, 8, 8, 10, 10, 12, 12]
    assert "dnaARelease_remainingDnaAIndexs" not in payload["role_groups"]

    substrate_local = payload["role_groups"]["substrateMetaboliteLocalIndexs"]
    assert substrate_local["wids"] == payload["vocabularies"]["substrateWholeCellModelIDs"]
    assert substrate_local["identity_over_vocab"] is True
