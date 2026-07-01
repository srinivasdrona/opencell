# ProteinTranslocation Semantic Audit

## Header
- Process name: `ProteinTranslocation` (`protein_translocation`)
- Audited files:
  - `data/schemas/per_process_wiring/ProteinTranslocation.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinTranslocation.m`
  - `docs/karr_extracts/process/22_ProteinTranslocation.md`
  - `docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md`
  - `opencell/vivarium/karr_protein_translocation.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_composite.py`
  - `opencell/vivarium/karr_allocation_step.py`
  - `tests/integration/test_ptransloc_enrollment_v3_v4.py`
  - `tests/vivarium/test_karr_protein_translocation.py`
  - `tests/vivarium/test_karr_request_calculators.py`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m` (allocator semantics support)
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m` (allocator/order semantics support)
- Scope policy: `strict completeness` (no exemplar-scoped completeness exception declared in row)
- Header note: `FULL` (not partial)

## Deliberate Action Prefix (v2)
- Beat 1 (contract): verify/falsify row semantic claims against executable MATLAB and OC behavior, and attribute each claim with the allowed verdicts only.
- Beat 2 (surface): row schema, MATLAB process + simulation allocator/order path, OC process/request/allocation/composite wiring, and listed tests were used as evidence surfaces.
- Beat 3 (expected outcome): a deterministic S1-S6 claim table with verdict totals and explicit row-remediation priorities.
- Beat 4 (invert): this audit could look complete but be wrong if it trusted stale extract prose over executable MATLAB/OC branches; falsifier is claim-level citation to executed formulas/branches.
- Beat 5 (verify): each claim below cites concrete branch/formula/routing/allocator evidence from row + MATLAB + OC.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

Design contract sentence: each claim is semantically valid only if row wording matches executable MATLAB and OC behavior (not anchor presence alone).

## Decision Ledger
- D1: MATLAB authority source
  - Decision: treat local `ProteinTranslocation.m` executable body as source-of-truth over extract prose when they differ.
  - Rationale: S4/S6 claims require executable control-flow/formula evidence.
- D2: Completeness attribution policy
  - Decision: use strict completeness for S1/S3.
  - Rationale: row does not declare exemplar-only consume/produce scope.
- D3: Allocator engagement attribution
  - Decision: include `Simulation/evolveState.m` for MATLAB grant injection semantics, not only process-local methods.
  - Rationale: S6 requires request/grant path validation, not just method existence.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| PT-S1-01 | S1 | `consume_stoichiometry` lists ATP/GTP/H2O in cytosol (`ProteinTranslocation.yaml:112-145`). | `evolveState` consumes ATP/GTP/H2O (`ProteinTranslocation.m:362-364`), matching substrate set (`:141-149`). | `next_update` decrements ATP/H2O and decrements GTP when SRP cost applies (`karr_protein_translocation.py:433-441`). | VERIFIED | Strict completeness satisfied for consume substrate set. |
