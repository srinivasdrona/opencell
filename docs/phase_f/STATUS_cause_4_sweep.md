# STATUS: CAUSE_4 Investigation + L2.5 Sweep

## Scope
Diagnose `CAUSE_4_UPSTREAM_STATE_POLLUTION` for `ChromosomeCondensation + ChromosomeSegregation`, then sweep all 256 honest-required L2.5 pairs for similar shared-substrate contention risk.

## Root Cause Verdict
`CAUSE_4` at tick 0 is primarily a **harness-path divergence** (H5), with an additional structural overwrite bug (H6).

- **H5 confirmed (primary for observed failing assertion):**
  - Composition path in no-hint mode does **not** inject trace hints (`run_integrated_replay_v2`, hint injection guarded by `if not disable_trace_hints`, `tests/vivarium/l2_2_replay_common_v2.py:933-940`).
  - Counterfactual diagnostic path **always** injects `trace_after_hint_observables` (`_build_counterfactual_step_vector`, `.../l2_2_replay_common_v2.py:383-388`), even when composition is running no-hint mode.
  - This makes isolated replay and composition structurally non-equivalent and can misclassify failures as CAUSE_4.

- **H6 confirmed (secondary, structural pattern):**
  - Before each downstream process step, harness overlays that process's own `states_before` for any observable that has upstream exposers (`.../l2_2_replay_common_v2.py:942-956`).
  - For shared substrates, this can reset/wipe upstream process deltas.

## Hypothesis Disposition
- H1 allocator double-counting: not supported by tick-0 traces/probe.
- H2 owner manifest override: not primary cause for observed tick-0 assertion (owner is Condensation and mismatch occurs before upstream processes).
- H3 update merge order: not primary cause (update apply is additive accumulate in `apply_count_update`).
- H4 pre-allocation reconciliation: not supported by evidence.
- H5 counterfactual/composition divergence: **confirmed (primary)**.
- H6 pre-step overwrite reset: **confirmed (structural secondary bug)**.

## Evidence
- Reproduced failing test:
  - `bin\\oc-pytest.cmd -x tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py -q`
  - Structured failure shows `CAUSE_4`, `upstream_processes=[]`, `oc_after_step=[ATP=75,ADP=3,PI=0,H2O=756718,H=0]`, `oc_counterfactual=[72,3,3,756715,3]`.
- Temporary probe (`_probe_cause4.py`, deleted before commit) showed:
  - No-hint composition step for Condensation emitted only `{ADP:+3}`.
  - Counterfactual path produced full ATP/H2O hydrolysis + PI/H byproducts.
  - Segregation `states_before.substrates` at tick 0 is `[GTP=0,GDP=0,H=0,H2O=0,PI=0]`; pre-step overlay rewrites shared state to these values before Segregation runs.
- Hint-enabled integrated replay check:
  - `bin\\oc-py.cmd _probe_run_hints.py` -> PASS.
  - Confirms no-hint vs hint path divergence is material.

## Sweep Outputs
- Generated script: `scripts/derive_l25_contention_sweep.py`.
- Generated report: `docs/phase_f/L2_5_CONTENTION_SWEEP.md`.
- Sweep summary (256 honest-required pairs):
  - predicted `likely_fail`: 60
  - predicted `at_risk`: 167
  - predicted `likely_pass`: 29
- Focus pair (`ChromosomeCondensation + ChromosomeSegregation`):
  - score 9 (`at_risk`)
  - shared substrates: `H`, `H2O`, `PI`
  - highest-risk signal: `H2O` baseline mismatch (`Condensation tick0=756718` vs `Segregation tick0=0`) with active consumption on Condensation side.

## Control Pair Verification
- `bin\\oc-pytest.cmd -x tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py -q`
- Result: `1 passed`.

## Decision (Per Task Rule)
Harness-level defects identified in `tests/vivarium/l2_2_replay_common_v2.py`; **no harness edits applied** (operator approval required).
No process-file fix applied in this turn.

## Proposed Harness Fixes (Not Applied)
1. Gate counterfactual hint injection on `disable_trace_hints` so isolated replay matches composition mode.
2. Remove or narrow pre-step `states_before` overlay (`:942-956`) so downstream setup does not overwrite shared mutable observables from upstream steps.

## Progress Log
- [2026-06-18 13:32:26 UTC] Read SESSION_CONTEXT Hard Rule 17 + L2.5 rubric.
- [2026-06-18 13:32:26 UTC] Reproduced failing pair test with structured CAUSE_4 payload.
- [2026-06-18 13:36:32 UTC] Ran probe and captured tick-0 per-step state/update evidence.
- [2026-06-18 13:38:19 UTC] Generated contention sweep report for all 256 honest-required pairs.
- [2026-06-18 13:40:04 UTC] Verified control pair still passes; finalized investigation and sweep status.
