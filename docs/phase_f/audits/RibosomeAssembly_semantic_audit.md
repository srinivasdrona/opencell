# RibosomeAssembly Semantic Wiring Audit

## Header
- Process: `RibosomeAssembly` (`ribosome_assembly`)
- Audited files:
  - `data/schemas/per_process_wiring/RibosomeAssembly.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RibosomeAssembly.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_ribosome_assembly.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_composite.py`
  - `opencell/vivarium/karr_allocation_step.py`
- Scope policy: **strict completeness** (row consume/produce lists treated as exhaustive because the row does not explicitly declare exemplar scope)

## Deliberate Action Prefix (v2)
- Beat 1 (Contract): Validate whether row semantic statements for S1-S6 are true against executable MATLAB and OC behavior.
- Beat 2 (Surface): Read row YAML claims, MATLAB `calcResourceRequirements_Current`/`evolveState` + simulation allocator flow, OC request calculator/process/allocation/composite flow wiring.
- Beat 3 (Expected outcome): Deterministic claim table with allowed verdict vocabulary and reproducible totals.
- Beat 4 (Invert): Worst failure mode is falsely marking completeness as valid by treating exemplar row entries as exhaustive without checking composition-matrix-driven species expansion.
- Beat 5 (Act then verify): Claims below cite concrete branches/formulas/routes; verification summary and evidence check are included after the table.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Design Contract (Revision-Class Minimum)
Contract sentence: The audit is correct iff an independent reader can reproduce each S1-S6 verdict directly from the same row + MATLAB + OC code paths without hidden assumptions.

## Decision Ledger
- D1: Scope attribution for completeness.
  - Decision: Use strict completeness.
  - Why: Row does not declare non-exhaustive exemplar policy.
- D2: Request-formula attribution where MATLAB and OC differ.
  - Decision: `CODE_DEVIATES` when row explicitly captures MATLAB-vs-OC non-equivalence.
  - Why: Row includes distinct MATLAB/OC formulas and deviation note for hardcoded MATLAB coefficient.
- D3: Production/consumption baseline method.
  - Decision: Evaluate per-tick `evolveState` semantics for S1-S5, with allocator engagement from simulation/composite scheduling for S6.
  - Why: This is the executable consume/produce path tied to allocation.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| RIBASM-S1-01 | S1 | `consume_stoichiometry` lists 5 consume entries (GTP, H2O, MGrrnA16S, MGrrnA23S, MG_417_MONOMER) with no exemplar-scope declaration (`RibosomeAssembly.yaml`). | `evolveState` consumes GTP/H2O plus all positive RNA and monomer composition rows per particle (`RibosomeAssembly.m:323-338`, `:326-336`). | `_build_update` decrements every positive-coefficient RNA/monomer entry (`karr_ribosome_assembly.py:300-308`, `:374-381`); fixture probe shows active consume set includes 3 rRNAs (`MGrrnA16S`,`MGrrnA23S`,`MGrrnA5S`) and 52 monomers (via `bin\\oc-py tmp_ribasm_probe.py`). | MISSING | Row omits at least `MGrrnA5S` and 51 consumed monomers under strict scope. |
