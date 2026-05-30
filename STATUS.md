# STATUS — L2.0 Bucket A Sweep

## Before / After Counts

- Before (from `docs/phase_e/L2_0_SCHEMA_AUDIT.md` at sweep start): GREEN=0, AMBER=24, RED=4, ERROR=0
- After (post-sweep `scripts/probe_l2_0_schema_audit.py`): GREEN=28, AMBER=0, RED=0, ERROR=0

## Per-Process Disposition Table

| Process | Before | After | Commit Hash | Notes |
|---|---|---|---|---|
| ChromosomeCondensation | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations from fixture WIDs. |
| ChromosomeSegregation | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations. |
| Cytokinesis | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations. |
| DNADamage | RED | GREEN | 5800f4a | Added declaration-only schema channels `substrates` / `enzymes` / `boundEnzymes` from fixture IDs. |
| DNARepair | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations. |
| DNASupercoiling | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations. |
| FtsZPolymerization | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations. |
| HostInteraction | RED | GREEN | 5800f4a | Added top-level `substrates` / `enzymes` / `boundEnzymes` declarations from fixture IDs. |
| MacromolecularComplexation | AMBER | GREEN | 5800f4a | Added `complexs` alias plus top-level `enzymes` / `boundEnzymes` declarations. |
| Metabolism | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations from model ID surface. |
| ProteinActivation | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations from fixture IDs. |
| ProteinDecay | AMBER | GREEN | 5800f4a | Added `complexs` / `monomers` aliases and top-level `enzymes` / `boundEnzymes` declarations. |
| ProteinFolding | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` plus `foldedMonomers` / `unfoldedMonomers` declarations. |
| ProteinModification | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` plus `modifiedMonomers` / `unmodifiedMonomers` declarations. |
| ProteinProcessingII | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` plus `processedMonomers` / `unprocessedMonomers` declarations. |
| ProteinProcessingI | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` plus `processedMonomers` / `unprocessedMonomers` declarations. |
| ProteinTranslocation | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` plus `monomers` declarations. |
| RNADecay | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations from fixture IDs. |
| RNAModification | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` plus `modifiedRNAs` / `unmodifiedRNAs` declarations. |
| RNAProcessing | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` plus `processedRNAs` / `unprocessedRNAs` declarations. |
| ReplicationInitiation | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations. |
| Replication | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations from fixture IDs. |
| RibosomeAssembly | AMBER | GREEN | 5800f4a | Added `complexs` / `monomers` aliases and top-level `enzymes` / `boundEnzymes` declarations. |
| TerminalOrganelleAssembly | RED | GREEN | 5800f4a | Added top-level `substrates` / `enzymes` / `boundEnzymes` declarations. |
| Transcription | AMBER | GREEN | 5800f4a | Added top-level `enzymes` / `boundEnzymes` declarations from fixture IDs. |
| TranscriptionalRegulation | RED | GREEN | 5800f4a | Added top-level `substrates` / `enzymes` / `boundEnzymes` declarations. |
| Translation | AMBER | GREEN | 5800f4a | Added top-level `monomers` plus `enzymes` / `boundEnzymes` declarations. |
| tRNAAminoacylation | AMBER | GREEN | 5800f4a | Added top-level `freeRNAs` / `aminoacylatedRNAs` plus `enzymes` / `boundEnzymes` declarations. |

## L2.1 Regression Check

- Pre-sweep PASSED count (from `docs/phase_e/L2_STATUS.md`): 9
- Post-sweep command run:
  - `E:\opencell\.venv-opencell\Scripts\python.exe -m pytest tests/vivarium -k "l2_replay" -q --tb=no`
  - Result in this worktree: `308 deselected`, no `l2_replay` tests collected, non-zero pytest exit due empty selection.
- Post-sweep PASSED count: not measurable in this worktree with the requested selector (no matching tests present).
- Regressed process names: not observed (selection empty).

## Bucket C Deferrals

- None in this sweep.

## Open Questions

1. This worktree has no `tests/vivarium/*l2_replay*` test files, so the requested L2.1 selector cannot validate 9-pass non-regression locally. Should we run the replay gate from the sibling sweep worktree that contains those tests and then backport results here?
2. Should `data/m1_sources/karr_native/per_process_traces` be symlinked/standardized for all audit worktrees so `scripts/probe_l2_0_schema_audit.py` is reproducible without manual copy?

## Pre-existing L2.1 WIP Note (carried from verify branch)

1. Residue WID(s): original fingerprint `substrates[0] = ATP` (tick 0, +3) shifted; current first failure is `enzymes[1] = MG_213_214_298_6MER_ADP` (tick 0, +3).
2. MATLAB file:line: `/mnt/e/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeCondensation.m:252-269` (`nBindingMax` and stochastic bind loop) and `:273-283` (substrate updates during binding).
3. Root cause: OC was anchored to legacy trace path and used Poisson relaxation throttling in `_sample_binding_events`; MATLAB evolves by binding up to `nBindingMax` each tick, so OC under-consumed ATP at tick 0.
4. Diff size in lines (<=15): 9 lines (`3` insertions, `6` deletions) in `opencell/vivarium/karr_chromosome_condensation.py`.
5. L2.1 result: shifted-failure (`[wip]`), pytest tail:
   F                                                                        [100%]
   =================================== FAILURES ===================================
   E   Failed: L2a mismatch record: tick=0, observable=enzymes, index=1, oc_val=3.0, karr_val=0.0, diff=3.0
   /mnt/e/opencell-worktrees/wave9-chromcond/tests/vivarium/l2_replay_common.py:537: Failed: L2a mismatch record: tick=0, observable=enzymes, index=1, oc_val=3.0, karr_val=0.0, diff=3.0
   1 failed in 39.99s
6. L1 chassis result: PASSED (`tests/vivarium/test_karr_chromosome_condensation.py`), tail:
   ......                                                                   [100%]
   6 passed in 44.24s
7. Commit hash: <pending>
8. Wall-time spent: ~54 minutes.
