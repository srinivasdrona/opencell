"""Consumed complex authority must match attested bytes, even with a warm cache."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat, savemat

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as helpers

from opencell.vivarium import karr_protein_modification as pm
from opencell.vivarium import karr_protein_translocation as pt

_LANES = {
    "ProteinModification": (pm, "_protein_modification_process", "MG_109_DIMER"),
    "ProteinTranslocation": (pt, "_protein_translocation_process", "MG_0001_048"),
}
_AUTHORITY_CASES = [
    pytest.param("ProteinModification", "MacromolecularComplexation", id="PM-macromol"),
    pytest.param("ProteinTranslocation", "MacromolecularComplexation", id="PT-macromol"),
    pytest.param("ProteinTranslocation", "RibosomeAssembly", id="PT-ribosome-only"),
]
_INTEGRITY_ERROR = re.compile(
    r"Consumed (?:.+ inputs differ from cached .+|input source hash drift: .+)"
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_wids(path, field="complexWholeCellModelIDs"):
    fixture = loadmat(path, squeeze_me=True, struct_as_record=False)["data"].fixture
    return tuple(np.asarray(getattr(fixture, field), dtype=object).ravel().astype(str))


def _replace_member(path, old, new):
    before = _fixture_wids(path)
    assert old in before and new not in before
    mat = loadmat(path)
    cells = mat["data"]["fixture"][0, 0]["complexWholeCellModelIDs"][0, 0]
    for index, wid in enumerate(before):
        if wid == old:
            cells.ravel()[index] = np.asarray([new])
    savemat(
        path, {key: value for key, value in mat.items() if not key.startswith("__")},
        long_field_names=True,
    )
    assert _fixture_wids(path) == tuple(new if wid == old else wid for wid in before)


def _clear_membership_cache(module):
    clear = getattr(module._canonical_complex_wids, "cache_clear", None)
    if clear is not None:
        clear()


@pytest.fixture
def copied_authority(tmp_path, monkeypatch):
    touched = []

    def copy(name):
        module, factory, target = _LANES[name]
        touched.append(module)
        _clear_membership_cache(module)
        authority_names = ["MacromolecularComplexation"]
        if name == "ProteinTranslocation":
            authority_names.append("RibosomeAssembly")
        fixture_names = {
            name, *authority_names, "ProteinTranslocation", "TerminalOrganelleAssembly",
        }
        fixtures = tmp_path / "data" / "karr_fixtures" / "per_process"
        fixtures.mkdir(parents=True)
        for fixture_name in fixture_names:
            relative = Path("data/karr_fixtures/per_process") / f"{fixture_name}_flat.mat"
            shutil.copyfile(REPO_ROOT / relative, tmp_path / relative)
        relative = Path("opencell/vivarium") / f"{module.__name__.split('.')[-1]}.py"
        (tmp_path / relative).parent.mkdir(parents=True)
        shutil.copyfile(REPO_ROOT / relative, tmp_path / relative)
        monkeypatch.setattr(helpers, "_REPO_ROOT", tmp_path)
        monkeypatch.setattr(
            module, "_MACROMOLECULAR_COMPLEXATION_FIXTURE_PATH",
            fixtures / "MacromolecularComplexation_flat.mat",
        )
        if name == "ProteinTranslocation":
            monkeypatch.setattr(
                module, "_RIBOSOME_ASSEMBLY_FIXTURE_PATH",
                fixtures / "RibosomeAssembly_flat.mat",
            )
        cls = getattr(module, f"Karr{name}Process")
        monkeypatch.setitem(cls.defaults, "fixture_path", str(fixtures / f"{name}_flat.mat"))
        paths = {
            authority_name: fixtures / f"{authority_name}_flat.mat"
            for authority_name in authority_names
        }
        return name, module, getattr(helpers, factory).__wrapped__, target, paths

    yield copy
    monkeypatch.undo()
    for module in touched:
        _clear_membership_cache(module)


def _seed_ribosome_membership(paths, name, target):
    ribosome = paths["RibosomeAssembly"]
    process_fixture = ribosome.with_name(f"{name}_flat.mat")
    enzyme_wids = set(_fixture_wids(process_fixture, "enzymeWholeCellModelIDs"))
    donors = set(_fixture_wids(ribosome)) - enzyme_wids - pm._SPECIAL_COMPLEX_WIDS
    assert donors and target not in _fixture_wids(ribosome)
    _replace_member(ribosome, sorted(donors)[0], target)


def _current_membership(paths):
    return frozenset().union(
        *(_fixture_wids(path) for path in paths.values()), pm._SPECIAL_COMPLEX_WIDS,
    )


def _classification(owner):
    return {
        "complex": list(owner.complex_enzyme_wids),
        "monomer": list(owner.monomer_enzyme_wids),
    }


def _expected_classification(owner, membership):
    return {
        "complex": [wid for wid in owner.enzyme_wids if wid in membership],
        "monomer": [wid for wid in owner.enzyme_wids if wid not in membership],
    }


def _assert_current_sources(sources, paths):
    records = {source["path"]: source["sha256"] for source in sources}
    for path in paths.values():
        assert records[str(path.resolve())] == _sha(path)


def _exercise_contract(case, warm, old_hashes, tmp_path):
    name, module, make, target, paths = case
    current = _current_membership(paths)
    expected = _expected_classification(warm, current)
    sources, owner, rejection = None, None, None
    # Do not clear the genuine warmed membership cache before this action.
    try:
        sources = helpers.capture_runtime_inputs(name)
        _assert_current_sources(sources, paths)
        owner = make(1)
        assert owner is not warm and type(owner) is type(warm)
        helpers.verify_input_sources(sources)
    except ValueError as exc:
        if not _INTEGRITY_ERROR.fullmatch(str(exc)):
            raise
        rejection = str(exc)

    actual = _classification(owner) if owner is not None else None
    # This post-action clear derives a separate current-fixture constructor control.
    _clear_membership_cache(module)
    reference = make(1)
    assert reference is not warm and reference is not owner
    assert _classification(reference) == expected
    witness = {
        "process": name,
        "target_enzyme": target,
        "warm_classification": _classification(warm),
        "actual_classification": actual,
        "expected_from_current_fixtures": expected,
        "post_action_uncached_classification": _classification(reference),
        "authority_memberships": {
            source: list(_fixture_wids(path)) for source, path in paths.items()
        },
        "old_hashes": old_hashes,
        "current_hashes": {str(path): _sha(path) for path in paths.values()},
        "captured_sources": sources,
        "integrity_rejection": rejection,
    }
    (tmp_path / "authority-witness.json").write_text(json.dumps(witness, indent=2) + "\n")
    assert rejection is not None or actual == expected, (
        f"{name} runtime capture and source verification accepted current fixture hashes "
        f"while a fresh actual owner consumed stale complex authority for {target}: "
        f"actual={actual}, expected={expected}"
    )


@pytest.mark.parametrize("name,authority_source", _AUTHORITY_CASES)
def test_unchanged_warmed_authority_is_accepted(copied_authority, name, authority_source, tmp_path):
    case = copied_authority(name)
    _, module, make, target, paths = case
    if authority_source == "RibosomeAssembly":
        _seed_ribosome_membership(paths, name, target)
        _replace_member(paths["MacromolecularComplexation"], target, f"removed::{target}")
    expected_membership = _current_membership(paths)
    warm = make(0)
    assert target in warm.complex_enzyme_wids
    assert _classification(warm) == _expected_classification(warm, expected_membership)
    assert target in module._canonical_complex_wids()
    hashes = {str(path): _sha(path) for path in paths.values()}
    for _ in range(2):
        sources = helpers.capture_runtime_inputs(name)
        _assert_current_sources(sources, paths)
        owner = make(1)
        assert owner is not warm
        assert _classification(owner) == _expected_classification(owner, expected_membership)
        helpers.verify_input_sources(sources)
    assert hashes == {str(path): _sha(path) for path in paths.values()}
    (tmp_path / "unchanged-witness.json").write_text(json.dumps({
        "process": name, "authority_source": authority_source, "hashes": hashes,
        "classification": _classification(owner), "captured_sources": sources,
    }, indent=2) + "\n")


@pytest.mark.parametrize("name,authority_source", _AUTHORITY_CASES)
def test_runtime_capture_does_not_certify_stale_actual_authority(
    copied_authority, name, authority_source, tmp_path,
):
    case = copied_authority(name)
    _, module, make, target, paths = case
    if authority_source == "RibosomeAssembly":
        _seed_ribosome_membership(paths, name, target)
        _replace_member(paths["MacromolecularComplexation"], target, f"removed::{target}")
    warm = make(0)
    assert target in warm.complex_enzyme_wids
    assert target in module._canonical_complex_wids()
    assert _classification(warm) == _expected_classification(warm, _current_membership(paths))
    old_hashes = {str(path): _sha(path) for path in paths.values()}
    _replace_member(paths[authority_source], target, f"removed::{target}")
    assert old_hashes[str(paths[authority_source])] != _sha(paths[authority_source])
    assert target not in _current_membership(paths), "the other PT authority must not mask removal"
    _exercise_contract(case, warm, old_hashes, tmp_path)


@pytest.mark.parametrize("removed_source", ["MacromolecularComplexation", "RibosomeAssembly"])
def test_pt_effective_union_keeps_membership_from_other_authority(
    copied_authority, removed_source, tmp_path,
):
    case = copied_authority("ProteinTranslocation")
    name, module, make, target, paths = case
    _seed_ribosome_membership(paths, name, target)
    assert all(target in _fixture_wids(path) for path in paths.values())
    warm = make(0)
    assert target in warm.complex_enzyme_wids
    assert target in module._canonical_complex_wids()
    old_membership = _current_membership(paths)
    old_hashes = {str(path): _sha(path) for path in paths.values()}
    _replace_member(paths[removed_source], target, f"removed::{target}")
    assert target not in _fixture_wids(paths[removed_source])
    enzymes = frozenset(warm.enzyme_wids)
    assert _current_membership(paths) & enzymes == old_membership & enzymes
    _exercise_contract(case, warm, old_hashes, tmp_path)
