# STATUS: L2.5 Deterministic-Stochastic Pair Sweep

## Scope
Scaffold and run L2.5 honest-mode deterministic-stochastic pair tests using a
single parametrized test file and seed_0 only.

## Constraints Check
- Python invocations use `bin\oc-py.cmd` / `bin\oc-pytest.cmd` only.
- Harness/process/schema/catalog files are not modified.
- Pair source is `data/schemas/l25_pair_list.toml`.

## Beat Tracker
| Beat | Description | Status | Notes |
|---|---|---|---|
| 1 | Scaffold helper that generates DS pair tests programmatically | COMPLETE | Loader reads TOML and filters DS honest-required pairs |
| 2 | Generate all 43 DS pair test cases | COMPLETE | `pytest --collect-only` confirms 43 case IDs |
| 3 | Run all 43 and commit result table | COMPLETE | Full run finished with verdicts for all 43 cases |
| 4 | Conditional failure investigation documentation | COMPLETE | Grouped by CAUSE_X and unsupported-process mode |

## Execution
- Primary run command:
  - `bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v --tb=no`
- Diagnostic parse command (to classify failures):
  - `bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -q --tb=short`

## Final Summary
- Total: 43
- Passed: 2
- Failed: 41
- Skipped: 0
- Errors: 0

Runner completed all 43 cases; no infrastructure error prevented completion.

## Failure Mode Grouping
- `CAUSE_4_UPSTREAM_STATE_POLLUTION`: 6
- Non-CAUSE harness precondition failure (`L2.2.v2 unsupported process name(s)`): 35
  - `Metabolism` (3)
  - `Cytokinesis`, `DNADamage`, `DNARepair`, `DNASupercoiling`, `FtsZPolymerization`, `ProteinDecay`, `ProteinFolding`, `ProteinModification`, `ProteinTranslocation`, `RNADecay`, `RNAModification`, `Replication`, `ReplicationInitiation`, `RibosomeAssembly`, `Transcription`, `tRNAAminoacylation` (2 each)

