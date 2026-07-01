# DNARepair Semantic Wiring Audit

## Deliberate Action Prefix v2
### Beat 1 - Contract
- Required behavior: verify/falsify row-level DNARepair semantic claims against MATLAB process behavior and OC runtime behavior using claim-level verdicts (`VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`).
- Done looks like: a reproducible claim table where each verdict is attributable to concrete MATLAB/OC execution logic and row statements, not anchor existence.

### Beat 2 - Surface
- Row surface: `data/schemas/per_process_wiring/DNARepair.yaml`
- MATLAB surfaces: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNARepair.m`, `docs/karr_extracts/process/05_DNARepair.md`, `docs/karr_extracts/architecture/01_simulation_loop.md`
- OC surface: `opencell/vivarium/karr_dna_repair.py`
- Suspect patterns called out before verdicting:
  - Row uses extract-only MATLAB anchors despite direct `.m` source availability.
  - Row mixes "Karr chemistry truth" and "current OC omissions" inside stoichiometry lists, which can mask completeness/fabrication failures.

### Beat 3 - Expected Outcome
- Observable: claim table covering S1-S6 with only allowed verdict vocabulary, aggregate counts, and explicit Priority-1 remediation list.
- Distinguishing evidence: at least one claim per category cites executable formula/route (allocator request/grant, substrate mutation, or routing tuple behavior).

### Beat 4 - Invert (Pre-mortem)
- Most embarrassing false-pass mode: audit "looks complete" by trusting row prose/extract summaries while missing MATLAB executable substrate mutations (for example NER corrections and ligation/modification stoichiometry paths).

### Beat 5 - Act Then Verify
- Action performed: re-read row, MATLAB executable branches, architecture allocator loop, OC update/request helpers, and fixture-backed reaction stoichiometry evidence.
- Verification method: claim-level citations below use concrete branch/formula locations and fixture-derived consume/produce sets.

PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Header
- Process name: `DNARepair` (`dna_repair`)
- Audited files:
  - `data/schemas/per_process_wiring/DNARepair.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNARepair.m`
  - `docs/karr_extracts/process/05_DNARepair.md`
  - `docs/karr_extracts/architecture/01_simulation_loop.md`
  - `opencell/vivarium/karr_dna_repair.py`
- Scope policy: `strict completeness` (row does not explicitly declare exemplar-only consume/produce scope).

## Revision-Class Minimum
Design contract sentence: Semantic truth checked here is whether row claims about consume/produce sets, formulas, routing tuples, and allocator coupling are materially true against MATLAB executable behavior and current OC behavior.

### Decision Ledger (non-obvious attribution calls)
- D1: Completeness policy
  - Choice: strict.
  - Why: row lacks explicit exemplar-scope declaration for `consume_stoichiometry` / `produce_stoichiometry`.
  - Falsifier: explicit row declaration that lists are exemplar-only.
- D2: MATLAB consume/produce evidence source
  - Choice: use executable MATLAB branches plus fixture-backed small-molecule stoichiometry set for DNARepair reactions.
  - Why: row’s MATLAB extract anchors omit executable updates and under-specify metabolite set.
  - Falsifier: MATLAB branch proving fixture reactions are not used by `evolveState` paths.
- D3: AMP/PPI row entries under fabrication
  - Choice: classify as `CODE_DEVIATES` (not `ROW_WRONG`) when claim is "MATLAB product exists, OC omits."
  - Why: row explicitly states omission in note; that is a correctly described divergence.
  - Falsifier: OC branch emitting AMP/PPI today.

## Claims
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| DNARepair-S1-01 | S1 | `consume_stoichiometry` lists only ATP + DATP/DCTP/DGTP/DTTP as consume set (`data/schemas/per_process_wiring/DNARepair.yaml:127-182`). | DNARepair consumes additional metabolites via executable reactions, including `NAD` (ligation), `AMET` (MunI methylation), and `H2O` (MunI restriction), plus ATP/dNTP (`data/m1_sources/.../DNARepair.m:1466-1469`, `1513-1516`, `1546-1549`; fixture reaction stoichiometry-backed set). | OC consumes ATP/dNTP tracked substrates and conditionally consumes AMET (`opencell/vivarium/karr_dna_repair.py:256-257`, `351-359`). | MISSING | Strict completeness fails: row omits MATLAB-consumed `NAD`, `AMET`, `H2O`. |
| DNARepair-S2-01 | S2 | Every row consume entry (ATP + four dNTPs) is declared with OC anchors (`data/schemas/per_process_wiring/DNARepair.yaml:127-182`). | MATLAB consumes ATP+dNTP in repair flows (`data/m1_sources/.../DNARepair.m:889-890`, `1400-1440`). | OC has real consume path for ATP/dNTP: tracked substrates, computed needs, negative substrate updates (`opencell/vivarium/karr_dna_repair.py:256-257`, `328`, `351-355`, `704-721`). | VERIFIED |  |
| DNARepair-S3-01 | S3 | `produce_stoichiometry` lists AMP, PPI, AHCYS, H (`data/schemas/per_process_wiring/DNARepair.yaml:183-231`). | MATLAB produces a larger set via repair chemistry and correction branches (for example `ADP`, `PI`, `NMN`, `DAMP/DCMP/DGMP/DTMP`, `DR5P`, damaged base products) (`data/m1_sources/.../DNARepair.m:1173-1204`, `1439-1440`, `1482-1483`, `1529-1530`; fixture-derived produced set). | OC emits only AHCYS/H side effect and does not emit broader MATLAB product set (`opencell/vivarium/karr_dna_repair.py:356-360`). | MISSING | Strict completeness fails on produce side. |
| DNARepair-S3-02 | S3 | Row explicitly marks AMP/PPI as MATLAB products currently omitted by OC (`data/schemas/per_process_wiring/DNARepair.yaml:184-207`). | MATLAB ligation/polymerization produce these products through stoichiometric updates (`data/m1_sources/.../DNARepair.m:1439-1440`, `1482-1483`). | OC update path has no AMP/PPI emissions (`opencell/vivarium/karr_dna_repair.py:350-360`). | CODE_DEVIATES | Divergence is accurately captured by row note. |
| DNARepair-S3-03 | S3 | Row lists AHCYS/H as RM methylation products (`data/schemas/per_process_wiring/DNARepair.yaml:208-231`). | MATLAB RM methylation applies reaction stoichiometry for `DNA_RM_MunI_Methylation` (`data/m1_sources/.../DNARepair.m:1513-1530`), whose small-molecule products include AHCYS/H. | OC emits AHCYS/H when AMET methylation side effect fires (`opencell/vivarium/karr_dna_repair.py:339-360`). | VERIFIED | judgment=required (MATLAB product identity is from reaction stoichiometry mapping, not explicit hard-coded species writes). |
| DNARepair-S4-01 | S4 | Row MATLAB request formula is expressed as pathway-level repair-count sum with per-event ATP/dNTP costs (`data/schemas/per_process_wiring/DNARepair.yaml:81-84`). | MATLAB request formula is `max(0,-S) * min(ceil(C*E*dt), rates)` with reaction-rate vector from lesion counts (`data/m1_sources/.../DNARepair.m:853-891`). | OC computes desired repairs with Poisson pathway capacities and then converts to substrate needs (`opencell/vivarium/karr_dna_repair.py:678-721`). | ROW_WRONG | Row’s MATLAB formula attribution is not mathematically equivalent to executable MATLAB logic. |
| DNARepair-S4-02 | S4 | Row consume formulas encode fixed pathway patch-length × `dntp_split` decomposition (`data/schemas/per_process_wiring/DNARepair.yaml:139-175`). | MATLAB dNTP usage is sequence/reaction driven (polymerize baseCosts, NER subsequence counts, stoichiometry-matrix updates), not a fixed global split formula (`data/m1_sources/.../DNARepair.m:1176-1180`, `1189-1204`, `1431-1440`). | OC uses explicit fixed split (`dntp_total * dntp_split`) (`opencell/vivarium/karr_dna_repair.py:708-711`). | ROW_WRONG | Cross-side formula equivalence is misstated. |
| DNARepair-S5-01 | S5 | Row routes ATP/dNTP consumption to cytosol tuples with `mismatch: false` (`data/schemas/per_process_wiring/DNARepair.yaml:233-257`). | MATLAB metabolite exchange runs through process substrate-compartment indices in allocator/evolve path (`docs/karr_extracts/architecture/01_simulation_loop.md:155-157`, `187-197`; `data/m1_sources/.../DNARepair.m:510-531`). | OC tracks ATP/dNTP as scalar substrate entries and updates those exact keys (`opencell/vivarium/karr_dna_repair.py:291-294`, `351-355`). | VERIFIED | judgment=required (MATLAB file here does not print explicit compartment label strings at mutation sites). |
| DNARepair-S5-02 | S5 | Row marks AMP/PPI routing as `mismatch: false` while also noting OC omits emissions (`data/schemas/per_process_wiring/DNARepair.yaml:258-267`). | MATLAB can emit AMP/PPI via ligation/polymerization stoichiometry (`data/m1_sources/.../DNARepair.m:1439-1440`, `1482-1483`). | OC does not emit AMP/PPI in substrate update (`opencell/vivarium/karr_dna_repair.py:350-360`). | ROW_WRONG | `(substrate, compartment)` tuple sets differ; `mismatch` should not be `false`. |
| DNARepair-S5-03 | S5 | Row says `shared_pool_projection_merges_compartments: false` (`data/schemas/per_process_wiring/DNARepair.yaml:384`). | MATLAB uses direct global-compartment allocation/writeback without merge projection step in process execution loop (`docs/karr_extracts/architecture/01_simulation_loop.md:187-200`). | OC path has no compartment-sum projection/merge operator in DNARepair update; writes direct per-key substrate deltas (`opencell/vivarium/karr_dna_repair.py:291-313`, `351-360`). | VERIFIED |  |
| DNARepair-S6-01 | S6 | Row declares allocation mode on both sides for core repair demand (`data/schemas/per_process_wiring/DNARepair.yaml:77-105`). | MATLAB computes per-process requirements then applies fair allocator grants before `evolveState` (`docs/karr_extracts/architecture/01_simulation_loop.md:148-161`, `187-194`; `data/m1_sources/.../DNARepair.m:829-891`). | OC emits `requests[self.name][wid]` and bounds actual repair by `substrates_allocated[self.name]` (`opencell/vivarium/karr_dna_repair.py:303-334`, `347`, `723-763`). | VERIFIED |  |
| DNARepair-S6-02 | S6 | Row records AMET/AHCYS/H bypasses in OC (`data/schemas/per_process_wiring/DNARepair.yaml:106-118`). | MATLAB RM methylation uses allocated `this.substrates` path (`data/m1_sources/.../DNARepair.m:1513-1530`) and participates in allocator loop (`docs/karr_extracts/architecture/01_simulation_loop.md:187-197`). | OC reads global `substrates['AMET']` and writes AHCYS/H directly in `next_update`, outside `substrates_allocated` budget (`opencell/vivarium/karr_dna_repair.py:338-360`). | CODE_DEVIATES | Row correctly describes allocator bypass divergence. |
| DNARepair-S6-03 | S6 | Row known deviations state MATLAB random subfunction order vs OC aggregated single update (`data/schemas/per_process_wiring/DNARepair.yaml:386-387`). | MATLAB randomizes process order in simulation and randomizes DNARepair subfunction order (`docs/karr_extracts/architecture/01_simulation_loop.md:172-179`; `data/m1_sources/.../DNARepair.m:906-919`). | OC computes request, bounding, and writeback in one deterministic helper chain (aside from stochastic draws), without subfunction-order randomization (`opencell/vivarium/karr_dna_repair.py:323-337`, `678-763`). | CODE_DEVIATES | judgment=required (allocator-coupled impact of ordering collapse is semantic but not fully quantified here). |

## Aggregate Counts
- VERIFIED: 5
- ROW_WRONG: 3
- CODE_DEVIATES: 3
- MISSING: 2

## Priority-1 Fixes
- `DNARepair-S1-01` (`MISSING`): expand row consume completeness beyond ATP/dNTP to include MATLAB-consumed metabolites (`NAD`, `AMET`, `H2O` at minimum).
- `DNARepair-S3-01` (`MISSING`): expand row produce completeness to include MATLAB-produced metabolites beyond AMP/PPI/AHCYS/H.
- `DNARepair-S4-01` (`ROW_WRONG`): replace row MATLAB request formula with executable `calcResourceRequirements_Current` formula shape.
- `DNARepair-S4-02` (`ROW_WRONG`): stop presenting MATLAB dNTP usage as fixed split formula; encode sequence/reaction-driven formulation or explicitly mark as OC-only approximation.
- `DNARepair-S5-02` (`ROW_WRONG`): set routing mismatch truthfully for AMP/PPI tuple absence in OC.

## Known-Deviation Mapping (optional)
- A1 (allocator participation mismatch): `DNARepair-S6-02` (AMET/AHCYS/H bypass in OC).
- A2 (ordering semantics mismatch): `DNARepair-S6-03` (random subfunction/process order vs aggregated OC update).
- A3 (formula/source mismatch): `DNARepair-S4-01`, `DNARepair-S4-02`.
- A4 (projection/tuple mismatch): `DNARepair-S5-02` (AMP/PPI tuple omission in OC).

## Auditor Discretion List
- `DNARepair-S3-03` (stoichiometric product identity inferred through reaction mapping): `judgment=required`.
- `DNARepair-S5-01` (compartment label mapping is index-based at mutation sites): `judgment=required`.
- `DNARepair-S6-03` (ordering-collapse allocator impact not numerically replayed): `judgment=required`.

## Risks (unresolved ambiguity)
- R1: Some MATLAB metabolite identities are implied through stoichiometry matrix/reaction IDs rather than explicit per-species writes; misread risk remains if fixture/reaction mapping drifts.
- R2: Compartment routing for certain metabolites is index-based in MATLAB (global-compartment indices) and not spelled as literal compartment strings near each mutation line.
- R3: Ordering-impact magnitude (not just presence) was not replay-simulated in this pass; divergence is structurally clear but quantitatively unmeasured.

