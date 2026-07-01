# ChromosomeCondensation Semantic Audit

Process name: `ChromosomeCondensation`  
Audited files:
- `data/schemas/per_process_wiring/ChromosomeCondensation.yaml`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeCondensation.m`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
- `opencell/vivarium/karr_chromosome_condensation.py`
- `opencell/vivarium/karr_composite.py`  
Scope policy: **strict completeness** (row does not declare exemplar/non-exhaustive consume/produce scope).

## Deliberate Action Prefix v2

Beat 1 (contract):
- Required behavior: classify S1-S6 semantic claims by comparing row statements to executable MATLAB and OC behavior.
- Done means: claim-level verdicts are reproducible from cited code anchors and use only `VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`.

Beat 2 (surface):
- Row surface: `ChromosomeCondensation.yaml` (`consume_stoichiometry`, `produce_stoichiometry`, `allocator`, `compartment_routing`, `ordering_constraints`, `deviations`).
- MATLAB surface: `ChromosomeCondensation.m` (`calcResourceRequirements_Current`, `evolveState`) and `Simulation/evolveState.m` (allocation/order loop).
- OC surface: `karr_chromosome_condensation.py` (`ports_schema`, `next_update`, `_allocated_or_state`) and `karr_composite.py` (allocation wiring + flow).
- Suspect pattern named before verdicting: stale row prose claiming allocator fallback to global substrates.

Beat 3 (expected outcome):
- Deliver a deterministic claim table covering S1-S6, with aggregate counts and Priority-1 row-remediation items.

Beat 4 (invert / pre-mortem):
- Likely false-pass mode: trusting row notes about allocator bypass/fallback without validating current OC helper implementation.

Beat 5 (act then verify):
- Verification evidence is captured per claim with executable MATLAB/OC anchors and row line references.

PM sanity-check sentence: **PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.**

## Revision-Class Minimum

Design contract sentence:
- Semantic truth being checked: row claims for consume/produce/formula/routing/allocator semantics must match MATLAB behavior and current OC behavior for ChromosomeCondensation.

Decision ledger (non-obvious attribution calls):
- D1: Compartment routing attribution.
  - Chosen: treat row cytosol routing as provisionally valid for listed substrates, but flag projection/merge representation risk separately.
  - Why: MATLAB here is compartment-indexed at simulation level, while OC process substrate store is flat per WID.
- D2: Allocator mode attribution.
  - Chosen: classify OC as allocator-fed (not mixed fallback) because `_allocated_or_state` returns allocated values only.
  - Why: direct code evidence (`karr_chromosome_condensation.py:832-838`) contradicts row fallback prose.
- D3: Allocator-coupled ordering attribution.
  - Chosen: mark timing-equivalence claim as `MISSING` with `judgment=required`.
  - Why: MATLAB ordering is explicit (`requirements -> allocation -> evolve`), while OC request emission is embedded in a process and allocation is wired as a step flow.

Risks (unresolved ambiguity):
- R1: Exact Vivarium process-vs-step execution timing is not fully derivable from `karr_composite.py` alone, so request/grant same-tick vs next-tick semantics are partially inferential.
- R2: Practical impact of flat substrate routing depends on whether these WIDs are effectively cytosol-only in runtime state.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| CC-S1-01 | S1 | Consume list includes only `ATP` and `H2O` with `-nBound` (`ChromosomeCondensation.yaml:175-199`). | Consume-side substrate decrements are only ATP and H2O (`ChromosomeCondensation.m:280-281`). | Consume deltas are only ATP and H2O (`karr_chromosome_condensation.py:398-400`). | VERIFIED | Strict consume completeness holds. |
| CC-S2-01 | S2 | Row consume entries anchor OC consume path in `next_update` (`ChromosomeCondensation.yaml:183-199`). | ATP/H2O consume path is in post-bind update (`ChromosomeCondensation.m:273-281`). | Real OC consume path exists (`substrate_delta` then `update["substrates"]`) (`karr_chromosome_condensation.py:397-400`, `417-419`). | VERIFIED | No fabricated consume entry detected. |
| CC-S3-01 | S3 | Produce list is `ADP`, `PI`, `H` (`ChromosomeCondensation.yaml:200-236`). | ADP produced on SMC-ADP dissociation and PI/H produced on hydrolysis (`ChromosomeCondensation.m:241-244`, `282-283`). | OC produces ADP from dissociation and PI/H from `n_bound` hydrolysis branch (`karr_chromosome_condensation.py:393-403`). | VERIFIED | Produce completeness and fabrication both hold. |
| CC-S4-01 | S4 | Row formulas encode hydrolysis family: `ATP/H2O=-nBound`, `PI/H=+nBound` (`ChromosomeCondensation.yaml:178-190`, `215-227`). | `nBound` is applied with matching signs to ATP/H2O/PI/H updates (`ChromosomeCondensation.m:266-283`). | `n_bound` is applied with identical sign pattern in `substrate_delta` (`karr_chromosome_condensation.py:397-403`). | VERIFIED | Hydrolysis formula family matches modulo syntax/casing. |
| CC-S4-02 | S4 | Row claims binding is energy-limited and SMC-limited (`ChromosomeCondensation.yaml:80`, `178-199`). | `nBindingMax = min(ATP, H2O, SMC_after_dissociation)` (`ChromosomeCondensation.m:242`, `247-250`). | `n_binding_max = min(available_atp, available_h2o, free_smc_after_dissociation)` (`karr_chromosome_condensation.py:323-368`). | VERIFIED | Bound/limit transform family matches. |
| CC-S5-01 | S5 | Row routes ATP/H2O consume and ADP/PI/H produce to cytosol (`ChromosomeCondensation.yaml:237-262`). | Process substrates are ATP/ADP/PI/H2O/H (`ChromosomeCondensation.m:139-145`) and are written through compartment-indexed simulation mappings (`Simulation/evolveState.m:63-73`). | OC writes same WID set through flat `substrates` deltas (`karr_chromosome_condensation.py:295-297`, `393-403`). | VERIFIED | `judgment=required`: tuple parity is inferred at cytosol layer; OC store is flat by WID. |
| CC-S5-02 | S5 | Row states `shared_pool_projection_merges_compartments: false` (`ChromosomeCondensation.yaml:401`). | MATLAB allocation/writeback is compartment-indexed (`Simulation/evolveState.m:27`, `32-33`, `63-73`). | OC process substrate port is compartment-flattened (WID-only map) and wired to shared `substrates` store (`karr_chromosome_condensation.py:295-297`; `karr_composite.py:2115-2119`). | ROW_WRONG | Row underreports projection/merge representation risk; `judgment=required` on practical effect. |
| CC-S6-01 | S6 | Row says `oc_current: mixed` with ATP/H2O fallback-to-global behavior (`ChromosomeCondensation.yaml:137-140`, `155-162`, `405`). | MATLAB is allocator-engaged: requirements computed then allocations applied before `evolveState` (`Simulation/evolveState.m:24-37`, `63-70`; `ChromosomeCondensation.m:233-237`). | OC reads `substrates_allocated` and helper returns allocated-only (`karr_chromosome_condensation.py:323-326`, `832-838`); process is in allocation consumer set (`karr_composite.py:1774-1776`). | ROW_WRONG | OC is not mixed fallback in current code; ATP/H2O bypass claim is stale. |
| CC-S6-02 | S6 | Row notes embedded OC request emission and no standalone request calculator, but no explicit allocator-coupled timing claim (`ChromosomeCondensation.yaml:73`, `404`, `282-287`). | MATLAB ordering is explicit: per-tick `calcResourceRequirements_Current -> allocation -> evolveState` (`Simulation/evolveState.m:31-37`, `69-70`). | OC emits requests inside process (`karr_chromosome_condensation.py:435-441`), while allocation step flow depends on request-calculator steps (`karr_composite.py:2320-2331`, `2345-2356`). | MISSING | Missing explicit row claim for request/grant timing equivalence; `judgment=required`. |

## Aggregate Counts

- VERIFIED: 6
- ROW_WRONG: 2
- CODE_DEVIATES: 0
- MISSING: 1

## Priority-1 Fixes

- `CC-S5-02` (`ROW_WRONG`): revise projection/merge field to reflect OC flat shared-substrate representation and its compartment implications.
- `CC-S6-01` (`ROW_WRONG`): update allocator mode/bypass text; remove stale ATP/H2O fallback-to-global claim.
- `CC-S6-02` (`MISSING`): add explicit allocator-coupled timing claim (same-tick vs next-tick request/grant semantics) for OC vs MATLAB ordering.

## Known-Deviation Mapping

- No A1-A4 deviation IDs are currently encoded for this row; current critical findings are row staleness/omission (`ROW_WRONG`, `MISSING`).

## Auditor Discretion List (`judgment=required`)

- `CC-S5-01` (cytosol tuple parity inferred while OC store is flat)
- `CC-S5-02` (projection/merge practical impact depends on runtime compartment usage of these WIDs)
- `CC-S6-02` (request/grant timing depends on engine process-step scheduling semantics)
