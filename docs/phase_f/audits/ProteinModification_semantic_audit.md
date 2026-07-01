# ProteinModification Semantic Audit

## Header
- Process name: `protein_modification` (`ProteinModification`)
- Header note: `FULL`
- Audited files:
  - `data/schemas/per_process_wiring/ProteinModification.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinModification.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m` (allocator/order evidence)
  - `docs/design/pb_turn8_protein_modification.md`
  - `plan.md`
  - `docs/design/pb_final_chassis_v4_integration.md`
  - `opencell/vivarium/karr_protein_modification.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_allocation_step.py`
- Scope policy: `strict completeness` (row does not declare exemplar-only scope).

## Slot 1: DELIBERATE_ACTION_PREFIX_v2
- Beat 1 (contract): verify/falsify row semantics for consume/produce/formula/compartment/allocator behavior against executable MATLAB and OC logic.
- Beat 2 (surface): row schema, MATLAB process + simulation allocator flow, OC process + request calculator + allocation step.
- Beat 3 (expected outcome): S1-S6 claim table with only `VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`, plus deterministic totals and Priority-1 fixes.
- Beat 4 (invert): this audit could look complete but be wrong if stale doc anchors (`plan.md` line ranges) are treated as behavioral truth instead of `ProteinModification.m` executable branches.
- Beat 5 (verify): each claim below cites concrete formulas/routes/branches; discretionary claims are flagged `judgment=required`.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Revision-Class Minimum
- Design contract sentence: the semantic truth being checked is whether row-level wiring claims are reproducible from current MATLAB `ProteinModification` behavior and current OC ProteinModification runtime behavior, not just anchor existence.

### Decision ledger (non-obvious attribution calls)
- D1: Used strict completeness for S1/S3 because row does not mark exemplar scope.
- D2: Classified allocator request-formula mismatch as `ROW_WRONG` (not `CODE_DEVIATES`) because row misstates MATLAB behavior before divergence attribution.
- D3: Kept S5 tuple-routing verdict `VERIFIED` with `judgment=required` because fixture flattening preserves numeric compartment index but hides label names.
- D4: Classified stale MATLAB doc anchors (`plan.md` ranges now unrelated) as semantic row defects (`ROW_WRONG`, anchor rot) since they prevent reproducible claim validation.

### Risks (unresolved ambiguity)
- R1: Scheduler-order precondition behind “equivalent under scheduler control” is not proven from the three OC files alone.
- R2: Compartment label resolution from flattened fixture is partial (index observed, textual compartment label inferred).
- R3: Replay `trace_hint` path is optional/runtime-conditional; production prevalence is not established in this audit.

