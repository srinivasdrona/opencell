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

Saved raw output to [tests/vivarium/_substrate_stress/trnaaa_stress_v2_results.txt](/E:/opencell-worktrees/validate-trnaaa-convergence/tests/vivarium/_substrate_stress/trnaaa_stress_v2_results.txt).

| alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | total_karr_events | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| 1.00 | 0.000000 | 0.000000 | 355351 | 355351 | PASS |
| 0.50 | 0.000000 | 0.000000 | 355351 | 355351 | PASS |
| 0.10 | 0.000000 | 0.000000 | 355351 | 355351 | PASS |
| 0.05 | 0.026865 | 5.432432 | 354846 | 355351 | FAIL |
| 0.01 | 10.479405 | 13.783784 | 96794 | 355351 | FAIL |

Sanity check passed: the `alpha=1.0` row is exact-zero W1, which is the expected signal that the harness is projecting the real OC post-state instead of reading the wrong `update[...]` payload path.

## Beat 4 - Verdict

Case **B — regime-bounded**.

The convergence-green claim holds exactly for `alpha` in `{1.0, 0.5, 0.1}` and fails below that floor in this harness: `alpha=0.05` crosses the PFolding-style max-W1 gate and `alpha=0.01` diverges strongly in both W1 and total aminoacylation events.
This does **not** look like the v1 payload-path bug recurring, because the same projection contract yields exact-zero W1 at `alpha=1.0` and remains exact through `alpha=0.1`.
Recommendation: mark `tRNAAminoacylation` as convergence-green only down to `alpha=0.1` in the current substrate-stress framing, and treat `0.05` / `0.01` as out-of-regime rather than globally green.
