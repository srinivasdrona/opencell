# RNAProcessing Semantic Audit (L1b)

## Header
- Process name: `RNAProcessing` (`rna_processing`)
- Audited files:
  - `data/schemas/per_process_wiring/RNAProcessing.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNAProcessing.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_rna_processing.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_composite.py`
  - `opencell/vivarium/karr_allocation_step.py`
- Scope policy: `exemplar-scoped completeness` for row stoichiometry claims (row explicitly states wiring-semantics scope, not full stoichiometry table: `RNAProcessing.yaml:13-15`).
- Header note: full audit (not `PARTIAL`)

## Deliberate Action Prefix (v2)
- Beat 1 (contract): classify RNAProcessing S1-S6 claims against executable MATLAB and OC behavior using only `VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`.
- Beat 2 (surface): row (`RNAProcessing.yaml`), MATLAB (`RNAProcessing.m`, `@Simulation/evolveState.m`), OC (`karr_rna_processing.py`, `karr_request_calculators.py`, `karr_composite.py`, `karr_allocation_step.py`). Suspect pattern: row prose says "preserves count-space update" while OC has replay-specific gating branches.
- Beat 3 (expected outcome): deterministic claim table with required columns, constrained verdict vocabulary, aggregate counts, and Priority-1 fixes.
- Beat 4 (invert / pre-mortem): false-pass risk is validating anchor presence and high-level notes while missing branch-level divergences (extra OC gates) or allocator timing semantics.
- Beat 5 (act then verify): each claim below cites concrete formulas/branches/routes rather than commentary-only text.
- PM sanity-check sentence: **PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.**

## Revision-Class Minimum
Design contract sentence:
- Semantic truth checked: RNAProcessing row consume/produce/formula/compartment/allocator claims must match MATLAB and OC execution semantics claim-by-claim.

Decision ledger (non-obvious attribution calls):
1. D1 (completeness policy)
- Chosen: exemplar-scoped completeness for substrate stoichiometry claims.
- Why: row explicitly states wiring semantics only (not full stoich table).
2. D2 (formula-drift attribution)
- Chosen: classify undocumented OC gating (`suppress_trna_for_rrna_tick`, first-maturation lag) as `ROW_WRONG`.
- Why: row claims preservation of count-space update but does not disclose these non-MATLAB gates.
3. D3 (allocator timing claim)
- Chosen: classify allocator-coupled timing specificity gap as `MISSING` with `judgment=required`.
- Why: MATLAB has explicit same-tick request/allocate/evolve ordering; row does not make an explicit equivalent timing claim for OC.

