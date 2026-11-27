"""Small file-backed checks for the common Design-A consumed-input contract."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as helpers

from tests.vivarium.test_l2_2_design_a_ensemble_loader import _write_mat_trace


def _write_seed(root: Path, seed: int, *, embedded_seed: int | None = None) -> Path:
    path = root / "data" / "m1_sources" / "karr_native" / f"per_process_traces_v2_s{seed:03d}" / "RNADecay_100ticks.mat"
    _write_mat_trace(
        path,
        states_before={
            "substrates": [np.asarray([seed + 1.0])],
            "enzymes": [np.asarray([1.0])],
            "boundEnzymes": [np.asarray([0.0])],
            "RNAs": [np.asarray([seed + 1.0])],
        },
        states_after={
            "substrates": [np.asarray([seed + 2.0])],
            "RNAs": [np.asarray([seed + 2.0])],
        },
    )
    with h5py.File(path, "a") as handle:
        handle["metadata"].create_dataset("rng_seed", data=[seed if embedded_seed is None else embedded_seed])
    return path


def test_loader_preserves_load_time_hashes_and_noncontiguous_seed_identities(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "_REPO_ROOT", tmp_path)
    paths = [_write_seed(tmp_path, seed) for seed in (0, 2)]
    oracle = helpers._load_v2_ensemble("RNADecay", max_seeds=3)
    assert oracle["seed_ids"] == [0, 2]
    assert [source["seed"] for source in oracle["input_sources"]] == [0, 2]
    assert [source["sha256"] for source in oracle["input_sources"]] == [
        hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    ]
    np.testing.assert_array_equal(oracle["before_substrates"][:, 0, 0], [1.0, 3.0])
    paths[1].write_bytes(paths[1].read_bytes() + b"#")
    with pytest.raises(ValueError, match="source hash drift"):
        helpers.verify_input_sources(oracle["input_sources"])


def test_loader_rejects_embedded_seed_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "_REPO_ROOT", tmp_path)
    _write_seed(tmp_path, 1, embedded_seed=0)
    with pytest.raises(ValueError, match="seed identity mismatch"):
        helpers._load_v2_ensemble("RNADecay", max_seeds=2)


@pytest.mark.parametrize("kind", ["parameter", "authority"])
def test_runtime_input_capture_rejects_drift_before_attestation(tmp_path, monkeypatch, kind):
    for relative in (
        "opencell/vivarium/karr_protein_processing_ii.py",
        "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat",
        "data/karr_fixtures/per_process/ProteinTranslocation_flat.mat",
        "data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, target)
    monkeypatch.setattr(helpers, "_REPO_ROOT", tmp_path)
    sources = helpers.capture_runtime_inputs("ProteinProcessingII")
    helpers.verify_input_sources(sources)
    path = tmp_path / (
        "data/karr_fixtures/per_process/ProteinTranslocation_flat.mat"
        if kind == "parameter" else "opencell/vivarium/karr_protein_processing_ii.py"
    )
    path.write_bytes(path.read_bytes() + b"#")
    with pytest.raises(ValueError, match="source hash drift"):
        helpers.verify_input_sources(sources)


def test_source_merge_deduplicates_shared_files_and_rejects_replacement(tmp_path):
    path = tmp_path / "shared.mat"
    path.write_bytes(b"loaded input")
    source = helpers.capture_input_source(path)
    assert helpers.merge_input_sources([source], [source]) == [source]
    path.write_bytes(b"never loaded replacement")
    replacement = helpers.capture_input_source(path)
    with pytest.raises(ValueError, match="Conflicting consumed input"):
        helpers.merge_input_sources([source], [replacement])


def test_runtime_capture_rechecks_import_time_protein_membership(monkeypatch):
    from opencell.vivarium import protein_state

    monkeypatch.setattr(protein_state, "MIGRATED_WIDS", protein_state.MIGRATED_WIDS[:-1])
    with pytest.raises(ValueError, match="authority inputs differ from cached MIGRATED_WIDS"):
        helpers.capture_runtime_inputs("ProteinProcessingII")


def test_formatter_rejects_unbound_arrays(tmp_path):
    with pytest.raises(ValueError, match="lack load-time source hashes"):
        helpers._format_ensemble_oracle(
            process_name="Metabolism", oracle_path=tmp_path / "not-loaded.mat",
            seed_paths=[tmp_path / "not-loaded.mat"],
            before_channels={"substrates": np.ones((1, 1, 1))},
            after_channels={"substrates": np.ones((1, 1, 1))},
        )
