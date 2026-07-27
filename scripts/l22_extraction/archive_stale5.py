"""Archive manifest for the five canonical seed-0 `.mat` files superseded by
the `regenerate-stale-l22-seed-zero` decision (2026-07-28).

Before any of ProteinDecay/ProteinFolding/ProteinProcessingII/RNADecay/
RNAProcessing's canonical `per_process_traces_v2/<Process>_100ticks.mat` is
overwritten, this records durable evidence about the file being replaced:
SHA256, size, original mtime, and everything we can honestly determine about
the extractor/source/MATLAB version that produced it. Raw `.mat` bytes are
never committed (they stay under the gitignored `artifacts/` tree, per
existing convention); only this JSON/markdown evidence is tracked.

Usage (WSL only, per project convention):
    bin\\oc-py scripts/l22_extraction/archive_stale5.py --out <path.json>
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

from scripts.l22_extraction.launcher import EXTRACTOR_SCRIPT, canonical_seed0_path, matlab_version_probe  # noqa: E402
from scripts.l22_extraction.seed0_regen import STALE5_PROCESSES  # noqa: E402
from scripts.l22_extraction.trace_validation import sha256_file  # noqa: E402

ARCHIVE_DIR = REPO_ROOT / "artifacts" / "l22_stale5_regen" / "archive_old_seed0"

# This script is executed under WSL (per project convention: "Never invoke
# python or pytest directly from a PowerShell prompt"), so `Path` operations
# see the Linux filesystem view. A bare Windows-style root like `E:\opencell`
# is not a valid path there -- it is treated as one opaque path segment and
# silently fails to resolve. Mirror the candidate-root fallback pattern
# already used elsewhere in this codebase (see
# tests/vivarium/_l2_2_design_a_runner_helpers.py, e.g. lines ~124-125,
# ~998-999) so this script also works if ever run natively on Windows.
_PRIMARY_CHECKOUT_CANDIDATES = (
    Path("/mnt/e/opencell"),
    Path(r"E:\opencell"),
    Path("E:/opencell"),
)


def _resolve_primary_checkout_root() -> Path:
    for candidate in _PRIMARY_CHECKOUT_CANDIDATES:
        if candidate.exists():
            return candidate
    # None exist -- return the WSL-mount candidate anyway so downstream
    # per-file checks produce an honest "file not found" rather than a
    # mangled path, and so behavior is deterministic in tests/sandboxes
    # where neither candidate is present.
    return _PRIMARY_CHECKOUT_CANDIDATES[0]


_MATLAB_EXE_CANDIDATES = (
    Path("/mnt/e/MATLAB/bin/matlab.exe"),
    Path(r"E:\MATLAB\bin\matlab.exe"),
)


def _resolve_matlab_exe() -> Path:
    for candidate in _MATLAB_EXE_CANDIDATES:
        if candidate.exists():
            return candidate
    return _MATLAB_EXE_CANDIDATES[0]

# The commit that introduced extract_per_process_traces_v2.m and whose
# pick_snapshot_properties() allowlist was still in effect for all five
# stale files (all five predate the next allowlist-changing commit,
# 2073647c on 2026-06-02). Identified by correlating each file's on-disk
# mtime against `git log --follow` on the extractor script -- NOT from any
# hash pinned at generation time (none was recorded), so this is a
# high-confidence historical inference, not a certified provenance record.
HISTORICAL_EXTRACTOR_COMMIT = "e4cd4ef31f0c090f996dac5ff7f6d2d5d3a24b45"
HISTORICAL_EXTRACTOR_COMMIT_DATE = "2026-05-29T01:13:31+05:30"
# The next commit that changed the allowlist after the stale files were
# generated (adds capital 'RNAs'); every stale file's mtime is strictly
# before this commit's date, which is the basis for the inference above.
NEXT_ALLOWLIST_COMMIT = "2073647caf93989b4fcb983bb38b0591c3812041"
NEXT_ALLOWLIST_COMMIT_DATE = "2026-06-02T17:12:52+05:30"
# The second, larger allowlist-growth commit (adds intergenicRNAs,
# signalSequenceMonomers, unfoldedComplexs, foldedComplexs).
SECOND_ALLOWLIST_COMMIT = "5c316642f37f7b785c04598f7fc9d9133d7cbf46"
SECOND_ALLOWLIST_COMMIT_DATE = "2026-06-06T16:20:39+05:30"


def _wsl_path_to_windows(path: Path) -> str:
    """Best-effort `/mnt/<drive>/...` -> `<Drive>:\\...` conversion.

    This repo's git worktrees record their `gitdir`/`commondir` pointer files
    using Windows-style paths (e.g. `E:/opencell-worktrees/.../.git`), which
    Git for Windows resolves fine but WSL's native (Linux) `git` cannot --
    it raises `fatal: not a git repository` because `/mnt/e/...` and
    `E:/...` are different strings on the same underlying tree. Only used
    as a fallback when the native `git` invocation fails for that reason.
    """
    text = str(path)
    if text.startswith("/mnt/") and len(text) > 6 and text[5] != "/":
        drive = text[5]
        rest = text[6:].lstrip("/")
        return f"{drive.upper()}:\\{rest.replace('/', chr(92))}"
    return text


def _git(args: list[str], *, cwd: Path = REPO_ROOT) -> str:
    proc = subprocess.run(  # noqa: S603
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if proc.returncode == 0:
        return proc.stdout.strip()
    if "not a git repository" in (proc.stderr or ""):
        # Fallback: invoke Git for Windows (reachable via WSL interop) with
        # a Windows-style working directory, which correctly resolves this
        # worktree's Windows-style gitdir/commondir pointer files.
        win_cwd = _wsl_path_to_windows(cwd)
        proc2 = subprocess.run(  # noqa: S603
            ["git.exe", "-C", win_cwd, *args], capture_output=True, text=True, check=True
        )
        return proc2.stdout.strip()
    raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)


def _historical_extractor_blob_sha1() -> str | None:
    try:
        return _git(["rev-parse", f"{HISTORICAL_EXTRACTOR_COMMIT}:scripts/matlab/extract_per_process_traces_v2.m"])
    except subprocess.CalledProcessError:
        return None


def _current_extractor_blob_sha1() -> str | None:
    try:
        return _git(["rev-parse", "HEAD:scripts/matlab/extract_per_process_traces_v2.m"])
    except subprocess.CalledProcessError:
        return None


def build_archive_manifest(
    *,
    primary_checkout_root: Path | None = None,
    archive_dir: Path = ARCHIVE_DIR,
    probe_matlab: bool = True,
) -> dict[str, Any]:
    if primary_checkout_root is None:
        primary_checkout_root = _resolve_primary_checkout_root()
    entries: dict[str, Any] = {}
    for process in STALE5_PROCESSES:
        primary_path = primary_checkout_root / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2" / f"{process}_100ticks.mat"
        archived_path = archive_dir / f"{process}_100ticks.mat"
        entry: dict[str, Any] = {
            "primary_checkout_path": str(primary_path),
            "archived_copy_path": str(archived_path),
        }
        for label, path in (("primary_checkout", primary_path), ("archived_copy", archived_path)):
            if path.exists():
                stat = path.stat()
                entry[label] = {
                    "sha256": sha256_file(path),
                    "size_bytes": stat.st_size,
                    "original_mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                }
            else:
                entry[label] = {"error": f"file not found: {path}"}
        if (
            "sha256" in entry.get("primary_checkout", {})
            and "sha256" in entry.get("archived_copy", {})
        ):
            entry["archive_matches_primary"] = (
                entry["primary_checkout"]["sha256"] == entry["archived_copy"]["sha256"]
            )
        entries[process] = entry

    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "decision_reference": {
            "slug": "regenerate-stale-l22-seed-zero",
            "log": r"D:\OneDrive - Microsoft\.pm-os\DECISIONS.md",
            "date": "2026-07-28",
            "source": "session 5c51d44b-5a9f-4b23-85ff-0fddaadf2212; Opus 4.8 independent adjudication",
        },
        "old_files": entries,
        "extractor_provenance": {
            "current_extractor_path": str(EXTRACTOR_SCRIPT),
            "current_extractor_blob_sha1_git": _current_extractor_blob_sha1(),
            "historical_extractor_commit_inferred": {
                "commit": HISTORICAL_EXTRACTOR_COMMIT,
                "commit_date": HISTORICAL_EXTRACTOR_COMMIT_DATE,
                "blob_sha1_git": _historical_extractor_blob_sha1(),
                "confidence": "high, inferred from mtime correlation -- NOT a hash pinned at generation time",
                "method": (
                    "All five stale files' on-disk mtimes (2026-05-29 01:18-01:20 and "
                    "2026-05-30 07:16/14:57) fall strictly between this commit's date "
                    "(2026-05-29 01:13:31, the commit that introduced "
                    "extract_per_process_traces_v2.m) and the next allowlist-changing "
                    "commit's date (2026-06-02 17:12:52). No extractor-version hash was "
                    "recorded at generation time; this is the best available historical "
                    "inference, stated explicitly as such, not a fabricated certainty."
                ),
            },
            "next_allowlist_changing_commits": [
                {
                    "commit": NEXT_ALLOWLIST_COMMIT,
                    "date": NEXT_ALLOWLIST_COMMIT_DATE,
                    "change": "adds capital 'RNAs' to pick_snapshot_properties allowlist",
                },
                {
                    "commit": SECOND_ALLOWLIST_COMMIT,
                    "date": SECOND_ALLOWLIST_COMMIT_DATE,
                    "change": (
                        "adds 'intergenicRNAs', 'signalSequenceMonomers', "
                        "'unfoldedComplexs', 'foldedComplexs' (+7 other props) to "
                        "pick_snapshot_properties allowlist"
                    ),
                },
            ],
        },
        "wholecell_source_tree_identity": {
            "strategy": (
                "data/m1_sources/WholeCell/ is gitignored and untracked; no hash of the "
                "tree that produced the May 2026 stale files was ever recorded, so its "
                "exact historical identity is UNKNOWABLE from this repository -- stated "
                "explicitly rather than fabricated. What CAN be verified: the tree copied "
                "into this worktree for the regeneration run (below) is byte-identical to "
                "the primary checkout's current tree at copy time, so all five processes' "
                "seed 0 and seeds 1-49 in this regeneration share one single source tree."
            ),
            "current_tree_root_this_worktree": str(REPO_ROOT / "data" / "m1_sources" / "WholeCell"),
            "current_tree_root_primary_checkout": str(primary_checkout_root / "data" / "m1_sources" / "WholeCell"),
        },
        "matlab_version": {
            "probed_now": matlab_version_probe(_resolve_matlab_exe()) if probe_matlab else "<not probed>",
            "historical_note": (
                "No per-run MATLAB version was recorded when the stale files were "
                "generated (May 2026). Every dated project record from that period "
                "(docs/phase_f, docs/agent_checkpoints, MULTISEED_PILOT_REPORT.md) "
                "references exactly one MATLAB install on this host: "
                "E:\\MATLAB\\bin\\matlab.exe, R2026a (trial license). No evidence of any "
                "other MATLAB version or install ever being used for this project exists "
                "in the repository. This is a strong circumstantial match, not a recorded "
                "pin -- stated as such."
            ),
        },
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-matlab-probe", action="store_true", help="Skip the (slow) MATLAB version probe.")
    args = parser.parse_args(argv)

    manifest = build_archive_manifest(probe_matlab=not args.no_matlab_probe)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"[archive_stale5] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
