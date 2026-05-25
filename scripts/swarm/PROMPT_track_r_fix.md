# Track-R-fix: Repair topology back-propagation + 1 fixture key + diagnose C1 ATP

## Context
Track-Q sweep found 51 failed + 2 errored across 7 buckets. Track-R-probe captured per-failure detail (see probe_*.log files at repo root and STATUS_r_probe.md). Three actionable clusters:

1. **TOPOLOGY (47 failures, all same root cause)**: Track-A added a `substrates_allocated` port to `karr_metabolism`. The v6 chassis builder (`build_karr_chassis_v6` in `opencell/vivarium/karr_composite.py`) got the topology-wiring update. **v2, v3, v4 builders did not.** Every engine constructed via those builders raises:
   ```
   Exception: topology for the process ('karr_metabolism',)
       at path () uses undeclared ports: {'substrates_allocated'}
   ```
2. **KEYERROR (1 failure)**: `tests/swarm/class_a_v3/test_Transcription_matches_karr.py` calls `replay_one_tick(process, fixture, tick_index)` (via `opencell/validation/replay.py:366`), which produces a `nested_state` lacking an `rna` key that `karr_transcription_v3.next_update` reads at line 171. Fixture / state-shape drift after A1 or A2 reshaped inputs.
3. **BIOLOGY_THRESHOLD diagnostic (1 failure, NOT a blind fix)**: `tests/integration/test_chassis_v6_biology_firing.py::test_c1_metabolism_dynamic_response_atp_delta_not_constant` fails with `std=0, first_delta=0, last_delta=0`. v6 engine builds fine, but ATP isn't moving. Could be: (a) test reads bulk substrate state, but post-A2 TX/TL write to `substrates_allocated` so bulk appears steady → cosmetic re-channel; (b) M1 not firing under v6 → real bug. **Your job is to DIAGNOSE, not blindly fix.** Print enough state to disambiguate; if (a) is confirmed, fix the test's read channel; if (b) is suspected, STOP and write findings to STATUS, do NOT modify M1.

## Out of scope (defer)
- `tests/probes/test_probe5_seedsequence.py::test_d2_real_different_seeds_different_output` (RNG divergence; pre-existing, not Track-A related)
- `tests/swarm/class_a_v3/test_Translation_matches_karr.py::test_Translation_matches_karr_at_tick_N` (XFAIL already, expected)

## Commit discipline preamble (mandatory)
- **Commit each cluster separately** with a clear scope-only message. Three commits maximum:
  1. `chassis: backport substrates_allocated topology wiring to v2/v3/v4 builders`
  2. `tests: fix Transcription_matches_karr replay fixture rna key`
  3. `tests: re-channel C1 ATP read to substrates_allocated` (IF cluster 3 turns out to be cosmetic)
- If cluster 3 turns out to be a real M1-firing bug, do NOT commit a M1 change. Write findings to STATUS, leave the test failing, end the session.
- After each commit, run the affected test bucket and verify it passes. If a topology fix doesn't fully clear v2/v3/v4 tests, capture the remaining failure mode in STATUS and STOP.
- If `HANDOFF_AUTO.md` appears, commit pending work as-is and STOP.

## Token budget contract
- Hard ceiling 200,000 tokens; self-managed handoff at 150,000.
- Should land under 80k. Most work is reading karr_composite.py + 1-3 test files, plus running pytest.

## Stale STATUS warning
First action: overwrite `STATUS_r_fix.md` with `# 2026-05-26T<UTC>Z track-r-fix mechanical repairs + C1 diagnostic`.

## Repo state assumptions
- Repo root: `/mnt/e/opencell` (WSL) / `E:\opencell` (Windows). Use WSL Python via `/mnt/e/opencell/.venv-wsl/bin/python` exclusively.
- HEAD should be at or descended from `240a17a`. Record HEAD; do NOT abort.
- Working tree has expected pre-session untracked artifacts and a modified `scripts/swarm/CLASS_A_TEMPLATE.md`. Do NOT abort. Only block on unstaged edits under `opencell/`, `tests/`, `pyproject.toml`, `setup.cfg`, `conftest.py` — none expected.

## CLUSTER 1: Topology back-propagation

### Investigate
Read `opencell/vivarium/karr_composite.py` and identify:
- `build_karr_chassis_v6` — find the `substrates_allocated` wiring (this is the canonical reference).
- `build_karr_chassis_v2`, `build_karr_chassis_v3`, `build_karr_chassis_v4` — find their `karr_metabolism` topology blocks.
- Also check whether there are non-v6 builders elsewhere (`grep -rn "karr_metabolism" tests/ opencell/` for test-local builders).

