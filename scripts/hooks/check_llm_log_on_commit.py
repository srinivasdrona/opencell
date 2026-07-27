#!/usr/bin/env python3
"""Commit-msg guard for Copilot-authored commits.

Runs as a `commit-msg` hook, not `pre-commit`: the enforcement below depends
on the commit message body (the `co-authored-by: copilot` trailer check),
and Git does not write that message to disk until the `commit-msg` phase.
A `pre-commit`-phase check has no reliable message to read -- on a repo's or
worktree's very first commit there is no prior `COMMIT_EDITMSG` at all, and
on established checkouts it would see a stale message left over from the
previous commit. `.git` is also a *file* (a gitdir pointer) in any linked
worktree, so a hardcoded `<repo_root>/.git/COMMIT_EDITMSG` path is doubly
wrong there. Staged files are still fully inspectable via `git diff --cached`
at `commit-msg` time because the commit object has not been created yet, so
moving phases does not weaken the staged-file trigger this hook depends on.

Git invokes commit-msg hooks with the message file path as $1. This script
also accepts that as its first CLI argument, falling back to
`git rev-parse --git-path COMMIT_EDITMSG` (worktree-correct, unlike a
hardcoded `.git/COMMIT_EDITMSG`) for manual/test invocation without an
argument.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.provenance.llm_log import iter_log  # noqa: E402

LOG_PATH = Path("opencell") / "provenance" / "llm_interactions.jsonl"


def _git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _resolve_commit_msg_path(argv: list[str]) -> Path:
    """Message file path: Git's $1 if provided, else the worktree-correct
    fallback for manual invocation (matches Git's own resolution, unlike a
    hardcoded `.git/COMMIT_EDITMSG`)."""
    if len(argv) > 1 and argv[1]:
        return Path(argv[1])
    return Path(_git_output("rev-parse", "--git-path", "COMMIT_EDITMSG"))


def _read_commit_message(msg_path: Path) -> str:
    if not msg_path.exists():
        return ""
    return msg_path.read_text(encoding="utf-8", errors="replace")


def _is_copilot_commit(author: str, commit_message: str) -> bool:
    if "copilot" in author.lower():
        return True
    return "co-authored-by: copilot" in commit_message.lower()


def _has_today_entry(log_path: Path) -> bool:
    today_utc = datetime.now(UTC).date().isoformat()
    for record in iter_log(log_path=log_path):
        ts = record.get("timestamp_utc")
        if isinstance(ts, str) and ts[:10] == today_utc:
            return True
    return False


def main() -> int:
    try:
        repo_root = Path(_git_output("rev-parse", "--show-toplevel"))
        staged_files = [
            line for line in _git_output("diff", "--cached", "--name-only").splitlines() if line
        ]
    except subprocess.CalledProcessError as exc:
        print(f"[llm-log-check] Unable to query git state: {exc}", file=sys.stderr)
        return 0

    if not staged_files:
        return 0

    author = os.environ.get("GIT_AUTHOR_NAME") or _git_output("config", "user.name")
    msg_path = _resolve_commit_msg_path(sys.argv)
    commit_message = _read_commit_message(msg_path)
    if not _is_copilot_commit(author, commit_message):
        return 0

    if _has_today_entry(repo_root / LOG_PATH):
        return 0

    print(
        "[llm-log-check] Copilot-linked commit detected, but no LLM log entry for today "
        f"({datetime.now(UTC).date().isoformat()}) was found in {LOG_PATH.as_posix()}.",
        file=sys.stderr,
    )
    print(
        "[llm-log-check] Add an entry with scripts/log_llm_interaction.py before committing. "
        "Bypass (not recommended): git commit --no-verify",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
