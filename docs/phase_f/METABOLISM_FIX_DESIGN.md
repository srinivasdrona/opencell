# Metabolism L2.1/L2.2 Fix — Design Document (Day-37)

**Status:** Root-cause diagnosed; multi-day implementation needed.

## TL;DR

OC's Metabolism implements FBA correctly but is missing **all** of Karr's
post-FBA substrate writeback steps. Karr's `evolveState`
(`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m:1213-1231`)
runs 4 substrate updates after FBA:

1. **Nutrient uptake**: `substrates[external, extracellular] -= round(flux[external_exchange] × step)`
2. **Recycled metabolites**: `substrates[internal] += round(flux[internal_exchange])`
3. **New biomass**: `substrates += round(metabolismNewProduction × growth × step)`
4. **Unaccounted energy**: `substrates[atp_hydrolysis] += [-1,-1,1,1,1] × round(unaccounted × growth × step)`

OC's `_static_update` returns only `metabolic_reaction.fluxs` — no substrate
deltas. OC's `_dynamic_update` does a partial cytosol-only `S @ v * step`
writeback (no integer rounding, no extracellular update, no biomass production
update, no unaccounted energy step).

Result: OC's substrate distribution diverges from Karr's by Karr's full
substrate writeback (148,121 molecules at tick 0 in seed 000). This is the
**L2.2 W1=171.39 on substrates** failure.

## Empirical confirmation

`scripts/probe_metab_substrate_update.py` runs FBA at tick 0 with Karr's
pre-state and applies Karr's 4 update steps without stochastic rounding:

```
Karr substrate delta at tick 0: nonzero=102, sum_abs=148,121
  Cytosol-only nonzero: 45, sum_abs=42,753
  Extracellular-only nonzero: 54, sum_abs=105,364

OC (current static mode):  produces 0 substrate delta
OC (dynamic_bounds=True):  41 cytosol-only float deltas, sum_abs=0 (all <0.5)
OC (4-step probe, no rounding): captures partial cytosol; off-by-13K on H2O/H/O2 because
  static FBA bounds underpower nutrient uptake reactions
```

The discrepancies in the probe (max diff 13,198 on H2O extracellular) come
from OC's static FBA using `model.lb/ub` rather than Karr's dynamic bounds
from `calcFluxBounds(substrates, enzymes, ...)`. So we need BOTH:

- **Dynamic bounds** (via `cfb.compute_bounds` — already implemented in
  `_dynamic_update`)
- **Full 4-step Karr substrate writeback** (NOT implemented anywhere)

## Implementation plan

### Step 1: Add stochasticRound helper (~30 min)

Reuse the `_Mcg16807` MATLAB-compatible RNG pattern from
`opencell/vivarium/karr_protein_decay_light.py:28-49`. Seed from `rng_seed`
process parameter.

### Step 2: Load Karr fixture data in `__init__` (~30 min)

In `KarrMetabolismProcess.__init__`, load from `Metabolism_flat.mat`:
- `substrateIndexs_externalExchangedMetabolites` (124,)
- `substrateIndexs_internalExchangedMetabolites` (42,)
- `substrateIndexs_atpHydrolysis` (5,)
- `fbaReactionIndexs_metaboliteExternalExchange` (124,)
- `fbaReactionIndexs_metaboliteInternalExchange` (42,)
- `metabolismNewProduction` (585, 3)
- `unaccountedEnergyConsumption` (scalar)

Convert MATLAB 1-based indices to 0-based.

### Step 3: Implement `_apply_karr_substrate_updates` method (~2-3 h)

