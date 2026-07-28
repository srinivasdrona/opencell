"""Resumable, bounded-parallel sweep launcher for the L2.2 Design-A runner.

Drives the existing, UNMODIFIED ``tests/vivarium/l2_2_design_a_runner.py``
across the 18 ``design_a_per_tick`` in-scope processes at their real catalog
``N_seeds``/``M_ticks`` values, writing each process's runner-native
evidence to ``artifacts/l2_2_gates/<Process>/latest/`` -- the exact
directory the evidence generator (``scripts/l22_evidence/generator.py``)
already reads (see ``schema.py``). This module only decides *when* and
*with what arguments* to invoke the existing runner subprocess and records
what happened; it never touches biology, metrics, thresholds, catalog
values, or verdict evaluators, and it never overrides the runner's own
output.

Resume semantics: a job is considered "already satisfied" only if its
output directory contains all three mandatory authority files
(``result.json``, ``input_manifest.json``, ``provenance.json``), they
parse as valid JSON, AND their recorded process/seed/tick fields match the
request -- never existence-only. ``--force`` overrides this and reruns
unconditionally. This mirrors ``scripts/l22_extraction/launcher.py``'s
"skip_valid / generate_missing / regenerate_invalid" resume policy for the
raw-oracle extraction sweep.

CLI:
    bin\\oc-py scripts/l22_evidence/sweep.py plan  [--processes P1,P2,...] [--out PATH]
    bin\\oc-py scripts/l22_evidence/sweep.py run   [--processes P1,P2,...] [--max-workers N]
                                                    [--force] [--report-out PATH]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

REPO_ROOT = cat.REPO_ROOT
RUNNER_SCRIPT = REPO_ROOT / "tests" / "vivarium" / "l2_2_design_a_runner.py"
DEFAULT_LOG_DIR = REPO_ROOT / "artifacts" / "l2_2_gates" / "_sweep_logs"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "sweep_report.json"
DEFAULT_STATUS_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "sweep_status.json"

# Status vocabulary for JobResult.status -- distinct from the evidence
# index's own mechanical_verdict vocabulary (schema.py), since this module
# reports *execution* outcome, not re-derived scientific verdict.
JOB_STATUS_SKIPPED_VALID = "SKIPPED_VALID"
JOB_STATUS_RAN_OK = "RAN_EXIT_0"
JOB_STATUS_RAN_FAIL = "RAN_NONZERO_EXIT"
JOB_STATUS_START_ERROR = "FAILED_TO_START"


@dataclass(frozen=True)
class SweepJob:
    process: str
    seeds: int  # count; runner resolves this to explicit seeds range(seeds)
    m_ticks: int
    output_dir: Path
    log_path: Path


@dataclass
class JobResult:
    process: str
    status: str
    exit_code: int | None
    started_at: str | None
    finished_at: str | None
    duration_s: float | None
    log_path: str
    output_dir: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "log_path": self.log_path,
            "output_dir": self.output_dir,
            "reason": self.reason,
        }


def plan_sweep(
    processes: list[str] | None = None,
    *,
    catalog_path: Path = schema.CATALOG_PATH,
    evidence_root: Path = schema.EVIDENCE_ROOT,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> list[SweepJob]:
    """Build the ordered job list: one job per requested (default: every
    in-scope) ``design_a_per_tick`` process, at its real catalog N_seeds/
    M_ticks. Never guesses M_ticks -- a design_a_per_tick process with no
    catalog M_ticks raises explicitly rather than silently defaulting."""
    entries = cat.in_scope_processes(catalog_path)
    design_a = {name: entry for name, entry in entries.items() if entry.harness_type == "design_a_per_tick"}

    if processes is None:
        wanted = sorted(design_a)
    else:
        unknown = [p for p in processes if p not in design_a]
        if unknown:
            raise ValueError(
                f"process(es) not in-scope design_a_per_tick: {unknown}; available: {sorted(design_a)}"
            )
        wanted = list(processes)

    jobs: list[SweepJob] = []
    for name in wanted:
        entry = design_a[name]
        if entry.m_ticks is None:
            raise ValueError(f"catalog process {name!r} has no M_ticks; refusing to guess a sweep tick count")
        jobs.append(
            SweepJob(
                process=name,
                seeds=int(entry.n_seeds),
                m_ticks=int(entry.m_ticks),
                output_dir=evidence_root / name / schema.DESIGN_A_SUBDIR,
                log_path=log_dir / f"{name}.log",
            )
        )
    return jobs


def _load_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def evidence_is_valid(job: SweepJob) -> tuple[bool, str | None]:
    """True only if `job.output_dir` already holds complete, parseable,
    request-matching runner evidence -- never existence-only. Returns
    (False, <reason>) for every way it can be invalid, so `--force`-less
    reruns have an honest, inspectable reason for why a job was (not)
    skipped."""
    missing = [f for f in schema.REQUIRED_AUTHORITY_FILES if not (job.output_dir / f).is_file()]
    if missing:
        return False, f"missing required authority file(s): {missing}"

    result = _load_json_safe(job.output_dir / "result.json")
    manifest = _load_json_safe(job.output_dir / "input_manifest.json")
    provenance = _load_json_safe(job.output_dir / "provenance.json")
    if result is None or manifest is None or provenance is None:
        return False, "one or more authority files failed to parse as JSON"

    expected_seeds = list(range(job.seeds))
    if result.get("process") != job.process:
        return False, f"result.json process={result.get('process')!r} != expected {job.process!r}"
    if sorted(result.get("seeds", [])) != expected_seeds:
        return False, f"result.json seeds do not match expected {job.seeds}-seed request"
    if int(result.get("ticks", -1)) != job.m_ticks:
        return False, f"result.json ticks={result.get('ticks')!r} != expected {job.m_ticks}"
    if sorted(manifest.get("resolved_seeds", [])) != expected_seeds:
        return False, "input_manifest.json resolved_seeds do not match expected seed request"
    if int(manifest.get("m_ticks", -1)) != job.m_ticks:
        return False, f"input_manifest.json m_ticks={manifest.get('m_ticks')!r} != expected {job.m_ticks}"

    return True, None


def runner_command(job: SweepJob, *, python_exe: str | None = None) -> list[str]:
    """The exact, unmodified runner CLI invocation for `job`. Seeds are
    passed as a plain count ("50"), which the runner's own `_parse_seed_spec`
    resolves to the explicit `range(50)` -- i.e. seeds 0..49, the real
    Karr-oracle seed count already populated on disk."""
    return [
        python_exe or sys.executable,
        str(RUNNER_SCRIPT),
        "--process",
        job.process,
        "--seeds",
        str(job.seeds),
        "--ticks",
        str(job.m_ticks),
        "--output-dir",
        str(job.output_dir),
    ]


def run_job(
    job: SweepJob,
    *,
    force: bool = False,
    command_builder: Callable[[SweepJob], list[str]] = runner_command,
    cwd: Path = REPO_ROOT,
) -> JobResult:
    """Run a single job, honoring resume-by-validation unless `force`.
    Never overwrites already-valid evidence unless explicitly forced. The
    child's exact exit code is captured directly via `subprocess.run` (no
    shell wrapper involved), so wrapper exit-code-masking bugs elsewhere in
    this project's tooling cannot affect this launcher."""
    if not force:
        valid, reason = evidence_is_valid(job)
        if valid:
            return JobResult(
                process=job.process,
                status=JOB_STATUS_SKIPPED_VALID,
                exit_code=None,
                started_at=None,
                finished_at=None,
                duration_s=None,
                log_path=cat.relative_to_repo(job.log_path),
                output_dir=cat.relative_to_repo(job.output_dir),
                reason="existing evidence already valid; use --force to rerun",
            )

    job.output_dir.mkdir(parents=True, exist_ok=True)
    job.log_path.parent.mkdir(parents=True, exist_ok=True)
    command = command_builder(job)
    started_at = datetime.now(UTC).isoformat()
    start_perf = time.perf_counter()
    try:
        with job.log_path.open("w", encoding="utf-8") as log_handle:
            log_handle.write(f"# command: {command}\n# started_at: {started_at}\n")
            log_handle.flush()
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
        exit_code = completed.returncode
    except OSError as exc:
        finished_at = datetime.now(UTC).isoformat()
        return JobResult(
            process=job.process,
            status=JOB_STATUS_START_ERROR,
            exit_code=None,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=time.perf_counter() - start_perf,
            log_path=cat.relative_to_repo(job.log_path),
            output_dir=cat.relative_to_repo(job.output_dir),
            reason=f"failed to start subprocess: {exc}",
        )

    finished_at = datetime.now(UTC).isoformat()
    duration_s = time.perf_counter() - start_perf
    status = JOB_STATUS_RAN_OK if exit_code == 0 else JOB_STATUS_RAN_FAIL
    reason = None
    if exit_code != 0:
        tail = _tail_lines(job.log_path, n=20)
        reason = f"nonzero exit {exit_code}; log tail: {tail}"
    return JobResult(
        process=job.process,
        status=status,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        log_path=cat.relative_to_repo(job.log_path),
        output_dir=cat.relative_to_repo(job.output_dir),
        reason=reason,
    )


