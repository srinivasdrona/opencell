# STATUS_wire_metabolism

## Beat 1 - SUT inspection

- SUT class: `KarrMetabolismProcess`.
- `next_update` return shape:
  - If `states["trace_hint"]["substrates_next"]` is present, it returns `{"substrates": {wid: delta}}` by differencing the hinted post-tick substrate vector against the current substrate store.
  - The Design-A runner uses the default static path (`dynamic_bounds=False`), where `next_update()` delegates to `_static_update()` and returns only `{"metabolic_reaction": {"fluxs": ..., "growth_per_s": ..., "growth_per_h": ...}}`.
  - Dynamic mode is not used by the Design-A harness, but `_dynamic_update()` would additionally emit `substrates`, `m1_dynamic_diagnostics`, and `m1_pools`.
- Primary channel store path: `("substrates",)` via `ports_schema()` and the generic observable-store mapping.
- Init-once / not-per-tick state:
  - The `model` from `opencell.m1.karr_metabolism.load_default()` should be cached and reused; repeated loads are unnecessary work for replay.
  - Static replay has no explicit per-process LP warm-start object; `_static_update()` calls `km.solve_fba(...)` each tick from the cached model.
  - Dynamic mode carries mutable FBA state on the process (`_sub_state`, `_enz_state`, `_prev_shared`, `_fba_reaction_bounds`, row-index caches, pool diagnostics), so process reuse would matter if that mode were ever used here.
- Contract risk observed before edits: `tests/vivarium/_l2_2_design_a_runner_helpers.py::_run_metabolism_tick()` currently overlays `oracle_after_substrates` into `trace_hint`, and `KarrMetabolismProcess.next_update()` consumes that hint before the honest static FBA path. This violates the task rule that the dispatcher must not pass `trace_hint`.

## Beat 2 - dispatcher + factory

- `_metabolism_process(seed)` was already present on the base branch and already cached by seed; kept that structure and reused the cached `load_default()` model.
- `_run_metabolism_tick(seed, tick, state)` was tightened to honor the task contract:
  - removed the `overlay_trace_after_hint(..., observable="substrates", ...)` call, so `KarrMetabolismProcess.next_update()` can no longer consume `oracle_after_substrates` through `trace_hint`;
  - preserved the substrates + enzymes + boundEnzymes state overlay and the post-tick projection shape;
  - left production `opencell/vivarium/karr_metabolism.py` untouched.
- `_tick_dispatch()` already contained `Metabolism`; no cross-process wiring changed.
- Ensemble source note: the worktree-local `data/m1_sources/karr_native` copy does not contain `Metabolism_100ticks.mat`, but the canonical external mirror at `E:\opencell\data\m1_sources\karr_native\per_process_traces_v2_s{000..049}\Metabolism_100ticks.mat` has all 50 seeds. Beat 2 extended the existing test-side external-v2 fallback set to include `Metabolism` so `load_karr_oracle("Metabolism")` resolves to the required 50-seed v2 traces instead of the legacy single-seed replay fixture.

## Beat 3 - wire runner

- `l2_2_design_a_runner.py` already had the `Metabolism` branch in `_process_sample_process()` and the generic `run_design_a()` sample-state assembly already populated the required `substrate_wids`, `enzyme_wids`, `oracle_before_substrates`, `oracle_before_enzymes`, and `oracle_before_bound_enzymes` fields for this process.
- `_observable_wids()` did not need a Metabolism-specific special case because the generic mapping already reads `_sub_ids` and `enzyme_wids`, which is the correct surface for `KarrMetabolismProcess`.
- Added an explicit catalog test to pin the runner wiring:
  - sample process class resolves to `KarrMetabolismProcess`;
  - substrate WID count is 585;
  - enzyme / boundEnzymes WID count is 104.

## Beat 4 - inversion

- Added `tests/vivarium/test_l2_2_design_a_runner_anticheat_metabolism.py` with two dedicated falsifiers:
  - oracle-replay cheat: monkeypatched `run_oc_tick()` returns `oracle_after_substrates` verbatim, and the test asserts the runner flips the primary channel to `FAIL` with `PRIMARY_CHANNEL_ORACLE_LAUNDERING`;
  - zero-substrates cheat: monkeypatched `run_oc_tick()` returns an all-zero substrate vector, and the test asserts `FAIL` with positive primary-channel W1 and `n_nonzero_oc == 0 < n_nonzero_karr`.
- Both tests are synthetic and self-contained; they exercise the verdicting logic without depending on the external 50-seed Metabolism ensemble mirror.

## Beat 5 - smoke gate

- Pending.
