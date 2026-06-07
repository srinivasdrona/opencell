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
- 2026-06-04T21:20:01Z ? l22-f3: loaded F3 context docs and inspected translation/per-process extractor surfaces.
- 2026-06-04T21:20:01Z ? l22-f3: reproduced pre-fix seed_000 semantics drift (substrates 0%, monomers 30%, enzymes/boundEnzymes 90%, free/aminoacylated tRNAs 0%).
- 2026-06-04T21:20:01Z ? l22-f3: MATLAB diagnostic confirmed proc.monomers diverges from backing until copyToState and next tick pre-value diverges again.
- 2026-06-04T21:21:20Z ? l22-f3: patched extractor to capture translation snapshots at global tick boundaries (pre-loop and post-loop copyFromState).
- 2026-06-04T21:21:20Z ? l22-f3: post-fix seed_000 probe is green at 100% snap-eq for all 9 translation snapshot channels.
- 2026-06-04T21:40:38Z ? l22-f3: regenerated translation ensemble seeds 001..049 with patched extractor (936.44s total), and spot-check probes for seeds 010/049 are 100% on all 9 channels.
- 2026-06-04T21:42:59Z ? l22-f3: completed with commits d8a5354 (diagnose), 6f1f6d5 (fix), b19688f (regen); detailed report in STATUS_f3.md.
- 2026-06-04T22:06:08Z — GATE_A/F1 wired in tests/vivarium/_l2_2_ensemble_runner.py: per-seed fitted_init load from Karr Translation ensemble MAT + pre-tick overlay for substrates/enzymes/boundEnzymes.
- 2026-06-04T22:06:53Z — GATE_A/F2 wired in tests/vivarium/test_l2_2_translation.py: substrates comparator now projects through wasserstein_over_wid_intersection with dropped-WID audit persisted in comparison_report.json.
- 2026-06-04T22:10:09Z — GATE_A regen complete: bin\\oc-py.cmd tests/vivarium/_l2_2_ensemble_runner.py --seeds 0:49 --force (wall=65.752s).
- 2026-06-04T22:11:48Z — GATE_A full gate run executed: bin\\oc-pytest tests/vivarium/test_l2_2_translation.py -q (FAIL: ks_failure_count=398, wasserstein_failure_count=400).
- 2026-06-04T22:13:31Z — Wrote STATUS_gate_translation.md with F1/F2 line refs, pre/post tick-0 W1 table, gate verdict, dropped WIDs, and commit trail.
- [2026-06-04 22:10:29 UTC] GATE_B C1 complete: added extract_transcription_ensemble.m with boundary snapshot semantics; seed_000 extracted and snap-eq validated >=99% on all channels.
- [2026-06-04 22:25:18 UTC] GATE_B C2 complete: generated transcription ensemble seeds 000-049 and MANIFEST.json (50/50 present, no missing seeds).
- [2026-06-04 22:31:34 UTC] GATE_B C3 complete: added Transcription OC ensemble runner with fitted-init overlay and generated 50 NPZ seeds under data/opencell_ensembles/transcription/.
- [2026-06-04 22:32:02 UTC] GATE_B C4 wired: added tests/vivarium/test_l2_2_transcription.py with Bonferroni KS/W1 checks and substrate WID-intersection projection.
- [2026-06-04 22:37:13 UTC] GATE_B full run complete: test_l2_2_transcription.py executed (FAIL expected as quantitative verdict); artifacts + STATUS_gate_transcription.md updated with per-channel metrics.
