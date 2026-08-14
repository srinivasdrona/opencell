# STATUS: L25 ProcessSpec Wiring

## Scope
Wire all 20 missing `_ProcessSpec` entries in `tests/vivarium/l2_2_replay_common_v2.py`, verify 28 total entries, and run the 43 deterministic-stochastic (DS) pair tests.

## Constraints Check
- Python invocations use `bin\oc-py.cmd` / `bin\oc-pytest.cmd` only.
- Modified files limited to:
  - `tests/vivarium/l2_2_replay_common_v2.py`
  - `docs/phase_f/status/STATUS_l25_processspec_wiring.md`

## Beat Tracker
| Beat | Description | Status | Notes |
|---|---|---|---|
| 1 | Wire all 20 missing `_ProcessSpec` entries | COMPLETE | Imports + specs added; `_COMPOSITION_ORDER_V2` expanded to 28 names |
| 2 | Verify 28 entries + collect-only run | COMPLETE | `Total: 28`; collect-only confirms `43 tests collected` |
| 3 | Run all 43 DS pair tests + summarize | COMPLETE | Run completed: 30 failed / 7 passed / 6 skipped |
| 4 | (Conditional) Document new failure modes | COMPLETE | New CAUSE_5 + Cytokinesis wid-length precondition mismatch documented |

## Wiring Notes
- Added all 20 requested process specs and expanded `_COMPOSITION_ORDER_V2` to include all 28 process names.
- Used per-process L2 replay test constants for process class, observables, WID attribute mapping, pass-through, and hint surfaces.
- Applied projection literals where trace vector cardinality differs from runtime observable cardinality (e.g. Metabolism substrates, Transcription substrates, ProteinActivation substrates, ProteinTranslocation monomers).

## Beat 2 Verification
- Spec inventory command:
  - `bin\oc-py.cmd _tmp_verify_specs.py` (temp script wrapper for `_PROCESS_SPECS` import/print)
  - Result: `Total: 28` with all expected process names present.
- Collect-only command:
  - `bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py --collect-only -q`
  - Result: `43 tests collected in 29.26s`.

## Beat 3 Execution
- Run command:
  - `bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v --tb=short`
- Captured log:
  - `.tmp_l25_ds_pairs_run.log`

## Beat 3 Summary
- Total: 43
- Passed: 7
- Failed: 30
- Skipped: 6
- Errors: 0

## Failed Count by Cause
- `CAUSE_4_UPSTREAM_STATE_POLLUTION`: 12
- `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE`: 16
- Non-CAUSE precondition (`wid-length mismatch`): 2

## Failure Table (pair, cause_code, first WID diverged)
| Pair | Cause Code | First WID |
|---|---|---|
| ChromosomeCondensation+DNASupercoiling | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ATP |
| ChromosomeCondensation+Metabolism | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ADP |
| ChromosomeCondensation+ProteinDecay | CAUSE_4_UPSTREAM_STATE_POLLUTION | MG_020_MONOMER |
| ChromosomeCondensation+ProteinFolding | CAUSE_4_UPSTREAM_STATE_POLLUTION | ATP |
| ChromosomeCondensation+ProteinTranslocation | CAUSE_4_UPSTREAM_STATE_POLLUTION | ATP |
| ChromosomeCondensation+RNAProcessing | CAUSE_4_UPSTREAM_STATE_POLLUTION | H2O |
| ChromosomeCondensation+ReplicationInitiation | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | MG_469_1MER_ATP |
| ChromosomeCondensation+tRNAAminoacylation | CAUSE_4_UPSTREAM_STATE_POLLUTION | ADP |
| ChromosomeSegregation+FtsZPolymerization | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | GTP |
| ChromosomeSegregation+Metabolism | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ADP |
| ChromosomeSegregation+ProteinDecay | CAUSE_4_UPSTREAM_STATE_POLLUTION | MG_020_MONOMER |
| ChromosomeSegregation+ProteinTranslocation | CAUSE_4_UPSTREAM_STATE_POLLUTION | ATP |
| ChromosomeSegregation+RNAProcessing | CAUSE_4_UPSTREAM_STATE_POLLUTION | H2O |
| ChromosomeCondensation+ProteinModification | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ADP |
| ChromosomeCondensation+Transcription | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ATP |
| ChromosomeSegregation+DNASupercoiling | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ATP |
| ChromosomeSegregation+Replication | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ATP |
| ChromosomeCondensation+Cytokinesis | PRECONDITION_WID_LENGTH_MISMATCH | N/A |
| ChromosomeCondensation+FtsZPolymerization | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | MG_224_2MER_GTP |
| ChromosomeSegregation+Cytokinesis | PRECONDITION_WID_LENGTH_MISMATCH | N/A |
| ChromosomeSegregation+ReplicationInitiation | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | MG_469_1MER_ATP |
| ChromosomeSegregation+Transcription | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ATP |
| ChromosomeCondensation+ProteinProcessingI | CAUSE_4_UPSTREAM_STATE_POLLUTION | H2O |
| ChromosomeCondensation+ProteinProcessingII | CAUSE_4_UPSTREAM_STATE_POLLUTION | H2O |
| ChromosomeCondensation+RNADecay | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | AMP |
| ChromosomeSegregation+ProteinModification | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ADP |
| ChromosomeSegregation+ProteinProcessingI | CAUSE_4_UPSTREAM_STATE_POLLUTION | H2O |
| ChromosomeSegregation+ProteinProcessingII | CAUSE_4_UPSTREAM_STATE_POLLUTION | H2O |
| ChromosomeSegregation+RNADecay | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | AMP |
| HostInteraction+Metabolism | CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE | ADP |

## Beat 4 Notes (New Failure Modes vs prior run)
- `CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE` is newly surfaced at scale after unsupported-process wiring (16 cases).
- New structural precondition failures appear for Cytokinesis pairings:
  - `L2.2.v2 precondition failed (wid-length mismatch): process=Cytokinesis, observable=substrates, len(runtime_wids)=4, len(initial_oracle_vector)=3`
- Unsupported-process precondition failures were eliminated (previously 35).

## Beat 4 Review Queue
- Review Cytokinesis WID source mapping in L2.5 harness (runtime inferred 4 substrate WIDs vs oracle 3).
- Review deterministic-stochastic composition ordering assumptions for Condensation/Segregation against shared substrate ownership, given CAUSE_5 concentration at tick 0 on `substrates`.

## Progress Log
- [2026-06-18 16:28:00 UTC] Loaded `SESSION_CONTEXT.md` and confirmed Hard Rule 17 naming discipline.
- [2026-06-18 16:28:00 UTC] Audited DS pair harness/test/status artifacts and identified unsupported-process gap as primary blocker.
- [2026-06-18 16:28:00 UTC] Wired 20 missing process specs and added required imports/order coverage in `l2_2_replay_common_v2.py`.
- [2026-06-18 16:28:00 UTC] Verified `_PROCESS_SPECS` inventory (`Total: 28`) and DS collect-only count (`43`).
- [2026-06-18 16:28:00 UTC] Executed full DS run (`-v --tb=short`): 30 failed / 7 passed / 6 skipped.
- [2026-06-18 16:28:00 UTC] Parsed full failure log and documented per-pair cause + first diverged WID.
