#!/usr/bin/env python3
"""Pre-commit guard for Copilot-authored commits."""

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


def _read_commit_message(repo_root: Path) -> str:
    msg_path = repo_root / ".git" / "COMMIT_EDITMSG"
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
    commit_message = _read_commit_message(repo_root)
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
