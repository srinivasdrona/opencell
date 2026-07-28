"""Archive manifest for the 3x50=150 canonical/suffixed 100-tick oracle
files (DNARepair, ProteinDecay, ReplicationInitiation) superseded by the
depth-200 regeneration described in `scripts/l22_extraction/depth200_regen.py`.

`PROCESS_CATALOG.yaml` requires `M_ticks: 200` for these three processes,
but the accepted 50-seed oracle sets on disk before this task only carried
100 ticks -- a real sweep at M=200 fails with `Requested 200 ticks, but
oracle only provides 100.`. Before any of these 150 files is overwritten
in-place (`depth200_regen.relabel_seed_to_legacy_filename` literally
replaces each `<Process>_100ticks.mat` file's bytes with a fresh 200-tick
extraction under the SAME legacy filename), this records durable evidence:
SHA256, size, original mtime for every one of the 150 files, which
preserved oracle worktree each was sourced from, and the
extractor/WholeCell-source-tree identity shared by the regeneration run.

Raw `.mat` bytes are never committed (gitignored `data/m1_sources/karr_native/`,
per existing convention); only this JSON/markdown evidence is tracked.

Usage (WSL only, per project convention):
    bin\\oc-py scripts/l22_extraction/archive_depth200.py --out <path.json>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.depth200_regen import (  # noqa: E402
    DEPTH200_PROCESSES,
    legacy_path_for_seed,
)
from scripts.l22_extraction.launcher import (  # noqa: E402
    EXTRACTOR_SCRIPT,
    KARR_NATIVE_ROOT,
    matlab_version_probe,
)
from scripts.l22_extraction.trace_validation import sha256_file  # noqa: E402

ARCHIVE_DIR = REPO_ROOT / "artifacts" / "l22_depth200_regen" / "archive_old_100tick_sets"

# Which preserved oracle worktree each process's accepted 50-seed 100-tick
# set was copied from into THIS worktree (see task instructions: raw
# extraction data is gitignored per-worktree, so every worktree needs its
# own copy). Recorded explicitly per-process rather than assumed uniform,
# since ProteinDecay's source differs from the other two.
SOURCE_WORKTREE_BY_PROCESS: dict[str, str] = {
    "DNARepair": "l22-full-extract",
    "ReplicationInitiation": "l22-full-extract",
    "ProteinDecay": "l22-stale5-regen",
}

_WORKTREE_ROOT_CANDIDATES = (
    Path("/mnt/e/opencell-worktrees"),
    Path(r"E:\opencell-worktrees"),
    Path("E:/opencell-worktrees"),
)


def _resolve_worktrees_root() -> Path:
    for candidate in _WORKTREE_ROOT_CANDIDATES:
        if candidate.exists():
            return candidate
    return _WORKTREE_ROOT_CANDIDATES[0]


# This script runs under WSL (per project convention), so a bare
# `E:\MATLAB\bin\matlab.exe` (launcher.DEFAULT_MATLAB_EXE) is one opaque,
# non-existent path segment on Linux -- mirrors archive_stale5.py's own
# `_resolve_matlab_exe` fallback so the version probe actually finds the
# binary instead of always failing.
_MATLAB_EXE_CANDIDATES = (
    Path("/mnt/e/MATLAB/bin/matlab.exe"),
    Path(r"E:\MATLAB\bin\matlab.exe"),
)


def _resolve_matlab_exe() -> Path:
    for candidate in _MATLAB_EXE_CANDIDATES:
        if candidate.exists():
            return candidate
    return _MATLAB_EXE_CANDIDATES[0]


def _wsl_path_to_windows(path: Path) -> str:
    text = str(path)
    if text.startswith("/mnt/") and len(text) > 6 and text[5] != "/":
        drive = text[5]
        rest = text[6:].lstrip("/")
        return f"{drive.upper()}:\\{rest.replace('/', chr(92))}"
    return text


def _git(args: list[str], *, cwd: Path = REPO_ROOT) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    if proc.returncode == 0:
        return proc.stdout.strip()
    if "not a git repository" in (proc.stderr or ""):
        win_cwd = _wsl_path_to_windows(cwd)
        proc2 = subprocess.run(  # noqa: S603
            ["git.exe", "-C", win_cwd, *args], capture_output=True, text=True, check=True
        )
        return proc2.stdout.strip()
    raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)


def _current_extractor_blob_sha1() -> str | None:
    try:
        return _git(["rev-parse", "HEAD:scripts/matlab/extract_per_process_traces_v2.m"])
    except subprocess.CalledProcessError:
        return None


def _file_entry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"error": f"file not found: {path}"}
    stat = path.stat()
    return {
        "sha256": sha256_file(path),
        "size_bytes": stat.st_size,
        "original_mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }


def _seed_relpath(process: str, seed: int) -> Path:
    return legacy_path_for_seed(process, seed, karr_native_root=KARR_NATIVE_ROOT).relative_to(KARR_NATIVE_ROOT)


def build_archive_manifest(
    *,
    processes: tuple[str, ...] = DEPTH200_PROCESSES,
    seeds: range = range(50),
    worktrees_root: Path | None = None,
    karr_native_root: Path = KARR_NATIVE_ROOT,
    probe_matlab: bool = True,
) -> dict[str, Any]:
    if worktrees_root is None:
        worktrees_root = _resolve_worktrees_root()

    per_process: dict[str, Any] = {}
    for process in processes:
        source_worktree = SOURCE_WORKTREE_BY_PROCESS[process]
        source_root = worktrees_root / source_worktree / "data" / "m1_sources" / "karr_native"
        seeds_entry: dict[str, Any] = {}
        all_match = True
        for seed in seeds:
            rel = _seed_relpath(process, seed)
            this_worktree_path = karr_native_root / rel
            source_path = source_root / rel
            this_entry = _file_entry(this_worktree_path)
            source_entry = _file_entry(source_path)
            entry: dict[str, Any] = {
                "this_worktree_path": str(this_worktree_path),
                "source_worktree_path": str(source_path),
                "this_worktree": this_entry,
                "source_worktree": source_entry,
            }
            if "sha256" in this_entry and "sha256" in source_entry:
                matches = this_entry["sha256"] == source_entry["sha256"]
                entry["matches_source"] = matches
                if not matches:
                    all_match = False
            else:
                entry["matches_source"] = False
                all_match = False
            seeds_entry[str(seed)] = entry
        per_process[process] = {
            "source_worktree": source_worktree,
            "seed_count": len(seeds_entry),
            "all_50_present_and_match_source": all_match and len(seeds_entry) == 50,
            "seeds": seeds_entry,
        }

    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "task": {
            "description": (
                "Regenerate the 3x50 accepted 100-tick DNARepair/ProteinDecay/"
                "ReplicationInitiation oracle sets at genuine 200-tick depth "
                "(PROCESS_CATALOG.yaml M_ticks=200 for these three), keeping the "
                "legacy `_100ticks.mat` filename the loader hardcodes -- see "
                "scripts/l22_extraction/depth200_regen.py module docstring."
            ),
            "source_worktree_by_process": SOURCE_WORKTREE_BY_PROCESS,
        },
        "old_files": per_process,
        "extractor_provenance": {
            "current_extractor_path": str(EXTRACTOR_SCRIPT),
            "current_extractor_blob_sha1_git": _current_extractor_blob_sha1(),
            "note": (
                "Verified byte-identical (git diff --no-index, no output) across "
                "this worktree and both source worktrees (l22-full-extract, "
                "l22-stale5-regen) at archive time -- the extractor is a tracked "
                "file with no worktree-local modifications, so 'current' is "
                "unambiguous here (unlike the stale5 regen's untracked historical "
                "extractor, which required commit-date inference)."
            ),
        },
        "wholecell_source_tree_identity": {
            "this_worktree_tree_root": str(REPO_ROOT / "data" / "m1_sources" / "WholeCell"),
            "copied_from": str(worktrees_root / "l22-full-extract" / "data" / "m1_sources" / "WholeCell"),
            "verification": (
                "robocopy /L /E list-only diff between l22-full-extract's and "
                "l22-stale5-regen's data/m1_sources/WholeCell/ trees reported zero "
                "New/Newer/Older/EXTRA entries (859 files, 125,778,037 bytes each) "
                "before this worktree's copy was made -- both source worktrees' "
                "WholeCell trees are byte-identical, and this worktree's copy came "
                "from l22-full-extract via robocopy /E (888 files incl. subdirs "
                "beyond src/, 199.63 MB, 0 mismatches/failures reported). All "
                "150 real 200-tick extractions in this task therefore share one "
                "single WholeCell source tree, identical to both processes' "
                "original 100-tick extraction sources."
            ),
        },
        "matlab_version": {
            "probed_now": matlab_version_probe(_resolve_matlab_exe()) if probe_matlab else "<not probed>",
        },
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-matlab-probe", action="store_true")
    args = parser.parse_args(argv)

    manifest = build_archive_manifest(probe_matlab=not args.no_matlab_probe)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"[archive_depth200] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
