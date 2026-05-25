# Track-A2 RESCUE — validate uncommitted L2 enrollment diff, commit if green

You are resuming work in worktree `E:\opencell-worktrees\track-a2` (branch
`track-a/L2-enrollment`). A prior Codex session died on an Azure compaction
API error AFTER authoring code but BEFORE committing it. Your job is narrow:
**validate the existing uncommitted diff, commit it in logical chunks if green,
stop if red**. Do NOT expand scope.

## Environment & failure-mode contract (read first)

### Tool availability
You are on Windows-with-WSL. Check `command -v <tool>` before invoking
ripgrep/fd/jq/gh. Fall back to grep/find/python-json/git+curl if missing.
A missing tool is not a reason to abort.

### Python interpreter (CRITICAL)
This repo uses an editable install in a WSL venv. Use this exact interpreter
for ALL Python:

  CORRECT:  wsl -e bash -lc "/mnt/e/opencell/.venv-wsl/bin/python ..."
  CORRECT:  wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest ..."
  WRONG:    py -3.12 ... (Windows interpreter, will ModuleNotFoundError)
  WRONG:    python ...

If the WSL venv path differs, check `E:\opencell\BOOTSTRAP.md` or
`/mnt/e/opencell/.venv-wsl/bin/python --version`.

### Commit-or-stop semantics
Never exit silently. Always write `STATUS_a2.md` with: what you attempted,
where you got stuck (specific error + command), what fallback you tried,
what the orchestrator should do next. Partial STATUS > no STATUS.

### Commit-as-you-go (NEVER hold work uncommitted)
Commit each logical chunk the MOMENT it is green. Never hold more than one
chunk uncommitted in the working tree. If `HANDOFF_AUTO.md` appears: commit
whatever is green, write STATUS with "HANDOFF — incomplete, next step: X",
STOP.

### Token budget
Hard ceiling: **200,000 tokens**. Self-managed handoff at **75% = 150,000
tokens**. At 150k: stop new exploration, commit, write STATUS "BUDGET
CHECKPOINT", request handoff if not done. The 50k buffer is for graceful
exit, not extra work.

### Stale STATUS warning
Overwrite `STATUS_a2.md` first thing with a "rescue task started at
<timestamp>" header. Do not trust an inherited STATUS.

## Task scope (narrow)

The worktree already contains an uncommitted diff (~321 LOC across 5 source
files + 4 new integration test files) that implements L2 allocator enrollment
for Metabolism + TX/TL v3. Your job:

### Step 1: Inspect the diff (5 min)
Run:
  - `git status` — list modified + untracked files
  - `git --no-pager diff --stat` — confirm ~321 lines across 5 files
  - `git --no-pager diff opencell/vivarium/karr_request_calculators.py | head -200`
  - Skim each of the 4 new test files in `tests/integration/`:
    - `test_b1_substrate_sanity.py`
    - `test_metabolism_allocator_enrollment.py`
    - `test_transcription_allocator_enrollment.py`
    - `test_translation_allocator_enrollment.py`

Sanity-check that the diff matches the L2 enrollment scope (request
calculators for Metabolism + TX v3 + TL v3 enrolled into the request layer,
composite wired, integration tests for B1 substrate sanity + 3 per-process
enrollment tests). If it looks like the wrong scope or partial work,
write STATUS_a2.md saying so and STOP — do NOT commit.

### Step 2: Run the targeted pytest (5-10 min)
Run ONLY the 4 new integration tests, plus a sanity unit pass:

  wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest \
    tests/integration/test_b1_substrate_sanity.py \
    tests/integration/test_metabolism_allocator_enrollment.py \
    tests/integration/test_transcription_allocator_enrollment.py \
    tests/integration/test_translation_allocator_enrollment.py \
    -v --ignore=tests/gates"

Then a broader unit sanity:

  wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest \
    tests/unit -q --ignore=tests/gates"

### Step 3: Commit decision

**If all 4 new integration tests pass AND tests/unit shows no regressions
vs main HEAD (cee0d73 — expected ~355 passed, 11 skipped from the Track-B
baseline; A2 should match or add passes, not subtract them):**

Commit in 3 logical chunks (separate commits):

  Commit 1: `karr_request_calculators.py` — the new request calculator surface
    `git add opencell/vivarium/karr_request_calculators.py`
    `git commit -m "L2 enrollment: request calculator surface for Metabolism + TX v3 + TL v3"`

  Commit 2: composite wiring + process modifications
    `git add opencell/vivarium/karr_composite.py opencell/vivarium/karr_metabolism.py opencell/vivarium/karr_transcription_v3.py opencell/vivarium/karr_translation_v3.py`
    `git commit -m "L2 enrollment: wire request calculators into composite + processes"`

  Commit 3: integration tests
    `git add tests/integration/test_b1_substrate_sanity.py tests/integration/test_metabolism_allocator_enrollment.py tests/integration/test_transcription_allocator_enrollment.py tests/integration/test_translation_allocator_enrollment.py`
    `git commit -m "L2 enrollment: integration tests including B1 substrate sanity"`

Then write STATUS_a2.md with:
  - "RESCUE COMPLETE"
  - 3 commit SHAs
  - pytest summary (e.g. "4/4 integration green; tests/unit X passed, Y skipped vs baseline 355/11")
  - confirmation that test_b1_substrate_sanity_no_negative_core_substrates is now green

**If any of the 4 integration tests fail:**

Do NOT commit. Write STATUS_a2.md with:
  - "RESCUE BLOCKED — integration tests failing"
  - Exact failing test names + first 30 lines of pytest output per failure
  - Your hypothesis for the root cause (don't fix it yet — the orchestrator
    will decide whether to attempt a fix or rewrite from scratch)
  - The diff is preserved on disk for inspection.

**If tests/unit shows new failures vs the cee0d73 baseline (regression):**

Do NOT commit. Same STATUS pattern as above.

### Step 4: Do NOT proceed past Step 3.
This rescue is intentionally narrow. Do not:
  - Add more tests
  - Refactor code
  - Run the gate tests (deliberately ignored)
  - Run the full ensemble
  - Modify anything outside the existing diff

If you complete Step 3 with time/budget remaining, write STATUS with
"RESCUE COMPLETE — awaiting orchestrator next step" and stop.

## Files & paths reference
- Worktree: `E:\opencell-worktrees\track-a2`
- WSL path: `/mnt/e/opencell-worktrees/track-a2`  (verify before pytest)
- Branch: `track-a/L2-enrollment`
- Baseline HEAD on main: `cee0d73`
- Python: `/mnt/e/opencell/.venv-wsl/bin/python` (editable install of opencell)
- Status file to write: `E:\opencell-worktrees\track-a2\STATUS_a2.md`
- Codex log will be at: `E:\opencell-worktrees\track-a2\codex_a2_rescue.log`

## Exit criteria
You are done when EITHER:
  (a) STATUS_a2.md says "RESCUE COMPLETE" with 3 commit SHAs + green test summary, OR
  (b) STATUS_a2.md says "RESCUE BLOCKED" with failing-test details + nothing committed
