# ProteinDecay Semantic Audit

## Header
- Process name: `ProteinDecay` (`protein_decay`)
- Audited files:
  - `data/schemas/per_process_wiring/ProteinDecay.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinDecay.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_protein_decay_light.py`
  - `opencell/vivarium/karr_request_calculators.py`
  - `opencell/vivarium/karr_allocation_step.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: **strict completeness** (MATLAB consume/produce sets must be represented explicitly in row stoichiometry lists; subset prose does not waive list completeness unless the list itself is explicitly exemplar-scoped).

## DELIBERATE_ACTION_PREFIX_v2
- Beat 1 (contract): verify/falsify row semantic truth against executable MATLAB and OC behavior for S1-S6, not anchor presence.
- Beat 2 (surface): row stoichiometry/allocator/compartment/order blocks in `ProteinDecay.yaml`; MATLAB `calcResourceRequirements_Current`, `evolveState_*`, and simulation allocator loop; OC `RequestCalculatorPD`, `ProteinDecayLightProcess.next_update`, allocation step, and composite flow/topology.
- Beat 3 (expected outcome): deterministic claim table with allowed verdicts only (`VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, `MISSING`) and reproducible totals.
- Beat 4 (invert): this audit could look complete while being wrong if dormant OC branches (latent monomer replay) are treated as active fabrication and if request-path wiring is mistaken for actual allocator-coupled consumption.
- Beat 5 (act/verify): line-level evidence captured below plus runtime probes using `bin\\oc-py` (`tmp/_pd_probe.py`, `tmp/_pd_consumed_sets.py`, `tmp/_pd_produced_sets.py`, `tmp/_pd_oc_active_stoich.py`) to confirm latent-branch activation and fixture-derived consume/produce sets.
- PM sanity-check sentence: **PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.**

## Revision-Class Minimum
- Design contract sentence: semantic truth here is that each row claim must either match MATLAB and OC behavior for the stated scope, or be explicitly labeled as omission/row error/code divergence with reproducible evidence.

### Decision ledger
- D1. Scope attribution for S1/S3 completeness.
  - Decision: strict completeness.
  - Why: `consume_stoichiometry` / `produce_stoichiometry` blocks are written as concrete lists without explicit exemplar markers, so omissions are attributable as row gaps.
- D2. Dormant OC branch attribution (latent monomer helper).
  - Decision: dormant-by-default branch does **not** satisfy fabrication for default semantic wiring.
  - Why: `_latent_enabled` is disabled by shape checks in constructor (`karr_protein_decay_light.py:209-217`) and runtime probe confirms `False`.
- D3. Allocator-order claim placement.
  - Decision: include request-calculator -> allocator flow as S6 ordering-coupled evidence.
  - Why: ProteinDecay allocator semantics depend on request step timing (`karr_composite.py:936-947`) even though process-local `ordering_constraints` is empty.

