# ProteinProcessingI Convergence Validation v2

## Beat 1 - Projection Contract
- `_run_protein_processing_i_tick` overlays three inputs into a fresh `runtime_state`: `substrates`, `enzymes`, and logical `monomers` (`tests/vivarium/_l2_2_design_a_runner_helpers.py`).
- The wrapper does not read `update[...]` payload paths back out; it calls `apply_count_update(runtime_state, update)` and then projects from state.
- The projected outputs are exactly two channels: `substrates` and logical `monomers`; the catalog marks `monomers` as the primary channel for ProteinProcessingI.
- All three overlay WID lists and both projection WID lists come from the prepared `state[...]` payload: `state["substrate_wids"]`, `state["enzyme_wids"]`, and `state["monomer_wids"]`.
- For ProteinProcessingI, that logical `monomers` channel maps to Karr's `unprocessedMonomers` trace, while `processedMonomers` and `boundEnzymes` exist in the oracle but are not part of the wrapper's projection contract.

## Beat 2 - Harness
- Added `tests/vivarium/_substrate_stress/ppi_stress_v2.py`, mirroring the PFolding v2 alpha-loop structure across `alpha in (1.0, 0.5, 0.1, 0.05, 0.01)` and seeds `s000`-`s004`.
- The harness scales only `states_before.substrates`, then passes `oracle_before_substrates`, `oracle_before_enzymes`, `oracle_before_monomers`, and the wrapper-style `state["*_wids"]` payload into `_run_protein_processing_i_tick`.
- Primary-channel comparison is against Karr `states_after.unprocessedMonomers`, using the wrapper's projected logical `monomers` output after `apply_count_update(...)`.
- Threshold policy matches PFolding v2: `PASS` iff `per_tick_W1_mean < 0.5` and `per_tick_W1_max < 2.0`.
- Guardrail command `bin\oc-pytest.cmd "tests/vivarium/test_l2_2_design_a*.py" -q` passed: `56 passed` in about 5 minutes.

## Beat 3 - Results
- Pending.

## Beat 4 - Verdict
- Pending.
