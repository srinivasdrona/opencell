# ProteinProcessingII Convergence Validation v2

## Beat 1 - Projection Contract

1. `_run_protein_processing_ii_tick` constructs a fresh process via `_protein_processing_ii_process(_sample_seed(seed, tick))`, then builds `runtime_state = build_state_template(process)` before any overlay.
2. The helper overlays exactly three input observables: `substrates` from `state["oracle_before_substrates"]` onto `list(state["substrate_wids"])`, `enzymes` from `state["oracle_before_enzymes"]` onto `list(state["enzyme_wids"])`, and `monomers` from `state["oracle_before_monomers"]` onto `list(state["monomer_wids"])`.
3. For ProteinProcessingII, `_protein_processing_ii_process` aliases `process.monomer_wids = list(process.unprocessed_monomer_wids)`, so the normalized Design-A `monomers` channel is backed by the process's unprocessed-monomer WID order.
4. After `refresh_allocator_views(process, runtime_state)`, the helper runs `process.next_update(1.0, runtime_state)`, applies the emitted delta with `apply_count_update(runtime_state, update)`, and never reads `update[...]` directly for verdict payloads.
5. The helper projects exactly two output observables from post-update state: `substrates` via `project_observable_from_state(... observable="substrates", wids=substrate_wids, bound_enzymes_before=None)` and primary-channel `monomers` via `project_observable_from_state(... observable="monomers", wids=monomer_wids, bound_enzymes_before=None)`, which for ProteinProcessingII resolves to `protein.counts` because the template does not expose a dedicated `protein.unprocessed_counts` store.

## Beat 2 - Harness

- Added [tests/vivarium/_substrate_stress/ppii_stress_v2.py](E:\opencell-worktrees\validate-ppii-convergence\tests\vivarium\_substrate_stress\ppii_stress_v2.py), mirroring PFolding's alpha sweep but using ProteinProcessingII's authoritative Design-A state overlay and post-update projection contract.
- The harness compares the runner-normalized primary channel (`monomers`) against oracle `states_after.unprocessedMonomers`, since the raw PPii seeded trace exposes `unprocessedMonomers` rather than a generic `monomers` dataset.
- The harness includes an explicit seed-path fallback to `E:\opencell\data\m1_sources\karr_native` / `/mnt/e/opencell/data/m1_sources/karr_native` because this worktree only contains `per_process_traces_v2_s001` locally.
- Verification command: `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
- Result: `56 passed, 4 warnings in 296.06s`

## Beat 3 - Results

Harness command: `bin\oc-py.cmd tests/vivarium/_substrate_stress/ppii_stress_v2.py`

Results file: [tests/vivarium/_substrate_stress/ppii_stress_v2_results.txt](E:\opencell-worktrees\validate-ppii-convergence\tests\vivarium\_substrate_stress\ppii_stress_v2_results.txt)

| alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | total_karr_events | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| 1.00 | 0.000000 | 0.000000 | 939 | 939 | PASS |
| 0.50 | 0.000008 | 0.002075 | 937 | 939 | PASS |
| 0.10 | 0.000012 | 0.002075 | 936 | 939 | PASS |
| 0.05 | 0.000012 | 0.002075 | 936 | 939 | PASS |
| 0.01 | 0.000012 | 0.002075 | 936 | 939 | PASS |

Sanity check: the `alpha=1.0` row is exact (`per_tick_W1_mean = 0`, `per_tick_W1_max = 0`), so the harness is measuring the intended post-update projection rather than replaying the v1 payload-path bug.
