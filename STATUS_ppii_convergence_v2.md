# ProteinProcessingII Convergence v2 Status

## Beat 1 summary
1. Mirror `tests/vivarium/_substrate_stress/pfolding_stress_v2.py`: load v2 traces for seeds `s000`-`s004`, scale `states_before.substrates`, run one OC tick, and compare against Karr per tick.
2. Reuse the ProteinProcessingII state-build pattern from `_run_protein_processing_ii_tick` so the harness writes the same stores the L2.2 runner writes.
3. Validate the pinned primary-channel/output-path contract against the actual `KarrProteinProcessingIIProcess.next_update` emission before writing the harness.
4. If the wiring matches, run the alpha sweep `(1.0, 0.5, 0.1, 0.05, 0.01)` and write `tests/vivarium/_substrate_stress/ppii_stress_v2_results.txt`.
5. If the wiring does not match, document the gap and stop without inventing fields.

## Stop reason
Stopped before Beat 2 per the task's hard rule: the pinned output payload field path does not match the actual OpenCell ProteinProcessingII emission surface, and the oracle schema also disagrees with the pinned `monomers` wording.

## Evidence
- `opencell/vivarium/karr_protein_processing_ii.py:321-345` writes processed-monomer deltas to `update["protein"]["processed_counts"]`, while `update["protein"]["counts"]` is populated from `unprocessed_delta_vec`.
- `opencell/vivarium/karr_protein_processing_ii.py:190-208` defines `output_wids = self.processed_monomer_wids` and keeps a separate `unprocessed_delta_vec`, confirming the two channels are distinct.
- `tests/vivarium/_l2_2_design_a_runner_helpers.py:2702-2705` sets `process.monomer_wids = list(process.unprocessed_monomer_wids)` for ProteinProcessingII.
- `tests/vivarium/_l2_2_design_a_runner_helpers.py:2767-2822` projects the ProteinProcessingII `"monomers"` output using those `unprocessed_monomer_wids`, so the existing runner helper surface is also aligned to unprocessed monomers, not processed monomers.
- The v2 oracle file at `E:\opencell\data\m1_sources\karr_native\per_process_traces_v2_s000\ProteinProcessingII_100ticks.mat` exposes `states_after` keys `boundEnzymes`, `enzymes`, `processedMonomers`, `signalSequenceMonomers`, `substrates`, and `unprocessedMonomers`; there is no `states_after.monomers`.

## Conclusion
The task pins `primary channel = monomers` and `output payload field path = update["protein"]["counts"] for processed_monomer_wids`, but the actual OC port emits processed monomers via `protein.processed_counts`, emits unprocessed monomers via `protein.counts`, and the v2 oracle splits the after-state the same way (`processedMonomers` vs `unprocessedMonomers`).

Per the instruction "If any of the above don't match the OC port's actual emission, document the gap in STATUS and STOP — don't invent fields," I did not author `tests/vivarium/_substrate_stress/ppii_stress_v2.py`, did not run the alpha sweep, and did not generate `tests/vivarium/_substrate_stress/ppii_stress_v2_results.txt`.

## Notes
- The worktree's `data/m1_sources/karr_native/` directory is manifest-only, but the required v2 seed traces do exist under `E:\opencell\data\m1_sources\karr_native\per_process_traces_v2_s000` through `..._s004`. This is not the blocker; the emission/schema mismatch above is the blocker.