### Fix
For each non-v6 builder, add the same `substrates_allocated` port wiring that v6 has. **Mirror v6's path exactly** — typically wires to `("substrates_allocated",)` or similar. Do NOT invent a new path; copy from v6.

If the metabolism process declares `substrates_allocated` as a required port but the topology layer in older builders intentionally omits it (e.g., older chassis variants don't have allocator-mediated TX/TL), you have two options:
  - **Preferred**: declare the port in older topologies pointing to `("substrates_allocated",)` so the engine builds cleanly. Older chassis variants that don't use the allocator will simply not write to or read from that path.
  - **Acceptable alternative**: if the v2 chassis genuinely predates the allocator surface and adding the port would change v2 semantics, add the port AND back the store with an empty dict so v2 tests run identically to before.

### Verify
After commit 1, run:
```
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/vivarium tests/d2 tests/m1 tests/phaseE tests/integration -q --tb=line"
```

Expectation: the 47 TOPOLOGY failures should collapse to ≤ 5 residual non-topology failures (cluster 3 C1 ATP plus any independent biology issues). If residual >5 or any new failures appear, write that to STATUS and STOP — do NOT compound fixes.

## CLUSTER 2: Transcription_matches_karr KeyError 'rna'

### Investigate
Read `tests/swarm/class_a_v3/test_Transcription_matches_karr.py` and `opencell/validation/replay.py:366` (`replay_one_tick`). The `nested_state` passed to `process.next_update` lacks an `rna` key. Identify whether:
- The fixture file (likely under `tests/swarm/class_a_v3/fixtures/` or `tests/fixtures/`) shapes the state incorrectly
- `replay_one_tick` strips a key it shouldn't
- `karr_transcription_v3.next_update` line 171 expects a key shape that changed post-A1

### Fix
Identify the minimum change to make the test pass WITHOUT changing the v3 process behavior. Most likely the fixture or the replay helper needs an `rna` sub-dict with `counts` key. Do NOT modify `karr_transcription_v3.py`.

### Verify
```
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/swarm -v"
```
Expect 3 passed + 1 xfail (Translation matches_karr is intentionally xfailed).

## CLUSTER 3: C1 ATP delta=0 diagnostic

### Investigate (DO NOT fix M1)
Read `tests/integration/test_chassis_v6_biology_firing.py::test_c1_metabolism_dynamic_response_atp_delta_not_constant` (line 198-220 area). Identify:
- Which store path the test reads ATP from
- Whether that's `("substrates", "ATP")` or `("substrates_allocated", "ATP")` or some emit-channel

Add a **temporary diagnostic print** (or run a one-off Python snippet via `wsl -e bash -lc "/mnt/e/opencell/.venv-wsl/bin/python -c '...'"` that builds the v6 chassis, runs 30 ticks, and reads both `("substrates", "ATP")` AND `("substrates_allocated", "ATP")` per tick) to disambiguate:

- **Case A (cosmetic)**: substrates ATP is flat AND substrates_allocated ATP varies → the test reads the wrong channel post-A2. Fix the test to read the post-A2 surface. Commit 3 lands.
- **Case B (real biology bug)**: both channels are flat or zero → M1 not firing. Do NOT fix. Write detailed findings to STATUS (per-tick raw values, which processes did/didn't write to substrates_allocated, whether M1's update dict was empty or absent). End session. Operator will investigate.

### Verify (Case A only)
```
wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest tests/integration/test_chassis_v6_biology_firing.py -v"
```
Expect all C1/A1/A2/A3/B1/B2/D1 tests to pass.

## Final report in STATUS_r_fix.md
```
# 2026-05-26T<UTC>Z track-r-fix — COMPLETE / STOPPED

## Commits landed
- <sha> <message>
- ...

## Bucket-by-bucket pass/fail after final commit
| Bucket | Total | Passed | Failed | Errored | Wall |
| vivarium | ... |
| d2 | ... |
| m1 | ... |
| phaseE | ... |
| integration | ... |
| swarm | ... |

## Remaining failures
- <test_id>: <one-line reason>

## C1 ATP diagnostic verdict
- Case A (cosmetic, fixed) / Case B (real bug, STOPPED)
- Raw per-tick values: <table or one-line summary>
- Decision: <what to tell operator>

## Outstanding risks for morning ensemble
- <list or "none">
```

## Hard rules
- Do NOT modify `opencell/vivarium/karr_metabolism.py` or any other M1/M2/M3 process file.
- Do NOT modify `karr_transcription_v3.py` line 171 area — fix the fixture/test side instead.
- Do NOT alter port declarations on processes; only topology builders.
- Do NOT fix the probe5 RNG test (out of scope).
- Do NOT add new tests.
- Do NOT bypass commit discipline — three small commits maximum, one per cluster.
- Do NOT git push.