## Results Table (Failures First)
| # | Pair | Result | Cause/Notes |
|---|---|---|---|
| 1 | ChromosomeSegregation + RibosomeAssembly | FAILED | UNSUPPORTED_PROCESS:RibosomeAssembly |
| 2 | ChromosomeCondensation + DNARepair | FAILED | UNSUPPORTED_PROCESS:DNARepair |
| 3 | ChromosomeCondensation + DNASupercoiling | FAILED | UNSUPPORTED_PROCESS:DNASupercoiling |
| 4 | ChromosomeCondensation + Metabolism | FAILED | UNSUPPORTED_PROCESS:Metabolism |
| 5 | ChromosomeCondensation + ProteinDecay | FAILED | UNSUPPORTED_PROCESS:ProteinDecay |
| 6 | ChromosomeCondensation + ProteinFolding | FAILED | UNSUPPORTED_PROCESS:ProteinFolding |
| 7 | ChromosomeCondensation + ProteinTranslocation | FAILED | UNSUPPORTED_PROCESS:ProteinTranslocation |
| 8 | ChromosomeCondensation + RNAProcessing | FAILED | CAUSE_4_UPSTREAM_STATE_POLLUTION |
| 9 | ChromosomeCondensation + Replication | FAILED | UNSUPPORTED_PROCESS:Replication |
| 10 | ChromosomeCondensation + ReplicationInitiation | FAILED | UNSUPPORTED_PROCESS:ReplicationInitiation |
| 11 | ChromosomeCondensation + tRNAAminoacylation | FAILED | UNSUPPORTED_PROCESS:tRNAAminoacylation |
| 12 | ChromosomeSegregation + FtsZPolymerization | FAILED | UNSUPPORTED_PROCESS:FtsZPolymerization |
| 13 | ChromosomeSegregation + Metabolism | FAILED | UNSUPPORTED_PROCESS:Metabolism |
| 14 | ChromosomeSegregation + ProteinDecay | FAILED | UNSUPPORTED_PROCESS:ProteinDecay |
| 15 | ChromosomeSegregation + ProteinTranslocation | FAILED | UNSUPPORTED_PROCESS:ProteinTranslocation |
| 16 | ChromosomeSegregation + RNAProcessing | FAILED | CAUSE_4_UPSTREAM_STATE_POLLUTION |
| 17 | ChromosomeCondensation + ProteinModification | FAILED | UNSUPPORTED_PROCESS:ProteinModification |
| 18 | ChromosomeCondensation + Transcription | FAILED | UNSUPPORTED_PROCESS:Transcription |
| 19 | ChromosomeSegregation + DNASupercoiling | FAILED | UNSUPPORTED_PROCESS:DNASupercoiling |
| 20 | ChromosomeSegregation + Replication | FAILED | UNSUPPORTED_PROCESS:Replication |
| 21 | ChromosomeCondensation + Cytokinesis | FAILED | UNSUPPORTED_PROCESS:Cytokinesis |
| 22 | ChromosomeCondensation + FtsZPolymerization | FAILED | UNSUPPORTED_PROCESS:FtsZPolymerization |
| 23 | ChromosomeCondensation + RNAModification | FAILED | UNSUPPORTED_PROCESS:RNAModification |
| 24 | ChromosomeCondensation + RibosomeAssembly | FAILED | UNSUPPORTED_PROCESS:RibosomeAssembly |
| 25 | ChromosomeSegregation + Cytokinesis | FAILED | UNSUPPORTED_PROCESS:Cytokinesis |
| 26 | ChromosomeSegregation + DNARepair | FAILED | UNSUPPORTED_PROCESS:DNARepair |
| 27 | ChromosomeSegregation + ProteinFolding | FAILED | UNSUPPORTED_PROCESS:ProteinFolding |
| 28 | ChromosomeSegregation + ReplicationInitiation | FAILED | UNSUPPORTED_PROCESS:ReplicationInitiation |
| 29 | ChromosomeSegregation + Transcription | FAILED | UNSUPPORTED_PROCESS:Transcription |
| 30 | ChromosomeSegregation + tRNAAminoacylation | FAILED | UNSUPPORTED_PROCESS:tRNAAminoacylation |
| 31 | ChromosomeCondensation + DNADamage | FAILED | UNSUPPORTED_PROCESS:DNADamage |
| 32 | ChromosomeCondensation + ProteinProcessingI | FAILED | CAUSE_4_UPSTREAM_STATE_POLLUTION |
| 33 | ChromosomeCondensation + ProteinProcessingII | FAILED | CAUSE_4_UPSTREAM_STATE_POLLUTION |
| 34 | ChromosomeCondensation + RNADecay | FAILED | UNSUPPORTED_PROCESS:RNADecay |
| 35 | ChromosomeSegregation + DNADamage | FAILED | UNSUPPORTED_PROCESS:DNADamage |
| 36 | ChromosomeSegregation + ProteinModification | FAILED | UNSUPPORTED_PROCESS:ProteinModification |
| 37 | ChromosomeSegregation + ProteinProcessingI | FAILED | CAUSE_4_UPSTREAM_STATE_POLLUTION |
| 38 | ChromosomeSegregation + ProteinProcessingII | FAILED | CAUSE_4_UPSTREAM_STATE_POLLUTION |
| 39 | ChromosomeSegregation + RNADecay | FAILED | UNSUPPORTED_PROCESS:RNADecay |
| 40 | ChromosomeSegregation + RNAModification | FAILED | UNSUPPORTED_PROCESS:RNAModification |
| 41 | HostInteraction + Metabolism | FAILED | UNSUPPORTED_PROCESS:Metabolism |
| 42 | ChromosomeSegregation + Translation | PASSED | — |
| 43 | ChromosomeCondensation + Translation | PASSED | — |

## Progress Log
- [2026-06-18 14:21:55 UTC] Loaded SESSION_CONTEXT Hard Rule 17 and L2.5 reference docs.
- [2026-06-18 14:21:55 UTC] Parsed `l25_pair_list.toml`; verified DS honest-required pair count is 43.
- [2026-06-18 14:21:55 UTC] Added new test module scaffold at `tests/vivarium/test_l25_deterministic_stochastic_pairs.py`.
- [2026-06-18 14:25:21 UTC] Updated case IDs to explicit `ProcessA+ProcessB` labels.
- [2026-06-18 14:25:21 UTC] Ran collection for DS test file; `43 tests collected`.
- [2026-06-18 14:33:09 UTC] Removed invalid pre-order assertion and re-ran full 43-case DS suite.
- [2026-06-18 14:33:09 UTC] Final run completed: 41 failed / 2 passed / 0 skipped / 0 errors.
- [2026-06-18 14:34:22 UTC] Grouped failures by mode: `CAUSE_4` (6) and unsupported-process precondition (35).
