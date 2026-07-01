# Translation Semantic Audit

## Header Block
- Process name: `Translation` (`translation`)
- Audited files:
  - `data/schemas/per_process_wiring/Translation.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Translation.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/Simulation.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+util/polymerize.m`
  - `opencell/vivarium/karr_translation_v3.py`
  - `opencell/vivarium/karr_translation.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_composite.py`
  - `opencell/m3/translation.py`
  - `opencell/m3/translation_v2.py`
  - `docs/prompts/SEMANTIC_AUDIT_TEMPLATE.md`
- Scope policy: strict completeness for MATLAB metabolite substrate consume/produce surfaces (`Translation.m` substrate vector and `this.substrates(...)` writes); row AA surrogate entries are audited as declared representative exemplars (`judgment=required` where used).
- Header note: `COMPLETE` (not `PARTIAL`)

## Deliberate Action Prefix (v2)
- Beat 1 (contract): verify whether Translation row claims are semantically true against MATLAB executed behavior and current OC behavior, and classify each claim with only `VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`. Done means another auditor can reproduce the same verdicts from cited branches/formulas.
- Beat 2 (surface): row surface is `Translation.yaml` sections `allocator`, `consume_stoichiometry`, `produce_stoichiometry`, `compartment_routing`, `ordering_constraints`, `deviations`; MATLAB surfaces are `calcResourceRequirements_Current`, `evolveState`, Simulation allocator/order path, and `polymerize`; OC surfaces are `RequestCalculatorTranslation`, `KarrTranslationV3Process.next_update`, `_compute_enzyme_transitions_from_biology`, and composite request/allocation wiring. Suspect patterns: row uses surrogate AA consume entries under `consume_stoichiometry`; OC GTP/H2O logic is a gating read, not a substrate decrement.
- Beat 3 (expected outcome): produce a deterministic S1-S6 claim table with allowed verdict vocabulary only, aggregate counts, and Priority-1 remediation list.
- Beat 4 (invert pre-mortem): most embarrassing false pass is treating anchor proximity as execution truth, especially counting OC GTP/H2O reads as consume writes and treating flat OC substrate pools as compartment-equal to MATLAB routed tuples.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.
- Beat 5 (act then verify): the table below cites executable lines for each claim, includes all S1-S6 categories, and records discretion with `judgment=required`.

## Revision-Class Minimum
- Design contract sentence: this audit checks semantic truth of Translation wiring claims, not anchor existence, by matching row statements to executed MATLAB and OC branches.

### Decision Ledger (non-obvious attribution calls)
- D1: Completeness scope boundary.
  - Choice: strict on MATLAB metabolite substrate vector; AA surrogate entries treated as exemplar rows.
  - Why: S1/S3 definitions are substrate-facing, while Translation biology also drains charged tRNA state.
  - Inversion risk: hidden omission in non-metabolite channels.
  - Falsifier: explicit evidence of direct MATLAB `this.substrates(...)` AA/FMET decrements in `Translation.m`.
- D2: GTP/H2O OC consume attribution.
  - Choice: classify consume-entry OC side as `ROW_WRONG` when only gating read exists.
  - Why: S2 requires a real OC consume path, not a read-side elongation cap.
  - Inversion risk: over-penalizing deliberate documentation of mixed mode.
  - Falsifier: any OC `next_update` branch that emits negative GTP/H2O substrate deltas.
- D3: Ordering constraint attribution.
  - Choice: classify row ordering claim as `ROW_WRONG` with `judgment=required` (ambiguous OC applicability).
  - Why: row `hard_after` is declared, but OC composite flow does not encode a matching process-order edge.
  - Inversion risk: treating MATLAB-only note as full cross-runtime contract.
  - Falsifier: explicit OC scheduler/flow dependency forcing `karr_trna_aminoacylation` before `karr_translation_v3`.

