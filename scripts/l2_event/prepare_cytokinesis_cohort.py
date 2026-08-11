"""Inventory and prepare the Cytokinesis event-window cohort.

This is a MATLAB-FREE preparation utility for the August 2026 Cytokinesis
closure lane:

* inventory every Cytokinesis trace visible under the current repo, the main
  checkout, and sibling worktrees unless the caller overrides the search roots;
* validate the real seed-0 event-window trace against the authoritative 4000-
  tick anchor-window contract;
* optionally materialize that valid seed-0 trace into THIS worktree's
  gitignored ``data/m1_sources/karr_native/per_process_traces_v2_event_s000/``
  slot, but only if the slot is absent or already byte-identical;
* write JSON inventory/spec/plan artifacts for the remaining missing cohort
  members (seeds 1-49), using the existing resumable/atomic
  ``scripts.l2_event.launcher`` planner.

Hard rules:
* never launches MATLAB;
* never overwrites a non-identical existing trace;
* never edits the shared catalog or evidence indexes;
* never infers the cohort-wide maximum onset span from a partial sample.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import evidence, launcher  # noqa: E402
from scripts.l2_event.survey_cytokinesis_onset_span import (  # noqa: E402
    REQUIRED_N_SEEDS,
    REQUIRED_OBSERVABLES,
    onset_span_for_trace,
)
from scripts.l2_event.window_loader import classify_trace_dir  # noqa: E402

PROCESS = "Cytokinesis"
AUTHORITATIVE_N_TICKS = 4000
_TRACE_NAME_RE = re.compile(r"^Cytokinesis_(\d+)ticks\.mat$")
_EVENT_SEED_DIR_RE = re.compile(r"per_process_traces_v2_event_s(\d+)$")
_STANDARD_SEED_DIR_RE = re.compile(r"per_process_traces_v2_s(\d+)$")


@dataclass(frozen=True)
class TraceCandidate:
    path: Path
    root: Path
    trace_kind: str
    seed: int | None
    n_ticks_hint: int


def _anchor_spec(seed: int, *, n_ticks: int = AUTHORITATIVE_N_TICKS) -> launcher.AnchorWindowSpec:
    return launcher.AnchorWindowSpec(
        process=PROCESS,
        seed=seed,
        n_ticks=n_ticks,
        required_observables=REQUIRED_OBSERVABLES,
        scalar_finite_observables=launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES,
    )


def _main_repo_root(repo_root: Path) -> Path | None:
    drive_root = repo_root.parents[1]
    candidate = drive_root / "opencell"
    return candidate if candidate.exists() else None


def autodiscover_karr_native_roots(repo_root: Path = REPO_ROOT) -> list[Path]:
    roots: list[Path] = []

    def _add(path: Path | None) -> None:
        if path is None:
            return
        resolved = path.resolve()
        if resolved.exists() and resolved not in roots:
            roots.append(resolved)

    _add(repo_root / "data" / "m1_sources" / "karr_native")

    main_repo = _main_repo_root(repo_root)
    if main_repo is not None:
        _add(main_repo / "data" / "m1_sources" / "karr_native")

    # Sibling worktrees live directly under the current worktree's parent
    # directory (e.g. E:/opencell-worktrees/*), not under the drive root.
    worktrees_root = repo_root.parent
    if worktrees_root.exists():
        for worktree in sorted(worktrees_root.iterdir()):
            if not worktree.is_dir():
                continue
            _add(worktree / "data" / "m1_sources" / "karr_native")

    return roots


def discover_trace_candidates(search_roots: list[Path]) -> list[TraceCandidate]:
    candidates: list[TraceCandidate] = []
    seen: set[Path] = set()
    for root in search_roots:
        for path in sorted(root.glob("*/Cytokinesis_*ticks.mat")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            name_match = _TRACE_NAME_RE.match(path.name)
            if name_match is None:
                continue
            parent_name = path.parent.name
            trace_kind = classify_trace_dir(path)
            seed: int | None = None
            event_match = _EVENT_SEED_DIR_RE.match(parent_name)
            if event_match is not None:
                seed = int(event_match.group(1))
            else:
                standard_match = _STANDARD_SEED_DIR_RE.match(parent_name)
                if standard_match is not None:
                    seed = int(standard_match.group(1))
                elif parent_name in {"per_process_traces", "per_process_traces_v2"}:
                    seed = 0
            candidates.append(
                TraceCandidate(
                    path=resolved,
                    root=root.resolve(),
                    trace_kind=trace_kind,
                    seed=seed,
                    n_ticks_hint=int(name_match.group(1)),
                )
            )
    return candidates


def _validate_event_candidate(candidate: TraceCandidate) -> dict[str, object]:
    record: dict[str, object] = {
        "path": str(candidate.path),
        "root": str(candidate.root),
        "trace_kind": candidate.trace_kind,
        "seed": candidate.seed,
        "n_ticks_hint": candidate.n_ticks_hint,
    }
    if candidate.trace_kind != "event_window" or candidate.seed is None:
        record["cohort_eligible"] = False
        record["valid_for_authoritative_cohort"] = False
        record["validation_reason"] = "not an event-window Cytokinesis seed trace"
        return record

    ok, reason = launcher.validate_existing_event_window(candidate.path, _anchor_spec(candidate.seed))
    record["cohort_eligible"] = True
    record["valid_for_authoritative_cohort"] = ok
    record["validation_reason"] = reason if not ok else ""
    if ok:
        record["sha256"] = evidence.sha256_file(candidate.path)
        onset_tick, completion_tick, span = onset_span_for_trace(candidate.path)
        record["onset_tick"] = onset_tick
        record["completion_tick"] = completion_tick
        record["span_ticks"] = span
    return record


def build_inventory(search_roots: list[Path]) -> list[dict[str, object]]:
    return [_validate_event_candidate(candidate) for candidate in discover_trace_candidates(search_roots)]


def select_seed0_source(inventory: list[dict[str, object]]) -> dict[str, object]:
    valid_seed0 = [
        row
        for row in inventory
        if row.get("seed") == 0 and row.get("valid_for_authoritative_cohort") is True
    ]
    if not valid_seed0:
        raise RuntimeError("No valid seed-0 Cytokinesis event-window trace found in the searched roots.")

    unique_hashes = {str(row["sha256"]) for row in valid_seed0}
    if len(unique_hashes) != 1:
        raise RuntimeError(
            "Multiple distinct valid seed-0 Cytokinesis event traces were found. "
            "Refusing to guess which one is canonical."
        )
    return valid_seed0[0]


def materialize_seed0(source_path: Path, *, output_root: Path) -> dict[str, object]:
    target_path = launcher.event_window_mat_path(
        PROCESS,
        0,
        n_ticks=AUTHORITATIVE_N_TICKS,
        karr_native_root=output_root,
    )
    source_path = source_path.resolve()
    target_path = target_path.resolve()

    if target_path == source_path:
        return {
            "status": "already_local",
            "target_path": str(target_path),
            "sha256": evidence.sha256_file(target_path),
        }

    source_sha = evidence.sha256_file(source_path)
    if target_path.exists():
        target_sha = evidence.sha256_file(target_path)
        if target_sha != source_sha:
            raise RuntimeError(
                f"Refusing to overwrite non-identical existing seed-0 trace at {target_path} "
                f"(existing sha256={target_sha}, source sha256={source_sha})."
            )
        return {
            "status": "already_present_identical",
            "target_path": str(target_path),
            "sha256": target_sha,
        }

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    copied_sha = evidence.sha256_file(target_path)
    if copied_sha != source_sha:
        raise RuntimeError(
            f"Copied seed-0 trace hash mismatch: source {source_sha}, target {copied_sha}."
        )
    ok, reason = launcher.validate_existing_event_window(target_path, _anchor_spec(0))
    if not ok:
        raise RuntimeError(
            f"Copied seed-0 trace failed authoritative validation at {target_path}: {reason}"
        )
    return {
        "status": "copied",
        "target_path": str(target_path),
        "sha256": copied_sha,
    }


def build_missing_seed_specs(valid_event_seeds: set[int]) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for seed in range(1, REQUIRED_N_SEEDS):
        if seed in valid_event_seeds:
            continue
        spec = _anchor_spec(seed)
        specs.append(
            {
                "process": spec.process,
                "seed": spec.seed,
                "window_contract": spec.window_contract,
                "required_observables": list(spec.required_observables),
                "n_ticks": spec.n_ticks,
                "max_search_ticks": spec.max_search_ticks,
                "signal_kind": spec.signal_kind,
                "signal_property": spec.signal_property,
                "signal_field": spec.signal_field,
                "scalar_finite_observables": list(spec.scalar_finite_observables),
            }
        )
    return specs


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def prepare_cohort(
    *,
    search_roots: list[Path],
    output_root: Path,
    out_dir: Path,
    materialize_seed0_locally: bool,
) -> dict[str, object]:
    inventory = build_inventory(search_roots)
    seed0_source = select_seed0_source(inventory)

    valid_event_seeds = {
        int(row["seed"])
        for row in inventory
        if row.get("valid_for_authoritative_cohort") is True and row.get("seed") is not None
    }
    missing_event_seeds = [
        seed for seed in range(REQUIRED_N_SEEDS) if seed not in valid_event_seeds
    ]

    materialization: dict[str, object] | None = None
    if materialize_seed0_locally:
        materialization = materialize_seed0(Path(str(seed0_source["path"])), output_root=output_root)

    specs_payload = build_missing_seed_specs(valid_event_seeds)
    plan = launcher.plan_event_window_extraction(
        [_anchor_spec(int(row["seed"])) for row in specs_payload],
        karr_native_root=output_root,
        validate_existing=True,
    )

    out_dir = out_dir.resolve()
    inventory_path = out_dir / "inventory.json"
    specs_path = out_dir / "seed_1_49_specs.json"
    plan_path = out_dir / "seed_1_49_plan.json"
    summary_path = out_dir / "summary.json"

    _write_json(inventory_path, inventory)
    _write_json(specs_path, specs_payload)
    _write_json(plan_path, plan.to_dict())
    summary = {
        "process": PROCESS,
        "authoritative_n_ticks": AUTHORITATIVE_N_TICKS,
        "required_n_seeds": REQUIRED_N_SEEDS,
        "searched_roots": [str(path) for path in search_roots],
        "output_root": str(output_root.resolve()),
        "valid_event_seeds": sorted(valid_event_seeds),
        "missing_event_seeds": missing_event_seeds,
        "seed0_source": seed0_source,
        "seed0_materialization": materialization,
        "inventory_path": str(inventory_path),
        "specs_path": str(specs_path),
        "plan_path": str(plan_path),
        "ready_for_matlab": True,
    }
    _write_json(summary_path, summary)
    summary["summary_path"] = str(summary_path)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-root",
        action="append",
        type=Path,
        default=None,
        help=(
            "Optional additional karr_native root(s) to inventory. If omitted, the script "
            "auto-discovers this worktree, the main checkout, and sibling worktrees."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=launcher.KARR_NATIVE_ROOT,
        help="karr_native root whose per_process_traces_v2_event_sNNN directories the future extraction will target.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "l2_event" / "cytokinesis_prep",
        help="Directory to write inventory/spec/plan JSON artifacts into.",
    )
    parser.add_argument(
        "--materialize-seed0",
        action="store_true",
        help=(
            "Copy the already-valid seed-0 trace into this worktree's output root if missing. "
            "Refuses to overwrite any non-identical existing file."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    search_roots = [path.resolve() for path in args.search_root] if args.search_root else autodiscover_karr_native_roots()
    if not search_roots:
        print("[prepare_cytokinesis_cohort] no karr_native roots found to search", file=sys.stderr)
        return 1

    summary = prepare_cohort(
        search_roots=search_roots,
        output_root=args.output_root.resolve(),
        out_dir=args.out_dir.resolve(),
        materialize_seed0_locally=args.materialize_seed0,
    )

    print(
        "[prepare_cytokinesis_cohort] "
        f"valid_event_seeds={summary['valid_event_seeds']} "
        f"missing_event_seed_count={len(summary['missing_event_seeds'])} "
        f"plan_path={summary['plan_path']}"
    )
    if summary.get("seed0_materialization"):
        materialization = summary["seed0_materialization"]
        print(
            "[prepare_cytokinesis_cohort] "
            f"seed0_materialization={materialization['status']} -> {materialization['target_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
