"""Targeted tests for scripts/l22_extraction/report.py's Phase 3 final-report
builder (`build_final_report`) and its seed-spec parser.

These tests exercise the report's aggregation/scoping logic (missing-file
detection, loader-warning detection, overall PASS/INCOMPLETE result) against
synthetic fixtures, without touching real Karr trace data or invoking
MATLAB/the real oracle loader. `derive_scope`, `canonical_seed0_path`,
`seed_mat_path`, and `loader_report` are monkeypatched at the point of use
inside `scripts.l22_extraction.report` (that module imports them by name, so
patching the module's own attribute is sufficient and does not require
touching the real underlying implementations).

Run via `bin\\oc-pytest tests/scripts/test_l22_report_final.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.l22_extraction.report as report_mod  # noqa: E402
from scripts.l22_extraction.derive_scope import ScopeReport  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def _healthy_loader(canonical_seed_count: int = 50, warnings: tuple[str, ...] = ()) -> dict:
    return {"ok": True, "canonical_seed_count": canonical_seed_count, "warnings": list(warnings)}


def _fake_scope(production: tuple[str, ...] = (), specialized_excluded: dict[str, str] | None = None) -> ScopeReport:
    """Build a minimal `ScopeReport` for tests; the event-class/out-of-scope/
    design-a-per-tick fields are irrelevant to `build_final_report` (it only
    reads `.production` and `.specialized_excluded`), so they're left empty."""
    return ScopeReport(
        production=production,
        specialized_excluded=specialized_excluded or {},
        event_class_excluded=(),
        out_of_scope_excluded=(),
        design_a_per_tick_in_scope=(),
    )


def test_parse_seed_spec_handles_ranges_and_commas():
    assert report_mod._parse_seed_spec("2-5") == [2, 3, 4, 5]
    assert report_mod._parse_seed_spec("1,3,7-9") == [1, 3, 7, 8, 9]
    assert report_mod._parse_seed_spec("5") == [5]


def test_build_final_report_passes_when_all_seeds_present(tmp_path, monkeypatch):
    """A production process with a valid seed0 and every requested seed
    present, plus a healthy loader report, must not appear in
    `missing_or_failing`, and the overall result must be PASS."""
    process = "FakeProcessA"
    seed0_path = write_synthetic_trace(
        tmp_path / "canonical" / f"{process}_100ticks.mat", process_name=process, seed=0, n_ticks=100
    )
    seed_paths = {
        seed: write_synthetic_trace(
            tmp_path / f"s{seed:03d}" / f"{process}_100ticks.mat", process_name=process, seed=seed, n_ticks=100
        )
        for seed in (1, 2)
    }

    monkeypatch.setattr(
        report_mod,
        "derive_scope",
        lambda: _fake_scope(production=(process,)),
    )
    monkeypatch.setattr(report_mod, "canonical_seed0_path", lambda proc, **_: seed0_path)
    monkeypatch.setattr(report_mod, "seed_mat_path", lambda proc, seed, **_: seed_paths[seed])
    monkeypatch.setattr(report_mod, "loader_report", lambda proc: _healthy_loader())
    monkeypatch.setattr(report_mod, "git_blob_sha256", lambda path: "deadbeef")

    result = report_mod.build_final_report(seeds=[1, 2])

    assert result["missing_or_failing"] == []
    assert result["result"] == "PASS"
    assert result["files"][process]["0"]["ok"] is True
    assert result["files"][process]["2"]["ok"] is True


def test_build_final_report_flags_missing_seed_file(tmp_path, monkeypatch):
    """A process missing one of its requested seed files must be reported
    in `missing_or_failing` with the exact process/seed identified, and the
    overall result must be INCOMPLETE -- this is the exact mechanism that
    correctly surfaced the 5 Phase-2-blocked processes as still incomplete
    in the real Phase 3 run (seeds 2-49 never generated for them)."""
    process = "FakeProcessB"
    seed0_path = write_synthetic_trace(
        tmp_path / "canonical" / f"{process}_100ticks.mat", process_name=process, seed=0, n_ticks=100
    )
    seed1_path = write_synthetic_trace(
        tmp_path / "s001" / f"{process}_100ticks.mat", process_name=process, seed=1, n_ticks=100
    )
    missing_seed2_path = tmp_path / "s002" / f"{process}_100ticks.mat"  # deliberately never written

    monkeypatch.setattr(
        report_mod,
        "derive_scope",
        lambda: _fake_scope(production=(process,)),
    )
    monkeypatch.setattr(report_mod, "canonical_seed0_path", lambda proc, **_: seed0_path)
    monkeypatch.setattr(
        report_mod,
        "seed_mat_path",
        lambda proc, seed, **_: seed1_path if seed == 1 else missing_seed2_path,
    )
    monkeypatch.setattr(report_mod, "loader_report", lambda proc: _healthy_loader())
    monkeypatch.setattr(report_mod, "git_blob_sha256", lambda path: "deadbeef")

    result = report_mod.build_final_report(seeds=[1, 2])

    assert result["result"] == "INCOMPLETE"
    assert len(result["missing_or_failing"]) == 1
    assert f"{process} seed2" in result["missing_or_failing"][0]
    assert "does not exist" in result["missing_or_failing"][0]


