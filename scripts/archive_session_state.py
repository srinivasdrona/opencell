"""Archive Copilot session-state checkpoints into the repo for provenance.

Background
----------
Each interactive Copilot CLI session writes per-checkpoint markdown summaries
to ``~/.copilot/session-state/<session-id>/checkpoints/`` plus a handful of
small persistent artifacts under ``files/``. None of this is in version
control by default, so on a fresh machine the agent loses the conversational
record that explains *why* commits look the way they do.

This script snapshots the small text artifacts into the repo, leaving the
heavy ones behind (``events.jsonl`` can be 70+ MB; ``session.db`` is a
SQLite binary). The result is a navigable, diffable trail of agent
decisions alongside the code they produced.

What gets copied
----------------
- ``checkpoints/*.md``           (per-checkpoint summaries)
- ``checkpoints/index.md``       (the checkpoint index)
- ``files/*``                    (persistent agent artifacts: status docs etc.)
- ``plan.md``                    (session-local plan; copied as ``plan.snapshot.md``)

What is deliberately skipped
----------------------------
- ``events.jsonl``               (large, raw event stream)
- ``session.db``                 (binary SQLite)
- ``*.lock``                     (transient)
- ``vscode.metadata.json``       (IDE state)
- ``workspace.yaml``             (per-machine paths)

Usage
-----
::

    python scripts/archive_session_state.py                  # archive current session
    python scripts/archive_session_state.py --session-id ID  # archive a specific session
    python scripts/archive_session_state.py --all            # archive every session this project touched
    python scripts/archive_session_state.py --list           # list candidate sessions
    python scripts/archive_session_state.py --dry-run        # show what would be copied
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEST_ROOT = REPO_ROOT / "docs" / "agent_checkpoints"

INCLUDE_DIRS = ("checkpoints", "files")
INCLUDE_TOP_FILES = ("plan.md",)
SKIP_NAMES = {
    "events.jsonl",
    "session.db",
    "vscode.metadata.json",
    "workspace.yaml",
}


def session_state_root() -> Path:
    """Return ``~/.copilot/session-state`` on the current OS."""
    if os.name == "nt":
        base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    else:
        base = Path.home()
    return base / ".copilot" / "session-state"


def list_sessions(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


def workspace_matches_repo(session_dir: Path) -> bool:
    """Best-effort check: does this session's workspace.yaml point at this repo?"""
    wf = session_dir / "workspace.yaml"
    if not wf.exists():
        return False
    try:
        text = wf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    needles = (str(REPO_ROOT).lower(), str(REPO_ROOT).replace("\\", "/").lower())
    haystack = text.lower()
    return any(n in haystack for n in needles)


def discover_current_session(root: Path) -> Path | None:
    """Pick the most recently updated session whose workspace matches this repo."""
    candidates = [s for s in list_sessions(root) if workspace_matches_repo(s)]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def copy_one(src: Path, dst: Path, dry_run: bool) -> int:
    """Copy a single file. Returns 1 if copied, 0 if skipped."""
    if src.name in SKIP_NAMES or src.name.endswith(".lock"):
        return 0
    if dry_run:
        print(f"  would copy: {src.relative_to(src.parents[1])}")
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return 1


def archive_session(session_dir: Path, dry_run: bool = False) -> int:
    """Snapshot one session into ``docs/agent_checkpoints/<session-id>/``."""
    session_id = session_dir.name
    dst_dir = DEST_ROOT / session_id
    print(f"Archiving session {session_id}")
    print(f"  source: {session_dir}")
    print(f"  dest  : {dst_dir.relative_to(REPO_ROOT)}")

    copied = 0
    for sub in INCLUDE_DIRS:
        src_sub = session_dir / sub
        if not src_sub.exists():
            continue
        for src_file in src_sub.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(session_dir)
            dst_file = dst_dir / rel
            copied += copy_one(src_file, dst_file, dry_run)

    for name in INCLUDE_TOP_FILES:
        src_file = session_dir / name
        if src_file.exists() and src_file.is_file():
            # Rename to avoid confusion with repo-root plan.md
            dst_file = dst_dir / "plan.snapshot.md"
            copied += copy_one(src_file, dst_file, dry_run)

    if not dry_run:
        # Write a tiny manifest so the archive is self-describing.
        manifest = dst_dir / "ARCHIVE.md"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest.write_text(
            f"# Session archive: `{session_id}`\n\n"
            f"- Archived at: {now}\n"
            f"- Source: `{session_dir}`\n"
            f"- Files copied: {copied}\n\n"
            f"This directory is a sanitized snapshot of the Copilot CLI "
            f"session state. Large/binary artifacts (`events.jsonl`, "
            f"`session.db`) are deliberately excluded.\n",
            encoding="utf-8",
        )
    print(f"  copied: {copied} file(s)")
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--session-id", help="Archive exactly this session id")
    grp.add_argument("--all", action="store_true", help="Archive every session that touched this repo")
    grp.add_argument("--list", action="store_true", help="List candidate sessions and exit")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be copied; write nothing")
    args = parser.parse_args(argv)

    root = session_state_root()
    if not root.exists():
        print(f"No session-state directory found at {root}", file=sys.stderr)
        return 1

    if args.list:
        for s in list_sessions(root):
            mark = "*" if workspace_matches_repo(s) else " "
            mtime = datetime.fromtimestamp(s.stat().st_mtime).isoformat(timespec="seconds")
            print(f"  {mark} {s.name}  (mtime={mtime})")
        print("\n(* = workspace.yaml references this repo)")
        return 0

    if args.session_id:
        targets = [root / args.session_id]
        if not targets[0].exists():
            print(f"Session not found: {targets[0]}", file=sys.stderr)
            return 1
    elif args.all:
        targets = [s for s in list_sessions(root) if workspace_matches_repo(s)]
        if not targets:
            print("No sessions matched this repo.", file=sys.stderr)
            return 1
    else:
        current = discover_current_session(root)
        if current is None:
            print(
                "Could not auto-discover a session for this repo. "
                "Use --list to see candidates or --session-id to specify.",
                file=sys.stderr,
            )
            return 1
        targets = [current]

    total = 0
    for t in targets:
        total += archive_session(t, dry_run=args.dry_run)

    verb = "Would archive" if args.dry_run else "Archived"
    print(f"\n{verb} {total} file(s) across {len(targets)} session(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
