# ProteinProcessingI Semantic Audit

Process name: `ProteinProcessingI`  
Audited files:
- `data/schemas/per_process_wiring/ProteinProcessingI.yaml`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingI.m`
- `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingI.m`
- `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
- `opencell/vivarium/karr_protein_processing_i.py`
- `opencell/vivarium/karr_request_calculators.py`
- `opencell/vivarium/karr_composite.py`
- `tests/vivarium/test_karr_protein_processing_i.py`
- `tests/vivarium/test_karr_request_calculators.py`

Scope policy: **strict completeness** (row does not declare exemplar-only consume/produce scope).

## Deliberate Action Prefix v2

Beat 1 (contract):
- Required behavior: validate row semantics against executable MATLAB and OC behavior for S1-S6.
- Done means: each claim has reproducible source-backed verdict using only `VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`.

Beat 2 (surface):
- Row surface: allocator, consume/produce stoichiometry, compartment routing, ordering/deviations (`ProteinProcessingI.yaml:88-311`).
- MATLAB surface: `calcResourceRequirements_Current`, `evolveState`, and allocation/order loop (`ProteinProcessingI.m:218-319`; `Simulation/evolveState.m:24-73`).
- OC surface: process update and allocated-substrate reader (`karr_protein_processing_i.py:182-378`), request step (`karr_request_calculators.py:468-549`), and composite request/allocation topology (`karr_composite.py:2056-2062`, `2320-2357`).
- Suspect pattern called out before verdicting: biology-docstring ordering prose can be mistaken for scheduler truth.

Beat 3 (expected outcome):
- Deliver a deterministic S1-S6 claim table with aggregate counts and Priority-1 row-remediation items.

Beat 4 (invert / pre-mortem):
- False-pass mode: accept `soft_after: Translation` from row prose while executable schedulers show no PP1-after-translation guarantee.

Beat 5 (act then verify):
- Each claim below cites concrete MATLAB/OC branches (conditions, formulas, routing, allocator wiring), not prose-only anchors.

PM sanity-check sentence: **PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.**

## Revision-Class Minimum

Design contract sentence:
- Semantic truth being checked: the row must truthfully represent MATLAB and OC behavior for consume/produce completeness, formula families, compartment tuples/projection, and allocator engagement for ProteinProcessingI.

Decision ledger (non-obvious attribution calls):
- D1: Completeness policy.
  - Chosen: strict completeness.
  - Why: row contains no explicit non-exhaustive scope contract for consume/produce surfaces.
- D2: Request-formula mismatch attribution.
  - Chosen: `CODE_DEVIATES`.
  - Why: row explicitly states MATLAB upper-bound request vs OC availability-based request; source code confirms both sides.
- D3: Ordering claim attribution.
  - Chosen: `ROW_WRONG` for `soft_after: Translation`.
  - Why: MATLAB runtime ordering is randomized (except tRNA<Translation), and OC wiring has no PP1-after-translation edge; row soft-order claim is unsupported.

