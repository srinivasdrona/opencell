# PROMPT — Substrate Cascade Fix (BLOCK-RELEASE v1.0)

## Context

OpenCell is a Python port of the Karr 2012 *M. genitalium* whole-cell model on
`vivarium-core`. The `chassis_v6` composite (28 processes) has a substrate
mass-balance failure: NTPs/AAs go strongly negative within ~100 ticks of any
integrated run.

A previous diagnostic (in worktree `substrate-leak-diagnosis`) identified the
root cause with both static analysis and a 100-tick instrumented probe.
Independent GPT-5.5 cross-check confirmed and added two secondary findings.

**Read these first**:
- `E:\opencell-worktrees\substrate-leak-diagnosis\STATUS.md`
- `E:\opencell-worktrees\substrate-leak-diagnosis\docs\diagnostics\substrate_leak_report.md`
- `E:\opencell-worktrees\substrate-leak-diagnosis\data\diagnostics\substrate_reconciliation_100t.csv`
- `E:\opencell-worktrees\substrate-leak-diagnosis\data\diagnostics\allocation_requested_vs_consumed_100t.csv`

You also have access to the same diagnostic script:
- `E:\opencell-worktrees\substrate-leak-diagnosis\scripts\diagnose_substrate_leak.py`

Use it as the verification harness for your fix.

## The contract decision (DO NOT REOPEN)

**Substrates = finite molecular pool.** This is canonical Karr biology and the
v1.0 release contract. Specifically:

- The `substrates` store holds molecule counts that must remain ≥ 0
- `karr_metabolism` (M1) is the **producer**: its FBA solution → substrate
  deltas that refill NTPs/AAs/dNTPs at biologically plausible rates
- `karr_transcription`, `karr_translation`, and all other consumers MUST go
  through `KarrAllocationStep` (request → grant → consume ≤ grant)
- Initial substrate counts must be Karr's biological initial conditions
  (~10^5-10^6 molecules), not the `1.0` placeholder

Any deviation from this contract requires you to STOP and add an OPEN QUESTION
to STATUS.md rather than guess.

## Scope of fix (3 bugs + 1 verification harness)

### Bug 1: Transcription/Translation bypass

- `karr_transcription_v3` and `karr_translation_v3` (renamed to
  `karr_transcription` / `karr_translation` in chassis_v6) write
  `{"substrates": {...}}` deltas directly via `write_substrate_deltas=True`
  default
- They are NOT enrolled in `KarrAllocationStep.consumer_processes`
- Net: ungated drain of -437.5 each NTP/tick, -894 AA/tick

**Fix**:
1. In `build_karr_chassis_v6` (`karr_composite.py` around line 1761), set
   `write_substrate_deltas=False` on both V3 processes at construction time
2. Add request calculators for NTPs (transcription demand) and AAs (translation
   demand). Look at existing `request_calculator_*` patterns in
   `karr_request_calculators.py` for the template
3. Enroll both processes in the `consumer_processes` list at v6's allocation
   step rebuild (around line 1894-1907) with proper NTP/AA wids
4. Wire `request` and `substrates_allocated` ports into their topology entries
5. Modify their `next_update` to honor `states["substrates_allocated"][self.name]`
   grants — cap synthesis by allocation, do NOT exceed grant per substrate
6. After fix, neither V3 process should emit `{"substrates": {...}}` deltas
   directly; consumption flows through allocation grants only

**Validation**: in your 100-tick canary, `karr_transcription` and
`karr_translation` should appear in the allocation requesters table with
`actual_consumed ≤ requested_amount`.

### Bug 2: Metabolism missing production side

- `karr_metabolism._static_update` returns `metabolic_reaction` updates but
  emits ZERO `{"substrates": {...}}` deltas
- The shared store has no producer; even tiny consumers (dna_repair) drain
  pools to zero

**Fix path A (preferred, biologically faithful)**:
1. In `karr_metabolism._static_update` (and `_dynamic_update` for the dynamic
   path), translate the FBA solution flux vector → substrate production deltas
2. Use the Karr stoichiometric matrix to compute per-substrate net production
   from fluxes
3. Return `update["substrates"] = {wid: +production_per_tick for wid, production_per_tick in net_production.items()}`
4. Sanity check: production rate should approximately match consumption
   rate at steady state. If FBA is solved for growth, the flux balance gives
   net production of biomass precursors

**Fix path B (fallback if A is too complex)**:
1. If the FBA→delta translation requires data you cannot find quickly (e.g.,
   the stoichiometric matrix is missing or `metabolic_reaction` rows don't map
   cleanly to substrate wids), use a **chemostat fallback**:
2. Enable `enable_pool_replenishment=True` AND make the replenishment write to
   the SHARED `substrates` store (not the internal `_sub_state`)
3. Document the fallback explicitly with a `TODO(v2): replace chemostat with
   FBA-derived production` comment
4. This is acceptable for v1.0 IF flagged

**Do not** mix paths or attempt both. Pick one, document why.

**Validation**: in 100-tick canary, `karr_metabolism` should appear with
positive (production) deltas for NTPs/AAs, not zero.

### Bug 3: Initial conditions

- All substrates initialize at `1.0` per `karr_composite.py:1424-1427`
- This is a test fixture, not biological reality

**Fix**:
1. Look up Karr's biological initial conditions. Sources to check:
   - `opencell/data/karr/` for any reference data files
   - The original Karr MATLAB code (likely in `opencell/data/karr/wholecell-matlab/` or similar)
   - `mgenitalium_params/` or any other data directory
   - Documented in `karr_metabolism.py` constants
