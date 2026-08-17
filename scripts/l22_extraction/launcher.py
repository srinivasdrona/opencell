"""Planning/manifest core for the L2.2 full multi-seed extraction launcher.

This module is intentionally MATLAB-free and side-effect-light (its own
tests run with no MATLAB and no real trace files, using synthetic fixtures)
so the *planning* logic -- which files are missing/invalid, how work is
sharded across bounded parallel workers, what the tracked manifest looks
like -- can be validated cheaply and independently of any long MATLAB run.

Actual MATLAB process spawning/bounding lives in the companion PowerShell
driver `scripts/matlab/run_l22_seed_shards.ps1`, which calls this module in
`plan` mode to get an executable job list, and in `manifest` mode afterwards
to assemble the tracked evidence artifact. Splitting it this way lets the
bounded-parallelism / resume / no-`_s000` policy be unit-tested directly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
# Self-contained sys.path bootstrap: makes `scripts.l22_extraction.*` absolute
# imports work identically whether this module is run directly as a script
# (`python scripts/l22_extraction/launcher.py ...`, no package context) or
# imported by pytest from `tests/scripts/` (which does not otherwise put the
# repo root on sys.path). Mirrors the pattern in scripts/verify_multiseed_pilot.py.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.trace_validation import sha256_file, validate_structural  # noqa: E402

KARR_NATIVE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native"
EXTRACTOR_SCRIPT = REPO_ROOT / "scripts" / "matlab" / "extract_per_process_traces_v2.m"
DEFAULT_N_TICKS = 100
DEFAULT_MATLAB_EXE = Path(r"E:\MATLAB\bin\matlab.exe")


class SeedZeroForbiddenError(ValueError):
    """Raised when seed 0 is requested through this launcher.

    Seed 0 is the canonical unsuffixed `per_process_traces_v2/` trace and is
    authoritative per the task's hard policy: this launcher must never
    generate or retain a competing `per_process_traces_v2_s000/` directory.
    """


def seed_output_dir(seed: int, *, karr_native_root: Path = KARR_NATIVE_ROOT) -> Path:
    if int(seed) == 0:
        raise SeedZeroForbiddenError("seed 0 is canonical/unsuffixed; this launcher only handles seeds >= 1")
    return karr_native_root / f"per_process_traces_v2_s{int(seed):03d}"


def seed_mat_path(
    process: str, seed: int, *, n_ticks: int = DEFAULT_N_TICKS, karr_native_root: Path = KARR_NATIVE_ROOT
) -> Path:
    return seed_output_dir(seed, karr_native_root=karr_native_root) / f"{process}_{n_ticks}ticks.mat"


def canonical_seed0_path(
    process: str, *, n_ticks: int = DEFAULT_N_TICKS, karr_native_root: Path = KARR_NATIVE_ROOT
) -> Path:
    return karr_native_root / "per_process_traces_v2" / f"{process}_{n_ticks}ticks.mat"


@dataclass
class FileDecision:
    process: str
    seed: int
    path: str
    action: str  # "skip_valid" | "generate_missing" | "regenerate_invalid"
    reason: str | None = None


@dataclass
class SeedJob:
    seed: int
    processes: tuple[str, ...]
    output_dir: str
    matlab_command: str
    log_path: str


@dataclass
class WorkerShard:
    worker_id: int
    jobs: list[SeedJob] = field(default_factory=list)


@dataclass
class ExtractionPlan:
    processes: tuple[str, ...]
    seeds: tuple[int, ...]
    n_ticks: int
    n_workers: int
    decisions: list[FileDecision]
    workers: list[WorkerShard]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "processes": list(self.processes),
            "seeds": list(self.seeds),
            "n_ticks": self.n_ticks,
            "n_workers": self.n_workers,
            "decisions": [asdict(d) for d in self.decisions],
            "workers": [
                {
                    "worker_id": w.worker_id,
                    "jobs": [asdict(j) for j in w.jobs],
                }
                for w in self.workers
            ],
            "generated_at": self.generated_at,
        }


def _validate_existing(path: Path, process: str, seed: int, n_ticks: int):
    return validate_structural(
        path,
        expected_process=process,
        expected_seed=seed,
        expected_n_ticks=n_ticks,
        compute_hash=False,
    )


def seed_log_relpath(seed: int, *, log_dir: str = "artifacts/l22_full_extraction/logs") -> str:
    return f"{log_dir}/seed{int(seed):03d}.log"


def build_matlab_command(
    processes: tuple[str, ...],
    seed: int,
    *,
    n_ticks: int = DEFAULT_N_TICKS,
    log_relpath: str | None = None,
    include_addpath: bool = True,
) -> str:
    """Build one seed's MATLAB statement(s), optionally `diary`-wrapped.

    `diary`-wrapping gives a genuine per-job (per-seed) log file even though
    several seed jobs may be concatenated into a single long-lived MATLAB
    `-batch` process per worker (amortizing MATLAB startup cost across a
    worker's seed shard). Any seed failure is rethrown so the worker exits
    nonzero rather than producing success-shaped output. The planner is
    resumable: a subsequent run skips completed valid seeds and retries the
    unfinished remainder of that shard.
    """
    output_subdir = f"per_process_traces_v2_s{int(seed):03d}"
    proc_list = ", ".join(f"'{p}'" for p in processes)
    call = (
        f"extract_per_process_traces_v2({{{proc_list}}}, '{output_subdir}', {int(n_ticks)}, "
        f"uint32({int(seed)}));"
    )
    prefix = (
        "addpath('scripts/matlab'); "
        "addpath(fullfile(matlabroot, 'toolbox', 'stats', 'stats'), '-begin'); "
        if include_addpath
        else ""
    )
    if log_relpath is None:
        return f"{prefix}{call}"
    return (
        f"{prefix}"
        f"diary('{log_relpath}'); "
        f"try; {call} catch err; disp(getReport(err, 'extended', 'hyperlinks', 'off')); rethrow(err); end; "
        f"diary off;"
    )


def plan_extraction(
    processes: list[str] | tuple[str, ...],
    seeds: list[int] | tuple[int, ...],
    *,
    n_ticks: int = DEFAULT_N_TICKS,
    n_workers: int = 2,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    validate_existing: bool = True,
) -> ExtractionPlan:
    """Build a resumable, disjoint-output, bounded-worker extraction plan.

    - Rejects seed 0 outright (see `SeedZeroForbiddenError`).
    - For every (process, seed) pair, decides skip_valid / generate_missing /
      regenerate_invalid via a real structural validation pass (not an
      existence-only check) when `validate_existing` is True.
    - Shards seeds (not processes) across workers so every worker's output
      directories (`per_process_traces_v2_s{seed:03d}/`) are disjoint from
      every other worker's -- no two workers ever write the same file.
    """
    processes = tuple(processes)
    seeds = tuple(sorted(set(int(s) for s in seeds)))
    if any(s == 0 for s in seeds):
        raise SeedZeroForbiddenError(f"seed 0 requested in {seeds}; canonical seed 0 must not be regenerated")
    if n_workers < 1:
        raise ValueError(f"n_workers must be >= 1, got {n_workers}")

    decisions: list[FileDecision] = []
    seed_needs: dict[int, list[str]] = {}

    for seed in seeds:
        needed: list[str] = []
        for process in processes:
            path = seed_mat_path(process, seed, n_ticks=n_ticks, karr_native_root=karr_native_root)
            if not path.exists():
                decisions.append(
                    FileDecision(process=process, seed=seed, path=str(path), action="generate_missing")
                )
                needed.append(process)
                continue
            if not validate_existing:
                decisions.append(FileDecision(process=process, seed=seed, path=str(path), action="skip_valid"))
                continue
            result = _validate_existing(path, process, seed, n_ticks)
            if result.ok:
                decisions.append(FileDecision(process=process, seed=seed, path=str(path), action="skip_valid"))
            else:
                decisions.append(
                    FileDecision(
                        process=process,
                        seed=seed,
                        path=str(path),
                        action="regenerate_invalid",
                        reason="; ".join(result.errors),
                    )
                )
                needed.append(process)
        if needed:
            seed_needs[seed] = needed

    pending_seeds = sorted(seed_needs.keys())
    workers = [WorkerShard(worker_id=i) for i in range(n_workers)]
    for i, seed in enumerate(pending_seeds):
        worker = workers[i % n_workers]
        output_dir = str(seed_output_dir(seed, karr_native_root=karr_native_root))
        log_relpath = seed_log_relpath(seed)
        command = build_matlab_command(tuple(seed_needs[seed]), seed, n_ticks=n_ticks, log_relpath=log_relpath)
        worker.jobs.append(
            SeedJob(
                seed=seed,
                processes=tuple(seed_needs[seed]),
                output_dir=output_dir,
                matlab_command=command,
                log_path=log_relpath,
            )
        )

    return ExtractionPlan(
        processes=processes,
        seeds=seeds,
        n_ticks=n_ticks,
        n_workers=n_workers,
        decisions=decisions,
        workers=workers,
        generated_at=datetime.now(UTC).isoformat(),
    )


def apply_invalidations(plan: ExtractionPlan) -> list[str]:
    """Delete files the plan marked `regenerate_invalid` so MATLAB's own
    (existence-only) skip check in `extract_per_process_traces_v2.m` will
    actually regenerate them instead of silently reusing bad data.
    """
    deleted: list[str] = []
    for decision in plan.decisions:
        if decision.action == "regenerate_invalid":
            path = Path(decision.path)
            if path.exists():
                path.unlink()
                deleted.append(str(path))
    return deleted


def git_blob_sha256(path: Path) -> str:
    return sha256_file(path)


def matlab_version_probe(matlab_exe: Path = DEFAULT_MATLAB_EXE) -> str:
    try:
        proc = subprocess.run(  # noqa: S603
            [str(matlab_exe), "-batch", "disp(version)"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return proc.stdout.strip() or proc.stderr.strip()
    except Exception as exc:  # noqa: BLE001
        return f"<matlab_version_probe failed: {exc}>"


def _cmd_plan(args: argparse.Namespace) -> int:
    seeds = _parse_seed_spec(args.seeds)
    processes = args.processes.split(",") if args.processes else []
    plan = plan_extraction(
        processes,
        seeds,
        n_ticks=args.n_ticks,
        n_workers=args.workers,
        validate_existing=not args.no_validate,
    )
    deleted: list[str] = []
    if args.apply_invalidation:
        deleted = apply_invalidations(plan)
    out = plan.to_dict()
    out["deleted_invalid_files"] = deleted
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[launcher] wrote plan with {sum(len(w.jobs) for w in plan.workers)} jobs to {args.out}")
    return 0


def _parse_seed_spec(spec: str) -> list[int]:
    """Parse "1-49" or "1,2,5-10" into an explicit int list (never implicit)."""
    seeds: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            seeds.update(range(int(lo), int(hi) + 1))
        else:
            seeds.add(int(chunk))
    return sorted(seeds)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan_parser = sub.add_parser("plan", help="Build a resumable extraction plan JSON.")
    plan_parser.add_argument("--processes", required=True, help="Comma-separated process names.")
    plan_parser.add_argument("--seeds", required=True, help='Explicit seed spec, e.g. "1-49" or "1,2,5-10".')
    plan_parser.add_argument("--n-ticks", type=int, default=DEFAULT_N_TICKS)
    plan_parser.add_argument("--workers", type=int, default=2)
    plan_parser.add_argument("--no-validate", action="store_true", help="Existence-only skip (debug only).")
    plan_parser.add_argument(
        "--apply-invalidation", action="store_true", help="Delete files marked regenerate_invalid."
    )
    plan_parser.add_argument("--out", required=True)
    plan_parser.set_defaults(func=_cmd_plan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
