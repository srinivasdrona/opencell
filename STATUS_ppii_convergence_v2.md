# ProteinProcessingII Convergence Validation v2

## Beat 1 - Projection Contract

1. `_run_protein_processing_ii_tick` constructs a fresh process via `_protein_processing_ii_process(_sample_seed(seed, tick))`, then builds `runtime_state = build_state_template(process)` before any overlay.
2. The helper overlays exactly three input observables: `substrates` from `state["oracle_before_substrates"]` onto `list(state["substrate_wids"])`, `enzymes` from `state["oracle_before_enzymes"]` onto `list(state["enzyme_wids"])`, and `monomers` from `state["oracle_before_monomers"]` onto `list(state["monomer_wids"])`.
3. For ProteinProcessingII, `_protein_processing_ii_process` aliases `process.monomer_wids = list(process.unprocessed_monomer_wids)`, so the normalized Design-A `monomers` channel is backed by the process's unprocessed-monomer WID order.
4. After `refresh_allocator_views(process, runtime_state)`, the helper runs `process.next_update(1.0, runtime_state)`, applies the emitted delta with `apply_count_update(runtime_state, update)`, and never reads `update[...]` directly for verdict payloads.
5. The helper projects exactly two output observables from post-update state: `substrates` via `project_observable_from_state(... observable="substrates", wids=substrate_wids, bound_enzymes_before=None)` and primary-channel `monomers` via `project_observable_from_state(... observable="monomers", wids=monomer_wids, bound_enzymes_before=None)`, which resolves to `protein.unprocessed_counts` when that store exists.