def _tail_lines(path: Path, *, n: int = 20) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "<log unreadable>"
    return "\n".join(lines[-n:])


# Interim-status vocabulary -- distinct from JobResult.status. `run_sweep()`
# only returns (and `write_sweep_report()` only writes) once EVERY requested
# job has finished, which is unusable for honest progress reporting on a
# long sweep still partway through (e.g. while a multi-hour Metabolism job
# is still running). `status_snapshot()` is a read-only, non-invasive
# inspector: it never starts, stops, or waits on any process -- it only
# looks at what is already on disk right now -- so it is always safe to run
# concurrently with an in-flight `sweep.py run` invocation.
STATUS_DONE_VALID = "DONE_VALID_EVIDENCE"
STATUS_DONE_INVALID_OR_FAILED = "DONE_NO_VALID_EVIDENCE"
STATUS_IN_PROGRESS = "IN_PROGRESS_OR_UNKNOWN"
STATUS_NOT_STARTED = "NOT_STARTED"


def status_snapshot(jobs: list[SweepJob]) -> list[dict[str, Any]]:
    """Read-only interim status for `jobs`, safe to call while a real sweep
    `run` is still executing elsewhere. Never inspects process state (no PID
    lookups) -- only what is already durably on disk: whether valid evidence
    exists, whether a log file exists (implying a run was at least attempted
    and may still be in progress), and the stored (non-authoritative) runner
    verdict/warnings for human-readable context."""
    rows: list[dict[str, Any]] = []
    for job in jobs:
        valid, reason = evidence_is_valid(job)
        log_exists = job.log_path.is_file()
        row: dict[str, Any] = {
            "process": job.process,
            "seeds": job.seeds,
            "m_ticks": job.m_ticks,
            "output_dir": cat.relative_to_repo(job.output_dir),
            "log_path": cat.relative_to_repo(job.log_path) if log_exists else None,
        }
        if valid:
            row["status"] = STATUS_DONE_VALID
            row["reason"] = None
            result = _load_json_safe(job.output_dir / "result.json")
            if result is not None:
                row["stored_verdict"] = result.get("verdict")
                row["stored_bucket"] = result.get("bucket")
                row["stored_warnings"] = result.get("warnings", [])
        elif log_exists:
            log_text = job.log_path.read_text(encoding="utf-8", errors="replace")
            log_looks_finished = any(
                marker in log_text for marker in ("Traceback", "Error", "error", "ticks, but oracle only provides")
            )
            row["status"] = STATUS_DONE_INVALID_OR_FAILED if log_looks_finished else STATUS_IN_PROGRESS
            row["reason"] = reason
            row["log_tail"] = _tail_lines(job.log_path, n=5)
        else:
            row["status"] = STATUS_NOT_STARTED
            row["reason"] = reason
        rows.append(row)
    return rows


