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

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import (
    schema,  # noqa: E402
    sweep,  # noqa: E402
)
from tests.scripts._l22_evidence_fixtures import (  # noqa: E402
    write_mandatory_sidecars,
    write_valid_sweep_provenance,
)

# A single real, always-tracked repo file used as a stand-in
# `input_manifest.json["inputs"]` entry throughout this file: since R3, an
# empty `inputs` list is itself a failure (a real oracle-input reference is
# mandatory), and `_verify_input_manifest`/`run_job` rehash every entry
# against the CURRENT tree right after a (fake) run completes -- so this
# must point at a file that genuinely exists with a genuinely matching hash,
# never a synthetic/inexistent path.
_FIXTURE_INPUT_PATH = "tests/vivarium/l2_2_design_a_runner.py"
_FIXTURE_INPUT_RECORD = {
    "path": _FIXTURE_INPUT_PATH,
    "sha256": hashlib.sha256((REPO_ROOT / _FIXTURE_INPUT_PATH).read_bytes()).hexdigest(),
}


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
        json.dumps({"resolved_seeds": expected_seeds, "m_ticks": job.m_ticks, "inputs": [_FIXTURE_INPUT_RECORD]}),
        encoding="utf-8",
    )
    (job.output_dir / "provenance.json").write_text(json.dumps({"git_sha": "deadbeef"}), encoding="utf-8")
    write_mandatory_sidecars(job.output_dir)
    write_valid_sweep_provenance(job.output_dir, process=job.process, n_seeds=job.seeds, m_ticks=job.m_ticks)


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
    write_mandatory_sidecars(job.output_dir)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "parse" in reason


# --- run_job / run_sweep with a FAKE fast command_builder -----------------------


def _fake_ok_command(job: sweep.SweepJob) -> list[str]:
    """A fake 'runner' that writes valid matching evidence (authority files
    plus all four mandatory sidecars) and exits 0. `sweep_provenance.json`
    is deliberately NOT written here -- `run_job` itself writes that as the
    completion sentinel after validating this output, exactly like the real
    runner + sweep launcher."""
    script = (
        "import json,sys\n"
        f"import pathlib\n"
        f"out = pathlib.Path(r'{job.output_dir}')\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        f"seeds = list(range({job.seeds}))\n"
        f"(out / 'result.json').write_text(json.dumps(dict(process={job.process!r}, seeds=seeds, ticks={job.m_ticks}, verdict='PASS')))\n"
        f"(out / 'input_manifest.json').write_text(json.dumps(dict(resolved_seeds=seeds, m_ticks={job.m_ticks}, inputs=[{_FIXTURE_INPUT_RECORD!r}])))\n"
        "(out / 'provenance.json').write_text(json.dumps(dict(git_sha='fake')))\n"
        "(out / 'thresholds.json').write_text(json.dumps(dict(channels={})))\n"
        "(out / 'null_calibration.json').write_text(json.dumps(dict(channels={})))\n"
        "(out / 'SUMMARY.json').write_text(json.dumps(dict(note='fake')))\n"
        "(out / 'analytical_check.json').write_text(json.dumps(dict(applicable=False, reason='fake')))\n"
        "print('fake runner ok')\n"
    )
    return [sys.executable, "-c", script]


