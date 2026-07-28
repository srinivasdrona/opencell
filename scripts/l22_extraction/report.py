"""Generate the Phase 2 (seed-1 preflight) and Phase 3 (final) evidence
reports for the L2.2 full multi-seed extraction, reusing:

  - `scripts/l22_extraction/preflight.py` (schema drift + real loader dispatch)
  - `scripts/l22_extraction/trace_validation.py` (structural file validation)
  - `scripts/l22_extraction/derive_scope.py` (the mechanically-derived
    production process set, so the report can never silently drift from the
    launcher's own scope)

Usage (WSL only, per project convention):
    bin\\oc-py scripts/l22_extraction/report.py preflight --out <path.json>
    bin\\oc-py scripts/l22_extraction/report.py final --seeds 1-49 --out <path.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.derive_scope import derive_scope  # noqa: E402
from scripts.l22_extraction.launcher import (  # noqa: E402
    EXTRACTOR_SCRIPT,
    canonical_seed0_path,
    git_blob_sha256,
    seed_mat_path,
)
from scripts.l22_extraction.preflight import loader_report, schema_preflight  # noqa: E402
from scripts.l22_extraction.trace_validation import validate_structural  # noqa: E402

SPECIALIZED_ENSEMBLE_PROCESSES = ("Transcription", "Translation")
EXPECTED_FULL_SEED_COUNT = 50


def _parse_seed_spec(spec: str) -> list[int]:
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


def build_preflight_report(
    *,
    seed: int = 1,
    processes: list[str] | tuple[str, ...] | None = None,
    include_specialized: bool = True,
) -> dict[str, Any]:
    """Phase 2: for every production process, does a freshly generated
    `seed` match canonical seed 0's schema? Also audits the two specialized
    ensembles (Transcription/Translation) stay at 50 seeds with no drift.

    `processes`, if given, narrows the production-process loop to an
    explicit subset (e.g. just the L22_STALE5 set) instead of the full
    mechanically-derived scope -- used so this report can be run for a
    partial worktree that only holds a subset of the 16 production
    processes' trace files, without falsely flagging the rest as missing.
    Defaults to the full `derive_scope().production` set (unchanged
    behaviour) when omitted.
    """
    scope = derive_scope()
    production = tuple(processes) if processes is not None else scope.production
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "preflight_seed": seed,
        "production_processes": list(production),
        "specialized_processes": list(scope.specialized_excluded.keys()),
        "results": {},
        "blockers": [],
    }

    for process in production:
        drift = schema_preflight(process, [seed])
        loader = loader_report(process)
        entry = {"schema_preflight": drift, "loader": loader}
        report["results"][process] = entry
        if not drift.get("ok"):
            report["blockers"].append(f"{process}: schema drift seed0 vs seed{seed}: {drift.get('error')}")
        if not loader.get("ok"):
            report["blockers"].append(f"{process}: loader dispatch failed: {loader.get('error')}")

    for process in SPECIALIZED_ENSEMBLE_PROCESSES if include_specialized else ():
        loader = loader_report(process)
        entry = {"loader": loader}
        ok = (
            loader.get("ok")
            and int(loader.get("canonical_seed_count", 0)) >= EXPECTED_FULL_SEED_COUNT
            and not any("drift" in w.lower() for w in loader.get("warnings", []))
        )
        entry["specialized_ensemble_healthy"] = bool(ok)
        report["results"][process] = entry
        if not ok:
            report["blockers"].append(
                f"{process}: specialized ensemble audit failed "
                f"(canonical_seed_count={loader.get('canonical_seed_count')}, warnings={loader.get('warnings')})"
            )

    report["result"] = "PASS" if not report["blockers"] else "BLOCKED"
    return report


def build_final_report(
    *,
    seeds: list[int],
    processes: list[str] | tuple[str, ...] | None = None,
    include_specialized: bool = True,
    expected_n_ticks: int = 100,
) -> dict[str, Any]:
    """Phase 3: validate every expected MAT for the production set, plus the
    real loader dispatch (expects canonical_seed_count == 50, no
    KARR_SINGLE_SEED_REUSED-class warning) for both production and
    specialized-ensemble processes.

    `processes`, if given, narrows the loop to an explicit subset (see
    `build_preflight_report`'s docstring for the rationale). Defaults to the
    full `derive_scope().production` set when omitted.

    `expected_n_ticks` (default 100, unchanged behaviour) only controls the
    *internal* tick-depth structural check (`validate_structural`'s
    `expected_n_ticks`) -- it never affects filename/path resolution
    (`canonical_seed0_path`/`seed_mat_path` keep resolving the legacy
    `_100ticks.mat` name regardless). This exists for the narrow
    `DEPTH200_PROCESSES` case (`scripts/l22_extraction/depth200_regen.py`):
    those processes' `_100ticks.mat` files genuinely carry 200 real ticks
    (a deliberate legacy-filename decision, see that module's docstring),
    so their final verification must pass `expected_n_ticks=200` while every
    other process keeps the default.
    """
    scope = derive_scope()
    production = tuple(processes) if processes is not None else scope.production
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "seeds_expected": seeds,
        "production_processes": list(production),
        "specialized_processes": list(scope.specialized_excluded.keys()),
        "extractor_source_sha256": git_blob_sha256(EXTRACTOR_SCRIPT) if EXTRACTOR_SCRIPT.exists() else None,
        "files": {},
        "loader_results": {},
        "missing_or_failing": [],
    }

    for process in production:
        per_process: dict[str, Any] = {}
        seed0 = canonical_seed0_path(process)
        seed0_result = validate_structural(
            seed0, expected_process=process, expected_seed=0, expected_n_ticks=expected_n_ticks
        )
        per_process["0"] = seed0_result.to_dict()
        if not seed0_result.ok:
            report["missing_or_failing"].append(f"{process} seed0: {seed0_result.errors}")
        for seed in seeds:
            path = seed_mat_path(process, seed)
            result = validate_structural(
                path, expected_process=process, expected_seed=seed, expected_n_ticks=expected_n_ticks
            )
            per_process[str(seed)] = result.to_dict()
            if not result.ok:
                report["missing_or_failing"].append(f"{process} seed{seed}: {result.errors}")
        report["files"][process] = per_process

        loader = loader_report(process)
        report["loader_results"][process] = loader
        if loader.get("ok") and int(loader.get("canonical_seed_count", 0)) != EXPECTED_FULL_SEED_COUNT:
            report["missing_or_failing"].append(
                f"{process}: canonical_seed_count={loader.get('canonical_seed_count')} != {EXPECTED_FULL_SEED_COUNT}"
            )
        if loader.get("ok") and any("KARR_SINGLE_SEED_REUSED" in w for w in loader.get("warnings", [])):
            report["missing_or_failing"].append(f"{process}: unexpected KARR_SINGLE_SEED_REUSED warning")

    for process in SPECIALIZED_ENSEMBLE_PROCESSES if include_specialized else ():
        loader = loader_report(process)
        report["loader_results"][process] = loader
        if loader.get("ok") and int(loader.get("canonical_seed_count", 0)) != EXPECTED_FULL_SEED_COUNT:
            report["missing_or_failing"].append(
                f"{process} (specialized): canonical_seed_count={loader.get('canonical_seed_count')} "
                f"!= {EXPECTED_FULL_SEED_COUNT}"
            )

    report["result"] = "PASS" if not report["missing_or_failing"] else "INCOMPLETE"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    pre = sub.add_parser("preflight")
    pre.add_argument("--seed", type=int, default=1)
    pre.add_argument("--processes", help="Comma-separated subset override (default: full derived scope).")
    pre.add_argument("--skip-specialized", action="store_true")
    pre.add_argument("--out", required=True)

    fin = sub.add_parser("final")
    fin.add_argument("--seeds", required=True, help='e.g. "1-49"')
    fin.add_argument("--processes", help="Comma-separated subset override (default: full derived scope).")
    fin.add_argument("--skip-specialized", action="store_true")
    fin.add_argument(
        "--expected-n-ticks",
        type=int,
        default=100,
        help=(
            "Internal tick-depth check only (default 100, unchanged behaviour); never "
            "affects filename resolution. Use 200 for DEPTH200_PROCESSES (see "
            "scripts/l22_extraction/depth200_regen.py)."
        ),
    )
    fin.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    processes = args.processes.split(",") if getattr(args, "processes", None) else None
    if args.cmd == "preflight":
        report = build_preflight_report(
            seed=args.seed, processes=processes, include_specialized=not args.skip_specialized
        )
    else:
        report = build_final_report(
            seeds=_parse_seed_spec(args.seeds),
            processes=processes,
            include_specialized=not args.skip_specialized,
            expected_n_ticks=args.expected_n_ticks,
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[report] wrote {out_path} result={report['result']}")
    if report["result"] not in ("PASS",):
        for item in report.get("blockers", report.get("missing_or_failing", [])):
            print(f"  BLOCKER: {item}")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
