# Track-R-probe: Capture full failure detail for the 5 failing buckets

## Context
Track-Q sweep ran the full bill-of-health and reported 51 failed / 2 errored out of 932 tests. The summary identified a likely single root cause cluster ("undeclared ports: {'substrates_allocated'}") affecting 5 buckets, plus 2 distinct findings:
- `tests/integration/test_chassis_v6_biology_firing.py::test_c1_metabolism_dynamic_response_atp_delta_not_constant`
- `tests/swarm/class_a_v3/test_Transcription_matches_karr.py::test_Transcription_v3_matches_karr_at_tick_N` (KeyError: 'rna')

The Track-Q STATUS got overwritten by the final summary and we LOST the per-test failure detail. This Track-R-probe re-runs ONLY the 5 failing buckets with full failure capture so we can triage cleanly before any fix is attempted.

You are read-only. You do not modify any source or test files. No git commits.

## Commit discipline preamble
- Read-only diagnostic. The only writes are STATUS_r_probe.md.
- Never modify source files. Never modify test files. Never commit.
- If `HANDOFF_AUTO.md` appears, commit your STATUS as-is (text only) and STOP.

## Token budget contract
- Hard ceiling 200,000 tokens; self-managed handoff at 150,000.
- Most output is captured pytest text; should land under 60k.

## Stale STATUS warning
First action: overwrite `STATUS_r_probe.md` with `# 2026-05-26T<now>Z track-r-probe failure detail capture` (UTC).

## Repo state assumptions
- Repo root: `/mnt/e/opencell` (WSL) / `E:\opencell` (Windows). You're on Windows.
- Python interpreter: `/mnt/e/opencell/.venv-wsl/bin/python` via WSL ONLY.
- HEAD should be at or descended from `2bd631b`. Record HEAD in STATUS; do NOT abort on later commit.
- Working tree: dirty with pre-session artifacts (untracked scripts/PROMPTs, modified CLASS_A_TEMPLATE.md). This is expected. Do NOT abort. Record `git status --porcelain` then proceed.
- Only block: unstaged edits under `opencell/`, `tests/`, `pyproject.toml`, `setup.cfg`, `conftest.py`. None expected.

## Sweep scope — the 5 failing buckets, verbose
Run each bucket with `-v --tb=short --no-header` and capture FULL output to a per-bucket log file, AND emit a structured failure table into STATUS_r_probe.md.

Order (cheapest first):

1. **d2** (1 failure):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/d2 -v --tb=short --no-header 2>&1 | tee /mnt/e/opencell/probe_d2.log"
   ```
2. **m1** (2 failures):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/m1 -v --tb=short --no-header 2>&1 | tee /mnt/e/opencell/probe_m1.log"
   ```
3. **probes** (1 failure):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/probes -v --tb=short --no-header 2>&1 | tee /mnt/e/opencell/probe_probes.log"
   ```
4. **swarm** (1 failure + 1 untracked):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/swarm -v --tb=short --no-header 2>&1 | tee /mnt/e/opencell/probe_swarm.log"
   ```
5. **phaseE** (6 failures + 4 untracked):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/phaseE -v --tb=short --no-header 2>&1 | tee /mnt/e/opencell/probe_phaseE.log"
   ```
6. **vivarium** (23 failures):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/vivarium -v --tb=short --no-header 2>&1 | tee /mnt/e/opencell/probe_vivarium.log"
   ```
7. **integration** (multiple failures + 1 critical biology-firing):
   ```
   wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/integration -v --tb=short --no-header 2>&1 | tee /mnt/e/opencell/probe_integration.log"
   ```

## Final report in STATUS_r_probe.md
After all 7 runs complete (don't stop on failures — capture is the point), structure STATUS as:

```
# 2026-05-26T<UTC>Z track-r-probe — COMPLETE

## Summary
| Bucket | Total | Failed | Errored | Wall |
| d2 | ... | ... | ... | ... |
| m1 | ... |
| probes | ... |
| swarm | ... |
| phaseE | ... |
| vivarium | ... |
| integration | ... |

## Failure classification
For each failing test, list:
- test ID
- first line of traceback / error message
- proposed bucket: TOPOLOGY (undeclared ports: {'substrates_allocated'}), KEYERROR, BIOLOGY_THRESHOLD, OTHER

## Tables by failure mode
### TOPOLOGY (undeclared ports)
list test IDs, one per line

### KEYERROR
list test IDs + key that's missing

### BIOLOGY_THRESHOLD
list test IDs + actual value vs expected threshold (if visible in traceback)

### OTHER
list test IDs + one-line summary

## Per-bucket log files written
- probe_d2.log
- probe_m1.log
- probe_probes.log
- probe_swarm.log
- probe_phaseE.log
- probe_vivarium.log
- probe_integration.log

## Next-step recommendation
- Topology fix scope (one-line: which fixture file most likely needs the port added)
- Real-bug scope (one-line: C1 ATP-variance and Transcription matches_karr)
```

## What you do NOT do
- Do NOT modify source or test files.
- Do NOT git add / git commit.
- Do NOT skip any of the 7 buckets.
- Do NOT attempt to fix anything.
- Do NOT consume more than 60k tokens reading source code — the failure detail in tracebacks is enough for classification.

## Why this matters
The Track-Q summary obliterated the per-test failure detail. Without this probe, the fix track would be working blind. Capture is the entire deliverable; the per-bucket .log files are the source-of-truth artifacts.