```python
def _apply_karr_substrate_updates(
    self,
    *,
    timestep: float,
    v_645: np.ndarray,       # FBA reaction fluxes (645,)
    growth: float,           # growth rate per second
) -> np.ndarray:             # returns substrate delta (585, 3)
    delta = np.zeros((585, 3), dtype=np.float64)
    # Step 1: nutrient uptake (Metabolism.m:1213-1215)
    nutrient_flow = v_645[self._fba_idx_external] * timestep
    delta[self._sub_idx_external, self._EXTRACELLULAR] -= self._rng.stochastic_round(nutrient_flow)
    # Step 2: internal exchange (Metabolism.m:1218-1220)
    internal_flow = v_645[self._fba_idx_internal]
    delta[self._sub_idx_internal, self._CYTOSOL] += self._rng.stochastic_round(internal_flow)
    # Step 3: new biomass (Metabolism.m:1223-1225)
    biomass_flow = self._metabolism_new_production * growth * timestep
    delta += self._rng.stochastic_round(biomass_flow)
    # Step 4: unaccounted energy (Metabolism.m:1228-1231)
    unaccounted_qty = self._unaccounted_energy * growth * timestep
    atp_signs = np.array([-1, -1, 1, 1, 1], dtype=np.int64)
    delta[self._sub_idx_atp_hydrolysis, self._CYTOSOL] += atp_signs * self._rng.stochastic_round(unaccounted_qty)
    return delta
```

### Step 4: Wire into `_static_update` and `_dynamic_update` (~1 h)

Both paths compute `v_645` and `growth`. Add:
```python
karr_delta_585x3 = self._apply_karr_substrate_updates(
    timestep=timestep, v_645=v_645, growth=growth_per_s
)
# Project to single-compartment substrate update for OC's flat substrates port
substrate_delta = {}
for sid_idx, sid in enumerate(self._sub_ids):
    total = karr_delta_585x3[sid_idx, :].sum()
    if abs(total) > 0:
        substrate_delta[sid] = float(total)
return {
    "substrates": substrate_delta,
    "metabolic_reaction": {...},  # existing
}
```

**OR** keep per-compartment if OC's substrates port grows to 585×3
(architectural decision — needs operator input).

### Step 5: Verify (~2 h)

- L2.1 strict-rubric: Metabolism should move COINCIDENTAL → GENUINE
- L2.2 design_a runner: Metabolism should move VERIFIED_FAIL → VERIFIED_GENUINE
  with W1 << 171.39 on substrates
- No regression in chassis tests (`tests/vivarium/test_karr_central_dogma_chassis.py`)
- No regression in per-process Metabolism tests (`test_karr_metabolism.py`)

### Step 6: L2.5 unlock check (~30 min)

Run L2.5 honest pairs involving Metabolism (Day-35 SS sweep had Seg+Metab,
Cond+Metab, HostInt+Metab all FAILing). With Metabolism fixed, expect these
to PASS. ~23 L2.5 pairs unlock.

## Total estimate

**6-8 hours of focused engineering**. Most of the complexity is:
- Index handling (MATLAB 1-based ↔ Python 0-based, especially for the 124
  external and 42 internal exchange index arrays)
- Compartment semantics (cytosol vs extracellular)
- Float-to-int stochasticRound consistency with Karr's RandStream

## Risks

1. **OC's `substrates` port is single-compartment** (just substrate WID → count),
   while Karr's substrates are (585, 3) compartmented. Summing across
   compartments may lose information that L2.5 pairs need. Architectural
   call: do we expand OC's substrates port? Or do we project to cytosol?
2. **Other chassis processes** read substrates and may expect the old
   (no-writeback) behavior. Need to audit M2/M3 chassis code path.
3. **Seed consistency**: Karr's RandStream is per-cell-cycle, not per-tick.
   OC's `_Mcg16807` may need similar handling.

## Cross-ladder impact

If implemented correctly:
- L2.1 strict-rubric GENUINE: 16 → 17 (Metabolism moves up)
- L2.2 in-scope GREEN: 10 → 11 (Metabolism moves up)
- L2.5 honest pairs: 15 → ~38 (23 Metabolism-pair unlocks if substrate
  contention is now accurate)

This is the single highest-leverage biology fix on the entire roadmap.

## Provenance

- Karr source: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m` lines 1200-1258
- OC source: `opencell/vivarium/karr_metabolism.py` lines 340-510
- Empirical probe: `scripts/probe_metab_substrate_update.py`
- Mode comparison: `scripts/probe_metab_dynamic_bounds.py`
- Fixture audit: `scripts/probe_metab_fixture.py`
- L2.5 pair count: `scripts/probe_metab_pair_count.py`
- Trigger: operator Day-37: "let's tackle metabolism as that is the largest,
  messiest and most important process. let's fix it properly across l2.1 and l2.2"
