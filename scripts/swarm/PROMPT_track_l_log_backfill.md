# Track-L1: LLM Interaction Log Backfill

## Context

You are working in worktree `E:\opencell-worktrees\llm-log-backfill` on branch
`track-l/log-backfill`. The operator (sdrona, session
`5c51d44b-5a9f-4b23-85ff-0fddaadf2212`) has spent ~3 weeks doing intensive
Copilot + Codex work on the OpenCell whole-cell simulation project. The
LLM interaction log infrastructure
(`opencell/provenance/llm_log.py`,
`scripts/log_llm_interaction.py`,
`data/provenance/llm_interactions.jsonl`)
shipped on 2026-05-22 and is mature (schema v1, append-only, content-addressed
event_ids, query CLI, controlled vocab, secrets-scrubbing, design doc).

However: **`data/provenance/llm_interactions.jsonl` currently has only 2 entries**
covering ~3 weeks and hundreds of consequential exchanges. The operator (and
the agents) have not been writing entries. This file backfills the gap so the
eventual L4 methods paper has data to draw from.

## Goal

Produce **15-30 retrospective entries** in
`data/provenance/llm_interactions.jsonl` that capture the most consequential
LLM interactions of the project to date, with explicit emphasis on:

1. **Successes**: architectural decisions, bug discoveries, design pivots
   that LLMs materially shaped.
