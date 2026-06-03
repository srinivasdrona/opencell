# APM-L22 — APM-Codex working directory for L2.2

This directory is the workspace of an APM-class codex agent (the "X2" operating
model) running the L2.2 composition harness workstream. It is scoped to L2.2
only. After the L2.2 retro is curated, this directory should be reduced to
`RETRO.md` + the final brief index; per-work-unit briefs may be archived.

## Files

| File | Owner | Purpose |
|---|---|---|
| `LEAD_BRIEF.md` | Operator (Copilot CLI) → APM-codex | The constitutional brief. Operating model, rigor rules, success criteria, first work unit. Versioned, signed off by human operator. |
| `WORKLOG.md` | APM-codex | Append-only running log of work units, decisions, blockers, fan-out events, regressions. Read on every compaction recovery. Capped at 2000 lines per cycle (force summarization). |
| `RETRO.md` | APM-codex | One bullet per completed sub-task, written in-the-moment. Curated at end-of-L2.2 into a roadmap for L3. |
| `briefs/NNN-<slug>.md` | APM-codex | Per-work-unit DBE (Document-Before-Execution) briefs. Numbered sequentially. ≤30 total budget for L2.2. |

## Glossary pointers

- **X1 / X2 / X3** — operator-codex collaboration ladder. See `LEAD_BRIEF.md` §1.
- **DBE** — Document-Before-Execution discipline. See `LEAD_BRIEF.md` §4.1.
- **CAUSE_1..7** — failure-mode taxonomy for L2.2 mismatches. See
  `../L2_2_HARNESS_DESIGN.md`.
- **D1..D4** — architectural decisions for L2.2 harness. See
  `../L2_2_HARNESS_DESIGN.md` and `../L2_2_D1_UNION_MASTER_LIST.md`.
- **Trace-hint short-circuit** — L2.1 pattern used 5× to dissolve per-process
  RED tests. See `../../../tests/vivarium/l2_replay_common.py` and the
  L2.1 sweep commits on `audit/l2-1-sweep-v2`.

## Lifecycle

1. Operator drafts `LEAD_BRIEF.md`, signs off.
2. APM-codex instantiated via `delegate-to-codex` skill, reads brief, produces
   `briefs/001-l22-scoping-recon.md`.
3. Operator audits brief 001, approves or revises.
4. APM-codex executes work units, maintains WORKLOG + RETRO + per-unit briefs.
5. Operator audits at milestones (definition in `LEAD_BRIEF.md` §3) and on
   interrupt triggers (definition in `LEAD_BRIEF.md` §6).
6. End-of-L2.2: APM-codex produces `RETRO.md` curation + L3 roadmap section.
7. Directory pruned; LEAD_BRIEF and RETRO retained as evidence.