### Risks (unresolved ambiguity)
- R1: AA surrogate scope in `consume_stoichiometry` may be interpreted as exhaustive by future auditors.
- R2: OC compartment flattening impact is context-sensitive; for single-compartment WIDs it may be harmless, but row currently states no projection merge.
- R3: OC process execution ordering semantics (processes vs steps) are not fully explicit in this row and can be misread as MATLAB-equivalent ordering.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| TL-S1-01 | S1 | `consume_stoichiometry` includes metabolite consumes `GTP` and `H2O` (`Translation.yaml:139-163`). | Translation substrate consume formulas are on `GTP`/`H2O` in `calcResourceRequirements_Current` (`Translation.m:588-595`) with consume applied in `evolveState` writeback (`Translation.m:907-908`); no direct AA substrate decrement branch appears (`Translation.m:207-213`, `672-676`, `907-911`). | OC has separate AA consume surrogate paths, but this claim is MATLAB-side completeness against row entries. | VERIFIED | `judgment=required` for scope boundary (metabolite substrate vector vs charged-tRNA channel). |
| TL-S2-01 | S2 | Row AA consume exemplars `ALA/MET/LYS` claim OC surrogate consume path (`Translation.yaml:164-199`). | MATLAB drains aminoacylated tRNA channel via `polymerize` call (`Translation.m:775-778`) and reconciles free vs aminoacylated tRNA (`Translation.m:904`). | OC emits AA requests from predicted synthesis (`karr_request_calculators.py:639-655`) and applies AA negative deltas via allocated budget or direct available clip (`karr_translation_v3.py:602-617`, `191-205`). | VERIFIED | `judgment=required`: exemplar AA rows are representative, not full 20-AA enumeration. |
| TL-S2-02 | S2 | Row places `GTP/H2O` under consume stoichiometry with OC anchors (`Translation.yaml:140-163`). | MATLAB actually consumes allocated `GTP/H2O` (`Translation.m:672-676`, `907-908`). | OC `GTP/H2O` branch is optional read-side gating only (`karr_translation_v3.py:234-245`, `341-352`) and `next_update` writes no negative `GTP/H2O` substrate deltas (`karr_translation_v3.py:601-618`). | ROW_WRONG | Row consume attribution conflates OC gating read with consume write path. |
| TL-S3-01 | S3 | Row produce set includes `GDP`, `PI`, `H` formulas (`Translation.yaml:200-236`). | MATLAB byproduct writes are `+GDP`, `+PI`, `+H` (`Translation.m:909-911`). | OC difference exists, but MATLAB-to-row produce completeness is intact for listed byproducts. | VERIFIED | Completeness side of S3 passes. |
| TL-S3-02 | S3 | Row notes OC does not emit `GDP/PI/H` metabolite byproducts (`Translation.yaml:208-236`, `431-436`). | MATLAB emits those byproducts (`Translation.m:909-911`). | OC update emits protein/enzyme/AA deltas only; no `GDP/PI/H` produce keys (`karr_translation_v3.py:590-618`). | CODE_DEVIATES | Row correctly captures MATLAB-vs-OC produce fabrication divergence. |
| TL-S4-01 | S4 | Row request-formula block states MATLAB requests `GTP/H2O` while OC requests AA pools via predicted synthesis (`Translation.yaml:105-108`, `431-433`). | MATLAB formulas: `GTP = nInit + 2*nElong + 3*nTerm`; water overwritten to final `+nElong` (`Translation.m:588-595`). | OC request formula is `predict_synthesis_per_s -> _predict_substrate_need -> max(0, need_by_aa)` (`karr_request_calculators.py:652-655`; `karr_translation_v3.py:185-189`). | CODE_DEVIATES | Formula families are not equivalent modulo syntax. |
| TL-S4-02 | S4 | Row deviation says MATLAB charged-tRNA/polymerize bookkeeping is collapsed in OC to synthesis-rate surrogate plus rounding (`Translation.yaml:436`). | MATLAB polymerization is greedy sequence/energy-limited with floor/min and random tie resolution (`polymerize.m:42-93`, `97-114`) called from Translation (`Translation.m:775-778`). | OC consume path computes continuous AA need, clips by budget (`min(need, budget)`), then stochastic-rounds (`karr_translation_v3.py:185-205`, `613-615`). | CODE_DEVIATES | Includes clipping/bounds-transform mismatch (not mathematically equivalent). |
| TL-S5-01 | S5 | Row declares `mismatch: false` for routing and sets `shared_pool_projection_merges_compartments: false` (`Translation.yaml:237-277`, `430`). | MATLAB allocation/writeback is compartment-indexed through metabolite global-compartment indices (`Simulation/evolveState.m:32-33`, `63-73`) and cytosol-indexed RNA local states (`Translation.m:329-347`). | OC translation surfaces use flat shared `substrates` keys without compartment axis (`karr_translation_v3.py:142-149`; `karr_composite.py:1306-1311`, `1466`). | ROW_WRONG | Compartment projection/merge behavior is present at OC surface; `judgment=required` on biological impact per WID. |
| TL-S5-02 | S5 | Row compartment routing marks `GDP/PI/H` produce mismatch false (`Translation.yaml:263-277`). | MATLAB routes byproduct writes to substrate compartment vector (`Translation.m:909-911`). | OC emits no `GDP/PI/H` byproduct route in Translation update (`karr_translation_v3.py:590-618`). | ROW_WRONG | Route-absence should not be labeled as compartment match. |
| TL-S6-01 | S6 | Row allocator mode says `karr=allocation`, `oc_current=mixed` (`Translation.yaml:101-104`, `130-138`, `433`). | MATLAB allocator path: requirements computed per process then fair fixed allocations injected into `mod.substrates` before `evolveState` (`Simulation/evolveState.m:31-37`, `63-70`). | OC uses AA request/grant path (`karr_request_calculators.py:639-655`; `karr_translation_v3.py:196-205`) while still directly reading `GTP/H2O` in biology helper (`karr_translation_v3.py:341-352`); composite enables allocator budget (`karr_composite.py:1016-1023`, `1160`, `1551-1561`). | CODE_DEVIATES | Row accurately captures mixed allocator engagement. |
| TL-S6-02 | S6 | Row request/bypass blocks say OC requests representative AAs and bypasses `GTP/H2O` (`Translation.yaml:109-138`). | MATLAB requests energy/water metabolites in allocator-facing method (`Translation.m:588-595`). | OC request calculator emits AA-only request vector from `allocation_substrate_wids` (`karr_request_calculators.py:618-619`, `640-644`, `654`), and `GTP/H2O` remain read-side bypass (`karr_translation_v3.py:341-347`). | CODE_DEVIATES | Request/grant participation differs but row states divergence correctly. |
| TL-S6-03 | S6 | Row declares `hard_after: tRNAAminoacylation` with MATLAB ordering note (`Translation.yaml:306-312`). | MATLAB explicitly loops until process order satisfies tRNAAminoacylation before Translation (`Simulation/evolveState.m:48-55`). | OC flow constrains request calculators before allocation, but no explicit dependency edge between `karr_trna_aminoacylation` and `karr_translation_v3` process execution (`karr_composite.py:1511-1515`, `1540-1563`, `2295-2299`, `2334-2357`). | ROW_WRONG | `judgment=required`: row ordering statement is ambiguous for OC-side applicability and should be made explicit. |

