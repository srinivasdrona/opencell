# Phase C Turn 3 — DNASupercoiling (`pc-t3-supercoiling`)

**Status**: design ready  
**Estimated wall**: 30-40 min  
**Karr process**: `Process_DNASupercoiling`

## Primary sources

- Karr extract: `docs/karr_extracts/process/06_DNASupercoiling.md`
- OpenCell fixture: `data/karr_fixtures/per_process/DNASupercoiling_flat.mat`
- Karr trace target: `data/m1_sources/karr_native/per_process_traces/DNASupercoiling_100ticks.mat`

## Scope

### v1 (Karr-light, this turn)

Implement `opencell/vivarium/karr_dna_supercoiling.py` with:

1. New chromosome scalar state: `chromosome.supercoil_density` (target steady-state around `-0.06`).
2. Stochastic per-tick supercoiling actions:
- gyrase action: introduces negative linking change (`-1` link/event in this light model)
- topoIV action: relaxes negative supercoils (`+1` link/event in this light model)
3. Coupling to `chromosome.replication_state`:
- during `elongating`, apply additional positive supercoiling pressure (fork demand), increasing effective gyrase demand.
4. ATP budgeting via `KarrAllocationStep` contract:
- write `requests.karr_dna_supercoiling.ATP`
- read `substrates_allocated.karr_dna_supercoiling.ATP`
- bound stochastic actions by allocated ATP
- emit ATP consumption as accumulate deltas on `substrates`.

### Deferred to v2

1. Full three-enzyme mechanism (explicit topoI processivity and enzyme-DNA occupancy dynamics).
2. Region-resolved LK tracking (unreplicated + 2 replicated regions) instead of single bulk supercoil-density scalar.
3. Replication-collision knockoff behavior for bound enzymes.
4. Supercoiling-dependent transcription fold-change output for gyrA/gyrB/parC/parE/topA transcription units.

## Process model (v1)

### State machine view

`supercoil_density` drives a three-regime controller:

1. **overwound** (`sigma > sigma_eq`) -> gyrase probability rises, topoIV probability falls
2. **underwound** (`sigma < sigma_eq`) -> topoIV probability rises, gyrase probability falls
3. **near_equilibrium** (around `sigma_eq = -0.06`) -> both low net drift, stochastic fluctuations only

During replication elongation, an exogenous positive-supercoiling load shifts the system toward the overwound regime, which in turn raises gyrase ATP demand.

### Event model

Per tick (`dt`):

1. Compute activity probabilities via logistic gating centered at `sigma_eq`.
2. Sample gyrase/topoIV event counts (Poisson) using fixture rates and current enzyme counts.
3. Compute ATP needed from sampled events (fixture ATP costs).
4. Cap executable events by allocated ATP.
5. Convert executed link changes into `delta_sigma` using `lk_relaxed` scaling.
6. Add replication-driven positive-supercoiling load when `replication_state == "elongating"`.
7. Emit accumulate deltas (`chromosome.supercoil_density`, `substrates.*`) and next ATP request.

## Vivarium ports and updaters

```python
"chromosome": {
    "supercoil_density": {"_default": -0.06, "_updater": "accumulate", "_emit": True},
    "replication_state": {"_default": "idle", "_updater": "set", "_emit": True},
    "supercoiled": {"_default": True, "_updater": "set", "_emit": False},
},
"protein": {
    "counts": {
        "DNA_GYRASE": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        "MG_203_204_TETRAMER": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
    }
},
"substrates": {
    "ATP": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
    "ADP": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
    "PI": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
},
"requests": {
    "karr_dna_supercoiling": {
        "ATP": {"_default": 0.0, "_updater": "set", "_emit": False},
    }
},
"substrates_allocated": {
    "karr_dna_supercoiling": {
        "ATP": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
    }
},
```

## Substrate consumption

- ATP is consumed for executed gyrase/topoIV events (fixture ATP costs).
- v1 closes ATP hydrolysis mass at minimal substrate level by emitting ATP -> ADP + PI deltas.

## Test plan

`tests/vivarium/test_karr_dna_supercoiling.py`:

1. `test_process_instantiates_with_defaults`  
   validates fixture load, enzyme/substrate IDs, and default equilibrium configuration.
2. `test_one_tick_gyrase_sign`  
   from overwound sigma, one-tick update trends negative (or requests ATP when allocation limits actions).
3. `test_allocation_contract_bounds_atp_use`  
   executed events are ATP-bounded by `substrates_allocated`; ATP delta magnitude never exceeds allocation.
4. `test_replication_elongating_increases_gyrase_request`  
   same sigma and enzymes, `elongating` state yields greater/equal ATP request than `idle`.
5. `test_100tick_steady_state_near_karr_sigma`  
   100-tick run remains within 10% of Karr target magnitude (`|-0.06|`) under steady baseline conditions.
6. `test_no_nan_or_negative_regressions`  
   no NaN/inf sigma and no negative substrate pool values under repeated updates with sufficient pools.

## Open questions

1. The v7.3 per-process trace container currently exposes fixture-like before/after snapshots but not an immediately decoded per-tick `supercoil_density` vector in Python loader paths. v1 therefore anchors the steady-state criterion to Karr's documented equilibrium sigma (`-0.06`) and fixture constants; deeper trace decoding is deferred for v2 verification hardening.
2. Full region-specific LK partitioning (downstream vs replicated loops) is deferred to keep this turn aligned with Karr-light scope and preserve chassis stability.
