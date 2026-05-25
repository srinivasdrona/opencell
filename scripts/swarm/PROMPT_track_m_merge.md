# Track-M — Linear Merge of 7 Swarm Branches into main + Verification

You are running in `E:\opencell` (NOT a worktree; you operate on the main repo
directly because merges land here). Your job: merge 7 branches into `main` in
a locked order, verify the full unit suite passes, then write STATUS_m.md.

## Environment & failure-mode contract (read first)

### Tool availability
Windows-with-WSL. Check `command -v <tool>` before invoking rg/fd/jq/gh;
fall back to grep/find/python-json/git+curl. A missing tool is not abort.

### Python interpreter (CRITICAL)
Use the WSL venv ONLY for any Python (including pytest):
  CORRECT:  wsl -e bash -lc "/mnt/e/opencell/.venv-wsl/bin/python ..."
  CORRECT:  wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest ..."
  WRONG:    py -3.12 ...
  WRONG:    python ...

### Commit-or-stop semantics
Always write `STATUS_m.md` before exiting, even on failure: what you
attempted, where you got stuck (exact error + command), fallback tried,
what orchestrator should do next. Partial STATUS > no STATUS.

### Commit-as-you-go (NEVER hold work uncommitted)
Each merge IS one commit (`--no-ff` produces a merge commit). Do NOT stack
multiple merges without verification between them; do NOT abort a merge
half-resolved (`git merge --abort` and report the conflict in STATUS instead
of leaving the index in a partial state). If `HANDOFF_AUTO.md` appears in
`E:\opencell`: commit current merge if clean, write STATUS "HANDOFF —
merged N/7, next: <branch>", STOP.

### Token budget
Hard ceiling: **200,000 tokens**. Self-managed handoff at **75% = 150,000
tokens**. At 150k: commit current merge if clean, write STATUS "BUDGET
CHECKPOINT — merged N/7, next: <branch>", stop. The 50k buffer between 150k
and 200k is for graceful exit, not extra work.

### Stale STATUS warning
Overwrite `STATUS_m.md` first thing with "merge task started at <timestamp>"
header. Do not trust an inherited STATUS.

## Pre-flight checks (run before any merge)

1. Confirm you are on main and clean:
   ```
   cd E:\opencell
   git status
   git --no-pager log --oneline -1   # should show 0b4048b (plan update) or newer
   ```
   If not on main or working tree dirty, STOP and write STATUS "BLOCKED — repo not on clean main".

2. Confirm all 7 branches exist locally and their tips match:
   ```
   git --no-pager log --oneline -1 track-a/L5-strict-zero      # expect c8875db
   git --no-pager log --oneline -1 track-a/L0-tx-tl-v3-fitness # expect d2d1758
   git --no-pager log --oneline -1 track-a/L4-L6-keys-request  # expect a4d2bf4
   git --no-pager log --oneline -1 track-a/L3-vectors          # expect 44d83b4
   git --no-pager log --oneline -1 track-a/L2-enrollment       # expect 7f8b440
   git --no-pager log --oneline -1 track-b/replay-fixtures     # expect e42ba0c
   git --no-pager log --oneline -1 track-l/log-backfill        # expect 33d3ea0
   ```
   If any branch tip differs, STOP and write STATUS "BLOCKED — branch tip mismatch: <branch> shows <sha> expected <sha>".

3. Record the pre-merge baseline:
   ```
   git rev-parse HEAD > .merge_baseline_sha.txt
   ```
   (This is your rollback target if anything goes sideways.)

## Merge sequence (LOCKED ORDER — do not reorder)

For each branch in this order, execute the merge step below:

1. `track-a/L5-strict-zero`        (A1 — L5 strict-zero, no deps)
2. `track-a/L0-tx-tl-v3-fitness`   (A5 — TX/TL guards, no deps)
3. `track-a/L4-L6-keys-request`    (A3 — depends on A1)
4. `track-a/L3-vectors`            (A4 — depends on A1)
5. `track-a/L2-enrollment`         (A2 — depends on A1+A5)
6. `track-b/replay-fixtures`       (B — independent)
7. `track-l/log-backfill`          (L — independent, data-only)

### Per-merge step (apply for each branch)

