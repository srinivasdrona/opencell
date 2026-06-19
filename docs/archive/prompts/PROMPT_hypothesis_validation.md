# Hypothesis Validation: Alternative/Compounding Causes of Substrate Cascade

## Context (READ THIS, but don't go deep on history)

The substrate cascade (NTPs/AAs going strongly negative in chassis_v6 100-tick runs) has been attributed to 3 bugs (transcription bypass, translation bypass, metabolism producer-silence). A fix is in progress. But before that fix lands, we want to validate whether OTHER causes could be primary or compounding.

Background docs you may need (skim only, don't deep-read):
- `/mnt/e/opencell-worktrees/substrate-leak-diagnosis/data/diagnostics/*.csv` — empirical per-tick data from a 100-tick instrumented run
- `/mnt/e/opencell-worktrees/substrate-leak-diagnosis/scripts/diagnose_substrate_leak.py` — the diagnostic script itself
- `/mnt/e/opencell/opencell/vivarium/karr_composite.py` — chassis_v6 builder

## Your task: validate or refute each hypothesis with EMPIRICAL EVIDENCE

Read-only analysis. **Do not modify any non-doc files.** Write findings to `docs/hypotheses/cascade_alt_hypotheses.md`.

## Self-imposed token budget

At **100k tokens used**, STOP and execute the handoff protocol:
1. Commit whatever findings you have
2. Write `HANDOVER.md` at root with status of each hypothesis (done/partial/not-started) and next-session instruction
3. Commit and exit with `HANDOFF COMPLETE`

(You should comfortably fit all hypotheses in 50-70k tokens. The ceiling is just insurance.)

## Hypotheses to validate

### H1: Initial conditions at 1.0 are the primary cause (not just additive)

**Question**: Does the cascade manifest as a single-tick cliff (1.0 → -437.5 on tick 1) or as monotonic drift over many ticks?

**Method**:
1. Read `data/diagnostics/substrate_trajectory.csv` (or equivalent — look for per-tick substrate values) from the substrate-leak-diagnosis worktree
2. For each substrate (ATP, CTP, GTP, UTP + sample AAs), record values at tick 0, 1, 2, 5, 10, 50, 100
3. Determine: cliff vs drift

**Verdict**:
- If single-tick cliff at tick 1, then H1 is PRIMARY (fixing the bypass won't help much if pools start at 1.0 — first tick still craters)
- If smooth monotonic decline, H1 is ADDITIVE (bypass is the real driver, low initial values just shift the timing)

### H2: Substrates store is empty at initialization (vivarium accumulator behavior)

**Question**: Does `initial_state["substrates"]` actually contain all the expected wids at tick 0, or is it empty/partial?

**Method**:
1. Write a 10-line standalone script `scripts/check_initial_substrate_state.py` that:
   - Builds chassis_v6 via `build_karr_chassis_v6()`
   - Prints `composite.state.get("substrates", {})` keys and values
   - Identifies which expected wids are missing or have value != 1.0
2. Run it: `source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/hypothesis-validation && python scripts/check_initial_substrate_state.py`
3. Capture full output in the report

**Verdict**:
- If all expected wids present at 1.0: H2 REFUTED (init state is intentional, just wrong magnitude)
- If wids missing or at 0.0: H2 CONFIRMED (initial state is structurally broken; even the 1.0 default isn't applying)

### H5: A `_updater: "set"` on substrates overwrites `accumulate` deltas

**Question**: Does any process port use `"set"` updater on the `substrates` schema, which would clobber other processes' accumulate updates within a tick?

**Method**:
1. `grep -rn '"_updater"' /mnt/e/opencell/opencell/vivarium/*.py | grep -i set` to find all "set" updaters
2. Cross-reference with each line's port context (look at ~10 lines around each match) to determine which port the "set" applies to
3. Flag any "set" updater applied to a port that ultimately maps to the `substrates` store

**Verdict**:
- If found on substrates port: H5 CONFIRMED, document file:line
- If only on non-substrate ports: H5 REFUTED

### H7: chassis_v6 has double-wiring (process runs twice per tick)

**Question**: After the v3-to-canonical rename, does the engine have 28 processes (expected) or more?

**Method**:
1. Reuse the standalone script from H2 (extend it):
   - Print `sorted(composite.processes.keys())`
   - Print `len(composite.processes)`
   - Check for any keys still containing `_v3`
   - Check `composite.topology.keys()` for the same
2. Compare against `CHASSIS_V6_EXPECTED_PROCESS_KEYS` in `karr_composite.py`

**Verdict**:
- If count is 28 and no `_v3` keys: H7 REFUTED
- If count > 28 or `_v3` keys present: H7 CONFIRMED, document

### H8: Substrate wid naming mismatches across modules

**Question**: Do all modules use the same wid spelling for NTPs/AAs/H2O/etc.?

**Method**:
1. For each of these key substrates: ATP, CTP, GTP, UTP, H2O, ALA (representative AA):
   ```
   grep -rn '"ATP"\|"M_ATP"\|"atp"' /mnt/e/opencell/opencell/vivarium/karr_metabolism.py /mnt/e/opencell/opencell/vivarium/karr_transcription_v3.py /mnt/e/opencell/opencell/vivarium/karr_translation_v3.py /mnt/e/opencell/opencell/vivarium/karr_allocation_step.py /mnt/e/opencell/opencell/vivarium/karr_request_calculators.py
   ```
2. Build a small table of {file: distinct ATP-like wids used}
3. Repeat for one AA spelling (ALA, alanine, A, M_ALA) and for H2O

**Verdict**:
- If all files use identical canonical wids: H8 REFUTED
- If divergence: H8 CONFIRMED, list mismatches

## Out of scope

- **H3 (chemostat vs finite pool)** — biology interpretation, deferred
- **H4 (unit mismatch)** — deferred unless H1 is REFUTED and we need to chase magnitude
- **H6 (residual _v3 references)** — already REFUTED by the bypass-precondition audit (Pattern F clean)
- **H9 (vivarium accumulate framework test)** — deferred

## Deliverable structure

`docs/hypotheses/cascade_alt_hypotheses.md` with sections per hypothesis:

```
## H1: Initial conditions primacy
**Status**: CONFIRMED / REFUTED / INCONCLUSIVE
**Evidence**: [paste relevant CSV rows, file:line refs]
**Strategy implication**: [1-2 lines]

## H2: ... (same structure)
```

Plus a top-level summary table.

## Commit cadence

Commit after each hypothesis is fully analyzed:
- `H1 validation: <verdict>`
- `H2 validation: <verdict>`
- ... etc

Final `STATUS.md` at root: count CONFIRMED / REFUTED / INCONCLUSIVE, list top-3 strategy implications.
