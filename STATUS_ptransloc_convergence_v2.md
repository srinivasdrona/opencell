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
Harness output written to `tests/vivarium/_substrate_stress/ptransloc_stress_v2_results.txt`.

| alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | total_karr_events | exact_primary_match | verdict |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| 1.00 | 0.000000 | 0.000000 | 84 | 84 | yes | PASS |
| 0.50 | 0.000000 | 0.000000 | 84 | 84 | yes | PASS |
| 0.10 | 0.000004 | 0.001186 | 83 | 84 | no | PASS |
| 0.05 | 0.000125 | 0.002667 | 59 | 84 | no | PASS |
| 0.01 | 0.000324 | 0.004149 | 0 | 84 | no | PASS |

Sanity check: the `alpha=1.00` row is exactly zero on both mean and max per-tick W1, so the v2 harness is exercising the correct OC projection path.

## Beat 4 - Verdict
Case **B - regime-bounded**.

The primary `monomers` channel matches Karr exactly at `alpha=1.00` and `alpha=0.50`, which supports the convergence-green claim in the non-limiting regime.
That claim does **not** extend to the full stress sweep: exact identity is lost at `alpha=0.10`, `0.05`, and `0.01`, even though the PFolding-style W1 thresholds still remain comfortably PASS.
This does not look like a harness bug: `alpha=1.00` is exactly zero, the wrapper-aligned projection path is exercised end-to-end, and the total OC event count declines monotonically as substrates are starved (`84 -> 83 -> 59 -> 0`), which is biologically plausible.
Recommendation: keep ProteinTranslocation in the convergence-green bucket, but qualify it explicitly as **high-substrate / non-limiting-regime convergence**, not as an alpha-invariant exact replay claim.
