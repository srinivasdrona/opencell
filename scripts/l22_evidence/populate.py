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
import re
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
    # None = unrestricted (may contribute to any process it has files for).
    # Any accepted-oracle worktree source (clean11/stale5) MUST be given an
    # explicit, non-None allowlist so it can never silently supply data for
    # a process outside its mechanically-derived accepted set -- e.g. so
    # clean11's own (stale, pre-regen) canonical seed0 for the 5 blocked
    # processes can never be selected over stale5's regenerated canonical.
    allowed_processes: frozenset[str] | None = None

    @property
    def karr_native_root(self) -> Path:
        return self.path / KARR_NATIVE_SUBDIR

    def may_contribute(self, process: str) -> bool:
        return self.allowed_processes is None or process in self.allowed_processes


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


_WINDOWS_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def _windows_path_to_wsl(path_str: str) -> str:
    """Translate a Windows-style absolute drive path (`E:\\foo\\bar` or
    `E:/foo/bar`) to its WSL `/mnt/<drive>/...` mount equivalent. A pure
    string transform -- no subprocess/shell involvement, so there is no
    injection surface. Paths that don't match the drive-letter pattern
    (already POSIX, or relative) are returned unchanged."""
    match = _WINDOWS_DRIVE_PATH_RE.match(path_str)
    if not match:
        return path_str
    drive, rest = match.groups()
    return f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"


def _maybe_translate_windows_path(path_str: str, *, platform: str | None = None) -> str:
    """Translate a Windows-style absolute path to its WSL mount equivalent,
    but ONLY when not running natively on Windows -- there, `E:\\...` paths
    are already correct as-is, and translating them would break them.
    `platform` defaults to `sys.platform`; tests inject a value directly so
    the branch is exercised without depending on the real host platform."""
    if platform is None:
        platform = sys.platform
    if platform.startswith("win32"):
        return path_str
    return _windows_path_to_wsl(path_str)


def _resolve_worktree_gitdir(path: Path) -> Path | None:
    """If `path` is a linked git *worktree* (its `.git` is a FILE containing
    `gitdir: <target>`, not an ordinary `.git` directory), read and resolve
    that target -- translating a Windows-style absolute target to its WSL
    mount equivalent when necessary.

    Every worktree in this project is created on Windows, so every linked
    worktree's `.git` file's target is always an absolute `E:/...`-style
    path (e.g. `gitdir: E:/opencell/.git/worktrees/l22-full-extract`).
    Native WSL/Linux `git` cannot itself resolve that (`git -C <path>` ends
    up concatenating the unrecognized `E:/...` fragment onto the cwd and
    fails with "not a git repository") -- so this project's tooling must
    translate it itself before invoking git.

    Returns None if `path`'s `.git` is an ordinary directory (a ordinary,
    non-worktree repo -- caller falls back to plain `git -C <path>`), if
    `.git` doesn't exist at all, or if the resolved target isn't an actual
    directory (e.g. stale/broken pointer) -- in every such case the caller
    falls through to its existing behavior, so nothing about resolution or
    copy semantics changes for non-worktree sources.
    """
    git_marker = path / ".git"
    if not git_marker.is_file():
        return None
    try:
        content = git_marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "gitdir:"
    if not content.startswith(prefix):
        return None
    target = content[len(prefix) :].strip()
    translated = _maybe_translate_windows_path(target)
    resolved = Path(translated)
    return resolved if resolved.is_dir() else None


