"""Tests for scripts/l22_evidence/sweep.py -- the resumable, bounded-parallel
Design-A runner sweep launcher.

Uses a FAKE, fast `command_builder` (never the real
`tests/vivarium/l2_2_design_a_runner.py`, which is slow and touches real
raw-oracle .mat data) so parallelism/resume/exit-code/failure-reporting
logic can be validated cheaply and deterministically. `plan_sweep()` itself
is exercised against the real PROCESS_CATALOG.yaml (read-only) to prove the
real 18-process/M_ticks/N_seeds derivation is correct.

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_sweep.py -v`.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import sweep  # noqa: E402


# --- plan_sweep against the REAL catalog ---------------------------------------


def test_plan_sweep_default_covers_all_18_design_a_per_tick_processes():
    jobs = sweep.plan_sweep()
    assert len(jobs) == 18
    assert len({j.process for j in jobs}) == 18
    for job in jobs:
        assert job.seeds == 50
        assert isinstance(job.m_ticks, int) and job.m_ticks > 0


def test_plan_sweep_metabolism_m_ticks_is_20_from_real_catalog():
    jobs = {j.process: j for j in sweep.plan_sweep(["Metabolism"])}
    assert jobs["Metabolism"].m_ticks == 20
    assert jobs["Metabolism"].seeds == 50


def test_plan_sweep_output_and_log_paths_are_disjoint_per_process():
    jobs = sweep.plan_sweep()
    output_dirs = {j.output_dir for j in jobs}
    log_paths = {j.log_path for j in jobs}
    assert len(output_dirs) == len(jobs)
    assert len(log_paths) == len(jobs)


def test_plan_sweep_rejects_unknown_or_event_class_process_names():
    with pytest.raises(ValueError, match="not in-scope design_a_per_tick"):
        sweep.plan_sweep(["NotARealProcess"])
    with pytest.raises(ValueError, match="not in-scope design_a_per_tick"):
        sweep.plan_sweep(["DNADamage"])  # a real catalog process, but event_class


# --- evidence_is_valid resume semantics -----------------------------------------


def _make_job(tmp_path: Path, process: str = "FakeProc", seeds: int = 3, m_ticks: int = 5) -> sweep.SweepJob:
    return sweep.SweepJob(
        process=process,
        seeds=seeds,
        m_ticks=m_ticks,
        output_dir=tmp_path / "evidence" / process / "latest",
        log_path=tmp_path / "logs" / f"{process}.log",
    )


def _write_valid_evidence(job: sweep.SweepJob) -> None:
    job.output_dir.mkdir(parents=True, exist_ok=True)
    expected_seeds = list(range(job.seeds))
    (job.output_dir / "result.json").write_text(
        json.dumps({"process": job.process, "seeds": expected_seeds, "ticks": job.m_ticks, "verdict": "PASS"}),
        encoding="utf-8",
    )
    (job.output_dir / "input_manifest.json").write_text(
        json.dumps({"resolved_seeds": expected_seeds, "m_ticks": job.m_ticks, "inputs": []}), encoding="utf-8"
    )
    (job.output_dir / "provenance.json").write_text(json.dumps({"git_sha": "deadbeef"}), encoding="utf-8")


def test_evidence_is_valid_missing_directory_is_invalid(tmp_path):
    job = _make_job(tmp_path)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "missing" in reason


def test_evidence_is_valid_complete_matching_evidence_is_valid(tmp_path):
    job = _make_job(tmp_path)
    _write_valid_evidence(job)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is True
    assert reason is None


def test_evidence_is_valid_seed_count_mismatch_is_invalid(tmp_path):
    job = _make_job(tmp_path, seeds=3)
    _write_valid_evidence(job)
    # Simulate a stale evidence dir written for a smaller seed count (e.g. an
    # old M=10 lie): overwrite with fewer resolved seeds than the job wants.
    stale_job = _make_job(tmp_path, seeds=2)
    _write_valid_evidence(stale_job)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "seeds" in reason


def test_evidence_is_valid_ticks_mismatch_is_invalid(tmp_path):
    job = _make_job(tmp_path, m_ticks=5)
    _write_valid_evidence(job)
    mismatched_job = _make_job(tmp_path, m_ticks=999)
    valid, reason = sweep.evidence_is_valid(mismatched_job)
    assert valid is False
    assert "ticks" in reason


def test_evidence_is_valid_process_name_mismatch_is_invalid(tmp_path):
    job = _make_job(tmp_path, process="Alpha")
    _write_valid_evidence(job)
    other_job = sweep.SweepJob(
        process="Beta", seeds=job.seeds, m_ticks=job.m_ticks, output_dir=job.output_dir, log_path=job.log_path
    )
    valid, reason = sweep.evidence_is_valid(other_job)
    assert valid is False
    assert "process" in reason


def test_evidence_is_valid_unparseable_json_is_invalid(tmp_path):
    job = _make_job(tmp_path)
    job.output_dir.mkdir(parents=True, exist_ok=True)
    (job.output_dir / "result.json").write_text("{not json", encoding="utf-8")
    (job.output_dir / "input_manifest.json").write_text("{}", encoding="utf-8")
    (job.output_dir / "provenance.json").write_text("{}", encoding="utf-8")
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "parse" in reason


# --- run_job / run_sweep with a FAKE fast command_builder -----------------------


def _fake_ok_command(job: sweep.SweepJob) -> list[str]:
    """A fake 'runner' that writes valid matching evidence and exits 0."""
    script = (
        "import json,sys\n"
        f"import pathlib\n"
        f"out = pathlib.Path(r'{job.output_dir}')\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        f"seeds = list(range({job.seeds}))\n"
        f"(out / 'result.json').write_text(json.dumps(dict(process={job.process!r}, seeds=seeds, ticks={job.m_ticks}, verdict='PASS')))\n"
        f"(out / 'input_manifest.json').write_text(json.dumps(dict(resolved_seeds=seeds, m_ticks={job.m_ticks}, inputs=[])))\n"
        "(out / 'provenance.json').write_text(json.dumps(dict(git_sha='fake')))\n"
        "print('fake runner ok')\n"
    )
    return [sys.executable, "-c", script]


def _fake_failing_command(job: sweep.SweepJob) -> list[str]:
    return [sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(1)"]


def _fake_slow_command(job: sweep.SweepJob, delay_s: float = 0.3) -> list[str]:
    script = f"import time; time.sleep({delay_s}); print('slow runner done')"
    return [sys.executable, "-c", script]


def test_run_job_success_writes_log_and_returns_exit_0(tmp_path):
    job = _make_job(tmp_path, process="Ok1")
    result = sweep.run_job(job, command_builder=_fake_ok_command)
    assert result.status == sweep.JOB_STATUS_RAN_OK
    assert result.exit_code == 0
    assert (tmp_path / "logs" / "Ok1.log").is_file()
    assert "fake runner ok" in (tmp_path / "logs" / "Ok1.log").read_text(encoding="utf-8")
    valid, _ = sweep.evidence_is_valid(job)
    assert valid is True


def test_run_job_failure_captures_nonzero_exit_and_reason(tmp_path):
    job = _make_job(tmp_path, process="Bad1")
    result = sweep.run_job(job, command_builder=_fake_failing_command)
    assert result.status == sweep.JOB_STATUS_RAN_FAIL
    assert result.exit_code == 1
    assert "boom" in result.reason


def test_run_job_skips_when_already_valid_and_not_forced(tmp_path):
    job = _make_job(tmp_path, process="AlreadyDone")
    _write_valid_evidence(job)
    result = sweep.run_job(job, command_builder=_fake_failing_command)  # would fail if actually run
    assert result.status == sweep.JOB_STATUS_SKIPPED_VALID
    assert result.exit_code is None


def test_run_job_force_reruns_even_when_valid(tmp_path):
    job = _make_job(tmp_path, process="ForceMe")
    _write_valid_evidence(job)
    result = sweep.run_job(job, force=True, command_builder=_fake_ok_command)
    assert result.status == sweep.JOB_STATUS_RAN_OK


def test_run_job_never_overwrites_valid_evidence_without_force(tmp_path):
    job = _make_job(tmp_path, process="Untouched")
    _write_valid_evidence(job)
    before = (job.output_dir / "result.json").read_text(encoding="utf-8")
    sweep.run_job(job, command_builder=_fake_failing_command)
    after = (job.output_dir / "result.json").read_text(encoding="utf-8")
    assert before == after


def test_run_sweep_bounded_parallel_all_jobs_complete_in_submission_order(tmp_path):
    jobs = [_make_job(tmp_path, process=f"Proc{i}") for i in range(6)]
    results = sweep.run_sweep(jobs, max_workers=3, command_builder=_fake_ok_command)
    assert [r.process for r in results] == [j.process for j in jobs]
    assert all(r.status == sweep.JOB_STATUS_RAN_OK for r in results)


def test_run_sweep_bounded_parallelism_is_actually_bounded(tmp_path):
    """With max_workers=2 and 4 jobs that each sleep, no more than 2 should
    ever run concurrently -- verified via wall-clock: 4 jobs * 0.3s each
    with concurrency 2 must take at least ~2 batches worth of time."""
    jobs = [_make_job(tmp_path, process=f"Slow{i}") for i in range(4)]
    start = time.perf_counter()
    results = sweep.run_sweep(jobs, max_workers=2, command_builder=lambda j: _fake_slow_command(j, 0.3))
    elapsed = time.perf_counter() - start
    assert all(r.status == sweep.JOB_STATUS_RAN_OK for r in results)
    # 4 jobs / 2 workers = 2 sequential batches of ~0.3s each => >= ~0.5s;
    # generously bounded above to avoid flakiness on a loaded CI box.
    assert elapsed >= 0.5


def test_run_sweep_mixed_success_and_failure_reports_both(tmp_path):
    ok_job = _make_job(tmp_path, process="MixedOk")
    bad_job = _make_job(tmp_path, process="MixedBad")

    def _builder(job: sweep.SweepJob) -> list[str]:
        return _fake_ok_command(job) if job.process == "MixedOk" else _fake_failing_command(job)

    results = sweep.run_sweep([ok_job, bad_job], max_workers=2, command_builder=_builder)
    by_process = {r.process: r for r in results}
    assert by_process["MixedOk"].status == sweep.JOB_STATUS_RAN_OK
    assert by_process["MixedBad"].status == sweep.JOB_STATUS_RAN_FAIL


# --- write_sweep_report ----------------------------------------------------------


def test_write_sweep_report_is_compact_and_records_tally(tmp_path):
    jobs = [_make_job(tmp_path, process="RepOk"), _make_job(tmp_path, process="RepBad")]

    def _builder(job: sweep.SweepJob) -> list[str]:
        return _fake_ok_command(job) if job.process == "RepOk" else _fake_failing_command(job)

    results = sweep.run_sweep(jobs, max_workers=2, command_builder=_builder)
    report_path = tmp_path / "report.json"
    payload = sweep.write_sweep_report(results, report_path)

    assert report_path.is_file()
    on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert payload["n_jobs"] == 2
    assert payload["tally"][sweep.JOB_STATUS_RAN_OK] == 1
    assert payload["tally"][sweep.JOB_STATUS_RAN_FAIL] == 1
    # Compact: no raw per-tick arrays/channel numbers in the sweep report itself.
    assert "channels" not in json.dumps(payload)


# --- status_snapshot / write_status_snapshot (read-only interim progress) ------


def test_status_snapshot_not_started_when_no_output_or_log(tmp_path):
    job = _make_job(tmp_path, process="Fresh")
    rows = sweep.status_snapshot([job])
    assert rows[0]["status"] == sweep.STATUS_NOT_STARTED
    assert rows[0]["log_path"] is None


def test_status_snapshot_done_valid_when_evidence_present(tmp_path):
    job = _make_job(tmp_path, process="Finished")
    _write_valid_evidence(job)
    rows = sweep.status_snapshot([job])
    assert rows[0]["status"] == sweep.STATUS_DONE_VALID
    assert rows[0]["stored_verdict"] == "PASS"


def test_status_snapshot_in_progress_when_log_exists_but_incomplete(tmp_path):
    job = _make_job(tmp_path, process="Running")
    job.log_path.parent.mkdir(parents=True, exist_ok=True)
    job.log_path.write_text("# command: [...]\n# started_at: now\nsome progress output\n", encoding="utf-8")
    rows = sweep.status_snapshot([job])
    assert rows[0]["status"] == sweep.STATUS_IN_PROGRESS


def test_status_snapshot_done_failed_when_log_shows_error_but_no_evidence(tmp_path):
    job = _make_job(tmp_path, process="Crashed")
    job.log_path.parent.mkdir(parents=True, exist_ok=True)
    job.log_path.write_text("# command: [...]\nTraceback (most recent call last):\nValueError: boom\n", encoding="utf-8")
    rows = sweep.status_snapshot([job])
    assert rows[0]["status"] == sweep.STATUS_DONE_INVALID_OR_FAILED


def test_write_status_snapshot_is_compact_and_tallies(tmp_path):
    done_job = _make_job(tmp_path, process="Done1")
    _write_valid_evidence(done_job)
    fresh_job = _make_job(tmp_path, process="Fresh1")
    rows = sweep.status_snapshot([done_job, fresh_job])
    out_path = tmp_path / "status.json"
    payload = sweep.write_status_snapshot(rows, out_path)
    assert out_path.is_file()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert payload["tally"][sweep.STATUS_DONE_VALID] == 1
    assert payload["tally"][sweep.STATUS_NOT_STARTED] == 1
    assert "channels" not in json.dumps(payload)


def test_cli_status_is_read_only_and_reports_real_catalog_processes(tmp_path, capsys):
    exit_code = sweep.main(
        [
            "status",
            "--processes",
            "Metabolism,DNARepair",
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--log-dir",
            str(tmp_path / "logs"),
            "--status-out",
            str(tmp_path / "status.json"),
        ]
    )
    assert exit_code == 0
    payload = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert payload["n_jobs"] == 2
    assert all(row["status"] == sweep.STATUS_NOT_STARTED for row in payload["jobs"])
    # Read-only: no evidence/log dirs should have been created as a side effect.
    assert not (tmp_path / "evidence").exists()



def test_cli_plan_does_not_execute_anything(tmp_path, capsys):
    exit_code = sweep.main(["plan", "--processes", "Metabolism,DNARepair", "--log-dir", str(tmp_path / "logs")])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Metabolism" in out
    assert "DNARepair" in out


def test_cli_run_with_fake_process_via_monkeypatched_runner_script(tmp_path, monkeypatch):
    """End-to-end CLI smoke test: monkeypatch RUNNER_SCRIPT to a tiny fake
    script so `run` exercises the real argv-building path (`runner_command`)
    without invoking the real slow Design-A harness."""
    fake_runner = tmp_path / "fake_runner.py"
    fake_runner.write_text(
        "import argparse, json, pathlib\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--process', required=True)\n"
        "p.add_argument('--seeds', required=True)\n"
        "p.add_argument('--ticks', required=True)\n"
        "p.add_argument('--output-dir', required=True)\n"
        "a = p.parse_args()\n"
        "out = pathlib.Path(a.output_dir)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "seeds = list(range(int(a.seeds)))\n"
        "(out / 'result.json').write_text(json.dumps(dict(process=a.process, seeds=seeds, ticks=int(a.ticks), verdict='PASS')))\n"
        "(out / 'input_manifest.json').write_text(json.dumps(dict(resolved_seeds=seeds, m_ticks=int(a.ticks), inputs=[])))\n"
        "(out / 'provenance.json').write_text(json.dumps(dict(git_sha='fake')))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sweep, "RUNNER_SCRIPT", fake_runner)

    evidence_root = tmp_path / "evidence"

    exit_code = sweep.main(
        [
            "run",
            "--processes",
            "Metabolism",
            "--max-workers",
            "1",
            "--evidence-root",
            str(evidence_root),
            "--log-dir",
            str(tmp_path / "logs"),
            "--report-out",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["tally"][sweep.JOB_STATUS_RAN_OK] == 1
    assert (evidence_root / "Metabolism" / "latest" / "result.json").is_file()