| PT-S2-01 | S2 | Each row consume entry maps to OC consume anchor (`ProteinTranslocation.yaml:120-145`). | Per-copy consume path exists for ATP/H2O always and GTP when SRP-path monomer selected (`ProteinTranslocation.m:334-337`, `:362-364`). | Real consume path is emitted via negative substrate deltas (`karr_protein_translocation.py:433`, `:436`, `:440`). | VERIFIED | `judgment=required` (GTP is sign/pathway-dependent). |
| PT-S3-01 | S3 | `produce_stoichiometry` lists ADP/GDP/PI/H in cytosol (`ProteinTranslocation.yaml:146-190`). | `evolveState` produces ADP/GDP/PI/H (`ProteinTranslocation.m:365-368`). | `next_update` produces ADP/PI/H always when translocation occurs and GDP when GTP spent (`karr_protein_translocation.py:434-441`). | VERIFIED | `judgment=required` (GDP is sign/pathway-dependent). |
| PT-S4-01 | S4 | Row says OC uses species-phase batching and raw enzyme counts, not Karr rate-scaled checks (`ProteinTranslocation.yaml:53-55`, `:320-321`). | Karr uses one global `randperm` over monomer copies plus rate-scaled capacities and break-on-first-failure (`ProteinTranslocation.m:321-347`). | OC now uses copy-level `randperm(total_copies)`, rate-scaled capacities, and break-on-first-failure (`karr_protein_translocation.py:366-406`). | ROW_WRONG | Row deviation text is stale against current OC behavior. |
| PT-S4-02 | S4 | Row MATLAB request formula omits capacity mins (`ProteinTranslocation.yaml:79-81`). | `calcResourceRequirements_Current` applies `min(translocases, demand)` for ATP and `min(SRPs, srp-demand)` for GTP before hydrolysis sum (`ProteinTranslocation.m:284-301`). | OC request calculator computes queued needs then applies pool-floor transform (`karr_request_calculators.py:734-753`). | ROW_WRONG | MATLAB-side row formula is semantically incomplete (capacity clipping missing). |
| PT-S4-03 | S4 | Row states OC request uses `max(need, current_pool)` and can over-request vs pure need (`ProteinTranslocation.yaml:80-81`, `:322`). | MATLAB current requirements do not apply a current-pool floor (`ProteinTranslocation.m:288-301`). | OC request calculator applies `max(need, substrate_state)` for ATP/GTP/H2O (`karr_request_calculators.py:742-753`). | CODE_DEVIATES | Row correctly captures MATLAB-vs-OC request-floor divergence. |
| PT-S5-01 | S5 | Row routes ATP/GTP/H2O consume and ADP/GDP/PI/H produce to cytosol tuples, mismatch=false (`ProteinTranslocation.yaml:191-226`). | Process substrate representation is single-compartment for this process and updates same substrate indices (`ProteinTranslocation.m:80-82`, `:362-368`). | OC writes flat shared-pool substrate deltas on `substrates` and is wired to shared substrate store (`karr_protein_translocation.py:432-442`; `karr_composite.py:855-860`, `:886-889`). | VERIFIED | Projection/merge exists, but no substrate tuple mismatch observed for this process. |
| PT-S5-02 | S5 | Row lists terminal-organelle handling deviation: OC excludes `MG_191/MG_192` instead of Karr remap (`ProteinTranslocation.yaml:324`). | MATLAB remaps terminal-organelle compartments to cytosol/membrane before translocating-set derivation (`ProteinTranslocation.m:199-203`). | OC excludes those two monomers during fixture load (`karr_protein_translocation.py:25`, `:195-196`). | CODE_DEVIATES | Row accurately documents a compartment-routing-related implementation deviation. |
| PT-S6-01 | S6 | Row allocator mode says Karr=`allocation`, OC=`allocation` (`ProteinTranslocation.yaml:75-77`). | Simulation computes per-process requirements and fair-share allocations, then injects allocation into `mod.substrates` before process `evolveState` (`@Simulation/evolveState.m:24-37`, `:63-70`). | OC wires `RequestCalculatorPTransloc` + `KarrAllocationStep` and process reads only `substrates_allocated[self.name]` (`karr_composite.py:789-791`, `:881-889`, `:941-948`; `karr_request_calculators.py:710-754`; `karr_protein_translocation.py:314-355`). | VERIFIED | Allocator engagement mode matches (request/grant-mediated execution). |
| PT-S6-02 | S6 | Row notes OC request path is separate calculator step and no ProteinTranslocation-specific scheduler exception (`ProteinTranslocation.yaml:32-34`, `:253`). | MATLAB process order is randomized with only tRNA-before-translation hard rule; no ProteinTranslocation exception (`@Simulation/evolveState.m:48-57`). | OC flow enforces request-calculator-to-allocation ordering for ptransloc request path, with no explicit ptransloc-specific ordering edge beyond allocator coupling (`karr_composite.py:935-949`, `:1541-1562`). | VERIFIED | `judgment=required` (engine-level process-order semantics are implicit outside this file set). |

## Aggregate Counts
- VERIFIED: 6
- ROW_WRONG: 2
- CODE_DEVIATES: 2
- MISSING: 0

## Priority-1 Fixes
- PT-S4-01 (`ROW_WRONG`): update row `methods.evolveState`/`known_deviations` text to reflect current OC copy-level randperm + rate-scaled capacity behavior.
- PT-S4-02 (`ROW_WRONG`): correct `allocator.request_formula.matlab` to include capacity min terms (`min(translocases, ...)`, `min(SRPs, ...)`) from `calcResourceRequirements_Current`.

## Known-Deviation Mapping (Optional)
- KD-PT-01: request-floor divergence (`PT-S4-03`).
- KD-PT-02: terminal-organelle exclusion/remap divergence (`PT-S5-02`).

## Auditor Discretion List
- PT-S2-01 (`judgment=required`)
- PT-S3-01 (`judgment=required`)
- PT-S6-02 (`judgment=required`)

## Risks
- R1: Row still carries stale OC divergence text from a prior implementation phase; future auditors could over-attribute drift unless row is remediated.
- R2: S6 ordering parity depends on Vivarium runtime scheduling semantics not fully encoded in `karr_composite.py`; claim PT-S6-02 is evidence-backed but marked discretionary.
