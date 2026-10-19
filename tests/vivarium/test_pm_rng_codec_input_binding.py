"""Narrow actual-PM-codec capture guards; no new dependency-hashing framework."""

from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT), str(_ROOT / "tests" / "vivarium")]

import opencell
import _l2_2_design_a_runner_helpers as helpers
from opencell.util import mcg16807_state_codec as codec
from opencell.vivarium import karr_protein_modification as pm
from scripts.l22_evidence import catalog, schema
from tests.scripts._l22_ast_import_audit import first_party_import_files
from tests.scripts.test_l22_evidence_ast_completeness import _covered_files_for

assert _ROOT in Path(opencell.__file__).resolve().parents
assert Path(pm.__file__).resolve() == _ROOT / "opencell/vivarium/karr_protein_modification.py"
assert Path(codec.__file__).resolve() == _ROOT / "opencell/util/mcg16807_state_codec.py"

_PM = "ProteinModification"
_KEY = "mcg16807_state_codec_module"
_CODEC = Path(codec.__file__).resolve()


def _assert_actual_codec_binding(sources) -> None:
    assert pm.seed_state is codec.seed_state, "actual codec seed function differs"
    assert pm.draw_and_advance is codec.draw_and_advance, "actual codec draw function differs"
    assert Path(inspect.getsourcefile(pm.seed_state)).resolve() == _CODEC
    assert Path(inspect.getsourcefile(pm.draw_and_advance)).resolve() == _CODEC
    assert schema.PROCESS_DEPENDENCY_FILES[_PM].get(_KEY) == _CODEC, "actual codec not registered"
    captured = {Path(row["path"]).resolve(): row for row in sources}
    assert _CODEC in captured, "actual codec source not captured"
    assert captured[_CODEC]["sha256"] == hashlib.sha256(_CODEC.read_bytes()).hexdigest()
    helpers.verify_input_sources(sources)


def test_pm_real_codec_calls_are_bound_by_actual_runtime_capture(monkeypatch) -> None:
    sources = helpers.capture_runtime_inputs(_PM)
    assert len(sources) == 13
    _assert_actual_codec_binding(sources)
    seed_function, draw_function = pm.seed_state, pm.draw_and_advance
    seeded, drawn = [], []

    def observe_seed(seed):
        seeded.append(seed)
        return seed_function(seed)

    def observe_draw(state):
        drawn.append(state)
        return draw_function(state)

    monkeypatch.setattr(pm, "seed_state", observe_seed)
    monkeypatch.setattr(pm, "draw_and_advance", observe_draw)
    first = helpers._protein_modification_process.__wrapped__(0)
    second = helpers._protein_modification_process.__wrapped__(0)
    assert first._rng is not second._rng
    second_before = second._rng.get_state()
    observed = first._rng.random((2, 3))
    encoded = codec.seed_state(0)
    expected, expected_states = [], []
    for _ in range(6):
        expected_states.append(encoded)
        value, encoded = codec.draw_and_advance(encoded)
        expected.append(value)
    assert seeded == [0, 0]
    assert drawn == expected_states
    np.testing.assert_array_equal(observed.ravel(order="F"), expected)
    assert second._rng.get_state() == second_before
    assert first._rng.get_state() != second_before
    helpers.verify_input_sources(sources)


def test_pm_codec_omission_exposes_real_import_and_actual_capture_gap(monkeypatch) -> None:
    reduced = {key: value for key, value in schema.PROCESS_DEPENDENCY_FILES[_PM].items() if key != _KEY}
    monkeypatch.setitem(schema.PROCESS_DEPENDENCY_FILES, _PM, reduced)
    imports = first_party_import_files(_ROOT, Path(pm.__file__).resolve())
    missing = imports - _covered_files_for(catalog.in_scope_processes()[_PM])
    assert _CODEC in missing
    sources = helpers.capture_runtime_inputs(_PM)
    assert _CODEC not in {Path(row["path"]).resolve() for row in sources}
    with pytest.raises(AssertionError, match="actual codec not registered"):
        _assert_actual_codec_binding(sources)


def test_pm_codec_same_filename_hash_cannot_replace_actual_function_source(
    monkeypatch, tmp_path
) -> None:
    duplicate = tmp_path / _CODEC.name
    duplicate.write_bytes(_CODEC.read_bytes())
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        _PM,
        {**schema.PROCESS_DEPENDENCY_FILES[_PM], _KEY: duplicate},
    )
    sources = helpers.capture_runtime_inputs(_PM)
    helpers.verify_input_sources(sources)
    assert duplicate in {Path(row["path"]).resolve() for row in sources}
    assert hashlib.sha256(duplicate.read_bytes()).hexdigest() == hashlib.sha256(_CODEC.read_bytes()).hexdigest()
    with pytest.raises(AssertionError, match="actual codec not registered"):
        _assert_actual_codec_binding(sources)


def test_pm_captured_codec_bytes_detect_drift_in_owned_copy(tmp_path) -> None:
    """Byte-drift unit control; the real imported source is never modified."""
    sources = helpers.capture_runtime_inputs(_PM)
    _assert_actual_codec_binding(sources)
    descriptor = next(row for row in sources if Path(row["path"]).resolve() == _CODEC)
    copy = tmp_path / _CODEC.name
    copy.write_bytes(_CODEC.read_bytes())
    copied_descriptor = {**descriptor, "path": str(copy)}
    helpers.verify_input_sources([copied_descriptor])
    copy.write_bytes(copy.read_bytes() + b"\n# independent codec drift unit control\n")
    with pytest.raises(ValueError, match="Consumed input source hash drift"):
        helpers.verify_input_sources([copied_descriptor])
