"""Sync the session todo DB to the canonical E drive copy.

Per the State Sync Protocol in .github/copilot-instructions.md, the E drive
DB (opencell_tasks.db) is the canonical store. The session DB used by the
agent's SQL tool can drift; this script dumps session todos+todo_deps and
replaces the canonical tables atomically (with backup).

Inputs:
  --src-json  Path to a JSON file with two top-level keys: "todos" (list of
              todo dicts), "deps" (list of {todo_id, depends_on} dicts).
  --dest      Path to opencell_tasks.db. Default: ./opencell_tasks.db

The destination DB's review_findings / review_notes tables are NEVER
touched (they have other writers).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src-json", required=True, type=Path)
    p.add_argument("--dest", type=Path, default=Path("opencell_tasks.db"))
    args = p.parse_args()

    if not args.src_json.exists():
        print(f"ERROR: {args.src_json} not found", file=sys.stderr)
        return 2
    if not args.dest.exists():
        print(f"ERROR: {args.dest} not found", file=sys.stderr)
        return 2

    payload = json.loads(args.src_json.read_text(encoding="utf-8"))
    todos = payload["todos"]
    deps = payload["deps"]

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = args.dest.with_suffix(args.dest.suffix + f".bak.{ts}")
    shutil.copy2(args.dest, backup)
    print(f"backup: {backup}")

    conn = sqlite3.connect(args.dest)
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM todo_deps")
        conn.execute("DELETE FROM todos")
        conn.executemany(
            "INSERT INTO todos (id, title, description, status, created_at, updated_at) "
            "VALUES (:id, :title, :description, :status, :created_at, :updated_at)",
            todos,
        )
        conn.executemany(
            "INSERT INTO todo_deps (todo_id, depends_on) VALUES (:todo_id, :depends_on)",
            deps,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    conn = sqlite3.connect(args.dest)
    n_t = conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
    n_d = conn.execute("SELECT COUNT(*) FROM todo_deps").fetchone()[0]
    by_s = dict(conn.execute("SELECT status, COUNT(*) FROM todos GROUP BY status").fetchall())
    conn.close()
    print(f"loaded: {n_t} todos, {n_d} deps, status={by_s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
