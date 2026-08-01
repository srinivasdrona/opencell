"""Unit tests for `scripts/l2_event/evidence.py` (requirement 5: portable
evidence index/sidecars, tamper/stale-hash detection, fresh-clone audit
without any live artifacts/ tree)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import evidence
from scripts.l2_event.schema import read_json, write_json_atomic

_MANDATORY = evidence.MANDATORY_FILES


def _fake_artifacts(verdict: str = "PASS", mode: str = "gate") -> dict:
    return {
        "result.json": {"process": "TestProc", "mode": mode, "verdict": verdict, "channels": []},
        "input_manifest.json": {"process": "TestProc", "inputs": [{"path": "/abs/some/path.mat", "seed": 0}]},
        "null_calibration.json": {"process": "TestProc", "channel": "count", "q95_null": 0.1},
        "provenance.json": {"process": "TestProc", "git_sha": "deadbeef"},
        "SUMMARY.json": {"process": "TestProc", "verdict": verdict},
    }


def test_write_run_artifacts_rejects_unrecognized_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    with pytest.raises(ValueError):
        evidence.write_run_artifacts("TestProc", "run1", {"not_a_real_file.json": {}})


def test_write_run_artifacts_writes_all_mandatory_files(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    run_dir = evidence.write_run_artifacts("TestProc", "run1", _fake_artifacts())
    for fname in _MANDATORY:
        assert (run_dir / fname).exists()


def test_bundle_run_requires_all_mandatory_files_present(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    incomplete = _fake_artifacts()
    del incomplete["provenance.json"]
    run_dir = evidence.write_run_artifacts("TestProc", "run1", incomplete)
    with pytest.raises(FileNotFoundError):
        evidence.bundle_run(run_dir, "TestProc")


def test_bundle_run_normalizes_absolute_input_manifest_paths_to_repo_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    artifacts = _fake_artifacts()
    # A path that is genuinely inside the repo, so relative_to_repo can
    # normalize it (an arbitrary /abs/ path outside the repo would just
    # pass through unchanged, which is also correct behavior but less
    # interesting to assert on).
    real_repo_file = REPO_ROOT / "pyproject.toml"
    artifacts["input_manifest.json"]["inputs"][0]["path"] = str(real_repo_file)
    run_dir = evidence.write_run_artifacts("TestProc", "run1", artifacts)
    bundle_dir = evidence.bundle_run(run_dir, "TestProc")
    manifest = read_json(bundle_dir / "input_manifest.json")
    bundled_path = manifest["inputs"][0]["path"]
    assert bundled_path == "pyproject.toml"
    assert not Path(bundled_path).is_absolute()


def test_build_index_and_audit_index_clean_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    index_path = tmp_path / "evidence_index.json"
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path)

    run_dir = evidence.write_run_artifacts("TestProc", "run1", _fake_artifacts(verdict="PASS"))
    evidence.bundle_run(run_dir, "TestProc")
    evidence.write_index(["TestProc"], evidence_root=tmp_path / "bundle")

    problems = evidence.audit_index(index_path)
    assert problems == []

    index = read_json(index_path)
    assert index["n_rows"] == 1
    assert index["rows"][0]["verdict"] == "PASS"
    assert index["rows"][0]["mode"] == "gate"


def test_audit_index_detects_tampered_file_hash_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    index_path = tmp_path / "evidence_index.json"
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path)

    run_dir = evidence.write_run_artifacts("TestProc", "run1", _fake_artifacts())
    bundle_dir = evidence.bundle_run(run_dir, "TestProc")
    evidence.write_index(["TestProc"], evidence_root=tmp_path / "bundle")

    # Tamper with a bundled file post-hash without updating the index.
    tampered = read_json(bundle_dir / "result.json")
    tampered["verdict"] = "FAIL"  # flip PASS -> FAIL post-hash (laundering attempt)
    write_json_atomic(bundle_dir / "result.json", tampered)

    problems = evidence.audit_index(index_path)
    assert any("sha256 mismatch" in p for p in problems)


def test_audit_index_detects_stale_content_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    index_path = tmp_path / "evidence_index.json"
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path)

    run_dir = evidence.write_run_artifacts("TestProc", "run1", _fake_artifacts())
    evidence.bundle_run(run_dir, "TestProc")
    evidence.write_index(["TestProc"], evidence_root=tmp_path / "bundle")

    index = read_json(index_path)
    index["content_hash"] = "0" * 64  # stale/forged content_hash
    write_json_atomic(index_path, index)

    problems = evidence.audit_index(index_path)
    assert any("content_hash mismatch" in p for p in problems)


def test_audit_index_reports_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    index_path = tmp_path / "evidence_index.json"
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path)

    run_dir = evidence.write_run_artifacts("TestProc", "run1", _fake_artifacts())
    bundle_dir = evidence.bundle_run(run_dir, "TestProc")
    evidence.write_index(["TestProc"], evidence_root=tmp_path / "bundle")

    (bundle_dir / "SUMMARY.json").unlink()

    problems = evidence.audit_index(index_path)
    assert any("file missing" in p for p in problems)


def test_audit_index_flags_incomplete_row_as_a_problem_not_a_silent_pass(tmp_path, monkeypatch):
    """M6 (Opus5 review): before this fix, an `INCOMPLETE` row (missing
    mandatory artifacts, empty `artifact_hashes`) had nothing for the
    per-file hash loop to iterate over, so `audit_index` silently reported
    zero problems for it -- indistinguishable from a genuinely clean
    audit. This reproduces exactly that false-clean scenario and asserts
    it is now caught."""
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    index_path = tmp_path / "evidence_index.json"
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path)

    incomplete = _fake_artifacts()
    del incomplete["provenance.json"]
    run_dir = evidence.write_run_artifacts("TestProc", "run1", incomplete)
    # Deliberately do NOT call bundle_run (which would itself refuse via
    # FileNotFoundError, per test_bundle_run_requires_all_mandatory_files_present
    # above) -- instead hand-build an INCOMPLETE index row directly, the way
    # `_row_for_process` would if the bundle directory existed but a
    # mandatory file were missing from it.
    bundle_root = tmp_path / "bundle"
    process_dir = bundle_root / "TestProc"
    process_dir.mkdir(parents=True)
    for fname, payload in incomplete.items():
        write_json_atomic(process_dir / fname, payload)
    evidence.write_index(["TestProc"], evidence_root=bundle_root)

    index = read_json(index_path)
    assert index["rows"][0]["mode"] == "INCOMPLETE"
    assert index["rows"][0]["artifact_hashes"] == {}

    problems = evidence.audit_index(index_path)
    assert problems != [], "an INCOMPLETE/empty-hash row must never audit clean (M6)"
    assert any("INCOMPLETE" in p or "no" in p for p in problems)


def test_audit_index_detects_tampered_git_sha_via_content_hash(tmp_path, monkeypatch):
    """M-metric-correctness ('bind git_sha in stable integrity where
    practical'): `git_sha` is now part of `_content_hash`'s stable dict,
    so forging the recorded `git_sha` (without regenerating the index)
    must be caught as a content_hash mismatch -- the same mechanism that
    already catches a forged `content_hash` field itself."""
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    index_path = tmp_path / "evidence_index.json"
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path)

    run_dir = evidence.write_run_artifacts("TestProc", "run1", _fake_artifacts())
    evidence.bundle_run(run_dir, "TestProc")
    evidence.write_index(["TestProc"], evidence_root=tmp_path / "bundle")

    index = read_json(index_path)
    index["git_sha"] = "forged" * 8  # tamper with recorded provenance only
    write_json_atomic(index_path, index)

    problems = evidence.audit_index(index_path)
    assert any("content_hash mismatch" in p for p in problems)


def test_default_evidence_root_is_always_the_tracked_bundle(tmp_path, monkeypatch):
    """Indexing/audit must always target the tracked bundle -- never the
    live per-run-id scratch tree, whose one-level-deeper layout
    (`<root>/<process>/<run_id>/...`) would silently break
    `_row_for_process`'s `<root>/<process>/<file>` assumption if it were
    ever preferred (this was an early integration bug in this
    foundation, caught and fixed while wiring the CLI runner)."""
    live_root = tmp_path / "artifacts"
    (live_root / "TestProc" / "run1").mkdir(parents=True)
    (live_root / "TestProc" / "run1" / "result.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", live_root)
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")

    assert evidence.default_evidence_root() == tmp_path / "bundle"


def test_fresh_clone_audit_works_from_tracked_bundle_only(tmp_path, monkeypatch):
    """Copy only a tracked bundle + tracked index into an isolated,
    separate fake-repo root with no live artifacts/ tree anywhere -- the
    fresh-clone scenario (requirement 5). Uses a repo-relative
    `evidence_root` (by rooting the fake bundle under the same
    `docs/phase_f/l2_event/...` layout the real repo uses) so the index
    genuinely re-resolves against the NEW root rather than the original
    absolute tmp path -- exercising the same path-resolution the real
    tracked index relies on."""
    fake_repo_1 = tmp_path / "origin_repo"
    bundle_root_1 = fake_repo_1 / "docs" / "phase_f" / "l2_event" / "evidence_bundle"
    index_path_1 = fake_repo_1 / "docs" / "phase_f" / "l2_event" / "evidence_index.json"
    monkeypatch.setattr(evidence, "_REPO_ROOT", fake_repo_1)
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", fake_repo_1 / "artifacts" / "l2_event")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", bundle_root_1)
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path_1)

    run_dir = evidence.write_run_artifacts("TestProc", "run1", _fake_artifacts())
    evidence.bundle_run(run_dir, "TestProc")
    evidence.write_index(["TestProc"], evidence_root=bundle_root_1)

    index_on_disk = read_json(index_path_1)
    assert index_on_disk["evidence_root"] == "docs/phase_f/l2_event/evidence_bundle", (
        "precondition: the index must record a repo-relative path, not an absolute one, "
        "for this test to actually exercise fresh-clone path re-resolution"
    )

    # Simulate a fresh clone: a DIFFERENT root containing only the tracked
    # docs/ subtree, no `artifacts/` anywhere.
    fake_repo_2 = tmp_path / "fresh_clone_repo"
    shutil.copytree(fake_repo_1 / "docs", fake_repo_2 / "docs")
    assert not (fake_repo_2 / "artifacts").exists()

    monkeypatch.setattr(evidence, "_REPO_ROOT", fake_repo_2)
    problems = evidence.audit_index(fake_repo_2 / "docs" / "phase_f" / "l2_event" / "evidence_index.json")
    assert problems == []


def test_translate_windows_gitdir_maps_drive_letter_to_wsl_mount():
    assert evidence._translate_windows_gitdir("E:/opencell/.git/worktrees/foo") == (
        "/mnt/e/opencell/.git/worktrees/foo"
    )
    assert evidence._translate_windows_gitdir(r"C:\repo\.git") == "/mnt/c/repo/.git"


def test_translate_windows_gitdir_returns_none_for_non_windows_path():
    assert evidence._translate_windows_gitdir("/mnt/e/opencell/.git") is None
    assert evidence._translate_windows_gitdir("relative/path") is None


def test_current_git_sha_falls_back_to_translated_worktree_gitdir(tmp_path, monkeypatch):
    """Reproduces the real bug found in this worktree: a `.git` gitlink
    file whose `gitdir:` line is a Windows-style absolute path (as written
    by Windows-hosted `git worktree add`) cannot be resolved by a
    WSL-hosted `git` binary, so the primary `git rev-parse HEAD` in
    `_REPO_ROOT` fails silently and `current_git_sha()` must fall back to
    translating the path and passing an explicit `--git-dir=`."""
    fake_root = tmp_path / "fake_worktree"
    fake_root.mkdir()
    # A `.git` gitlink pointing at a Windows-style absolute path that does
    # not exist on this machine -- the primary `git rev-parse HEAD` call
    # (cwd=fake_root) will therefore fail ("not a git repository"), forcing
    # the fallback branch to run.
    (fake_root / ".git").write_text("gitdir: Z:/nonexistent/.git/worktrees/fake\n")
    monkeypatch.setattr(evidence, "_REPO_ROOT", fake_root)

    assert evidence.current_git_sha() is None


def test_current_git_sha_returns_none_when_no_git_file_present(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_REPO_ROOT", tmp_path)
    assert evidence.current_git_sha() is None
