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
| PT-S1-01 | S1 | `consume_stoichiometry` exhaustively lists ATP/GTP/H2O in cytosol with primary-source anchors. | `evolveState` computes and consumes ATP/GTP/H2O per selected copy (`ProteinTranslocation.m:334-368`). | `next_update` emits the same negative substrate deltas after successful authority-state transfers (`karr_protein_translocation.py:484-510`). | VERIFIED | Strict completeness satisfied for the consumed substrate set. |
| PT-S2-01 | S2 | Each consume entry maps to the executable OC write path. | ATP/H2O are consumed for every translocated copy and GTP only for SRP-path copies (`ProteinTranslocation.m:334-368`). | OC uses the same pathway-dependent costs and emits deltas only for resources actually spent (`karr_protein_translocation.py:421-510`). | VERIFIED | GTP is correctly conditional on the SRP pathway. |
| PT-S3-01 | S3 | `produce_stoichiometry` exhaustively lists ADP/GDP/PI/H in cytosol. | `evolveState` produces ADP/GDP/PI/H from the same hydrolysis ledger (`ProteinTranslocation.m:365-368`). | OC produces ADP/PI/H for ATP hydrolysis and GDP when GTP is spent (`karr_protein_translocation.py:493-510`). | VERIFIED | Product identities and magnitudes match. |
| PT-S4-01 | S4 | Row states one persistent one-based copy-level permutation, rate-scaled capacities, and break-on-first-infeasible-copy behavior. | Karr draws one `randperm` over pending copies and stops at the first resource or enzyme failure (`ProteinTranslocation.m:309-347`). | OC rejects non-`MatlabRandStream`, draws before feasibility checks, applies the same capacities, and breaks on the first infeasible copy (`karr_protein_translocation.py:347-457`). | VERIFIED | Fixture-order and three-call observable sequence were independently re-probed. |
| PT-S4-02 | S4 | Row request formula includes both capacity mins and `H2O = ATP + GTP`. | `calcResourceRequirements_Current` applies `min(translocases, demand)` and `min(SRPs, SRP demand)` (`ProteinTranslocation.m:281-301`). | `RequestCalculatorPTransloc.next_update` transcribes those terms over authoritative cytosolic processed-I counts (`karr_request_calculators.py:804-846`). | VERIFIED | Constructed cases independently matched `0/0/0`, `320/14/334`, `320/6/326`, and `0/14/14`. |
| PT-S4-03 | S4 | Row states that OC has no current-pool floor and requests only calculated need. | MATLAB does not floor current requirements against the substrate pool (`ProteinTranslocation.m:281-301`). | OC initializes all requests to zero, computes only pending-copy need, and never reads the substrate pool in `next_update` (`karr_request_calculators.py:804-846`). | VERIFIED | The former request-floor deviation is removed. |
| PT-S5-01 | S5 | Row routes ATP/GTP/H2O consumption and ADP/GDP/PI/H production to the cytosolic shared substrate pool. | ProteinTranslocation updates the same seven substrate indices (`ProteinTranslocation.m:362-368`). | OC emits the same seven flat shared-pool deltas and the composite wires them to `substrates` (`karr_protein_translocation.py:493-510`; `karr_composite.py:905-910`). | VERIFIED | No substrate-compartment mismatch exists for this process. |
| PT-S5-02 | S5 | Row states all 119 translocatable WIDs use authoritative processed-I compartment counts. | MATLAB remaps terminal-organelle compartments before deriving the translocating set and transfers every selected copy between compartment columns (`ProteinTranslocation.m:198-201,350-353`). | OC declares and reads every translocatable WID under `compartment_counts.processed_i`, then conservatively transfers `c -> e/m`; no `protein.location` or translocation queue branch remains (`karr_protein_translocation.py:282-340,363-482`). | VERIFIED | Fixture-derived union is 124 authority WIDs / 7,440 leaves; 119 participate in translocation. |
| PT-S6-01 | S6 | Row allocator mode says Karr=`allocation`, OC=`allocation`. | Simulation computes requirements, fair-share allocations, and injects grants before process evolution (`@Simulation/evolveState.m:24-37,63-70`). | OC wires `RequestCalculatorPTransloc` to `KarrAllocationStep`; the process reads only `substrates_allocated[self.name]` (`karr_composite.py:931-1005`; `karr_protein_translocation.py:358-359`). | VERIFIED | Same-tick Engine acceptance proves request, allocation, and evolution. |
| PT-S6-02 | S6 | Row records a separate OC request Step and no ProteinTranslocation-specific scheduler exception. | MATLAB randomizes process order except for the tRNA-before-translation rule (`@Simulation/evolveState.m:48-57`). | OC adds only the generic request-before-allocation dependency and the common post-allocation process phase (`karr_composite.py:998-1008,2503-2518`). | VERIFIED | No process-specific ordering claim remains. |

## Aggregate Counts
- VERIFIED: 10
- ROW_WRONG: 0
- CODE_DEVIATES: 0
- MISSING: 0

## Priority-1 Fixes
- None.

## Known-Deviation Mapping (Optional)
- None. The schema-required calcFluxBounds absence is shared by MATLAB and OC and is not a behavioral deviation.

## Auditor Discretion List
- PT-S2-01 (`judgment=required`)
- PT-S3-01 (`judgment=required`)
- PT-S6-02 (`judgment=required`)

## Risks
- R1: Future changes to the compartment authority, request calculator, or RNG seeding must stale this adjudication and the L2.2 evidence bundle.
- R2: L2.2 validates isolated process distributions; chassis allocation and same-tick integration remain independently guarded by C12 and L2.4.

## Current independent evidence acceptance - 2026-10-19

`PTRANS-COMPLETE-ATTESTATION` and `PTRANS-SAMPLE-ISOLATION` are independently
ACCEPTED at reviewed source `65df71c26553f42dd95759b948de42647987bf68`.
The producer/algorithm findings above remain resolved; they were not reopened.
Complete independent commands, numeric proof, source inventories, ownership
witnesses and preservation receipts are published under
`docs/phase_f/pre_l25/acceptance/ProteinTranslocation/`. `VERDICT.json` records
the separate finding verdicts; `controls_retry1.xml` records 27 PASS with no
failures, errors, skips or xfails.

The fresh full registered gate used 50 distinct seeds, 100 ticks, B1000 and
all 2,892 compartment positions. Independent Karr-null recalibration and
numeric re-scoring give PASS; primary monomer W1 is zero. This is not a claim
that saved full OC tensors exist or that the reviewer reran the full campaign.
There is no retained deterministic-convergence/H12 demotion in this packet.

All 64 consumed records, including all 50 seed files and all runtime/parameter
inputs, were independently rehashed against the actual loader descriptors and
accepted population. Constructor authority reads, 12 registered source hashes,
sidecar/sentinel bindings and all 5,000 allocator summaries are verified.
Strict and portable candidate audits both have integrity OK. The four
unchanged publication assertions were executed against the explicit new
candidate bundle, not the stale historical tracked publication.

Actual repeated/interleaved active Design-A samples have six distinct public
execution owners with matching initial per-sample streams and full-width
outputs, even with advanced metadata and poisoned after/hint inputs. No
execution reset or cache clearing hid reuse. The unchanged contiguous legacy
100-tick replay instead retains one owner and its persistent stream. Original
sources and prior outputs are unchanged. The eight published compact files
are byte-identical to the independently accepted candidate.
