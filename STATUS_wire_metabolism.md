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

- Pending.

## Beat 3 - wire runner

- Pending.

## Beat 4 - inversion

- Pending.

## Beat 5 - smoke gate

- Pending.
