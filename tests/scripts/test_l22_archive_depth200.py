"""Targeted tests for scripts/l22_extraction/archive_depth200.py.

Covers the archive-manifest builder that must run BEFORE any of the 3x50
depth-200 regeneration's legacy `_100ticks.mat` files is overwritten in
place:
  - honest `{"error": ...}` entries (never fabricated hashes) when a file
    is genuinely absent, for both "this worktree" and "source worktree"
    sides
  - `matches_source` is True only when both sides exist and their SHA256
    are equal; a genuine mismatch is flagged, not silently accepted
  - `all_50_present_and_match_source` is True only when every one of the
    50 seed entries for a process is present and matches
  - `_seed_relpath` resolves the same canonical-vs-suffixed directory
    layout as `depth200_regen.legacy_path_for_seed` (seed 0 unsuffixed,
    seeds >= 1 under `_sNNN/`)

Run via `bin\\oc-pytest tests/scripts/test_l22_archive_depth200.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction import archive_depth200  # noqa: E402
from scripts.l22_extraction.depth200_regen import DEPTH200_PROCESSES  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def test_seed_relpath_matches_canonical_and_suffixed_layout(tmp_path):
    rel0 = archive_depth200._seed_relpath("DNARepair", 0)
    assert str(rel0) in (r"per_process_traces_v2\DNARepair_100ticks.mat", "per_process_traces_v2/DNARepair_100ticks.mat")
    rel5 = archive_depth200._seed_relpath("ProteinDecay", 5)
    assert "per_process_traces_v2_s005" in str(rel5)
    assert rel5.name == "ProteinDecay_100ticks.mat"


def test_build_archive_manifest_reports_honest_missing_files(tmp_path):
    manifest = archive_depth200.build_archive_manifest(
        processes=("DNARepair",),
        seeds=range(2),
        worktrees_root=tmp_path / "nonexistent_worktrees",
        karr_native_root=tmp_path / "nonexistent_this_worktree",
        probe_matlab=False,
    )
    entry = manifest["old_files"]["DNARepair"]
    assert entry["seed_count"] == 2
    assert entry["all_50_present_and_match_source"] is False
    for seed_entry in entry["seeds"].values():
        assert "error" in seed_entry["this_worktree"]
        assert "error" in seed_entry["source_worktree"]
        assert seed_entry["matches_source"] is False


def test_build_archive_manifest_matches_real_files_and_detects_mismatch(tmp_path):
    worktrees_root = tmp_path / "opencell-worktrees"
    this_root = tmp_path / "this_worktree" / "karr_native"

    source_root = worktrees_root / "l22-full-extract" / "data" / "m1_sources" / "karr_native"
    matching_path = source_root / "per_process_traces_v2" / "DNARepair_100ticks.mat"
    write_synthetic_trace(matching_path, process_name="DNARepair", seed=0, n_ticks=100)
    this_matching_path = this_root / "per_process_traces_v2" / "DNARepair_100ticks.mat"
    this_matching_path.parent.mkdir(parents=True)
    this_matching_path.write_bytes(matching_path.read_bytes())

    mismatch_source = source_root / "per_process_traces_v2_s001" / "DNARepair_100ticks.mat"
    write_synthetic_trace(mismatch_source, process_name="DNARepair", seed=1, n_ticks=100)
    this_mismatch_path = this_root / "per_process_traces_v2_s001" / "DNARepair_100ticks.mat"
    this_mismatch_path.parent.mkdir(parents=True)
    write_synthetic_trace(this_mismatch_path, process_name="DNARepair", seed=1, n_ticks=100, channel_width=99)

    manifest = archive_depth200.build_archive_manifest(
        processes=("DNARepair",),
        seeds=range(2),
        worktrees_root=worktrees_root,
        karr_native_root=this_root,
        probe_matlab=False,
    )
    entry = manifest["old_files"]["DNARepair"]
    assert entry["seeds"]["0"]["matches_source"] is True
    assert entry["seeds"]["1"]["matches_source"] is False
    assert entry["all_50_present_and_match_source"] is False


def test_build_archive_manifest_covers_all_depth200_processes_by_default(tmp_path):
    manifest = archive_depth200.build_archive_manifest(
        seeds=range(1),
        worktrees_root=tmp_path / "nonexistent_worktrees",
        karr_native_root=tmp_path / "nonexistent_this_worktree",
        probe_matlab=False,
    )
    assert set(manifest["old_files"]) == set(DEPTH200_PROCESSES)
    assert set(manifest["task"]["source_worktree_by_process"]) == set(DEPTH200_PROCESSES)