def write_status_snapshot(rows: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    """Compact tracked JSON: one interim status row per job, plus a tally.
    Excludes raw per-tick arrays/channel numbers -- same compactness
    discipline as `write_sweep_report()`."""
    tally: dict[str, int] = {}
    for r in rows:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_jobs": len(rows),
        "tally": tally,
        "jobs": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def run_sweep(
    jobs: list[SweepJob],
    *,
    max_workers: int = 2,
    force: bool = False,
    command_builder: Callable[[SweepJob], list[str]] = runner_command,
    cwd: Path = REPO_ROOT,
) -> list[JobResult]:
    """Bounded-parallel execution of `jobs`. Every job's output_dir/log_path
    is disjoint by construction (`plan_sweep` derives them 1:1 from process
    name), so no two concurrent workers ever write the same file. Returns
    results in the SAME order as `jobs` (not completion order), so a
    resumed/partial sweep's report is stable regardless of scheduling."""
    if max_workers < 1:
        raise ValueError(f"max_workers must be >= 1, got {max_workers}")

    results: list[JobResult | None] = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_index = {
            pool.submit(run_job, job, force=force, command_builder=command_builder, cwd=cwd): i
            for i, job in enumerate(jobs)
        }
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            results[i] = future.result()
    return [r for r in results if r is not None]


def write_sweep_report(results: list[JobResult], path: Path = DEFAULT_REPORT_PATH) -> dict[str, Any]:
    """Compact, tracked JSON summary of one sweep invocation: process,
    execution status, exit code, timing, disjoint output/log paths, and a
    failure reason where relevant. Deliberately excludes raw per-tick
    arrays or channel numbers -- that detail lives in the runner's own
    result.json (evidence_root), which this report only points at."""
    tally: dict[str, int] = {}
    for r in results:
        tally[r.status] = tally.get(r.status, 0) + 1
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_jobs": len(results),
        "tally": tally,
        "jobs": [r.to_dict() for r in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _parse_processes_arg(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def _cmd_plan(args: argparse.Namespace) -> int:
    jobs = plan_sweep(
        _parse_processes_arg(args.processes),
        evidence_root=Path(args.evidence_root),
        log_dir=Path(args.log_dir),
    )
    for job in jobs:
        valid, reason = evidence_is_valid(job)
        status = "SKIP(valid)" if valid else f"WOULD-RUN({reason})"
        print(f"{job.process:28s} seeds={job.seeds:<3d} ticks={job.m_ticks:<4d} {status}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    jobs = plan_sweep(
        _parse_processes_arg(args.processes),
        evidence_root=Path(args.evidence_root),
        log_dir=Path(args.log_dir),
    )
    rows = status_snapshot(jobs)
    report = write_status_snapshot(rows, Path(args.status_out))
    print(f"wrote {args.status_out} ({report['n_jobs']} jobs)")
    for status, count in sorted(report["tally"].items()):
        print(f"  {status}: {count}")
    for row in rows:
        extra = f" verdict={row.get('stored_verdict')}" if row["status"] == STATUS_DONE_VALID else ""
        print(f"    {row['process']:28s} {row['status']}{extra}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    jobs = plan_sweep(
        _parse_processes_arg(args.processes),
        evidence_root=Path(args.evidence_root),
        log_dir=Path(args.log_dir),
    )
    results = run_sweep(jobs, max_workers=args.max_workers, force=args.force)
    report = write_sweep_report(results, Path(args.report_out))
    print(f"wrote {args.report_out} ({report['n_jobs']} jobs)")
    for status, count in sorted(report["tally"].items()):
        print(f"  {status}: {count}")
    any_hard_failure = any(r.status == JOB_STATUS_START_ERROR for r in results)
    return 1 if any_hard_failure else 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Print the resume-aware plan without running anything.")
    plan.add_argument("--processes", help="Comma-separated subset; default is all 18 design_a_per_tick.")
    plan.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    plan.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    plan.set_defaults(func=_cmd_plan)

    run = sub.add_parser("run", help="Run the sweep (bounded-parallel, resumable).")
    run.add_argument("--processes", help="Comma-separated subset; default is all 18 design_a_per_tick.")
    run.add_argument("--max-workers", type=int, default=2)
    run.add_argument("--force", action="store_true", help="Rerun even if existing evidence is already valid.")
    run.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    run.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    run.add_argument("--report-out", default=str(DEFAULT_REPORT_PATH))
    run.set_defaults(func=_cmd_run)

    status = sub.add_parser(
        "status",
        help="Read-only interim progress snapshot; safe to run while `run` is executing elsewhere.",
    )
    status.add_argument("--processes", help="Comma-separated subset; default is all 18 design_a_per_tick.")
    status.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    status.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    status.add_argument("--status-out", default=str(DEFAULT_STATUS_PATH))
    status.set_defaults(func=_cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
