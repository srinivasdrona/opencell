# MacromolecularComplexation Semantic Audit

## Header
- process name: `MacromolecularComplexation` (`macromolecular_complexation`)
- audited files:
  - `data/schemas/per_process_wiring/MacromolecularComplexation.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/MacromolecularComplexation.m`
  - `docs/design/a33_turn3_d2_real.md`
  - `docs/design/a3_step3_joint_design_v1.md`
  - `docs/phase_f/L2_5_HARNESS_DESIGN.md`
  - `opencell/vivarium/karr_macromolecular_complexation.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_allocation_step.py`
  - `opencell/vivarium/karr_macromolecular_complexation_stub.py`
  - `opencell/vivarium/karr_composite.py` (ordering evidence)
- scope policy: exemplar-scoped completeness (row explicitly marks representative consume/produce entries). Strict-completeness counterfactual is documented in Notes where applicable.

## DELIBERATE_ACTION_PREFIX_v2

### Beat 1 - Contract
Validate whether row-level semantic claims about consume/produce/formulas/compartments/allocator behavior are true against executable MATLAB and OC code paths. Done means each claim is reproducibly classified as `VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, or `MISSING` with source-backed evidence.

### Beat 2 - Surface
Read surfaces: row YAML (`consume_stoichiometry`, `produce_stoichiometry`, `allocator`, `deviations`), MATLAB `calcResourceRequirements_Current`, `evolveState`, MC/bounds helpers, MATLAB compartment copy paths, OC `next_update` + helpers, OC request calculator, OC allocation step, and OC chassis flow ordering.
Suspect patterns named before verdicting: stale row prose from prior OC revisions (Poisson claim), exemplar scope ambiguity, and compartment flattening risk hidden by representative-only tuples.

### Beat 3 - Expected Outcome
Expected output is a deterministic claim table covering S1-S6, using only allowed verdict vocabulary, plus aggregate totals and Priority-1 row-remediation list.

### Beat 4 - Invert (pre-mortem)
Worst embarrassing false-pass mode: treating design prose as runtime truth and missing branch-level drift (for example, row says Poisson multiplicity, but code increments one complex per MC iteration). Another false-pass mode: marking compartment routing as matched from exemplar cytosol rows while ignoring global compartment projection.
PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

### Beat 5 - Act, then verify
Action performed: claim-by-claim semantic comparison against code branches and formulas (plus fixture probe for compartment IDs and substrate/complex universe sizes).
Verification result: claim table and totals below include branch-level evidence and explicit discretionary notes.

## Revision-Class Minimum

### Design contract sentence
This audit checks semantic truthfulness of the row against MATLAB and OC behavior, not structural anchor presence.

### Decision ledger (non-obvious attribution)
- D1 (completeness attribution): Chosen policy is exemplar-scoped because row entries are labeled representative; strict policy would classify omitted substrate/complex universe entries as `MISSING`. Tradeoff accepted: completeness verdicts require `judgment=required` notes.
- D2 (allocator mismatch attribution): `ROW_WRONG` is used (not `CODE_DEVIATES`) when row states MATLAB/OC allocator engagement matches but OC actually hard-gates D2 on `substrates_allocated` while MATLAB evolves from `this.substrates`.
- D3 (compartment projection attribution): `ROW_WRONG` is used when row says no compartment merge but OC emits flat `complex.counts[wid]` while MATLAB writes compartment-indexed complex counts.

### Risks (unresolved ambiguity)
- Compartment name mapping ambiguity: audited files expose compartment IDs, not a direct ID->name map; exemplar cytosol labels are accepted only where row itself declares them.
- Engine scheduling semantics risk: ordering verification relies on chassis flow wiring + process read path; final runtime ordering is inferred from Vivarium step/process semantics and marked where judgment is required.

## Claim Table

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| MCX-S1-01 | S1 | `consume_stoichiometry` lists four representative monomers (yaml:147-195). | `this.substrates = this.substrates - this.complexComposition * newComplexs` applies over full substrate vector (m:313); fixture substrate universe is 210. | `delta_substrates = -(self.complex_composition @ new_complexes)` over full `self.substrate_wids` (py:244-250); fixture substrate universe is 210. | VERIFIED | Exemplar policy applied; strict completeness would be `MISSING` for non-listed consumed substrates. `judgment=required`. |
| MCX-S2-01 | S2 | Each listed consume formula is `-sum_c complexComposition[s,c] * newComplexs[c]` (yaml:150/162/174/186). | Same mass-balance subtraction path in evolveState (m:313). | Same subtraction path in emitted substrate deltas (py:244-250). | VERIFIED | Fabrication path exists for each row consume entry when its delta is nonzero in a tick. |
| MCX-S3-01 | S3 | `produce_stoichiometry` lists four representative produced complexes (yaml:196-244). | Produce side is `this.complexs = this.complexs + newComplexs` over all process complexes (m:312); fixture complex universe is 147. | Emits positive complex deltas from `new_complexes` for all process complexes (py:251-255); fixture complex universe is 147. | VERIFIED | Exemplar policy applied; strict completeness would be `MISSING` for non-listed produced complexes. `judgment=required`. |
| MCX-S3-02 | S3 | Listed produced complexes map to `newComplexs[wid]` (yaml:199/211/223/235). | `newComplexs` comes from cluster bounds + per-cluster MC (m:294-305), then added to `complexs` (m:312). | `new_complexes` comes from cluster bounds + per-cluster MC (py:220-242), then emitted to `complex.counts` (py:251-255). | VERIFIED | Produce fabrication path is real and branch-complete. |
| MCX-S4-01 | S4 | Row consume/produce formulas describe matrix mass-balance update (yaml:150-199,199-235). | Matrix mass-balance update is explicit (m:312-313). | Matrix mass-balance update is explicit (py:240-255). | VERIFIED | Formula family matches modulo OC delta-emission syntax. |
| MCX-S4-02 | S4 | `buildProteinComplexs_bounds` is implemented equivalently in OC (yaml:57-71). | `floor(min(totalProteinMonomers ./ proteinComplexMatrix, [], 1))'` (m:390-391). | `_closed_form_bounds` computes integer min over active stoich entries (py:80-90). | VERIFIED | Equivalent for nonnegative availability and stoichiometry. |
| MCX-S4-03 | S4 | Row claims OC MC helper has Poisson multiplicity and is not one-copy-per-iteration (yaml:56-57,84-87,396). | MC increments selected complex by exactly 1 per iteration (m:355). | MC increments selected complex by exactly 1 per iteration (py:135); no Poisson count sample exists. | ROW_WRONG | Stale row attribution; current OC code is one-copy-per-iteration like MATLAB. |
| MCX-S4-04 | S4 | Row claims OC adds cluster-1 fallback to MC guard (yaml:397). | Cluster-1 path is direct closed-form only (m:294-296). | Cluster-1 path falls back to `_per_cluster_mc` if overconsume guard trips (py:228-234). | CODE_DEVIATES | Row accurately describes a real MATLAB-vs-OC divergence. |
| MCX-S5-01 | S5 | Row states `shared_pool_projection_merges_compartments: false` and exemplar routing mismatches are false (yaml:245-285,394). | Complex state is compartment-indexed (`complexCompartmentIndexs`, `complexGlobalCompartmentIndexs`; m:149-153,216,235). | Complex output is flat `complex.counts[wid]` with no compartment axis (py:175-178,251-255). | ROW_WRONG | Fixture probe shows D2 complexes span at least two compartment IDs (`[1, 4]`), so OC flattening implies projection/merge loss. |
| MCX-S6-01 | S6 | Request formula is zero on both sides (`zeros(size(this.substrates))` vs zero request dict; yaml:109-112). | `calcResourceRequirements_Current` returns zeros (m:285-287). | `RequestCalculatorD2` writes zero requests for all D2 substrate WIDs (req:69,89). | VERIFIED | Request-surface equivalence is correct. |
| MCX-S6-02 | S6 | Row says Karr and OC allocator engagement modes match (`allocation`; yaml:105-109,34). | D2 evolveState consumes `this.substrates` directly (m:295,303,313). | D2 next_update reads only `states["substrates_allocated"][self.name]` (py:208-214) and returns no-op when allocation is zero (py:215-216). | ROW_WRONG | Row misses allocator-coupled behavioral divergence: OC hard-gates D2 by grants; MATLAB process logic is not coded that way. |
| MCX-S6-03 | S6 | Row anchors allocation-before-process sequencing (yaml:335-338). | Scheduler excerpt states precomputed allocation before process evolveState (L2_5:89-91). | Chassis flow enforces request calculators -> allocation step dependencies (composite:935-948), and D2 reads allocation store (py:208-214). | VERIFIED | Ordering-coupled claim supported by available wiring evidence. `judgment=required` for final runtime phase semantics outside these files. |

## Aggregate Counts
VERIFIED: 8
ROW_WRONG: 3
CODE_DEVIATES: 1
MISSING: 0

## Priority-1 fixes
- MCX-S4-03 (`ROW_WRONG`): remove/update stale Poisson multiplicity claim in row method/deviations prose.
- MCX-S5-01 (`ROW_WRONG`): correct compartment projection claim (`shared_pool_projection_merges_compartments`) and document flattening impact explicitly.
- MCX-S6-02 (`ROW_WRONG`): correct allocator engagement statement to reflect MATLAB `this.substrates` consumption vs OC grant-gated consumption.

## Known-deviation mapping (optional)
- KD-1: Cluster-1 fallback guard in OC (`MCX-S4-04`) is a real divergence and correctly captured as `CODE_DEVIATES`.

## Auditor discretion list
- MCX-S1-01: exemplar-scoped completeness policy selection (`judgment=required`).
- MCX-S3-01: exemplar-scoped completeness policy selection (`judgment=required`).
- MCX-S6-03: runtime ordering inference uses wiring evidence plus scheduler semantics outside strict file-local code (`judgment=required`).
