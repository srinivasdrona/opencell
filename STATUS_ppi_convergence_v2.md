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
- Wrote harness output to `tests/vivarium/_substrate_stress/ppi_stress_v2_results.txt`.
- Sanity check passed: the `alpha=1.0` row has `per_tick_W1_mean = 0.000000` and `per_tick_W1_max = 0.000000`, so the v2 projection path is not laundering a mismatch.
- Result table:

| alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | total_karr_events | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| 1.00 | 0.000000 | 0.000000 | 953 | 953 | PASS |
| 0.50 | 0.000000 | 0.000000 | 953 | 953 | PASS |
| 0.10 | 0.000000 | 0.000000 | 953 | 953 | PASS |
| 0.05 | 0.000000 | 0.000000 | 953 | 953 | PASS |
| 0.01 | 0.000000 | 0.000000 | 953 | 953 | PASS |

- Extra check on the limiting substrate (`water`) shows why alpha-scaling does not perturb this trace: across all positive-event ticks, even `floor(0.01 * water)` stayed above both `processed` and `2 * processed`, so the process never entered a new water-limited regime.

## Beat 4 - Verdict
- Verdict: **Case A (biology green)**.
- Answer to the task question: **yes**. For seeds `s000`-`s004`, OpenCell ProteinProcessingI's primary-channel output (`monomers` projected from post-update state, matching Karr `unprocessedMonomers`) matches Karr's recorded `states_after` exactly at every tested `alpha`.
- Recommendation: keep the convergence-green claim for ProteinProcessingI, and cite the v2 harness specifically because it uses the runner's projection contract rather than brittle `update[...]` payload inspection.

## Verification
- Expected outcome: `alpha=1.0` should show effectively zero primary-channel W1 if the harness is using the correct post-apply projection path.
- Actual outcome: `alpha=1.0` produced `per_tick_W1_mean = 0.000000` and `per_tick_W1_max = 0.000000`; all lower alphas also remained exactly zero.
- Commands run:
  - `bin\oc-pytest.cmd "tests/vivarium/test_l2_2_design_a*.py" -q`
  - `bin\oc-py.cmd tests/vivarium/_substrate_stress/ppi_stress_v2.py`
  - follow-up water-margin probe against the same five seeds
- Inversion check: the harness never reads `update[...]` to reconstruct outputs; it delegates output extraction to `_run_protein_processing_i_tick`, which applies the update into `runtime_state` and projects `monomers` from state.
- Inversion check: no production code was modified; the diff is limited to `STATUS_ppi_convergence_v2.md`, `tests/vivarium/_substrate_stress/ppi_stress_v2.py`, and `tests/vivarium/_substrate_stress/ppi_stress_v2_results.txt`.