## Claims
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| PM-S1-01 | S1 | Consume set is ATP/GLU/LIPOYLAMP (`ProteinModification.yaml:123-156`). | Consumed metabolites are stoich-negative rows projected in substrate update (`ProteinModification.m:324-327`, `ProteinModification.m:386-389`); fixture probe consumed set is ATP/GLU/LIPOYLAMP. | Same stoich family is consumed through `substrate_delta = reaction_stoich @ reaction_fluxes` (`karr_protein_modification.py:267-276`). | VERIFIED | Strict completeness satisfied. |
| PM-S2-01 | S2 | Each consume row is fabricated via OC stoich projection (`ProteinModification.yaml:131-156`). | Consumption is applied by substrate projection (`ProteinModification.m:387-389`). | Negative deltas are written to `substrates` (`karr_protein_modification.py:268-279`); request path targets consumed rows (`karr_request_calculators.py:392-394`, `karr_request_calculators.py:518-520`). | VERIFIED | Consume entries have real OC consume path. |
| PM-S3-01 | S3 | Produce set is ADP/AMP/H/PI (`ProteinModification.yaml:157-201`). | Produced byproducts are stoich-positive rows in same substrate projection (`ProteinModification.m:155-158`, `ProteinModification.m:387-389`); fixture probe produced set is ADP/AMP/H/PI. | Positive `substrate_delta` entries are emitted to `substrates` (`karr_protein_modification.py:268-279`). | VERIFIED | Completeness + fabrication both hold. |
| PM-S4-01 | S4 | MATLAB request formula is “active gate + max(0, available substrate counts)” (`ProteinModification.yaml:85-88`). | Actual MATLAB request formula is `max(0,-S) * min(ceil(C*E*dt), R*U)` (`ProteinModification.m:324-327`) and does not read available substrate counts. | OC request uses available-count identity for consumed rows with activity gate (`karr_request_calculators.py:21-29`, `karr_request_calculators.py:486-489`, `karr_request_calculators.py:518-520`). | ROW_WRONG | Row misstates MATLAB and masks real MATLAB-vs-OC request-formula drift. |
| PM-S4-02 | S4 | Stochastic feasibility + weighted draw structure matches (`ProteinModification.yaml:46-62`). | MATLAB builds species matrices then applies stochasticRound + weighted `randsample` loop (`ProteinModification.m:215-222`, `ProteinModification.m:359-379`). | OC mirrors this with `_build_species_matrices`, `_stochastic_round_vector`, `_weighted_index_sample`, and species decrement loop (`karr_protein_modification.py:465-480`, `karr_protein_modification.py:401-427`, `karr_protein_modification.py:482-501`). | VERIFIED | Formula family matches modulo syntax/implementation detail. |
| PM-S4-03 | S4 | OC has replay-only `trace_hint` short-circuit not present in MATLAB (`ProteinModification.yaml:60-62`, `ProteinModification.yaml:365`). | No `trace_hint` branch in MATLAB evolveState (`ProteinModification.m:331-393`). | Optional replay hook bypasses sampler when hint present (`karr_protein_modification.py:255-257`, `karr_protein_modification.py:298-324`). | CODE_DEVIATES | Row correctly documents MATLAB-vs-OC divergence. |
| PM-S4-04 | S4 | Consume/produce formulas are `reactionStoichiometryMatrix(row,:) * reactionFluxes` (`ProteinModification.yaml:126`, `ProteinModification.yaml:137`, `ProteinModification.yaml:148`, `ProteinModification.yaml:160`, `ProteinModification.yaml:171`, `ProteinModification.yaml:182`, `ProteinModification.yaml:193`). | MATLAB substrate update uses `reactionStoichiometryMatrix * reactionModificationMatrix(:,monomerIndexs_modified) * reactionFluxes` (`ProteinModification.m:387-389`). | OC also performs two-stage projection: `reaction_fluxes = reaction_modification @ protein_fluxes`; `substrate_delta = reaction_stoich @ reaction_fluxes` (`karr_protein_modification.py:267-269`). | ROW_WRONG | `judgment=required`: row formula could be shorthand, but as written is dimensionally incomplete vs executable path. |
| PM-S4-05 | S4 | MATLAB formula anchors rely on `plan.md:1198-1222` / `1198-1209` (`ProteinModification.yaml:22-24`, `ProteinModification.yaml:43-45`, `ProteinModification.yaml:293-299`). | Current `plan.md` lines 1198-1222 are handoff text, not ProteinModification formulas (`plan.md:1198-1222`); executable formulas live in `ProteinModification.m:324-327` and `ProteinModification.m:359-375`. | OC anchors are executable and present in code (`karr_protein_modification.py:196-481`, `karr_request_calculators.py:362-520`). | ROW_WRONG | Anchor rot in MATLAB evidence paths. |
| PM-S5-01 | S5 | All tracked consume/produce tuples are cytosolic; no compartment merge mismatch (`ProteinModification.yaml:202-237`, `ProteinModification.yaml:363`). | Simulation uses global-compartment indexed substrate allocation/writeback (`@Simulation/evolveState.m:32-33`, `@Simulation/evolveState.m:63-73`); fixture probe shows all active PM stoich rows share one compartment index (`distinct_comp_idx={1}`). | OC store is WID-flat for substrates (`karr_protein_modification.py:142-145`, `karr_protein_modification.py:272-279`) with no per-process compartment projection merge. | VERIFIED | `judgment=required`: comp_idx=1 interpreted as cytosol from process convention; flattened fixture does not expose compartment label text. |
| PM-S6-01 | S6 | Both sides are allocator-engaged; OC reads `substrates_allocated[self.name]` (`ProteinModification.yaml:81-84`). | MATLAB computes requirements and allocations then sets `mod.substrates = allocation` before evolve (`@Simulation/evolveState.m:31-37`, `@Simulation/evolveState.m:63-70`). | OC request calculator emits PM requests, allocator grants floor-scaled counts, and PM reads strict-zero allocated pool (`karr_request_calculators.py:518-520`, `karr_allocation_step.py:246-255`, `karr_protein_modification.py:205-213`). | VERIFIED | Engagement mode matches (`allocation` on both sides). |
| PM-S6-02 | S6 | Enzyme/protein bookkeeping bypasses allocator (`ProteinModification.yaml:102-122`). | MATLAB species vector includes enzymes + unmodified proteins as process-local species, separate from metabolite allocation requests (`ProteinModification.m:346-349`, `ProteinModification.m:361-364`). | OC reads required enzymes from `protein.counts`/`complex.counts` and unmodified proteins from `protein.unmodified_counts` (`karr_protein_modification.py:214-243`, `karr_protein_modification.py:356-371`). | VERIFIED | Bypass behavior is real and semantically aligned. |

## Aggregate Counts
- VERIFIED: 7
- ROW_WRONG: 3
- CODE_DEVIATES: 1
- MISSING: 0

## Priority-1 Fixes
- PM-S4-01 (`ROW_WRONG`): fix `allocator.request_formula.matlab` to executable MATLAB formula (`max(0,-S) * min(ceil(C*E*dt), R*U)`), and optionally record OC divergence explicitly.
- PM-S4-04 (`ROW_WRONG`): fix consume/produce formula text to include reaction-to-protein projection term (or explicitly define reactionFluxes symbol as post-projection).
- PM-S4-05 (`ROW_WRONG`): replace stale `plan.md` MATLAB anchors with direct `ProteinModification.m` line anchors.

## Known-Deviation Mapping (Optional)
- KD1: Replay hint short-circuit (`PM-S4-03`) -> `CODE_DEVIATES`.

## Auditor Discretion List
- PM-S4-04 (`judgment=required`)
- PM-S5-01 (`judgment=required`)
