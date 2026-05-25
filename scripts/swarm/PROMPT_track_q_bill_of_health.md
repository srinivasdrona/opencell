# Track-Q: Pre-ensemble full bill-of-health test sweep

## Context
Track-A swarm just landed on `main` at HEAD `437b3b9`. Three explicit landing gates passed (unit suite 381/381, B1 substrate sanity, L3 integration spot-check) but we have not yet run the broader test universe post-merge. Before tomorrow morning's 4-seed × 32,400-tick ensemble, we want a comprehensive bill of health across every test bucket EXCEPT `tests/gates/` (those are slow scorecard-targeted G14-G18 checks that the ensemble run itself drives; running them here would burn budget for no signal).

You are running a read-only diagnostic sweep. You do not modify code unless explicitly directed below.

## Commit discipline preamble (mandatory)
- This is a diagnostic sweep, not an authoring task. The only writes you make are: STATUS_q.md (your status file), and one git commit at the end if you choose to record sweep results as a markdown summary (see Final report step).
- Never modify source files. Never modify test files. If a test fails, capture the failure; do NOT attempt a fix.
- If `HANDOFF_AUTO.md` appears, commit your STATUS as-is and STOP.

## Token budget contract
- Hard ceiling 200,000 tokens; self-managed handoff at 150,000.
- Most of your work is shelling out pytest; very little reading. You should land well under 50k.

## Stale STATUS warning
First action: overwrite `STATUS_q.md` with `# 2026-05-25T<now>Z track-q pre-ensemble bill of health` (UTC). Do not trust prior content.

## Repo state assumptions
- Repo root: `/mnt/e/opencell` (WSL) or `E:\opencell` (Windows). You're on Windows; use WSL for pytest via `/mnt/e/opencell/.venv-wsl/bin/python`.
- Current branch: `main`. HEAD should be at or descended from `437b3b9` (the Bug 6a/6b hardening). Run `git log --oneline -5` and record HEAD in STATUS; do NOT abort if HEAD is a later commit.
- Working tree may contain untracked pre-session artifacts (scripts/launch_*.ps1, PROMPT_*.md drafts, .codex_q_pid.txt, etc.) and a modified `scripts/swarm/CLASS_A_TEMPLATE.md` — these are pre-existing and EXPECTED. Do NOT abort on a dirty tree. Just record `git status --porcelain` output verbatim in STATUS for the record, then proceed.
- The ONLY condition that should make you stop is if there are unstaged modifications to files under `opencell/`, `tests/`, or `pyproject.toml` / `setup.cfg` / `conftest.py` — anything that could affect the test run itself. In that case STOP and report.

## Sweep scope and execution order
Run each bucket as a separate pytest invocation so we can attribute failures cleanly. Use this exact order (cheapest → most expensive):

1. **Unit suite** (already known green; sanity re-check):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/unit -q --tb=line"
   ```
2. **Vivarium tests**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/vivarium -q --tb=line"
   ```
3. **D2 module**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/d2 -q --tb=line"
   ```
4. **M1 module**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/m1 -q --tb=line"
   ```
5. **M2 module**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/m2 -q --tb=line"
   ```
6. **M3 module**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/m3 -q --tb=line"
   ```
7. **Probes**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/probes -q --tb=line"
   ```
8. **Provenance**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/provenance -q --tb=line"
   ```
9. **Validation**:
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/validation -q --tb=line"
   ```
10. **Swarm**:
    ```
    wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/swarm -q --tb=line"
    ```
11. **PhaseE phenotypes** (biology-relevant; may be slow):
    ```
    wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/phaseE -q --tb=line"
    ```
12. **Integration** (the bulk — 24 files; longest, run last):
    ```
    wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/integration -q --tb=line"
    ```

## Per-bucket protocol
For each bucket, capture: total tests collected, passed count, failed count, skipped count, errored count, wall time. Append to STATUS_q.md a table row.

If a bucket fails (any non-passed), do NOT stop — continue with the remaining buckets. We want the full failure picture, not the first failure. (The 3 known-green landing gates already certify nothing critical is regressed.)

For failures, capture the failing test ID + the first 5 lines of the traceback into STATUS_q.md under a "Failures" section keyed by bucket name.

## Python interpreter
WSL venv only: `/mnt/e/opencell/.venv-wsl/bin/python`. Do NOT use Windows python.

## Final report (in STATUS_q.md)
On completion, write the following structure:

```
# 2026-05-25T<UTC>Z track-q pre-ensemble bill of health — COMPLETE

## Summary
| Bucket | Collected | Passed | Failed | Skipped | Errored | Wall |
|---|---|---|---|---|---|---|
| unit | ... | ... | ... | ... | ... | ... |
| vivarium | ... |
| d2 | ... |
| m1 | ... |
| m2 | ... |
| m3 | ... |
| probes | ... |
| provenance | ... |
| validation | ... |
| swarm | ... |
| phaseE | ... |
| integration | ... |
| **TOTAL** | sum | sum | sum | sum | sum | total |

## Verdict
- ENSEMBLE READY: <yes/no with reason>
- Critical failures (block ensemble): <list or "none">
- Cosmetic/known-broken failures (do not block): <list or "none">

## Failure detail
### <bucket-name>
- `<test_id>`: <first 5 lines of traceback>
...
```

## What you do NOT do
- Do NOT modify source files.
- Do NOT modify test files.
- Do NOT skip buckets to save time.
- Do NOT run `tests/gates/` (excluded by design).
- Do NOT attempt to fix any failure you find.
- Do NOT push to remote.

## Verdict criteria
- ENSEMBLE READY = yes if: zero unexpected failures in unit/vivarium/m1/m2/m3/d2/integration; phaseE/swarm/validation/provenance/probes may have known-shaped skips but no new failures vs the bug6a/6b harden lineage.
- ENSEMBLE READY = no if: any test that ran green at HEAD `2151d35` now fails at `437b3b9`, or any biology-firing test (`test_chassis_v6_biology_firing.py`, `tests/swarm/class_a_v3/test_Transcription_biology_fires.py`, `tests/swarm/class_a_v3/test_Translation_biology_fires.py`) fails.

Treat the verdict as advisory; the operator makes the final ensemble go/no-go call after reading your STATUS.
