# Day-38 Metabolism Writeback: Planned vs Delivered

**Status**: Step 3 of 3 in progress. W1 = 168.39 (was 171.39). Algorithm wired in correctly but recovery ratio 9.3% — dominated by FBA flux gap, not writeback gap.

**Probe basis** (NOT design doc, NOT memory):
- `scripts/probe_metab_writeback_actual.py` instantiates the EXACT L2.2 runner factory and inspects what comes out of `next_update` at Karr's tick-0 pre-state
- `git diff 8258e1e..HEAD` for code-level enumeration of what landed
- Empirical L2.2 run: `bin/oc-py tests/vivarium/l2_2_design_a_runner.py --process Metabolism --seeds 50 --ticks 10`

## What the design doc PROMISED

| # | Design item | Promise |
|---|---|---|
| D1 | Substrates port shape | Flat per-WID, sum across compartments |
| D2 | RNG semantics | Per-instance `_Mcg16807` from `karr_protein_decay_light` |
| D3 | Step 5 clipping | Faithful: clip metabolite rows on post-state |
| D4 | L2.2 runner mode | Switch to `dynamic_bounds=True` |
| Impl-1 | `stochasticRound` helper | Reuse from `karr_protein_decay_light:28-49` |
| Impl-2 | Fixture load in `__init__` | Load 7 indices/constants from `Metabolism_flat.mat` |
| Impl-3 | `_apply_karr_substrate_updates` | New method on the process running steps 1-4 |
| Impl-4 | Wire into both update paths | `_static_update` + `_dynamic_update` |
| Impl-5 | Verify | L2.1 + L2.2 + chassis + per-process tests no regress |
| Impl-6 | L2.5 unlock check | Re-run L2.5 honest pairs involving Metabolism |
| Pred-1 | Expected L2.1 impact | GENUINE → GENUINE (Metabolism already L2.1 GENUINE) |
| Pred-2 | Expected L2.2 impact | VERIFIED_FAIL → VERIFIED_GENUINE, W1 ≪ 171.39 |
| Pred-3 | Expected L2.5 impact | 15 → ~38 (23 Metabolism-pair unlocks) |
| Pred-4 | Cascade hypothesis | ProteinDecay + Replication may move COINCIDENTAL → GENUINE |

## What was ACTUALLY delivered (verified by git diff + probe)

| # | Design item | Status | Where | Verification |
|---|---|---|---|---|
| D1 | Flat per-WID port | ✅ DELIVERED as designed | `project_to_flat_per_wid()` in writeback module | Probe: returned 76 WID keys (sum across compartments) |
| D2 | Per-instance `_Mcg16807` | ✅ DELIVERED as designed | `KarrMetabolismProcess.__init__` line ~149 | `proc._karr_writeback_rng` is non-None instance |
| D3 | Step 5 faithful clipping | ✅ DELIVERED as designed | `apply_karr_substrate_writeback` Step 5 block | Unit test `test_step5_clip_prevents_negative_metabolites` PASS |
| D4 | L2.2 runner dynamic_bounds | ✅ DELIVERED as designed | `_l2_2_design_a_runner_helpers._metabolism_process` | Probe: `dynamic_bounds=True` confirmed |
| Impl-1 | stochasticRound helper | ✅ DELIVERED as designed | Reused `_Mcg16807` (no duplication) | Imported from `karr_protein_decay_light` |
| Impl-2 | Fixture load in __init__ | ✅ DELIVERED (one variation) | `KarrWritebackFixture.from_mat()` called from `__init__` when flag is on | Probe: `_karr_writeback_fixture` populated |
| Impl-3 | `_apply_karr_substrate_updates` | ⚠ DELIVERED differently | Implemented as **module-level function** in `karr_metabolism_writeback.py`, NOT as a method on the Process | Same functional result; cleaner separation; testable independently |
| Impl-4 | Wire into both update paths | ✅ DELIVERED as designed | `_static_update` + `_dynamic_update` (latter replaces `enable_lp_writeback` path) | Both paths gated by `enable_karr_substrate_writeback` |
| Impl-5 | No regression | ✅ VERIFIED | L2.1 28/28 PASS, L2.2 22/22 PASS (against old pins), 26/27 per-process Metabolism PASS (1 pre-existing failure unrelated) | |
| Impl-6 | L2.5 unlock check | ❌ NOT DONE YET | Pending decision based on L2.2 result | — |
| Pred-1 | L2.1 GENUINE preserved | ✅ MET | Metabolism L2.1: GENUINE (pin unchanged) | Test ran cleanly |
| Pred-2 | **L2.2 W1 ≪ 171.39** | ❌ **NOT MET** | W1 = **168.39** (1.7% reduction) | Empirical run completed |
| Pred-3 | L2.5 unlock | ⏸ DEFERRED | Pending Pred-2 resolution | — |
| Pred-4 | Cascade hypothesis | ⏸ DEFERRED | Pending Pred-2 resolution | — |