2. **Failures** (project principle:
   *"LLM failure modes are first-class outputs. Any L-track writeup must
   document where LLMs failed, not just where they succeeded."*):
   misfires, hallucinations, reversions, fix-up sprints, EXIT-RULE triggers.
3. **Methodology patterns**: adversarial cross-model critique rounds, swarm
   pilot, layer-scoped audits, detached Codex fanout.

All entries MUST use `verification_status: retrospective_inferred` (per the
schema's `_VERIFICATION_STATUSES` enum) so they are clearly distinguishable
from real-time entries.

## Sources (read all of these, in order)

The operator has provided three categories of source material. Read everything
before drafting any entries.

### A. Primary narrative sources (richest, read in this order)

1. **`E:\opencell_p9.md`** — full Copilot CLI session transcript for the
   current session `5c51d44b-...` (~14 MB; export of THIS session).
   This is your single richest source. It covers the EXIT RULE trigger,
   contract taxonomy v1, swarm audit fanout, Track-A1..A5 planning,
   detached Codex pattern, multi-round critique, this very prompt's
   creation, and dozens of micro-decisions. Skim chronologically; you
   do not need to read every word.
2. **`E:\opencell_p8.md`** — prior session export (~14 MB, 2026-05-25 earlier).
   Covers Day 10 wrap, Sprint 0 chassis canary, swarm pilot launch,
   28-auditor fanout, GPT-5.5 critique gate.
3. **`E:\opencell_p7.md`** — earlier session (~10 MB, 2026-05-23). Covers
   Bug 5 + Bug 6 landing, the 4-seed × 32,400t ensemble that surfaced
   Bugs 1-3, the cascade-fix v5 regression discovery.
4. **`E:\opencell_p1.md` … `opencell_p6.md`** — optional, only consult
   for specific dates if other sources cite them. Total ~33 MB combined.

### B. Curated decision sources (authoritative summaries)

5. `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` — cross-project decision
   log. Each entry there is paper-grade material. Especially:
   `swarm-contract-taxonomy-v1`, `swarm-audit-before-track-a`,
   `swarm-pilot-cross-model-critique-gate`, plus any older opencell
   decisions.
6. `E:\opencell\plan.md` — the project plan with "Current Status" /
   "Prior Status" blocks dated through the project. The narrative arc
   of decisions and reversals is captured there.

### C. Design and skill artifacts

7. `E:\opencell\docs\design\*.md` — design docs (D.2 v1/v2/v3, phase E,
   release gate, critique outputs).
8. `E:\opencell\opencell\validation\swarm\consolidated\CONSOLIDATED_AUDIT_REPORT.md`
   and the per-team audit reports under `opencell/validation/swarm/`.
9. `C:\Users\sdrona\.copilot\skills\delegate-to-codex\SKILL.md` —
   has been updated multiple times this week with detached-codex pattern,
   5-gap hardening, multi-agent fanout. Each update reflects a discovered
   methodology lesson.

### D. Schema & existing entries

10. `E:\opencell\data\provenance\llm_interactions.jsonl` — the 2 existing
    entries. Mirror their structure precisely.
11. `E:\opencell\docs\llm_log_design.md` — schema rationale.
12. `E:\opencell\docs\llm_log_tag_vocabulary.md` — canonical tags + namespacing
    guidance (`topic:`, `decision:`, `phase:`, `process:`, `review:`,
    `model:`, `status:`, `option:`).
13. `E:\opencell\opencell\provenance\llm_log.py` — the dataclass, especially
    `LlmInteraction.__init__` and `_VERIFICATION_STATUSES`.
14. `E:\opencell\scripts\log_llm_interaction.py` — the CLI; use `log` subcommand.

## Concrete plan

### Step 1 — Read and inventory (1-2 hours of reading)

Read sources in the order above. As you read, maintain a working note file
`E:\opencell-worktrees\llm-log-backfill\backfill_inventory.md` (NOT committed
to main; this is your scratchpad). For each candidate entry, capture:

- approximate date (UTC offset +05:30; operator is in IST)
- model used (claude-opus-4.7, gpt-5.5, gpt-5.4, sonnet-4.6, codex variants,
  etc. — read from transcript context)
- role (`main_agent`, `sub_agent`, `critique`, `human` — the schema's roles)
- task_summary (one line)
- output_summary (3-6 lines)
- tags (namespaced per vocab doc)
- linked_artifacts (file paths)
- linked_commits (SHAs if discoverable from transcripts)
- linked_todo (todo id if mentioned)
- decision_impact (downstream consequence)
- verification_notes (what makes this credible retrospectively — usually
  a commit SHA, a merged PR, or a plan.md entry)

Aim for **15-30 entries** in your inventory. Prioritize density of
methodology lessons over completeness — pick the entries that would most
help an L4 reader understand "how was this project actually built with
LLMs".

### Step 2 — Coverage requirements (MUST include)

Your final inventory MUST cover at least these themes (one or more entries
each):

**Successes:**

- The 2026-04-24 four-round adversarial critique pivot (Phase 4 hardening,
  Vivarium chassis, JAX removal).
- Bug 5 + Bug 6 landing (protein maturation pipeline + LP writeback).
- Sprint 0 chassis canary + 3 bootstrap monitors.
- Swarm pilot launch (28 class-A auditors + seam auditors).
- Contract taxonomy v1 restructure (the EXIT RULE save).
- Track-A1 land + Track-A5 land (this session, ~2-3 hours ago).

**Failures (≥4 entries, this is a hard requirement):**

- Cascade-fix v5 self-regression: diagnosed `is_step==True → timestep=0`,
  then introduced that exact bug in the next commit (`b51819d`).
- TX/TL at timestep=0 missed by 1000t canary, surfaced only at 32,400t
  ensemble.
- Symptom-shaped "allocator-bypass" reducer cluster that triggered EXIT
  RULE (5 distinct seams collapsed into one symptom).
- Multiple Codex / Copilot environment misfires this session:
  `$(type FILE)` PowerShell-vs-cmd confusion;
  `AZURE_OPENAI_API_KEY` not propagating through `Start-Process`;
  `--full-auto` Windows sandbox death;
  `codex exec resume --last` doesn't inherit `--dangerously-bypass`;
  Python 3.14 default-shadowing pint/numpy/jax;
  `tests/gates` benchmarks site-packages shadowing.
- Karr-reference Codex v1 wasted cycles scraping simtk.org before being
  killed and relaunched with local-data prompt.
- LLM log discipline: only 2 entries in 3 weeks (THIS backfill is itself
  a failure-mode lesson — log it).

**Methodology patterns:**

- Cross-model critique gate (5.4 → 5.5 → 5.3-codex round-robin).
- Detached Codex multi-agent fanout (proven this session: A1/A5 sequential,
  then A2/A3/A4/B parallel).
- `manage_schedule` poll as session-restart-proof watcher.
- 5-gap hardening framework for prompts.
- Swarm-pilot reducer pattern + audit consolidation.

### Step 3 — Append entries (Codex's actual work)

For each inventory item, append a record using the CLI:

```powershell
py -3.12 E:\opencell\scripts\log_llm_interaction.py log \
  --role main_agent \
  --model claude-opus-4.7-1m-internal \
  --task-summary "Resolve EXIT RULE on allocator-bypass cluster" \
  --output-summary-file E:\opencell-worktrees\llm-log-backfill\summaries\swarm-contract-taxonomy.md \
  --tags "topic:swarm,decision:architecture,review:gpt-5.5,phase:audit-and-ratchet,status:resolved,model:claude-opus-4.7-1m-internal" \
  --linked-artifacts "D:/OneDrive - Microsoft/.pm-os/DECISIONS.md,E:/opencell/opencell/validation/swarm/consolidated/CONSOLIDATED_AUDIT_REPORT.md" \
  --linked-todo "bug6-track-a-min" \
  --linked-commits "ffbe5b8,0888735,5f882bc" \
  --decision-impact "Restructured Class B into 7-layer contract taxonomy; locked Track-A1..A5 at 5 layer-scoped PRs; supersedes swarm-audit-before-track-a partially" \
  --verification-status retrospective_inferred \
  --verification-notes "Decision logged in DECISIONS.md; CONSOLIDATED_AUDIT_REPORT.md in main; Track-A1+A5 landed validated" \
  --session-id "5c51d44b-5a9f-4b23-85ff-0fddaadf2212" \
  --timestamp "2026-05-25T19:30:00+05:30"
```

Notes on the CLI:

- `--output-summary-file` and `--prompt-file` accept paths and read the
  content. Use these for any summary >2 lines to keep the command line
  readable.
- Use `--timestamp` (ISO 8601 with offset) for backfilled entries — DO NOT
  default to "now". Reasonable approximations from transcript timestamps
  are fine.
- `--verification-status retrospective_inferred` is REQUIRED for all
  backfill entries.
- Use `--session-id "5c51d44b-5a9f-4b23-85ff-0fddaadf2212"` for entries
  from this session; use `null` or omit for entries from older sessions
  (the CLI will accept omission).
- `--supersedes <event_id>` is rarely applicable for backfill; only use
  if a later decision in your inventory replaces an earlier one in your
  inventory.
- Tags MUST be lowercase, comma-separated, no spaces.

Stage all per-entry output summary files under
`E:\opencell-worktrees\llm-log-backfill\summaries\<short-slug>.md` so they
are reusable and reviewable.

### Step 4 — Commit

Two commits on `track-l/log-backfill`:

1. `track-l: backfill summaries scratch` — adds the
   `summaries/<slug>.md` files only.
2. `track-l: backfill 15-30 retrospective LLM log entries` — adds the
   appended lines to `data/provenance/llm_interactions.jsonl` AND
   `backfill_inventory.md` (the audit trail of what you decided to log).

### Step 5 — Self-check

After all entries are appended, run:

```powershell
py -3.12 E:\opencell\scripts\log_llm_interaction.py query --since 2026-04-01 2>&1 | Select-Object -First 50
py -3.12 E:\opencell\scripts\log_llm_interaction.py stats
```

Confirm:

- Total entries = 2 (pre-existing) + N (your backfill).
- `retrospective_inferred` count = N.
- Tag distribution shows your namespaced tags.
- All your entries appear in the `--since 2026-04-01` query.
- Stats subcommand returns counts grouped by model/role.

Append a 10-20 line summary to
`E:\opencell-worktrees\llm-log-backfill\backfill_summary.md` covering:

- How many entries appended.
- Theme coverage (which of the required success/failure/methodology themes
  got at least one entry; flag any uncovered).
- 3-5 lessons surfaced while doing the backfill that would themselves be
  paper-worthy (meta-observation; expected since this exercise *is*
  itself an L4 data point).
- Any LLM log schema gaps you noticed that would impair future entries
  (e.g., missing field for "critique round number", "parent_event_id"
  for tree structure, etc.).
- Recommended next steps for log discipline (e.g., commit-msg hook
  investigation — operator suspects it's not firing).

## Constraints

- Use `py -3.12` for ALL python invocations. Default `python` is 3.14 and
  may break.
- Do NOT modify `opencell/provenance/llm_log.py` or
  `scripts/log_llm_interaction.py`. The schema is fine; only feed it data.
- Do NOT modify any other file under `E:\opencell\` outside of
  `data/provenance/llm_interactions.jsonl` and the worktree-local scratch
  files (`backfill_inventory.md`, `summaries/`, `backfill_summary.md`).
- Stay strictly within `E:\opencell-worktrees\llm-log-backfill\` for any
  output files. The session transcript files at `E:\opencell_p*.md` are
  read-only sources — do NOT modify them.
- DO NOT scope-creep into writing the L4 paper itself. Your output is the
  log data, not the paper.

## Definition of Done

- Branch `track-l/log-backfill` has 2 commits as above.
- `data/provenance/llm_interactions.jsonl` has gained 15-30 new lines, all
  parsing as valid JSON, all with `verification_status:
  retrospective_inferred`.
- `summaries/` contains one markdown file per logged entry (use the
  `<slug>.md` naming).
- `backfill_inventory.md` and `backfill_summary.md` exist as described.
- All 4 required failure themes are covered.
- All 6 required success themes are covered.
- All 5 required methodology patterns are covered.
- Query CLI returns the new entries cleanly under
  `--since 2026-04-01`.

## Hand-off

When done, exit cleanly. The operator (Copilot CLI session) will review
`backfill_summary.md`, scan a sample of the appended entries, and decide
whether to merge `track-l/log-backfill` into main directly or have you
iterate on coverage.
