# STATUS H9 Fix

## Beat 1
In `tests/vivarium/l2_2_replay_common_v2.py:1236-1302`, replaced the global owner-init substrate seed with per-process own-baseline pre-step overlays while preserving H6 upstream-mutation index preservation (now only where baseline-compatible on owned observables).

## Beat 2
### (a) H9 diagnosis (verbatim: verdict + fix sketch)
> H9 **CONFIRMED**.
>
> Exact arithmetic at tick 0:
> - DNASupercoiling Karr baseline: `907 ATP`
> - Owner-seeded path baseline: `75 ATP` (`ChromosomeCondensation` `states_before`)
> - Upstream Condensation deterministic step: `75 -> 72` (`-3 ATP`)
> - Captured shared pre-DNAS baseline: `72 ATP`
>
> So the pre-step substrate state seen by DNASupercoiling is on the owner (`ChromosomeCondensation`) timeline, not DNASupercoiling's own `states_before` timeline.
>
> Bug site: `tests/vivarium/l2_2_replay_common_v2.py:1236-1252` (global owner-init from `before_vectors[owner_name][obs]`), interacting with per-process overlay in `1268-1302`. Smallest correction is to stop using a single owner snapshot as the global substrate seed for composed steps and instead initialize each process's pre-step substrate baseline from that process's own `before_vectors` at the moment its step is prepared (while still preserving upstream-mutated indices where intended), so DNASupercoiling receives its own tick-0 baseline (`907`) rather than the owner timeline baseline (`75 -> 72`).

### (b) Harness code at bug site (verbatim from diagnosis)
`tests/vivarium/l2_2_replay_common_v2.py:1236-1252`:
```python
            for obs in all_observables:
                owner_name = owner_manifest[obs]
                owner_ctx = contexts[owner_name]
                source_vec = before_vectors[owner_name][obs]
                master_vec = np.zeros(len(master_wids_by_observable[obs]), dtype=np.float64)
                owner_wids = owner_ctx.wids_by_observable[obs]
                for owner_idx, owner_wid in enumerate(owner_wids):
                    master_idx = owner_ctx.process_wid_to_master_idx[obs][owner_wid]
                    master_vec[master_idx] = float(source_vec[owner_idx])
                overlay_observable_into_state(
                    process=owner_ctx.process,
                    state=shared_state,
                    observable=obs,
                    vector=master_vec,
                    wids=master_wids_by_observable[obs],
                    store_path_override=owner_ctx.spec.store_path_override,
                )
```

`tests/vivarium/l2_2_replay_common_v2.py:1268-1302`:
```python
                for obs in ctx.spec.observables:
                    upstream_exposers = [
                        p
                        for p in ordered
                        if order_idx[p] < order_idx[name] and obs in contexts[p].spec.observables
                    ]
                    if upstream_exposers:
                        overlay_vec = before_vectors[name][obs]
                        mutated_master_indices = upstream_mutated_master_indices_by_observable[obs]
                        # H6 fix (STATUS_cause_4_sweep.md): do not wipe shared WIDs that
                        # were already mutated by upstream steps in this tick.
                        if mutated_master_indices:
                            running_vec = project_observable_from_state(
                                process=ctx.process,
                                state=shared_state,
                                observable=obs,
                                wids=ctx.wids_by_observable[obs],
                                bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                                store_path_override=ctx.spec.store_path_override,
                            )
                            overlay_vec = before_vectors[name][obs].copy()
                            for proc_idx, proc_wid in enumerate(ctx.wids_by_observable[obs]):
                                master_idx = ctx.process_wid_to_master_idx[obs][proc_wid]
                                if master_idx in mutated_master_indices:
                                    # Keep upstream-mutated shared WIDs from the
                                    # live shared state; overlay only untouched WIDs.
                                    overlay_vec[proc_idx] = running_vec[proc_idx]
                        overlay_observable_into_state(
                            process=ctx.process,
                            state=shared_state,
                            observable=obs,
                            vector=overlay_vec,
                            wids=ctx.wids_by_observable[obs],
                            store_path_override=ctx.spec.store_path_override,
                        )
```