## Aggregate Counts
- VERIFIED: 3
- ROW_WRONG: 4
- CODE_DEVIATES: 5
- MISSING: 0

## Priority-1 Fixes
- TL-S2-02: move OC `GTP/H2O` gating read out of consume-fabrication wording (or add explicit non-consume qualifier in row schema fielding).
- TL-S5-01: correct compartment projection flag/routing prose for flat OC substrate surface.
- TL-S5-02: mark `GDP/PI/H` OC routing as absent/deviant instead of `mismatch: false`.
- TL-S6-03: disambiguate ordering constraint as MATLAB-only or encode OC-side enforcement claim explicitly.

## Known-Deviation Mapping (Translation)
- T-A1 (request vector divergence: MATLAB energy/water vs OC AA requests): `TL-S4-01`, `TL-S6-02`
- T-A2 (mixed allocator mode with direct GTP/H2O bypass): `TL-S2-02`, `TL-S6-01`
- T-A3 (MATLAB byproduct emission absent in OC): `TL-S3-02`, `TL-S5-02`
- T-A4 (compartment projection/merge ambiguity on OC shared substrate surface): `TL-S5-01`

## Auditor Discretion List
- `TL-S1-01` (scope boundary between metabolite substrate vector vs charged-tRNA state channel)
- `TL-S2-01` (representative AA exemplar interpretation)
- `TL-S5-01` (materiality of compartment flattening for specific WIDs)
- `TL-S6-03` (ordering claim applicability across MATLAB vs OC execution models)
