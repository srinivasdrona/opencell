"""Targeted tests for scripts/l22_extraction/trace_validation.py.

Run via `bin\\oc-pytest tests/scripts/test_l22_trace_validation.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.trace_validation import sha256_file, validate_structural  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def test_validate_structural_missing_file_is_invalid(tmp_path):
    result = validate_structural(tmp_path / "does_not_exist.mat")
    assert not result.ok
    assert "does not exist" in result.errors[0]


def test_validate_structural_accepts_well_formed_synthetic_trace(tmp_path):
    path = write_synthetic_trace(tmp_path / "RNADecay_100ticks.mat", process_name="RNADecay", seed=1, n_ticks=5)
    result = validate_structural(path, expected_process="RNADecay", expected_seed=1, expected_n_ticks=5)
    assert result.ok, result.errors
    assert result.metadata["process_name"] == "RNADecay"
    assert int(result.metadata["rng_seed"]) == 1
    assert int(result.metadata["n_ticks"]) == 5
    assert result.sha256 == sha256_file(path)


def test_validate_structural_rejects_process_name_mismatch(tmp_path):
    path = write_synthetic_trace(tmp_path / "RNADecay_100ticks.mat", process_name="RNADecay", seed=1, n_ticks=5)
    result = validate_structural(path, expected_process="ProteinDecay", expected_seed=1, expected_n_ticks=5)
    assert not result.ok
    assert any("process_name" in e for e in result.errors)


def test_validate_structural_rejects_seed_mismatch(tmp_path):
    path = write_synthetic_trace(tmp_path / "RNADecay_100ticks.mat", process_name="RNADecay", seed=1, n_ticks=5)
    result = validate_structural(path, expected_process="RNADecay", expected_seed=2, expected_n_ticks=5)
    assert not result.ok
    assert any("rng_seed" in e for e in result.errors)


def test_validate_structural_rejects_tick_count_mismatch(tmp_path):
    path = write_synthetic_trace(tmp_path / "RNADecay_100ticks.mat", process_name="RNADecay", seed=1, n_ticks=5)
    result = validate_structural(path, expected_process="RNADecay", expected_seed=1, expected_n_ticks=100)
    assert not result.ok
    assert any("n_ticks" in e for e in result.errors)


def test_validate_structural_rejects_truncated_file(tmp_path):
    path = tmp_path / "corrupt.mat"
    path.write_bytes(b"not a real hdf5 file")
    result = validate_structural(path)
    assert not result.ok
    assert any("unreadable" in e.lower() or "corrupt" in e.lower() for e in result.errors)


def test_validate_structural_skips_hash_when_disabled(tmp_path):
    path = write_synthetic_trace(tmp_path / "RNADecay_100ticks.mat", process_name="RNADecay", seed=0, n_ticks=3)
    result = validate_structural(path, compute_hash=False)
    assert result.ok
    assert result.sha256 is None
