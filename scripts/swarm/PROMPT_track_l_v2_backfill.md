# Track-L (v2) — LLM Interaction Log Retrospective Backfill (hardened)

You are running in worktree `E:\opencell-worktrees\llm-log-backfill` (branch
`track-l/log-backfill`). A prior Codex session on this branch died on a
context-overflow compaction error because it tried to ingest 14 MB of
transcripts up-front. Your job is to append **10-15 retrospective entries**
to `data/provenance/llm_interactions.jsonl` covering the May 8-25 work
period, using **grep-only source probing** and **commit-per-batch discipline**.

## Environment & failure-mode contract (read first)

### Tool availability
Windows-with-WSL. Check `command -v <tool>` before invoking rg/fd/jq/gh;
fall back to grep/find/python-json/git+curl. A missing tool is not abort.

### Python interpreter (CRITICAL)
Use the WSL venv ONLY for any Python (including the log CLI):
  CORRECT:  wsl -e bash -lc "/mnt/e/opencell/.venv-wsl/bin/python /mnt/e/opencell/scripts/log_llm_interaction.py ..."
  WRONG:    py -3.12 ...
  WRONG:    python ...

### Commit-or-stop semantics
Always write `STATUS_l.md` before exiting, even on failure: what you
attempted, where you got stuck (specific error + command), fallback tried,
what orchestrator should do next. Partial STATUS > no STATUS.

### Commit-as-you-go (NEVER hold work uncommitted)
After EVERY batch of 3-5 entries: `git add data/provenance/llm_interactions.jsonl`
and `git commit -m "track-l: batch N — <theme>"`. Do NOT accumulate more
than one uncommitted batch. If `HANDOFF_AUTO.md` appears: commit current
batch, write STATUS "HANDOFF — N entries written, next theme: X", STOP.

### Token budget (HARD)
Hard ceiling: **200,000 tokens**. Self-managed handoff at **75% = 150,000
tokens**. At 150k: commit current batch, write STATUS "BUDGET CHECKPOINT
at <token count> — N/15 entries written, next theme: X", stop. The 50k
buffer between 150k and 200k is for graceful exit, not extra work.

**Critical discipline for THIS task**: source files are huge (14 MB each).
Do NOT use `Get-Content -Raw`, `cat`, or any whole-file read. Use ONLY:
  - `grep -n "<pattern>" <file> | head -50`
  - `sed -n '<start>,<end>p' <file>` (after grep finds line numbers)
  - `head -200 <file>` / `tail -200 <file>` for skim
A single whole-file read of p9.md will burn ~40k+ tokens. Don't do it.

### Stale STATUS warning
Overwrite `STATUS_l.md` first thing with a "task started at <timestamp>"
header. Don't trust an inherited STATUS.

## Task scope (narrow)

### What exists today
`E:\opencell\data\provenance\llm_interactions.jsonl` has only 2 entries
despite 3 weeks of dense LLM-collaborative work. We have logging
infrastructure (`scripts/log_llm_interaction.py` CLI + schema) but
discipline gaps left the log nearly empty. This task backfills the
biggest themes RETROSPECTIVELY — entries get `verification_status:
"retrospective_inferred"` to mark that they were reconstructed after
the fact, not logged live.

### Sources (probe with grep, never read whole)
PRIMARY (this session, freshest, most relevant — the only transcript you need):
  - `E:\opencell_p9.md` — 14 MB, session 5c51d44b through 2026-05-25

REFERENCE (small, safe to read in full):
  - `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` — cross-project decision log
  - `E:\opencell\plan.md` — current plan, Phase-5 M-table at lines 214-368
  - `E:\opencell\docs\llm_log_design.md` — entry schema
  - `E:\opencell\docs\llm_log_tag_vocabulary.md` — tag conventions

Do NOT open `opencell_p7.md` or `opencell_p8.md`. p9 + DECISIONS + plan +
design docs is the complete source set. If a theme isn't traceable from
those, skip it — don't widen the source set.

### CLI invocation
The log writer is invoked as (verify path with `--help` first):
```
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/python \
  scripts/log_llm_interaction.py \
  --role <role> \
  --task-summary '<1-line>' \
  --output-summary '<1-line>' \
  --timestamp '<ISO 8601 with offset>' \
  --session-id 5c51d44b-5a9f-4b23-85ff-0fddaadf2212 \
  --linked-commits '<csv of short shas>' \
  --tags '<csv: topic:X,decision:Y,phase:Z>' \
  --verification-status retrospective_inferred"
```

Run `--help` first to confirm the exact flag names and the
`retrospective_inferred` enum value before bulk-writing.

## Workflow (chunked, committable)

