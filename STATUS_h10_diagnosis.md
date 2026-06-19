# H10 Diagnosis — Allocator-Budget Squeeze Under Composition

## Beats 1-5

**Beat 1.** REJECTED: at tick 0 in composition, `DNASupercoiling` reads `substrates_allocated` but receives ATP/H2O budgets equal to the full pool (`ATP=907`, `H2O=9080624`), not a squeezed budget like 4.

**Beat 2.**

Operator empirical finding (verbatim):

> Post-H9 fix (commit `07febee`), the pair test `ChromosomeCondensation+DNASupercoiling` STILL fails — but with a different signature. The H9 fix correctly seeds the shared substrate pool with DNASupercoiling's own tick-0 baseline (907 ATP). But DNAS still emits only `-4` ATP under composition vs `-60` in isolation.
>
> Failure record (post-H9):
> ```
> cause_code: CAUSE_4_UPSTREAM_STATE_POLLUTION
> observable: substrates, wid: ATP
> oc_after_step: [903, 7, 7, 9080620, 7]
> karr_after:    [847, 60, 60, 9080564, 60]
> oc_counterfactual:    [847, 60, 60, 9080564, 60]   <-- isolated replay matches Karr exactly
> oc_counterfactual_compare: [-60, +60, +60, -60, +60]
> oc_compare:                [-4, +4, +4, -4, +4]
> ```
>
> **Key observations:**
> - `oc_counterfactual` (isolated DNAS replay) matches Karr exactly: -60 ATP delta. Confirms DNAS's biology port (commit `250b777`) is correct.
> - `oc_after_step` (composition DNAS step) only consumed 4 ATP. So in composition mode, DNAS computes ~4 events instead of ~60.
> - The shared substrate pool baseline pre-DNAS is now 907 (post-H9 fix). So baseline is NOT the squeeze.
>
> **Suspicion:** DNAS reads its substrate budget from `substrates_allocated[DNAS][ATP]` (via `self._allocated_or_state(...)`). In composition mode, the harness may populate this key with a squeezed value (e.g., what the allocator "fairly" gives DNAS after Cond requested ATP). In isolation, this key is absent and DNAS falls back to the full 907 from `states["substrates"]`.
>
> The 56-ATP gap (60 expected - 4 actual) and the symmetric pattern across ATP/ADP/PI/H2O/H suggest a single budget number determining everything (likely `hydrolysis_budget = min(available_atp, available_h2o) = 4`, then 4 hydrolyses produce 4 of each product).

DNAS allocator-read code (`opencell/vivarium/karr_dna_supercoiling.py`, requested snippet):

```python
allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
available_atp = self._allocated_or_state(allocated_state, self.atp_wid)
available_h2o = self._allocated_or_state(allocated_state, self.h2o_wid)
hydrolysis_budget = min(available_atp, available_h2o)
```

**Beat 3.** Implemented and ran [`scripts/probe_h10_allocator_budget.py`](/E:/opencell/scripts/probe_h10_allocator_budget.py), which monkey-patches `DNASupercoiling.next_update` and captures, at tick 0 immediately before invocation, `states["substrates_allocated"]`, `states["substrates"]` ATP/H2O, and the exact `_allocated_or_state(...)` returns in both composition and isolated runs (`disable_trace_hints=True`).

**Beat 4 (pre-mortem, inversion).**

1. Way 1: The hypothesis might be wrong — DNAS may NOT be reading from `substrates_allocated` in composition mode (perhaps the key is absent, in which case `_allocated_or_state` falls back to `states["substrates"]` and the budget would be 907, not 4). If so, the bug is elsewhere (e.g., DNAS's no-hints sampler computing events differently when the available pool is large enough that integer overflow / int division produces 4).
2. Way 2: The probe might find that `substrates_allocated[DNAS][ATP] = 907` (correct) but the SAMPLER's actual ATP consumption is 4 due to a stochastic reason — e.g., gyrase processivity sampler draws 4 events because of an RNG-seed difference under composition. Verify by reading what the sampler actually computed (instrument `gyrase_events` / `topoiv_events` / `hydrolysis_budget` values).
3. Way 3: There might be no allocator at all in this pair — `substrates_allocated` may be an empty dict, and `_allocated_or_state` falls back to a different path that returns a small value (e.g., a default budget like the no-hints binding limit).

**Beat 5 (verification).** Probe emitted explicit composition-vs-isolation values for all required fields and returned `VERDICT=REJECTED`.

## Probe-finding table

| Case | `substrates_allocated` key present? | top-level `substrates_allocated` keys | `alloc[DNAS][ATP]` | `alloc[DNAS][H2O]` | `states["substrates"]["ATP"]` | `states["substrates"]["H2O"]` | `_allocated_or_state(..., ATP)` | `_allocated_or_state(..., H2O)` |
|---|---|---|---:|---:|---:|---:|---:|---:|
| composition (`ChromosomeCondensation+DNASupercoiling`) | True | `karr_chromosome_condensation`, `karr_dna_supercoiling` | 907 | 9080624 | 907 | 9080624 | 907 | 9080624 |
| isolation (`DNASupercoiling` only) | True | `karr_dna_supercoiling` | 907 | 9080624 | 907 | 9080624 | 907 | 9080624 |

## Harness allocator path

Quote from [`tests/vivarium/l2_2_replay_common_v2.py`](/E:/opencell/tests/vivarium/l2_2_replay_common_v2.py:1317):

```python
                    oc_before_step[obs] = project_observable_from_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=obs,
                        wids=ctx.wids_by_observable[obs],
                        bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                        store_path_override=ctx.spec.store_path_override,
                    )

                refresh_allocator_views(ctx.process, shared_state)
                update = ctx.process.next_update(1.0, shared_state)
                _apply_update(shared_state, update)
```

This harness path refreshes allocator views immediately before each `next_update`, and the probe shows that for DNAS at tick 0 it refreshes to full ATP/H2O (not squeezed) in both composition and isolation.

## Verdict

**H10 REJECTED.** Composition arithmetic at DNAS call entry is:

- `available_atp = _allocated_or_state(...) = 907`
- `available_h2o = _allocated_or_state(...) = 9080624`
- `hydrolysis_budget = min(907, 9080624) = 907`

So the budget read path is not squeezing to 4. The observed composition delta remains `-4/+4/+4/-4/+4`, but it is not caused by `substrates_allocated[DNAS][ATP/H2O]` being squeezed.

## Fix sketch (≤1 paragraph)

Exact bug site is not the harness allocator path; it is in DNASupercoiling’s no-hints event-production path before ATP capping, at [`opencell/vivarium/karr_dna_supercoiling.py`](/E:/opencell/opencell/vivarium/karr_dna_supercoiling.py:470) through [`opencell/vivarium/karr_dna_supercoiling.py`](/E:/opencell/opencell/vivarium/karr_dna_supercoiling.py:517), where `gyrase_events/topoiv_events` are sampled and then limited. Smallest correction sketch: instrument/align those sampled totals under composition vs isolated replay at identical tick-0 inputs (same sigma regions, catalytic counts, and replay/no-hints mode) and then apply the minimal logic change there so composition reproduces the isolated `~60` hydrolysis-events regime when the ATP/H2O budget is already 907.
