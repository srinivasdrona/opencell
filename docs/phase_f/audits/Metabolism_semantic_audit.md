# Metabolism Semantic Audit (Worked Example)

Process: `Metabolism`

Row file:
- `data/schemas/per_process_wiring/Metabolism.yaml`

MATLAB files:
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`

OC files:
- `opencell/vivarium/karr_metabolism.py`
- `opencell/m1/karr_metabolism_writeback.py`
- `opencell/m1/karr_metabolism.py`
- `opencell/vivarium/karr_request_calculators.py`
- `opencell/vivarium/karr_allocation_step.py`
- `opencell/m1/calc_flux_bounds.py`
- `opencell/m1/compartmented.py`
- `opencell/vivarium/karr_composite.py` (ordering evidence)

Scope policy:
- Exemplar-scoped completeness (`Metabolism.yaml` notes: "example shape, not a full 585-substrate enumeration").

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| MET-S1-00 | S1 | Row explicitly declares non-exhaustive exemplar scope (`Metabolism.yaml:10-11`). | MATLAB consume/produce surfaces are broader than seven exemplars (`Metabolism.m:1213-1231`). | OC writeback operates on vector index sets, not just exemplars (`karr_metabolism_writeback.py:55-61`, `127-150`). | VERIFIED | `judgment=required` applied; completeness evaluated at declared exemplar scope. |
| MET-S1-01 | S1 | `consume_stoichiometry` includes `GLC` and `O2` in extracellular compartment (`Metabolism.yaml:112-137`). | Nutrient uptake subtracts external exchange flux from extracellular pool (`Metabolism.m:1213-1215`). | Step 1 subtracts rounded external flows from `EXTRACELLULAR` column (`karr_metabolism_writeback.py:127-131`). | VERIFIED | Exemplar consume completeness holds for external uptake claims. |
| MET-S1-02 | S1 | `consume_stoichiometry` includes `ATP` cytosol hydrolysis claim (`Metabolism.yaml:190-203`). | ATP consumed in hydrolysis sign vector `[-1; -1; 1; 1; 1]` (`Metabolism.m:1228-1231`). | ATP hydrolysis signs include ATP as negative entry (`karr_metabolism_writeback.py:45`, `143-150`). | VERIFIED | Consume completeness holds for ATP exemplar. |
| MET-S2-01 | S2 | Every consume exemplar has OC anchor in writeback steps (`Metabolism.yaml:124-203`). | Consume paths are in evolveState steps 1 and 4 (`Metabolism.m:1213-1215`, `1228-1231`). | Anchored OC consume paths exist for each exemplar (`karr_metabolism_writeback.py:127-131`, `143-150`). | VERIFIED | No fabricated consume exemplar found in row scope. |
| MET-S3-01 | S3 | Produce exemplars include `ADP`, `PI`, `H` cytosol (`Metabolism.yaml:243-282`). | Hydrolysis products produced in step 4 (`Metabolism.m:1228-1231`). | Step 4 sign vector yields product-side deltas for these WIDs (`karr_metabolism_writeback.py:45`, `143-150`). | VERIFIED | Produce completeness/fabrication holds for hydrolysis products. |
| MET-S3-02 | S3 | Produce exemplars include `LIPOATE` and `THF` (`Metabolism.yaml:217-242`). | New-metabolite production added in step 3 (`Metabolism.m:1223-1225`). | Step 3 adds rounded biomass-flow matrix (`karr_metabolism_writeback.py:138-142`). | VERIFIED | Produce completeness/fabrication holds for biomass exemplars. |
| MET-S3-03 | S3 | Row includes bidirectional internal-exchange exemplars (`AMP`, `GMP`) on consume+produce surfaces (`Metabolism.yaml:138-164`, `204-230`). | Internal exchange adds signed rounded flux (`Metabolism.m:1218-1220`). | OC mirrors signed rounded internal exchange without step multiplier (`karr_metabolism_writeback.py:132-137`). | VERIFIED | `judgment=required` due sign-dependent consume/produce direction. |
| MET-S4-01 | S4 | External consume formula is `stochasticRound(v[external]*step)` (`Metabolism.yaml:115`, `128`). | Step 1 uses stochasticRound(external flux * stepSizeSec) (`Metabolism.m:1213-1215`). | Step 1 uses identical multiplication then stochastic round (`karr_metabolism_writeback.py:127-131`). | VERIFIED | Formula skeleton matches. |
| MET-S4-02 | S4 | Internal exchange exemplar formula has no `stepSizeSec` factor (`Metabolism.yaml:141`, `154`). | Step 2 applies stochasticRound(internal flux) without step multiplier (`Metabolism.m:1218-1220`). | Step 2 explicitly keeps no-step multiplier (`karr_metabolism_writeback.py:135-137`). | VERIFIED | Formula match confirmed. |
| MET-S4-03 | S4 | Hydrolysis formula uses growth-coupled scalar and sign vector (`Metabolism.yaml:193`, `245`, `258`, `271`). | Step 4 applies one rounded scalar times `[-1;-1;1;1;1]` (`Metabolism.m:1228-1231`). | OC computes one rounded scalar and multiplies by `ATP_HYDROLYSIS_SIGNS` (`karr_metabolism_writeback.py:45`, `145-150`). | VERIFIED | Formula match confirmed. |
| MET-S4-04 | S4 | Clip behavior anchored as evolveState metabolite-row max-zero (`Metabolism.yaml:455-459`). | Step 5 clips metabolite rows to nonnegative (`Metabolism.m:1235-1253`). | OC clip step recomputes delta after row-wise `max(0)` (`karr_metabolism_writeback.py:152-160`). | VERIFIED | Matches known A3b grep anchor. |
| MET-S5-01 | S5 | Row compartment routing claims external uptake at extracellular and hydrolysis in cytosol (`Metabolism.yaml:285-314`). | MATLAB writes step1 to extracellular and step2/4 to cytosol (`Metabolism.m:1213-1215`, `1218-1220`, `1228-1231`). | OC writeback targets `EXTRACELLULAR=1` and `CYTOSOL=0` consistently (`karr_metabolism_writeback.py:39-42`, `130`, `136`, `148`). | VERIFIED | Internal routing tuple match holds before projection. |
| MET-S6-01 | S6 | Allocator mode states `karr=allocation`, `oc_current=bypass` (`Metabolism.yaml:81-84`). | MATLAB always computes requirements/allocations each tick before process evolve (`Simulation/evolveState.m:24-37`, `63-70`). | OC default is allocator bypass (`use_allocator_budget=False`) and request calculator emits zeros when bypassed (`karr_metabolism.py:131`, `166`; `karr_request_calculators.py:810-812`). | VERIFIED | Row truthfully states engagement-mode split. |
| MET-S6-A1 | S6 | Row records A1 request-formula comparison surface (`Metabolism.yaml:85-93`, `544`). | Allocation uses `allocations = max(0, fix(requirements .* tmp(:,...)))` (`Simulation/evolveState.m:36-37`) with requirements from `calcResourceRequirements_Current` (`Metabolism.m:1188-1196`). | OC request path uses `_last_allocation_demand` (or zero in bypass) and allocator step scales/floors requests (`karr_request_calculators.py:810-820`; `karr_allocation_step.py:246-255`). | CODE_DEVIATES | A1 surfaced: row is accurate about MATLAB-vs-OC difference. |
| MET-S6-A2 | S6 | Row known deviations include ordering check A2 (`Metabolism.yaml:545`), with note on MATLAB hard constraint (`Metabolism.yaml:417`). | MATLAB picks random process order each tick with constraint tRNAAminoacylation before Translation (`Simulation/evolveState.m:48-57`). | OC chassis wiring uses fixed process/step maps and explicit flow edges; no `randperm` equivalent in runtime path (`karr_composite.py:917-949`). | CODE_DEVIATES | A2 surfaced: OC scheduling semantics differ from MATLAB randomization contract. |
| MET-S6-A3 | S6 | Row deviation says Karr LP bounds source is allocation; OC current source is internal pool (`Metabolism.yaml:529-541`, `546`). | MATLAB sets `mod.substrates = allocation` before `mod.evolveState`, then `calcFluxBounds(this.substrates,...)` consumes that allocated state (`Simulation/evolveState.m:63-70`; `Metabolism.m:1200-1204`, `1318-1321`). | OC computes bounds from internal `_sub_state` before allocation clipping; allocated budget is applied only after substrate delta emission (`karr_metabolism.py:495-505`, `592-603`). | CODE_DEVIATES | A3 surfaced: row correctly encodes the deviation. |
| MET-S5-A4 | S5 | Row deviation states shared-pool projection merges compartments (`Metabolism.yaml:542`, `548`). | MATLAB writeback/clip acts on full `substrates(585,3)` compartment matrix (`Metabolism.m:1223-1253`). | OC emits shared-store delta via `project_to_flat_per_wid` summing across compartments (`karr_metabolism_writeback.py:164-177`; `karr_metabolism.py:462`, `573`). | CODE_DEVIATES | A4 surfaced: row correctly captures compartment-loss behavior at output surface. |

## Aggregate

- VERIFIED: 13
- ROW_WRONG: 0
- CODE_DEVIATES: 4
- MISSING: 0

## Priority-1 Fixes

Priority-1 fixes: none.

## Known-Deviation Mapping (A1-A4)

- A1 -> `MET-S6-A1`
- A2 -> `MET-S6-A2`
- A3 -> `MET-S6-A3`
- A4 -> `MET-S5-A4`

## Auditor Discretion Used

- `MET-S1-00` (exemplar-scope completeness policy)
- `MET-S3-03` (sign-dependent internal exchange consume/produce labeling)

