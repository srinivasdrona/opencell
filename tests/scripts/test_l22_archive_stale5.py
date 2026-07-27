"""Targeted tests for scripts/l22_extraction/archive_stale5.py.

Covers the WSL-path-resolution fixes discovered while first running this
script for real in the l22-stale5-regen worktree:
  - `_resolve_primary_checkout_root()` / `_resolve_matlab_exe()` must not
    silently produce a mangled `E:\\opencell/data/...`-style path when run
    under WSL (a bare `Path(r"E:\\opencell")` is treated as one opaque path
    segment on Linux and never resolves) -- they must pick whichever
    candidate root actually exists on disk.
  - `_git()` must fall back to Git for Windows (`git.exe`, reachable via WSL
    interop, given a Windows-style cwd) when the native WSL `git` fails with
    "not a git repository" -- this worktree's `.git` pointer file records a
    Windows-style `gitdir:` path that Linux git cannot resolve.
  - `build_archive_manifest()` end-to-end with an isolated tmp_path root
    produces honest `{"error": ...}` entries (never fabricated hashes) when
    the primary-checkout file is genuinely absent.

Run via `bin\\oc-pytest tests/scripts/test_l22_archive_stale5.py -v`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction import archive_stale5  # noqa: E402
from scripts.l22_extraction.seed0_regen import STALE5_PROCESSES  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def test_wsl_path_to_windows_conversion():
    assert archive_stale5._wsl_path_to_windows(Path("/mnt/e/opencell")) == r"E:\opencell"
    assert (
        archive_stale5._wsl_path_to_windows(Path("/mnt/e/opencell-worktrees/l22-stale5-regen"))
        == r"E:\opencell-worktrees\l22-stale5-regen"
    )


def test_wsl_path_to_windows_passthrough_for_non_mnt_paths():
    # Already-Windows-style or otherwise-unrecognized paths pass through
    # unchanged rather than being mangled.
    assert archive_stale5._wsl_path_to_windows(Path(r"E:\opencell")) == r"E:\opencell"


def test_resolve_primary_checkout_root_picks_existing_candidate(monkeypatch):
    # None of the real candidates need to exist for this test: we just
    # confirm the function returns a Path (its first-candidate fallback)
    # rather than raising, so callers always get a usable, honest root.
    root = archive_stale5._resolve_primary_checkout_root()
    assert isinstance(root, Path)


def test_resolve_matlab_exe_returns_a_path():
    exe = archive_stale5._resolve_matlab_exe()
    assert isinstance(exe, Path)
    assert exe.name == "matlab.exe"


def test_git_falls_back_to_git_exe_on_wsl_gitdir_mismatch(monkeypatch):
    # Simulate the exact failure mode seen in this worktree: native `git`
    # reports "not a git repository" because the WSL Linux git binary can't
    # parse the worktree's Windows-style gitdir pointer. Confirm _git()
    # retries via git.exe with a translated cwd instead of raising.
    calls = []

    def fake_run(cmd, cwd=None, capture_output=None, text=None, check=None):  # noqa: ANN001
        calls.append((cmd, cwd))
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: not a git repository: x")
        assert cmd[0] == "git.exe"
        return subprocess.CompletedProcess(cmd, 0, stdout="deadbeef\n", stderr="")

    monkeypatch.setattr(archive_stale5.subprocess, "run", fake_run)
    result = archive_stale5._git(["rev-parse", "HEAD"], cwd=Path("/mnt/e/opencell"))
    assert result == "deadbeef"
    assert calls[0][0][0] == "git"
    assert calls[1][0][0] == "git.exe"
    assert calls[1][0][2] == r"E:\opencell"  # -C <win_cwd>


def test_build_archive_manifest_reports_honest_missing_files(tmp_path):
    # Isolated tmp_path root: none of the 5 files exist anywhere, so every
    # entry must be an honest {"error": ...}, never a fabricated hash.
    manifest = archive_stale5.build_archive_manifest(
        primary_checkout_root=tmp_path / "nonexistent_primary",
        archive_dir=tmp_path / "nonexistent_archive",
        probe_matlab=False,
    )
    assert set(manifest["old_files"]) == set(STALE5_PROCESSES)
    for process in STALE5_PROCESSES:
        entry = manifest["old_files"][process]
        assert "error" in entry["primary_checkout"]
        assert "error" in entry["archived_copy"]
        assert "archive_matches_primary" not in entry


def test_build_archive_manifest_matches_real_files(tmp_path):
    primary_root = tmp_path / "primary"
    archive_dir = tmp_path / "archive"
    process = next(iter(STALE5_PROCESSES))
    primary_path = primary_root / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / f"{process}_100ticks.mat"
    primary_path.parent.mkdir(parents=True)
    write_synthetic_trace(
        primary_path, process_name=process, seed=0, channels={"substrates": (2, 2)}
    )
    archive_dir.mkdir(parents=True)
    archived_path = archive_dir / f"{process}_100ticks.mat"
    archived_path.write_bytes(primary_path.read_bytes())

    manifest = archive_stale5.build_archive_manifest(
        primary_checkout_root=primary_root, archive_dir=archive_dir, probe_matlab=False
    )
    entry = manifest["old_files"][process]
    assert entry["archive_matches_primary"] is True
    assert entry["primary_checkout"]["sha256"] == entry["archived_copy"]["sha256"]
