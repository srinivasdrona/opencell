# ProteinFolding Semantic Audit

## Header
Process name: `ProteinFolding` (`protein_folding`)

Audited files:
- `data/schemas/per_process_wiring/ProteinFolding.yaml`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinFolding.m`
- `docs/karr_extracts/process/19_ProteinFolding.md`
- `docs/phase_e/L2_STATUS.md`
- `docs/phase_f/L2_2_STOCHASTIC_AUDIT.md`
- `docs/design/pb_final_chassis_v4_integration.md`
- `opencell/vivarium/karr_protein_folding.py`
- `opencell/vivarium/karr_request_calculators.py`
- `opencell/vivarium/karr_allocation_step.py` (allocator engagement evidence)
- `opencell/vivarium/karr_composite.py` (allocator-coupled flow evidence)

Scope policy: `strict completeness` (row does not declare exemplar/non-exhaustive consume or produce scope).

## Slot 1 — DELIBERATE_ACTION_PREFIX_v2
Beat 1 (contract):
- Required behavior: classify semantic row claims against MATLAB and OC runtime behavior for S1-S6.
- Done means: each claim has reproducible evidence-backed verdict attribution (`VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`), not just anchor presence.

Beat 2 (surface):
- Row surface: `data/schemas/per_process_wiring/ProteinFolding.yaml`.
- MATLAB surface: `ProteinFolding.m` (`calcResourceRequirements_Current`, `evolveState`, `copyFromState`, `copyToState`).
- OC surface: `karr_protein_folding.py`, `karr_request_calculators.py`, allocator wiring in `karr_allocation_step.py` and `karr_composite.py`.
- Suspect patterns called out before verdicting: stale row provenance claiming missing MATLAB body, ATP-gating prose that may not match executed branches, and shared request-calculator whitelisting that can hide consume-path reachability.

Beat 3 (expected observable):
- Observable: a claim table with deterministic IDs and S1-S6 coverage, aggregate verdict counts, and Priority-1 row remediation items.

Beat 4 (invert / pre-mortem):
- Most likely false-pass mode: treating doc extracts as semantic truth while skipping executable MATLAB branches now present in `ProteinFolding.m`, which would incorrectly preserve ATP-centric row claims.

Beat 5 (act then verify):
- Verification used executable logic and branch math from MATLAB/OC methods, plus one fixture probe via `bin\\oc-py` to avoid guessing active prosthetic-ion columns.

PM sanity-check sentence:
- PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Slot 2 — Revision-Class Minimum
Design contract sentence:
- Semantic truth being checked: row claims for `ProteinFolding` must faithfully represent MATLAB substrate/protein folding semantics and current OC request/consume/routing/allocator behavior at claim granularity.

Decision ledger (non-obvious attribution calls):
- D1: `strict completeness` chosen because row has concrete consume entries and no non-exhaustive declaration.
- D2: ATP consume mismatch attributed as `ROW_WRONG` (not `CODE_DEVIATES`) because row states ATP as MATLAB consume semantics, but MATLAB executed substrate update is prosthetic-matrix-only.
- D3: Missing MN/NA row consume claims attributed as `MISSING` based on matrix-driven consume semantics and current fixture nonzero prosthetic columns; flagged with `judgment=required` because KB-driven columns are data-dependent.
- D4: Complex-channel omission attributed as `CODE_DEVIATES` because row explicitly records MATLAB-vs-OC surface divergence.

Risks (unresolved ambiguity):
- R1: MATLAB consume column activity is KB/fixture dependent; FE3 is listed in prose but not nonzero in the current fixture probe.
- R2: OC allocator-coupled timing is composition-dependent; this audit used chassis flow evidence but did not execute a full scheduler trace.
- R3: ATP-gating intent in row/history may reflect prior patches; verdicts here are branch-semantic, not intent-semantic.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| PF-S1-01 | S1 | `consume_stoichiometry` enumerates `ATP, FE2, MG, ZN, K` as consume set (`ProteinFolding.yaml:110-166`). | Consume is matrix-driven (`proteinProstheticGroupMatrix`) and applied in `evolveState` substrate delta (`ProteinFolding.m:264-270, 570`); indices include `MN` and `NA` (`ProteinFolding.m:278-280`). | Fixture-backed prosthetic matrix used by OC has nonzero columns `FE2, K, MG, MN, NA, ZN` (`karr_protein_folding.py:120-150`; probe via `bin\\oc-py` on `ProteinFolding_flat.mat`). | MISSING | Row omits at least `MN` and `NA` relative to active matrix-driven consume surface; `judgment=required` (KB/fixture-dependent activity). |
| PF-S1-02 | S1 | ATP is asserted as a MATLAB consume entry (`ProteinFolding.yaml:111-121`). | Executed substrate update is prosthetic-matrix subtraction only (`ProteinFolding.m:570`); request formula is also prosthetic-matrix-only (`ProteinFolding.m:507-514`). | OC does include ATP consume in phase 2 (`karr_protein_folding.py:282-290, 474-477`). | ROW_WRONG | Row conflates OC ATP behavior with MATLAB consume semantics. |
| PF-S2-01 | S2 | FE2/MG/ZN/K entries claim OC consume paths (`ProteinFolding.yaml:122-166`). | MATLAB consumes prosthetic groups via matrix × flux (`ProteinFolding.m:570`). | `_phase1_ion_binding` decrements every required prosthetic index from `protein_prosthetic_matrix` and reports `ion_consumed` (`karr_protein_folding.py:400-423`). | VERIFIED | Real OC consume path exists for prosthetic-ion entries. |
| PF-S2-02 | S2 | ATP consume entry exists (`ProteinFolding.yaml:111-121`). | MATLAB has no explicit ATP consume term in `evolveState` (`ProteinFolding.m:533-570`). | OC ATP consume path exists: `atp_consumed` from `_phase2_chaperone_folding` then ATP subtraction in `next_update` (`karr_protein_folding.py:282-290, 474-477`). | VERIFIED | Fabrication check only: OC path exists even though MATLAB mismatch is handled in S1/S4. |
| PF-S3-01 | S3 | `produce_stoichiometry: []` (`ProteinFolding.yaml:166`). | No metabolite byproducts in lifecycle (`byProd=zeros`, `ProteinFolding.m:475-479`) and `evolveState` only decrements substrates (`ProteinFolding.m:570`). | OC writes negative substrate deltas and protein count shifts; no metabolite positive production path (`karr_protein_folding.py:288-316`). | VERIFIED | Substrate-produce side is empty on both MATLAB and OC. |
| PF-S4-01 | S4 | MATLAB request formula says unfolded-dependent ATP + prosthetic-ion request (`ProteinFolding.yaml:85`). | `calcResourceRequirements_Current` is `proteinProstheticGroupMatrix' * (...)` with enzyme gate, no ATP additive term (`ProteinFolding.m:507-514`). | OC `pf_req` whitelists ATP/FE2/MG/ZN when `pf_active` (`karr_request_calculators.py:490-534`). | ROW_WRONG | MATLAB-side formula in row is incorrect. |
| PF-S4-02 | S4 | ATP-gated folding + ATP consume formula `min(available_ATP, 4 * n_events)` (`ProteinFolding.yaml:42, 113`). | `evolveState` uses stochastic matrix-limited fold selection with no ATP state variable (`ProteinFolding.m:533-562, 570`). | ATP feasibility gate uses `atp_remaining < 0` (not `<= 0`), allowing zero-ATP chaperone-dependent feasibility; ATP decrement uses `min(atp_remaining, 4)` (`karr_protein_folding.py:453-456, 474-477`). | ROW_WRONG | Row formula family does not match MATLAB and overstates OC ATP gating. |
| PF-S5-01 | S5 | Consume routing marked cytosolic (`ProteinFolding.yaml:167-192`). | Prosthetic matrix is projected to cytosol index (`ProteinFolding.m:264`) and process runs in pseudo-compartment representation (`ProteinFolding.m:113-120`). | OC uses single substrate store (no explicit compartment axis) (`karr_protein_folding.py:187-190, 244-252`). | VERIFIED | Cytosol/pseudo-compartment projection is consistent at substrate consume boundary; `judgment=required` (projection semantics). |
| PF-S5-02 | S5 | Row explicitly notes OC omission of `unfoldedComplexs/foldedComplexs` surfaces (`ProteinFolding.yaml:61, 307`). | MATLAB reads/writes unfolded/folded complex channels with compartment-index mapping (`ProteinFolding.m:386-389, 421-424, 575-579`). | OC schema/update expose monomer unfolding/folding and enzyme pools but no unfolded/folded complex channels (`karr_protein_folding.py:184-220, 302-316`). | CODE_DEVIATES | Row accurately describes MATLAB-vs-OC routing deviation. |
| PF-S6-01 | S6 | Allocator mode is `allocation` on both sides; OC reads `substrates_allocated[self.name]` (`ProteinFolding.yaml:80-84`). | MATLAB allocation hook exists via `calcResourceRequirements_Current` (`ProteinFolding.m:507-514`). | OC request path emits `requests[self._pf_proc.name]` (`karr_request_calculators.py:521-547`), allocator computes grants into `substrates_allocated` (`karr_allocation_step.py:197-280`), process reads allocated pool (`karr_protein_folding.py:244-252`); flow wires request calculators before allocation step (`karr_composite.py:1546-1558`). | VERIFIED | Allocator engagement and grant-read path are implemented on OC side. |
| PF-S6-02 | S6 | Known deviation says OC request helper surfaces only ATP/FE2/MG/ZN while Karr prosthetic-ion surface is broader (`ProteinFolding.yaml:306`). | MATLAB request derives from prosthetic matrix surface; indices include K/MN/NA (`ProteinFolding.m:271-281, 507-514`). | OC request whitelist for ProteinFolding is exactly ATP/FE2/MG/ZN (`karr_request_calculators.py:526-529`). | CODE_DEVIATES | Row correctly records allocator request-surface divergence; `judgment=required` (FE3 mention is prose-level, fixture activity varies). |