def _fake_failing_command(job: sweep.SweepJob) -> list[str]:
    return [sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(1)"]


def _fake_slow_command(job: sweep.SweepJob, delay_s: float = 0.3) -> list[str]:
    script = (
        f"import time,json,pathlib; time.sleep({delay_s})\n"
        f"out = pathlib.Path(r'{job.output_dir}')\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        f"seeds = list(range({job.seeds}))\n"
        f"(out / 'result.json').write_text(json.dumps(dict(process={job.process!r}, seeds=seeds, ticks={job.m_ticks}, verdict='PASS')))\n"
        f"(out / 'input_manifest.json').write_text(json.dumps(dict(resolved_seeds=seeds, m_ticks={job.m_ticks}, inputs=[{_FIXTURE_INPUT_RECORD!r}])))\n"
        "(out / 'provenance.json').write_text(json.dumps(dict(git_sha='fake')))\n"
        "(out / 'thresholds.json').write_text(json.dumps(dict(channels={})))\n"
        "(out / 'null_calibration.json').write_text(json.dumps(dict(channels={})))\n"
        "(out / 'SUMMARY.json').write_text(json.dumps(dict(note='fake')))\n"
        "(out / 'analytical_check.json').write_text(json.dumps(dict(applicable=False, reason='fake')))\n"
        "print('slow runner done')\n"
    )
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


def test_committed_sweep_status_is_not_a_stale_pre_run_snapshot():
    """Regression test for a real incident (l22-projection-rerun, 2026-07-31):
    a `sweep.py status` snapshot generated BEFORE a `sweep.py run --force`
    invocation had finished was committed alongside that same run's
    `sweep_report.json`, so the tracked `sweep_status.json` spuriously
    showed every just-reran process as IN_PROGRESS_OR_UNKNOWN even though
    the tracked report recorded a successful RAN_EXIT_0 for each of them.
    That mismatch went unnoticed until an external review caught it.

    Guard: for every process the tracked `sweep_report.json` records as
    RAN_EXIT_0 or SKIPPED_VALID (i.e. valid evidence existed on disk as of
    that report), the tracked `sweep_status.json` snapshot must show
    DONE_VALID_EVIDENCE for that same process -- never NOT_STARTED,
    IN_PROGRESS_OR_UNKNOWN, or DONE_NO_VALID_EVIDENCE. A process that is
    absent from the report (not part of that sweep invocation -- e.g.
    deliberately excluded, such as Replication pending its own rerun) is
    not constrained by this check. Also guards the simpler, complementary
    invariant that the status snapshot's own `generated_at` is not older
    than the report's, since a report generated after the status snapshot
    is the direct signature of "status was captured before the run"."""
    report_path = sweep.DEFAULT_REPORT_PATH
    status_path = sweep.DEFAULT_STATUS_PATH
    if not report_path.is_file() or not status_path.is_file():
        pytest.skip("no tracked sweep_report.json/sweep_status.json committed yet")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))

    assert status["generated_at"] >= report["generated_at"], (
        f"sweep_status.json generated_at ({status['generated_at']!r}) is "
        f"older than sweep_report.json generated_at ({report['generated_at']!r}) "
        "-- the committed status snapshot predates the run it's committed "
        "alongside; regenerate `sweep.py status` after the run completes."
    )

    status_by_process = {row["process"]: row["status"] for row in status["jobs"]}
    valid_job_statuses = {sweep.JOB_STATUS_RAN_OK, sweep.JOB_STATUS_SKIPPED_VALID}
    for job in report["jobs"]:
        if job["status"] not in valid_job_statuses:
            continue
        process = job["process"]
        assert process in status_by_process, (
            f"{process} succeeded ({job['status']}) in the tracked "
            "sweep_report.json but has no corresponding row in the tracked "
            "sweep_status.json at all"
        )
        assert status_by_process[process] == sweep.STATUS_DONE_VALID, (
            f"{process} recorded {job['status']!r} in the tracked "
            f"sweep_report.json, but the tracked sweep_status.json shows "
            f"{status_by_process[process]!r} for it -- this is exactly the "
            "stale-pre-run-snapshot bug this test guards against."
        )


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
        f"(out / 'input_manifest.json').write_text(json.dumps(dict(resolved_seeds=seeds, m_ticks=int(a.ticks), inputs=[{_FIXTURE_INPUT_RECORD!r}])))\n"
        "(out / 'provenance.json').write_text(json.dumps(dict(git_sha='fake')))\n"
        "(out / 'thresholds.json').write_text(json.dumps(dict(channels={})))\n"
        "(out / 'null_calibration.json').write_text(json.dumps(dict(channels={})))\n"
        "(out / 'SUMMARY.json').write_text(json.dumps(dict(note='fake')))\n"
        "(out / 'analytical_check.json').write_text(json.dumps(dict(applicable=False, reason='fake')))\n",
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


# --- sweep exit code: `run` must return nonzero on ANY hard child failure -------


