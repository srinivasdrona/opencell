# ProteinProcessingI Convergence Validation v2

## Beat 1 - Projection Contract
- `_run_protein_processing_i_tick` overlays three inputs into a fresh `runtime_state`: `substrates`, `enzymes`, and logical `monomers` (`tests/vivarium/_l2_2_design_a_runner_helpers.py`).
- The wrapper does not read `update[...]` payload paths back out; it calls `apply_count_update(runtime_state, update)` and then projects from state.
- The projected outputs are exactly two channels: `substrates` and logical `monomers`; the catalog marks `monomers` as the primary channel for ProteinProcessingI.
- All three overlay WID lists and both projection WID lists come from the prepared `state[...]` payload: `state["substrate_wids"]`, `state["enzyme_wids"]`, and `state["monomer_wids"]`.
- For ProteinProcessingI, that logical `monomers` channel maps to Karr's `unprocessedMonomers` trace, while `processedMonomers` and `boundEnzymes` exist in the oracle but are not part of the wrapper's projection contract.

## Beat 2 - Harness
- Pending.

## Beat 3 - Results
- Pending.

## Beat 4 - Verdict
- Pending.
