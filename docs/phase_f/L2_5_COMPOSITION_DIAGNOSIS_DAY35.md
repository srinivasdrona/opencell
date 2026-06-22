# Allocator/Composition Diagnosis — Day-35 EOD

**Status:** Partial. One harness contract bug found and fixed. Two deeper bugs
characterized but not yet fixed.

## Finding 1: Hidden read-surface contract gap (FIXED)

### The gap

`_build_counterfactual_step_vector` (line 825 of `l2_2_replay_common_v2.py`)
calls `_inject_hidden_read_surface(...)` to populate the `chromosome`,
`stimulus.values`, and `rnaPolymerase.supercoilingBindingProbFoldChange`
channels before invoking `next_update`.

`run_integrated_replay_v2` (the composition harness path) was NOT calling it.

### Affected processes (have hidden_read_surface declared)

- `chromosome`: Replication, ReplicationInitiation, DNARepair, Cytokinesis,
  FtsZPolymerization, ChromosomeCondensation, ChromosomeSegregation
- `stimulus.values`: ProteinActivation, TranscriptionalRegulation (has both)
- All three channels: TranscriptionalRegulation

### Fix

Added `_inject_hidden_read_surface(ctx=ctx, state=shared_state, tick=tick)`
in `run_integrated_replay_v2` right before `refresh_allocator_views(...)`,
matching the counterfactual contract.

### Impact

DNARepair pairs went from large-drift FAIL → 1-event-drift FAIL. The contract
is now consistent. But the per-tick comparison still fails because the
remaining 1-event drift exceeds tolerance for a single-seed run. This is
genuinely a stochastic-variance question (need ensemble to verify).

L2.5 honest scoreboard unchanged: 15 PASS / 46 FAIL / 41 SKIP of 102 wired.

DS regression: clean (7 PASS / 29 FAIL / 8 SKIP of 44, same as pre-fix).

## Finding 2: ProteinTranslocation composition over-eagerness (CHARACTERIZED)

### What we know

Failure: ProteinFolding + ProteinTranslocation, tick 21, 14 extra ATP
hydrolyses by Translocation that Karr didn't perform.

Symbol pattern: textbook ATP hydrolysis `ATP + H2O → ADP + PI + H` × 14.

The failure record says:
- `isolated_replay_result: matches_oracle` ✓
- `oc_counterfactual_compare: [0,0,0,0,0,0,0]` ✓

### What we tried

Wrote `scripts/probe_translocation_composition.py` to run the same composition
sequence outside pytest. **The probe failed to reproduce the 14-event drift** —
when I run ProteinFolding+ProteinTranslocation at tick 21 directly,
Translocation produces 0 events (matching Karr).

This means the bug is NOT in the per-tick state construction (which my probe
mirrors). It's somewhere in the harness's accumulated process-instance state.

### Likely causes (UNCONFIRMED)

1. **Process RNG state accumulation.** The harness reuses the same process
   instance across ticks 0..N. The RNG advances. My probe started fresh at
   tick 21 with a fresh RNG. If Translocation's stochastic sampler depends
   on accumulated RNG state, this could produce different samples.
2. **Allocator views state.** `refresh_allocator_views` may carry per-process
   state (`substrates_allocated` port). My probe and the harness both call
   `refresh_allocator_views`, but with different state-template ancestry.
3. **Counterfactual happens to pass by coincidence.** Counterfactual replay
   builds a fresh state template per call, where `protein.unprocessed_counts`
   defaults to all zeros (Translocation's port template has zero defaults).
   With queue empty, `cytoplasmic_counts` is empty and Translocation returns
   `{}`. So counterfactual matches Karr's `karr_compare=[0,...]` by both
   producing zero — not because Translocation's biology is right, but
   because both produce nothing.

If hypothesis 3 is correct, this is a major insight: **counterfactual-replay
"PASS" for stochastic processes whose Karr trace has zero deltas is a
coincidence, not a validation.** The harness's CAUSE_4_UPSTREAM_STATE_POLLUTION
attribution is misleading — the real bug is that composition fills
`protein.unprocessed_counts` with non-zero values via the `monomers` overlay
(which resolves to that path), and Translocation then processes them
because RNG sampling at tick 21 happens to fire.

### Recommendation

Add a `scripts/probe_translocation_rng_isolation.py` that runs ticks 0..21
in two modes side-by-side:
- Mode A: tick-by-tick reset (fresh state per tick, fresh template)
- Mode B: continuous (same process instance, same accumulated RNG, but tick
  state from Karr's trace)

If Mode B reproduces the 14-event drift, the bug is RNG-state-driven and
needs a `process.reset_rng_per_tick()` hook (or similar). If Mode B also
shows 0 events, the bug is somewhere we haven't instrumented yet.

This investigation is the 1-2 hour scope for Day-36 morning.

## Finding 3: DNARepair stochastic-variance drift (CHARACTERIZED)

After the Finding-1 fix, DNARepair pairs fail with diff=1 (single AHCYS+H
events, classic methylation chemistry). This is within typical stochastic
variance for a 100-tick run.

### Recommendation

DNARepair's L2.5 oracle is `distributional`, not bit-identity. The per-tick
comparison may be too strict. Two options:

A. Switch the per-tick check to bound the per-tick magnitude against a
   distributional envelope derived from multiple seeds (proper L2.5 semantics).
B. Run an N-seed ensemble for the 6 DNARepair pairs to see if the
   distributional envelope passes.

Option B is faster to verify. Option A is the long-term right answer.

## Status

- ✅ Finding 1: fixed, no regression, doesn't move scoreboard.
- 🔬 Finding 2: characterized, root-cause hypothesis pending; needs ~1-2h
  RNG-isolation probe.
- 🔬 Finding 3: characterized, needs ensemble verification (~30 min) or
  per-tick rubric review (~half day).

The 12 of 15 SS FAILs explained by these two findings:
- 6 DNARepair pairs (Finding 1 contract + Finding 3 stochastic-variance)
- 6 ProteinTranslocation pairs (Finding 2 — same root-cause hypothesis)

The remaining 3 FAILs are stragglers (MacromolComplex+Folding, ProcI+ProcII,
Folding+ProcII, RNAProc+tRNA) — likely 4 individual investigations.
