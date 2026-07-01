# Cytokinesis Semantic Wiring Audit

## Header
- Process name: `Cytokinesis` (`cytokinesis`)
- Audited files: `data/schemas/per_process_wiring/Cytokinesis.yaml`; `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Cytokinesis.m`; `opencell/vivarium/karr_cytokinesis.py`; `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`; `opencell/vivarium/karr_composite.py`
- Scope policy: `strict completeness` (MATLAB consume/produce claims are treated as complete within audited Cytokinesis executable surfaces, including lifecycle + per-tick methods)
- Header note: full audit (not `PARTIAL`)

## Deliberate Action Prefix (v2)
- Beat 1 (contract): Verify that each row-level Cytokinesis semantic claim is true against executable MATLAB and OC behavior, not anchor presence alone. Done means another auditor can replay the same claims and obtain the same verdict labels from the cited lines.
- Beat 2 (surface): Row surface is `data/schemas/per_process_wiring/Cytokinesis.yaml`; MATLAB surfaces are `.../process/Cytokinesis.m` and `.../@Simulation/evolveState.m`; OC surfaces are `opencell/vivarium/karr_cytokinesis.py` plus `opencell/vivarium/karr_composite.py` for ordering context. Suspect pattern called out before auditing: OC embeds request emission inside `next_update`, so allocator-timing attribution can be misread without checking scheduler/flow context.
- Beat 3 (expected outcome): Produce one claim table (S1-S6) with only `VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, `MISSING`, then aggregate counts and Priority-1 remediations.
- Beat 4 (invert / pre-mortem): Worst false-pass mode is to mark request semantics as matched by reading only port schemas while missing that MATLAB request formula and OC request formula differ; this would hide a real divergence behind shared `requests`/`substrates_allocated` wiring.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Design Contract (Revision Minimum)
Semantic truth being checked: the Cytokinesis row must faithfully represent MATLAB-vs-OC consume/produce sets, formulas, compartment tuples, and allocator engagement semantics at claim level.

## Decision Ledger
Decision D1
- Question: Completeness policy for S1/S3?
- Options considered: exemplar-scoped completeness; strict completeness.
- Chosen option: strict completeness.
- Rationale: row prose (`Small substrate row...only substrate channel`) is declarative, not exemplar-qualified, so omissions should count.
- Beat-4 inversion: strict policy could over-penalize if row was intended as non-exhaustive.
- Falsifier: explicit non-exhaustive scope text in row.

Decision D2
- Question: How to classify request-formula mismatch?
- Options considered: `ROW_WRONG`; `CODE_DEVIATES`.
- Chosen option: `CODE_DEVIATES`.
- Rationale: row explicitly states MATLAB and OC request formulas differ and names both formula families.
- Beat-4 inversion: could hide a row ambiguity by overusing `CODE_DEVIATES`.
- Falsifier: if row text failed to state both sides concretely, relabel to `ROW_WRONG`.

Decision D3
- Question: Compartment tuple attribution when Cytokinesis local vectors are compartment-implicit?
- Options considered: force `ROW_WRONG`; keep `VERIFIED` with flagged discretion.
- Chosen option: `VERIFIED` with `judgment=required`.
- Rationale: executable writes are tuple-stable across both sides, but cytosol labeling is inferred via mapping surfaces.
- Beat-4 inversion: implicit-compartment assumptions could mask a hidden projection.
- Falsifier: evidence of non-cytosolic tuple mapping for these WIDs in runtime mapping.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| CYTOKINESIS-S1-01 | S1 | Consume set is just `H2O` (`Cytokinesis.yaml:120-132`) and process notes claim only PI/H2O/H substrate channel (`Cytokinesis.yaml:12`). | `evolveState` consumes only water (`Cytokinesis.m:224,229`); lifecycle resource accounting also uses water only on consume side (`Cytokinesis.m:152`). | Hydrolysis consume path decrements only `water_wid` (`karr_cytokinesis.py:578`). | VERIFIED | Strict completeness satisfied within audited scope. |
| CYTOKINESIS-S2-01 | S2 | Row consume entry `H2O@cytosol` is backed by OC hydrolysis anchor (`Cytokinesis.yaml:121-131`). | Hydrolysis branch requires and consumes water per successful edge (`Cytokinesis.m:223-231`). | `_phase_hydrolyze_and_bend` checks `water_available` then subtracts water delta (`karr_cytokinesis.py:574,578`). | VERIFIED | Real OC consume path exists. |
| CYTOKINESIS-S3-01 | S3 | Produce set is `PI`, `H` (`Cytokinesis.yaml:133-155`). | Hydrolysis produces phosphate + hydrogen (`Cytokinesis.m:230-231`); lifecycle byproducts are same species (`Cytokinesis.m:153-154`). | OC hydrolysis produces `pi_wid` and `hydrogen_wid` deltas (`karr_cytokinesis.py:579-580`). | VERIFIED | Strict completeness satisfied. |
| CYTOKINESIS-S3-02 | S3 | Each row produce entry maps to OC helper `_phase_hydrolyze_and_bend` (`Cytokinesis.yaml:141-155`). | Produce writes occur in hydrolysis branch (`Cytokinesis.m:229-231`). | OC emits positive substrate deltas for both products (`karr_cytokinesis.py:579-580,404-408`). | VERIFIED | No fabricated row produce entry found. |
| CYTOKINESIS-S4-01 | S4 | Hydrolysis stoich formula is `2 * numFtsZSubunitsPerFilament * nHydrolyzedEdges` (`Cytokinesis.yaml:123,136,147`). | Per successful edge, `n = 2 * numFtsZSubunitsPerFilament`; consume/produce uses exactly `n` (`Cytokinesis.m:223-231`). | `hydrolysis_cost = 2 * numFtsZSubunitsPerFilament` and per-success deltas use that cost (`karr_cytokinesis.py:572-580`). | VERIFIED | Formula family match (hydrolysis stoichiometry). |
| CYTOKINESIS-S4-02 | S4 | Geometry helper family is claimed as corresponding MATLAB/OC pinch-diameter evolution (`Cytokinesis.yaml:70-72,214-242`). | `calcNextPinchedDiameter`: `flooredDiameter`, `newDiameter`, `result = new + (old - floored)`, clamp-to-zero (`Cytokinesis.m:271-283`). | `calc_next_pinched_diameter` uses same operation sequence and clamp (`karr_cytokinesis.py:653-658`). | VERIFIED | Formula family match (bounds transform / clipping). |
| CYTOKINESIS-S4-03 | S4 | Row states request formulas differ: MATLAB polymer-pool formula vs OC geometry-gated hydrolysis-opportunity formula (`Cytokinesis.yaml:98-101,278`). | Request formula is `numFtsZSubunitsPerFilament * enzymes(ftsZ_GTP_polymer)` (`Cytokinesis.m:168-169`). | Request formula is `2 * numFtsZSubunitsPerFilament * max(0, potential_hydrolysis_edges)` with segregation/pinched gating (`karr_cytokinesis.py:491-503`). | CODE_DEVIATES | Row correctly documents real MATLAB-vs-OC formula divergence. |
| CYTOKINESIS-S5-01 | S5 | Routing claims: `H2O` consumed in cytosol; `PI`,`H` produced in cytosol; no row mismatch flags (`Cytokinesis.yaml:156-171`). | Writes target only Cytokinesis substrate indices for water/phosphate/hydrogen (`Cytokinesis.m:77-81,229-231`), and simulation writes back on process global-compartment indices (`@Simulation/evolveState.m:63-73`). | OC routes only `water_wid`, `pi_wid`, `hydrogen_wid` through `substrates` updates (`karr_cytokinesis.py:578-580,404-408`). | VERIFIED | `judgment=required` (cytosol tuple label is mapping-derived, not explicit literal in process code). |
| CYTOKINESIS-S5-02 | S5 | Row claims `shared_pool_projection_merges_compartments: false` (`Cytokinesis.yaml:276`). | MATLAB path performs direct indexed writeback; no sum/flatten merge in Cytokinesis path (`@Simulation/evolveState.m:63-73`). | OC emits direct per-WID deltas; no projection/merge operator in Cytokinesis updater (`karr_cytokinesis.py:404-408,578-580`). | VERIFIED | Explicit projection/merge check passed; no merge behavior found in audited surfaces. |
| CYTOKINESIS-S6-01 | S6 | Allocator mode is `allocation` on both sides and OC consumes `substrates_allocated` (`Cytokinesis.yaml:93-97`). | Simulation computes `requirements`/`allocations`, sets `mod.substrates = allocation`, then process consumes and writes net delta (`@Simulation/evolveState.m:31-37,69-73`). | OC exposes `requests` + `substrates_allocated` ports and reads allocated water before hydrolysis (`karr_cytokinesis.py:316-325,343-360,574`). | VERIFIED | Allocator participation mode matches request/grant pattern class. |
| CYTOKINESIS-S6-02 | S6 | Row states MATLAB has dedicated lifecycle resource method while OC does not (`Cytokinesis.yaml:35-51,280`). | `calcResourceRequirements_LifeCycle` exists and computes lifecycle bm/byproducts (`Cytokinesis.m:138-154`). | OC class has no dedicated lifecycle method; logic is only in per-tick `next_update` family (`karr_cytokinesis.py:330-614`). | CODE_DEVIATES | Row correctly attributes divergence. |
| CYTOKINESIS-S6-03 | S6 | Ordering constraint is soft-after ChromosomeSegregation via state gate, not hard scheduler rule (`Cytokinesis.yaml:189-195`). | Process order is randomized except a different hard exception; Cytokinesis itself gates on `chromosome.segregated` (`@Simulation/evolveState.m:48-57`; `Cytokinesis.m:174-176`). | OC gates execution on `_segregated` and has no explicit hard flow edge from `karr_chromosome_segregation` to `karr_cytokinesis` (`karr_cytokinesis.py:348-361,479-483`; `karr_composite.py:2335-2358`). | VERIFIED | `judgment=required` (engine-level process/step scheduling semantics are inferred from flow/topology evidence). |
| CYTOKINESIS-S6-04 | S6 | Row notes legacy zero `GTP` request key is preserved in OC while MATLAB requests only water (`Cytokinesis.yaml:12,279`). | MATLAB current request writes only water (`Cytokinesis.m:166-169`). | OC schema includes `GTP` request slot and `next_update` sets it to `0.0` every tick (`karr_cytokinesis.py:318,370`). | CODE_DEVIATES | Row accurately captures compatibility-key divergence. |

## Aggregate Counts
- VERIFIED: 10
- ROW_WRONG: 0
- CODE_DEVIATES: 3
- MISSING: 0

## Priority-1 Fixes
Priority-1 fixes: none

## Known-Deviation Mapping
- KD1 (request formula family divergence): `CYTOKINESIS-S4-03`
- KD2 (legacy zero GTP request key in OC): `CYTOKINESIS-S6-04`
- KD3 (separate lifecycle method absent in OC): `CYTOKINESIS-S6-02`

## Auditor Discretion List
- `CYTOKINESIS-S5-01` (`judgment=required`)
- `CYTOKINESIS-S6-03` (`judgment=required`)

## Risks
- R1: OC allocator timing for Cytokinesis requests is embedded in a process rather than a dedicated request step, so same-tick vs next-tick request consumption remains runtime-engine sensitive without a targeted execution trace.
- R2: Cytosol compartment labeling is indirect in the audited process files (index/mapping mediated), so tuple attribution depends on mapping invariants outside Cytokinesis.m literal declarations.

## Verification (Beat 5)
- Expected outcome (Beat 3): complete S1-S6 claim table with constrained verdict vocabulary and reproducible attributions.
- Actual outcome: delivered 13 deterministic claims covering S1-S6 with only allowed verdict labels and line-anchored evidence.
- Commands/evidence path: `rg -n` extraction on audited files and line-numbered source reads of `Cytokinesis.m`, `karr_cytokinesis.py`, `@Simulation/evolveState.m`, `karr_composite.py`.
- Beat 4 inversion check: request semantics were explicitly audited via executable formulas (`Cytokinesis.m:168-169` vs `karr_cytokinesis.py:491-503`) and not inferred from shared port names alone.
- Verdict: matched.
