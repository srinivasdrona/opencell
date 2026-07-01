# DNASupercoiling Semantic Audit

## Header
- Process name: `DNASupercoiling` (`dna_supercoiling`)
- Audited files:
  - `data/schemas/per_process_wiring/DNASupercoiling.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNASupercoiling.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_dna_supercoiling.py`
  - `opencell/vivarium/karr_allocation_step.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: `strict completeness` (row treated as exhaustive unless explicitly marked exemplar-scoped; this row is not marked exemplar-scoped).

## DELIBERATE_ACTION_PREFIX_v2
- Beat 1 (contract): verify/falsify whether row-level semantic claims for DNASupercoiling match executable MATLAB and OC behavior for S1-S6. Done means claim-level verdicts are reproducible from cited code paths, not just anchor presence.
- Beat 2 (surface): row `DNASupercoiling.yaml`; MATLAB `DNASupercoiling.m` + `@Simulation/evolveState.m`; OC `karr_dna_supercoiling.py`, `karr_allocation_step.py`, `karr_composite.py`. Suspect pattern: request-path vs consume-path conflation in row OC anchors.
- Beat 3 (expected outcome): produce a claim table using only `VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`, plus aggregate counts and Priority-1 fixes.
- Beat 4 (invert): worst false-pass mode is accepting row consume fabrication because ATP appears in OC request logic even if actual consume occurs elsewhere.
- Beat 5 (act/verify): each claim below cites executable conditions/formulas/routes (not prose-only descriptions), then totals and remediation priorities are computed from the table.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Revision-Minimum Addenda
- Design contract sentence: semantic truth for DNASupercoiling is that consume/produce tuples, formulas, compartment routing, and allocator coupling in the row are reproducible from MATLAB and OC execution paths.

### Decision Ledger (non-obvious attribution)
- D1: `strict completeness` chosen over exemplar-scoped completeness because row lacks explicit exemplar declaration; omission verdicts therefore use `MISSING`.
- D2: ATP consume fabrication classified `ROW_WRONG` (not `VERIFIED`) because row OC consume anchor points request emission (`karr_dna_supercoiling.py:555-577`) rather than the consume write path (`1024-1035`).
- D3: allocator ordering gap classified `MISSING` (not `CODE_DEVIATES`) because MATLAB ordering is explicit but OC same-tick coupling depends on runtime scheduling semantics not fully encoded in row; omission is certain, runtime consequence needs judgment.

### Risks (unresolved ambiguity)
- R1: MATLAB compartment identity for each substrate is inferred via process global-compartment indexing path, not an explicit compartment literal in `DNASupercoiling.m` (`judgment=required`).
- R2: OC allocator-coupled timing for process-emitted requests vs allocation step is partially schedule-dependent; wiring evidence shows missing explicit dependency but exact tick-lag behavior needs runtime confirmation (`judgment=required`).

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| DNASUP-S1-01 | S1 | `consume_stoichiometry` lists only ATP and H2O as consumed substrates (`DNASupercoiling.yaml:221-245`). | Substrate accounting consumes ATP and H2O (`DNASupercoiling.m:495-496`), with no other negative substrate writes in this process block. | Consume delta is ATP/H2O negative only (`karr_dna_supercoiling.py:1027-1030`). | VERIFIED | Strict completeness satisfied for consume set. |
| DNASUP-S2-01 | S2 | ATP consume entry points OC anchor `karr_dna_supercoiling.py:555-577` (`DNASupercoiling.yaml:222-233`). | ATP is consumed in evolve substrate accounting (`DNASupercoiling.m:494-496`). | `555-577` is request emission; ATP consume write is `_substrate_delta` (`karr_dna_supercoiling.py:1027-1029`) applied via `update["substrates"]` (`623-630`). | ROW_WRONG | Row OC anchor fabricates consume-path evidence (request path != consume path). |
| DNASUP-S2-02 | S2 | H2O consume entry points `_substrate_delta` (`DNASupercoiling.yaml:234-245`). | H2O consumed with ATP hydrolysis (`DNASupercoiling.m:494-496`). | H2O decremented 1:1 with ATP in `_substrate_delta` (`karr_dna_supercoiling.py:1028-1030`) and emitted as substrate delta (`623-630`). | VERIFIED | Real OC consume path exists for row H2O entry. |
| DNASUP-S3-01 | S3 | Produce set is ADP, PI, H (`DNASupercoiling.yaml:246-282`). | Produce writes are ADP, phosphate, hydrogen (`DNASupercoiling.m:497-499`). | OC produce writes ADP/PI and conditional H in `_substrate_delta` (`karr_dna_supercoiling.py:1030-1035`). | VERIFIED | Produce completeness holds for declared process outputs. |
| DNASUP-S3-02 | S3 | ADP and PI are direct hydrolysis products (`DNASupercoiling.yaml:247-270`). | ADP/PI increment by `nATP` (`DNASupercoiling.m:497-498`). | ADP/PI increment by `atp_used` (`karr_dna_supercoiling.py:1030-1032`). | VERIFIED | Produce fabrication confirmed for ADP/PI. |
| DNASUP-S3-03 | S3 | H is produced when fixture exposes hydrogen (`DNASupercoiling.yaml:271-282`). | H incremented by `nATP` (`DNASupercoiling.m:499`). | H emitted only if `self.h_wid is not None` (`karr_dna_supercoiling.py:212`, `1033-1034`). | VERIFIED | `judgment=required` (conditional branch is explicit; fixture-dependent parity). |
| DNASUP-S4-01 | S4 | Hydrolysis formula family is event-count times ATP cost; 1:1 ATP/H2O consume and ADP/PI/H produce (`DNASupercoiling.yaml:224-245`, `249-273`). | `nATP = nStrandPassingEvents * atpCost`; then ATP/H2O `-nATP`, ADP/PI/H `+nATP` (`DNASupercoiling.m:486-499`). | `atp_used = gyrase_events*gyrase_cost + topoiv_events*topoiv_cost` (`karr_dna_supercoiling.py:555-558`), then same sign pattern in `_substrate_delta` (`1027-1034`) after ATP/H2O clipping (`510-517`, `912-947`). | VERIFIED | `judgment=required` (equivalent hydrolysis family despite different event-limiting implementation shape). |
| DNASUP-S4-02 | S4 | Row states OC request is a superset of MATLAB current-request helper (`DNASupercoiling.yaml:187-190`). | Current request is gyrase-only (`DNASupercoiling.m:346-352`). | `_atp_request` includes expected gyrase + topoIV + replication extra, dt scaling, safety factor, max cap (`karr_dna_supercoiling.py:985-1022`). | CODE_DEVIATES | Row correctly attributes MATLAB-vs-OC formula divergence. |
| DNASUP-S5-01 | S5 | Routing table claims ATP/H2O consume and ADP/PI/H produce in cytosol (`DNASupercoiling.yaml:283-308`). | Process substrate vector (`ATP, ADP, PI, H2O, H`) is mapped through global-compartment indices in simulation allocation/writeback path (`DNASupercoiling.m:160-166`; `evolveState.m:32-33`, `63-73`). | OC writes these WIDs through flat shared `substrates` port (`karr_dna_supercoiling.py:319-322`, `623-630`, `1027-1034`). | VERIFIED | `judgment=required` (MATLAB compartment literal is indirect; inferred via process substrate-compartment indexing). |
| DNASUP-S5-02 | S5 | Row claims no compartment projection/merge mismatch (`shared_pool_projection_merges_compartments: false`; `DNASupercoiling.yaml:438`, `445`). | No process-local projection transform is encoded in this process block; writes occur on process substrate vector then simulation remaps via global-compartment indices (`DNASupercoiling.m:494-499`; `evolveState.m:32-33`, `63-73`). | OC DNASupercoiling has no `sum(axis=1)`/projection stage; it emits direct WID deltas (`karr_dna_supercoiling.py:623-630`, `1024-1035`). | VERIFIED | `judgment=required` (no merge transform observed; effective parity assumes only the cited tuple set is in scope). |
| DNASUP-S6-01 | S6 | Allocator mode is `allocation` for both MATLAB and OC; ATP/H2O requested then granted (`DNASupercoiling.yaml:183-199`). | MATLAB computes requirements then fair-share allocations, then runs process against allocation (`evolveState.m:24-37`, `63-70`). | OC process reads `substrates_allocated[self.name]` (`karr_dna_supercoiling.py:459-462`), emits requests (`573-577`); allocator step allocates fair-share (`karr_allocation_step.py:210-280`); process ports wired to `requests` and `substrates_allocated` (`karr_composite.py:2107-2113`) and enrolled as ATP/H2O consumer (`karr_composite.py:1772`). | VERIFIED | Allocator engagement mode matches (request/grant participation present). |
| DNASUP-S6-02 | S6 | Row states no DNASupercoiling-specific ordering rule, but does not encode allocator-coupled request/allocate timing claim (`DNASupercoiling.yaml:328-333`). | MATLAB enforces per-tick request calculation then allocation before process `evolveState` (`evolveState.m:24-37`, `59-71`). | OC emits DNASupercoiling request inside process `next_update` (`karr_dna_supercoiling.py:560-577`), while allocation-step flow dependencies list request-calculator steps only (`karr_composite.py:2335-2356`). | MISSING | `judgment=required` (row omits an allocator-coupled ordering claim that is semantically load-bearing). |

## Aggregate Counts
- VERIFIED: 9
- ROW_WRONG: 1
- CODE_DEVIATES: 1
- MISSING: 1

## Priority-1 Fixes
- `DNASUP-S2-01` (`ROW_WRONG`): update ATP consume OC anchor/note to point to actual consume path (`karr_dna_supercoiling.py:1024-1035`, `623-630`), not request emission.
- `DNASUP-S6-02` (`MISSING`): add explicit row claim for allocator-coupled ordering semantics (MATLAB per-tick request→allocation→evolve contract vs current OC wiring/dependency shape).

## Known-Deviation Mapping
- A1-like (allocator/request semantics): `DNASUP-S6-02`
- Formula/controller-shape divergence: `DNASUP-S4-02`

## Auditor Discretion List
- `DNASUP-S3-03`
- `DNASUP-S4-01`
- `DNASUP-S5-01`
- `DNASUP-S5-02`
- `DNASUP-S6-02`
