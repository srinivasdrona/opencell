# TranscriptionalRegulation Semantic Audit

Header block:
- Process name: `TranscriptionalRegulation` (`transcriptional_regulation`)
- Audited files:
  - `data/schemas/per_process_wiring/TranscriptionalRegulation.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/TranscriptionalRegulation.m`
  - `docs/karr_extracts/process/10_TranscriptionalRegulation.md`
  - `docs/karr_extracts/architecture/03_variable_allocation.md`
  - `docs/karr_extracts/architecture/01_simulation_loop.md`
  - `docs/design/pb_turn3_transcriptional_regulation.md`
  - `opencell/vivarium/karr_transcriptional_regulation.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: **strict completeness** (not exemplar-scoped)

## Deliberate Action Prefix v2

Beat 1 - contract:
- Required behavior: classify S1-S6 row claims against executable MATLAB and OC semantics using only `VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`.
- Done property: an independent auditor can reproduce the same verdicts from the same line-level sources.

Beat 2 - surface:
- Read surfaces: row YAML wiring claims; MATLAB `initializeState`, `calcResourceRequirements_Current`, `evolveState`, `bindTranscriptionFactors`, `calcBindingProbabilityFoldChange`; OC `ports_schema`, `_read_tf_counts`, `next_update`; chassis topology/allocation wiring in `karr_composite.py`; Karr allocation/loop extracts.
- Suspect patterns called out before attribution: (a) "regulatory-only" prose masking allocator engagement via zero-vector requests, (b) strand-axis projection in MATLAB hidden by scalar fold-change store in OC.

Beat 3 - expected outcome:
- Observable: one claim table covering S1-S6 with deterministic claim IDs, allowed verdict vocabulary, aggregate counts, and Priority-1 row remediations.

Beat 4 - inversion (pre-mortem):
- Most embarrassing false-pass: concluding "no substrate stoichiometry => full parity" while missing MATLAB allocator participation (`calcResourceRequirements_Current` is invoked every tick) and missing MATLAB accessibility gating in binding-site selection.

Beat 5 - act then verify:
- Verification evidence is embedded claim-by-claim in the table below with concrete source lines and explicit discretionary flags.
- PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Design Contract
This audit checks the semantic truth that the row's consume/produce/formula/routing/allocator claims are behaviorally consistent with executed MATLAB logic and current OC runtime wiring, not merely anchor presence.

## Decision Ledger

Decision D1
- Question: Completeness policy for `consume_stoichiometry` / `produce_stoichiometry` empties?
- Options considered: (1) strict completeness, (2) exemplar-scoped completeness.
- Chosen option: strict completeness.
- Rationale: row does not declare exemplar scope; empty lists are therefore exhaustive claims.
- Beat-4 inversion: strict mode can over-call omissions when row intended examples.
- Falsifier: explicit row declaration of exemplar-only scope.

Decision D2
- Question: How to classify allocator mode when MATLAB requests are always zero?
- Options considered: (1) bypass, (2) engaged-zero-request.
- Chosen option: engaged-zero-request for MATLAB.
- Rationale: MATLAB simulation loop still calls `calcResourceRequirements_Current` and enters allocation math for every process.
- Beat-4 inversion: labeling this bypass would hide real MATLAB-vs-OC participation divergence.
- Falsifier: evidence that MATLAB excludes this process from the requirement/allocation loop.

Decision D3
- Question: Should MATLAB strand-axis (`nTU x 2`) to OC scalar-per-TU be treated as S5 projection/merge?
- Options considered: (1) ignore as non-compartment axis, (2) treat as routing projection.
- Chosen option: treat as routing projection under S5.
- Rationale: S5 explicitly requires projection/merge checks; this is a state-shape projection that changes tuple targeting semantics.
- Beat-4 inversion: overextending "compartment" could misclassify harmless dimensional reductions.
- Falsifier: authoritative policy restricting S5 strictly to biochemical compartments only.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| TR-S1-01 | S1 | `consume_stoichiometry: []` and "no substrate stoichiometry" (`TranscriptionalRegulation.yaml:11,94`). | `calcResourceRequirements_Current` returns zeros; `evolveState` only computes TF binding/fold-change (`TranscriptionalRegulation.m:334-346`). | `next_update` emits `tf_binding` and `tx_rate_fold_change` only (`karr_transcriptional_regulation.py:420-425`); chassis topology for this process has no `substrates` port (`karr_composite.py:1342-1346`). | VERIFIED | Strict completeness policy applied. |
| TR-S2-01 | S2 | No consume entries are declared (`TranscriptionalRegulation.yaml:94`). | No substrate consume formula beyond zero request vector (`TranscriptionalRegulation.m:334-336`). | No substrate-delta consume path exists in process update payload (`karr_transcriptional_regulation.py:420-425`). | VERIFIED | Vacuous fabrication check (empty row consume set). |
| TR-S3-01 | S3 | `produce_stoichiometry: []` (`TranscriptionalRegulation.yaml:95`). | No byproduct production path; lifecycle method returns zero byproducts and no substrate writes in `evolveState` (`TranscriptionalRegulation.m:315-319,339-346`). | No substrate-production update path (`karr_transcriptional_regulation.py:420-425`). | VERIFIED | Strict completeness policy applied. |
| TR-S4-01 | S4 | Row describes per-tick weighted TF binding + fold-change sweep (`TranscriptionalRegulation.yaml:43-45`). | Binding uses TF-specific site set with affinity-weighted stochastic bind (`TranscriptionalRegulation.m:371-379`). | Binding chooses available promoters with affinity-derived probabilities (`karr_transcriptional_regulation.py:373-384`). | VERIFIED | Weighted-binding family matches modulo API syntax. |
| TR-S4-02 | S4 | Row does not claim any chromosome accessibility gate in binding-site selection (`TranscriptionalRegulation.yaml:43-45`). | Candidate sites are gated by chromosome accessibility (`isRegionPolymerized`) before sampling (`TranscriptionalRegulation.m:355,371`). | Process has no chromosome port and no accessibility predicate; candidates are `(row==0) & (affinity>0)` (`karr_transcriptional_regulation.py:281-318,373`). | MISSING | MATLAB behavior exists but is omitted from row semantic claims. |
| TR-S4-03 | S4 | Row claims fold-change product semantics (`TranscriptionalRegulation.yaml:43-45`). | Fold-change multiplies bound TF effects and TF-presence `otherActivities` effects (`TranscriptionalRegulation.m:383-400`). | `fold_change_total = prod(bound_effects) * prod(other_effects for tf_present)` (`karr_transcriptional_regulation.py:391-408`). | VERIFIED | `judgment=required` (equivalence accepted modulo MATLAB strand-axis duplication; projection handled in S5). |
| TR-S5-01 | S5 | Row routes TF abundance reads as monomers from `protein.counts` and dimers from `complex.counts` (`TranscriptionalRegulation.yaml:73-93`). | MATLAB explicitly enumerates the same monomer/dimer TF IDs and maps monomer/complex indices (`TranscriptionalRegulation.m:202-206,231-267`). | OC enforces TF source partition via `_tf_wid_source` and `_read_tf_counts`; complex TF source list is seeded in chassis (`karr_transcriptional_regulation.py:267-337`; `karr_composite.py:1035-1045,1342-1346`). | VERIFIED | `judgment=required` (row labels "cytosol" while OC store routing is source-store based, not explicit compartment indexing). |
| TR-S5-02 | S5 | Row asserts no projection/merge mismatch (`shared_pool_projection_merges_compartments: false`, all `mismatch: false`) (`TranscriptionalRegulation.yaml:96-121,221`). | MATLAB fold-change state is TU-by-strand (`ones(...,2)` and two-column updates) (`TranscriptionalRegulation.m:385,394-395,399`). | OC emits a single scalar fold-change per TU (`karr_transcriptional_regulation.py:314-317,422-424`). | ROW_WRONG | `judgment=required` (strand-axis projection treated as required S5 projection/merge disclosure). |
| TR-S6-01 | S6 | Row states allocator bypass on both sides and claims no MATLAB resource-requirement method in local sources (`TranscriptionalRegulation.yaml:29-30,65-71`). | MATLAB implements `calcResourceRequirements_Current` (zero vector) and simulation loop calls it for every process before allocation (`TranscriptionalRegulation.m:334-336`; `01_simulation_loop.md:148-161`; `03_variable_allocation.md:14-23`). | OC bypasses allocator for TR: no request-calculator enrollment/consumer entry and no `requests`/`substrates_allocated` topology ports (`karr_composite.py:1107-1133,1342-1346`). | ROW_WRONG | MATLAB mode is engaged-zero-request, not bypass; row attribution is incorrect. |
| TR-S6-02 | S6 | Row records known deviation: OC performs first binding sweep on tick 1, not MATLAB t=0 pre-binding (`TranscriptionalRegulation.yaml:225`). | MATLAB `initializeState` calls `evolveState` before normal tick progression (`TranscriptionalRegulation.m:329-331`). | OC documents "No explicit t=0 pre-binding" and does first sweep in `next_update`; chassis state seeds `tx_rate_fold_change` but not `tf_binding` (`karr_transcriptional_regulation.py:5-12,350-389`; `karr_composite.py:1489-1497`). | CODE_DEVIATES | Row correctly describes this MATLAB-vs-OC temporal divergence. |

Aggregate counts:
- VERIFIED: 6
- ROW_WRONG: 2
- CODE_DEVIATES: 1
- MISSING: 1

Priority-1 fixes:
1. `TR-S4-02` (`MISSING`): add explicit row claim for MATLAB accessibility gating (`isRegionPolymerized`) and OC non-implementation status.
2. `TR-S5-02` (`ROW_WRONG`): remediate projection/merge statement; disclose MATLAB strand-axis output vs OC scalar-per-TU routing.
3. `TR-S6-01` (`ROW_WRONG`): correct allocator mode attribution to "MATLAB engaged-zero-request vs OC bypass"; remove "no method found" claim.

Known-deviation mapping:
- KD-TR-01: tick-0 pre-binding divergence -> `TR-S6-02` (`CODE_DEVIATES`).

Auditor discretion list:
- `TR-S4-03` (`judgment=required`)
- `TR-S5-01` (`judgment=required`)
- `TR-S5-02` (`judgment=required`)

## Risks (Unresolved Ambiguity)

R1. Strand-axis vs compartment-axis interpretation for S5 projection checks.
- Likelihood: medium
- Impact: medium (can change S5 attribution class)
- Mitigation: codify whether S5 includes non-compartment state-shape projection.

R2. MATLAB free-vs-total TF count semantics around binding/unbinding are implicit.
- Likelihood: medium
- Impact: low-to-medium (could affect finer-grained S4 parity claims not asserted here)
- Mitigation: trace `Process`/chromosome state coupling for `enzymes` and `isDnaBound` in a follow-up deep audit.