Risks (unresolved ambiguity):
- R1: Vivarium process-vs-step scheduling details can affect strict same-tick interpretation of allocation consumption.
- R2: Compartment-index `1` interpreted as cytosol relies on fixture convention; MATLAB process code itself does not spell that mapping literally.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| RNAPROC-S1-01 | S1 | Consume set is `ATP`, `GTP`, `H2O` (`RNAProcessing.yaml:150-186`). | Reactant/byproduct matrix consume rows are ATP/GTP/H2O (`RNAProcessing.m:316-327`) and applied in substrate update (`RNAProcessing.m:469-470`). | OC consume set comes from negative stoich rows (`karr_composite.py:1065-1068`) used for allocation enrollment (`karr_composite.py:1117`). | VERIFIED | Row consume completeness holds under declared exemplar scope. |
| RNAPROC-S2-01 | S2 | Each consume entry maps to OC substrate-delta path (`RNAProcessing.yaml:158-185`). | MATLAB writes substrate deltas by matrix-vector multiply (`RNAProcessing.m:469-470`). | OC computes `substrate_delta = reaction_stoich @ processing_events` then updates `substrates` (`karr_rna_processing.py:284-305`). | VERIFIED | No fabricated consume entries detected. |
| RNAPROC-S3-01 | S3 | Produce set is `ADP`, `GDP`, `PI`, `H` (`RNAProcessing.yaml:187-235`). | Positive byproduct rows are ADP/GDP/PI/H (`RNAProcessing.m:316-327`) and emitted in substrate update (`RNAProcessing.m:469-470`). | OC emits positive stoich rows through same `reaction_stoich @ processing_events` update (`karr_rna_processing.py:284-305`). | VERIFIED | Substrate-produce completeness/fabrication match for row-scoped set. |
| RNAPROC-S3-02 | S3 | Row explicitly records OC omission of MATLAB `intergenicRNAs` output (`RNAProcessing.yaml:402`). | MATLAB increments `intergenicRNAs` and writes it back to state (`RNAProcessing.m:460-462,367`). | OC update only writes `substrates` and `rna.counts`; no `intergenicRNAs` store/output path (`karr_rna_processing.py:298-308`, `karr_rna_processing.py:182-234`). | CODE_DEVIATES | Row correctly describes MATLAB-vs-OC produce-path divergence. |
| RNAPROC-S4-01 | S4 | Row says OC request formula is availability-based and not a literal MATLAB clone (`RNAProcessing.yaml:124-135`). | MATLAB request formula is enzyme/unprocessed capped matrix expression (`RNAProcessing.m:406-409`). | OC request uses `_request_from_available(...)` on consumed WIDs when active (`karr_request_calculators.py:335-353`, helper `21-30`). | CODE_DEVIATES | Row accurately captures formula-family divergence for requests. |
| RNAPROC-S4-02 | S4 | Row says OC preserves count-space reaction-cap/sampling update path (`RNAProcessing.yaml:76-79,278-282`). | MATLAB cap/sampling kernel: substrate ratio + stochastic enzyme limit + `randCounts` (`RNAProcessing.m:443-448,454`) then stoich writeback (`469-470`). | OC kernel mirrors this family: substrate limits, stochastic enzyme limits, `rand_counts`, then stoich writeback (`karr_rna_processing.py:379-420`). | VERIFIED | Core formula family matches modulo syntax/order. `judgment=required`. |
| RNAPROC-S4-03 | S4 | Row lists simplifications (allocated input, intergenic omission, etc.) but otherwise frames preserved evolve semantics (`RNAProcessing.yaml:76-81,400-404`). | MATLAB has no explicit `tRNA` suppression gate or first-activation lag branch in evolve helpers (`RNAProcessing.m:413-471`). | OC adds `suppress_trna_for_rrna_tick` (`karr_rna_processing.py:359-370`) and `_apply_identity_activation_lag` (`karr_rna_processing.py:423-438`). | ROW_WRONG | Row under-specifies material OC formula/gating drift. `judgment=required`. |
| RNAPROC-S5-01 | S5 | Row routes listed substrates as cytosol and says no projection merge (`RNAProcessing.yaml:236-271,398`). | MATLAB uses compartment-indexed substrate writeback (`@Simulation/evolveState.m:63-73`); process RNA state is cytosol-indexed (`RNAProcessing.m:356-358,365-367`). | OC substrate routing is flat WID-only (`karr_rna_processing.py:182-187,299-305`); fixture probe shows all RNAProcessing substrate compartment indices are `1` (`bin\\oc-py .tmp_rna_probe2.py`). | VERIFIED | For this process, projection appears identity on a single compartment. `judgment=required`. |
| RNAPROC-S5-02 | S5 | Row declares OC omits intergenic RNA routing (`RNAProcessing.yaml:402`). | MATLAB routes `intergenicRNAs` through cytosol RNA state (`RNAProcessing.m:358,367,460-462`). | OC has no intergenic routing surface in schema/update (`karr_rna_processing.py:182-234,298-308`). | CODE_DEVIATES | Row accurately captures routing mismatch. |
| RNAPROC-S6-01 | S6 | Row says both sides are allocation-backed; OC consumes `substrates_allocated[self.name]`; no bypasses (`RNAProcessing.yaml:117-123,149`). | MATLAB tick ordering computes requests, fair-share allocations, then runs process with allocated substrates (`@Simulation/evolveState.m:24-37,63-70`). | OC wires RNA request calculator + allocation step + allocated read path (`karr_composite.py:1138-1142,1551-1557`; `karr_allocation_step.py:184-207,213-280`; `karr_rna_processing.py:248-252`). | VERIFIED | Allocator engagement mode matches request/grant semantics. |
| RNAPROC-S6-02 | S6 | Row has no explicit allocator-coupled timing equivalence claim (ordering section is empty for hard/soft constraints: `RNAProcessing.yaml:296-304`). | MATLAB explicitly performs same-tick `calcResourceRequirements_Current -> allocation -> evolveState` (`@Simulation/evolveState.m:24-37,60-73`). | OC exposes request-calculator flow dependencies into allocation step (`karr_composite.py:1545-1562`), but row does not state process-vs-allocation timing equivalence semantics. | MISSING | Add explicit allocator-timing claim for reproducibility. `judgment=required`. |

Aggregate counts:
- VERIFIED: 6
- ROW_WRONG: 1
- CODE_DEVIATES: 3
- MISSING: 1

Priority-1 fixes:
- `RNAPROC-S4-03` (`ROW_WRONG`): explicitly document OC-specific gating branches (`suppress_trna_for_rrna_tick`, first-maturation lag) or narrow the row's formula-equivalence language.
- `RNAPROC-S6-02` (`MISSING`): add allocator-coupled timing claim (same-tick vs staged grant usage) with explicit MATLAB/OC anchors.

Known-deviation mapping:
- KD1 (request formula divergence): `RNAPROC-S4-01`.
- KD2 (intergenic RNA omission/routing mismatch): `RNAPROC-S3-02`, `RNAPROC-S5-02`.

Auditor discretion list (`judgment=required`):
- `RNAPROC-S4-02`
- `RNAPROC-S4-03`
- `RNAPROC-S5-01`
- `RNAPROC-S6-02`

## Verification (Beat 5)
- Expected (Beat 3): one complete S1-S6 claim table with constrained verdict vocabulary and reproducible attributions.
- Actual: 11 claims spanning S1-S6 using only `VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`, with aggregate counts and Priority-1 fixes included.
- Beat-4 inversion check: avoided anchor-only pass by auditing branch-level request formulas, reaction-cap math, OC-specific gating branches, compartment projection behavior, and allocator ordering surfaces.
- Verdict: matched.