def test_build_final_report_flags_wrong_canonical_seed_count(tmp_path, monkeypatch):
    """Even with every file present, a loader-reported `canonical_seed_count`
    that doesn't equal 50 must be flagged (guards against the loader
    silently under/over-counting seeds)."""
    process = "FakeProcessC"
    seed0_path = write_synthetic_trace(
        tmp_path / "canonical" / f"{process}_100ticks.mat", process_name=process, seed=0, n_ticks=100
    )
    seed1_path = write_synthetic_trace(
        tmp_path / "s001" / f"{process}_100ticks.mat", process_name=process, seed=1, n_ticks=100
    )

    monkeypatch.setattr(
        report_mod,
        "derive_scope",
        lambda: _fake_scope(production=(process,)),
    )
    monkeypatch.setattr(report_mod, "canonical_seed0_path", lambda proc, **_: seed0_path)
    monkeypatch.setattr(report_mod, "seed_mat_path", lambda proc, seed, **_: seed1_path)
    monkeypatch.setattr(report_mod, "loader_report", lambda proc: _healthy_loader(canonical_seed_count=49))
    monkeypatch.setattr(report_mod, "git_blob_sha256", lambda path: "deadbeef")

    result = report_mod.build_final_report(seeds=[1])

    assert result["result"] == "INCOMPLETE"
    assert any("canonical_seed_count=49" in item for item in result["missing_or_failing"])


def test_build_final_report_flags_karr_single_seed_reused_warning(tmp_path, monkeypatch):
    """A `KARR_SINGLE_SEED_REUSED`-class loader warning must be treated as a
    hard failure even when `canonical_seed_count` reports 50 and every file
    is structurally valid -- this is the exact regression this task's
    hard policy is designed to prevent (a process silently reusing one seed
    dressed up as 50 distinct seeds)."""
    process = "FakeProcessD"
    seed0_path = write_synthetic_trace(
        tmp_path / "canonical" / f"{process}_100ticks.mat", process_name=process, seed=0, n_ticks=100
    )
    seed1_path = write_synthetic_trace(
        tmp_path / "s001" / f"{process}_100ticks.mat", process_name=process, seed=1, n_ticks=100
    )

    monkeypatch.setattr(
        report_mod,
        "derive_scope",
        lambda: _fake_scope(production=(process,)),
    )
    monkeypatch.setattr(report_mod, "canonical_seed0_path", lambda proc, **_: seed0_path)
    monkeypatch.setattr(report_mod, "seed_mat_path", lambda proc, seed, **_: seed1_path)
    monkeypatch.setattr(
        report_mod,
        "loader_report",
        lambda proc: _healthy_loader(warnings=("KARR_SINGLE_SEED_REUSED: only seed 0 available",)),
    )
    monkeypatch.setattr(report_mod, "git_blob_sha256", lambda path: "deadbeef")

    result = report_mod.build_final_report(seeds=[1])

    assert result["result"] == "INCOMPLETE"
    assert any("KARR_SINGLE_SEED_REUSED" in item for item in result["missing_or_failing"])


def test_build_final_report_checks_specialized_ensembles_independently_of_file_scan(monkeypatch):
    """Specialized ensembles (Transcription/Translation) are not part of the
    per-seed file scan (they're excluded from `scope.production`); only
    their loader-reported seed count is checked. A drifted specialized
    ensemble must still surface as INCOMPLETE."""
    monkeypatch.setattr(
        report_mod,
        "derive_scope",
        lambda: _fake_scope(specialized_excluded={"Transcription": "50-seed ensemble", "Translation": "50-seed ensemble"}),
    )
    monkeypatch.setattr(report_mod, "loader_report", lambda proc: _healthy_loader(canonical_seed_count=48 if proc == "Translation" else 50))
    monkeypatch.setattr(report_mod, "git_blob_sha256", lambda path: None)

    result = report_mod.build_final_report(seeds=[])

    assert result["result"] == "INCOMPLETE"
    assert any("Translation (specialized)" in item for item in result["missing_or_failing"])
