# Track-M v2: resume merges after manual L3 resolution

## Context
Track-M v1 merged 3/7 branches cleanly (A1 → A5 → A3), then aborted on step 4 (L3-vectors) due to a real semantic conflict against A1's L5 strict-zero contract. The operator manually resolved L3 (preserving strict-zero in `_allocated_or_state` and `_available_substrate` while keeping L3's vector-accounting additions) and committed it as merge commit `3164f7e`.

You are now resuming the merge train from step 5. Three branches remain.

## Commit discipline preamble (mandatory)
- After each `git merge --no-ff` succeeds, that merge IS the commit — proceed immediately to the next.
- Never hold uncommitted work. If a merge conflict appears, run `git merge --abort` and STOP. Do NOT attempt manual resolution.
- If `HANDOFF_AUTO.md` appears in the worktree, commit any green state and STOP with STATUS line "HANDOFF — incomplete, next: step X".

## Token budget contract
- Hard ceiling: 200,000 tokens.
- Self-managed handoff threshold: 150,000 (75%). At that point, stop and emit STATUS "BUDGET CHECKPOINT".
- 50k buffer above 150k is for graceful exit, not extra work.

## Stale STATUS warning
First action: overwrite `STATUS_m.md` with a fresh header (UTC timestamp + "track-m v2 resume run"). Do not trust any prior content.

## Repo state assumptions
- Repo root: `/mnt/e/opencell` (WSL) or `E:\opencell` (Windows). You are on Windows; use WSL for python via `/mnt/e/opencell/.venv-wsl/bin/python`.
- Current branch: `main`. Current HEAD: `3164f7e` (Merge track-a/L3-vectors into main).
- Working tree: must be clean before you start. Run `git status --porcelain` first. If non-empty, STOP with STATUS "BLOCKED — repo not clean, working tree has: <list>". Do not proceed.
- Remaining branches to merge, in order:
  1. `track-a/L2-enrollment` (tip `7f8b440` — Track-A2 rescue: direct-writer enrollment for Metabolism + TX/TL v3)
  2. `track-b/replay-fixtures` (tip `e42ba0c` — replay fixture pipeline)
  3. `track-l/log-backfill` (tip `33d3ea0` — 13 retrospective LLM-interaction JSONL entries)

## Merge protocol
For each branch in order:
1. Verify branch tip SHA matches expected (above). If mismatch, STOP with STATUS "BLOCKED — tip drift on <branch>: expected <X>, got <Y>".
2. Run `git merge --no-ff <branch> -m "Merge <branch> into main"`.
3. If conflict: `git diff --name-only --diff-filter=U`, then `git merge --abort`, then STOP with STATUS "BLOCKED — conflict at step N on <branch>: <files>". Do not attempt resolution.
4. If clean merge: log the merge commit SHA and proceed to next branch.

## Post-merge gates (only run if all 3 merges land clean)
1. **Unit suite**: `wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/unit -q --ignore=tests/gates"` — expect ≥355 passed. Record actual count.
2. **B1 substrate sanity** (was the main blocker pre-Track-A): `wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/integration/test_b1_substrate_sanity.py -v"` — must be green.
3. **Integration spot-check**: `wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/integration/test_dna_supercoiling_h2o_enrollment.py tests/integration/test_protein_translocation_full_vector.py -v"` — these were added by L3-vectors, must be green post-merge.

If any gate fails: STOP with STATUS "MERGE COMPLETE — gate regression: <gate> failed with <summary>". Do not attempt rollback.

## STATUS_m.md final report shape
On clean completion, write:
```
# Track-M v2 resume — COMPLETE
Final HEAD: <sha>
Merges landed: 3/3 (this run) + 4/4 (prior runs incl. manual L3) = 7/7 total
  - track-a/L2-enrollment -> <merge sha>
  - track-b/replay-fixtures -> <merge sha>
  - track-l/log-backfill -> <merge sha>
Gates:
  - Unit suite: <N>/<N> passed
  - B1 substrate sanity: PASSED
  - Integration spot-check (L3 tests): <N>/<N> passed
Working tree: clean
```

On any abort: write the BLOCKED line and a `Commands run:` list.

## Python interpreter
WSL venv only: `/mnt/e/opencell/.venv-wsl/bin/python`. Do NOT use Windows python.

## What you do NOT do
- Do NOT resolve any conflicts. Abort on first conflict.
- Do NOT push to remote.
- Do NOT modify any source files.
- Do NOT touch the working tree outside `git merge` and `pytest` invocations.
