"""Actual combined adapters must bind the helpers and fixtures they consume."""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as helpers

from opencell.vivarium import (
    karr_protein_modification,
    karr_rna_modification,
    karr_rna_processing,
    karr_trna_aminoacylation,
    protein_state,
)
from scripts.l22_evidence import schema


@pytest.mark.parametrize("name", ["RNAProcessing", "RNAModification"])
def test_rna_runtime_helper_is_registered_and_captured(name):
    path = Path(sys.modules["_rna_replay_inputs"].__file__).resolve()
    assert schema.PROCESS_DEPENDENCY_FILES[name]["rna_replay_inputs_module"] == path
    sources = {Path(source["path"]): source for source in helpers.capture_runtime_inputs(name)}
    assert sources[path]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    if name == "RNAProcessing":
        parser = Path(karr_trna_aminoacylation.__file__).resolve()
        assert sources[parser]["sha256"] == hashlib.sha256(parser.read_bytes()).hexdigest()
        assert karr_rna_processing._parse_wid_array is karr_trna_aminoacylation._parse_wid_array
        assert karr_rna_processing._resolve_fixture_path is karr_trna_aminoacylation._resolve_fixture_path


@pytest.mark.parametrize(
    ("name", "factory", "expected"),
    [
        ("RNAProcessing", "_rna_processing_process", {"RNAProcessing", "Rna"}),
        ("RNAModification", "_rna_modification_process", {"RNAModification", "RNAProcessing"}),
        (
            "ProteinModification",
            "_protein_modification_process",
            {"ProteinModification", "MacromolecularComplexation",
             "ProteinTranslocation", "TerminalOrganelleAssembly"},
        ),
    ],
)
def test_actual_fresh_constructor_fixture_reads_are_bound(monkeypatch, name, factory, expected):
    seen = set()
    for module in (
        karr_protein_modification, karr_rna_modification, karr_rna_processing,
        karr_trna_aminoacylation, protein_state,
    ):
        loadmat = module.loadmat

        def record(path, *args, _loadmat=loadmat, **kwargs):
            seen.add(Path(path).resolve())
            return _loadmat(path, *args, **kwargs)

        monkeypatch.setattr(module, "loadmat", record)
    karr_protein_modification._canonical_complex_wids.cache_clear()
    karr_rna_modification._nascent_rna_wids.cache_clear()
    sources = helpers.capture_runtime_inputs(name)
    process = getattr(helpers, factory).__wrapped__(0)
    assert process.name == "karr_" + factory.removeprefix("_").removesuffix("_process")
    bound = {Path(source["path"]) for source in sources}
    assert seen <= bound, f"unbound actual fixture reads: {seen - bound}"
    assert {path.stem.removesuffix("_flat") for path in seen} == expected
    helpers.verify_input_sources(sources)


def test_pm_dispatch_has_no_folding_constructor_or_obsolete_dependencies():
    tree = ast.parse(Path(helpers.__file__).read_text(encoding="utf-8"))
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    calls = {
        node.func.id
        for name in ("_run_protein_modification_tick", "_protein_modification_process")
        for node in ast.walk(functions[name])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "KarrProteinModificationProcess" in calls
    assert "KarrProteinFoldingProcess" not in calls
    assert "_protein_folding_process" not in calls
    assert "protein_folding_module" not in schema.PROCESS_DEPENDENCY_FILES["ProteinModification"]
    assert schema.PROCESS_PARAMETER_FIXTURES["ProteinModification"] == ("MacromolecularComplexation",)
    sources = helpers.capture_runtime_inputs("ProteinModification")
    paths = {Path(source["path"]).name for source in sources}
    assert "ProteinFolding_flat.mat" not in paths
    assert "RibosomeAssembly_flat.mat" not in paths
    assert "ProteinTranslocation_flat.mat" in paths
    assert "TerminalOrganelleAssembly_flat.mat" in paths


@pytest.mark.parametrize("name", ["RNAProcessing", "RNAModification"])
def test_capture_rejects_stale_rna_fixture_metadata(monkeypatch, name):
    original = helpers.load_fixture_channel_wids

    def stale(*args):
        return ("stale::wid",)

    stale.__wrapped__ = original.__wrapped__
    monkeypatch.setattr(helpers, "load_fixture_channel_wids", stale)
    with pytest.raises(ValueError, match="RNA fixture inputs differ from cached"):
        helpers.capture_runtime_inputs(name)


def test_capture_rejects_stale_rm_nascent_membership(monkeypatch):
    original = karr_rna_modification._nascent_rna_wids

    def stale():
        return frozenset()

    stale.__wrapped__ = original.__wrapped__
    monkeypatch.setattr(karr_rna_modification, "_nascent_rna_wids", stale)
    with pytest.raises(ValueError, match="cached nascent WIDs"):
        helpers.capture_runtime_inputs("RNAModification")
