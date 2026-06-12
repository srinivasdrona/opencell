"""One-off sync: dump todos + todo_deps from this session's DB to JSON,
then invoke sync_tasks_db.py to atomically replace the canonical repo DB.

Usage: bin/oc-py.cmd scripts/_sync_session_to_repo.py
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SESSION_DB = Path(r"/mnt/c/Users/sdrona/.copilot/session-state/5c51d44b-5a9f-4b23-85ff-0fddaadf2212/session.db")
REPO_ROOT = Path("/mnt/e/opencell")
REPO_DB = REPO_ROOT / "opencell_tasks.db"
DUMP_JSON = REPO_ROOT / ".session_todos_dump.json"
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync_tasks_db.py"


def main() -> int:
    if not SESSION_DB.exists():
        print(f"ERROR: session DB not found at {SESSION_DB}", file=sys.stderr)
        return 2
    if not REPO_DB.exists():
        print(f"ERROR: repo DB not found at {REPO_DB}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(SESSION_DB)
    conn.row_factory = sqlite3.Row
    todos = [dict(r) for r in conn.execute(
        "SELECT id, title, description, status, created_at, updated_at FROM todos ORDER BY id"
    )]
    deps = [dict(r) for r in conn.execute(
        "SELECT todo_id, depends_on FROM todo_deps ORDER BY todo_id, depends_on"
    )]
    conn.close()

    payload = {"todos": todos, "deps": deps}
    DUMP_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    by_status = {}
    for t in todos:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    print(f"dumped {len(todos)} todos, {len(deps)} deps to {DUMP_JSON}")
    print(f"  status counts: {by_status}")

    print(f"running sync_tasks_db.py -> {REPO_DB}")
    res = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--src-json", str(DUMP_JSON), "--dest", str(REPO_DB)],
        capture_output=True, text=True,
    )
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return res.returncode

    DUMP_JSON.unlink()
    print(f"cleaned up {DUMP_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
