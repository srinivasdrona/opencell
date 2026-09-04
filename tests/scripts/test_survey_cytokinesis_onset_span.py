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
    found = survey.discover_traces(m_ticks=4000)
    assert found == {7: trace}


def test_discover_traces_filters_out_a_different_m_ticks_cohort(tmp_path, monkeypatch):
    """A trace preregistered under a DIFFERENT M_ticks (e.g. the preserved
    4000-tick cohort) must never appear in a 5000-tick survey, and vice
    versa -- mixing cohorts would silently compare two non-comparable
    populations (2026-09-04 corrective fix, item 4)."""
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    seed_dir = tmp_path / "per_process_traces_v2_event_s007"
    seed_dir.mkdir()
    (seed_dir / "Cytokinesis_4000ticks.mat").write_bytes(b"")
    assert survey.discover_traces(m_ticks=5000) == {}
    assert len(survey.discover_traces(m_ticks=4000)) == 1


def test_discover_traces_ignores_non_cytokinesis_files_and_non_seed_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    seed_dir = tmp_path / "per_process_traces_v2_event_s000"
    seed_dir.mkdir()
    (seed_dir / "RibosomeAssembly_100ticks.mat").write_bytes(b"")
    other_dir = tmp_path / "per_process_traces_v2_s000"
    other_dir.mkdir()
    (other_dir / "Cytokinesis_100ticks.mat").write_bytes(b"")
    assert survey.discover_traces(m_ticks=100) == {}


def test_discover_traces_returns_empty_dict_when_trace_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path / "does_not_exist")
    assert survey.discover_traces(m_ticks=5000) == {}


def test_main_reports_no_traces_found(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    exit_code = survey.main([])
    assert exit_code == 1
    assert "nothing to survey" in capsys.readouterr().out


def test_main_defaults_m_ticks_from_the_shared_spec(tmp_path, monkeypatch, capsys):
    from scripts.l2_event.division_window_spec import CYTOKINESIS_M_TICKS

    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    exit_code = survey.main([])
    assert exit_code == 1
    assert f"Cytokinesis_{CYTOKINESIS_M_TICKS}ticks.mat" in capsys.readouterr().out


def test_main_m_ticks_flag_overrides_the_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    exit_code = survey.main(["--m-ticks", "4000"])
    assert exit_code == 1
    assert "Cytokinesis_4000ticks.mat" in capsys.readouterr().out


@pytest.mark.skipif(not _REAL_CYTOKINESIS_TRACE.exists(), reason="Real Cytokinesis seed-000 event-window MAT not present locally")
def test_main_reports_partial_survey_with_the_one_real_seed(monkeypatch, capsys):
    """With only the seed-0 Canary D trace present (1/50) under its own
    preserved M_ticks=4000 cohort, the survey must print a partial-survey
    refusal and exit nonzero -- it must never claim a cohort-wide maximum
    from a single seed. Explicitly surveys the M_ticks=4000 cohort (the
    2026-09-04 fix's default is now M_ticks=5000, under which this
    preserved trace is non-authoritative and correctly excluded -- see
    test_main_m_ticks_flag_overrides_the_default)."""
    monkeypatch.setattr(survey, "TRACE_ROOT", _REAL_CYTOKINESIS_TRACE.parent.parent)
    exit_code = survey.main(["--m-ticks", "4000"])
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
    onset_abs, completion_abs, span = survey.onset_span_for_trace(_REAL_CYTOKINESIS_TRACE, m_ticks=4000)
    assert onset_abs == 27556
    assert completion_abs == 31427
    assert span == 3871


@pytest.mark.skipif(not _REAL_CYTOKINESIS_TRACE.exists(), reason="Real Cytokinesis seed-000 event-window MAT not present locally")
def test_onset_span_for_trace_fails_closed_on_m_ticks_metadata_mismatch():
    """A caller-asserted m_ticks that disagrees with the trace's own
    on-disk metadata.n_ticks must raise, never silently proceed (item 4:
    'fail closed on any trace whose metadata.n_ticks differs')."""
    with pytest.raises(survey.MTicksMetadataMismatchError):
        survey.onset_span_for_trace(_REAL_CYTOKINESIS_TRACE, m_ticks=5000)


# ---------------------------------------------------------------------------
# Provisional-margin gate (Opus final review, 2026-09-04): integration-level
# boundary tests through onset_span_for_trace itself. A real on-disk window
# has exactly n_ticks rows, so onset_row/completion_row are both confined to
# [0, n_ticks-1] -- the inclusive span computed from two in-window ticks can
# therefore never exceed n_ticks structurally. That means the M+1 (genuine
# overrun) case cannot be constructed as an on-disk trace at all; it is
# covered at the pure-function level by
# test_division_window_spec.py::test_margin_gate_rejects_span_one_tick_above_m_ticks.
# These two tests cover the two cases a real trace CAN exhibit: M-1 margin
# (accepted) and exactly-M (zero margin, rejected).
# ---------------------------------------------------------------------------


def _write_margin_probe_trace(path, *, n_ticks: int, tick_start: int, onset_row: int, completion_row: int):
    """Minimal synthetic Cytokinesis event-window trace with a real
    pinchedDiameter curve that decreases exactly once (at ``onset_row``)
    and reaches exactly zero exactly once (at ``completion_row``), sized
    exactly ``n_ticks`` rows so ``window.n_ticks == n_ticks`` (satisfying
    the m_ticks metadata check) while onset/completion are placed
    precisely -- a constant-then-single-step curve (no floating-point
    step accumulation) so the completion tick can never drift earlier due
    to rounding."""
    import h5py
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    before_pinched = np.full(n_ticks, 10.0, dtype=float)
    after_pinched = np.full(n_ticks, 10.0, dtype=float)
    # Before onset: flat at 10.0 (no decrease yet).
    # At onset_row: single strict decrease 10.0 -> 9.0 (the ratified onset
    # predicate: before > after >= 0).
    before_pinched[onset_row] = 10.0
    after_pinched[onset_row] = 9.0
    # Between onset and completion (exclusive): flat at 9.0 -- no further
    # decrease, so onset_row remains the ONLY strict-decrease tick.
    for row in range(onset_row + 1, completion_row):
        before_pinched[row] = 9.0
        after_pinched[row] = 9.0
    # At completion_row: before=9.0 (>0), after=0.0 -- the ratified
    # completion predicate, and the ONLY tick satisfying it.
    before_pinched[completion_row] = 9.0
    after_pinched[completion_row] = 0.0
    # After completion: flat at 0.0.
    before_pinched[completion_row + 1 :] = 0.0
    after_pinched[completion_row + 1 :] = 0.0

    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=np.array([ord(c) for c in "Cytokinesis"], dtype=np.uint16).reshape(-1, 1))
        metadata.create_dataset("rng_seed", data=np.array([0]))
        metadata.create_dataset("tick_offset", data=np.array([0.0]))
        metadata.create_dataset("stride", data=np.array([1]))
        metadata.create_dataset("tick_start", data=np.array([tick_start]))
        metadata.create_dataset("window_anchor", data=np.array([tick_start + completion_row]))
        metadata.create_dataset("onset_tick", data=np.array([tick_start + onset_row]))

        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        for observable in survey.REQUIRED_OBSERVABLES:
            if observable == "pinchedDiameter":
                before, after = before_pinched, after_pinched
            elif observable == "chromosome_segregated":
                before = after = np.ones(n_ticks, dtype=float)
            else:
                before = after = np.zeros(n_ticks, dtype=float)
            states_before.create_dataset(observable, data=before.reshape(1, -1))
            states_after.create_dataset(observable, data=after.reshape(1, -1))
    return path


