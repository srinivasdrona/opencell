# FtsZPolymerization Semantic Audit

## INTENT
1. One-sentence summary: execute a semantic S1-S6 wiring audit for `FtsZPolymerization` against raw MATLAB + current OC code and classify each claim with the required verdict vocabulary.
2. Contract (Beat 1): row semantics must match executable MATLAB and OC behavior (not just anchor presence); done means claim-level verdict reproducibility from cited sources.
3. Expected observable change (Beat 3): this file contains a complete S1-S6 claim table with deterministic IDs, aggregate counts, and Priority-1 row-remediation items.
4. Inversion (Beat 4): this audit could look complete but be wrong if it trusts extract prose and misses raw MATLAB formulas / allocator overwrite semantics.
5. PM sanity-check sentence: PM: I am assuming row scope is strict completeness (not exemplar-only); if that is wrong, S1/S3 omission attributions would change.

## Header
- Process name: `FtsZPolymerization` (`fts_z_polymerization`)
- Audited files:
  - `data/schemas/per_process_wiring/FtsZPolymerization.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/FtsZPolymerization.m`
  - `docs/karr_extracts/process/25_FtsZPolymerization.md`
  - `docs/karr_extracts/architecture/01_simulation_loop.md`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_ftsz_polymerization.py`
  - `opencell/vivarium/karr_composite.py`
  - `opencell/vivarium/karr_allocation_step.py`
- Scope policy: `strict completeness` for S1/S3.
- Design contract sentence: Semantic truth being checked is whether row-described consume/produce formulas, routing, and allocator engagement match executable MATLAB behavior and current OC behavior for this process.

## Decision Ledger
- D1 (scope policy): Chose strict completeness (not exemplar scope) because row does not declare exemplar-only behavior. Alternative was exemplar-scoped completeness. Rationale: avoid silently waiving omissions.
- D2 (request formula attribution): Classified request-formula issue as `ROW_WRONG` (not `CODE_DEVIATES`) because row states MATLAB request body is unavailable even though raw MATLAB exposes an explicit formula.
- D3 (non-GTP allocator path): Classified non-GTP routing as `CODE_DEVIATES` because row explicitly marks GDP/PI/H2O/H as OC bypasses, while MATLAB allocation loop overwrites process-local substrate vector from grants.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| FTSZ-S1-01 | S1 | `consume_stoichiometry` includes GTP, GDP, H2O as consumed families (`FtsZPolymerization.yaml:104-137`). | `applySubstrateLimits` consumes GTP and GDP via `- nGTP*(enzymes-this.enzymes)` / `- nGDP*(...)`, and consumes H2O in hydrolysis compensation vector (`FtsZPolymerization.m:403-433`). | OC clamp path consumes same families (`karr_ftsz_polymerization.py:448-479`, `:573-585`). | VERIFIED | GDP is dual-role (consume + compensate-produce); classification is net-sign dependent; `judgment=required`. |
| FTSZ-S2-01 | S2 | Each row consume entry maps to OC clamp/delta anchors (`FtsZPolymerization.yaml:112-137`). | MATLAB consume families are executable in `applySubstrateLimits` (`FtsZPolymerization.m:403-433`). | OC has concrete consume paths: GTP/GDP decrements (`:472-473`), H2O decrement in shortfall branch (`:477`, `:584`). | VERIFIED | Consume fabrication confirmed for all row consume entries. |
| FTSZ-S3-01 | S3 | `produce_stoichiometry` includes GDP, PI, H from shortfall compensation (`FtsZPolymerization.yaml:138-171`). | MATLAB hydrolysis compensation adds `[1;-1;1;-1;1] * max(0,-GDP)` so GDP/PI/H are produced (`FtsZPolymerization.m:432-433`). | OC shortfall branch adds same positive products (`karr_ftsz_polymerization.py:475-477`, `:582-585`). | VERIFIED | GDP is also a consume family before compensation; dual-role is intentional; `judgment=required`. |
| FTSZ-S4-01 | S4 | Row describes ODE + discretize + clamp flow (`FtsZPolymerization.yaml:35-55`). | MATLAB ODE/Jacobian families in `diff` and `jacobian` match Karr process equations (`FtsZPolymerization.m:461-497`, `:512-545`). | OC `ode_diff` / `ode_jacobian` implements same term structure and indexing family (`karr_ftsz_polymerization.py:338-403`). | VERIFIED | Formula-family parity holds modulo syntax/solver implementation details. |
| FTSZ-S4-02 | S4 | Row says MATLAB request formula body is unavailable and only extract-level (`FtsZPolymerization.yaml:21`, `:78-81`). | MATLAB has explicit formula: `result(gtp)=FtsZ + FtsZ_GDP` (`FtsZPolymerization.m:189-193`). | OC request formula uses post-update `next_counts` (`karr_ftsz_polymerization.py:274-279`). | ROW_WRONG | Row attribution is false (raw formula exists) and does not explicitly capture current-vs-next request formula divergence. |
| FTSZ-S4-03 | S4 | Row claims OC divergence is mainly wiring-shape, not biochemistry (`FtsZPolymerization.yaml:304`). | MATLAB clamp loops run without explicit nonnegative guard checks in loop body (`FtsZPolymerization.m:407-423`). | OC adds defensive breaks (`if positive.size<=0` / `if FtsZ_GDP<=0: break`) in clamp loops (`karr_ftsz_polymerization.py:450-452`, `:466-467`). | ROW_WRONG | Defensive branches are semantic additions relative to MATLAB source; reachability impact is unresolved; `judgment=required`. |
| FTSZ-S5-01 | S5 | Row routes GTP/GDP/H2O/PI/H to cytosol tuples with `mismatch: false` (`FtsZPolymerization.yaml:172-197`). | Process is explicitly cytosolic and writes through substrate global-compartment indices (`FtsZPolymerization.m:6-8`; `evolveState.m:32-33`, `:63-73`). | OC uses same five WIDs in shared `substrates` store with FtsZ topology on `substrates` (`karr_ftsz_polymerization.py:192-194`; `karr_composite.py:2140-2144`). | VERIFIED | Tuple family matches at process surface; `judgment=required` because OC substrate store has no explicit compartment axis. |
| FTSZ-S5-02 | S5 | Row says `shared_pool_projection_merges_compartments: false` (`FtsZPolymerization.yaml:298`). | MATLAB runtime tracks compartmented metabolite indices (`evolveState.m:32-33`, `:63-73`). | OC chassis projects initial substrate pools from cytosol compartment 0 (`karr_composite.py:134-145`); FtsZ uses per-WID vector without in-process compartment merge (`karr_ftsz_polymerization.py:537-545`). | VERIFIED | For this process, projection is cytosol-only rather than cross-compartment merge; `judgment=required`. |
| FTSZ-S6-01 | S6 | Row says allocator mode is active and GTP request tuple participates (`FtsZPolymerization.yaml:73-86`). | MATLAB request + fair allocation loop: `calcResourceRequirements_Current` then global `allocations` applied before `evolveState` (`FtsZPolymerization.m:189-193`; `evolveState.m:31-37`, `:63-69`). | OC emits GTP request, allocation step includes FtsZ consumer `(ftsz_proc, [GTP])`, and process reads `substrates_allocated` for GTP (`karr_ftsz_polymerization.py:274-283`, `:530-545`; `karr_composite.py:1782`; `karr_allocation_step.py:210-280`). | VERIFIED | Allocator engagement for GTP is implemented on both sides. |
| FTSZ-S6-02 | S6 | Row marks GDP/PI/H2O/H as OC bypasses (`FtsZPolymerization.yaml:87-103`). | MATLAB loop overwrites process-local substrate vector from `allocation` each tick (`evolveState.m:63-69`), so non-requested metabolites are allocator-mediated by zero grant unless produced internally. | OC seeds clamp substrate vector from shared `substrates` for all WIDs, then overrides only GTP with allocated value (`karr_ftsz_polymerization.py:537-545`). | CODE_DEVIATES | Row correctly captures MATLAB-vs-OC divergence on non-GTP allocator bypass behavior; `judgment=required`. |
| FTSZ-S6-03 | S6 | Row says no FtsZ-specific ordering constraint (`FtsZPolymerization.yaml:221-226`). | MATLAB uses random process evaluation each tick with only tRNA-before-translation hard constraint (`evolveState.m:50-55`). | OC composite includes no FtsZ-specific flow edge; FtsZ only participates as allocation consumer + process topology entry (`karr_composite.py:1782`, `:2140-2144`). | VERIFIED | Allocator-coupled ordering claim checked at file-visible level; deeper engine-phase timing remains an external assumption; `judgment=required`. |

## Aggregate Counts
- VERIFIED: 8
- ROW_WRONG: 2
- CODE_DEVIATES: 1
- MISSING: 0

## Priority-1 Fixes
- `FTSZ-S4-02` (`ROW_WRONG`): replace row's "MATLAB request formula unavailable" statement with raw MATLAB formula and explicitly classify current-vs-next request formula mismatch.
- `FTSZ-S4-03` (`ROW_WRONG`): row should explicitly document OC clamp defensive-guard additions or justify parity if proven unreachable.

## Known-Deviation Mapping
- D-ALLOC-01 -> `FTSZ-S6-02`: OC bypasses allocator for GDP/PI/H2O/H while MATLAB is allocation-mediated for local substrate vector.

## Auditor Discretion (`judgment=required`)
- `FTSZ-S1-01`, `FTSZ-S3-01`, `FTSZ-S4-03`, `FTSZ-S5-01`, `FTSZ-S5-02`, `FTSZ-S6-02`, `FTSZ-S6-03`.

## Risks
- R1: Reachability of OC defensive clamp guards (`FTSZ-S4-03`) is unresolved without targeted runtime probes.
- R2: OC engine-phase timing (process vs step visibility in same tick) is not fully proven from these files alone; ordering verdicts are file-surface bounded.
- R3: Compartment semantics in OC are store-projected (cytosol snapshot) rather than explicit per-process compartment tensors; tuple equivalence assumes cytosol-only relevance for this process.

## VERIFICATION
- Beat 3 expected outcome: complete S1-S6 table with allowed verdicts + totals + Priority-1 list.
- Actual measured outcome: 11 deterministic claims across S1-S6, verdict vocabulary constrained, totals and Priority-1 list present.
- Evidence commands used: targeted `rg -n` and line-numbered source reads over row/MATLAB/OC/allocation/composite files.
- Beat 4 inversion checks:
  - Extract-only failure mode avoided by auditing raw MATLAB request/clamp formulas (`FtsZPolymerization.m:189-193`, `:403-433`).
  - Allocator-surface blind spot avoided by checking both simulation allocation overwrite (`evolveState.m:63-69`) and OC non-GTP shared-store path (`karr_ftsz_polymerization.py:537-545`).
- Verdict: matched.