### Batch 1: setup + sanity (one entry, prove the pipeline works)
1. Read `docs/llm_log_design.md` + `docs/llm_log_tag_vocabulary.md` (small files, safe).
2. Run the CLI with `--help` to confirm flag names.
3. Tail the existing 2 entries to confirm format:
   `wsl -e bash -lc "tail -3 /mnt/e/opencell/data/provenance/llm_interactions.jsonl"`
4. Write ONE retrospective entry covering a small, well-documented theme.
   Suggested: `phase:m1-karr-native-validation` (Apr 25 milestone, easy to
   document: per-reaction oracle median |log2|=0.96 vs Karr stored).
5. Confirm append worked: `tail -1` and verify JSON is valid.
6. **COMMIT BATCH 1.**
   `git add data/provenance/llm_interactions.jsonl && git commit -m "track-l: batch 1 — pipeline sanity entry (M1 Karr-native validation)"`

If anything goes wrong in batch 1 (CLI errors, schema rejection, etc.):
**STOP. Write STATUS_l.md with the failure and exit.** Do not proceed.

### Batch 2-4: thematic batches (3-5 entries each)

Pick themes from this priority order. For each, do a SINGLE grep probe
against `/mnt/e/opencell_p9.md` to find the relevant section (e.g.,
`grep -n "EXIT RULE" /mnt/e/opencell_p9.md | head -10`), then `sed -n`
to read only that 50-200 line window. Never load the whole file.

**Required themes (must cover at least 6):**
1. Contract taxonomy (EXIT RULE → 7-layer L0-L7) — search "EXIT RULE" or "contract taxonomy"
2. Bug 5 / Bug 6 fixes — search "Bug 5" "Bug 6" "clamped_reactions"
3. Vivarium-core chassis adoption (removed JAX) — search "Vivarium" or "removed JAX"
4. Karr-native M1 pivot — search "Karr-native" or "M1"
5. Swarm pilot 5-gap hardening — search "5-gap" or "swarm-pilot"
6. Fixture investigation Option B — search "Option B" or "fixture pipeline"

**Failure-mode themes (must cover at least 3):**
7. Karr Cloudflare detour (Codex spent 30 min on wrong source) — search "Cloudflare"
8. Stale-STATUS inheritance silent failure — search "stale STATUS" or "TASK COMPLETE"
9. Track-A2/L compaction death (today's lesson) — search "compaction" or "high demand"
10. JAX removal lesson (numpy faster at our scale) — search "JAX" "removed"

**Methodology themes (cover 2-3):**
11. Codex prompt template v2 (commit discipline + budget contract) — TODAY
12. Detached background launches survive session restart — search "detached"
13. Per-worktree fanout for parallel PRs — search "worktree" or "fanout"

**For each batch:**
1. Pick 3-5 adjacent themes (e.g. all biology themes together, all failure themes together).
2. For each, ONE grep probe → ONE sed window-read → write ONE log CLI call.
3. After 3-5 entries: `git add` + `git commit -m "track-l: batch N — <theme group>"`.
4. **Then** check token usage. If approaching 150k, write STATUS "BUDGET
   CHECKPOINT at <count> — N entries written, next theme: X" and STOP.

### Acceptance criteria
You are done when EITHER:
  (a) 10-15 entries are committed across multiple batches; STATUS_l.md says
      "BACKFILL COMPLETE — N entries (X required-themes + Y failure-themes + Z methodology)";
  (b) Budget hit at 150k with N < 10 entries committed; STATUS_l.md says
      "BUDGET CHECKPOINT at <count> — N entries committed, next batch: <theme list>";
  (c) Batch 1 failed; STATUS_l.md says "BLOCKED — <failure detail>", no commits.

### What NOT to do
- Do NOT open p7.md or p8.md. p9 is the only transcript source.
- Do NOT use `Get-Content -Raw` or `cat <full-file>` on p9.
- Do NOT write more than 5 entries before committing.
- Do NOT exceed 15 entries (this is intentional scope cap; backfill more later).
- Do NOT modify any code, tests, or docs other than `data/provenance/llm_interactions.jsonl`.
- Do NOT verify the entries' *content* against runtime behavior — these are
  retrospective, marked as such. Source-grounded in p9 / DECISIONS is enough.

## Paths reference
- Worktree: `E:\opencell-worktrees\llm-log-backfill`
- WSL path: `/mnt/e/opencell-worktrees/llm-log-backfill`
- Branch: `track-l/log-backfill`
- Python: `/mnt/e/opencell/.venv-wsl/bin/python`
- Status file: `E:\opencell-worktrees\llm-log-backfill\STATUS_l.md`
- Log file (Codex's own log): will be at `codex_l_v2.log`
- Target JSONL: `data/provenance/llm_interactions.jsonl`
- Session id: `5c51d44b-5a9f-4b23-85ff-0fddaadf2212`