```
# 1. Merge with --no-ff so a merge commit exists per layer (atomic revert)
git merge --no-ff <branch> -m "Merge <branch> into main"

# 2. Inspect result
git --no-pager log --oneline -3
git --no-pager diff --stat HEAD~1 HEAD | tail -5

# 3. If conflict: ABORT, do NOT attempt resolution. Write STATUS.
#    git merge --abort
#    STATUS_m.md: "BLOCKED — merge conflict on <branch>: <files conflicted>"
#    STOP. Do not proceed.

# 4. If clean: proceed to next branch.
```

**Do NOT push to remote.** Local only. Orchestrator will push after review.

**Do NOT run pytest between individual merges** — that would 7x the test
time. Run pytest ONCE at the end, after all 7 merges are in.

## Post-merge verification gate

After all 7 merges are in (or after as many as completed if a conflict
forced a stop):

### Gate 1: Full unit suite
```
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest \
  tests/unit -q --ignore=tests/gates 2>&1 | tail -20"
```

Expected: ≥355 passed, 11 skipped, 0 failed. Track-A2's rescue showed
354/11 in isolation, but the consolidated tree may differ — record exact
counts in STATUS regardless.

### Gate 2: B1 substrate sanity test (the original B1 blocker)
```
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest \
  tests/integration/test_b1_substrate_sanity.py -v --ignore=tests/gates 2>&1 | tail -20"
```

Expected: `test_b1_substrate_sanity_no_negative_core_substrates` passes.
This is the primary deliverable of the entire Track-A effort.

### Gate 3: Integration suite spot-check
Run the 4 new enrollment tests + replay smoke:
```
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest \
  tests/integration/test_metabolism_allocator_enrollment.py \
  tests/integration/test_transcription_allocator_enrollment.py \
  tests/integration/test_translation_allocator_enrollment.py \
  tests/integration/test_replay_fixture_loaded.py \
  -v --ignore=tests/gates 2>&1 | tail -30"
```

Expected: all pass.

### Do NOT run
- `tests/gates` — deliberately ignored (benchmarks)
- The full ensemble (`scripts/run_ensemble.py` or similar) — that's the
  next step after merge, orchestrator-gated.
- `bug 8` / `bug 9` fixes — deferred per plan.md

## Exit criteria

Write `STATUS_m.md` with one of these outcomes:

**(a) MERGE COMPLETE — all gates green**
- 7/7 branches merged (list SHAs of the 7 merge commits)
- Gate 1 (unit): X passed, Y skipped, 0 failed
- Gate 2 (B1 sanity): green
- Gate 3 (integration spot-check): green
- Final main HEAD: <sha>

**(b) MERGE COMPLETE — gate regression**
- 7/7 branches merged
- One or more gates failed
- List failing tests + first 30 lines of pytest output per failure
- Recommendation: revert to baseline `cat .merge_baseline_sha.txt` ? Or fix?

**(c) MERGE BLOCKED — conflict**
- N/7 merged (list)
- Conflict on branch <X>, files <list>
- `git merge --abort` executed
- Repo is at clean state with N successful merges in place
- Do not attempt resolution; orchestrator will decide

**(d) BUDGET CHECKPOINT**
- N/7 merged (list)
- Remaining: <list>
- Repo state: clean (N merges in, working tree clean)

## What NOT to do
- Do NOT push to remote.
- Do NOT resolve merge conflicts — abort and report.
- Do NOT skip the locked order even if it "seems fine" to reorder.
- Do NOT run gates between every merge (only at the end).
- Do NOT modify any branch or commit any new code outside the merge commits themselves.
- Do NOT update plan.md or DECISIONS.md — those are orchestrator-owned.
- Do NOT rebase — only `--no-ff` merges are authorized.

## Paths reference
- Repo: `E:\opencell` (NOT a worktree; main repo)
- WSL path: `/mnt/e/opencell`
- Python: `/mnt/e/opencell/.venv-wsl/bin/python`
- Status file: `E:\opencell\STATUS_m.md`
- Baseline SHA file: `E:\opencell\.merge_baseline_sha.txt`
- Codex log: will be at `E:\opencell\codex_m.log`
- Pre-merge main HEAD: should be `0b4048b` (plan update) — if not, STOP.
