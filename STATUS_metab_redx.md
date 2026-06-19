# Metabolism L2.5 No-Hints Replay Re-Diagnosis (bounds-from-substrates)

## Beat 1
Hypothesis **H is REJECTED**: enabling OC's existing bound-aware `_dynamic_update` path does not produce Karr-like tick-0 substrate deltas for ATP/ADP/ACCOA/H2O/H.

## Beat 2
Operator finding (verbatim):

> ```
> _sub_ids length: 585
> _cytosol_rows length: 225
> _cyt_row_to_sid size: 225 (includes ATP, ADP, PI, H2O, H, ACCOA, ...)
> 
> FBA v: shape=(504,), nonzero=328, max|v|=1000.000000
> info: biomass_per_s=1.09e-05, biomass_per_h=0.0392
> 
> cytosol rates (S[cyt_rows,:] @ v): shape=(225,), nonzero count=0  <-- ALL ZERO
> ```

MATLAB authoritative per-tick bound setup range:

- `Metabolism.evolveState` calls `calcGrowthRate(calcFluxBounds(this.substrates, ...))` at [data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m](E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m:1200).
- `calcFluxBounds` sets bounds from current `substrates` at lines 1367-1387 (external/internal metabolite availability), same file.

## Beat 3
`scripts/probe_metab_bounds.py` plan:

- Instantiate `KarrMetabolismProcess(dynamic_bounds=True)` to force bound-aware path.
- Build a tick-0-like `states_before["substrates"]` using known Karr values for ATP/ADP/H2O/H (plus defaults).
- Run `next_update(1.0, states_before)` and capture emitted `update["substrates"]`.
- Compare ATP/ADP/ACCOA/H2O/H against Karr expected deltas with tolerance `+/-10`.
- Print a strict PASS/FAIL and next-step fix shape.

## Beat 4
Two ways this probe can mislead:

- It uses known tick-0 substrate values for key metabolites (not a full direct trace load), so if hidden non-key pools materially affect bounds, mismatch can be amplified.
- `_dynamic_update` seeds `_prev_shared` on first call (delta=0 construction), so this probe tests current OC dynamic semantics; MATLAB may effectively consume already-updated per-tick demand state before solve.

## Beat 5
Verification outcome from probe output:

- ATP expected `+3626`, observed `0`
- ADP expected `-3622`, observed `0`
- ACCOA expected `-3622`, observed `0`
- H2O expected `+9195`, observed `0`
- H expected `-11323`, observed `0`

Result: **FAIL/REJECTED**; next-step fix is **not** "route static gate to existing `_dynamic_update` as-is."

## Hypothesis test result
**REJECTED.**

Probe command:

```bash
wsl bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python scripts/probe_metab_bounds.py"
```

Probe artifact: [probe_metab_bounds.py](E:/opencell/scripts/probe_metab_bounds.py)

Key evidence: all five target substrate deltas were zero from dynamic path, far outside `+/-10` tolerance.

## Fix shape
Actual Karr mechanism in MATLAB is not "write back `S @ v * dt` for cytosol rows." It is:

- Solve LP with per-tick bounds from `calcFluxBounds(this.substrates, ...)`.
- Update substrates by **specific flux partitions**:
  - external exchange uptake term
  - internal exchange recycling term
  - `metabolismNewProduction * growth * stepSizeSec` term
  - unaccounted ATP hydrolysis term

Alternative fix shape for OC L2.5 replay:

1. In [karr_metabolism.py](E:/opencell/opencell/vivarium/karr_metabolism.py:352), keep `dynamic_bounds` behavior unchanged.
2. Replace `enable_static_substrate_writeback` wiring target so it no longer uses current static `S@v` path; introduce a replay-specific update function (for example `_replay_update`) adjacent to [karr_metabolism.py](E:/opencell/opencell/vivarium/karr_metabolism.py:359).
3. In that replay path, reuse bound setup arithmetic from `_dynamic_update` (`compute_bounds(...)`, optional override solves), but emit substrate deltas via MATLAB-style partition terms (external/internal exchange + growth production + ATP hydrolysis), not aggregate `S[self._cytosol_rows,:] @ v`.
4. L2 replay test override remains projection to cytosol 585 (`np.arange(585)`), but should assert against replay-path emissions rather than static `S@v` writeback behavior.

## MATLAB anchor
Authoritative bounds-from-substrates quote (lines 1367-1376):

```matlab
1367:            %external metabolite availability
1368:            if applyExternalMetaboliteBounds
1369:                upperBounds(this.fbaReactionIndexs_metaboliteExternalExchange) = min(...
1370:                    upperBounds(this.fbaReactionIndexs_metaboliteExternalExchange), ...
1371:                    substrates(this.substrateIndexs_externalExchangedMetabolites, this.compartmentIndexs_extracellular) / this.stepSizeSec);
1372:                
1373:                cellDryMass = sum(this.mass.cellDry);
1374:                lowerBounds(this.fbaReactionIndexs_metaboliteExternalExchange) = ...
1375:                    max(lowerBounds(this.fbaReactionIndexs_metaboliteExternalExchange), ...
1376:                    fbaReactionBounds(this.fbaReactionIndexs_metaboliteExternalExchange, 1) * cellDryMass);
```

And the per-tick solve call (lines 1202-1203):

```matlab
1202:            [this.metabolicReaction.growth, this.metabolicReaction.fluxs, fbaReactionFluxs] = ...
1203:                this.calcGrowthRate(this.calcFluxBounds(this.substrates, this.enzymes, this.fbaReactionBounds, this.fbaEnzymeBounds));
```
