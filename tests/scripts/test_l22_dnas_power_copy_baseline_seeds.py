"""Targeted tests for scripts/l22_dnas_power/copy_baseline_seeds.py.

Uses `tmp_path` source/dest roots and `write_synthetic_trace` fixtures --
never touches real Karr trace data or the real `l22-final-sweep` worktree.

Run via `bin\\oc-pytest tests/scripts/test_l22_dnas_power_copy_baseline_seeds.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l22_dnas_power.copy_baseline_seeds import PROCESS, copy_dnas_baseline  # noqa: E402
from scripts.l22_extraction.launcher import canonical_seed0_path, seed_mat_path  # noqa: E402
from scripts.l22_extraction.trace_validation import sha256_file  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def _write_source_seeds(source_root: Path, seeds: tuple[int, ...]) -> None:
    for seed in seeds:
        path = (
            canonical_seed0_path(PROCESS, karr_native_root=source_root)
            if seed == 0
            else seed_mat_path(PROCESS, seed, karr_native_root=source_root)
        )
        write_synthetic_trace(path, process_name=PROCESS, seed=seed, n_ticks=100)


def test_copy_dnas_baseline_copies_seed0_unsuffixed_and_others_suffixed(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    _write_source_seeds(source_root, (0, 1, 2))

    records = copy_dnas_baseline(source_native_root=source_root, dest_native_root=dest_root, seeds=(0, 1, 2))

    assert [r.action for r in records] == ["copied", "copied", "copied"]
    assert canonical_seed0_path(PROCESS, karr_native_root=dest_root).exists()
    assert "per_process_traces_v2_s000" not in str(canonical_seed0_path(PROCESS, karr_native_root=dest_root))
    assert seed_mat_path(PROCESS, 1, karr_native_root=dest_root).exists()
    assert seed_mat_path(PROCESS, 2, karr_native_root=dest_root).exists()


def test_copy_dnas_baseline_verifies_hash_matches_source(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    _write_source_seeds(source_root, (0,))

    records = copy_dnas_baseline(source_native_root=source_root, dest_native_root=dest_root, seeds=(0,))

    src_path = canonical_seed0_path(PROCESS, karr_native_root=source_root)
    dst_path = canonical_seed0_path(PROCESS, karr_native_root=dest_root)
    assert records[0].verified is True
    assert sha256_file(src_path) == sha256_file(dst_path) == records[0].sha256


def test_copy_dnas_baseline_is_idempotent_on_identical_existing_dest(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    _write_source_seeds(source_root, (1,))

    first = copy_dnas_baseline(source_native_root=source_root, dest_native_root=dest_root, seeds=(1,))
    second = copy_dnas_baseline(source_native_root=source_root, dest_native_root=dest_root, seeds=(1,))

    assert first[0].action == "copied"
    assert second[0].action == "skipped_identical"


def test_copy_dnas_baseline_refuses_to_overwrite_diverging_dest(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    _write_source_seeds(source_root, (1,))
    # A different, pre-existing destination file with the same name but
    # different content (simulates a corrupted/edited-in-place destination).
    write_synthetic_trace(
        seed_mat_path(PROCESS, 1, karr_native_root=dest_root),
        process_name=PROCESS,
        seed=1,
        n_ticks=100,
        channel_width=99,  # forces different byte content than the source fixture
    )

    with pytest.raises(FileExistsError):
        copy_dnas_baseline(source_native_root=source_root, dest_native_root=dest_root, seeds=(1,))


def test_copy_dnas_baseline_raises_on_missing_source_seed(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    _write_source_seeds(source_root, (0,))  # seed 1 deliberately never written

    with pytest.raises(FileNotFoundError):
        copy_dnas_baseline(source_native_root=source_root, dest_native_root=dest_root, seeds=(0, 1))


def test_copy_dnas_baseline_dry_run_does_not_write_anything(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    _write_source_seeds(source_root, (0, 1))

    records = copy_dnas_baseline(
        source_native_root=source_root, dest_native_root=dest_root, seeds=(0, 1), dry_run=True
    )

    assert all(r.action == "would_copy" for r in records)
    assert not canonical_seed0_path(PROCESS, karr_native_root=dest_root).exists()
    assert not seed_mat_path(PROCESS, 1, karr_native_root=dest_root).exists()
