# Phase C Turn 9 — Cytokinesis (`pc-t9-cytokinesis`)

**Status**: design ready  
**Estimated wall**: 30 min  
**Karr process**: `Process_Cytokinesis`

## Primary Source Reference

- Karr extract: `docs/karr_extracts/process/26_Cytokinesis.md`
- OpenCell fixture: `data/karr_fixtures/per_process/Cytokinesis_flat.mat`
- Karr trace target: `data/m1_sources/karr_native/per_process_traces/Cytokinesis_100ticks.mat`

Notes from source availability:
- The requested extract path `docs/karr_extracts/process/10_Cytokinesis.md` is not present in this worktree.
- `26_Cytokinesis.md` is the local Cytokinesis extract.
- The available 100-tick trace snapshots for this process show zero net per-tick deltas in captured `substrates` and `enzymes`; we therefore use trace window length (`n_ticks=100`) as the light-rate calibration anchor and document this inference explicitly.

## Scope

### In-scope (Karr-light v1)

- New process: `opencell/vivarium/karr_cytokinesis.py`
- Gate cytokinesis progress on:
  - `cell.ftsz_ring_complete == True`
  - `chromosome.segregation_progress >= 1.0`
- New cell-cycle state:
  - `cell.division_progress` (`0.0..1.0`, accumulate deltas)
  - `cell.division_complete` (bool event flag)
- Per-tick progress uses trace-window calibrated rate (`~1/100` progress per active tick).
- GTP-limited progress using `KarrAllocationStep` contract:
  - write `requests.karr_cytokinesis.GTP`
  - read `substrates_allocated.karr_cytokinesis.GTP`
  - consume from `substrates.GTP`

### Deferred to v2

- Explicit FtsZ ring polygon state machine (bind/bend/dissociate cycles per edge).
- Per-monomer GTP/GDP filament cycling (`MG_224_*` species-level dynamics).
- Geometry-coupled constriction (pinched diameter evolution from `CellGeometry` state).
- Stochastic Li et al.-style edge-level mechanics.

## Algorithm (v1)

1. Read `division_progress` and clamp to `[0, 1]`.
2. Evaluate gates (`ftsz_ring_complete` and `segregation_progress`).
3. If either gate is false, emit zero progress and request `0 GTP`.
4. If both gates true and not yet complete:
   - compute desired progress increment: `active_division_rate_per_s * dt`
   - convert to GTP request via `progress_per_gtp`
   - bound actual progress by allocated GTP
   - emit accumulate deltas:
     - `cell.division_progress += delta`
     - `substrates.GTP -= gtp_used`
5. If resulting progress reaches `1.0`, set `cell.division_complete = True`.

## State Ports and Updaters

```python
cell:
  ftsz_ring_complete: set bool input gate
  division_progress: accumulate float [0,1]
  division_complete: set bool event/state

chromosome:
  segregation_progress: set float input gate

substrates:
  GTP: accumulate (consumption delta)

requests:
  karr_cytokinesis:
    GTP: set (required by allocation contract)

substrates_allocated:
  karr_cytokinesis:
    GTP: accumulate (allocation readback)
```

## Substrate Consumption

- Minimal v1 energetic coupling: `GTP` is consumed proportional to progress advancement.
- `GTP` usage is bounded by allocation (`substrates_allocated`) when provided.
- If allocation store is absent/unwired, process safely falls back to current substrate availability.

## Rate Calibration

- Trace metadata reports `n_ticks=100`; v1 maps one full cytokinesis completion to this active window.
- Default active progress rate: `1.0 / 100.0` per second at `dt=1s`.
- This is an explicit Karr-light inference because captured trace snapshots have zero net deltas for exposed `substrates/enzymes` in this fixture context.

## Test Plan

At minimum in `tests/vivarium/test_karr_cytokinesis.py`:

1. Process instantiates with defaults and exposes required ports.
2. Dependency gating: no progress if either gate is false.
3. Completion event: progress reaches 1.0 and `division_complete` flips true.
4. Allocation contract: progress/consumption bounded by allocated `GTP`.
5. 100-tick rate match: active gated run tracks expected trace-window progress trajectory.
6. Numerical safety: no NaN, no negative progress, no over-1 progress.

## Open Questions

1. Should `division_complete` be represented as a one-tick pulse vs persistent bool?
2. Should v1 also emit `PI/H` byproducts for explicit GTP hydrolysis mass closure, or keep energy-sink simplification aligned with other Phase B light processes?
3. Should chassis v4 wiring include this process immediately, or defer integration to `build_karr_chassis_v5` as originally planned for Phase C final integration?