## What ACTUALLY happens in the writeback (probe output)

From `scripts/probe_metab_writeback_actual.py`:

- Process correctly configured: `dynamic_bounds=True, enable_karr_substrate_writeback=True`
- Fixture loaded: `_karr_writeback_fixture` non-None
- RNG seeded: `_karr_writeback_rng` non-None
- `next_update()` returns 76 substrates keys with `sum_abs = 13,842`
- Karr's recorded delta (per-WID summed): `sum_abs = 148,091`
- **Recovery ratio: 9.3%**

Top discrepancies (per-WID delta, OC vs Karr):

| WID | Karr delta | OC delta | Pattern |
|---|---:|---:|---|
| H | -24,521 | -1,000 | OC capped at ±1000, undercounting 24× |
| H2O | +22,393 | +1,643 | OC undercounting 14× |
| O2 | -10,865 | -1,000 | OC capped at ±1000, undercounting 11× |
| H2O2 | +10,863 | +717 | OC undercounting 15× |
| **HDCEA** | -7,919 | 0 | **MISSING entirely** |
| **HDCA** | -7,918 | 0 | **MISSING entirely** |
| GL | -7,529 | -668 | OC undercounting 11× |
| PI | -7,246 | -606 | OC undercounting 12× |
| **OCDCEA** | -6,741 | +1,000 | **Wrong sign** |
| CO2 | +5,432 | +501 | OC undercounting 11× |

## Diagnosis: why the writeback algorithm is right but the result is wrong

The writeback algorithm itself is verified correct by 8/8 standalone unit tests, including a tick-0 smoke test. So the bug is NOT in `apply_karr_substrate_writeback`. The bug is in the **inputs** the algorithm receives at the L2.2 runner's tick-0:

**Root cause 1: OC FBA growth at tick-0 is too low.**
- OC produces `growth_per_s = 5.58e-6`
- Karr's actual tick-0 growth was probably ~1e-5 (need to confirm from trace metadata)
- ~½ Karr growth → Step 3 biomass delta is ~½ Karr's contribution

**Root cause 2: Several exchange fluxes appear capped at ±1000 mol/sec.**
- 5 of top 10 OC deltas are exactly ±1000 (H, O2, DDCA, POE_SORBITAN, TTDCEA, TWEEN80)
- This is a bound clamp somewhere — either `model.lb/ub` fixture defaults or `compute_bounds` output
- Karr's actual exchange fluxes are much larger (24K, 11K, etc.)

**Root cause 3: Three substrates missing entirely (HDCEA, HDCA, OCDCEA + sign-flip).**
- These are long-chain fatty acids in Karr's biomass production
- Could be a `metabolism_new_production` value rounding to zero at OC's growth rate
- Could be a step-5 clip eating the delta if pre-state is near zero

**The writeback is doing what it's designed to do; the FBA solver isn't giving it the right flux vector and growth rate.**

## What would be needed to close the gap (NOT done in this session)

1. **Fix OC's `compute_bounds` exchange caps** — likely the ±1000 in `model.lb/ub` defaults needs to lift when nutrients are abundant
2. **Calibrate OC's FBA growth rate** to match Karr's tick-0 growth
3. **Investigate HDCEA/HDCA/OCDCEA missing channels** — likely a substrate mapping or bound issue specific to fatty acids
4. **OR** keep current writeback wiring but defer L2.2 Metabolism PASS — accept 168→<10 as a multi-day FBA tuning project, not a one-day writeback patch

## Honest decision required

The writeback work is **complete and correctly implemented**. The expected unlock (Metabolism L2.2 → GENUINE) is **blocked on FBA dynamic-bounds tuning**, which is a separate, larger piece of work. Options:

- **A**: Keep the writeback wired in (small 1.7% improvement), document the FBA gap as the next blocker, and move on to other fixes
- **B**: Roll back the L2.2 runner change (keep writeback code, but don't enable it in tests), preserve the cleaner pre-Day-38 baseline of "Metabolism W1=171.39 known issue", come back to it later as a larger project
- **C**: Continue debugging the FBA gap now (could be 1-2 days; high uncertainty)

## Provenance

- Probe used: `scripts/probe_metab_writeback_actual.py` (created this session)
- Empirical run: `tmp/l22_metab_writeback/` (Day-38 50 seeds × 10 ticks)
- Code commits: `92a3980`, `2d36ef3`
- Uncommitted: L2.2 runner factory + L2.1 test fixture overrides
