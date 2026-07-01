# Replication Semantic Audit

## Header
- Process name: `Replication`
- Process slug: `replication`
- Audited files:
  - `data/schemas/per_process_wiring/Replication.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Replication.m`
  - `docs/karr_extracts/process/03_Replication.md`
  - `docs/karr_extracts/architecture/03_variable_allocation.md`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_replication.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: `strict completeness` (row does not explicitly declare exemplar-only scope)
- Header note: `FULL`

## Deliberate Action Prefix v2
- Beat 1 (contract): prove/falsify Replication row semantics against executable MATLAB + OC behavior for S1-S6 with row-vs-code attribution.
- Beat 2 (surface): row `Replication.yaml`; MATLAB `Replication.m` + `@Simulation/evolveState.m`; OC `karr_replication.py` + `karr_composite.py` + allocator wiring assumptions.
- Beat 3 (expected outcome): deterministic claim table using only `VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`, plus totals and Priority-1 remediation list.
- Beat 4 (invert): a false pass could happen by trusting extract prose and stale row anchors while missing executed MATLAB substrate branches (`initiateReplication`, `unwindAndPolymerizeDNA`, `initiateOkazakiFragment`, `ligateDNA`) and OC branch gating (`trace_hint` vs non-hint).
- Beat 5 (act then verify): every claim below cites executable lines for requests, grants, consumes/produces, formulas, tuple routing, and ordering.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

Design contract sentence: The audit is complete only if an independent auditor can recompute each verdict from cited row/MATLAB/OC branches without relying on prose-only interpretation.

## Decision Ledger
Decision D1
- Question: completeness policy for S1/S3 omissions.
- Options considered: exemplar-scoped completeness; strict completeness.
- Chosen option: strict completeness.
- Rationale: row does not declare exemplar scope.

Decision D2
- Question: OC byproduct fabrication when only `trace_hint` branch emits byproducts.
- Options considered: treat as fabricated; treat as row-ambiguous/wrong.
- Chosen option: `ROW_WRONG` when row presents byproducts as general OC behavior.
- Rationale: main `next_update` path emits no byproducts; branch gating is load-bearing.

Decision D3
- Question: compartment projection attribution with WID-only OC substrate store.
- Options considered: ignore projection; classify as row routing mismatch.
- Chosen option: classify projection claim and mark practical tuple match separately.
- Rationale: requirement explicitly asks to test projection/merge behavior.

