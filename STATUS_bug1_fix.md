# STATUS bug1 fix

## Approach chosen
Option (a), with branch-state clarification:
- In this worktree's `HEAD`, TX/TL were already not marked as Steps and TX/TL flow deps on `karr_allocation_step` were already absent.
- I completed the remaining low-risk alignment by restoring canonical process-name rebinding for the renamed TX/TL wrappers.
- I did **not** apply option (d), because no ordering/runtime breakage evidence appeared after test execution.

## Exact code changes (file:line)
1. `opencell/vivarium/karr_composite.py:1891`
- Added:
  - `processes[new_key].name = new_key`
- Purpose: preserve canonical process key alignment (`karr_transcription` / `karr_translation`) on the process instances after renaming from `*_v3` keys.

2. `opencell/vivarium/karr_composite.py:1893-1895`
- Added explanatory comment documenting why TX/TL must remain Processes (real dt) and not Steps (step path dispatch uses `timestep=0`).

## Flow-dependency cleanup status
- Verified TX/TL flow deps on `karr_allocation_step` are not present in this branch's `HEAD` (no additional edit needed).
- Verified `karr_observability_step` dep is retained:
  - `opencell/vivarium/karr_composite.py:1950` -> `flow["karr_observability_step"] = [("karr_allocation_step",)]`

## Diff summary
- Functional code delta is the single canonical-name assignment line in v6 wrapper remap loop.
- No Bug 2 / Bug 3 sites were touched.
- No v3 wrapper files were modified.

## Test and sanity results
1. Import sanity (WSL venv):
- Command: `/mnt/e/opencell/.venv-wsl/bin/python -c 'from opencell.vivarium.karr_composite import build_karr_chassis_v6; print("import ok")'`
- Result: `import ok`

2. v6 smoke integration:
- Command: `pytest tests/integration/test_karr_chassis_v6.py -v`
- Result: `6 passed`
- Log: `bug1_smoke.log`

3. Biology canary:
- Command: `pytest tests/integration/test_chassis_v6_biology_firing.py -v`
- Result: `2 failed, 4 passed, 1 xfailed`
- Log: `bug1_biology.log`

Per-gate outcome:
- A1: GREEN (passed)
- A2: RED (failed)
- A3: GREEN (passed)
- D1: XFAIL (did not un-xfail)
- B1: RED
- B2: GREEN
- C1: GREEN

## Biology metrics (5,000s deterministic run)
- `newly_expressed=386` (A1 evidence)
- `output_pool_increased=0` (A2 criterion)
- `mature_pool_increased=257` (translation activity observed in mature pool)
- `max_MG_469=1.8489449504652435`
- `max_MG_469_MONOMER=0.0`
- `max_oric_bound_total=0.0` (consistent with D1 xfail)
- Final core substrates: `{'AD': 0.0, 'URA': 0.0, 'ATP': -2041988.5, 'GTP': -2041909.5, 'H2O': 309737601.0}`

## Ordering observations
- No engine scheduling/runtime errors surfaced in smoke or canary runs.
- No direct evidence of allocation-ordering breakage requiring option (d) in this run.
- A2 failure appears specific to `unprocessed_counts` criterion despite mature-protein increases.

## Risks and notes
- `consumer_map` / process-name alignment is now explicitly preserved via `processes[new_key].name = new_key`.
- Requested reference artifacts were not present in this worktree at:
  - `artifacts/cascade_fix_v5/step1_verdict.md`
  - `artifacts/cascade_fix_v5/probe_1_4_engine_source_excerpt.txt`

