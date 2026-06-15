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
Pending.

## Verdict
Pending.