## Aggregate Counts
VERIFIED: 5
ROW_WRONG: 3
CODE_DEVIATES: 2
MISSING: 1

## Priority-1 Fixes
- PF-S1-01 (`MISSING`): add missing consume claims for active prosthetic-ion surface (`MN`, `NA`) or explicitly declare exemplar scope.
- PF-S1-02 (`ROW_WRONG`): remove/qualify ATP as MATLAB consume claim.
- PF-S4-01 (`ROW_WRONG`): replace MATLAB request formula with actual prosthetic-matrix formula from `calcResourceRequirements_Current`.
- PF-S4-02 (`ROW_WRONG`): correct ATP-gating formula claim (or mark as OC-specific divergence rather than MATLAB truth).

## Known-Deviation Mapping (Optional)
- PF-A1 (request-surface narrowing): PF-S6-02.
- PF-A2 (complex-channel omission): PF-S5-02.
- PF-A3 (ATP semantics drift): PF-S1-02 and PF-S4-02.

## Auditor Discretion List
- PF-S1-01 (`judgment=required`): consume completeness inferred from matrix-driven semantics + current fixture activity.
- PF-S5-01 (`judgment=required`): compartment projection equivalence is pseudo-compartmental, not explicit per-compartment tuples in OC.
- PF-S6-02 (`judgment=required`): broader-ion prose includes FE3 while active fixture columns vary by KB content.
