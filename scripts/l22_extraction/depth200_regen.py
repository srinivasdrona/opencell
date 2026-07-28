"""Depth-200 regeneration for the three processes whose PROCESS_CATALOG.yaml
`M_ticks: 200` requirement (DNARepair, ProteinDecay, ReplicationInitiation)
was previously served by stale 100-tick oracle files -- see
`docs/phase_f/l2_2_design_a/L22_DEPTH200_REGEN_REPORT.md` for full evidence
and rationale.

**The legacy-filename decision (read this before touching this module):**
`extract_per_process_traces_v2.m` names its own output
`<Process>_<n_ticks>ticks.mat`, so a genuine 200-tick extraction naturally
produces `<Process>_200ticks.mat`. But the real-oracle loader
(`tests/vivarium/_l2_2_design_a_runner_helpers.py`) hardcodes the literal
string `_100ticks.mat` in every path it resolves (`_v2_canonical_seed0_mat_path`,
`_v2_suffixed_seed_mat_path`, `_v2_seed_mat_path`, `_ensembles_seed_mat_path`)
-- it is NOT parameterized by an actual tick count. That loader is the
runner-adjacent oracle-serving code this task must not change. Consequently
a fresh 200-tick extraction is only *usable* if its bytes end up at the
literal `<Process>_100ticks.mat` path the loader already looks up.

This module therefore runs the real extraction at `REAL_N_TICKS = 200`
(genuine per-tick simulation depth, honest `metadata.n_ticks == 200`,
honest `states_before`/`states_after` arrays with 200 tick-rows) into its
natural `_200ticks.mat` filename, then RELABELS (renames in place) that
file to the legacy `_100ticks.mat` name the loader expects --
`relabel_seed_to_legacy_filename` verifies the source file's own
`metadata.n_ticks == REAL_N_TICKS` immediately before the rename, so a
partial/wrong-depth file can never be silently relabeled. The resulting
`_100ticks.mat` file's *name* is therefore a legacy label that no longer
describes its content (200 real ticks, not 100) -- this is intentional,
narrowly scoped to `DEPTH200_PROCESSES`, and must be called out explicitly
in any report/manifest this module's output feeds into. It does not create
any new filename the loader wouldn't already recognize, and it never
touches `_s000` (seed 0 stays canonical/unsuffixed per the general policy
enforced by `launcher.SeedZeroForbiddenError`).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.launcher import (  # noqa: E402
    KARR_NATIVE_ROOT,
    ExtractionPlan,
    canonical_seed0_path,
    plan_extraction,
    seed_mat_path,
)
from scripts.l22_extraction.seed0_regen import build_seed0_matlab_command  # noqa: E402
from scripts.l22_extraction.trace_validation import validate_structural  # noqa: E402

# Closed allowlist: exactly the three processes named in the ratified
# "depth200 regen" scope (PROCESS_CATALOG.yaml M_ticks=200 for these three,
# stale 100-tick oracle files accepted files predate that requirement).
# Never extend this set implicitly; a new M_ticks depth mismatch requires
# its own scoped decision.
DEPTH200_PROCESSES: tuple[str, ...] = ("DNARepair", "ProteinDecay", "ReplicationInitiation")

# The genuine simulated tick depth this module always extracts at.
REAL_N_TICKS = 200
# The filename component the loader hardcodes (see module docstring). Never
# change this to match REAL_N_TICKS -- that would create exactly the
# "parallel unrecognized name" the task forbids.
LEGACY_FILENAME_N_TICKS_LABEL = 100


class UnauthorizedDepth200RegenError(ValueError):
    """Raised when a process outside `DEPTH200_PROCESSES` is requested here.

    Mirrors `seed0_regen.UnauthorizedSeed0RegenError`'s closed-allowlist
    policy: this module must never be usable as a general-purpose
    tick-depth override for any process outside its ratified scope.
    """


def _assert_authorized(processes: list[str] | tuple[str, ...]) -> None:
    unauthorized = [p for p in processes if p not in DEPTH200_PROCESSES]
    if unauthorized:
        raise UnauthorizedDepth200RegenError(
            f"depth-200 regeneration is only authorized for {DEPTH200_PROCESSES}; refusing {unauthorized}"
        )


def real_path_for_seed(
    process: str,
    seed: int,
    *,
    real_n_ticks: int = REAL_N_TICKS,
    karr_native_root: Path = KARR_NATIVE_ROOT,
) -> Path:
    """Path the extractor naturally writes to for a genuine `real_n_ticks`-tick run."""
    if int(seed) == 0:
        return canonical_seed0_path(process, n_ticks=real_n_ticks, karr_native_root=karr_native_root)
    return seed_mat_path(process, seed, n_ticks=real_n_ticks, karr_native_root=karr_native_root)


def legacy_path_for_seed(
    process: str,
    seed: int,
    *,
    legacy_label: int = LEGACY_FILENAME_N_TICKS_LABEL,
    karr_native_root: Path = KARR_NATIVE_ROOT,
) -> Path:
    """Path the loader actually looks up (the pre-existing `_100ticks.mat` name)."""
    if int(seed) == 0:
        return canonical_seed0_path(process, n_ticks=legacy_label, karr_native_root=karr_native_root)
    return seed_mat_path(process, seed, n_ticks=legacy_label, karr_native_root=karr_native_root)


def build_seed0_depth200_command(
    processes: list[str] | tuple[str, ...],
    *,
    real_n_ticks: int = REAL_N_TICKS,
    log_relpath: str | None = None,
) -> str:
    """Build the canonical (unsuffixed), seed=0, `real_n_ticks`-tick MATLAB command.

    Reuses `seed0_regen.build_seed0_matlab_command` as-is (it is already
    generic over `processes`/`n_ticks`; only `seed0_regen.plan_seed0_regen`
    enforces that module's own closed allowlist, which this module does not
    call). Enforces THIS module's own `DEPTH200_PROCESSES` allowlist first.
    """
    _assert_authorized(processes)
    return build_seed0_matlab_command(tuple(processes), n_ticks=real_n_ticks, log_relpath=log_relpath)


def plan_depth200_extraction(
    processes: list[str] | tuple[str, ...],
    seeds: list[int] | tuple[int, ...],
    *,
    real_n_ticks: int = REAL_N_TICKS,
    n_workers: int = 1,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    validate_existing: bool = True,
) -> ExtractionPlan:
    """Seeds >= 1 plan, built by directly reusing `launcher.plan_extraction`.

    No invalidation dance is needed here: a genuine `real_n_ticks`-tick
    extraction writes to its own naturally-named `_{real_n_ticks}ticks.mat`
    path, which is disjoint from the pre-existing legacy `_100ticks.mat`
    file, so the extractor's own existence-only skip check never collides
    with old data. The relabel step (see `relabel_seed_to_legacy_filename`)
    is a separate, explicit, post-generation move.
    """
    _assert_authorized(processes)
    return plan_extraction(
        tuple(processes),
        tuple(seeds),
        n_ticks=real_n_ticks,
        n_workers=n_workers,
        karr_native_root=karr_native_root,
        validate_existing=validate_existing,
    )


@dataclass
class RelabelResult:
    process: str
    seed: int
    real_path: str
    legacy_path: str
    action: str  # "relabeled" | "missing_real_file" | "verify_failed"
    real_metadata_n_ticks: int | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def relabel_seed_to_legacy_filename(
    process: str,
    seed: int,
    *,
    real_n_ticks: int = REAL_N_TICKS,
    legacy_label: int = LEGACY_FILENAME_N_TICKS_LABEL,
    karr_native_root: Path = KARR_NATIVE_ROOT,
) -> RelabelResult:
    """Rename a freshly-generated `_{real_n_ticks}ticks.mat` file to the
    loader-recognized `_{legacy_label}ticks.mat` name, replacing whatever
    (stale, 100-tick) content previously lived there.

    Verifies BEFORE renaming that the real file exists, is structurally
    valid for `(process, seed)`, and its own `metadata.n_ticks ==
    real_n_ticks` -- a partial/wrong-depth extraction is reported as
    `verify_failed`, never silently relabeled. The move is a same-directory
    `Path.replace` (atomic on the same filesystem), not a copy.
    """
    _assert_authorized([process])
    real_path = real_path_for_seed(process, seed, real_n_ticks=real_n_ticks, karr_native_root=karr_native_root)
    legacy_path = legacy_path_for_seed(process, seed, legacy_label=legacy_label, karr_native_root=karr_native_root)

    if not real_path.exists():
        return RelabelResult(
            process=process,
            seed=seed,
            real_path=str(real_path),
            legacy_path=str(legacy_path),
            action="missing_real_file",
            reason=f"expected freshly-generated file not found: {real_path}",
        )

    structural = validate_structural(
        real_path, expected_process=process, expected_seed=seed, expected_n_ticks=real_n_ticks, compute_hash=False
    )
    if not structural.ok:
        return RelabelResult(
            process=process,
            seed=seed,
            real_path=str(real_path),
            legacy_path=str(legacy_path),
            action="verify_failed",
            reason="; ".join(structural.errors),
        )

    metadata_n_ticks = int(structural.metadata.get("n_ticks", -1))
    if metadata_n_ticks != int(real_n_ticks):
        return RelabelResult(
            process=process,
            seed=seed,
            real_path=str(real_path),
            legacy_path=str(legacy_path),
            action="verify_failed",
            reason=f"real file metadata.n_ticks={metadata_n_ticks} != expected {real_n_ticks}",
        )

    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    real_path.replace(legacy_path)
    return RelabelResult(
        process=process,
        seed=seed,
        real_path=str(real_path),
        legacy_path=str(legacy_path),
        action="relabeled",
        real_metadata_n_ticks=metadata_n_ticks,
    )


def relabel_all(
    processes: list[str] | tuple[str, ...],
    seeds: list[int] | tuple[int, ...],
    *,
    real_n_ticks: int = REAL_N_TICKS,
    legacy_label: int = LEGACY_FILENAME_N_TICKS_LABEL,
    karr_native_root: Path = KARR_NATIVE_ROOT,
) -> list[RelabelResult]:
    _assert_authorized(processes)
    results: list[RelabelResult] = []
    for process in processes:
        for seed in seeds:
            results.append(
                relabel_seed_to_legacy_filename(
                    process,
                    seed,
                    real_n_ticks=real_n_ticks,
                    legacy_label=legacy_label,
                    karr_native_root=karr_native_root,
                )
            )
    return results


def _cmd_seed0_plan(args: argparse.Namespace) -> int:
    import json  # noqa: PLC0415

    processes = args.processes.split(",")
    command = build_seed0_depth200_command(processes, real_n_ticks=args.n_ticks, log_relpath=args.log)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"processes": processes, "n_ticks": args.n_ticks, "matlab_command": command}, indent=2))
    print(f"[depth200_regen] wrote seed0 plan to {args.out}")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    import json  # noqa: PLC0415

    from scripts.l22_extraction.launcher import _parse_seed_spec  # noqa: PLC0415

    processes = args.processes.split(",")
    seeds = _parse_seed_spec(args.seeds)
    plan = plan_depth200_extraction(
        processes, seeds, real_n_ticks=args.n_ticks, n_workers=args.workers, validate_existing=not args.no_validate
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan.to_dict(), indent=2))
    print(f"[depth200_regen] wrote plan with {sum(len(w.jobs) for w in plan.workers)} jobs to {args.out}")
    return 0


def _cmd_relabel(args: argparse.Namespace) -> int:
    import json  # noqa: PLC0415

    from scripts.l22_extraction.launcher import _parse_seed_spec  # noqa: PLC0415

    processes = args.processes.split(",")
    seeds = _parse_seed_spec(args.seeds)
    results = relabel_all(processes, seeds, real_n_ticks=args.n_ticks)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([r.to_dict() for r in results], indent=2))
    n_relabeled = sum(1 for r in results if r.action == "relabeled")
    n_failed = sum(1 for r in results if r.action != "relabeled")
    print(f"[depth200_regen] relabeled {n_relabeled}/{len(results)} (failed/missing={n_failed}); wrote {args.out}")
    return 0 if n_failed == 0 else 1


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed0 = sub.add_parser("seed0-plan", help="Build the canonical seed=0 MATLAB command.")
    seed0.add_argument("--processes", required=True)
    seed0.add_argument("--n-ticks", type=int, default=REAL_N_TICKS)
    seed0.add_argument("--log")
    seed0.add_argument("--out", required=True)
    seed0.set_defaults(func=_cmd_seed0_plan)

    plan_parser = sub.add_parser("plan", help="Build a resumable seeds>=1 extraction plan JSON.")
    plan_parser.add_argument("--processes", required=True)
    plan_parser.add_argument("--seeds", required=True)
    plan_parser.add_argument("--n-ticks", type=int, default=REAL_N_TICKS)
    plan_parser.add_argument("--workers", type=int, default=1)
    plan_parser.add_argument("--no-validate", action="store_true")
    plan_parser.add_argument("--out", required=True)
    plan_parser.set_defaults(func=_cmd_plan)

    relabel_parser = sub.add_parser("relabel", help="Relabel freshly-generated real-depth files to the legacy name.")
    relabel_parser.add_argument("--processes", required=True)
    relabel_parser.add_argument("--seeds", required=True)
    relabel_parser.add_argument("--n-ticks", type=int, default=REAL_N_TICKS)
    relabel_parser.add_argument("--out", required=True)
    relabel_parser.set_defaults(func=_cmd_relabel)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