| RIBASM-S2-01 | S2 | Each listed consume entry has OC consume anchors (`RibosomeAssembly.yaml` consume entries). | Listed entries are consumed in `evolveState` update loop and substrate vector update (`RibosomeAssembly.m:323-338`). | GTP/H2O decremented from allocated pool (`karr_ribosome_assembly.py:371-372`); RNA/monomer listed entries are decremented in composition loops (`:374-381`). | VERIFIED | Fabrication check passes for all row-listed consume entries. |
| RIBASM-S3-01 | S3 | `produce_stoichiometry` lists GDP, PI, H, RIBOSOME_30S, RIBOSOME_50S (`RibosomeAssembly.yaml`). | `evolveState` produces complexes and hydrolysis byproducts via `[-1;1;1;-1;1] * newComplexs * gtpPerComplex` plus complex increments (`RibosomeAssembly.m:333`, `:338`). | `_build_update` emits GDP/PI/H and positive complex deltas (`karr_ribosome_assembly.py:310-319`, `:330-331`). | VERIFIED | Produce completeness for per-tick assembly path is complete. |
| RIBASM-S3-02 | S3 | Each row produce entry has an OC produce path (`RibosomeAssembly.yaml` produce anchors). | Production occurs when `newComplexs > 0` (`RibosomeAssembly.m:328-338`). | Production emitted when `total_gtp_hydrolyzed > 0` and `n_formed > 0` (`karr_ribosome_assembly.py:312-331`). | VERIFIED | Produce fabrication check passes. |
| RIBASM-S4-01 | S4 | Consume/produce formulas are `±n_form * n_gtpases_per_particle[particle]` and composition-scaled RNA/monomer deltas (`RibosomeAssembly.yaml`). | Core update computes `newComplexs = floor(min(GTP/gtpPerComplex, H2O/gtpPerComplex, RNA limits, monomer limits))` then applies composition and hydrolysis updates (`RibosomeAssembly.m:323-338`). | Core update computes `n_form = min(rna_limit, monomer_limit, floor(gtp_alloc/gpp), floor(h2o_alloc/gpp))` then applies same composition and hydrolysis multipliers (`karr_ribosome_assembly.py:363-381`, `:313-319`). | VERIFIED | Core per-particle hydrolysis/limit algebra matches modulo syntax/implementation structure. |
| RIBASM-S4-02 | S4 | Row `allocator.request_formula` explicitly encodes distinct MATLAB and OC formulas, and `known_deviations` notes MATLAB hardcoded `getGtpPerComplex(2)` usage (`RibosomeAssembly.yaml`). | Request uses `getGtpPerComplex(2)` in both 30S and 50S terms with `1 + min(...)` form (`RibosomeAssembly.m:289-295`). | Request uses `sum(formable_particle * n_gtpases_per_particle)` with particle-specific coefficients and no `+1` term (`karr_request_calculators.py:212-218`). | CODE_DEVIATES | Row correctly records a real formula divergence between MATLAB and OC request semantics. |
| RIBASM-S4-03 | S4 | `known_deviations` says OC early-returns when GTP or H2O allocation is non-positive, whereas MATLAB only checks GTP (`RibosomeAssembly.yaml`). | Early return guard checks only GTP (`RibosomeAssembly.m:303-305`). | Early return guard checks `gtp_alloc <= 0.0 or h2o_alloc <= 0.0` (`karr_ribosome_assembly.py:340-341`). | CODE_DEVIATES | Row correctly describes this branch-level divergence. |
| RIBASM-S5-01 | S5 | `compartment_routing` marks all listed consume/produce tuples as cytosolic and mismatch=false (`RibosomeAssembly.yaml`). | RNA/monomer compositions are explicitly cytosol-sliced (`RibosomeAssembly.m:163`, `:177`); substrate writeback uses process global-compartment indices (`@Simulation/evolveState.m:63-73`). | OC writes direct single-store deltas by WID in `substrates`, `rna.counts`, `protein.counts`, `complex.counts` (`karr_ribosome_assembly.py:149-187`, `:323-331`). | VERIFIED | `judgment=required` (MATLAB substrate-compartment mapping is inferred through base process indexing, not explicitly named in this class). |
| RIBASM-S5-02 | S5 | `deviations.shared_pool_projection_merges_compartments: false` (`RibosomeAssembly.yaml`). | No projection/merge operator inside `RibosomeAssembly.evolveState`; direct vector updates only (`RibosomeAssembly.m:333-338`). | No compartment-axis reduction/merge operation in process update; direct key-based deltas (`karr_ribosome_assembly.py:312-331`). | VERIFIED | `judgment=required` (absence-of-merge conclusion is local to audited files). |
| RIBASM-S6-01 | S6 | `allocator.mode`: Karr allocation, OC allocation (`RibosomeAssembly.yaml`). | Allocator cycle is `calcResourceRequirements_Current -> fair-share allocation -> process consume allocation` (`@Simulation/evolveState.m:24-37`, `:63-70`). | `RequestCalculatorRibAsm` emits requests (`karr_request_calculators.py:210-226`), `KarrAllocationStep` proportionally floors grants (`karr_allocation_step.py:245-255`), process consumes `substrates_allocated` (`karr_ribosome_assembly.py:336-341`). | VERIFIED | Allocator engagement mode matches (request/grant, not bypass). |
| RIBASM-S6-02 | S6 | Row notes request generation is split into dedicated OC step; no process-specific hard ordering constraints (`RibosomeAssembly.yaml`). | MATLAB computes all requests before allocations, then each process runs using its allocated pool (`@Simulation/evolveState.m:24-37`, `:59-73`). | Composite flow requires `karr_allocation_step` after `request_calculator_ribasm` (`karr_composite.py:1543-1555` / `:2345-2349`); ribosome process reads shared `substrates_allocated` (`karr_composite.py:1334-1340`). | VERIFIED | `judgment=required` (global process-order randomness differs by runtime, but allocator-coupled request→grant ordering for this process is explicit). |
| RIBASM-S6-03 | S6 | `bypasses` include catalytic enzyme presence checks as direct (non-allocator-mediated) gates (`RibosomeAssembly.yaml`). | Catalysis gate is direct enzyme-presence check `~all(this.enzymes(...))` (`RibosomeAssembly.m:328-330`). | `_particle_resource_limits` applies direct `gtpase_pool >= 1` gate (`karr_ribosome_assembly.py:264-270`) used by both request estimate and update loop (`:280-287`, `:351-358`). | VERIFIED | Enzyme gating bypass parity holds. |

## Aggregate Counts
- VERIFIED: 9
- ROW_WRONG: 0
- CODE_DEVIATES: 2
- MISSING: 1

## Priority-1 Fixes
- `RIBASM-S1-01` (`MISSING`): expand `consume_stoichiometry` to include the full MATLAB/OC consumed set (missing at least `MGrrnA5S` and 51 monomer WIDs under strict scope).

## Known-Deviation Mapping
- KD1 (MATLAB request hardcodes `getGtpPerComplex(2)` vs OC per-particle coefficients): `RIBASM-S4-02`
- KD2 (OC stricter early-return guard on H2O allocation): `RIBASM-S4-03`

## Auditor Discretion (`judgment=required`)
- `RIBASM-S5-01`
- `RIBASM-S5-02`
- `RIBASM-S6-02`

## Risks (Revision-Class Minimum)
- Scope-policy sensitivity: if operator later declares exemplar-scope for consume/produce lists, completeness attribution for `RIBASM-S1-01` would change.
- Compartment inference risk: MATLAB substrate compartment for GTP/H2O/GDP/PI/H is inferred from simulation indexing flow, not explicitly re-declared in `RibosomeAssembly.m`.
- Runtime-order risk: allocator-coupled ordering is explicit, but full cross-process execution-order parity vs MATLAB randomized process loop is not fully proven in this audit.

## Beat 5 Verification Summary
- Expected outcome met: claim table covers S1-S6 with allowed verdict vocabulary and aggregate totals.
- Evidence check against Beat-4 inversion: consume completeness was validated via composition-matrix-driven species expansion (including fixture probe), not by row anchors alone.
- Verification verdict: matched.
