# tRNAAminoacylation Convergence Validation v2

## Beat 1 - Projection Contract Identified

- `_run_trna_aminoacylation_tick` overlays four inputs into a fresh `build_state_template(process)` state: `substrates`, `enzymes`, `freeRNAs`, and `aminoacylatedRNAs`.
- Substrate and enzyme vectors use fixture/runtime WID lists sourced from `state["substrate_wids"]` and `state["enzyme_wids"]`; the split RNA channels use `process.free_rna_wids` and `process.aminoacylated_rna_wids`.
- The helper calls `refresh_allocator_views(process, runtime_state)`, runs `process.next_update(1.0, runtime_state)`, and applies the emitted delta with `apply_count_update(runtime_state, update)`.
- Post-update projection reads `substrates`, `freeRNAs`, and `aminoacylatedRNAs` back out of `runtime_state` via `project_observable_from_state(...)`; it never digs into `update[...]` paths directly.
- The Design-A catalog marks `tRNAAminoacylation` primary channel as `rnas`, so the harness should gate on `np.concatenate([free_after, aminoacylated_after])` against Karr's `states_after.freeRNAs` + `states_after.aminoacylatedRNAs`.

## Beat 2 - Harness

Pending.

## Beat 3 - Results

Pending.

## Beat 4 - Verdict

Pending.
