# tRNAAminoacylation Convergence Validation v2

## Beat 1 Summary
1. Mirror the structure of `tests/vivarium/_substrate_stress/pfolding_stress_v2.py` for `KarrTRNAAminoacylationProcess`.
2. Load v2 per-process traces for seeds `s000`-`s004` via the existing seeded-trace helpers.
3. Rebuild OpenCell runtime state from scaled `states_before.substrates` plus unscaled `enzymes`, `freeRNAs`, and `aminoacylatedRNAs`.
4. Run `process.next_update(1.0, state)` and compare OC's projected `aminoacylatedRNAs` against Karr's `states_after.aminoacylatedRNAs`.
5. Record per-alpha W1 results, then classify the convergence-green claim using the PFolding v2 case matrix.

## Wiring Notes
- Required `states_before` channels confirmed from runner helpers: `substrates`, `enzymes`, `boundEnzymes`, `freeRNAs`, `aminoacylatedRNAs`.
- Primary comparison channel for this investigation: `aminoacylatedRNAs`.
- Verified OC entry point: `KarrTRNAAminoacylationProcess.next_update`.
- Verified OC emission path differs from the task's suggested field path: aminoacylated tRNA deltas are emitted under `update["rna"]["aminoacylated_counts"]`, not `update["protein"]["counts"]`.
- The seeded v2 oracle files exist via the helper's external fallback root at `E:/opencell/data/m1_sources/karr_native/per_process_traces_v2_s000` ... `s004`.

## Results
Not run.

## Verdict
STOPPED before Beat 2 / harness authoring.

## Stop Reason
- The task pinned the output payload field path as `update["protein"]["counts"] (aminoacylated_rna_wids)` and instructed: if this does not match the OC port's actual emission, document the gap in STATUS and stop.
- Source check in `opencell/vivarium/karr_trna_aminoacylation.py` showed the actual write path is:
  - `update["rna"]["counts"]` for free RNA deltas
  - `update["rna"]["aminoacylated_counts"]` for aminoacylated RNA deltas
- `next_update` does not emit aminoacylated tRNA deltas through `protein.counts`.
- Proceeding would require overriding the pinned payload-path assumption from the task, which would violate the "document the gap in STATUS and STOP — don't invent fields" rule.

## Verification
- Expected observable change: `bin\oc-py.cmd tests/vivarium/_substrate_stress/trnaaa_stress_v2.py` prints a five-row alpha table and shows `alpha=1.00` with per-tick W1 approximately `0.0`.
- Actual measured value: not measured, because the investigation stopped before harness authoring.
- Evidence for the named inversion failure mode: the OC port was checked before writing the harness, and the mismatch was found in the real `next_update` emission path rather than being papered over in test code.
- Verdict: could-not-measure, because the task's pinned payload field path conflicts with the OC port.
