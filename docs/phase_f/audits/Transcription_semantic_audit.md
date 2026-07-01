# Transcription Semantic Wiring Audit

## Deliberate Action Prefix v2

### Beat 1 - Contract
- Required behavior: validate whether `data/schemas/per_process_wiring/Transcription.yaml` makes semantically true claims against MATLAB `Transcription.m` + `Simulation/evolveState.m` and OC transcription/request/composite implementations.
- Done = every audited claim is reproducibly classified with allowed verdicts (`VERIFIED | ROW_WRONG | CODE_DEVIATES | MISSING`) from executable anchors, not prose.

### Beat 2 - Surface
- Row: `data/schemas/per_process_wiring/Transcription.yaml`
- MATLAB: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Transcription.m`, `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
- OC: `opencell/vivarium/karr_transcription.py`, `opencell/vivarium/karr_transcription_v3.py`, `opencell/vivarium/karr_request_calculators.py`, `opencell/vivarium/karr_composite.py`, `opencell/m2/transcription_v2.py`
- Suspect patterns called out before verdicting:
  - mixed canonical-vs-legacy OC surfaces can make allocator-mode attribution ambiguous
  - row anchors can point to legacy files while row `oc_class` is v3
  - flat `substrates` store in OC can hide compartment projection effects

### Beat 3 - Expected Outcome
- Expected observable: one claim table covering S1-S6 with deterministic claim IDs, aggregate counts, and Priority-1 remediation list for all `ROW_WRONG`/`MISSING` claims.

### Beat 4 - Invert (pre-mortem)
- Most plausible false-success mode: treat row commentary as equivalent to executable wiring and miss that OC update dictionaries never emit some row-listed products.
- Additional failure mode: audit only canonical v6 wiring and ignore legacy bypass paths that row explicitly includes.

### Beat 5 - Act Then Verify
- Action: compared row claims against executable MATLAB/OC branches for consume/produce/formula/routing/allocator engagement.
- Verification: claims below include path:line evidence and explicit `judgment=required` where attribution depends on policy.

PM sanity-check sentence: PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Revision-Class Minimum

Design contract sentence: Semantic truth being checked is whether row-level Transcription wiring claims remain executable-truthful for substrate consume/produce, formulas, compartment targeting, and allocator participation across MATLAB and OC.

### Decision Ledger (non-obvious attribution)
- D1: Scope policy for completeness checks.
  - Choice: strict completeness over explicit per-tick consume/produce surfaces (`calcResourceRequirements_Current` + `evolveState` substrate writes), not exemplar-scoped.
  - Why: row does not declare exemplar policy for `consume_stoichiometry` / `produce_stoichiometry`.
- D2: Divergence-vs-row-error precedence.
  - Choice: use `CODE_DEVIATES` when row explicitly and correctly states MATLAB-vs-OC drift; otherwise `ROW_WRONG`.
  - Why: enforced by required verdict precedence.
- D3: OC behavior baseline for allocator engagement.
  - Choice: treat both canonical chassis wiring and extant legacy/default bypass paths as OC behavior surfaces; mark policy-sensitive calls with `judgment=required`.
  - Why: row itself claims `oc_current: mixed` and enumerates bypass entries.

### Risks (unresolved ambiguity)
- R1: Canonical-only interpretation could undercount legacy bypass semantics that row encodes; mitigated with `judgment=required` on allocator-mode claims.
- R2: OC flat substrate store may project compartment semantics; tuple-equivalence claims can be overconfident without per-WID compartment metadata checks.
- R3: Row uses legacy anchors for some v3-era claims; semantic truth can hold while anchors drift.

## Header Block
- Process name: `Transcription`
- Audited files:
  - `data/schemas/per_process_wiring/Transcription.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Transcription.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_transcription.py`
  - `opencell/vivarium/karr_transcription_v3.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_composite.py`
  - `opencell/m2/transcription_v2.py`