Decision D4
- Question: whether to include ordering under S6.
- Options considered: omit ordering; include allocator-coupled ordering claim.
- Chosen option: include ordering claim under S6.
- Rationale: MATLAB random subfunction order vs OC fixed update affects allocator-coupled semantics interpretation.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| REP-S1-01 | S1 | `consume_stoichiometry` includes `DATP/DCTP/DGTP/DTTP/ATP` (`Replication.yaml:127-182`). | These substrates are consumed in initiation/unwind/polymerization branches (`Replication.m:667-668,909-910,945`). | Non-hint path requests + consumes these same WIDs (`karr_replication.py:538-592,628-635,968-971,1005-1008`). | VERIFIED | Core consume set for fork advance is represented. |
| REP-S1-02 | S1 | `consume_stoichiometry` omits `H2O` (`Replication.yaml:127-183`). | `H2O` is consumed in initiation, unwind, and clamp loading (`Replication.m:668,910,1086`). | `H2O` consumption exists in trace-hint replay (`karr_replication.py:753-757,857`). | MISSING | MATLAB consume behavior exists but row consume list omits it. |
| REP-S1-03 | S1 | `consume_stoichiometry` omits `NAD` (`Replication.yaml:127-183`). | Ligation consumes `NAD` (`Replication.m:1228-1231,1244`). | Trace-hint replay consumes `NAD` during ligations (`karr_replication.py:758-761,849-850,870`). | MISSING | MATLAB consume behavior exists but row consume list omits it. |
| REP-S2-01 | S2 | Each listed consume entry has OC anchors for `_demand_from_advances` (`Replication.yaml:127-182`). | MATLAB consume exists for listed entries (`Replication.m:667,909,945`). | Real OC consume path exists for listed entries via request build + grant-clipped decrement (`karr_replication.py:628-635,968-971,978-1008`). | VERIFIED | Fabrication check passes for row-listed consume entries. |
| REP-S3-01 | S3 | `produce_stoichiometry` lists `ADP/PI/H/PPI/NMN` only (`Replication.yaml:183-238`). | Ligation produces `AMP` (`Replication.m:1245-1247`). | Trace-hint replay also produces `AMP` (`karr_replication.py:869-873`). | MISSING | MATLAB produce behavior exists but row produce list omits `AMP`. |
| REP-S3-02 | S3 | Row anchors OC produce entries to `karr_replication.py:978-1012` as direct substrate deltas (`Replication.yaml:191-238`). | MATLAB does produce ADP/PI/H/PPI/NMN in executed branches (`Replication.m:669-671,911-913,946,1245-1247`). | OC non-hint branch at `978-1012` only decrements requested substrates; byproduct production is in trace-hint branch (`karr_replication.py:854-873,1005-1008`). | ROW_WRONG | `judgment=required` (branch-conditional OC production is not stated in row). |
| REP-S4-01 | S4 | Row dNTP formula is `partition_counts(2 * total_advanced_bp)` (`Replication.yaml:130-170`). | MATLAB dNTP usage is sequence-exact `subsequenceBaseCounts(...)` after polymerization (`Replication.m:939-946`). | OC non-hint uses GC-fraction partition + remainder distribution (`karr_replication.py:616-626,628-635`). | ROW_WRONG | Formula family is not mathematically equivalent to MATLAB execution. |
| REP-S4-02 | S4 | Row formula for `H` is `atp_events` (`Replication.yaml:206-216`). | MATLAB `H` increases from ATP hydrolysis and ligation (`Replication.m:671,913,1089,1247`). | OC trace-hint branch also adds `H` from both ATP events and ligations (`karr_replication.py:860,873`). | ROW_WRONG | Row understates hydrogen formula family (missing ligation term). |
| REP-S4-03 | S4 | Row allocator formula distinguishes MATLAB fair-share and OC inline clipped demand (`Replication.yaml:81-84`). | MATLAB allocation is `allocations = max(0, fix(requirements .* tmp(...)))` (`evolveState.m:35-37`). | OC non-hint uses per-process scale/floor + while-loop clipping against grants (`karr_replication.py:984-1000`). | CODE_DEVIATES | Row correctly captures MATLAB-vs-OC clipping-family divergence. |
| REP-S5-01 | S5 | Row sets `shared_pool_projection_merges_compartments: false` (`Replication.yaml:373`). | MATLAB updates substrate vectors through global-compartment indices (`evolveState.m:32-33,63-73`). | OC substrate port is WID-keyed with no compartment axis (`karr_replication.py:566-569`). | ROW_WRONG | OC does project away compartment dimension at process interface. |
| REP-S5-02 | S5 | Row routes tracked tuples to cytosol (`Replication.yaml:239-289`). | Replication substrate edits in `Replication.m` use one local substrate vector; no explicit multi-compartment branch in-process (`Replication.m:667-671,909-913,945-946,1244-1247`). | OC writes same WID keys in one pooled substrate store (`karr_replication.py:566-569,1005-1008`). | VERIFIED | `judgment=required` (MATLAB compartment identity is mediated by global-compartment mapping). |
| REP-S6-01 | S6 | Row allocator request list is `DATP/DCTP/DGTP/DTTP/ATP` (`Replication.yaml:85-105`). | MATLAB `calcResourceRequirements_Current` requests `ATP`, `H2O`, dNTPs, and `NAD` (`Replication.m:530-563`). | OC request schema emits only dNTP+ATP (`karr_replication.py:538-592`). | MISSING | Row omits MATLAB request-set members `H2O` and `NAD`. |
| REP-S6-02 | S6 | Row mode says allocator participation on both sides (`Replication.yaml:77-84`). | MATLAB performs requirements -> fair-share allocations -> process evolve using allocation vector (`evolveState.m:24-37,63-73`). | OC exposes `requests`/`substrates_allocated` and consumes allocated grants in main path (`karr_replication.py:578-588,968-981`). | VERIFIED | Participation mode matches at high level (request/grant engagement). |
| REP-S6-03 | S6 | Row says OC has raw-substrates fallback when allocation surface absent (`Replication.yaml:80`). | MATLAB always injects allocation vector before process evolve (`evolveState.m:63-70`). | OC non-hint path reads strictly from `substrates_allocated` for requested WIDs (`karr_replication.py:978-983,599-600`), no raw-substrate fallback there. | ROW_WRONG | Fallback statement is false for the main OC execution branch. |
| REP-S6-04 | S6 | Row notes OC is light-bulk replay and not full 8-stage mechanistic loop (`Replication.yaml:56-58,376`). | MATLAB executes subfunctions in random order each tick (`Replication.m:588-609`). | OC non-hint path is a fixed-state update function without random subfunction scheduling (`karr_replication.py:896-1030`). | CODE_DEVIATES | `judgment=required` (ordering impact is branch/runtime-mode sensitive). |

