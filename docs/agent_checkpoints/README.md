# Agent Checkpoints

This directory archives sanitized snapshots of Copilot CLI session state so
that the conversational and decision context behind each commit survives
beyond the original developer machine.

## What lives here

Each subdirectory is a single session, named by its session id, e.g.:

```
docs/agent_checkpoints/5c51d44b-5a9f-4b23-85ff-0fddaadf2212/
    ARCHIVE.md             ← when/where this was snapshotted
    checkpoints/
        001-...md
        002-...md
        ...
        index.md
    files/                 ← persistent agent artifacts (status docs, etc.)
    plan.snapshot.md       ← session-local plan.md at archive time
```

## What is deliberately excluded

- `events.jsonl` (raw event stream, can be 70+ MB)
- `session.db` (binary SQLite of session DB)
- `*.lock`, `vscode.metadata.json`, `workspace.yaml` (transient / per-machine)

## How to refresh

```bash
# Inside the activated venv:
python scripts/archive_session_state.py            # current session
python scripts/archive_session_state.py --all      # every session that touched this repo
python scripts/archive_session_state.py --list     # candidates
python scripts/archive_session_state.py --dry-run  # preview
```

Typical cadence: at end of session, or after a checkpoint that mattered
(major BLOCKER resolved, design rework completed, gate closed). Commit the
result alongside the related code change so the trail is one merge away
from the production commit.

## Why this matters

Without these archives, the only durable record on a fresh machine is
`plan.md` + `SESSION_CONTEXT.md`. Those capture *what was decided* but not
the reasoning chains, bug-pattern derivations, or cross-model critiques
that led to each decision. Mining the checkpoint summaries can recover
the latter when needed — e.g., to write a methods paper, audit a wrong
turn, or onboard a future contributor.