- Scope policy: strict completeness (no exemplar exception) for explicit Transcription consume/produce substrate surfaces.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| TRN-S1-01 | S1 | `consume_stoichiometry` lists ATP/CTP/GTP/UTP/H2O (`Transcription.yaml:168-223`). | NTPs consumed via `polymerize(...)` (`Transcription.m:895-897`); H2O consumed at termination (`Transcription.m:950`); requests include NTPs + H2O (`Transcription.m:611-614`). | OC consume surfaces exist for NTPs but not H2O. | VERIFIED | Completeness check is row-vs-MATLAB set inclusion under strict scope. |
| TRN-S2-01 | S2 | ATP/CTP/GTP/UTP consume entries have OC anchors (`Transcription.yaml:169-212`). | NTP uptake is explicit (`Transcription.m:895-897`). | v3 emits NTP deltas from `consumed_substrates` (`karr_transcription_v3.py:72,212-220`); legacy emits negative NTP deltas (`karr_transcription.py:14,475-536,658-673`). | VERIFIED | Real OC consume path exists for NTP quartet. |
| TRN-S2-02 | S2 | H2O consume entry is present and row explicitly says OC request path omits water (`Transcription.yaml:213-223,417`). | H2O consumed one-for-one with terminated RNAPs (`Transcription.m:926-951`). | Request calculator wid set derives from NTP-only `allocation_substrate_wids` (`karr_request_calculators.py:565-602`, `karr_transcription_v3.py:28,72-73`); no H2O consume update in transcription wrappers. | CODE_DEVIATES | Row correctly captures MATLAB-vs-OC consume gap for H2O. |
| TRN-S3-01 | S3 | `produce_stoichiometry` lists PPI and H (`Transcription.yaml:224-246`). | Diphosphate produced as `+sum(usedNTPs)` (`Transcription.m:962-964`); hydrogen produced `+nTrmPols` (`Transcription.m:950-951`). | OC wrappers do not emit these products. | VERIFIED | Completeness pass: MATLAB produce set appears in row. |
| TRN-S3-02 | S3 | PPI row entry points to legacy OC next_update as produce anchor (`Transcription.yaml:225-235`). | PPI production is explicit (`Transcription.m:962-964`). | OC substrate updates are constrained to NTP `consumed_substrates` only (`karr_transcription.py:14,475-536`; `karr_transcription_v3.py:28,72,218-220`). | ROW_WRONG | Row PPI fabrication anchor does not correspond to real OC PPI emission; judgment=required (anchor note says "corresponds" but not direct product write). |
| TRN-S3-03 | S3 | H row note says MATLAB-only product in current OC port (`Transcription.yaml:236-246`). | Hydrogen produced during termination (`Transcription.m:950-951`). | No hydrogen key in transcription consumed/emitted substrate sets (`karr_transcription.py:14,475-536`; `karr_transcription_v3.py:28,72,218-220`). | CODE_DEVIATES | Row correctly states this divergence. |
| TRN-S4-01 | S4 | Request formulas differ: MATLAB composition-weighted NTP demand + H2O vs OC `total_nt/4*dt` and no water (`Transcription.yaml:130-133`). | `2 * sum(nmpComposition,2) * nActive * elongRate` for NTPs; `H2O=nActive` (`Transcription.m:611-614`). | `per_ntp_need = total_nt / 4 * dt`; requests only NTP wid list (`karr_request_calculators.py:565-602`; `karr_transcription_v3.py:146-151`). | CODE_DEVIATES | Formula-family mismatch captured correctly by row (uptake/request family). |
| TRN-S4-02 | S4 | Row includes H2O/H termination stoichiometry (`Transcription.yaml:213-246`). | Termination hydrolysis branch clips by available H2O before applying `H2O--, H++` (`Transcription.m:926-951`); PPi byproduct added (`Transcription.m:962-964`). | OC clipping is allocator-budget `min(per_ntp_need,budget)` on NTPs only (`karr_transcription_v3.py:159-167`); no H2O/H/PPi branch. | CODE_DEVIATES | Concrete formula families audited: hydrolysis + clipping/bounds transform. |
| TRN-S5-01 | S5 | Row routes NTP consumption to cytosol with `mismatch: false` (`Transcription.yaml:248-267`). | MATLAB addresses substrate-compartment indices (`Transcription.m:251-257`; `Simulation/evolveState.m:63-70`). | OC routes NTPs through flat shared `substrates` store (`karr_transcription_v3.py:104-111,218-222`; `karr_composite.py:1991-1995`). | VERIFIED | Effective tuple match for NTPs, but OC is projected to flat store; judgment=required. |
| TRN-S5-02 | S5 | Row marks H2O/PPI/H routing as `mismatch: false` and cytosolic (`Transcription.yaml:268-282`). | MATLAB mutates H2O/H/PPI substrate indices (`Transcription.m:950-951,962-964`, index defs `Transcription.m:255-257`). | OC transcription updates do not carry H2O/PPI/H keys (`karr_transcription.py:14,475-536`; `karr_transcription_v3.py:28,72,218-220`). | ROW_WRONG | Row routing agreement claim is false for these species. |
| TRN-S6-01 | S6 | Row says MATLAB allocation mode and OC allocation-aware path exists (`Transcription.yaml:126-133`, methods `14-34`). | MATLAB always computes requests then injects per-process allocation before `mod.evolveState()` (`Simulation/evolveState.m:24-37,63-70`). | Canonical chassis instantiates `RequestCalculatorTranscription`, wires allocator flow, and constructs transcription v3 with `use_allocator_budget=True` (`karr_composite.py:738-744,787,2329,2345-2355`). | VERIFIED | Allocator-coupled engagement matches on canonical path. |
| TRN-S6-02 | S6 | Row claims OC mode is mixed and lists bypasses (`Transcription.yaml:128-129,151-167,419`). | MATLAB process execution is allocation-mediated (no direct-substrate bypass branch) (`Simulation/evolveState.m:63-73`). | Legacy wrapper writes direct substrate deltas (`karr_transcription.py:658-674`); v3 default parameter allows bypass when not allocator-wired (`karr_transcription_v3.py:47,212-220`). | VERIFIED | Mixed-mode attribution depends on whether "OC current" means canonical chassis only; judgment=required. |
| TRN-S6-03 | S6 | Row says Transcription has no special ordering rule; only tRNA<Translation hard gate exists globally (`Transcription.yaml:304-309`). | MATLAB order gate constrains only tRNA aminoacylation before translation (`Simulation/evolveState.m:48-57`). | OC flow enforces request calculators before allocation step, with no transcription-specific process-order edge (`karr_composite.py:2335-2358`). | VERIFIED | Allocator-coupled ordering claim holds at stated granularity; judgment=required (Vivarium process iteration order not random-permute MATLAB equivalent). |

VERIFIED: 7
ROW_WRONG: 2
CODE_DEVIATES: 4
MISSING: 0

Priority-1 fixes:
- TRN-S3-02 (`ROW_WRONG`): correct/remove PPI OC fabrication anchor; point to real OC behavior (currently no PPI emission).
- TRN-S5-02 (`ROW_WRONG`): change H2O/PPI/H `compartment_routing` mismatch flags to reflect current OC non-emission/non-consumption in Transcription.

Known-deviation mapping (row `deviations.known_deviations` -> claims):
- KD1 (OC omits H2O request) -> TRN-S2-02, TRN-S4-01, TRN-S4-02
- KD2 (OC mechanism wrapper vs MATLAB RNAP state machine) -> TRN-S4-01, TRN-S4-02
- KD3 (legacy bypass direct deltas) -> TRN-S6-02

Auditor discretion list (`judgment=required`):
- TRN-S3-02
- TRN-S5-01
- TRN-S6-02
- TRN-S6-03