## Aggregate Counts
- VERIFIED: 4
- ROW_WRONG: 5
- CODE_DEVIATES: 2
- MISSING: 4

## Priority-1 Fixes
- REP-S1-02 (`MISSING`): add `H2O` to `consume_stoichiometry` (or explicitly declare exemplar scope).
- REP-S1-03 (`MISSING`): add `NAD` to `consume_stoichiometry`.
- REP-S3-01 (`MISSING`): add `AMP` to `produce_stoichiometry`.
- REP-S3-02 (`ROW_WRONG`): correct OC produce attribution/gating (non-hint vs trace-hint branch).
- REP-S4-01 (`ROW_WRONG`): document MATLAB sequence-exact dNTP formula vs OC partition approximation.
- REP-S4-02 (`ROW_WRONG`): fix `H` formula to include ligation contribution.
- REP-S5-01 (`ROW_WRONG`): correct compartment projection/merge statement.
- REP-S6-01 (`MISSING`): include `H2O` and `NAD` in allocator request-set semantics.
- REP-S6-03 (`ROW_WRONG`): correct fallback claim for OC non-hint allocator path.

## Known-Deviation Mapping
- REP-D1 (formula family): MATLAB sequence-exact dNTP vs OC partition approximation (`REP-S4-01`).
- REP-D2 (allocation clipping family): MATLAB global fair-share vs OC per-process clip loop (`REP-S4-03`).
- REP-D3 (runtime algorithm shape): MATLAB random 8-subfunction loop vs OC fixed light-bulk update (`REP-S6-04`).

## Auditor Discretion List
- REP-S3-02: `judgment=required` (OC byproduct fabrication differs by trace-hint mode).
- REP-S5-02: `judgment=required` (MATLAB compartment identity is indirect via global-compartment indices).
- REP-S6-04: `judgment=required` (ordering impact depends on runtime branch/mode).

## Risks
R1. OC trace-hint branch and non-hint branch have materially different substrate deltas.
- Likelihood: high
- Impact: high
- Detection: compare one tick of `_next_update_from_trace_hint` and `next_update` on identical substrate/enzyme states.

R2. MATLAB compartment tuple identity for each WID is mediated by state mappings outside Replication.m.
- Likelihood: medium
- Impact: medium
- Detection: inspect `substrateMetaboliteGlobalCompartmentIndexs` materialization in process/state glue.

R3. Row was authored against extracted docs while raw MATLAB file is now present.
- Likelihood: high
- Impact: medium
- Detection: reconcile all row anchors/formulas directly against `Replication.m` executable branches.