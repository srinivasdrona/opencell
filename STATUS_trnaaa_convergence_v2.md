# tRNAAminoacylation Convergence Validation v2

## Beat 1 - Projection Contract Identified

- `_run_trna_aminoacylation_tick` overlays four inputs into a fresh `build_state_template(process)` state: `substrates`, `enzymes`, `freeRNAs`, and `aminoacylatedRNAs`.
- Substrate and enzyme vectors use fixture/runtime WID lists sourced from `state["substrate_wids"]` and `state["enzyme_wids"]`; the split RNA channels use `process.free_rna_wids` and `process.aminoacylated_rna_wids`.
- The helper calls `refresh_allocator_views(process, runtime_state)`, runs `process.next_update(1.0, runtime_state)`, and applies the emitted delta with `apply_count_update(runtime_state, update)`.
- Post-update projection reads `substrates`, `freeRNAs`, and `aminoacylatedRNAs` back out of `runtime_state` via `project_observable_from_state(...)`; it never digs into `update[...]` paths directly.
- The Design-A catalog marks `tRNAAminoacylation` primary channel as `rnas`, so the harness should gate on `np.concatenate([free_after, aminoacylated_after])` against Karr's `states_after.freeRNAs` + `states_after.aminoacylatedRNAs`.

## Beat 2 - Harness

Added [tests/vivarium/_substrate_stress/trnaaa_stress_v2.py](/E:/opencell-worktrees/validate-trnaaa-convergence/tests/vivarium/_substrate_stress/trnaaa_stress_v2.py), which mirrors the PFolding alpha-loop but rebuilds state with the tRNAAminoacylation wrapper's overlay/apply/project flow.
The harness loads `s000`-`s004` through `runner_helpers._v2_seed_mat_path(...)`, scales only `states_before.substrates`, overlays `substrates`/`enzymes`/`freeRNAs`/`aminoacylatedRNAs`, then projects `substrates`, `freeRNAs`, and `aminoacylatedRNAs` from the post-update state.
Primary-channel comparison uses the catalog's `rnas` contract: `np.concatenate([free_after, aminoacylated_after])` versus Karr `states_after.freeRNAs` + `states_after.aminoacylatedRNAs`.
Thresholds match the PFolding harness: `PASS` iff mean per-tick W1 `< 0.5` and max per-tick W1 `< 2.0`, over 5 seeds x 100 ticks.

## Beat 3 - Results

Pending.

## Beat 4 - Verdict

Pending.
