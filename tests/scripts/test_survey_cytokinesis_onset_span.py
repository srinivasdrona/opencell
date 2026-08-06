"""Unit tests for `scripts/l2_event/survey_cytokinesis_onset_span.py`
(Opus review, 2026-08-05, item 4: a small, explicitly read-only survey
tool -- never an uncontrolled 50-seed launch -- that reports the
onset-to-completion span over whatever Cytokinesis event-window seeds
already exist on disk, and refuses to claim a cohort-wide maximum until
all 50 required seeds are present."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.l2_event.survey_cytokinesis_onset_span as survey

_REAL_CYTOKINESIS_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s000"
    / "Cytokinesis_4000ticks.mat"
)


def test_discover_traces_finds_seed_from_directory_and_file_name(tmp_path, monkeypatch):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    seed_dir = tmp_path / "per_process_traces_v2_event_s007"
    seed_dir.mkdir()
    trace = seed_dir / "Cytokinesis_4000ticks.mat"
    trace.write_bytes(b"")
    found = survey.discover_traces()
    assert found == {7: trace}


def test_discover_traces_ignores_non_cytokinesis_files_and_non_seed_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    seed_dir = tmp_path / "per_process_traces_v2_event_s000"
    seed_dir.mkdir()
    (seed_dir / "RibosomeAssembly_100ticks.mat").write_bytes(b"")
    other_dir = tmp_path / "per_process_traces_v2_s000"
    other_dir.mkdir()
    (other_dir / "Cytokinesis_100ticks.mat").write_bytes(b"")
    assert survey.discover_traces() == {}


def test_discover_traces_returns_empty_dict_when_trace_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path / "does_not_exist")
    assert survey.discover_traces() == {}


def test_main_reports_no_traces_found(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    exit_code = survey.main([])
    assert exit_code == 1
    assert "nothing to survey" in capsys.readouterr().out


@pytest.mark.skipif(not _REAL_CYTOKINESIS_TRACE.exists(), reason="Real Cytokinesis seed-000 event-window MAT not present locally")
def test_main_reports_partial_survey_with_the_one_real_seed(monkeypatch, capsys):
    """With only the seed-0 Canary D trace present (1/50), the survey
    must print a partial-survey refusal and exit nonzero -- it must
    never claim a cohort-wide maximum from a single seed."""
    monkeypatch.setattr(survey, "TRACE_ROOT", _REAL_CYTOKINESIS_TRACE.parent.parent)
    exit_code = survey.main([])
    assert exit_code == 2
    out = capsys.readouterr().out
    assert "1/50 required seeds present" in out
    assert "PARTIAL SURVEY ONLY" in out
    assert "seed=000" in out


@pytest.mark.skipif(not _REAL_CYTOKINESIS_TRACE.exists(), reason="Real Cytokinesis seed-000 event-window MAT not present locally")
def test_onset_span_for_trace_matches_the_known_canary_d_values():
    """Ground-truth regression: the real seed-0 anchor trace's span must
    still compute to the exact Canary D closeout numbers (onset=27556,
    completion=31427, span=3871) -- if this ever drifts, either the
    trace or the onset/completion detection logic changed unexpectedly."""
    onset_abs, completion_abs, span = survey.onset_span_for_trace(_REAL_CYTOKINESIS_TRACE)
    assert onset_abs == 27556
    assert completion_abs == 31427
    assert span == 3871
