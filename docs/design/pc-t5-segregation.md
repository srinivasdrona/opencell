# Phase C Turn 5 — ChromosomeSegregation (pc-t5-segregation)

**Status**: design ready  
**Estimated wall**: 25 min  
**Karr process**: `Process_ChromosomeSegregation`

## Primary source references

- Karr extract: `docs/karr_extracts/process/08_ChromosomeSegregation.md`
- Karr MATLAB source path (from extract metadata):  
  `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeSegregation.m`
- Karr trace target:  
  `data/m1_sources/karr_native/per_process_traces/ChromosomeSegregation_100ticks.mat`

## Process summary (Karr fidelity)

Karr models chromosome segregation as a boolean rule: segregation can occur when all gating conditions are satisfied:

1. chromosome is replicated
2. chromosome is properly supercoiled
3. at least one free molecule of each segregation protein is available
4. at least `gtpCost` free GTP molecules are available

Known process parameter from fixture:

- `gtpCost = 1` GTP per segregation decision/action event.

## Scope (Karr-LIGHT v1)

This turn ships a Karr-LIGHT process that keeps Karr gating logic intact and maps the boolean completion event to continuous Vivarium state needed by downstream Phase C turns.

### In-scope

- Gated progression from `chromosome.segregation_progress` 0.0 -> 1.0.
- ATP/GTP allocation protocol compliance (this process consumes GTP via requests/allocations).
- Daughter pole position interpolation (`left` and `right`) from progress.
- Completion signaling for cytokinesis gate:
  - `chromosome.segregation_complete: bool`
  - `chromosome.cell_cycle_event: "none" | "segregation_complete"`

### Deferred to v2

- Explicit chromosome topology/decatenation mechanics (TopoIV-mediated unlinking as a mechanistic state machine).
- Distinct entropy-driven during-replication component vs post-replication protein-assisted component.
- Spatial stochasticity and per-locus position dynamics beyond two pole scalars.

## State ports and schema

New/used `chromosome` state:

- `replication_state` (`set`): read gate from pc-t2 / CellCycleCoordinator (`"idle" | "initiating" | "elongating" | "complete"`).
- `supercoiled` (`set`): read gate from pc-t3 / coordinator.
- `segregation_progress` (`accumulate`): float [0, 1], per-tick delta writer.
- `daughter_pole_positions.left` (`accumulate`): float [-1, 0], pole coordinate.
- `daughter_pole_positions.right` (`accumulate`): float [0, 1], pole coordinate.
- `segregation_complete` (`set`): completion latch.
- `cell_cycle_event` (`set`): emits `"segregation_complete"` exactly on completion tick.

Process-local substrate/enzyme ports:

- `substrates` (`accumulate`): `GTP`, `GDP`, `H`, `H2O`, `PI`.
- `protein.counts` (`accumulate`): segregation proteins from fixture:
  - `MG_470_MONOMER`, `MG_221_OCTAMER`, `MG_387_MONOMER`, `MG_384_MONOMER`.
  - `MG_203_204_TETRAMER` (topoIV) retained as a gate-aware enzyme from fixture.
- `requests.karr_chromosome_segregation.GTP` (`set`).
- `substrates_allocated.karr_chromosome_segregation.GTP` (`accumulate`).

## Algorithm (v1)

Per tick:

1. Read gating state:
   - `replication_state == "complete"`
   - `supercoiled is True`
   - each required enzyme count >= 1
   - allocated/available GTP >= `gtpCost`
2. If gated:
   - consume `gtpCost` GTP (bounded by allocation)
   - produce stoichiometric products consistent with GTP hydrolysis:
     - `GDP +1`, `PI +1`, `H +1`
   - advance progress by `segregation_rate_per_s * dt`, clamped at 1.0
3. Update daughter positions as deterministic mapping from new progress:
   - `left = -progress`
   - `right = +progress`
4. If crossing to 1.0 and not yet complete:
   - set `segregation_complete=True`
   - set `cell_cycle_event="segregation_complete"`
   Else:
   - set `cell_cycle_event="none"`
5. Always publish GTP request for next tick based on whether process can still progress.

## Trace alignment plan

`ChromosomeSegregation_100ticks.mat` in Karr native traces is expected to define the default per-tick observed rate. In local main-repo trace data, the default snapshot trajectory is flat (zero deltas across 100 ticks), consistent with gating not being satisfied early in cycle.

Validation strategy:

- Default-state 100-tick run should produce near-zero progress rate (within 10% of trace mean, i.e., 0).
- Active-gated synthetic state should show positive rate with deterministic configured `segregation_rate_per_s`.

## Test plan

Minimum tests in `tests/vivarium/test_karr_chromosome_segregation.py`:

1. process instantiates and exposes expected fixtures/indices/ports
2. one-tick gated run advances progress positively and consumes GTP
3. one-tick ungated run (replication incomplete) does not advance
4. allocation contract: allocated GTP bounds consumption/progress
5. completion semantics: progress clamps at 1.0 and emits completion event
6. 100-tick default-state rate matches Karr trace within 10% (flat-zero tolerance band)
7. no NaN/negative regressions for progress and pole positions

## Open questions

1. Final store name for event signaling (`cell_cycle_event` vs coordinator-owned event bus) may be harmonized in pc-final.
2. Whether topoIV should be mandatory in v1 gate (extract says decatenation proteins are required; current plan keeps all listed proteins as required).