def test_margin_gate_integration_accepts_span_one_tick_below_m_ticks(tmp_path):
    """M-1 margin: a real on-disk trace whose inclusive span is exactly
    m_ticks - 1 must be accepted by onset_span_for_trace's margin check."""
    m_ticks = 20
    trace = _write_margin_probe_trace(
        tmp_path / "Cytokinesis_20ticks.mat", n_ticks=m_ticks, tick_start=1000, onset_row=1, completion_row=m_ticks - 1
    )
    onset_abs, completion_abs, _span = survey.onset_span_for_trace(trace, m_ticks=m_ticks)
    inclusive_span = completion_abs - onset_abs + 1
    assert inclusive_span == m_ticks - 1  # must not raise


def test_margin_gate_integration_rejects_span_exactly_equal_to_m_ticks(tmp_path):
    """Exactly-M (zero margin): a real on-disk trace whose inclusive span
    equals m_ticks exactly must be REJECTED by onset_span_for_trace's
    margin check, even though it is a structurally complete, valid window
    by the MATLAB extractor's own (unchanged) capture invariant."""
    m_ticks = 20
    trace = _write_margin_probe_trace(
        tmp_path / "Cytokinesis_20ticks.mat", n_ticks=m_ticks, tick_start=1000, onset_row=0, completion_row=m_ticks - 1
    )
    with pytest.raises(survey.ProvisionalMarginOverrunError):
        survey.onset_span_for_trace(trace, m_ticks=m_ticks)


def test_main_fails_closed_and_reports_margin_overrun(tmp_path, monkeypatch, capsys):
    """main() must exit nonzero and print a clear MARGIN OVERRUN message
    rather than crash with a raw traceback when a surveyed seed hits the
    zero-margin boundary."""
    m_ticks = 20
    monkeypatch.setattr(survey, "TRACE_ROOT", tmp_path)
    seed_dir = tmp_path / "per_process_traces_v2_event_s001"
    _write_margin_probe_trace(
        seed_dir / f"Cytokinesis_{m_ticks}ticks.mat", n_ticks=m_ticks, tick_start=1000, onset_row=0, completion_row=m_ticks - 1
    )
    exit_code = survey.main(["--m-ticks", str(m_ticks)])
    assert exit_code == 3
    out = capsys.readouterr().out
    assert "MARGIN OVERRUN" in out
