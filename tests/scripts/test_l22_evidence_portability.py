"""Portability tests: the tracked evidence bundle + index must be
self-sufficient without the gitignored, live `artifacts/l2_2_gates/` tree.

Before this test existed, `generator.py generate`/`audit` only ever read
`result.json`/`input_manifest.json`/`provenance.json` (the mandatory
per-process authority files) from `artifacts/l2_2_gates/<Process>/latest/`,
which is fully gitignored (see `.gitignore` line ~30). A fresh clone that
never ran the sweep locally has no `artifacts/` directory at all, so every
row would look like MISSING_EVIDENCE regardless of what is actually
committed -- `audit` could never succeed there, making any claim of
"portable, tracked evidence" false.

`scripts/l22_evidence/generator.bundle_process_evidence()` mirrors the
compact authority + sidecar files (excluding `schema.BUNDLE_EXCLUDE_FILES`,
the large raw per-seed/tick arrays) into a tracked
`docs/phase_f/l2_2_design_a/evidence_bundle/` directory, and
`schema.default_evidence_root()` makes `generate`/`audit` fall back to that
tracked bundle whenever the live `artifacts/l2_2_gates` tree is absent or
empty. This file proves that fallback actually works end-to-end by copying
*only* the tracked bundle + tracked index into an isolated temp root that
deliberately has no `artifacts/l2_2_gates` anywhere under it, and confirming
`audit()` still succeeds there with the identical tally as the real tracked
index.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402


def test_bundle_excludes_large_array_sidecars():
    """The tracked bundle must never contain the large per-seed/tick raw
    array sidecars (currently just allocator_inputs.json) -- only compact
    JSON authority + sidecar files."""
    assert schema.BUNDLE_ROOT.is_dir(), f"{schema.BUNDLE_ROOT} does not exist; run `generator.py bundle` first"
    bundled_files = list(schema.BUNDLE_ROOT.rglob("*"))
    assert bundled_files, "bundle is empty; nothing to check portability of"
    for excluded in schema.BUNDLE_EXCLUDE_FILES:
        assert not any(f.name == excluded for f in bundled_files), (
            f"{excluded} must never be committed to the tracked evidence bundle "
            "(large raw array, not needed for mechanical verdict re-derivation)"
        )
    total_bytes = sum(f.stat().st_size for f in bundled_files if f.is_file())
    # Generous sanity ceiling: compact JSON sidecars for 18 processes should
    # never approach the multi-MB territory the excluded arrays live in.
    assert total_bytes < 5_000_000, f"tracked bundle is {total_bytes} bytes -- suspiciously large for compact JSON only"


def test_bundle_mirrors_every_process_with_real_live_evidence():
    """Every process that currently has real evidence under the live
    artifacts/l2_2_gates tree must also have a bundle entry with matching
    required-authority-file content. `result.json`/`provenance.json` are
    byte-identical copies; `input_manifest.json` is a semantically-matching
    but NOT byte-identical copy, since `bundle_process_evidence` normalizes
    its `inputs[*]["path"]` entries to repo-relative POSIX paths so the
    tracked bundle never embeds this machine's absolute worktree path (see
    `generator._normalize_input_manifest_paths`)."""
    catalog_entries = cat.in_scope_processes()
    for name, entry in sorted(catalog_entries.items()):
        subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
        live_dir = schema.EVIDENCE_ROOT / name / subdir
        if not all((live_dir / fname).is_file() for fname in schema.REQUIRED_AUTHORITY_FILES):
            continue  # no real evidence for this process yet locally; nothing to compare
        bundle_dir = schema.BUNDLE_ROOT / name / subdir
        for fname in ("result.json", "provenance.json"):
            live_bytes = (live_dir / fname).read_bytes()
            bundle_file = bundle_dir / fname
            assert bundle_file.is_file(), f"{name}: {fname} missing from tracked bundle at {bundle_file}"
            assert bundle_file.read_bytes() == live_bytes, f"{name}: bundled {fname} is not byte-identical to the live copy"

        live_manifest = json.loads((live_dir / "input_manifest.json").read_text(encoding="utf-8"))
        bundle_manifest_file = bundle_dir / "input_manifest.json"
        assert bundle_manifest_file.is_file(), f"{name}: input_manifest.json missing from tracked bundle"
        bundle_manifest = json.loads(bundle_manifest_file.read_text(encoding="utf-8"))
        assert bundle_manifest["resolved_seeds"] == live_manifest["resolved_seeds"], name
        assert bundle_manifest["m_ticks"] == live_manifest["m_ticks"], name
        assert len(bundle_manifest["inputs"]) == len(live_manifest["inputs"]), name
        for bundled_input in bundle_manifest["inputs"]:
            path = bundled_input.get("path")
            assert path, f"{name}: bundled input_manifest.json has an empty path"
            assert not Path(path).is_absolute(), (
                f"{name}: bundled input_manifest.json path {path!r} must be repo-relative, not absolute"
            )


def test_audit_succeeds_from_a_temp_root_with_no_local_artifacts_tree(tmp_path):
    """The critical portability guarantee: copy *only* the tracked bundle +
    tracked index into an isolated temp root (no `artifacts/l2_2_gates`
    anywhere under it) and confirm `audit()` still succeeds there, with the
    identical aggregate/tally as the real committed index. This is what a
    fresh clone that never ran the sweep locally would see."""
    temp_bundle_root = tmp_path / "evidence_bundle"
    shutil.copytree(schema.BUNDLE_ROOT, temp_bundle_root)
    temp_index_path = tmp_path / "evidence_index.json"
    shutil.copy2(schema.INDEX_PATH, temp_index_path)

    # Prove the temp root really does not contain a live artifacts/ tree of
    # any kind -- this is the "no local gitignored artifacts" scenario.
    assert not (tmp_path / "artifacts").exists()
    assert not any(p.name == "l2_2_gates" for p in tmp_path.rglob("*"))

    # F3 (Opus5 final review): pass explicit index_path/evidence_root for
    # BOTH sides rather than relying on `gen.audit()`'s ambient
    # `schema.INDEX_PATH`/`schema.default_evidence_root()` default
    # arguments -- this test is specifically about proving the *portable*
    # (tracked-bundle-only) path reproduces the real tally, and should not
    # itself depend on `audit()`'s own default-argument resolution (that
    # resolution is separately exercised by
    # `test_default_evidence_root_prefers_live_tree_when_present` /
    # `test_generate_falls_back_to_bundle_when_evidence_root_absent` below).
    real_evidence_root = schema.EVIDENCE_ROOT if schema.EVIDENCE_ROOT.is_dir() else schema.BUNDLE_ROOT
    real = gen.audit(index_path=schema.INDEX_PATH, evidence_root=real_evidence_root)
    portable = gen.audit(index_path=temp_index_path, evidence_root=temp_bundle_root)

    assert portable.ok, f"portable audit (bundle-only, no local artifacts/) failed integrity: {portable.problems}"
    assert portable.aggregate_verdict == real.aggregate_verdict
    assert portable.tally == real.tally


def test_generate_falls_back_to_bundle_when_evidence_root_absent(tmp_path, monkeypatch):
    """`schema.default_evidence_root()` -- and therefore `build_evidence_index()`
    with no explicit `evidence_root` -- must resolve to the tracked bundle
    when the live tree does not exist at all (the literal fresh-clone case),
    not silently produce a DIFFERENT index than the live tree would.

    As of this commit no row is real PASS yet (the Phase-A provenance
    hardening demotes every pre-hardening evidence dir to MISSING_EVIDENCE
    until it is rerun through the hardened sweep -- see
    test_l22_evidence_generator.py), so this only asserts the bundle-sourced
    fallback reproduces the SAME honest tally as the live tree, not that it
    contains a PASS row; once Phase-B reruns repopulate real PASS/FAIL rows
    this assertion set should be tightened back to require at least one
    real PASS."""
    live_payload = gen.build_evidence_index(evidence_root=schema.EVIDENCE_ROOT)

    nonexistent_live_root = tmp_path / "artifacts_that_do_not_exist" / "l2_2_gates"
    assert not nonexistent_live_root.exists()
    monkeypatch.setattr(schema, "EVIDENCE_ROOT", nonexistent_live_root)

    resolved = schema.default_evidence_root()
    assert resolved == schema.BUNDLE_ROOT

    payload = gen.build_evidence_index()  # no explicit evidence_root -> must use the fallback above
    assert payload["n_in_scope"] == 22
    assert payload["tally"] == live_payload["tally"]


def test_default_evidence_root_prefers_live_tree_when_present(tmp_path, monkeypatch):
    """The converse of the fallback test above: when the live tree exists
    and is non-empty, it must still win over the bundle (no behavior change
    for local dev iterating against a real sweep)."""
    live_root = tmp_path / "artifacts" / "l2_2_gates"
    (live_root / "SomeProcess" / "latest").mkdir(parents=True)
    (live_root / "SomeProcess" / "latest" / "result.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(schema, "EVIDENCE_ROOT", live_root)

    assert schema.default_evidence_root() == live_root


def test_resolve_input_path_falls_back_to_current_repo_root_by_suffix(tmp_path, monkeypatch):
    """`generator._resolve_input_path` must recover from a recorded absolute
    path baked in at a *different* worktree/clone root than the one running
    right now, by matching the longest path suffix that resolves to a real
    file under the CURRENT `cat.REPO_ROOT` -- this is what lets current-tree
    staleness checking work when the evidence bundle is read from a
    different clone/worktree than the one that generated it, without ever
    touching the runner's own (off-limits) absolute-path-recording
    behavior."""
    fake_repo_root = tmp_path / "some_other_clone_root"
    real_relative = Path("data") / "m1_sources" / "portability_test_fixture.txt"
    (fake_repo_root / real_relative.parent).mkdir(parents=True)
    (fake_repo_root / real_relative).write_text("fixture content", encoding="utf-8")

    monkeypatch.setattr(cat, "REPO_ROOT", fake_repo_root)
    monkeypatch.setattr(gen.cat, "REPO_ROOT", fake_repo_root)

    # A path recorded at a totally different, nonexistent absolute location,
    # but sharing the same trailing relative structure as the real file.
    recorded_elsewhere = "/mnt/e/some-worktree-that-no-longer-exists/" + str(real_relative).replace("\\", "/")
    resolved = gen._resolve_input_path(recorded_elsewhere)
    assert resolved == fake_repo_root / real_relative
    assert resolved.read_text(encoding="utf-8") == "fixture content"


def test_resolve_input_path_prefers_exact_absolute_match_when_it_exists(tmp_path):
    """If the recorded absolute path still exists as-is (same worktree,
    unmoved -- the common case), it must be used directly rather than
    going through suffix-matching, so genuine content drift there is still
    caught exactly as before."""
    real_file = tmp_path / "still_here.json"
    real_file.write_text("{}", encoding="utf-8")
    resolved = gen._resolve_input_path(str(real_file))
    assert resolved == real_file
