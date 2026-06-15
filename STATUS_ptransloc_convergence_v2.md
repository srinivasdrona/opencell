# STATUS_ptransloc_convergence_v2

## Beat 1 - Projection Contract Identified
1. `_run_protein_translocation_tick` overlays exactly three input observables into `runtime_state`: `substrates`, `enzymes`, and `monomers`.
2. The same wrapper projects exactly two output observables after `apply_count_update(...)`: `substrates` and `monomers`.
3. WID sources in the wrapper come from the prepared sample state, not guessed process attrs: `substrate_wids = state["substrate_wids"]`, `enzyme_wids = state["enzyme_wids"]`, `monomer_wids = state["monomer_wids"]`.
4. `boundEnzymes` is not overlaid into the runtime state for ProteinTranslocation; the wrapper only carries `oracle_before_bound_enzymes` forward as `bound_enzymes_before` for projection compatibility.
5. Catalog and L2 replay evidence agree that `monomers` is the primary channel and the Karr monomer trace must be compared on the OC 482-monomer surface (the raw trace is 2892 = 482 monomers x 6 compartments, with the OC comparison using the cytosol slice).

## Beat 2 - Harness
Implemented `tests/vivarium/_substrate_stress/ptransloc_stress_v2.py`.
The harness mirrors the authoritative `_run_protein_translocation_tick(...)` state-build/update/projection path and only injects alpha-scaled `substrates` before invoking it.
Karr `monomers` comparisons use the OC 482-monomer surface by projecting the raw 2892-entry trace down to the leading cytosol slice, matching the existing L2 replay contract.
Validation command `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q` passed: `56 passed, 4 warnings`.

## Beat 3 - Run + Record
Pending.

## Beat 4 - Verdict
Pending.
