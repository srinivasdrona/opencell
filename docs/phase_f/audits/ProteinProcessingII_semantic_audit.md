# ProteinProcessingII Semantic Wiring Audit

## Deliberate Action Prefix v2
### Beat 1 - Contract
- Required behavior: validate whether `data/schemas/per_process_wiring/ProteinProcessingII.yaml` is semantically true against MATLAB and OC runtime behavior for S1-S6, not just anchor presence.
- Done property: an independent auditor can reproduce the same claim-level verdicts (`VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, `MISSING`) from the cited sources.

### Beat 2 - Surface
- Row: `data/schemas/per_process_wiring/ProteinProcessingII.yaml`
- MATLAB: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingII.m`
- MATLAB allocator/order support: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
- OC process: `opencell/vivarium/karr_protein_processing_ii.py`
- OC request path: `opencell/vivarium/karr_request_calculators.py`
- OC allocation + wiring: `opencell/vivarium/karr_allocation_step.py`, `opencell/vivarium/karr_composite.py`
- Suspect patterns checked: flat OC substrate schema (compartment inference), availability-based request fallback vs enzyme/monomer-capped request, comment-chemistry vs emitted deltas (`diacylglycerolCys`).

### Beat 3 - Expected Outcome
- Expected observable: at least one claim for each S1-S6 with deterministic IDs, allowed verdict vocabulary only, aggregate totals, and immediate remediation list.

### Beat 4 - Invert (Pre-mortem)
- Plausible false-pass mode: treating chemistry comments as executed behavior (would wrongly mark `diacylglycerolCys` as produced).
- Plausible false-pass mode: validating only row anchors without checking allocator request/grant execution path.

### Beat 5 - Act Then Verify
- Evidence was taken from executable branches (request computation, allocation scaling/flooring, process consumption/production updates, MATLAB allocation loop) and mapped claim-by-claim below.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Revision-Class Minimum
Design contract sentence: This audit checks semantic truth of row wiring claims against actual MATLAB/OC behavior under strict completeness policy for consume/produce sets.

Decision ledger (non-obvious attribution calls):
- D1: Scope policy
  - Decision: strict completeness (not exemplar-scoped), because this row does not declare non-exhaustive consume/produce scope.
- D2: `diacylglycerolCys` attribution
  - Decision: treat as a documented non-materialized chemistry product (not a missing produce entry), because both MATLAB and OC executable updates omit it.
- D3: Allocator ordering evidence
  - Decision: include `@Simulation/evolveState.m` for MATLAB and composite flow/allocation step for OC, to avoid inferring request/grant ordering from process files alone.

Risks (unresolved ambiguity):
- R1: OC uses flat substrate keys without explicit compartment dimension; tuple matching relies on WID semantic identity (`judgment=required` where noted).
- R2: OC `pp2_active` gate uses `processed_counts` lipoproteins; row correctly captures availability-based request family but does not fully specify this gate condition.
- R3: No stochastic replay run was executed in this audit; formula equivalence is branch-logic equivalence, not trajectory-level numeric replay.

## Header Block
- Process name: `ProteinProcessingII` (`protein_processing_ii`)
- Audited files:
  - `data/schemas/per_process_wiring/ProteinProcessingII.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingII.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_protein_processing_ii.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_allocation_step.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: strict completeness (MATLAB executed consume/produce sets must be fully represented in row claims).

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| PP2-S1-01 | S1 | `consume_stoichiometry` lists only `H2O[c]` and `PG160[m]` as consumed (`ProteinProcessingII.yaml:197-219`). | Only `H2O` and `PG160` are decremented in executable updates (`ProteinProcessingII.m:409-414`, `442-444`). | Only water and PG160 get negative deltas (`karr_protein_processing_ii.py:427-434`). | VERIFIED | Strict completeness check passed for consumed substrates. |
| PP2-S2-01 | S2 | Row consume entries map to OC anchors for water/PG160 (`ProteinProcessingII.yaml:205-219`). | Consume formulas are `-sum(transformations(peptidaseIndexs))` for water and `-sum(transformations(transferaseIndexs))` for PG160 (`ProteinProcessingII.m:409-414`). | `_apply_transformations` subtracts `peptidase_events` from water and `transferase_events` from PG160 (`karr_protein_processing_ii.py:427-434`). | VERIFIED | No fabricated consume entry found in row. |
| PP2-S3-01 | S3 | `produce_stoichiometry` lists `SNGLYP[c]` and `H[c]` (`ProteinProcessingII.yaml:220-242`). | Transferase update is `[-1;1;1] * sum(transformations(transferaseIndexs))` on `[PG160; SNGLYP; H]` (`ProteinProcessingII.m:412-414`). | Transferase branch adds SNGLYP and H (`karr_protein_processing_ii.py:432-433`). | VERIFIED | Produce completeness+fabrication for emitted byproducts is correct. |
| PP2-S3-02 | S3 | Row marks `diacylglycerolCys` as nominal chemistry product not emitted in code (`ProteinProcessingII.yaml:193-196`, `264-268`, `395`). | Chemistry comment names `diacylglycerolCys`, but executable metabolite updates do not emit it (`ProteinProcessingII.m:342`, `412-414`). | `reaction_stoich`/update paths emit PG160, SNGLYP, H, H2O only (`karr_protein_processing_ii.py:110-114`, `430-434`). | VERIFIED | This is a documented chemistry-vs-implementation omission, not a row fabrication. |
| PP2-S4-01 | S4 | Row says OC preserves two-phase count-space maturation logic (`ProteinProcessingII.yaml:116-140`). | Phase-1/phase-2 formula family: scale by enzyme limits, stochastic round, clip by water/PG160, apply deltas (`ProteinProcessingII.m:381-421`, `427-444`). | Same formula family implemented via `_scale_transformations`, `_stochastic_round`, `_clip_by_resource`, `_apply_transformations` (`karr_protein_processing_ii.py:239-295`, `349-434`). | VERIFIED | `judgment=required` (algebraic equivalence across helper decomposition). |
| PP2-S4-02 | S4 | Row states request-formula divergence: MATLAB enzyme/monomer-capped demand vs OC availability-based request (`ProteinProcessingII.yaml:163-174`). | `calcResourceRequirements_Current` computes `min(ceil(enzyme*rate*step), unprocessed sum)` for H2O/PG160 (`ProteinProcessingII.m:327-344`). | `pp2_req` uses `_request_from_available(substrate_state, _pp2_consumed, active=pp2_active)` (`karr_request_calculators.py:389-391`, `513-516`). | CODE_DEVIATES | Row correctly describes MATLAB-vs-OC formula divergence. |
| PP2-S5-01 | S5 | Row routes `H2O[c]`, `PG160[m]`, `SNGLYP[c]`, `H[c]` as non-mismatch entries (`ProteinProcessingII.yaml:243-263`). | MATLAB updates these same substrate IDs in the expected reaction branches (`ProteinProcessingII.m:409-414`). | OC updates the same WIDs in transferase/cleavage branches (`karr_protein_processing_ii.py:111-114`, `427-433`). | VERIFIED | `judgment=required` (OC compartment identity is inferred from flat WID semantics). |
| PP2-S5-02 | S5 | Row claims no compartment projection/merge loss (`shared_pool_projection_merges_compartments: false`) (`ProteinProcessingII.yaml:391`). | Process uses dedicated substrate indices for this pathway; no in-process compartment merge transform appears (`ProteinProcessingII.m:409-414`). | OC process applies direct keyed deltas with no projection/merge operator (`karr_protein_processing_ii.py:313-320`, `427-434`). | VERIFIED | Explicit projection/merge test passed for this process surface. |
| PP2-S6-01 | S6 | Row mode is allocator-backed in both MATLAB and OC (`ProteinProcessingII.yaml:159-162`), with strict-zero allocated read in OC (`:12`, `:393`). | MATLAB allocator loop computes requirements then allocates before `mod.evolveState()` (`@Simulation/evolveState.m:24-37`, `63-70`). | OC request calculator emits PP2 requests, allocator step scales/floors grants, process reads `substrates_allocated[self.name]` (`karr_request_calculators.py:513-516`, `karr_allocation_step.py:214-255`, `273-280`, `karr_protein_processing_ii.py:180-185`, `karr_composite.py:2063-2067`, `2345-2356`). | VERIFIED | Request/grant path is engaged; consume path is grant-backed, while byproducts are direct writebacks. |
| PP2-S6-02 | S6 | Row says no bespoke PP2 hard ordering constraints (`ProteinProcessingII.yaml:291-296`). | MATLAB randomizes process eval order with only `tRNAAminoacylation < Translation` hard constraint (`@Simulation/evolveState.m:48-57`), no PP2-specific hard ordering. | OC flow imposes request-calculator -> allocation-step dependency; no PP2-specific hard-before edge beyond grant dependency (`karr_composite.py:2335-2357`). | VERIFIED | `judgment=required` (Vivarium process-vs-step same-tick scheduling semantics are framework-level). |

## Aggregate Counts
- VERIFIED: 9
- ROW_WRONG: 0
- CODE_DEVIATES: 1
- MISSING: 0

## Priority-1 Fixes
Priority-1 fixes: none

## Known-Deviation Mapping
- D-PP2-01: Allocator request formula differs (MATLAB enzyme/monomer-capped vs OC availability-based) -> `PP2-S4-02` (`CODE_DEVIATES`).
- D-PP2-02: `diacylglycerolCys` is chemistry-comment nominal product not emitted in either implementation -> `PP2-S3-02` (`VERIFIED` row statement).

## Auditor Discretion List
- `PP2-S4-01` (`judgment=required`)
- `PP2-S5-01` (`judgment=required`)
- `PP2-S6-02` (`judgment=required`)