## Claim Table
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| PD-S1-01 | S1 | `consume_stoichiometry` lists only ATP/H2O/H (`ProteinDecay.yaml:147-179`). | Current requirements consume ATP/H2O plus matrix-negative decay terms (`ProteinDecay.m:505-527`, `355-375`). | OC update is matrix-driven over full substrate vector (`karr_protein_decay_light.py:528-556`). | MISSING | Strict completeness: row omits consumed substrates beyond ATP/H2O/H (probe `bin\\oc-py tmp/_pd_consumed_sets.py` reported union consumed `AMP,H,H2O,PAP,PPI`). |
| PD-S2-01 | S2 | ATP/H2O consume entries map to OC request path (`ProteinDecay.yaml:148-169`). | ATP/H2O are consumed in current requirements (`ProteinDecay.m:494-502`, `511-527`). | `RequestCalculatorPD` emits ATP/H2O requests (`karr_request_calculators.py:122-160`), wired before allocator (`karr_composite.py:927`, `941-947`). | VERIFIED | Real OC consume-request path exists (allocator bypass of actual debit handled in S6). |
| PD-S2-02 | S2 | H consume is represented as direct complex-decay projection (`ProteinDecay.yaml:170-179`). | Modified-complex decay checks/uses `max(0,-complexDecayReactions)` before consuming substrates (`ProteinDecay.m:718-733`). | OC clips to positive-only substrate deltas when ATP/H2O demand is zero (`karr_protein_decay_light.py:548-566`), so negative H deltas can be suppressed. | ROW_WRONG | `judgment=required` (sign-dependent, gate-dependent consume behavior is stronger-constrained than row text). |
| PD-S3-01 | S3 | `produce_stoichiometry` lists ADP/PI/ALA/GLY/MET (`ProteinDecay.yaml:181-236`). | Produce side includes refolding byproducts and matrix-positive complex/monomer outputs (`ProteinDecay.m:433-435`, `439`, `443`, `453-454`, `753`, `911-914`). | OC substrate updates are matrix-projected over full substrate WID list (`karr_protein_decay_light.py:528-556`). | MISSING | Strict completeness: row omits many MATLAB-produced substrates (probe `bin\\oc-py tmp/_pd_produced_sets.py` reported 45 produced WIDs). |
| PD-S3-02 | S3 | ALA/GLY/MET OC anchors point to latent monomer helper (`ProteinDecay.yaml:204-236`). | MATLAB produces amino-acid outputs from aborted-polypeptide and monomer decay (`ProteinDecay.m:828-829`, `908-914`). | Latent helper requires `_latent_enabled` and `monomers` state (`karr_protein_decay_light.py:299-305`), but constructor disables latent mode on shape mismatch (`209-217`). | ROW_WRONG | `judgment=required` (default runtime fabrication is absent; replay-only/dormant path does not provide active parity). |
| PD-S4-01 | S4 | Row explicitly states OC request formula is narrower than MATLAB (`ProteinDecay.yaml:106-116`). | MATLAB request formula includes refolding + complex + monomer + aborted-polypeptide terms (`ProteinDecay.m:494-527`). | OC request formula is `abs(stoich_row @ expected_decays)` for ATP/H2O from complex decay only (`karr_request_calculators.py:133-150`, `153-160`). | CODE_DEVIATES | Row correctly captures formula-family divergence. |
| PD-S4-02 | S4 | H consume formula is presented as shared projection family (`ProteinDecay.yaml:172-179`). | MATLAB complex decay uses `stochasticRound` + substrate-gated while-loop and full stoich writeback (`ProteinDecay.m:687-733`, `751-753`). | OC uses Poisson decays + matrix multiply, then positive-only clipping branch (`karr_protein_decay_light.py:525-566`). | ROW_WRONG | `judgment=required` (not mathematically equivalent modulo syntax due clipping behavior). |
| PD-S5-01 | S5 | Compartment routing marks listed metabolites as cytosol with `mismatch: false` (`ProteinDecay.yaml:237-277`). | MATLAB explicitly uses cytosol + terminal-organelle cytosol compartment axes (`ProteinDecay.m:491-492`, `609`, `683-690`, `846-853`). | OC substrate store is flat per-WID (no compartment axis) and writes merged deltas (`karr_protein_decay_light.py:243-246`, `528-583`). | ROW_WRONG | Row also flags merge behavior (`ProteinDecay.yaml:433`), which conflicts with `mismatch: false` routing rows. |
| PD-S6-01 | S6 | Row states MATLAB allocation mode vs OC bypass mode (`ProteinDecay.yaml:102-105`, `435-437`). | Simulation injects per-process allocations before `mod.evolveState()` (`evolveState.m:63-70`). | Allocator exists (`karr_allocation_step.py:210-280`) and PD request is wired (`karr_composite.py:927`, `941-947`), but process reads `states['substrates']` and does not read `substrates_allocated` (`karr_protein_decay_light.py:281-287`, `502-588`; schema-only declaration `265-270`). | CODE_DEVIATES | Row correctly describes MATLAB-vs-OC allocator engagement divergence. |
| PD-S6-02 | S6 | `ordering_constraints` has no hard/soft edges (`ProteinDecay.yaml:302-306`). | MATLAB has only global tRNA-before-Translation hard constraint in this loop (`evolveState.m:48-55`). | OC wiring introduces allocator-coupled order for this process (`request_calculator_pd` must precede `karr_allocation_step`) (`karr_composite.py:936-947`). | MISSING | `judgment=required` (schema may need explicit step-flow ordering claim for allocator-coupled semantics). |

## Aggregate Counts
- VERIFIED: 1
- ROW_WRONG: 4
- CODE_DEVIATES: 2
- MISSING: 3

## Priority-1 Fixes
- PD-S1-01 (`MISSING`): extend `consume_stoichiometry` to cover full MATLAB consume set or explicitly mark exemplar scope at list level.
- PD-S2-02 (`ROW_WRONG`): qualify H consume claim with OC clipping gate semantics.
- PD-S3-01 (`MISSING`): extend `produce_stoichiometry` to full MATLAB produce set or explicitly mark exemplar scope at list level.
- PD-S3-02 (`ROW_WRONG`): correct ALA/GLY/MET OC fabrication statement to reflect latent path disabled-by-default behavior.
- PD-S4-02 (`ROW_WRONG`): correct formula-equivalence language for complex-decay consume path (Poisson/clipping vs MATLAB stochasticRound/while-loop).
- PD-S5-01 (`ROW_WRONG`): reconcile `compartment_routing` `mismatch: false` entries with explicit compartment merge deviation.
- PD-S6-02 (`MISSING`): add allocator-coupled ordering claim (or explicitly declare why step-order semantics are out of scope).

## Known-Deviation Mapping (optional)
- D-A (light subset vs full MATLAB): PD-S4-01, PD-S6-01
- D-B (allocator bypass despite request wiring): PD-S6-01, PD-S6-02
- D-C (compartment projection/merge): PD-S5-01
- D-D (latent monomer path disabled by default): PD-S3-02

## Auditor Discretion List
- PD-S2-02 (`judgment=required`)
- PD-S3-02 (`judgment=required`)
- PD-S4-02 (`judgment=required`)
- PD-S6-02 (`judgment=required`)

## Risks
- R1: Scope-policy ambiguity (strict vs exemplar) remains a comparability risk across process audits if list-level exemplar markers are not standardized.
- R2: Fixture-dependent active stoichiometry (e.g., filtered complex set) can change nonzero consume/produce realizations without code edits.
- R3: Allocator step-flow semantics may not be uniformly represented in `ordering_constraints`, risking under-specified S6 ordering claims.
