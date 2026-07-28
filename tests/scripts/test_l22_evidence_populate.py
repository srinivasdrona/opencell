"""Tests for scripts/l22_evidence/populate.py -- the raw Karr-oracle
source-root merge tool.

Uses purely SYNTHETIC fixture files (plain bytes with realistic file names,
not real MATLAB .mat content) under tmp_path-based fake source roots. This
file NEVER touches the real sibling extraction worktrees
(E:\\opencell-worktrees\\l22-full-extract / l22-stale5-regen) -- per the task
instruction to design/test the population command now but not execute it
against real data until Phase-A code is committed and stale5 is integrated
into local main.

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_populate.py -v`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import populate  # noqa: E402


def _entry(**overrides) -> cat.ProcessEntry:
    base = dict(
        name="FakeProc",
        bucket="ALGORITHMIC_SHALLOW",
        harness_type="design_a_per_tick",
        m_ticks=100,
        n_seeds=50,
        primary_channel="substrates",
        closed_form_dominant="false",
        event_channels=(),
        output_channels=("substrates",),
        primary_distance="per_tick_vector_w1_mean",
    )
    base.update(overrides)
    return cat.ProcessEntry(**base)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _v2_seed_file(root: Path, process: str, seed: int) -> Path:
    return root / populate.KARR_NATIVE_SUBDIR / f"per_process_traces_v2_s{seed:03d}" / f"{process}_100ticks.mat"


def _v2_canonical_file(root: Path, process: str) -> Path:
    return root / populate.KARR_NATIVE_SUBDIR / "per_process_traces_v2" / f"{process}_100ticks.mat"


def _ensembles_seed_file(root: Path, process: str, seed: int) -> Path:
    return (
        root
        / populate.KARR_NATIVE_SUBDIR
        / "ensembles"
        / process.lower()
        / f"seed_{seed:03d}"
        / f"{process}_100ticks.mat"
    )


def _ensembles_manifest_file(root: Path, process: str) -> Path:
    return root / populate.KARR_NATIVE_SUBDIR / "ensembles" / process.lower() / "MANIFEST.json"


def _populate_all_v2_seeds(root: Path, process: str, seeds: range, *, content_prefix: bytes = b"seed") -> None:
    for seed in seeds:
        _write(_v2_seed_file(root, process, seed), content_prefix + str(seed).encode())


# --- Single-source resolution --------------------------------------------------


def test_single_source_full_v2_ensemble_resolves(tmp_path):
    source = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    _populate_all_v2_seeds(source.path, "FakeProc", range(50))

    report = populate.evaluate_process("FakeProc", _entry(), [source])
    assert report.status == populate.STATUS_RESOLVED
    assert report.layout == "v2"
    assert report.seed_count == 50
    assert len(report.selected_files) == 50


def test_no_data_anywhere_is_insufficient(tmp_path):
    source = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    (source.path / populate.KARR_NATIVE_SUBDIR).mkdir(parents=True)

    report = populate.evaluate_process("FakeProc", _entry(), [source])
    assert report.status == populate.STATUS_INSUFFICIENT_DATA
    assert report.seed_count == 0
    assert any("INSUFFICIENT_DATA" in p for p in report.problems)


def test_partial_seeds_below_required_is_insufficient(tmp_path):
    source = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    _populate_all_v2_seeds(source.path, "FakeProc", range(30))

    report = populate.evaluate_process("FakeProc", _entry(n_seeds=50), [source])
    assert report.status == populate.STATUS_INSUFFICIENT_DATA
    assert report.seed_count == 30


# --- Combining multiple sources -------------------------------------------------


def test_combining_two_non_overlapping_sources_resolves(tmp_path):
    clean11 = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    stale5 = populate.SourceRoot(name="stale5", path=tmp_path / "stale5")
    _populate_all_v2_seeds(clean11.path, "FakeProc", range(0, 25))
    _populate_all_v2_seeds(stale5.path, "FakeProc", range(25, 50))

    report = populate.evaluate_process("FakeProc", _entry(), [clean11, stale5])
    assert report.status == populate.STATUS_RESOLVED
    assert report.seed_count == 50
    source_names = {obs.source_name for obs in report.selected_files}
    assert source_names == {"clean11", "stale5"}


def test_duplicate_identical_file_across_sources_is_not_a_conflict(tmp_path):
    clean11 = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    stale5 = populate.SourceRoot(name="stale5", path=tmp_path / "stale5")
    _populate_all_v2_seeds(clean11.path, "FakeProc", range(50))
    _populate_all_v2_seeds(stale5.path, "FakeProc", range(50))  # identical content

    report = populate.evaluate_process("FakeProc", _entry(), [clean11, stale5])
    assert report.status == populate.STATUS_RESOLVED
    assert report.seed_count == 50
    # Deterministic: lexicographically-first source name wins when identical.
    assert all(obs.source_name == "clean11" for obs in report.selected_files)


# --- Split conflicts -------------------------------------------------------------


def test_conflicting_content_for_same_seed_across_sources_is_split_conflict(tmp_path):
    clean11 = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    stale5 = populate.SourceRoot(name="stale5", path=tmp_path / "stale5")
    _populate_all_v2_seeds(clean11.path, "FakeProc", range(50))
    _write(_v2_seed_file(stale5.path, "FakeProc", 7), b"DIFFERENT-CONTENT-FOR-SEED-7")

    report = populate.evaluate_process("FakeProc", _entry(), [clean11, stale5])
    assert report.status == populate.STATUS_SPLIT_CONFLICT
    assert any("SPLIT_CONFLICT" in p and "s007" in p for p in report.problems)
    assert any("clean11=" in p and "stale5=" in p for p in report.problems)


def test_split_conflict_blocks_resolution_even_with_enough_raw_seed_count(tmp_path):
    """50 total seed files exist, but one seed disagrees between sources --
    must not silently resolve just because the *count* looks sufficient."""
    clean11 = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    stale5 = populate.SourceRoot(name="stale5", path=tmp_path / "stale5")
    _populate_all_v2_seeds(clean11.path, "FakeProc", range(50))
    _write(_v2_seed_file(stale5.path, "FakeProc", 0), b"CONFLICTING-SEED-0")

    report = populate.evaluate_process("FakeProc", _entry(), [clean11, stale5])
    assert report.status == populate.STATUS_SPLIT_CONFLICT


# --- Ensembles layout + MANIFEST.json --------------------------------------------


def test_ensembles_layout_with_matching_manifest_resolves(tmp_path):
    source = populate.SourceRoot(name="specialized", path=tmp_path / "specialized")
    for seed in range(50):
        _write(_ensembles_seed_file(source.path, "Transcription", seed), f"seed{seed}".encode())
    _write(
        _ensembles_manifest_file(source.path, "Transcription"),
        json.dumps({"present_seed_count": 50}).encode(),
    )

    report = populate.evaluate_process("Transcription", _entry(name="Transcription", n_seeds=50), [source])
    assert report.status == populate.STATUS_RESOLVED
    assert report.layout == "ensembles"
    assert report.seed_count == 50


def test_ensembles_manifest_mismatch_fails(tmp_path):
    source = populate.SourceRoot(name="specialized", path=tmp_path / "specialized")
    for seed in range(40):
        _write(_ensembles_seed_file(source.path, "Transcription", seed), f"seed{seed}".encode())
    _write(
        _ensembles_manifest_file(source.path, "Transcription"),
        json.dumps({"present_seed_count": 50}).encode(),  # lies: only 40 actually present
    )

    report = populate.evaluate_process("Transcription", _entry(name="Transcription", n_seeds=50), [source])
    assert report.status == populate.STATUS_MANIFEST_MISMATCH
    assert any("MANIFEST_MISMATCH" in p and "40" in p for p in report.problems)


# --- apply_population / write_manifest -------------------------------------------


def test_apply_refuses_when_any_process_unresolved(tmp_path):
    resolved = populate.ProcessPopulationReport(
        process="A", status=populate.STATUS_RESOLVED, layout="v2", seed_count=50, required_seeds=50
    )
    unresolved = populate.ProcessPopulationReport(
        process="B", status=populate.STATUS_INSUFFICIENT_DATA, layout=None, seed_count=10, required_seeds=50
    )
    with pytest.raises(ValueError, match="not RESOLVED"):
        populate.apply_population({"A": resolved, "B": unresolved}, tmp_path / "current")


def test_apply_copies_resolved_files_into_current_root(tmp_path):
    clean11 = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    stale5 = populate.SourceRoot(name="stale5", path=tmp_path / "stale5")
    _populate_all_v2_seeds(clean11.path, "FakeProc", range(0, 25))
    _populate_all_v2_seeds(stale5.path, "FakeProc", range(25, 50))
    report = populate.evaluate_process("FakeProc", _entry(), [clean11, stale5])
    assert report.resolved

    current_root = tmp_path / "current_repo"
    copied = populate.apply_population({"FakeProc": report}, current_root)
    assert copied == 50
    for seed in range(50):
        dest = _v2_seed_file(current_root, "FakeProc", seed)
        assert dest.is_file()

    # Re-applying is idempotent (no re-copy needed, no error).
    copied_again = populate.apply_population({"FakeProc": report}, current_root)
    assert copied_again == 0


def test_apply_refuses_to_overwrite_divergent_existing_current_file(tmp_path):
    clean11 = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    _populate_all_v2_seeds(clean11.path, "FakeProc", range(50))
    report = populate.evaluate_process("FakeProc", _entry(), [clean11])
    assert report.resolved

    current_root = tmp_path / "current_repo"
    _write(_v2_seed_file(current_root, "FakeProc", 0), b"PRE-EXISTING-DIVERGENT-CONTENT")

    with pytest.raises(ValueError, match="refusing to overwrite"):
        populate.apply_population({"FakeProc": report}, current_root)


def test_write_manifest_records_source_and_process_detail(tmp_path):
    clean11 = populate.SourceRoot(name="clean11", path=tmp_path / "clean11")
    _populate_all_v2_seeds(clean11.path, "FakeProc", range(50))
    report = populate.evaluate_process("FakeProc", _entry(), [clean11])

    out_path = tmp_path / "manifest.json"
    payload = populate.write_manifest({"FakeProc": report}, [clean11], out_path)

    assert out_path.is_file()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert payload["processes"]["FakeProc"]["status"] == populate.STATUS_RESOLVED
    assert payload["processes"]["FakeProc"]["seed_count"] == 50
    assert len(payload["processes"]["FakeProc"]["files"]) == 50
    assert payload["sources"][0]["name"] == "clean11"


# --- Current-tree-as-implicit-source (specialized ensembles already in place) ----


def test_current_root_alone_can_satisfy_requirement(tmp_path):
    """Mirrors Transcription/Translation 'remain in their existing ensemble
    source' -- no external --source flag needed if the current tree already
    has a full ensemble."""
    current = populate.SourceRoot(name=populate.CURRENT_SOURCE_NAME, path=tmp_path / "current_repo")
    _populate_all_v2_seeds(current.path, "Transcription", range(50))

    report = populate.evaluate_process("Transcription", _entry(name="Transcription", n_seeds=50), [current])
    assert report.status == populate.STATUS_RESOLVED


# --- CLI-level integration (main()) using the REAL catalog, virtualized roots ----


def test_main_reports_nonzero_when_unresolved(tmp_path, monkeypatch):
    fake_current = tmp_path / "current_repo"
    fake_current.mkdir()
    monkeypatch.setattr(populate.cat, "REPO_ROOT", fake_current)

    exit_code = populate.main(["--processes", "ProteinDecay", "--out", str(tmp_path / "manifest.json")])
    assert exit_code == 1


def test_main_dry_run_is_zero_when_resolved_and_writes_nothing(tmp_path, monkeypatch):
    fake_current = tmp_path / "current_repo"
    clean11_root = tmp_path / "clean11"
    _populate_all_v2_seeds(clean11_root, "ProteinDecay", range(50))
    monkeypatch.setattr(populate.cat, "REPO_ROOT", fake_current)

    manifest_out = tmp_path / "manifest.json"
    exit_code = populate.main(
        ["--source", f"clean11={clean11_root}", "--processes", "ProteinDecay", "--out", str(manifest_out)]
    )
    assert exit_code == 0
    assert not manifest_out.exists(), "dry-run must not write the manifest"
    assert not (fake_current / populate.KARR_NATIVE_SUBDIR).exists(), "dry-run must not copy any files"


def test_main_apply_copies_and_writes_manifest_for_real_catalog_process(tmp_path, monkeypatch):
    fake_current = tmp_path / "current_repo"
    fake_current.mkdir()
    clean11_root = tmp_path / "clean11"
    _populate_all_v2_seeds(clean11_root, "ProteinDecay", range(50))
    monkeypatch.setattr(populate.cat, "REPO_ROOT", fake_current)

    manifest_out = tmp_path / "manifest.json"
    exit_code = populate.main(
        [
            "--source",
            f"clean11={clean11_root}",
            "--processes",
            "ProteinDecay",
            "--apply",
            "--out",
            str(manifest_out),
        ]
    )
    assert exit_code == 0
    assert manifest_out.is_file()
    payload = json.loads(manifest_out.read_text(encoding="utf-8"))
    assert payload["processes"]["ProteinDecay"]["status"] == populate.STATUS_RESOLVED
    for seed in range(50):
        assert _v2_seed_file(fake_current, "ProteinDecay", seed).is_file()
