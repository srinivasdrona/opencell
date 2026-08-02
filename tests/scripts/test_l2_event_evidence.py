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


# ---------------------------------------------------------------------------
# Opus5 review round 3: git_sha/registry_sha256/karr_source verification
# (item #4), exact mandatory-file coverage (item #5)
# ---------------------------------------------------------------------------


def _build_bundle_and_index(tmp_path, monkeypatch, artifacts: dict) -> Path:
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    index_path = tmp_path / "evidence_index.json"
    monkeypatch.setattr(evidence, "TRACKED_INDEX_PATH", index_path)
    run_dir = evidence.write_run_artifacts("TestProc", "run1", artifacts)
    evidence.bundle_run(run_dir, "TestProc")
    evidence.write_index(["TestProc"], evidence_root=tmp_path / "bundle")
    return index_path


def test_audit_index_detects_forged_git_sha_not_a_real_commit(tmp_path, monkeypatch):
    """Opus5 review round 3, item #4: 'audit verifies git_sha ..., not
    merely stores'. A well-formed-looking (40-hex) but fabricated git_sha
    that does not exist anywhere in this repository's history must be
    flagged -- forging a plausible-looking sha must not be enough to pass
    the audit."""
    artifacts = _fake_artifacts()
    artifacts["provenance.json"]["git_sha"] = "f" * 40  # syntactically valid, does not exist
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert any("does not exist as a real commit" in p for p in problems)


def test_audit_index_accepts_a_real_existing_git_sha(tmp_path, monkeypatch):
    """The mirror-positive case: the CURRENT HEAD sha (guaranteed to exist
    in this repo's history) must not be flagged."""
    real_sha = evidence.current_git_sha()
    if not real_sha:
        pytest.skip("git is not available/resolvable in this test environment")
    artifacts = _fake_artifacts()
    artifacts["provenance.json"]["git_sha"] = real_sha
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert not any("git_sha" in p for p in problems)


def test_audit_index_short_placeholder_git_sha_is_skipped_not_flagged(tmp_path, monkeypatch):
    """Existing test fixtures across this file use an 8-char placeholder
    git_sha ('deadbeef') that is not a real 40-hex commit sha -- this must
    remain a no-op for the new verification (format-gated), not a new
    false failure across every other test in this file."""
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, _fake_artifacts())
    problems = evidence.audit_index(index_path)
    assert problems == []


def test_audit_index_detects_forged_registry_sha256(tmp_path, monkeypatch):
    """Opus5 review round 3, item #4: a `registry_sha256` that does not
    match the registry file's OWN actual current hash must be flagged --
    the audit recomputes it independently rather than trusting the
    recorded value."""
    artifacts = _fake_artifacts()
    artifacts["provenance.json"]["registry_sha256"] = "0" * 64
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert any("registry_sha256" in p for p in problems)


def test_audit_index_accepts_a_correct_registry_sha256(tmp_path, monkeypatch):
    from scripts.l2_event.registry import registry_sha256

    artifacts = _fake_artifacts()
    artifacts["provenance.json"]["registry_sha256"] = registry_sha256()
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert not any("registry_sha256" in p for p in problems)


def test_audit_index_registry_sha256_not_set_is_skipped_not_flagged(tmp_path, monkeypatch):
    """Existing fixtures never set `registry_sha256` at all -- this must
    remain a no-op (presence-gated), matching `_fake_artifacts`'s
    provenance.json which has no such key."""
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, _fake_artifacts())
    problems = evidence.audit_index(index_path)
    assert problems == []


def test_audit_index_detects_karr_source_inconsistent_with_input_manifest(tmp_path, monkeypatch):
    """Opus5 review round 3, item #4: `karr_source` must be internally
    consistent with `input_manifest.json`'s own recorded input
    directory/directories -- a provenance doc claiming a karr_source that
    disagrees with the manifest it ships alongside is a real integrity
    problem."""
    artifacts = _fake_artifacts()
    artifacts["input_manifest.json"]["inputs"][0]["path"] = "/abs/some/path.mat"
    artifacts["provenance.json"]["karr_source"] = "/abs/totally/different/dir"
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert any("karr_source" in p for p in problems)


def test_audit_index_accepts_karr_source_consistent_with_input_manifest(tmp_path, monkeypatch):
    artifacts = _fake_artifacts()
    artifacts["input_manifest.json"]["inputs"][0]["path"] = "/abs/some/path.mat"
    artifacts["provenance.json"]["karr_source"] = "/abs/some"
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert not any("karr_source" in p for p in problems)


# ---------------------------------------------------------------------------
# Opus5 review round 4, item #1: karr_source multi-seed ancestor/prefix
# semantics (single file, common parent, root, forged sibling/traversal)
# ---------------------------------------------------------------------------


