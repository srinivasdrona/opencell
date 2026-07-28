"""L2.2 raw Karr-oracle population: merge sibling-worktree oracle data.

Context (2026-07-28): full Design-A Karr oracle extraction is split across
two raw-extraction worktrees (`clean11` and `stale5`), plus the pre-existing
specialized Transcription/Translation ensembles already present in the
current tree. This module is the *population* step that will eventually
assemble those three sources into the current repo's canonical oracle
location (`data/m1_sources/karr_native/`, the same fixed path
`tests/vivarium/_l2_2_design_a_runner_helpers.py::load_karr_oracle` reads
from) -- but it is deliberately conservative:

  - It NEVER guesses. A process is only ever marked ``RESOLVED`` when its
    required seed count is met by files whose content is either present in
    exactly one source or byte-identical across every source that has it.
  - Any two sources disagreeing about the *same* relative file path (a
    `SPLIT_CONFLICT`) is a hard failure naming the exact path, sources, and
    hashes -- never silently resolved by picking one side.
  - A process with fewer than its catalog-required seed count after merging
    every given source is `INSUFFICIENT_DATA` -- never silently accepted
    with a partial ensemble.
  - An `ensembles/<process>/MANIFEST.json` that disagrees with the actual
    merged seed-file count is a `MANIFEST_MISMATCH` -- never trusted at
    face value.
  - `--apply` (the only mode that actually copies files and writes the
    tracked manifest) refuses to run at all unless every requested process
    is `RESOLVED`. There is no partial-copy mode.

Per explicit task instruction, this module is implemented and tested against
SYNTHETIC fixtures only in this commit; it is NOT invoked against the real
`E:\\opencell-worktrees\\l22-full-extract` / `E:\\opencell-worktrees\\l22-stale5-regen`
worktrees yet. That is a follow-up step, gated on (a) this Phase-A code being
committed [done] and (b) the stale5 tracked commits being integrated into
local main [not yet done as of this commit].

CLI:
    bin\\oc-py scripts/l22_evidence/populate.py \\
        --source clean11=E:\\opencell-worktrees\\l22-full-extract \\
        --source stale5=E:\\opencell-worktrees\\l22-stale5-regen \\
        [--processes Metabolism,Transcription] [--apply] [--out PATH]

The current repo tree is always an implicit source named "current" (no flag
needed) -- this is what lets already-resolved processes (e.g. the
specialized Transcription/Translation ensembles, which "remain in their
existing ensemble source" per the task) resolve without requiring an
explicit --source pointing at themselves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402

KARR_NATIVE_SUBDIR = Path("data") / "m1_sources" / "karr_native"
MAX_SEEDS = 50
CURRENT_SOURCE_NAME = "current"

MANIFEST_PATH = cat.REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "oracle_population_manifest.json"

STATUS_RESOLVED = "RESOLVED"
STATUS_SPLIT_CONFLICT = "SPLIT_CONFLICT"
STATUS_MANIFEST_MISMATCH = "MANIFEST_MISMATCH"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def design_a_per_tick_processes(catalog_path: Path = cat.CATALOG_PATH) -> dict[str, cat.ProcessEntry]:
    """The 18 in-scope processes this population step is responsible for.

    Event-class processes (Cytokinesis excepted -- it IS design_a_per_tick;
    the true event-class 4 are DNADamage/FtsZPolymerization/RibosomeAssembly's
    sibling set per PROCESS_CATALOG.yaml) route to the L2.event harness, not
    this raw-oracle population step, and are excluded here.
    """
    return {
        name: entry
        for name, entry in cat.in_scope_processes(catalog_path).items()
        if entry.harness_type == "design_a_per_tick"
    }


@dataclass(frozen=True)
class SourceRoot:
    name: str
    path: Path

    @property
    def karr_native_root(self) -> Path:
        return self.path / KARR_NATIVE_SUBDIR


@dataclass(frozen=True)
class FileObservation:
    relative_path: str
    source_name: str
    sha256: str
    absolute_path: str


@dataclass
class ProcessPopulationReport:
    process: str
    status: str
    layout: str | None
    seed_count: int
    required_seeds: int
    problems: list[str] = field(default_factory=list)
    selected_files: list[FileObservation] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.status == STATUS_RESOLVED


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _v2_relative_paths(process: str) -> list[Path]:
    """Every relative path (under a source's karr_native_root) that could be
    part of the v2 layout for `process`: the canonical unsuffixed seed-0
    trace plus every seed-padded per_process_traces_v2_s{NNN}/ trace."""
    paths = [Path("per_process_traces_v2") / f"{process}_100ticks.mat"]
    for seed in range(MAX_SEEDS):
        paths.append(Path(f"per_process_traces_v2_s{seed:03d}") / f"{process}_100ticks.mat")
    return paths


def _ensembles_relative_paths(process: str) -> list[Path]:
    proc_lower = process.lower()
    paths = [Path("ensembles") / proc_lower / "MANIFEST.json"]
    for seed in range(MAX_SEEDS):
        paths.append(Path("ensembles") / proc_lower / f"seed_{seed:03d}" / f"{process}_100ticks.mat")
    return paths


def _git_sha(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _observe(relative_paths: list[Path], sources: list[SourceRoot]) -> dict[str, dict[str, FileObservation]]:
    """relative_path -> {source_name: FileObservation} for paths that exist in >=1 source."""
    observations: dict[str, dict[str, FileObservation]] = {}
    for rel in relative_paths:
        rel_str = rel.as_posix()
        per_source: dict[str, FileObservation] = {}
        for source in sources:
            abs_path = source.karr_native_root / rel
            if abs_path.is_file():
                per_source[source.name] = FileObservation(
                    relative_path=rel_str,
                    source_name=source.name,
                    sha256=_sha256_file(abs_path),
                    absolute_path=str(abs_path),
                )
        if per_source:
            observations[rel_str] = per_source
    return observations


def _resolve_layout(
    process: str, relative_paths: list[Path], sources: list[SourceRoot], *, layout_name: str
) -> tuple[list[FileObservation], list[str]]:
    """Merge one layout's files across all sources.

    A relative path present in more than one source with DIFFERING content
    is a hard SPLIT_CONFLICT (named explicitly, never silently resolved).
    If identical across sources, the lexicographically-first source name is
    selected deterministically (arbitrary but reproducible; true dedup, not
    a real conflict).
    """
    problems: list[str] = []
    selected: list[FileObservation] = []
    for rel_str, per_source in sorted(_observe(relative_paths, sources).items()):
        hashes = {obs.sha256 for obs in per_source.values()}
        if len(hashes) > 1:
            detail = ", ".join(f"{name}={obs.sha256[:12]}.." for name, obs in sorted(per_source.items()))
            problems.append(
                f"{STATUS_SPLIT_CONFLICT}: {process} ({layout_name}) {rel_str} differs across sources: {detail}"
            )
            continue
        chosen_name = sorted(per_source.keys())[0]
        selected.append(per_source[chosen_name])
    return selected, problems


def _v2_seed_count(process: str, selected: list[FileObservation]) -> int:
    canonical_rel = f"per_process_traces_v2/{process}_100ticks.mat"
    seeds: set[int] = set()
    for obs in selected:
        if obs.relative_path == canonical_rel:
            seeds.add(0)
            continue
        stem = obs.relative_path.split("/")[0]  # per_process_traces_v2_s{NNN}
        seeds.add(int(stem.rsplit("_s", 1)[1]))
    return len(seeds)


def _ensembles_seed_count(selected_without_manifest: list[FileObservation]) -> int:
    seeds: set[int] = set()
    for obs in selected_without_manifest:
        seed_dir = obs.relative_path.split("/")[-2]  # seed_{NNN}
        seeds.add(int(seed_dir.split("_")[1]))
    return len(seeds)


def evaluate_process(
    process: str, entry: cat.ProcessEntry, sources: list[SourceRoot]
) -> ProcessPopulationReport:
    required_seeds = int(entry.n_seeds)

    v2_selected, v2_problems = _resolve_layout(process, _v2_relative_paths(process), sources, layout_name="v2")
    ens_selected_all, ens_problems = _resolve_layout(
        process, _ensembles_relative_paths(process), sources, layout_name="ensembles"
    )

    problems = list(v2_problems) + list(ens_problems)
    if problems:
        return ProcessPopulationReport(
            process=process,
            status=STATUS_SPLIT_CONFLICT,
            layout=None,
            seed_count=0,
            required_seeds=required_seeds,
            problems=problems,
        )

    manifest_obs = next((o for o in ens_selected_all if o.relative_path.endswith("MANIFEST.json")), None)
    ens_seed_files = [o for o in ens_selected_all if not o.relative_path.endswith("MANIFEST.json")]

    v2_seed_count = _v2_seed_count(process, v2_selected)
    ens_seed_count = _ensembles_seed_count(ens_seed_files)

    if manifest_obs is not None:
        manifest_payload = json.loads(Path(manifest_obs.absolute_path).read_text(encoding="utf-8"))
        expected = manifest_payload.get("present_seed_count", manifest_payload.get("expected_seed_count"))
        if expected is not None and int(expected) != ens_seed_count:
            return ProcessPopulationReport(
                process=process,
                status=STATUS_MANIFEST_MISMATCH,
                layout=None,
                seed_count=ens_seed_count,
                required_seeds=required_seeds,
                problems=[
                    f"{STATUS_MANIFEST_MISMATCH}: {process} ensembles/MANIFEST.json (source="
                    f"{manifest_obs.source_name}) claims {expected} seed(s) but {ens_seed_count} "
                    "seed file(s) are actually present after merging all sources"
                ],
            )

    if v2_seed_count >= required_seeds and v2_seed_count >= ens_seed_count:
        return ProcessPopulationReport(
            process=process,
            status=STATUS_RESOLVED,
            layout="v2",
            seed_count=v2_seed_count,
            required_seeds=required_seeds,
            selected_files=v2_selected,
        )
    if ens_seed_count >= required_seeds:
        selected = ens_seed_files + ([manifest_obs] if manifest_obs is not None else [])
        return ProcessPopulationReport(
            process=process,
            status=STATUS_RESOLVED,
            layout="ensembles",
            seed_count=ens_seed_count,
            required_seeds=required_seeds,
            selected_files=selected,
        )

    return ProcessPopulationReport(
        process=process,
        status=STATUS_INSUFFICIENT_DATA,
        layout=None,
        seed_count=max(v2_seed_count, ens_seed_count),
        required_seeds=required_seeds,
        problems=[
            f"{STATUS_INSUFFICIENT_DATA}: {process} requires {required_seeds} seed(s); found "
            f"v2={v2_seed_count}, ensembles={ens_seed_count} after merging sources "
            f"{[s.name for s in sources]}"
        ],
    )


def evaluate_all(
    sources: list[SourceRoot], processes: dict[str, cat.ProcessEntry] | None = None
) -> dict[str, ProcessPopulationReport]:
    entries = processes if processes is not None else design_a_per_tick_processes()
    return {name: evaluate_process(name, entry, sources) for name, entry in sorted(entries.items())}


def apply_population(
    reports: dict[str, ProcessPopulationReport], current_root: Path
) -> int:
    """Copy every RESOLVED report's selected files into `current_root`'s
    karr_native tree. Refuses to run (raises) if any report is not RESOLVED,
    or if a destination file already exists with DIFFERENT content than what
    would be copied (never silently overwrites divergent local data)."""
    unresolved = {name: r for name, r in reports.items() if not r.resolved}
    if unresolved:
        raise ValueError(
            f"refusing to apply population: {len(unresolved)} process(es) not RESOLVED: "
            f"{sorted(unresolved)}"
        )

    destination_root = current_root / KARR_NATIVE_SUBDIR
    copied = 0
    for report in reports.values():
        for obs in report.selected_files:
            dest = destination_root / obs.relative_path
            if dest.is_file():
                if _sha256_file(dest) != obs.sha256:
                    raise ValueError(
                        f"refusing to overwrite {dest}: existing content differs from the "
                        f"resolved source ({obs.source_name}:{obs.absolute_path})"
                    )
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(obs.absolute_path, dest)
            copied += 1
    return copied


def write_manifest(
    reports: dict[str, ProcessPopulationReport], sources: list[SourceRoot], out_path: Path
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": [
            {"name": s.name, "path": str(s.path), "git_sha": _git_sha(s.path)} for s in sources
        ],
        "processes": {
            name: {
                "status": r.status,
                "layout": r.layout,
                "seed_count": r.seed_count,
                "required_seeds": r.required_seeds,
                "problems": r.problems,
                "files": [
                    {"relative_path": o.relative_path, "source_name": o.source_name, "sha256": o.sha256}
                    for o in sorted(r.selected_files, key=lambda o: o.relative_path)
                ],
            }
            for name, r in sorted(reports.items())
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _print_report(reports: dict[str, ProcessPopulationReport], sources: list[SourceRoot]) -> None:
    print(f"sources: {', '.join(f'{s.name}={s.path}' for s in sources)}\n")
    print(f"{'Process':<32} {'status':>20} {'layout':>10} {'seeds':>8}")
    print("-" * 74)
    for name, r in sorted(reports.items()):
        print(f"{name:<32} {r.status:>20} {str(r.layout):>10} {f'{r.seed_count}/{r.required_seeds}':>8}")
    problems = [p for r in reports.values() for p in r.problems]
    if problems:
        print("\n## Problems")
        for p in problems:
            print(f"  {p}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Named source worktree root (repeatable), e.g. --source clean11=E:\\opencell-worktrees\\l22-full-extract",
    )
    parser.add_argument("--processes", help="Comma-separated process allowlist; default = all 18 design_a_per_tick.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually copy resolved files into the current repo tree and write the tracked manifest. "
        "Default is dry-run/report only. Refuses to run at all unless every requested process is RESOLVED.",
    )
    parser.add_argument("--out", default=str(MANIFEST_PATH))
    args = parser.parse_args(argv)

    sources = [SourceRoot(name=CURRENT_SOURCE_NAME, path=cat.REPO_ROOT)]
    seen_names = {CURRENT_SOURCE_NAME}
    for raw in args.source:
        if "=" not in raw:
            parser.error(f"--source must be NAME=PATH, got {raw!r}")
        name, _, path_str = raw.partition("=")
        if not name or name in seen_names:
            parser.error(f"--source name must be non-empty and unique, got {name!r}")
        seen_names.add(name)
        sources.append(SourceRoot(name=name, path=Path(path_str)))

    entries = design_a_per_tick_processes()
    if args.processes:
        wanted = {p.strip() for p in args.processes.split(",") if p.strip()}
        unknown = wanted - set(entries)
        if unknown:
            parser.error(f"unknown/non-design_a_per_tick process(es): {sorted(unknown)}")
        entries = {name: e for name, e in entries.items() if name in wanted}

    reports = evaluate_all(sources, entries)
    _print_report(reports, sources)

    unresolved = {name: r for name, r in reports.items() if not r.resolved}
    if unresolved:
        print(f"\n{len(unresolved)} of {len(reports)} process(es) NOT resolved; refusing to populate.")
        return 1

    if not args.apply:
        print(f"\nAll {len(reports)} requested process(es) resolved. Dry-run only (pass --apply to copy + write manifest).")
        return 0

    copied = apply_population(reports, cat.REPO_ROOT)
    write_manifest(reports, sources, Path(args.out))
    print(f"\nApplied: copied {copied} file(s); wrote manifest to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