def _git_sha(path: Path) -> str | None:
    """The HEAD commit SHA of the git repository/worktree at `path`, or
    `None` if `path` isn't a git repository at all (explicit, never
    fabricated). Linked worktrees (see `_resolve_worktree_gitdir`) are
    resolved via their own `--git-dir` rather than `-C <path>`, since a
    Windows-created worktree's `.git` pointer file is otherwise
    unresolvable by native WSL/Linux git."""
    worktree_gitdir = _resolve_worktree_gitdir(path)
    args = (
        ["git", "--git-dir", str(worktree_gitdir), "rev-parse", "HEAD"]
        if worktree_gitdir is not None
        else ["git", "-C", str(path), "rev-parse", "HEAD"]
    )
    try:
        result = subprocess.run(
            args,
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


def _eligible_sources(process: str, sources: list[SourceRoot]) -> list[SourceRoot]:
    """Sources scoped (via `SourceRoot.allowed_processes`) OUT of contributing
    to `process` are dropped entirely before any file is observed -- this is
    what prevents e.g. clean11's own stale pre-regen canonical seed0 for a
    stale5-owned process from ever being a candidate, even if the file is
    physically present in clean11's tree."""
    return [s for s in sources if s.may_contribute(process)]


def evaluate_process(
    process: str, entry: cat.ProcessEntry, sources: list[SourceRoot]
) -> ProcessPopulationReport:
    required_seeds = int(entry.n_seeds)
    eligible = _eligible_sources(process, sources)

    v2_selected, v2_problems = _resolve_layout(process, _v2_relative_paths(process), eligible, layout_name="v2")
    ens_selected_all, ens_problems = _resolve_layout(
        process, _ensembles_relative_paths(process), eligible, layout_name="ensembles"
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
            f"v2={v2_seed_count}, ensembles={ens_seed_count} after merging ELIGIBLE sources "
            f"{[s.name for s in eligible]} (of {[s.name for s in sources]} total, source scoping applied)"
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


# Known pre-existing tracked artifact from the Phase 2 seed-1 schema
# preflight (commit cc66914): a single stray Translation_100ticks.mat landed
# in the generic v2 layout's seed-1 directory during specialized-ensemble
# preflight validation, and remains committed there in every worktree
# descended from that commit (current tree, clean11, stale5 alike). It is
# harmless -- `load_karr_oracle` always prefers Translation's 50-seed
# `ensembles/` layout over this lone v2 file by seed count -- and this task
# must not delete or modify tracked raw MAT evidence. Named explicitly here
# (mechanical, visible) rather than silently loosening validate_destination's
# extras check for every unnamed file.
KNOWN_PRE_EXISTING_V2_EXTRAS: frozenset[str] = frozenset(
    {"per_process_traces_v2_s001/Translation_100ticks.mat"}
)


@dataclass
class DestinationValidationReport:
    expected_processes: list[str]
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra


def validate_destination(
    dest_karr_native_root: Path,
    expected_processes: set[str] | frozenset[str],
    seeds: range = range(1, MAX_SEEDS),
    ignore_relative_paths: frozenset[str] = KNOWN_PRE_EXISTING_V2_EXTRAS,
) -> DestinationValidationReport:
    """Verify the v2-layout destination directories contain EXACTLY the
    expected process x seed matrix: canonical (`per_process_traces_v2/`,
    the sole, authoritative location for seed 0 -- per the hard
    no-competing-`_s000` policy, no `per_process_traces_v2_s000/` directory
    should ever exist) plus every `per_process_traces_v2_s{seed:03d}/` for
    `seeds` (default 1-49), one `{process}_100ticks.mat` per expected
    process, per directory -- no missing files, and no extra/unexpected
    `.mat` files (e.g. a wrong-process file that leaked in from copying a
    whole directory instead of the exact named files this tool always
    copies).

    This is a pure filesystem check -- it does not re-verify content
    hashes (that is `evaluate_process`'s job); it only verifies *presence*
    and *absence* of exactly the right file names, which is what "no
    extras" means at the destination.
    """
    missing: list[str] = []
    extra: list[str] = []
    ignored: list[str] = []
    expected_filenames = {f"{p}_100ticks.mat" for p in expected_processes}

    dirnames = ["per_process_traces_v2"] + [f"per_process_traces_v2_s{seed:03d}" for seed in seeds]
    for dirname in dirnames:
        dir_path = dest_karr_native_root / dirname
        present = {p.name for p in dir_path.glob("*.mat")} if dir_path.is_dir() else set()
        for process in sorted(expected_processes):
            fname = f"{process}_100ticks.mat"
            if fname not in present:
                missing.append(f"{dirname}/{fname}")
        for fname in sorted(present - expected_filenames):
            rel = f"{dirname}/{fname}"
            if rel in ignore_relative_paths:
                ignored.append(rel)
            else:
                extra.append(rel)

    return DestinationValidationReport(
        expected_processes=sorted(expected_processes), missing=missing, extra=extra, ignored=ignored
    )


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


def _print_destination_report(report: DestinationValidationReport) -> None:
    print(f"\ndestination check: expected process(es) = {report.expected_processes}")
    if report.ignored:
        print(f"  ignored (known pre-existing, unrelated to this population): {report.ignored}")
    if not report.missing and not report.extra:
        print("  OK: exact matrix present, no unexpected extras.")
        return
    if report.missing:
        print(f"  MISSING ({len(report.missing)}):")
        for rel in report.missing:
            print(f"    {rel}")
    if report.extra:
        print(f"  EXTRA/UNEXPECTED ({len(report.extra)}):")
        for rel in report.extra:
            print(f"    {rel}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Named source worktree root (repeatable), e.g. --source clean11=E:\\opencell-worktrees\\l22-full-extract",
    )
    parser.add_argument(
        "--source-scope",
        action="append",
        default=[],
        metavar="NAME=Proc1,Proc2,...",
        help="Restrict a named --source to only ever contribute to this explicit, comma-separated "
        "process allowlist (repeatable, one per source name). A source with no --source-scope entry "
        "is unrestricted -- appropriate ONLY for the implicit 'current' source. Any accepted-oracle "
        "worktree source (e.g. clean11/stale5) MUST be scoped explicitly so it can never silently "
        "supply data for a process outside its mechanically-derived accepted set.",
    )
    parser.add_argument("--processes", help="Comma-separated process allowlist; default = all 18 design_a_per_tick.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually copy resolved files into the current repo tree and write the tracked manifest. "
        "Default is dry-run/report only. Refuses to run at all unless every requested process is RESOLVED.",
    )
    parser.add_argument(
        "--check-destination",
        action="store_true",
        help="Validate the current repo tree's v2-layout destination directories contain EXACTLY the "
        "requested process x seed(0-49) matrix, with no missing files and no unexpected extras. Runs "
        "standalone (read-only, reports current state) unless combined with --apply, in which case it "
        "runs AFTER the copy to confirm the result. Exits nonzero if the check fails.",
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
        sources.append(SourceRoot(name=name, path=Path(_maybe_translate_windows_path(path_str))))

    scopes: dict[str, frozenset[str]] = {}
    for raw in args.source_scope:
        if "=" not in raw:
            parser.error(f"--source-scope must be NAME=Proc1,Proc2,..., got {raw!r}")
        name, _, procs_str = raw.partition("=")
        if name not in seen_names:
            parser.error(f"--source-scope refers to unknown source name {name!r}; declare it with --source first")
        if name in scopes:
            parser.error(f"--source-scope given more than once for {name!r}")
        wanted_procs = frozenset(p.strip() for p in procs_str.split(",") if p.strip())
        if not wanted_procs:
            parser.error(f"--source-scope for {name!r} must list at least one process")
        scopes[name] = wanted_procs
    if scopes:
        sources = [
            SourceRoot(name=s.name, path=s.path, allowed_processes=scopes.get(s.name))
            for s in sources
        ]

    entries = design_a_per_tick_processes()
    if args.processes:
        wanted = {p.strip() for p in args.processes.split(",") if p.strip()}
        unknown = wanted - set(entries)
        if unknown:
            parser.error(f"unknown/non-design_a_per_tick process(es): {sorted(unknown)}")
        entries = {name: e for name, e in entries.items() if name in wanted}

    reports = evaluate_all(sources, entries)
    _print_report(reports, sources)

    if args.check_destination and not args.apply:
        # Standalone/read-only: report current destination state for the
        # requested process set without requiring resolution or copying.
        dest_report = validate_destination(cat.REPO_ROOT / KARR_NATIVE_SUBDIR, frozenset(entries))
        _print_destination_report(dest_report)
        return 0 if dest_report.ok else 1

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

    if args.check_destination:
        dest_report = validate_destination(cat.REPO_ROOT / KARR_NATIVE_SUBDIR, frozenset(entries))
        _print_destination_report(dest_report)
        if not dest_report.ok:
            print("\nPost-apply destination check FAILED -- see EXTRA/MISSING above.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
