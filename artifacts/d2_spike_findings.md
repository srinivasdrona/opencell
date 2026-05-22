# D.2 Decision Spike - Findings (2026-05-22)

## TL;DR
Probes 1-4 support the core Vivarium mechanics assumed by both Option A and Option C: accumulate semantics work, Step/Deriver reconciliation can be made to work, same-tick visibility behaves as start-of-tick (ordering does not change it), and mixed substrate topology (flat + nested) is technically possible. Probe 5 produced a high-signal first-pass `AssertionError` on a trivial fourth-process addition, then passed after spike-only process wiring/module-load adjustments. Net: Option C is feasible, but currently carries higher integration fragility than estimated; Option A remains the lower-risk near-term path with clean reversibility.

## Probe 1 - Accumulate semantics
- Observation 1: Single-writer accumulate matched expectation exactly (`expected_final_x=112`, `observed_final_x=112.0`).
- Observation 2: Two writers on the same accumulate port also produced the expected summed result (`observed_final_x=112.0`).
- Observation 3: Parameter step state persisted across ticks (`parameters_persist_write_ok=true`).
- Decision impact: No blocker for either A or C.

## Probe 2 - Step reconciliation
- Observation 1: Both Step and Deriver variants reached `final_protein_A=190.0` with repeated reconcile cycles.
- Observation 2: Execution traces show reconciliation running each tick (`reconcile_*`, `m3`, `d2` sequence repeated).
- Observation 3: `d2_consumed` reset path behaved as intended (`final_d2_consumed_A=0.0`).
- Decision impact: Reconciliation primitive is viable; this does not force A or C.

## Probe 3 - Same-tick visibility
- Observation 1: Reader saw `100.0` then `200.0` onward in both process orders.
- Observation 2: Reversing writer/reader insertion order did not change observed sequence.
- Observation 3: Behavior is consistent with start-of-tick visibility plus one-tick propagation.
- Decision impact: v4 "run-first" intuition is not a reliable assumption; both A and C should explicitly model one-tick lag.

## Probe 4 - Substrate topology
- Observation 1: Migration surface is non-trivial (`occurrences_substrates_key=52` across `files_with_substrates_refs=15`, `files_scanned=146`).
- Observation 2: Mixed topology probe succeeded (`ok=true`) and emitted both `ATP` and `counts` keys under shared substrate store.
- Observation 3: No immediate hard failure requiring forced all-at-once migration to nested topology.
- Recommended path: (c) align D.2 design to current flat substrate topology now; defer broad migration unless/until a concrete functional need appears.
- Decision impact: Reduces migration pressure on both A and C.

## Probe 5 - Third-process addition
- First pass (high-signal failure): probe run returned `engine_run_ok=false` with `engine_run_error="AssertionError()"` and zero emitted time points. Full traceback is preserved in `experiments/d2_spike/probe5_first_pass_traceback.txt`.
- Traceback location: `vivarium/core/engine.py` assertion in `_process_state` (`assert isinstance(store.value, Process)`), indicating a process-state wiring/module-load class of failure at first integration attempt.
- Rerun after spike-only patch: probe passed (`engine_run_ok=true`, `timeseries_time_points=6`, `wall_seconds~27.48`), with no edits to `opencell/` or `tests/`.
- Composer metrics:
- `base_loc=285` (`opencell/vivarium/karr_composite.py`)
- `probe_loc=92` (`experiments/d2_spike/karr_composite_4process.py`)
- `protein_decay_stub_token_hits=3`
- Decision impact: Option C is feasible but first-pass integration friction exists and is higher than a "trivial additive process" assumption.

## Surprises (NOT in the original probe plan)
- Probe 5 first-pass assertion happened before any core-repo changes, which is itself a data point about integration fragility.
- The LOC delta metric for probe 5 is not directly comparable to base composer complexity because the spike composer copy is intentionally minimal/probe-specific.
- Mixed substrate topology worked better than expected, which lowers immediate migration risk.

## Time accounting
- Execution window (from session log): approximately 19 minutes from probe run start through final successful probe outputs.
- Per-probe script execution timing captured directly:
- Probe 5 first pass: `~29.87s` (failed).
- Probe 5 final pass: `~27.48s` (passed).
- Probes 1-4 emitted results but did not include per-script wall-seconds in their JSON artifacts.
- Probes skipped/abandoned: none.

## A-vs-C decision recommendation
**My recommendation (the spike runner):** A

**Reasoning**
Empirical results remove several conceptual blockers for both options, but the first-pass Probe 5 assertion shows that even a trivial "add fourth process" path can fail in ways that are not obvious from design review alone. Since A has lower reversibility cost and can still pivot to C after incremental hardening, A is the safer immediate choice under uncertainty. This recommendation is about near-term execution risk, not a definitive rejection of C.

**Evidence the operator should review before deciding**
- `artifacts/d2_probe1_results.json`
- `artifacts/d2_probe2_results.json`
- `artifacts/d2_probe3_results.json`
- `artifacts/d2_probe4_results.json`
- `artifacts/d2_probe5_results.json`
- `experiments/d2_spike/probe5_first_pass_traceback.txt`
- Decision matrix in `docs/design/d2_decision_spike_2026-05-22.md` (section 7)
