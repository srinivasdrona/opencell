# STATUS H9 Diagnosis

## Beat 1
CONFIRMED: in `ChromosomeCondensation+DNASupercoiling`, the pre-step shared `substrates` baseline feeding DNASupercoiling is inherited from the owner process path (`before_vectors[owner]["substrates"]`, owner=`ChromosomeCondensation`) rather than DNASupercoiling's own tick-0 `before_vectors`.

## Beat 2
### (a) Operator empirical finding (verbatim)
> Yesterday's H8 probe (`scripts/probe_h8_composition_delta.py`, commit `7c6320d`) revealed:
>
> | WID | karr_states_before | oc_states_before_tick_start | oc_states_before_step (pre-DNASupercoiling) | oc_emitted_delta_dnasc | karr_compare | oc_compare |
> |---|---:|---:|---:|---:|---:|---:|
> | ATP | 907 | 907 | **72** | -4 | -60 | -4 |
> | H2O | 9080624 | 9080624 | **756715** | -4 | -60 | -4 |
>
> **Key observation:** Between tick start and DNASupercoiling's step, ATP dropped from 907 to 72 (-835). ChromosomeCondensation, which ran between those points, is DETERMINISTIC and known to consume at most a few units of ATP (`docs/phase_f/status/STATUS_cause5_diagnosis.md` previously showed Cond's substrate touches at tick 0 as `ATP: 75 -> 72 delta=-3` — only -3, NOT -835).
>
> **Suspicion:** The `72` figure matches Karr's *Metabolism* trace ATP value at tick 0 (also documented in `STATUS_cause5_diagnosis.md` yesterday: `ATP: 72 -> 72` for Metabolism). This is suspicious: why would DNASupercoiling see Metabolism's substrate baseline?

### (b) Harness pre-step initialization code (`tests/vivarium/l2_2_replay_common_v2.py:1236-1302`)
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

            for name in ordered:
                ctx = contexts[name]
                if _trace_hints_enabled(
                    disable_trace_hints=disable_trace_hints,
                    oracle_type=resolved_oracle_type_by_process[name],
                ):
                    for obs in ctx.spec.trace_after_hint_observables:
                        overlay_trace_after_hint(
                            state=shared_state,
                            observable=obs,
                            vector=after_vectors[name][obs],
                            wids=ctx.wids_by_observable[obs],
                        )

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

## Beat 3
Implemented `scripts/probe_h9_owner_overlay.py` that reproduces the harness tick-0 flow for `ChromosomeCondensation+DNASupercoiling` with `disable_trace_hints=True`, then captures state exactly after the per-process overlay loop (`1268-1302`) for `DNASupercoiling` and before calling its `next_update`.

## Beat 4 (Pre-mortem, inversion)
1. Way 1: owner may be `DNASupercoiling` instead of `ChromosomeCondensation`; probe must read `owner_manifest["substrates"]` before interpretation.
2. Way 2: H6 mutation-preservation (`1277-1294`) may alter the overlay vector; if `mutated_master_indices["substrates"]` is empty after Cond, overlay should remain DNASupercoiling's own `before_vectors`.
3. Way 3: baseline at pre-`next_update` may already be correct (907), and mismatch could instead arise between `next_update` and `oc_after_step` (allocator budget / process read path).

## Beat 5 (Verification)
Probe command:
```bash
wsl bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python scripts/probe_h9_owner_overlay.py"
```
Observed:
- `owner_manifest["substrates"] = ChromosomeCondensation`
- `before_vectors["ChromosomeCondensation"]["substrates"]["ATP"] = 75`
- `before_vectors["DNASupercoiling"]["substrates"]["ATP"] = 907`
- `shared_state["substrates"]` immediately before `DNASupercoiling.next_update`: `ATP=72, ADP=3, PI=3, H2O=756715, H=3`
- Verdict from probe: `CONFIRMED`

## Probe-finding table
| Measurement | Value |
|---|---|
| `owner_manifest["substrates"]` | `ChromosomeCondensation` |
| `before_vectors["ChromosomeCondensation"]["substrates"]["ATP"]` | `75` |
| `before_vectors["DNASupercoiling"]["substrates"]["ATP"]` | `907` |
| `shared_state["substrates"]["ATP"]` pre-DNAS step | `72` |
| `shared_state["substrates"]["ADP"]` pre-DNAS step | `3` |
| `shared_state["substrates"]["PI"]` pre-DNAS step | `3` |
| `shared_state["substrates"]["H2O"]` pre-DNAS step | `756715` |
| `shared_state["substrates"]["H"]` pre-DNAS step | `3` |

## Owner manifest
- `owner_manifest["substrates"] = ChromosomeCondensation`.
- Owner selection path:
  - `_owned_observables(spec)` (`tests/vivarium/l2_2_replay_common_v2.py:559-560`) returns all `spec.observables` not in `spec.pass_through`.
  - `_build_owner_manifest(...)` (`tests/vivarium/l2_2_replay_common_v2.py:874-895`) computes `mutating_candidates` using `_owned_observables` and picks `mutating_candidates[0]`.
  - For ordered pair `['ChromosomeCondensation', 'DNASupercoiling']`, probe confirmed `mutating_candidates['substrates'] = ['ChromosomeCondensation', 'DNASupercoiling']`, so owner resolves to the first process: `ChromosomeCondensation`.

## Verdict
H9 **CONFIRMED**.

Exact arithmetic at tick 0:
- DNASupercoiling Karr baseline: `907 ATP`
- Owner-seeded path baseline: `75 ATP` (`ChromosomeCondensation` `states_before`)
- Upstream Condensation deterministic step: `75 -> 72` (`-3 ATP`)
- Captured shared pre-DNAS baseline: `72 ATP`

So the pre-step substrate state seen by DNASupercoiling is on the owner (`ChromosomeCondensation`) timeline, not DNASupercoiling's own `states_before` timeline.

## Fix sketch (≤1 paragraph)
Bug site: `tests/vivarium/l2_2_replay_common_v2.py:1236-1252` (global owner-init from `before_vectors[owner_name][obs]`), interacting with per-process overlay in `1268-1302`. Smallest correction is to stop using a single owner snapshot as the global substrate seed for composed steps and instead initialize each process's pre-step substrate baseline from that process's own `before_vectors` at the moment its step is prepared (while still preserving upstream-mutated indices where intended), so DNASupercoiling receives its own tick-0 baseline (`907`) rather than the owner timeline baseline (`75 -> 72`).
