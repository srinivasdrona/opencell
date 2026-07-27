"""Narrowly-scoped canonical seed-0 regeneration for the five processes
ratified stale by the operator/Opus decision `regenerate-stale-l22-seed-zero`
(`D:\\OneDrive - Microsoft\\.pm-os\\DECISIONS.md`, 2026-07-28).

`launcher.py` hard-forbids seed 0 (`SeedZeroForbiddenError`) because the
canonical unsuffixed `per_process_traces_v2/` trace is normally authoritative
and must never be silently regenerated. This module is a deliberate,
minimal, explicit exception to that policy for exactly the five processes
named in the ratified decision -- it does NOT relax the general policy for
any other process or caller: `STALE5_PROCESSES` is a closed allowlist and
every entry point here raises `UnauthorizedSeed0RegenError` for anything
outside it.

Rationale for the exception (see `docs/phase_f/l2_2_design_a/
L22_STALE5_REGEN_REPORT.md` for full evidence): the canonical seed-0 `.mat`
files for these five processes were generated 2026-05-29/05-30, before the
extractor's `pick_snapshot_properties()` allowlist gained the `RNAs`
(2026-06-02, commit 2073647c) and `intergenicRNAs`/`signalSequenceMonomers`/
`unfoldedComplexs`/`foldedComplexs` (2026-06-06, commit 5c316642) entries --
all five of which are genuine MATLAB-declared properties on the
corresponding process classes (not extractor bugs). Regenerating seed 0
together with seeds 1-49 under the *current* unmodified extractor closes
that schema gap without ever mixing an old-schema seed 0 with new-schema
seeds 1-49 (which `_seed_schema_preflight` would reject anyway).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.launcher import (  # noqa: E402
    DEFAULT_N_TICKS,
    KARR_NATIVE_ROOT,
    canonical_seed0_path,
)
from scripts.l22_extraction.trace_validation import validate_structural  # noqa: E402

# Closed allowlist matching exactly the five processes named in the ratified
# decision. Never extend this set implicitly; a new stale-seed-zero finding
# requires its own ratified decision entry.
STALE5_PROCESSES: tuple[str, ...] = (
    "ProteinDecay",
    "ProteinFolding",
    "ProteinProcessingII",
    "RNADecay",
    "RNAProcessing",
)

# The extra states_before/states_after channel(s) each process's fresh seed
# schema must contain relative to the stale canonical seed 0 -- used to tell
# "already regenerated under the current extractor" (skip, resumable) apart
# from "still the old stale file" (must regenerate) without relying on
# existence alone.
REQUIRED_EXTRA_CHANNELS: dict[str, tuple[str, ...]] = {
    "ProteinDecay": ("RNAs",),
    "ProteinFolding": ("foldedComplexs", "unfoldedComplexs"),
    "ProteinProcessingII": ("signalSequenceMonomers",),
    "RNADecay": ("RNAs",),
    "RNAProcessing": ("intergenicRNAs",),
}


class UnauthorizedSeed0RegenError(ValueError):
    """Raised when a process outside `STALE5_PROCESSES` is requested here.

    This module must never be usable as a general-purpose seed-0 override;
    see `launcher.SeedZeroForbiddenError` for the default (correct) policy.
    """


def _assert_authorized(processes: list[str] | tuple[str, ...]) -> None:
    unauthorized = [p for p in processes if p not in STALE5_PROCESSES]
    if unauthorized:
        raise UnauthorizedSeed0RegenError(
            f"seed-0 regeneration is only authorized for {STALE5_PROCESSES} "
            f"(ratified decision `regenerate-stale-l22-seed-zero`); refusing {unauthorized}"
        )


@dataclass
class Seed0Decision:
    process: str
    path: str
    action: str  # "skip_valid" | "generate_missing" | "regenerate_stale"
    reason: str | None = None


@dataclass
class Seed0Plan:
    processes: tuple[str, ...]
    n_ticks: int
    decisions: list[Seed0Decision]
    matlab_command: str | None
    log_path: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "processes": list(self.processes),
            "n_ticks": self.n_ticks,
            "decisions": [asdict(d) for d in self.decisions],
            "matlab_command": self.matlab_command,
            "log_path": self.log_path,
            "generated_at": self.generated_at,
        }


def _has_required_channels(path: Path, process: str) -> tuple[bool, str | None]:
    """Cheaply check whether `path`'s states_before already carries this
    process's required extra channel(s) -- i.e. was already regenerated
    under the current extractor -- without a full schema-drift comparison
    (there is no second seed file to compare against yet at this point).
    """
    import h5py  # noqa: PLC0415 (only needed here, mirrors trace_validation's lazy style)

    required = REQUIRED_EXTRA_CHANNELS[process]
    try:
        with h5py.File(path, "r") as handle:
            if "states_before" not in handle:
                return False, "missing states_before group"
            present = set(handle["states_before"].keys())
            missing = [c for c in required if c not in present]
            if missing:
                return False, f"missing required channel(s) {missing} (stale pre-regen schema)"
            return True, None
    except OSError as exc:
        return False, f"unreadable/corrupt HDF5 file: {exc}"


def build_seed0_matlab_command(
    processes: tuple[str, ...],
    *,
    n_ticks: int = DEFAULT_N_TICKS,
    log_relpath: str | None = None,
    include_addpath: bool = True,
) -> str:
    """Build the MATLAB statement(s) for a canonical (unsuffixed) seed-0 run.

    Mirrors `launcher.build_matlab_command`'s diary/try-catch wrapping, but
    targets the canonical unsuffixed `per_process_traces_v2` output
    directory and `seed=0` explicitly -- something `launcher.py` refuses to
    construct at all.
    """
    proc_list = ", ".join(f"'{p}'" for p in processes)
    call = f"extract_per_process_traces_v2({{{proc_list}}}, 'per_process_traces_v2', {int(n_ticks)}, uint32(0));"
    prefix = "addpath('scripts/matlab'); " if include_addpath else ""
    if log_relpath is None:
        return f"{prefix}{call}"
    return (
        f"{prefix}"
        f"diary('{log_relpath}'); "
        f"try; {call} catch err; disp(getReport(err, 'extended', 'hyperlinks', 'off')); end; "
        f"diary off;"
    )


def plan_seed0_regen(
    processes: list[str] | tuple[str, ...],
    *,
    n_ticks: int = DEFAULT_N_TICKS,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    log_relpath: str = "artifacts/l22_stale5_regen/logs/seed000.log",
) -> Seed0Plan:
    """Build a resumable plan for regenerating canonical seed 0 for a subset
    of `STALE5_PROCESSES`.

    - Raises `UnauthorizedSeed0RegenError` for any process outside the
      closed allowlist.
    - `skip_valid`: canonical file exists, is structurally sound, AND
      already carries this process's required extra channel(s) (i.e. it was
      already regenerated under the current extractor this run/resume).
    - `regenerate_stale`: canonical file exists but is structurally invalid
      or is missing the required extra channel(s) (the stale pre-decision
      file, or a partial/corrupt regeneration attempt) -- MUST be deleted
      before MATLAB is invoked (extractor's own skip check is
      existence-only and would otherwise silently keep it).
    - `generate_missing`: no canonical file exists at all.
    """
    processes = tuple(processes)
    _assert_authorized(processes)

    decisions: list[Seed0Decision] = []
    needed: list[str] = []
    for process in processes:
        path = canonical_seed0_path(process, n_ticks=n_ticks, karr_native_root=karr_native_root)
        if not path.exists():
            decisions.append(Seed0Decision(process=process, path=str(path), action="generate_missing"))
            needed.append(process)
            continue
        structural = validate_structural(
            path, expected_process=process, expected_seed=0, expected_n_ticks=n_ticks, compute_hash=False
        )
        if not structural.ok:
            decisions.append(
                Seed0Decision(
                    process=process, path=str(path), action="regenerate_stale",
                    reason="; ".join(structural.errors),
                )
            )
            needed.append(process)
            continue
        has_channels, reason = _has_required_channels(path, process)
        if has_channels:
            decisions.append(Seed0Decision(process=process, path=str(path), action="skip_valid"))
        else:
            decisions.append(
                Seed0Decision(process=process, path=str(path), action="regenerate_stale", reason=reason)
            )
            needed.append(process)

    matlab_command = (
        build_seed0_matlab_command(tuple(needed), n_ticks=n_ticks, log_relpath=log_relpath) if needed else None
    )
    return Seed0Plan(
        processes=processes,
        n_ticks=n_ticks,
        decisions=decisions,
        matlab_command=matlab_command,
        log_path=log_relpath,
        generated_at=datetime.now(UTC).isoformat(),
    )


def apply_seed0_invalidations(plan: Seed0Plan) -> list[str]:
    """Delete files marked `regenerate_stale` so the extractor's own
    existence-only skip check will actually regenerate them."""
    deleted: list[str] = []
    for decision in plan.decisions:
        if decision.action == "regenerate_stale":
            path = Path(decision.path)
            if path.exists():
                path.unlink()
                deleted.append(str(path))
    return deleted


def _cmd_plan(args: argparse.Namespace) -> int:
    import json  # noqa: PLC0415

    processes = args.processes.split(",")
    plan = plan_seed0_regen(processes, n_ticks=args.n_ticks)
    deleted: list[str] = []
    if args.apply_invalidation:
        deleted = apply_seed0_invalidations(plan)
    out = plan.to_dict()
    out["deleted_stale_files"] = deleted
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[seed0_regen] wrote plan to {args.out}: matlab_command={'set' if plan.matlab_command else 'None (nothing to do)'}")
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan_parser = sub.add_parser("plan", help="Build a resumable seed-0 regeneration plan JSON.")
    plan_parser.add_argument(
        "--processes", required=True, help="Comma-separated subset of STALE5_PROCESSES."
    )
    plan_parser.add_argument("--n-ticks", type=int, default=DEFAULT_N_TICKS)
    plan_parser.add_argument(
        "--apply-invalidation", action="store_true", help="Delete files marked regenerate_stale."
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
