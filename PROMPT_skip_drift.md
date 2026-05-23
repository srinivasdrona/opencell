# Skip-Drift Audit — Reactivate or Delete 11 Tests That Went pass→skip After Rename

You are a Codex session. Read `SESSION_CONTEXT.md` first (8 hard rules).

## Token budget
**~60k**. This is a narrow forensic + fix turn. 3 checkpoint commits expected.

## Mission

Yesterday's `naming-drift-rename` (commit `cf6a1ad`) renamed `karr_m1/m2/m3/d2_*` modules to canonical biology names (metabolism, transcription, translation, macromolecular_complexation). After that landed, full-suite counts moved:

- **Pre-rename baseline (a265de1)**: 883 pass / 9 skip / 4 xfail / 0 fail
- **Post-rename (cf6a1ad)**: 872 pass / 20 skip / 4 xfail / 0 fail
- **Post-chassis_v6 (51aac1e, current main)**: 877 pass / 20 skip / 4 xfail / 0 fail (+5 new v6 tests)

Same total (896 → 901), but 11 tests went **pass→skip**. They're now silently inert. Find which 11, decide each:
- **Reactivate** if the skip is a false-trigger (e.g., `pytest.importorskip` on a renamed module path that should now import a different module)
- **Delete** if the test was a legacy stub that genuinely no longer applies (e.g., asserts on the deprecated `karr_m1` module signature that no longer exists)
- **Document and keep skipped** if the test is intentionally parked behind a feature flag we expect to flip later (rare; needs `xfail` reason or skip reason update)

DO NOT change test semantics beyond reactivation/deletion. If you find a test whose logic is now stale (e.g., asserts old class name), update the assertion to match the canonical name and reactivate — that's part of the rename completion.

## Out of scope (DO NOT TOUCH)
- Anything in `opencell/validation/` or `scripts/phase_e*` — Phase E.1 is running concurrently in a different worktree
- `karr_composite.py`, `karr_allocation_step.py`, `karr_rna_decay.py`, `karr_host_interaction.py` — reserved for the allocation-consumer-enrollment follow-up
- Any new tests for chassis_v6 (already exist)

If your investigation surfaces the 11 skipping tests outside `tests/` (unlikely), STOP and STATUS.md.

## Investigation steps

1. Run skip-reasons report. **This is slow on 9P (~15 min)**, but it's the canonical source of truth:
   ```bash
   PYTHONPATH=. .venv-wsl/bin/pytest -q --tb=no -rs 2>&1 | tee skip_report.txt
   ```
   (Run via WSL inside the worktree, per usual chassis_v6 pattern.)

2. Parse `skip_report.txt` for the `SKIPPED` block. Categorize each by reason string.

3. Cross-reference against the rename map to identify candidates that were passing pre-rename:
   ```
   karr_m1 → karr_metabolism
   karr_m2, m2_v2, m2_v3 → karr_transcription[, _v2, _v3]
   karr_m3, m3_v2, m3_v3 → karr_translation[, _v2, _v3]
   karr_d2_real → karr_macromolecular_complexation (class KarrD2RealProcess → MacromolecularComplexationProcess)
   karr_d2_stub → karr_macromolecular_complexation_stub (class KarrD2StubProcess → ...Stub)
   ```
   Tests using `pytest.importorskip("opencell.vivarium.karr_m1")` etc. are the prime suspects.

4. For each candidate, decide: reactivate / delete / keep-with-doc.

## Acceptance criteria

After fix:
- `pytest -q --tb=no` shows **≥888 pass** (877 baseline + at least 11 reactivated), OR
- Skip count goes from 20 → 9 (matches pre-rename baseline of 9 skipped)
- Equivalent combinations of the above (some delete + some reactivate; net effect: 11 skips removed by being either passing or gone)
- Zero new failures
- xfail count stays 4 (don't promote xfails)

If a subset (e.g., 8 of 11) is reactivatable and the remaining are legitimately stale, deleting the stale ones is fine — track in STATUS.md which were reactivated vs deleted.

## Commit checkpoints (3 expected)

1. Investigation: `skip_report.txt` analyzed, hit-list documented in STATUS.md, no code changes yet → no commit (skip_report.txt is gitignored if not already)
2. Reactivation/fix batch: all reactivable tests updated → commit "skip-drift: reactivate N tests post-rename"
3. Deletion batch (if any): stale tests removed → commit "skip-drift: delete N legacy stub tests post-rename"

If only one of step 2/3 has content, ship just one commit.

## Hard rules
- Narrow pytest only on the specific test files you change in inner loop
- Full suite verify only after final checkpoint
- DO NOT touch `opencell/validation/`, `scripts/phase_e*`, the 4 reserved process modules listed above
- DO NOT add new tests — this is a hygiene turn
- If `skip_report.txt` shows ZERO tests skipping due to rename (i.e., the 11 drift is from some other cause), STOP and write findings to STATUS.md — don't guess-fix

## Acceptance for STATUS
Per-checkpoint milestones. Final tally: N reactivated, M deleted, K kept-with-updated-doc. Full-suite final counts.
