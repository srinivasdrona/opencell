# ReplicationInitiation Semantic Audit

## Header
- Process name: `ReplicationInitiation`
- Process slug: `replication_initiation`
- Audited files:
  - `data/schemas/per_process_wiring/ReplicationInitiation.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ReplicationInitiation.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_replication_initiation.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: `strict completeness` (all MATLAB evolveState substrate behaviors must be represented; not exemplar-scoped)
- Header note: `FULL`

## Deliberate Action Prefix v2
- Beat 1 (contract): Verify or falsify row semantics against executable MATLAB and OC behavior for S1-S6, with attribution to row vs code.
- Beat 2 (surface): row `ReplicationInitiation.yaml`; MATLAB process `ReplicationInitiation.m`; MATLAB scheduler/allocation `@Simulation/evolveState.m`; OC process `karr_replication_initiation.py`; OC flow wiring `karr_composite.py`.
- Beat 3 (expected outcome): A claim table using only `VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`, plus aggregate counts and Priority-1 row fixes.
- Beat 4 (invert): A false pass could happen if only row anchors are checked while missing real substrate updates in MATLAB `reactivateFreeDnaAADP` and allocator-ordering semantics from scheduler/flow files.
- Beat 5 (act then verify): Claims below cite executable lines for activation, hydrolysis, reactivation, requests, allocation, and flow ordering; inversion check explicitly included via `ReplicationInitiation.m:858-884` and `@Simulation/evolveState.m:24-73`.
- PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

Design contract sentence: This audit is done only if an independent reader can reproduce each verdict from the cited row, MATLAB, and OC branches without relying on prose-only anchors.

## Decision Ledger
Decision D1
- Question: completeness policy for S1/S3.
- Options considered: exemplar-scoped completeness; strict completeness.
- Chosen option: strict completeness.
- Rationale: row does not declare exemplar scope; strict policy avoids hiding omissions.

Decision D2
- Question: verdict precedence when row is inaccurate and OC also diverges.
- Options considered: `CODE_DEVIATES` first; `ROW_WRONG` first.
- Chosen option: `ROW_WRONG` first.
- Rationale: remediation owner is the row when row statement/anchor is false.

Decision D3
- Question: handling mode-dependent OC branches (main path vs trace-hint path).
- Options considered: ignore trace-hint branch; include with discretion marker.
- Chosen option: include and mark `judgment=required` where branch-dependent.
- Rationale: branch semantics exist and can change consume/produce evidence.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| RI-S1-01 | S1 | `consume_stoichiometry` lists only `ATP` and `H2O` (`ReplicationInitiation.yaml:158-180`). | `evolveState` consumes `ATP` in `activateFreeDnaA` and `reactivateFreeDnaAADP`, and `H2O` in `inactivateFreeDnaAATP` (`ReplicationInitiation.m:547,577,882`). | Main update consumes `ATP` in `_activate_free_dnaa` and `H2O` in `_inactivate_free_dnaa_atp` (`karr_replication_initiation.py:740-747,749-777`). | VERIFIED | Completeness by substrate WID passes; ATP has two MATLAB consume branches. |
| RI-S2-01 | S2 | Row consume entries map to OC consume anchors for `ATP` and `H2O` (`ReplicationInitiation.yaml:166-180`). | Consume paths are allocation-limited substrate reads (`ReplicationInitiation.m:537-539,563-574,867-869`). | Real consume deltas exist in main path (`karr_replication_initiation.py:747,776`); trace-hint branch only emits `H2O` consume (`karr_replication_initiation.py:681-685`). | VERIFIED | judgment=required: ATP consume is absent in trace-hint replay branch. |
| RI-S3-01 | S3 | Produce list is `ADP`, `PI`, `H` (`ReplicationInitiation.yaml:181-214`). | Substrate products are `PI`/`H` in hydrolysis and `ADP` in reactivation (`ReplicationInitiation.m:578-579,883`). | Main path produces `ADP`, `PI`, `H` in hydrolysis helper (`karr_replication_initiation.py:774-777`). | VERIFIED | Completeness by produced substrate set passes. |
| RI-S3-02 | S3 | Row anchors `ADP` production to hydrolysis block (`ReplicationInitiation.yaml:182-192`, MATLAB anchor `576-581`). | Hydrolysis updates `PI`/`H` and DnaA-ADP enzyme, not substrate `ADP` (`ReplicationInitiation.m:576-581`); substrate `ADP` is produced in reactivation (`ReplicationInitiation.m:883`). | OC produces substrate `ADP` during hydrolysis (`karr_replication_initiation.py:774`). | ROW_WRONG | Row MATLAB attribution for `ADP` production is false. |
| RI-S4-01 | S4 | Request formulas are explicitly different in row (`ReplicationInitiation.yaml:132-135`). | `ATP` request = free `DnaA` + free/bound `DnaA-ADP`; `H2O` request = `(2:7)*DnaA_polymer_ATP` (`ReplicationInitiation.m:497-503`). | `ATP` request = `max(0, free_dnaa_adp)`; `H2O` request = `max(0, free_dnaa_atp)` (`karr_replication_initiation.py:435-439`). | CODE_DEVIATES | Row correctly documents MATLAB-vs-OC request-formula divergence. |
| RI-S4-02 | S4 | `H2O` consume formula is polymer-based with water clipping (`ReplicationInitiation.yaml:172`). | Hydrolysis uses polymer counts `(2:7)*nDissociatingPolymers` and iterative clipping to water (`ReplicationInitiation.m:561-574`). | Hydrolysis uses binomial events on free ATP monomers, then water clamp (`karr_replication_initiation.py:757-768`). | ROW_WRONG | Row does not state OC’s non-equivalent hydrolysis formula family. |
| RI-S4-03 | S4 | No row formula claim covers reactivation substrate transform in consume/produce sections (`ReplicationInitiation.yaml:158-214`). | Reactivation consumes `ATP` and produces substrate `ADP` with stochastic-round bound (`ReplicationInitiation.m:865-883`). | Reactivation helper changes protein pools only; no `ATP`/`ADP` substrate deltas (`karr_replication_initiation.py:923-938`). | MISSING | Reactivation substrate formula family is omitted from row semantics. |
| RI-S5-01 | S5 | Routing says `ATP`/`H2O` consumed in cytosol and `ADP`/`PI`/`H` produced in cytosol; no compartment merge projection (`ReplicationInitiation.yaml:215-240,371-377`). | Process substrate updates are mapped through `substrateMetaboliteGlobalCompartmentIndexs` (`@Simulation/evolveState.m:32-33,63-73`). | OC writes substrate deltas by WID keys and reads allocated WID keys (`karr_replication_initiation.py:270-285,334-337,429-433`); no in-process compartment projection/merge operator. | VERIFIED | judgment=required: OC substrate store is compartment-implicit (single shared keyspace). |
| RI-S6-01 | S6 | Allocator mode is `allocation` on both sides; `ATP/H2O` requested, `ADP/PI/H` bypass allocator (`ReplicationInitiation.yaml:127-157`). | MATLAB computes requirements then fair-share allocations, injects allocation before process `evolveState` (`@Simulation/evolveState.m:24-37,63-70`). | OC reads `substrates_allocated[self.name]` and emits `requests[self.name]` in process update (`karr_replication_initiation.py:334-336,435-439`). | VERIFIED | Allocator engagement mode matches (request/grant path is active). |
| RI-S6-02 | S6 | Row states OC embeds request semantics in `next_update` rather than dedicated request-calculator (`ReplicationInitiation.yaml:22-34,373`). | MATLAB uses dedicated pre-pass requirement computation before process execution (`@Simulation/evolveState.m:24-31,59-70`). | Chassis flow has request-calculator steps feeding allocation, but no replication-initiation request-calculator step; replication initiation emits requests inside process update (`karr_composite.py:2320-2356`, `karr_replication_initiation.py:435-439`). | CODE_DEVIATES | judgment=required: exact same-tick vs next-tick visibility depends on Vivarium process/step ordering semantics. |

## Aggregate Counts
- VERIFIED: 5
- ROW_WRONG: 2
- CODE_DEVIATES: 2
- MISSING: 1

## Priority-1 Fixes
- RI-S3-02 (`ROW_WRONG`): fix `ADP` MATLAB anchor/formula attribution (hydrolysis vs reactivation).
- RI-S4-02 (`ROW_WRONG`): document OC hydrolysis family divergence from MATLAB polymer-based formula.
- RI-S4-03 (`MISSING`): add explicit reactivation substrate formula claim (`ATP -> ADP` branch) and OC divergence status.

## Known-Deviation Mapping
- RI-D1: Request-formula and request-surface drift is documented (`RI-S4-01`, `RI-S6-02`).
- RI-D2: Hydrolysis/reactivation substrate-formula drift is under-documented or mis-attributed (`RI-S3-02`, `RI-S4-02`, `RI-S4-03`).

## Auditor Discretion List
- RI-S2-01: `judgment=required` (trace-hint branch consume behavior differs from main path).
- RI-S5-01: `judgment=required` (implicit vs explicit compartment axis mapping).
- RI-S6-02: `judgment=required` (allocator-coupled ordering visibility depends on engine semantics).

## Risks
R1. OC trace-hint replay path omits some substrate deltas present in main path.
- Likelihood: medium
- Impact: medium
- Detection: compare `next_update` vs `_next_update_from_trace_hint` substrate updates each release.

R2. Compartment semantics are implicit in OC substrate keyspace.
- Likelihood: medium
- Impact: medium
- Detection: verify future compartment-explicit substrate stores do not silently invalidate `cytosol` routing claims.

R3. Process-vs-step ordering semantics in Vivarium can change allocator visibility timing.
- Likelihood: medium
- Impact: high
- Detection: add an integration probe that logs one tick of requests, allocations, and consumption for `karr_replication_initiation`.
