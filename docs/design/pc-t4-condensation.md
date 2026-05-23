# Phase C Turn 4 — ChromosomeCondensation (`pc-t4-condensation`)

**Status**: design ready (Karr-light v1)  
**Estimated wall**: 25 min  
**Karr process**: `Process_ChromosomeCondensation`

## Primary Sources

1. `docs/karr_extracts/process/07_ChromosomeCondensation.md` (verbatim MATLAB header)
2. `data/karr_fixtures/per_process/ChromosomeCondensation_flat.mat`
3. `data/m1_sources/karr_native/per_process_traces/ChromosomeCondensation_100ticks.mat`

Notes from fixture/traces used for calibration:
- `smcSepNt = 7130`, `smcSepProbCenter = 2800`
- SMC enzyme WIDs: `MG_213_214_298_6MER`, `MG_213_214_298_6MER_ADP`
- substrates: `ATP, ADP, PI, H2O, H`
- initial fixture pools: free enzymes `[5, 3]`, bound enzymes `[0, 78]`
- trace file has `states_before.boundEnzymes = [0, 78]` and `states_after.*` encoded as MATLAB empty (`MATLAB_empty=1`), so v1 steady-state calibration uses the available pre-state anchor.

## Why This Turn

Chromosome condensation is needed for Phase C chromosome organization. In Karr, SMC complexes bind DNA with spacing constraints and replication can displace complexes. This turn ships an aggregate Karr-light model that preserves substrate coupling and approximate binding/compaction behavior without per-loop topology.

## Scope

### In scope (v1 / light)
- New chromosome state:
  - `chromosome.smc_bound_count` (int-like count via accumulate deltas)
  - `chromosome.condensation_level` (float in `[0, 1]` via accumulate deltas)
- Aggregate SMC binding toward spacing-derived target count (`genome_length_bp / smcSepNt`)
- ATP/H2O-limited binding events with Karr allocation contract
- Condensation relaxation toward ATP- and SMC-driven target
- Loose replication coupling:
  - pause / reduced binding during fork passage or `replication_state == "elongating"`
  - optional displacement term during elongation

### Deferred to v2
- Explicit region finding and stochastic region-position sampling (`p(L)`, `p(x)`)
- Separate left/right chromosome occupancy geometry and no-overlap footprints at base resolution
- Explicit replication bubble geometry and deterministic displacement at fork coordinates
- Per-loop topology and supercoiling coupling at genomic-position level

## Ports / State Contract

### Reads
- `chromosome.smc_bound_count`
- `chromosome.condensation_level`
- `chromosome.replication_state` (optional; default `idle`)
- `chromosome.forks_passing` (optional boolean-like flag)
- `substrates` (`ATP`, `H2O` fallback)
- `substrates_allocated.karr_chromosome_condensation` (`ATP`, `H2O`)

### Writes
- `chromosome.smc_bound_count` delta (`_updater: "accumulate"`)
- `chromosome.condensation_level` delta (`_updater: "accumulate"`)
- `substrates` deltas (`ATP-`, `H2O-`, `ADP+`, `PI+`, `H+`)
- `requests.karr_chromosome_condensation.{ATP,H2O}` (`_updater: "set"`)

No `set` updater is used on per-tick writers for new shared ports.

## Substrate Consumption + Allocation

Per binding event:
- consume 1 ATP, 1 H2O
- produce 1 ADP, 1 PI, 1 H

Contract:
1. Request ATP/H2O at tick start from expected gap-to-target binding demand.
2. Read allocation from `substrates_allocated` (fallback to `substrates` if allocator absent).
3. Bound events by allocated ATP/H2O and free SMC pool.
4. Emit accumulate deltas on `substrates`.

## Karr-light Dynamics

1. Compute spacing-derived target SMC occupancy:
   - `target_bound = min(total_smc, round(genome_length_bp / smcSepNt))`
2. Compute expected binding gap and sample bounded Poisson binding events.
3. During fork passage / elongation, reduce or pause binding and optionally displace a small number of bound complexes.
4. Compute condensation target:
   - `target_condensation = clip((smc_bound_count / target_bound) * atp_activity, 0, 1)`
   - `atp_activity = ATP / (ATP + atp_half_saturation)`
5. Relax `condensation_level` toward target with first-order time constant.

## Test Plan

1. `test_process_initializes_with_fixture_defaults`
- validates WIDs, indices, and default chromosome anchors.

2. `test_one_tick_binding_and_condensation_sign`
- low starting `smc_bound_count` and high ATP should yield non-negative `smc_bound_count` delta and non-negative `condensation_level` delta.

3. `test_allocation_contract_caps_binding`
- if allocation is zero, no substrate consumption / no SMC binding.

4. `test_100_tick_steady_state_matches_trace_anchor`
- initialize from trace-before anchor (`boundEnzymes[SMC_ADP]=78`), run 100 ticks, and assert `condensation_level` final within 10% of trace-derived steady anchor.

5. `test_no_nan_or_negative_regression_100_ticks`
- run 100 ticks and assert no NaN and no negative counts for bound SMC or substrates.

6. `test_replication_pause_reduces_binding`
- compare elongation/fork-passage mode vs idle; paused mode should not bind faster.

## Open Questions

1. The current per-process trace file encodes empty `states_after` for this process; if regenerated with non-empty per-tick outputs, we should re-fit binding/relaxation constants directly from that trajectory.
2. Should v2 expose explicit SMC free/bound pools on `complex.counts` for stronger chassis mass-accounting across processes?
3. Should condensation directly gate future segregation/replication process rates in v5 coordinator wiring?
