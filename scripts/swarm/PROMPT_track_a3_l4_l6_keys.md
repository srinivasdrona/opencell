# Track-A3: L4 Key Drift + L6 Request-Calc Fix

## Mandate
Three precise fixes in the allocator/request-calculator seam:

1. **L4: `MacromolecularComplexation` default-key drift** — allocator defaults use `d2_real`, but process and request-calculator use `karr_macromolecular_complexation`. Rename allocator default to match.
2. **L4: `ProteinDecay` default-key drift** — allocator defaults use `protein_decay_light`, but process and request-calculator use `karr_protein_decay_light`. Rename allocator default to match.
3. **L6: `MacromolecularComplexation` zero-demand-while-consuming** — `RequestCalculatorD2` returns hard-zero each tick, but the process directly consumes substrates via `delta_substrates`. Either make the calculator return non-zero demand matching observed consumption, OR refactor the process to consume only allocated amounts. Recommend the latter (matches L5 strict-zero pattern).

## Authoritative references (all merged on main)
- `opencell/validation/swarm/allocator/allocator_audit.md` — L4 hot list (lines 26-40) + L6 hot list (lines 44-50)
- `opencell/validation/swarm/consolidated/CONSOLIDATED_AUDIT_REPORT.md` — rows 7, 9, 19

## Specific file/line targets
- `opencell/vivarium/karr_allocation_step.py:67` — `d2_real` → `karr_macromolecular_complexation`
- `opencell/vivarium/karr_allocation_step.py:68` — `protein_decay_light` → `karr_protein_decay_light`
- `opencell/vivarium/karr_request_calculators.py:30-32, 61-63` — `RequestCalculatorD2` zero-demand logic
- `opencell/vivarium/karr_macromolecular_complexation.py:205-209, 236-242` — direct substrate-consumption sites

## Implementation plan

### Part 1 — L4 key renames
Trivial. Two lines in `karr_allocation_step.py`. Grep the repo for both old strings (`d2_real` and `protein_decay_light`) to make sure no other code path depends on the old keys; if it does, fix those too.

### Part 2 — L6 MacromolComplex zero-demand fix
Recommended approach: **change the process to consume from allocation, not from raw substrates** (matches strict-zero L5 pattern A1 just landed).

1. Read `karr_macromolecular_complexation.py:205-209, 236-242` to understand the current `delta_substrates` flow.
2. Add a `substrates_allocated` port read (mirroring how other allocator-enrolled processes read it).
3. Replace direct global-pool consumption with allocated-budget consumption.
4. If non-trivial: update `RequestCalculatorD2` to compute a real demand vector based on the process's expected substrate consumption. Otherwise the allocator will grant zero and the process will do nothing.

Take whichever path is least disruptive given the existing test coverage. Document the choice in the summary.

## Tests
- `tests/integration/test_allocator_key_consistency.py` — assert allocator default keys match process names for all consumers.
- `tests/integration/test_macromol_complex_allocator_path.py` — assert MacromolComplex respects allocated budget (no consumption when allocated=0).

Run existing test suite:
```
py -3.12 -m pytest tests/unit -q --ignore=tests/gates
```
Must remain green.

## Self-grading
Write `opencell/validation/track_a/a3_key_drift_request_calc_summary.md`:
- Two key-rename diffs (file:line, before/after)
- MacromolComplex approach chosen (process-side or calc-side) + rationale
- Test names + assertions
- Any other allocator default keys that drift from process names (sweep for completeness)

## Commit discipline
- Branch: `track-a/L4-L6-keys-request` (worktree `E:\opencell-worktrees\track-a3`).
- Commits:
  1. `track-a3: fix L4 default-key drift (d2_real, protein_decay_light)`
  2. `track-a3: fix L6 MacromolComplex zero-demand-while-consuming path`
  3. `track-a3: integration tests for allocator key consistency + MacromolComplex contract`

## Python interpreter
**Use `py -3.12`** for all pytest invocations.

## Budget
- Token budget: 180k with compaction at 75%.
- This is the smallest A-PR. If you finish under 100k, sweep for any other L4 key drifts (e.g. `karr_replication` vs `replication_real`-style mismatches) and fix them.

## Scope discipline
- Do not touch L5 helpers (A1 done).
- Do not enroll new processes (A2 territory).
- Do not change resource vectors (A4 territory).
- Stay in `karr_allocation_step.py` + `karr_request_calculators.py` + the two named process files.