def test_audit_index_karr_source_single_file_exact_parent_accepted(tmp_path, monkeypatch):
    """Single-file/single-seed convention: karr_source equal to the one
    recorded input's own parent directory must be accepted."""
    artifacts = _fake_artifacts()
    artifacts["input_manifest.json"]["inputs"][0]["path"] = (
        "data/m1_sources/karr_native/per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat"
    )
    artifacts["provenance.json"]["karr_source"] = (
        "data/m1_sources/karr_native/per_process_traces_v2_event_s000"
    )
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert not any("karr_source" in p for p in problems)


def test_audit_index_karr_source_common_parent_multi_seed_ancestor_accepted(tmp_path, monkeypatch):
    """Multi-seed convention: karr_source is a common ANCESTOR directory
    several seeds' individually-different input directories all live
    under (e.g. per-seed `per_process_traces_v2_event_s000`, `..._s001`
    subdirectories sharing a `karr_native` parent) -- every recorded input
    path must independently resolve as covered, not just any one of
    them."""
    artifacts = _fake_artifacts()
    artifacts["input_manifest.json"]["inputs"] = [
        {"path": "data/m1_sources/karr_native/per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat", "seed": 0},
        {"path": "data/m1_sources/karr_native/per_process_traces_v2_event_s001/RibosomeAssembly_100ticks.mat", "seed": 1},
    ]
    artifacts["provenance.json"]["karr_source"] = "data/m1_sources/karr_native"
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert not any("karr_source" in p for p in problems)


def test_audit_index_karr_source_root_ancestor_covers_all_inputs_accepted(tmp_path, monkeypatch):
    """An even shorter common ancestor (the repo-relative "root" of the
    whole data tree, well above the per-seed subdirectories) must still
    be accepted -- the ancestor check has no fixed depth requirement."""
    artifacts = _fake_artifacts()
    artifacts["input_manifest.json"]["inputs"] = [
        {"path": "data/m1_sources/karr_native/per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat", "seed": 0},
        {"path": "data/m1_sources/karr_native/per_process_traces_v2_event_s001/RibosomeAssembly_100ticks.mat", "seed": 1},
    ]
    artifacts["provenance.json"]["karr_source"] = "data/m1_sources"
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert not any("karr_source" in p for p in problems)


def test_audit_index_karr_source_forged_sibling_directory_rejected(tmp_path, monkeypatch):
    """A sibling directory that merely shares a string PREFIX with the
    real karr_source (`karr_native` vs. `karr_native_evil`) must be
    rejected -- a naive `path.startswith(karr_source)` string check would
    wrongly accept this, since 'karr_native_evil/...'.startswith(
    'karr_native') is True even though it is a completely different
    directory. The segment-wise ancestor check must reject it."""
    artifacts = _fake_artifacts()
    artifacts["input_manifest.json"]["inputs"][0]["path"] = (
        "data/m1_sources/karr_native_evil/per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat"
    )
    artifacts["provenance.json"]["karr_source"] = "data/m1_sources/karr_native"
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert any("karr_source" in p for p in problems)


def test_audit_index_karr_source_path_traversal_rejected(tmp_path, monkeypatch):
    """A recorded input path that uses `..` to traverse above its own
    given string entirely (e.g. climbing out of a relative root with no
    prior segments to pop) must be rejected as malformed, not silently
    treated as covered."""
    artifacts = _fake_artifacts()
    artifacts["input_manifest.json"]["inputs"][0]["path"] = "../../etc/passwd"
    artifacts["provenance.json"]["karr_source"] = "data/m1_sources/karr_native"
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, artifacts)
    problems = evidence.audit_index(index_path)
    assert any("karr_source" in p for p in problems)


def test_is_repo_relative_ancestor_rejects_ambiguous_string_prefix_directly():
    """Unit-level check of the helper itself (Opus5 review round 4, item
    #1): a raw string-prefix comparison would wrongly treat
    'karr_native_evil/x' as being 'under' 'karr_native', but the
    segment-wise ancestor check must not."""
    assert evidence._is_repo_relative_ancestor("a/karr_native", "a/karr_native_evil/x.mat") is False
    assert evidence._is_repo_relative_ancestor("a/karr_native", "a/karr_native/x.mat") is True
    assert evidence._is_repo_relative_ancestor("a/b/c", "a/b/c") is True


