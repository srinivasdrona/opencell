# tRNAAminoacylation Semantic Audit

## INTENT (Deliberate Action Prefix v2)
- Beat 1 (contract): Validate whether the row for `tRNAAminoacylation` semantically matches MATLAB behavior and OC behavior for S1-S6, using executable logic rather than anchor presence.
- Beat 2 (surface): Read row schema, MATLAB process code, OC process code, OC request-calculator code, plus MATLAB simulation ordering/allocation and OC composite flow where ordering/allocation coupling is claimed.
- Beat 3 (expected outcome): Produce a claim table with only `VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, `MISSING`, plus deterministic aggregate counts and Priority-1 row remediation items.
- Beat 4 (invert): This audit could look complete but still be wrong if exemplar-style row snippets are treated as exhaustive without declaring scope policy; or if MATLAB ordering guarantees are assumed to exist in OC without scheduler evidence.
- Beat 5 (act/verify): Claims below cite concrete formulas/branches/store routes and include `judgment=required` where attribution depends on policy or runtime-order interpretation.
- PM sanity-check: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Design Contract (Revision-Class Minimum)
Semantic truth being checked: for each audited claim, the row must either faithfully describe matched MATLAB/OC behavior, or explicitly and correctly describe divergence, without omission/ambiguity in a way that changes remediation ownership.

## Header
- Process name: `tRNAAminoacylation` (`t_rna_aminoacylation`)
- Audited files:
  - `data/schemas/per_process_wiring/tRNAAminoacylation.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/tRNAAminoacylation.m`
  - `opencell/vivarium/karr_trna_aminoacylation.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m` (ordering/allocation coupling evidence)
  - `opencell/vivarium/karr_composite.py` (OC runtime wiring/ordering evidence)
- Scope policy: **strict completeness** (row does not declare exemplar-only scope for consume/produce/request enumerations).

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| TRNA-S1-01 | S1 | `consume_stoichiometry` enumerates consume side as `{ATP, ALA, GLN, H2O, FTHF10}` (`tRNAAminoacylation.yaml:182-237`). | Consume update uses full `reactionStoichiometryMatrix` row-space (`tRNAAminoacylation.m:458-459`) with amino-acid/glutamine/water/formyl donors indexed broadly (`:190-203`, `:266-270`). | Fixture-backed stoich consume set is 23 WIDs; row misses 18 (`ARG, ASN, ASP, CYS, GLU, GLY, HIS, ILE, LEU, LYS, MET, PHE, PRO, SER, THR, TRP, TYR, VAL`) from `reaction_stoich` sign probe and process matrix use (`karr_trna_aminoacylation.py:127`, `:270-282`). | MISSING | `judgment=required` (scope policy strict; row lacks exemplar declaration). |
| TRNA-S2-01 | S2 | Each listed consume entry has MATLAB+OC anchors (`tRNAAminoacylation.yaml:183-237`). | Listed substrates are consumed through stoich projection path (`tRNAAminoacylation.m:458-459`, plus transfer remap `:266-270`). | OC consumes via `substrate_delta = reaction_stoich @ (...)` (`karr_trna_aminoacylation.py:270-282`), and request path targets consumed stoich WIDs (`karr_request_calculators.py:241-244`, `:276-283`). | VERIFIED | No fabricated consume entries among row-listed WIDs. |
| TRNA-S3-01 | S3 | `produce_stoichiometry` enumerates produce side as `{ADP, AMP, PPI, PI, THF}` (`tRNAAminoacylation.yaml:238-293`). | Produce update is also full stoich row-space (`tRNAAminoacylation.m:458-459`); transfer remap explicitly includes `GLU` production path (`:267`) and stoich includes additional byproduct channels. | Fixture-backed produce set is 7 WIDs; row omits `GLU` and `H` (`karr_trna_aminoacylation.py:127`, `:270-282`). | MISSING | `judgment=required` (scope policy strict; row lacks exemplar declaration). |
| TRNA-S3-02 | S3 | Each listed produce entry has MATLAB+OC anchors (`tRNAAminoacylation.yaml:239-293`). | Listed byproducts are emitted via stoich writeback (`tRNAAminoacylation.m:458-459`, transfer-specific `:266-270`). | OC emits same listed byproducts through stoich projection (`karr_trna_aminoacylation.py:270-282`). | VERIFIED | No fabricated produce entries among row-listed WIDs. |
| TRNA-S4-01 | S4 | Evolve-state mutation flow is semantically preserved (`methods.evolveState` + consume/produce formulas; `tRNAAminoacylation.yaml:112-133`, `:182-293`). | Substrate delta formula is `reactionStoichiometryMatrix * reactionModificationMatrix * reactionFluxes` (`tRNAAminoacylation.m:458-459`). | OC computes `reaction_events_by_rxn = reaction_modification @ reaction_fluxes`, then `substrate_delta = reaction_stoich @ reaction_events_by_rxn` (`karr_trna_aminoacylation.py:267-271`), algebraically equivalent modulo orientation. | VERIFIED | Matrix multiplication family matches modulo syntax/shape orientation. |
| TRNA-S4-02 | S4 | Row explicitly states request-formula divergence (MATLAB `max(0,-stoich)*min(...)` vs OC availability/ATP*25 shim) (`tRNAAminoacylation.yaml:156-160`, `:469`). | MATLAB request formula exactly `max(0, -reactionStoichiometryMatrix) * min(reactionModification*(free+amino+1), reactionCatalysis*enzymes*stepSizeSec)` (`tRNAAminoacylation.m:380-384`). | OC request formula is active-gated availability request with ATP scaled `avail*25.0` (`karr_request_calculators.py:268-283`). | CODE_DEVIATES | Row correctly attributes real MATLAB-vs-OC formula deviation. |
| TRNA-S4-03 | S4 | Row calls out OC guard/rounding deviation in flux loop (`tRNAAminoacylation.yaml:133`, `:470`). | MATLAB loop is unbounded `while true` until limits empty (`tRNAAminoacylation.m:410-423`), then direct matrix writeback (`:458-459`) without OC-style final `rint`. | OC loop is bounded by `max_stochastic_iterations` (`karr_trna_aminoacylation.py:16`, `:376-377`) and rounds reaction events/substrate deltas with `np.rint` (`:268`, `:271`). | CODE_DEVIATES | Row correctly records non-equivalent stochastic/rounding behavior. |
| TRNA-S5-01 | S5 | Compartment routing is cytosol with no mismatch for listed metabolites (`tRNAAminoacylation.yaml:294-344`, `shared_pool_projection_merges_compartments=false` at `:467`). | Process compartment is cytosol (`tRNAAminoacylation.m:180-181`); RNA copy in/out is explicitly cytosolic (`:305-306`, `:313-314`); substrate updates apply to process substrate vector (`:458-459`). | OC stores substrates by WID (no explicit compartment axis) and reads/writes through single pooled substrate maps (`karr_trna_aminoacylation.py:145-148`, `:215-219`, `:276-282`). | VERIFIED | `judgment=required` (projection implicit: no OC compartment axis; no observed merge loss for this process because substrate channels are single-compartment in fixture). |
| TRNA-S6-01 | S6 | Allocator mode is `allocation` in both systems (`tRNAAminoacylation.yaml:152-155`). | Simulation computes `calcResourceRequirements_Current`, allocates, injects allocation into `mod.substrates`, then writes usage back (`@Simulation/evolveState.m:31-37`, `:63-73`). | OC split path: request step emits into `requests` (`karr_request_calculators.py:258-283`), process consumes grants from `substrates_allocated[self.name]` (`karr_trna_aminoacylation.py:215-219`). | VERIFIED | Allocator engagement mode matches (request/grant consumption path present). |
| TRNA-S6-02 | S6 | `allocator.requests` lists ATP/ALA/GLN/H2O/FTHF10 as shared demand surface (`tRNAAminoacylation.yaml:160-180`). | MATLAB request formula projects demand across all consumed stoich rows, not only 5 exemplars (`tRNAAminoacylation.m:380-384`). | OC request calculator builds consumed-WID set from full stoich negativity (`karr_request_calculators.py:16-18`, `:241-244`) and fills those when active (`:276-283`). | MISSING | Row omits allocator-request claims for additional consumed donors (same 18 amino-acid channels omitted in S1 completeness). |
| TRNA-S6-03 | S6 | `ordering_constraints.hard_before: Translation` presented as process constraint (`tRNAAminoacylation.yaml:366-372`). | MATLAB enforces `tRNAAminoacylation` before `Translation` via `randperm` resampling (`@Simulation/evolveState.m:50-57`). | OC process/request files contain no translation-order constraint; runtime composite flow constrains request calculators before allocation but does not encode TRNA-before-Translation process dependency, and process map order places translation before TRNA (`karr_composite.py:2295-2299`, `:2334-2357`). | ROW_WRONG | `judgment=required` (OC engine scheduling semantics could evolve, but no explicit hard-before constraint is encoded in current runtime wiring). |

## Aggregate Counts
- VERIFIED: 5
- ROW_WRONG: 1
- CODE_DEVIATES: 2
- MISSING: 3

## Priority-1 Fixes
- TRNA-S1-01 (`MISSING`): expand `consume_stoichiometry` to full consumed substrate set (or explicitly declare exemplar scope policy).
- TRNA-S3-01 (`MISSING`): add omitted produce channels (`GLU`, `H`) or explicitly declare exemplar scope policy.
- TRNA-S6-02 (`MISSING`): expand `allocator.requests` enumeration to match full consumed request surface.
- TRNA-S6-03 (`ROW_WRONG`): revise ordering claim to distinguish MATLAB hard-before from OC runtime behavior (or add OC scheduler evidence if truly enforced).

## Decision Ledger (Non-Obvious Attribution)
- D1: Completeness policy for S1/S3/S6 request list.
  - Options: exemplar-scoped vs strict.
  - Chosen: strict completeness.
  - Rationale: row has no explicit non-exhaustive declaration.
  - Falsifier: if row policy text is added declaring exemplar scope, these `MISSING` claims should be re-attributed.
- D2: Ordering attribution (`ROW_WRONG` vs `CODE_DEVIATES`).
  - Options: mark code deviation only vs mark row wrong.
  - Chosen: `ROW_WRONG`.
  - Rationale: row states hard-before as if current constraint but does not record OC non-enforcement.
  - Falsifier: explicit OC hard-before constraint in runtime flow/scheduler would overturn this verdict.
- D3: MATLAB consume/produce substrate universe evidence source.
  - Options: prose-only inference vs matrix-sign extraction.
  - Chosen: matrix-sign extraction (fixture-backed) plus MATLAB full-row formula evidence.
  - Rationale: set completeness is data-driven and more reproducible via stoich sign probe.
  - Falsifier: fixture/model mismatch against current MATLAB KB export for this process.

## Risks (Unresolved Ambiguity)
- R1: OC process execution order may depend on engine semantics beyond explicit `flow`; if engine introduces deterministic process ordering guarantees elsewhere, TRNA-S6-03 could need reclassification.
- R2: Stoichiometry set extraction used fixture-backed matrices; if fixture drifts from source MATLAB KB state, S1/S3 exact omission lists may change.
- R3: Compartment projection is implicit in OC WID-only substrate maps; if future multi-compartment substrate channels are introduced, S5 verdict may flip without row schema changes.

## Known-Deviation Mapping
- KD-TRNA-1 -> TRNA-S4-02 (request formula divergence).
- KD-TRNA-2 -> TRNA-S4-03 (stochastic iteration cap + rounding divergence).

## Auditor Discretion List
- TRNA-S1-01 (`judgment=required`: strict vs exemplar policy).
- TRNA-S3-01 (`judgment=required`: strict vs exemplar policy).
- TRNA-S5-01 (`judgment=required`: implicit compartment projection interpretation).
- TRNA-S6-03 (`judgment=required`: OC scheduler semantics vs explicit constraints).