def _fake_runner_script(tmp_path: Path, *, body: str) -> Path:
    fake_runner = tmp_path / "fake_runner_exit.py"
    fake_runner.write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--process', required=True)\n"
        "p.add_argument('--seeds', required=True)\n"
        "p.add_argument('--ticks', required=True)\n"
        "p.add_argument('--output-dir', required=True)\n"
        "a = p.parse_args()\n" + body,
        encoding="utf-8",
    )
    return fake_runner


def test_cli_run_returns_nonzero_when_child_exits_nonzero(tmp_path, monkeypatch):
    fake_runner = _fake_runner_script(tmp_path, body="import sys; sys.exit(3)\n")
    monkeypatch.setattr(sweep, "RUNNER_SCRIPT", fake_runner)
    exit_code = sweep.main(
        [
            "run",
            "--processes",
            "Metabolism",
            "--max-workers",
            "1",
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--log-dir",
            str(tmp_path / "logs"),
            "--report-out",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code != 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["tally"][sweep.JOB_STATUS_RAN_FAIL] == 1


def test_cli_run_returns_nonzero_when_exit_0_but_no_valid_evidence_produced(tmp_path, monkeypatch):
    """A child that exits 0 without producing complete, request-matching
    evidence (e.g. a runner bug, or a crash after partial writes) must still
    be treated as a hard sweep failure -- exit 0 alone is never sufficient."""
    fake_runner = _fake_runner_script(tmp_path, body="print('did nothing useful')\n")
    monkeypatch.setattr(sweep, "RUNNER_SCRIPT", fake_runner)
    exit_code = sweep.main(
        [
            "run",
            "--processes",
            "Metabolism",
            "--max-workers",
            "1",
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--log-dir",
            str(tmp_path / "logs"),
            "--report-out",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code != 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["tally"][sweep.JOB_STATUS_RAN_INVALID_EVIDENCE] == 1


def test_cmd_run_treats_skipped_valid_as_non_failure(tmp_path):
    """`_cmd_run`'s hard-failure set must never include JOB_STATUS_SKIPPED_VALID
    -- already-valid, resumed evidence is a legitimate "nothing to do", not
    a failure."""
    assert sweep.JOB_STATUS_SKIPPED_VALID not in (
        sweep.JOB_STATUS_START_ERROR,
        sweep.JOB_STATUS_RAN_FAIL,
        sweep.JOB_STATUS_RAN_INVALID_EVIDENCE,
    )
    job = _make_job(tmp_path, process="AlreadyValidCli")
    _write_valid_evidence(job)
    result = sweep.run_job(job, command_builder=_fake_failing_command)  # would fail if actually (re)run
    assert result.status == sweep.JOB_STATUS_SKIPPED_VALID


# --- resume/staleness: unknown git_sha / source-hash mismatch / schema drift ----


def _make_valid_job_with_provenance(tmp_path: Path, **overrides) -> sweep.SweepJob:
    job = _make_job(tmp_path, process="StaleCheck")
    _write_valid_evidence(job)
    payload = json.loads((job.output_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    payload.update(overrides)
    (job.output_dir / schema.SWEEP_PROVENANCE_FILE).write_text(json.dumps(payload), encoding="utf-8")
    return job


def test_evidence_is_valid_accepts_unknown_git_sha_when_hashes_match(tmp_path):
    """git SHA is informational only, not gating: an unknown git_sha alone
    must not invalidate evidence whose source hashes and evaluator schema
    version still match the CURRENT tree (scope-corrected -- content
    hashes are the gating authority, not Windows-linked-worktree git
    plumbing)."""
    job = _make_valid_job_with_provenance(tmp_path, git_sha="unknown")
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is True
    assert reason is None


def test_evidence_is_valid_accepts_missing_git_sha_when_hashes_match(tmp_path):
    job = _make_valid_job_with_provenance(tmp_path, git_sha=None)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is True
    assert reason is None


def test_evidence_is_valid_still_rejects_stale_hash_even_with_unknown_git_sha(tmp_path):
    """Unknown git_sha does not grant a free pass: a stale source hash must
    still invalidate evidence regardless of git_sha state."""
    job = _make_valid_job_with_provenance(tmp_path, git_sha="unknown", source_hashes={"runner": "deadbeef" * 8})
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "source hash" in reason


def test_evidence_is_valid_rejects_stale_source_hash(tmp_path):
    job = _make_valid_job_with_provenance(tmp_path, source_hashes={"runner": "deadbeef" * 8})
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "source hash" in reason


def test_evidence_is_valid_rejects_extra_source_hash_key(tmp_path):
    """F5 bidirectional staleness: a `source_hashes` key that is NOT part
    of the CURRENT expected dependency set (e.g. a hand-tampered sentinel,
    or evidence generated against a since-shrunk/renamed
    `schema.PROCESS_DEPENDENCY_FILES` registry entry) must invalidate the
    sentinel even when every currently-expected key is still present and
    correctly matching -- the per-key loop alone only ever checks "is
    every CURRENTLY-expected key present/matching", never "does the
    recorded key SET exactly equal the current expected key set", so an
    extra recorded key would otherwise be silently ignored forever."""
    job = _make_valid_job_with_provenance(tmp_path)
    payload = json.loads((job.output_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    payload["source_hashes"]["a_key_no_longer_in_the_registry"] = "deadbeef" * 8
    (job.output_dir / schema.SWEEP_PROVENANCE_FILE).write_text(json.dumps(payload), encoding="utf-8")
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "extra" in reason


def test_evidence_is_valid_accepts_stale_evaluator_schema_version_when_hashes_match(tmp_path):
    """v3 policy change: `evaluator_schema_version` is recorded
    informationally but no longer gates `evidence_is_valid` -- otherwise
    every already-completed sweep job would spuriously need a rerun any
    time `verdict.py`'s mechanical re-derivation logic is fixed, even
    though no process/oracle/threshold changed and the job's own recorded
    source/sidecar hashes still match the current tree."""
    job = _make_valid_job_with_provenance(tmp_path, evaluator_schema_version=-999)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is True
    assert reason is None


def test_evidence_is_valid_accepts_missing_result_schema_version_as_version_1(tmp_path):
    """Item 1: `RESULT_SCHEMA_VERSION` versions the raw runner evidence
    contract, distinct from `evaluator_schema_version`. A sentinel written
    before this field existed (no `result_schema_version` key at all) must
    be treated as version 1 -- exactly the current
    `schema.RESULT_SCHEMA_VERSION` -- so it does not spuriously invalidate."""
    job = _make_valid_job_with_provenance(tmp_path)
    payload = json.loads((job.output_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert schema.RESULT_SCHEMA_VERSION == 1
    del payload["result_schema_version"]
    (job.output_dir / schema.SWEEP_PROVENANCE_FILE).write_text(json.dumps(payload), encoding="utf-8")
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is True
    assert reason is None


def test_evidence_is_valid_rejects_result_schema_version_mismatch(tmp_path):
    """UNLIKE `evaluator_schema_version`, `result_schema_version` IS gating:
    a mismatch means the raw result.json/sidecar field contract itself may
    have changed since this evidence was generated, so a rerun is required."""
    job = _make_valid_job_with_provenance(tmp_path, result_schema_version=schema.RESULT_SCHEMA_VERSION + 1)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert "result_schema_version" in reason


def test_evidence_is_valid_accepts_evaluator_bump_when_result_schema_matches(tmp_path):
    """Combining both axes: an `evaluator_schema_version` mismatch alongside
    a MATCHING `result_schema_version` must still be accepted -- the two
    fields are orthogonal, and only `result_schema_version` is gating."""
    job = _make_valid_job_with_provenance(
        tmp_path, evaluator_schema_version=-999, result_schema_version=schema.RESULT_SCHEMA_VERSION
    )
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is True
    assert reason is None


def test_build_sweep_provenance_records_current_result_schema_version(tmp_path):
    job = _make_valid_job_with_provenance(tmp_path)
    payload = json.loads((job.output_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert payload["result_schema_version"] == schema.RESULT_SCHEMA_VERSION


def test_evidence_is_valid_rejects_missing_sweep_provenance_file(tmp_path):
    """Evidence written before the provenance hardening (no
    sweep_provenance.json at all) must be treated as stale, never DONE_VALID."""
    job = _make_job(tmp_path, process="PreHardening")
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
    write_mandatory_sidecars(job.output_dir)
    valid, reason = sweep.evidence_is_valid(job)
    assert valid is False
    assert schema.SWEEP_PROVENANCE_FILE in reason


# --- atomic force / crash recovery / concurrent lock ----------------------------


def test_force_rerun_atomically_replaces_prior_valid_evidence(tmp_path):
    job = _make_job(tmp_path, process="AtomicForce")
    _write_valid_evidence(job)
    old_provenance = json.loads((job.output_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    result = sweep.run_job(job, force=True, command_builder=_fake_ok_command)
    assert result.status == sweep.JOB_STATUS_RAN_OK
    new_provenance = json.loads((job.output_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    # A genuinely fresh, real run_job-written sentinel (not the manually
    # fixture-authored one `_write_valid_evidence` writes) proves the swap
    # actually replaced the directory rather than silently keeping the old one.
    assert new_provenance["written_at"] != old_provenance["written_at"]
    # No leftover temp/backup dirs after a clean swap.
    leftovers = list(job.output_dir.parent.glob(f".{job.output_dir.name}.*"))
    assert leftovers == []


def test_crashed_swap_backup_is_recovered_before_validity_check(tmp_path):
    """Simulate a crash between `_atomic_replace_dir`'s two renames: the
    final `output_dir` is missing but its `<name>.prev` backup (the
    last-known-good evidence) still exists on disk. `evidence_is_valid` (and
    therefore `run_job`) must recover it automatically rather than treating
    the process as never having valid evidence."""
    job = _make_job(tmp_path, process="CrashRecover")
    _write_valid_evidence(job)
    good_bytes = (job.output_dir / "result.json").read_bytes()

    backup_dir = job.output_dir.parent / f"{job.output_dir.name}.prev"
    job.output_dir.rename(backup_dir)
    assert not job.output_dir.exists()
    assert backup_dir.is_dir()

    valid, reason = sweep.evidence_is_valid(job)
    assert valid is True, reason
    assert job.output_dir.is_dir()
    assert not backup_dir.exists()
    assert (job.output_dir / "result.json").read_bytes() == good_bytes


def test_concurrent_lock_prevents_double_launch_and_preserves_evidence(tmp_path):
    """A second, concurrently-running `sweep.py run` invocation that already
    holds this process's O_EXCL lock must not be able to relaunch it -- and
    must leave existing evidence (valid or not) completely untouched."""
    job = _make_job(tmp_path, process="LockedConcurrent")
    _write_valid_evidence(job)  # so a real relaunch (if it happened) would be visible as a change
    before = (job.output_dir / "result.json").read_bytes()

    lock_path = sweep._lock_path_for(job)
    lock_fd = sweep._acquire_lock(lock_path)
    try:
        result = sweep.run_job(job, force=True, command_builder=_fake_ok_command)
    finally:
        sweep._release_lock(lock_fd, lock_path)

    assert result.status == sweep.JOB_STATUS_LOCKED_SKIPPED
    assert (job.output_dir / "result.json").read_bytes() == before


def test_concurrent_lock_released_after_run_allows_next_invocation(tmp_path):
    job = _make_job(tmp_path, process="LockReleased")
    lock_path = sweep._lock_path_for(job)
    sweep.run_job(job, command_builder=_fake_ok_command)
    assert not lock_path.exists()


def test_stale_lock_with_dead_pid_is_silently_reaped_and_job_runs_normally(tmp_path):
    """A lock file left behind by a PID that is genuinely dead (crashed
    sweep invocation, no clean unlock) must never permanently block every
    future rerun of that process. `_acquire_lock` reaps it and this
    attempt proceeds as an ordinary run -- NOT `JOB_STATUS_LOCKED_SKIPPED`."""
    import subprocess

    job = _make_job(tmp_path, process="StaleLockReap")
    lock_path = sweep._lock_path_for(job)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Spawn and wait for a real child process so its PID is guaranteed to be
    # a genuinely dead, real (recently-valid) PID rather than a guessed number.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = proc.pid
    proc.wait()
    assert not sweep._pid_is_alive(dead_pid)
    lock_path.write_text(str(dead_pid), encoding="utf-8")

    result = sweep.run_job(job, command_builder=_fake_ok_command)
    assert result.status == sweep.JOB_STATUS_RAN_OK
    assert not lock_path.exists()  # released again after this run's own hold


def test_cli_run_returns_nonzero_when_another_invocation_holds_a_live_lock(tmp_path, monkeypatch):
    """CLI-level: if a concurrently-running `sweep.py run` genuinely holds
    this process's lock (a live PID -- here, this very test process), `run`
    must report it as a hard failure (nonzero exit), never a silent
    no-op/success, and must never touch existing evidence."""
    fake_runner = _fake_runner_script(tmp_path, body="import sys; sys.exit(0)\n")
    monkeypatch.setattr(sweep, "RUNNER_SCRIPT", fake_runner)

    evidence_root = tmp_path / "evidence"
    job = sweep.SweepJob(
        process="Metabolism",
        seeds=3,
        m_ticks=5,
        output_dir=evidence_root / "Metabolism" / "latest",
        log_path=tmp_path / "logs" / "Metabolism.log",
    )
    lock_path = sweep._lock_path_for(job)
    lock_fd = sweep._acquire_lock(lock_path)  # this test process itself is alive -> genuinely live lock
    try:
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
    finally:
        sweep._release_lock(lock_fd, lock_path)

    assert exit_code != 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["tally"].get(sweep.JOB_STATUS_LOCKED_SKIPPED) == 1
    assert not (evidence_root / "Metabolism" / "latest" / "result.json").exists()


# --- dangling absolute temp-dir refs are sanitized to logical repo-relative paths


def test_sanitize_dangling_temp_refs_rewrites_absolute_paths_to_repo_relative(tmp_path):
    """Direct unit test of `_sanitize_dangling_temp_refs`: simulate the real
    production layout (a fake `repo_root` containing both the evidence tree
    and a `data/` oracle file) so `.resolve().relative_to(repo_root)`
    actually succeeds, proving the rewritten refs are genuine repo-relative
    logical paths -- never the (about-to-be-deleted) absolute temp rebuild
    directory, and never any other absolute filesystem path."""
    repo_root = tmp_path / "repo"
    final_output_dir = repo_root / "evidence" / "SomeProc" / "latest"
    tmp_output_dir = repo_root / "evidence" / "SomeProc" / ".latest.rebuild-123-456"
    tmp_output_dir.mkdir(parents=True)
    oracle_file = repo_root / "data" / "oracle.mat"
    oracle_file.parent.mkdir(parents=True)
    oracle_file.write_bytes(b"oracle-bytes")

    (tmp_output_dir / "allocator_inputs.json").write_text("{}", encoding="utf-8")
    (tmp_output_dir / "result.json").write_text(
        json.dumps(
            {
                "allocator_inputs_ref": str(tmp_output_dir / "allocator_inputs.json"),
                "provenance_ref": str(tmp_output_dir / "provenance.json"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_output_dir / "provenance.json").write_text(
        json.dumps({"git_sha": "fake", "oracle_path": str(oracle_file)}), encoding="utf-8"
    )

    sweep._sanitize_dangling_temp_refs(tmp_output_dir, final_output_dir=final_output_dir, repo_root=repo_root)

    result_payload = json.loads((tmp_output_dir / "result.json").read_text(encoding="utf-8"))
    provenance_payload = json.loads((tmp_output_dir / "provenance.json").read_text(encoding="utf-8"))

    for value in (
        result_payload["allocator_inputs_ref"],
        result_payload["provenance_ref"],
        provenance_payload["oracle_path"],
    ):
        assert not Path(value).is_absolute(), value
        assert "rebuild-" not in value, value

    assert result_payload["allocator_inputs_ref"] == "evidence/SomeProc/latest/allocator_inputs.json"
    assert result_payload["provenance_ref"] == "evidence/SomeProc/latest/provenance.json"
    assert provenance_payload["oracle_path"] == "data/oracle.mat"


# --- F2: _normalize_input_manifest_file ALWAYS writes the canonical form -------


def test_normalize_input_manifest_file_rewrites_absolute_paths_to_relative(tmp_path):
    """Baseline (pre-existing) case: an absolute path is rewritten to a
    repo-relative POSIX path."""
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "evidence" / "SomeProc" / "latest"
    output_dir.mkdir(parents=True)
    oracle_file = repo_root / "data" / "oracle.mat"
    oracle_file.parent.mkdir(parents=True)
    oracle_file.write_bytes(b"oracle-bytes")
    manifest_path = output_dir / "input_manifest.json"
    manifest_path.write_text(
        json.dumps({"inputs": [{"path": str(oracle_file), "sha256": "abc123"}], "m_ticks": 100}),
        encoding="utf-8",
    )

    sweep._normalize_input_manifest_file(output_dir, repo_root=repo_root)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["inputs"][0]["path"] == "data/oracle.mat"


def test_normalize_input_manifest_file_always_rewrites_canonical_bytes_even_when_already_relative(tmp_path):
    """F2 (Opus5 final review): the function must ALWAYS write the
    canonical serialized form (`json.dumps(..., indent=2, sort_keys=True) +
    "\\n"`, matching `generator.bundle_process_evidence`'s own
    serialization exactly), even when every `path` value is ALREADY
    relative and therefore no `path` string itself changes -- there used
    to be a `changed` guard that skipped the rewrite entirely in that case,
    which meant a manifest already holding repo-relative paths but written
    by the runner with different whitespace/key-ordering than the
    canonical form would silently keep those different bytes, breaking the
    live-tree/bundle byte-identity guarantee this function exists for.
    Writes the manifest with compact (no indent, unsorted-key) formatting
    up front so a no-op result would be trivially detectable as a bug."""
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "evidence" / "SomeProc" / "latest"
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "input_manifest.json"
    already_relative_payload = {
        "m_ticks": 100,
        "inputs": [{"path": "tests/vivarium/l2_2_design_a_runner.py", "sha256": "abc123"}],
    }
    # Deliberately NOT the canonical serialization: no indent, insertion-order
    # (not sorted) keys, no trailing newline.
    non_canonical_bytes = json.dumps(already_relative_payload)
    manifest_path.write_bytes(non_canonical_bytes.encode("utf-8"))
    assert manifest_path.read_bytes() != (
        json.dumps(already_relative_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8"), "fixture setup bug: pre-write bytes must NOT already equal the canonical form"

    sweep._normalize_input_manifest_file(output_dir, repo_root=repo_root)

    expected_canonical_bytes = (json.dumps(already_relative_payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert manifest_path.read_bytes() == expected_canonical_bytes, (
        "already-relative input_manifest.json must still be rewritten to the canonical serialized form"
    )
    # Content (not just bytes) must also be preserved exactly -- no data loss.
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == already_relative_payload


def test_normalize_input_manifest_file_is_idempotent_on_a_second_call(tmp_path):
    """Calling the normalizer twice in a row (as would happen if `run_job`
    were ever invoked again against the same temp dir) must produce
    byte-identical output the second time -- proving the canonical form is
    a true fixed point, not merely "different from the input" once."""
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "evidence" / "SomeProc" / "latest"
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "input_manifest.json"
    manifest_path.write_text(
        json.dumps({"inputs": [{"path": "tests/vivarium/l2_2_design_a_runner.py", "sha256": "abc123"}]}),
        encoding="utf-8",
    )

    sweep._normalize_input_manifest_file(output_dir, repo_root=repo_root)
    first_pass_bytes = manifest_path.read_bytes()
    sweep._normalize_input_manifest_file(output_dir, repo_root=repo_root)
    second_pass_bytes = manifest_path.read_bytes()

    assert first_pass_bytes == second_pass_bytes