Risks (unresolved ambiguity):
- R1: MATLAB substrate compartment tuple is inferred from process representation comments (`compartment dimension ... length 1`), not from an explicit per-substrate compartment map in this file.
- R2: OC process execution ordering among processes is engine-level behavior; composite flow evidence is strong for request/allocation ordering but weaker for soft process-after-process semantics.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| PPI-S1-01 | S1 | `consume_stoichiometry` lists only `H2O` as consumed substrate (`ProteinProcessingI.yaml:115-126`). | Consume-side metabolite updates only decrement water (`ProteinProcessingI.m:286-292`). | Only water has negative substrate delta (`karr_protein_processing_i.py:273-277`). | VERIFIED | Strict completeness passes: MATLAB consume set = `{H2O}`. |
| PPI-S2-01 | S2 | Row consume entry for `H2O` claims OC consume path in `next_update` (`ProteinProcessingI.yaml:116-126`). | Water consumed by total transformations plus cleavage subset (`ProteinProcessingI.m:286-292`). | Real OC consume path exists: `substrate_delta[H2O] -= total_processed + cleavage_count` (`karr_protein_processing_i.py:267-277`). | VERIFIED | No fabricated consume entry found. |
| PPI-S3-01 | S3 | `produce_stoichiometry` lists `H`, `FOR`, `MET` (`ProteinProcessingI.yaml:127-160`). | Produce-side updates are `+H,+FOR` per total transformations and `+MET` for cleavage subset (`ProteinProcessingI.m:286-292`). | OC produces same three substrates (`karr_protein_processing_i.py:275-277`). | VERIFIED | Strict completeness passes for produce set. |
| PPI-S3-02 | S3 | Each produce entry is claimed to map to OC writeback (`ProteinProcessingI.yaml:127-160`). | MATLAB writeback emits all listed products in evolve-state metabolite updates (`ProteinProcessingI.m:286-292`). | OC writeback emits positive deltas for all listed products (`karr_protein_processing_i.py:275-277`, `280-287`). | VERIFIED | No fabricated produce entry found. |
| PPI-S4-01 | S4 | Row formulas: `H2O = -sum(transformations)-sum(transformations(cleavageMask))`, `H/FOR = +sum(transformations)`, `MET = +sum(transformations(cleavageMask))` (`ProteinProcessingI.yaml:118-153`). | MATLAB uses identical stoichiometric family (`ProteinProcessingI.m:286-292`). | OC uses `total_processed` and `cleavage_count` with same math (`karr_protein_processing_i.py:267-277`). | VERIFIED | Formula family match (hydrolysis + cleavage stoichiometry). |
| PPI-S4-02 | S4 | Row states request-formula split: MATLAB upper bound vs OC availability-based H2O request (`ProteinProcessingI.yaml:93-96`). | MATLAB request is `min(deformylaseLimit,sum(unprocessed)) + min(cleavageLimit,mask'*unprocessed)` at H2O index (`ProteinProcessingI.m:220-230`). | OC PP1 request is `max(0, substrate_state['H2O'])` when active, else zero (`karr_request_calculators.py:479-511`). | CODE_DEVIATES | Row correctly describes MATLAB-vs-OC request-formula divergence. |
| PPI-S4-03 | S4 | Row records stochastic-sampler difference (`ProteinProcessingI.yaml:70`, `305-308`). | MATLAB uses `stochasticRound` plus `mnrnd` and `min` clipping under water gating (`ProteinProcessingI.m:253-274`, `306-308`). | OC uses bounded event counts plus `multivariate_hypergeometric` (or fallback choice loop) (`karr_protein_processing_i.py:232-265`, `399-414`). | CODE_DEVIATES | `judgment=required` (different stochastic kernels, same count-domain stoichiometric surface). |
| PPI-S5-01 | S5 | Row claims routing tuples are cytosolic for `H2O/H/FOR/MET` with `mismatch: false` (`ProteinProcessingI.yaml:161-181`). | Process representation states a single relevant compartment axis for this process and substrate writes occur through process substrate indices (`ProteinProcessingI.m:45-47`, `286-292`); simulation writes via global compartment indices (`Simulation/evolveState.m:63-73`). | OC uses one flat substrate store keyed by WID, with direct per-WID updates (`karr_protein_processing_i.py:136-139`, `273-287`; `karr_composite.py:2056-2062`). | VERIFIED | `judgment=required` (MATLAB per-substrate compartment map is implicit in this source set). |
| PPI-S5-02 | S5 | Row says `shared_pool_projection_merges_compartments: false` (`ProteinProcessingI.yaml:304`). | MATLAB process-level representation is single-compartment for this process surface (`ProteinProcessingI.m:45-47`). | OC path is already single-axis WID store; no extra compartment projection/merge op in PP1 read/write path (`karr_protein_processing_i.py:369-378`, `280-287`). | VERIFIED | Explicit projection/merge check passes for PP1 path. |
| PPI-S6-01 | S6 | Row allocator mode is `karr=allocation`, `oc_current=allocation`; OC reads only allocated pool (`ProteinProcessingI.yaml:89-92`). | MATLAB gathers per-process requirements, computes allocations, injects allocation into process substrate state before `evolveState` (`Simulation/evolveState.m:24-37`, `63-70`). | OC request step feeds allocation step, and PP1 reads `substrates_allocated[self.name]` only (`karr_composite.py:2326`, `2345-2352`; `karr_protein_processing_i.py:369-377`). | VERIFIED | Allocator engagement mode matches at request/grant usage level. |
| PPI-S6-02 | S6 | Row says allocator request list is only `H2O`; `H/MET/FOR` are bypass writeback side effects (`ProteinProcessingI.yaml:97-114`). | MATLAB `calcResourceRequirements_Current` sets only water request and evolve-state directly writes H/MET/FOR products (`ProteinProcessingI.m:225-230`, `286-292`). | OC PP1 request dictionary only makes H2O potentially nonzero; products are direct process substrate deltas (`karr_request_calculators.py:499-511`; `karr_protein_processing_i.py:275-277`). | VERIFIED | Request/grant vs bypass split matches. |
| PPI-S6-03 | S6 | Row declares `soft_after: Translation` and notes no extra hard scheduler exception beyond global tRNA<Translation rule (`ProteinProcessingI.yaml:210-212`). | MATLAB runtime order is randomized each tick with only tRNA-before-translation hard constraint (`Simulation/evolveState.m:48-57`). | OC composite flow has no explicit Translation->PP1 dependency edge; only request calculators are ordered into allocation (`karr_composite.py:2334-2357`, `2056-2062`). | ROW_WRONG | `judgment=required`: row soft-order claim is unsupported/ambiguous as executable ordering semantics. |

## Aggregate Counts

- VERIFIED: 9
- ROW_WRONG: 1
- CODE_DEVIATES: 2
- MISSING: 0

## Priority-1 Fixes

- `PPI-S6-03` (`ROW_WRONG`): remediate `ordering_constraints.soft_after: Translation` to reflect executable scheduler semantics (or explicitly mark as biological-prose, not runtime wiring).

## Known-Deviation Mapping

- `PPI-S4-02`: request-formula divergence (MATLAB upper-bound request vs OC availability-based request).
- `PPI-S4-03`: stochastic-sampler divergence (MATLAB `stochasticRound/mnrnd` path vs OC `multivariate_hypergeometric`/fallback).

## Auditor Discretion List (`judgment=required`)

- `PPI-S4-03` (stochastic-kernel equivalence judgment)
- `PPI-S5-01` (implicit MATLAB compartment mapping)
- `PPI-S6-03` (interpreting `soft_after` as executable ordering contract)
