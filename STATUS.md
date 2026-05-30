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