## Beat 3 (Plan)
- Remove the global owner-seed pass entirely; do not seed shared substrate/state from `before_vectors[owner]`.
- In the per-process loop, always overlay each observable from `before_vectors[name][obs]` before that process step.
- Keep H6 preservation logic, but preserve only for owned observables and only when downstream baseline equals upstream pre-mutation baseline for that master index.
- Mirror probe logic (`probe_h9_owner_overlay.py`, `probe_h8_composition_delta.py`) to the same harness flow so probes remain faithful.
- Must not touch process files, `_PROCESS_SPECS`, `_build_owner_manifest`, or `_owned_observables`.

## Beat 4 (Pre-mortem, inversion)
1. Way 1: regress currently passing L2.5 pairs (Translation+RNAProc, Cond+Seg, HostInteraction+TerminalOrganelle, plus DS passes) by changing pre-step overlays too aggressively.
2. Way 2: regress L2.2/L2.1 single-process replay behavior; with one process, own-baseline must remain behaviorally identical.
3. Way 3: break H6 upstream-mutation preservation; downstream could incorrectly overwrite a real upstream mutation where both processes share pre-mutation baseline.

## Beat 5 (Verification protocol + results)
1. `bin\oc-pytest tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v --tb=no -q`
   - Result: `20 failed, 15 passed, 8 skipped` (PASS count increased from baseline 7 to 15; +8).
2. `bin\oc-pytest tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py -v`
   - Result: `2 passed`.
3. `bin\oc-pytest tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py -v`
   - Result: `2 passed`.
4. `bin\oc-pytest tests/vivarium/test_karr_dna_supercoiling_l2_replay.py tests/vivarium/test_karr_metabolism_l2_replay.py tests/vivarium/test_karr_translation_l2_replay.py -v`
   - Result: `3 passed`.
5. `python scripts/probe_h9_owner_overlay.py` (executed via `wsl bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && ..."`).
   - Result: pre-DNAS shared ATP now `907` (target met; no longer `72`).
6. `python scripts/probe_h8_composition_delta.py` (executed via `wsl bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && ..."`).
   - Result: `oc_compare` remains `-4` (not near `-60`); H8 delta behavior not unlocked by H9 fix alone.

## Implementation choice
- Chosen shape: **Shape 1 (merged passes)**.
- Global owner-init pass removed.
- Per-process own-baseline overlay always runs.
- H6 preservation retained, narrowed to owned-observable overlays with baseline compatibility on each preserved master index.

## L2.5 DS scoreboard (post-fix)
- Total: 43
- Passed: 15
- Failed: 20
- Skipped: 8
- Net vs stated baseline (7 PASS): **+8 PASS** (>=3 unlock threshold met).

Passing DS pairs:
- `ChromosomeCondensation+DNARepair`
- `ChromosomeCondensation+ProteinFolding`
- `ChromosomeCondensation+RNAProcessing`
- `ChromosomeCondensation+Replication`
- `ChromosomeCondensation+tRNAAminoacylation`
- `ChromosomeSegregation+RNAProcessing`
- `ChromosomeSegregation+Translation`
- `ChromosomeCondensation+Translation`
- `ChromosomeSegregation+DNARepair`
- `ChromosomeSegregation+ProteinFolding`
- `ChromosomeSegregation+tRNAAminoacylation`
- `ChromosomeCondensation+ProteinProcessingI`
- `ChromosomeCondensation+ProteinProcessingII`
- `ChromosomeSegregation+ProteinProcessingI`
- `ChromosomeSegregation+ProteinProcessingII`

Predicted canary unlock checks:
- `Cond+DNASupercoiling`: still FAIL.
- `Seg+DNASupercoiling`: still FAIL.
- `Cond+ReplicationInitiation`: still FAIL.
- `Seg+ReplicationInitiation`: still FAIL.
- `Seg+Replication`: still FAIL.

## Files changed
- `tests/vivarium/l2_2_replay_common_v2.py`
- `scripts/probe_h9_owner_overlay.py`
- `scripts/probe_h8_composition_delta.py`
