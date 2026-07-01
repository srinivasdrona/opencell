# RNAModification Semantic Audit

## Header
- Process: `RNAModification` (`rna_modification`)
- Audited files:
  - `data/schemas/per_process_wiring/RNAModification.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNAModification.m`
  - `docs/phase_f/L2_5_HARNESS_DESIGN.md`
  - `opencell/vivarium/karr_rna_modification.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_composite.py`
  - `docs/prompts/SEMANTIC_AUDIT_TEMPLATE.md`
- Scope policy: `exemplar-scoped completeness` (row explicitly marks consume/produce entries as "Representative").

## Deliberate Action Prefix v2
- Beat 1 (contract): classify each semantic claim against MATLAB behavior and OC behavior using only `VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, `MISSING`.
- Beat 2 (surface): row YAML + RNAModification MATLAB process + OC process/request/composite wiring + harness ordering note.
- Beat 3 (expected outcome): deterministic S1-S6 claim table with aggregate counts and Priority-1 row remediation list.
- Beat 4 (invert): audit could look complete but be wrong if representative examples are treated as strict completeness without policy declaration, or if comments are cited instead of executed branches/formulas.
- Beat 5 (verify): each claim below cites executable formulas/routes (request, allocation, stoichiometric update, compartment/write surfaces) and records discretionary calls as `judgment=required`.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Revision-Class Minimum
Design contract sentence: Semantic truth being checked is whether RNAModification row claims are reproducible from MATLAB execution logic and OC execution logic, including allocator coupling, formula families, and compartment tuples.

### Decision Ledger (non-obvious attribution calls)
- D1: Completeness policy for S1/S3.
  - Chosen: exemplar-scoped completeness.
  - Why: each consume/produce row entry is labeled representative; treating as strict exhaustive would override declared scope.
  - Falsifier: if operator policy is strict completeness, S1/S3 verdicts must be reopened.
- D2: Request-formula mismatch attribution.
  - Chosen: `CODE_DEVIATES` (not `ROW_WRONG`).
  - Why: row explicitly states MATLAB formula and OC shared availability-based request behavior as different.
  - Falsifier: if OC now implements MATLAB min/ceil/catalysis formula, this claim must flip to `ROW_WRONG` or `VERIFIED` depending row update.
- D3: Compartment tuple interpretation from fixture indices.
  - Chosen: keep `VERIFIED` with `judgment=required`.
  - Why: fixture shows one substrate compartment index for all 29 substrates, but compartment handle labels are flattened in MAT export.
  - Falsifier: if index mapping is proven non-cytosolic, compartment claims must be relabeled.

### Risks (unresolved ambiguity)
- R1: If strict completeness policy is enforced, row omissions (`GLY`, `H2O` on consume side; `H2O`, `SER` on produce side) would become immediate remediation items.
- R2: Compartment name resolution in flattened fixture is indirect; index-level single-compartment evidence is strong but not self-labeled.
- R3: Allocator-coupled ordering in OC depends on Vivarium step/process scheduling semantics beyond static `flow` dependency declarations.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| RNAMOD-S1-01 | S1 | `consume_stoichiometry` lists representative consumed substrates (`AMET`, `ATP`, `CYS`, `FTHF5`, `LYS`). | Substrate consumption is driven by full `reactionStoichiometryMatrix` update (`RNAModification.m:356-357`), with consumed families including `AMET, ATP, CYS, FTHF5, GLY, H2O, LYS` (fixture-derived from MATLAB stoich). | RNAModification consumed set from `reaction_stoich < 0` is `AMET, ATP, CYS, FTHF5, GLY, H2O, LYS` (request calculator derives same consumed set at `karr_request_calculators.py:300-305`). | VERIFIED | Exemplar policy applied; strict completeness would mark omissions (`GLY`, `H2O`). `judgment=required` |
| RNAMOD-S2-01 | S2 | Each listed consume entry is claimed to flow through OC substrate-delta path (`karr_rna_modification.py:244-281`). | MATLAB consumes via negative stoich in reaction loop and applies net substrate delta (`RNAModification.m:327-357`). | OC consume path is real: negative stoich limits in `_substrate_limit_for_reaction` (`karr_rna_modification.py:415-424`) and substrate update via `substrate_delta` (`karr_rna_modification.py:271-281`). | VERIFIED | Consume fabrication confirmed for all row-listed exemplars. |
| RNAMOD-S3-01 | S3 | `produce_stoichiometry` lists representative products (`AHCYS`, `AMP`, `H`, `PPI`, `THF`). | MATLAB net products come from full stoich writeback (`RNAModification.m:356-357`); produced families include `AHCYS, AMP, H, H2O, PPI, SER, THF` (fixture-derived from MATLAB stoich). | OC net products come from same `reaction_stoich @ reaction_events` path (`karr_rna_modification.py:271-281`), yielding same produced family set. | VERIFIED | Exemplar policy applied; strict completeness would mark omissions (`H2O`, `SER`). `judgment=required` |
| RNAMOD-S3-02 | S3 | Row-listed produce entries are claimed to use the same stoichiometric writeback path as consume side. | MATLAB produces through `this.substrates += reactionStoichiometryMatrix * ...` (`RNAModification.m:356-357`). | OC produces through `substrate_delta = reaction_stoich @ reaction_events` and emits nonzero deltas (`karr_rna_modification.py:271-281`). | VERIFIED | Produce fabrication confirmed for all row-listed exemplars. |
| RNAMOD-S4-01 | S4 | Row declares MATLAB request formula (`max(0,-S)*min(ceil(C*E*dt), M*U)`) and OC shared availability request formula. | MATLAB request formula is exactly `max(0, -this.reactionStoichiometryMatrix) * min(ceil(this.reactionCatalysisMatrix * this.enzymes * this.stepSizeSec), (this.reactionModificationMatrix * this.unmodifiedRNAs))` (`RNAModification.m:289-294`). | OC shared RNA-pathway request uses `_request_from_available` (availability only, active-gated) for RM consumed WIDs (`karr_request_calculators.py:21-30, 350-353`). | CODE_DEVIATES | Row correctly captures MATLAB-vs-OC formula divergence. |
| RNAMOD-S4-02 | S4 | Row states substrate/RNA deltas are assembled from reaction stoichiometry and completed reaction events. | MATLAB updates substrates and RNA counts via linear transforms of reaction completion counts (`RNAModification.m:356-361`). | OC computes `reaction_events = reaction_modification @ transition_events`, then substrate/RNA deltas (`karr_rna_modification.py:271-299`), matching the same transform family. | VERIFIED | Formula family equivalence holds modulo syntax/shape conventions. |
| RNAMOD-S4-03 | S4 | Row deviations note OC adds deterministic pass + stochastic residual with iteration cap, unlike MATLAB unbounded stochastic `while true`. | MATLAB uses unbounded stochastic loop with weighted sampling until infeasible (`RNAModification.m:327-348`). | OC runs deterministic phase then capped stochastic residual iterations (`karr_rna_modification.py:344-380`), parameterized by `max_stochastic_iterations`. | CODE_DEVIATES | Row accurately documents non-equivalent sampling/control-flow formula family. |
| RNAMOD-S5-01 | S5 | Row routes listed substrates/products to `cytosol` compartments. | MATLAB RNA reads/writes explicitly at `compartment.cytosolIndexs` (`RNAModification.m:242-243,250-251`); substrate stoich operates one local substrate compartment index set for this process. | OC uses one WID-keyed `substrates` store and writes deltas without compartment axis (`karr_rna_modification.py:115-120,271-281`). | VERIFIED | Single-compartment tuple alignment supported; fixture compartment indices are uniform but label mapping is indirect. `judgment=required` |
| RNAMOD-S5-02 | S5 | Row sets `shared_pool_projection_merges_compartments: false`. | MATLAB path performs direct local substrate vector updates (no explicit compartment projection/merge op in `evolveState`). | OC performs direct per-WID delta emission (no `sum(axis=...)` / flatten projection in RNAModification path), with direct topology wiring to shared stores (`karr_composite.py:1356-1363`). | VERIFIED | Projection/merge mismatch not observed for this process surface. `judgment=required` |
| RNAMOD-S6-01 | S6 | Row allocator mode says Karr=`allocation`, OC=`allocation`; OC consumes `substrates_allocated[self.name]`. | MATLAB exposes allocator-facing request method `calcResourceRequirements_Current` (`RNAModification.m:289-294`) and consumes allocated process substrate state in `evolveState`. | OC allocator chain is active: shared request step emits RM requests (`karr_request_calculators.py:335-359`), allocation step grants into `substrates_allocated` (`karr_composite.py:1453-1457`), RM process reads only allocated pool with strict no-fallback (`karr_rna_modification.py:185-193`). | VERIFIED | Allocator engagement mode matches (request/grant path is present and consumed). |
| RNAMOD-S6-02 | S6 | Row ordering constraints claim no RNAModification-specific hard order exception; only canonical scheduler hard edge is `tRNAAminoacylation < Translation`. | Harness design notes Karr scheduler hard edge `tRNAAminoacylation < Translation` (`L2_5_HARNESS_DESIGN.md:88-90`), with no RNAModification-specific exception documented there. | OC flow enforces request calculators before allocation (`karr_composite.py:1540-1562`), and RM process is wired to allocator outputs (`karr_composite.py:1356-1363`). | VERIFIED | Allocator-coupled ordering claim is consistent at documented wiring level; engine runtime ordering semantics remain a residual risk. `judgment=required` |

## Aggregate Counts
- VERIFIED: 8
- ROW_WRONG: 0
- CODE_DEVIATES: 3
- MISSING: 0

## Priority-1 fixes
Priority-1 fixes: none

## Known-deviation mapping (optional)
- RNAMOD-D1: request formula divergence (MATLAB process-local formula vs OC shared availability request) -> `RNAMOD-S4-01` (`CODE_DEVIATES`).
- RNAMOD-D2: stochastic execution divergence (MATLAB unbounded weighted loop vs OC deterministic+capped residual) -> `RNAMOD-S4-03` (`CODE_DEVIATES`).
- RNAMOD-D3: allocator wiring adaptation (shared request calculator + split protein/complex enzyme surfaces) remains semantically allocator-engaged -> captured across `RNAMOD-S6-01` (`VERIFIED`) and row deviation notes.

## Auditor discretion list (optional)
- RNAMOD-S1-01 (`judgment=required`): exemplar-vs-strict completeness policy.
- RNAMOD-S3-01 (`judgment=required`): exemplar-vs-strict completeness policy.
- RNAMOD-S5-01 (`judgment=required`): compartment index label resolution from flattened fixture.
- RNAMOD-S5-02 (`judgment=required`): no-merge conclusion conditioned on single-compartment process surface.
- RNAMOD-S6-02 (`judgment=required`): static flow evidence vs full runtime scheduling semantics.