def test_bundle_run_normalizes_provenance_karr_source_to_repo_relative(tmp_path, monkeypatch):
    """Opus5 review round 3, item #4/#5: `bundle_run` must normalize
    `provenance.json`'s `karr_source` field the same way it already
    normalizes `input_manifest.json`'s input paths -- before this fix,
    only the manifest was made portable, leaving an absolute worktree
    path baked into every tracked provenance.json."""
    monkeypatch.setattr(evidence, "LIVE_EVIDENCE_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(evidence, "TRACKED_BUNDLE_ROOT", tmp_path / "bundle")
    artifacts = _fake_artifacts()
    real_repo_dir = REPO_ROOT / "scripts" / "l2_event"
    artifacts["provenance.json"]["karr_source"] = str(real_repo_dir)
    run_dir = evidence.write_run_artifacts("TestProc", "run1", artifacts)
    bundle_dir = evidence.bundle_run(run_dir, "TestProc")
    provenance = read_json(bundle_dir / "provenance.json")
    assert provenance["karr_source"] == "scripts/l2_event"
    assert not Path(provenance["karr_source"]).is_absolute()


def test_audit_index_flags_unexpected_extra_file_beyond_mandatory_set(tmp_path, monkeypatch):
    """Opus5 review round 3, item #5: 'exact coverage' -- an evidence
    directory containing an unrecognized extra file alongside the 5
    mandatory ones must be flagged, not silently ignored."""
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, _fake_artifacts())
    bundle_dir = tmp_path / "bundle" / "TestProc"
    (bundle_dir / "unexpected_extra.json").write_text("{}", encoding="utf-8")
    problems = evidence.audit_index(index_path)
    assert any("unexpected file" in p for p in problems)


def test_audit_index_flags_recorded_artifact_set_not_exactly_matching_mandatory_files(tmp_path, monkeypatch):
    """Opus5 review round 3, item #5: even if every recorded hash matches
    on disk, a row whose recorded artifact-hash KEY SET does not exactly
    equal MANDATORY_FILES (e.g. a hand-edited/stale index missing one
    entry while still claiming a non-INCOMPLETE mode) must be flagged --
    'missing 1 of N fails'."""
    index_path = _build_bundle_and_index(tmp_path, monkeypatch, _fake_artifacts())
    index = read_json(index_path)
    del index["rows"][0]["artifact_hashes"]["SUMMARY.json"]
    # Recompute content_hash so this test isolates the exact-coverage
    # check from the (already-covered) content_hash tamper-detection path.
    index["content_hash"] = evidence._content_hash(index)
    write_json_atomic(index_path, index)
    problems = evidence.audit_index(index_path)
    assert any("does not exactly cover MANDATORY_FILES" in p for p in problems)


# ---------------------------------------------------------------------------
# Canary-A closeout: the tracked RibosomeAssembly bundle's ACTIVE
# input_manifest.json claim must bind the new, M4-complete raw hash --
# never regress to the stale pre-M4 hash a prior worktree round tracked.
# ---------------------------------------------------------------------------

_TRACKED_RA_INPUT_MANIFEST = REPO_ROOT / "docs" / "phase_f" / "l2_event" / "evidence_bundle" / "RibosomeAssembly" / "input_manifest.json"

# Canary-A (this closeout): full M4 stride/tick_start/tick_end contract.
_CANARY_A_SHA256 = "c65902a8232cb6afe2c8dd9476597a64418a0c740676c763af1223ef6338a79b"
# Pre-Canary-A (superseded): predates the M4 contract entirely. Retained
# here ONLY as the negative half of the regression check below -- this is
# not a claim this codebase makes anywhere active, and it must stay that
# way. Historical/superseded mentions of this same hash in dated narrative
# docs (e.g. RIBOSOME_ASSEMBLY_GATE_ADAPTER_REPORT.md's "Environment
# landmine" note, an append-only record of a since-fixed worktree quirk)
# are explicitly out of scope for this check -- this test is only about
# the ACTIVE tracked manifest claim, not the narrative history.
_PRE_CANARY_A_SHA256 = "6f1ad7f8d1c96e3807e8e454bb5914820d509b72f9eb6f62ea1b934d0ef41ca8"


def test_tracked_ra_input_manifest_binds_canary_a_hash_not_the_stale_pre_m4_hash():
    """Regression guard: the tracked (portable, fresh-clone-auditable)
    ``evidence_bundle/RibosomeAssembly/input_manifest.json`` must record
    the Canary-A raw file's sha256 as its ACTIVE claim, and must never
    regress to the stale pre-M4 hash. This is checked directly against
    the real tracked file (not a runner recomputation) because the whole
    point of the tracked bundle is that a fresh clone without the
    gitignored raw MAT still audits the CLAIM, not a live recomputation
    against data that may not even be present."""
    manifest = read_json(_TRACKED_RA_INPUT_MANIFEST)
    recorded = manifest["inputs"][0]["sha256"]
    assert recorded == _CANARY_A_SHA256
    assert recorded != _PRE_CANARY_A_SHA256