2. Replace the `1.0` defaults with Karr's per-substrate initial counts
3. If you cannot find authoritative initial conditions in <20 minutes of
   searching, use sensible defaults (e.g., ATP=10^5, GTP=10^5, CTP/UTP=10^5,
   dNTPs=10^4, AAs=10^5 each, H2O=10^9) AND add a TODO with the gap

**Validation**: tick 0 substrate counts in your canary should be 10^4-10^6
range, not 1.0.

### Bug 4 (minor): protein_folding K/MN/NA mismatch

- `karr_protein_folding` consumes K, MN, NA in its update but its request
  calculator requests 0 for those (per
  `allocation_requested_vs_consumed_100t.csv:228-231`)

**Fix**:
1. Find the request calculator for protein_folding (in
   `karr_request_calculators.py` or similar)
2. Add K, MN, NA to the requested substrates with the same per-tick magnitude
   that the actual update consumes
3. Small fix, but include it for hygiene

## Verification harness

After the fix, run:

```bash
cd /mnt/e/opencell-worktrees/substrate-cascade-fix
source .venv-wsl/bin/activate
python scripts/diagnose_substrate_leak.py --max-ticks 100
```

(The script is already in the worktree from the diagnostic branch base.)

**100-tick PASS criteria** (all must hold):
- All substrates remain ≥ 0 at every tick
- `unattributed_delta = 0` for every substrate (no hidden mutation)
- `karr_transcription` and `karr_translation` appear in
  `allocation_requested_vs_consumed_100t.csv` with `actual_consumed ≤ requested_amount`
- `karr_metabolism` appears in `per_process_substrate_deltas_pivot.csv` with
  positive deltas (production) for NTPs and AAs
- Net summed delta per substrate is close to zero over 100 ticks (within ~10%
  of starting pool size, allowing for transient and growth dilution)

If 100-tick passes, run 500-tick:

```bash
python scripts/diagnose_substrate_leak.py --max-ticks 500
```

**500-tick PASS criteria**:
- Same as 100-tick
- Pools remain in steady-state-ish range (no runaway accumulation or depletion
  beyond a factor of ~3 from initial)

## Test suite

After all fixes, run the full test suite in WSL:

```bash
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/e/opencell-worktrees/substrate-cascade-fix && source .venv-wsl/bin/activate && python -m pytest -q --no-header 2>&1 | tail -50"
```

**Pass criteria**: 903 tests still pass (was the baseline before fix). Some
tests may need updates if they depended on the old bypass behavior — fix those
test fixtures rather than weakening assertions. If you must skip a test,
document why in STATUS.md.

## Checkpoints

Commit + write STATUS.md update after each checkpoint:

- **CP1**: Bug 1 implementation (transcription/translation enrollment). Run
  narrow tests for transcription/translation. Commit.
- **CP2**: Bug 2 implementation (metabolism production). Run narrow tests for
  metabolism. Commit.
- **CP3**: Bug 3 implementation (initial conditions). Quick smoke check that
  chassis still builds. Commit.
- **CP4**: Bug 4 (protein_folding mismatch). Commit.
- **CP5**: 100-tick canary diagnostic run. Verify all PASS criteria.
  Write summary to STATUS.md. Commit diagnostic output to `data/diagnostics/`.
- **CP6**: 500-tick canary diagnostic run. Verify all PASS criteria. Commit.
- **CP7**: Full test suite. Fix any failures. Commit.

If any checkpoint fails its PASS criteria, STOP and document what failed in
STATUS.md. Do not silently weaken criteria or skip.

## Budget

- **Token budget**: 100k
- **Wall time budget**: ~2-3 hours
- **Files expected to change**: ~6-8 files
  - `karr_composite.py` (chassis_v6 wiring)
  - `karr_transcription_v3.py` (grant-aware update)
  - `karr_translation_v3.py` (grant-aware update)
  - `karr_metabolism.py` (production side)
  - `karr_request_calculators.py` (new request calculators + protein_folding fix)
  - Initial conditions data (location TBD by your investigation)
  - Test fixture updates (if needed)

## Hard guardrails

1. **Do NOT modify the diagnostic script** to make failing PASS criteria pass.
   The diagnostic is the oracle; fix the implementation, not the test.
2. **Do NOT delete or weaken any existing test** without documenting why.
3. **Do NOT introduce new substrate stores** or aliases to work around the
   contract — substrates must remain a single shared store.
4. **Do NOT skip the 500-tick run** — 100-tick is necessary but not sufficient.
5. **Do NOT consider "all tests pass" as the conclusion**. The diagnostic
   canary IS the success criterion.

## Output

When done, write a final STATUS.md with:
1. Summary of changes per checkpoint
2. Final 100-tick and 500-tick PASS/FAIL summary (with the actual reconciliation
   numbers, not just "passed")
3. Test suite result (count passing)
4. Any OPEN QUESTIONS or TODOs left for human review
5. Recommended next steps (e.g., "ready to merge to main" or "needs human
   review on X")

## Merge plan (after Codex completes)

Human will:
1. Read STATUS.md and verify the canary numbers
2. Spot-check the changed files
3. Compare to GPT-5.5's suggestions in `files/gpt55_independent_leak_analysis.md`
4. If everything checks out, merge `agent/substrate-cascade-fix` to main
5. Add `mass-balance-regression-test` as the next item
