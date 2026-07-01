# ChromosomeSegregation Semantic Audit

## Header
- Process name: `ChromosomeSegregation` (`chromosome_segregation`)
- Audited files:
  - `data/schemas/per_process_wiring/ChromosomeSegregation.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeSegregation.m`
  - `docs/karr_extracts/process/08_ChromosomeSegregation.md`
  - `opencell/validation/swarm/l5/karr_zero_grant_behavior.md`
  - `docs/karr_extracts/architecture/01_simulation_loop.md`
  - `docs/design/pc-t5-segregation.md`
  - `opencell/vivarium/karr_chromosome_segregation.py`
  - `opencell/vivarium/karr_allocation_step.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: strict completeness (row does not declare exemplar-only scope).

## Deliberate Action Prefix v2
- Beat 1 (contract): classify S1-S6 row claims against MATLAB and OC executable behavior with only `VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`.
- Beat 2 (surface): row YAML, MATLAB process method bodies (`calcResourceRequirements_Current`, `evolveState`), OC process `next_update`, and allocator/scheduler wiring in simulation-loop/composite sources.
- Beat 3 (expected outcome): a deterministic claim table with stable claim IDs, aggregate verdict counts, and Priority-1 row fixes.
- Beat 4 (invert): most likely false pass is trusting extract prose and missing branch-level gates (especially request gating and enzyme gate membership) that differ between MATLAB and OC.
- Beat 5 (act/verify): every claim below cites concrete code-path statements (conditions, formulas, write targets), not only comments.

Design contract sentence: This audit is done only if an independent auditor can reproduce the same claim-level verdicts from the cited MATLAB and OC branches under the same strict scope policy.

## Decision Ledger (non-obvious attribution calls)
- D1
  - Question: Should completeness be strict or exemplar-scoped?
  - Decision: strict completeness.
  - Rationale: row does not declare exemplar scope; S1/S3 must therefore be exhaustive.
- D2
  - Question: How to label the request-gate mismatch where row says MATLAB includes `supercoiled` but code does not?
  - Decision: `ROW_WRONG`.
  - Rationale: row statement about MATLAB is factually false; precedence requires row fault over deviation labeling.
- D3
  - Question: How to label TopoIV gate attribution (`source: oc`) when MATLAB gate uses `all(this.enzymes)` including TopoIV?
  - Decision: `ROW_WRONG`.
  - Rationale: divergence exists, but row misattributes MATLAB side and cannot be credited as an accurate MATLAB-vs-OC divergence statement.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| CHRSEG-S1-01 | S1 | `consume_stoichiometry` lists only `GTP`, `H2O` (`.../ChromosomeSegregation.yaml:118-140`). | `evolveState` consumes only `GTP` and `H2O` (`.../ChromosomeSegregation.m:201-207`). | Only `GTP`/`H2O` are consumed in substrate update (`.../karr_chromosome_segregation.py:372-374`). | VERIFIED | Strict consume-set completeness holds. |
| CHRSEG-S2-01 | S2 | Each consume row entry points to OC consume anchor (`.../ChromosomeSegregation.yaml:126-140`). | Consume branch is gate-conditional (`.../ChromosomeSegregation.m:196-207`). | Real consume path exists: `next_update` emits negative deltas for `GTP`/`H2O` (`.../karr_chromosome_segregation.py:369-374`). | VERIFIED | Fabrication check passes (path exists and executes when branch opens). |
| CHRSEG-S3-01 | S3 | `produce_stoichiometry` lists `GDP`, `H`, `PI` (`.../ChromosomeSegregation.yaml:141-174`). | `evolveState` produces exactly `GDP`, `PI`, `H` (`.../ChromosomeSegregation.m:208-210`). | OC produces exactly `GDP`, `PI`, `H` (`.../karr_chromosome_segregation.py:375-377`). | VERIFIED | Produce completeness + fabrication both hold for listed products. |
| CHRSEG-S4-01 | S4 | Consume/produce formulas are `gtpCost * 1` when gate is open (`.../ChromosomeSegregation.yaml:121-167`). | On pass, MATLAB applies `-gtpCost` to `GTP/H2O` and `+gtpCost` to `GDP/PI/H` (`.../ChromosomeSegregation.m:206-210`). | OC applies identical stoichiometric vector with `self.gtp_cost` (`.../karr_chromosome_segregation.py:372-377`). | VERIFIED | `judgment=required`: OC adds `progress_delta > 0` guard, equivalent under default positive `segregation_rate_per_s` and `dt`. |
| CHRSEG-S4-02 | S4 | Request formula says MATLAB requests only when replicated + supercoiled + proteins + not segregated (`.../ChromosomeSegregation.yaml:85-87`). | `calcResourceRequirements_Current` gate does **not** include `supercoiled`; it checks `~segregated`, replication completion, and `all(this.enzymes)` (`.../ChromosomeSegregation.m:182-189`). | OC request path is gated by `_gates_satisfied`, which includes `supercoiled` by default (`.../karr_chromosome_segregation.py:287-299,348-365`). | ROW_WRONG | Row misstates MATLAB request formula and masks a MATLAB-vs-OC gate difference. |
| CHRSEG-S4-03 | S4 | Row notes OC is a continuous projection of MATLAB’s boolean state machine (`.../ChromosomeSegregation.yaml:59-61`). | MATLAB flips `c.segregated = true` in one successful event (`.../ChromosomeSegregation.m:204`). | OC advances `segregation_progress` continuously and latches completion at 1.0 (`.../karr_chromosome_segregation.py:370-400`). | CODE_DEVIATES | Row accurately describes this implementation deviation. |
| CHRSEG-S4-04 | S4 | Row says process has no `calcFluxBounds` / LP-bound path (`.../ChromosomeSegregation.yaml:62-78`). | No `calcFluxBounds` method exists in MATLAB process file (`.../ChromosomeSegregation.m`). | No flux-bound helper exists in OC process file (`.../karr_chromosome_segregation.py`). | VERIFIED | Bounds-transform family is absent on both sides. |
| CHRSEG-S5-01 | S5 | Routing table claims cytosolic tuples for `GTP/H2O/GDP/H/PI` with no mismatch (`.../ChromosomeSegregation.yaml:175-200`). | MATLAB substrate surface is the five-ID local substrate vector (`.../ChromosomeSegregation.m:99-105,206-210`). | OC writes same five WIDs on the `substrates` port (`.../karr_chromosome_segregation.py:223-226,372-377`). | VERIFIED | `judgment=required`: MATLAB file is compartment-implicit; tuple names align but explicit compartment labels are not printed in this file. |
| CHRSEG-S5-02 | S5 | Row says `shared_pool_projection_merges_compartments: false` (`.../ChromosomeSegregation.yaml:296`). | Simulation loop writes allocation-indexed deltas directly back (`counts + mod.substrates - allocation`) with no per-metabolite projection merge (`.../01_simulation_loop.md:187-197`). | OC process emits direct per-WID deltas and has no compartment projection operator (`.../karr_chromosome_segregation.py:401-412`). | VERIFIED | Explicit projection/merge behavior check: no merge path observed. |
| CHRSEG-S6-01 | S6 | Allocator mode is allocation on both sides; OC has no global-substrate fallback (`.../ChromosomeSegregation.yaml:80-84`). | MATLAB overwrites `mod.substrates` with allocated vector before `mod.evolveState()` (`.../01_simulation_loop.md:187-194`). | OC reads only `states['substrates_allocated'][self.name]`; helper returns clamped allocated value only (`.../karr_chromosome_segregation.py:269-275,355-357`). | VERIFIED | Allocator engagement mode matches strict grant gating. |
| CHRSEG-S6-02 | S6 | Row says OC request logic is inlined in process (no dedicated request-calculator class) (`.../ChromosomeSegregation.yaml:35-37`). | MATLAB uses dedicated `calcResourceRequirements_Current` for allocator demand (`.../ChromosomeSegregation.m:179-189`). | OC inlines request emission in `next_update` and consumes `substrates_allocated`; composite enrolls this process in allocator consumer vectors for `GTP/H2O` (`.../karr_chromosome_segregation.py:355-365,401-406`; `.../karr_composite.py:1778-1780`; `.../karr_allocation_step.py:254-255`). | VERIFIED | Engagement is present on both sides despite different request-implementation shape. |
| CHRSEG-S6-03 | S6 | Row marks `MG_203_204_TETRAMER` as `source: oc` optional gate (`.../ChromosomeSegregation.yaml:114-117,299`). | MATLAB enzyme list includes TopoIV and gate uses `all(this.enzymes)` (includes TopoIV) (`.../ChromosomeSegregation.m:107-113,185,200`). | OC default required gate excludes TopoIV unless `include_topoiv_gate=True` (`.../karr_chromosome_segregation.py:121-124,157-162`). | ROW_WRONG | Row misattributes TopoIV participation to OC-only; real divergence is MATLAB-required vs OC-optional default. |
| CHRSEG-S6-04 | S6 | Row says no process-specific ordering constraint for this process (`.../ChromosomeSegregation.yaml:222-227`). | MATLAB uses random process order with only global tRNA<translation constraint (`.../01_simulation_loop.md:172-181`). | OC flow constrains request-calculator steps then allocation step, but no explicit per-process dependency edge for chromosome segregation is declared in composite flow (`.../karr_composite.py:2334-2358`). | VERIFIED | `judgment=required`: exact process-vs-step phase ordering in Vivarium engine is not proven from these files alone. |

## Aggregate Counts
- VERIFIED: 10
- ROW_WRONG: 2
- CODE_DEVIATES: 1
- MISSING: 0

## Priority-1 Fixes
- `CHRSEG-S4-02`: fix `allocator.request_formula.matlab` to remove the unsupported `supercoiled` gate term (or explicitly split MATLAB-vs-OC formulas).
- `CHRSEG-S6-03`: fix TopoIV attribution (`MG_203_204_TETRAMER`) so MATLAB participation is represented correctly and OC default optionality is described as a deviation, not OC-only origin.

## Known-Deviation Mapping (optional)
- KD-1 -> `CHRSEG-S4-03`: boolean MATLAB segregation event vs continuous OC progress/latch.
- KD-2 -> `CHRSEG-S6-03`: MATLAB TopoIV-required gate vs OC default TopoIV-optional gate.

## Auditor Discretion List
- `CHRSEG-S4-01` (`judgment=required`)
- `CHRSEG-S5-01` (`judgment=required`)
- `CHRSEG-S6-04` (`judgment=required`)

## Risks (unresolved ambiguity)
- R1: MATLAB compartment labels are implicit in process-local substrate vectors; cytosol labeling in row is plausible but not explicitly printed in the process file.
- R2: OC process-vs-step execution phase ordering is not fully evidenced here; allocator-to-process tick timing should be confirmed against engine scheduling semantics if same-tick parity is required.
- R3: OC parameter overrides (`require_supercoiled`, `include_topoiv_gate`, `segregation_rate_per_s`) can change formula equivalence relative to MATLAB defaults; row should state default-assumption scope explicitly.
