# RNADecay Semantic Audit (L1b)

## Header
- Process name: `RNADecay` (`rna_decay`)
- Audited files:
  - `data/schemas/per_process_wiring/RNADecay.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNADecay.m`
  - `docs/karr_extracts/process/13_RNADecay.md`
  - `docs/karr_extracts/architecture/03_variable_allocation.md`
  - `docs/karr_extracts/architecture/01_simulation_loop.md`
  - `docs/design/allocation_consumer_enrollment.md`
  - `opencell/vivarium/karr_rna_decay.py`
  - `opencell/vivarium/karr_allocation_step.py`
  - `opencell/vivarium/karr_composite.py`
  - `tests/vivarium/test_karr_rna_decay.py`
- Scope policy: `strict completeness` (row does not declare exemplar/non-exhaustive consume/produce scope)
- Header note: full audit (not `PARTIAL`)

## Deliberate Action Prefix (v2)
- Beat 1 (contract): classify RNADecay S1-S6 row claims against executable MATLAB and OC semantics, not anchor presence alone.
- Beat 2 (surface): row (`RNADecay.yaml`); MATLAB (`RNADecay.m`, allocation/simulation-loop extracts); OC (`karr_rna_decay.py`, `karr_allocation_step.py`, `karr_composite.py`, `test_karr_rna_decay.py`). Suspect pattern: row relies on extract-era assumptions (`raw MATLAB absent`) while raw `.m` is present and has richer formulas.
- Beat 3 (expected outcome): one deterministic claim table with only `VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`, plus aggregate counts and Priority-1 remediation.
- Beat 4 (invert / pre-mortem): false-pass risk is treating `requests`/`substrates_allocated` wiring as proof of allocator equivalence while missing request-formula and same-tick ordering differences.
- Beat 5 (act then verify): each claim below cites concrete MATLAB/OC execution branches (conditions, formulas, write paths) and row anchors.
- PM sanity-check sentence: **PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.**

## Revision-Class Minimum
Design contract sentence:
- Semantic truth checked: RNADecay row consume/produce/formula/compartment/allocator statements must match MATLAB behavior and OC behavior claim-by-claim.

Decision ledger (non-obvious attribution calls):
1. D1 (S3 completeness source of truth)
- Chosen: use strict set-completeness against executable stoichiometry (`decayReactions`) and fixture-derived substrate set.
- Why: row has no exemplar qualifier; `produce_stoichiometry` therefore reads as complete.
2. D2 (S5 projection/merge attribution)
- Chosen: classify `shared_pool_projection_merges_compartments: false` as row-risk because OC substrate routing is flat WID-only.
- Why: MATLAB allocation/writeback is compartment-indexed; OC process port lacks compartment dimension.
3. D3 (S6 ordering-coupled allocator semantics)
- Chosen: mark missing timing-equivalence claim as `MISSING` with `judgment=required`.
- Why: MATLAB has explicit `requirements -> allocations -> evolveState`; OC RNADecay emits requests inline in process and is not in request-calculator flow edges.

Risks (unresolved ambiguity):
- R1: exact process-vs-step tick scheduling details in Vivarium can affect same-tick vs next-tick request/grant interpretation.
- R2: practical impact of flat substrate representation depends on whether any RNADecay-relevant WIDs appear in multiple compartments in runtime state.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| RNADECAY-S1-01 | S1 | Consume set is `H2O` only (`RNADecay.yaml:121-133`). | RNADecay algorithm states only reactant is water (`13_RNADecay.md:85-87`); fixture-derived decay stoich consume set is `H2O` (`allocation_consumer_enrollment.md:14-19`). | OC consume stoich is fixture-driven and water need vector is `max(0, -decay_reactions[:, H2O])` (`karr_rna_decay.py:165-167`). | VERIFIED | Strict consume completeness holds. |
| RNADECAY-S2-01 | S2 | Row consume entry `H2O@cytosol` maps to OC water-gate path (`RNADecay.yaml:122-132`). | MATLAB gates decay by available water before accepting events (`RNADecay.m:354-365`) then applies stoich to substrates (`RNADecay.m:373`). | OC gates by `_available_water()` (`karr_rna_decay.py:355-368`, `443-450`) and writes `substrates` deltas from stoich (`karr_rna_decay.py:379-387`). | VERIFIED | Real OC consume path exists; no fabricated consume entry. |
| RNADECAY-S3-01 | S3 | Row produce set lists only `ALA, AMP, CMP, GMP, UMP` (`RNADecay.yaml:134-194`). | MATLAB emits full decay stoich product vector via `this.decayReactions' * decayingRNAs` (`RNADecay.m:373`), with broad substrate universe initialized (`RNADecay.m:173-180,195-209`); fixture evidence shows 36 produced WIDs (`allocation_consumer_enrollment.md:16-20`). | OC emits products for all nonzero stoich columns (`karr_rna_decay.py:380-385`) over fixture substrate list (`karr_rna_decay.py:130,151-154`). | MISSING | Row omits many produced WIDs under strict policy. |
| RNADECAY-S3-02 | S3 | Each listed row produce WID is emitted from decay stoichiometry (`RNADecay.yaml:135-194`). | Listed WIDs are members of MATLAB decay product space (`RNADecay.m:173-180,195-209,373`). | OC produce path is generic `decay_events @ decay_reactions` then per-WID update (`karr_rna_decay.py:380-387`). | VERIFIED | Produce fabrication passes for row-listed entries. |
| RNADECAY-S4-01 | S4 | Row claims stochastic decay loop parity (`RNADecay.yaml:43-65`). | MATLAB samples `poisson(RNAs .* min(1e6, decayRates*stepSizeSec))` then clips by counts (`RNADecay.m:330-333`). | OC computes `expected = min(1e6, decay_rates_per_s*dt) * rna_counts`, samples Poisson, then clips (`karr_rna_decay.py:322-325,420-441`). | VERIFIED | Poisson/clip formula family matches modulo syntax and sampler implementation. `judgment=required`. |
| RNADECAY-S4-02 | S4 | Row implies aminoacylated peptidyl-hydrolase gating parity in evolve flow (`RNADecay.yaml:43-65`). | MATLAB computes hydrolase capacity via stochastic round and enforces weighted aminoacylated gating loop (`RNADecay.m:303-307,337-350`). | OC computes stochastic-rounded capacity and weighted gating over aminoacylated indices (`karr_rna_decay.py:316,341-353,452-473`). | VERIFIED | Gating formula family matches. |
| RNADECAY-S4-03 | S4 | Row request formula says MATLAB `lambda = RNAs .* decayRates * stepSizeSec; H2O_request = waterNeedPerDecay' * lambda` (`RNADecay.yaml:88-94`). | MATLAB request is `max(0, -decayReactions' * (min(1, decayRates) .* RNAs))` with extra aborted-transcript water add (`RNADecay.m:288-293`). | OC request is `dot(water_need_per_decay, sampled_decay)` from stochastic sampled decay (`karr_rna_decay.py:323-333`). | ROW_WRONG | Row MATLAB formula attribution is not the executable `calcResourceRequirements_Current` expression. |
| RNADECAY-S5-01 | S5 | Row routes `H2O` consume and listed products to cytosol (`RNADecay.yaml:195-225`). | MATLAB RNA state is explicitly cytosol-indexed (`RNADecay.m:216,223,375,379`) and substrate writeback occurs through process substrate mapping (`RNADecay.m:373`; simulation mapping in `01_simulation_loop.md:187-197`). | OC writes flat per-WID substrate deltas (no compartment key) via shared `substrates` store (`karr_rna_decay.py:246-249,379-387`; `karr_composite.py:2443-2447`). | VERIFIED | Tuple parity for this process appears consistent with cytosol-only behavior, but OC representation is flattened. `judgment=required`. |
| RNADECAY-S5-02 | S5 | Row states `shared_pool_projection_merges_compartments: false` (`RNADecay.yaml:331`). | MATLAB allocator/writeback uses global-compartment indices (`01_simulation_loop.md:156-157,187-197`). | OC substrate routing is WID-only (`karr_rna_decay.py:246-249,379-387`) so compartment identity is projected away at process boundary. | ROW_WRONG | Row underreports projection/merge risk from flat OC substrate representation. `judgment=required`. |
| RNADECAY-S6-01 | S6 | Row allocator mode is `allocation` on both sides with H2O request/grant path (`RNADecay.yaml:84-99`). | MATLAB collects per-process requests then fair-share allocations before process evolve (`03_variable_allocation.md:10-24`; `01_simulation_loop.md:148-161,184-197`); RNADecay request method exists (`RNADecay.m:282-294`). | OC exposes `requests` and `substrates_allocated` ports (`karr_rna_decay.py:250-259`), is enrolled as H2O consumer in allocation step (`karr_allocation_step.py:70-76` and `karr_composite.py:2468-2475`), and reads allocated water first (`karr_rna_decay.py:443-447`). | VERIFIED | Allocator engagement mode matches (with OC fallback branch if allocation store absent). |
| RNADECAY-S6-02 | S6 | Row says OC folds request emission into `next_update` instead of dedicated request calculator (`RNADecay.yaml:37,333`). | MATLAB uses dedicated `calcResourceRequirements_Current` method (`RNADecay.m:282-294`). | OC emits request inline in `next_update` (`karr_rna_decay.py:327-334`) and tests assert request emission from process tick (`test_karr_rna_decay.py:82,98`). | CODE_DEVIATES | Row correctly describes this MATLAB-vs-OC structural semantic divergence. |
| RNADECAY-S6-03 | S6 | Row has no explicit allocator-coupled timing equivalence claim (ordering section is empty/no RNADecay-specific rule) (`RNADecay.yaml:249-257`). | MATLAB timing is explicit same-tick `calcResourceRequirements_Current -> allocations -> evolveState` (`01_simulation_loop.md:148-161,184-197`). | OC RNADecay requests are process-emitted (`karr_rna_decay.py:327-334`), while allocation step flow depends on request calculators, not RNADecay (`karr_composite.py:2335-2356,2441-2447`). | MISSING | Add explicit row claim for allocator-coupled ordering semantics. `judgment=required`. |

Aggregate counts:
- VERIFIED: 7
- ROW_WRONG: 2
- CODE_DEVIATES: 1
- MISSING: 2

Priority-1 fixes:
- `RNADECAY-S3-01` (`MISSING`): expand `produce_stoichiometry` to full MATLAB/fixture byproduct set (or explicitly declare exemplar scope policy).
- `RNADECAY-S4-03` (`ROW_WRONG`): correct MATLAB request formula attribution to executable `calcResourceRequirements_Current` expression (including aborted-transcript water term).
- `RNADECAY-S5-02` (`ROW_WRONG`): revise projection/merge statement to reflect OC flat substrate representation and its compartment implications.
- `RNADECAY-S6-03` (`MISSING`): add explicit allocator-coupled timing claim (same-tick vs staged behavior) with clear MATLAB/OC anchors.

Known-deviation mapping:
- KD1 (inline OC request emission vs dedicated MATLAB request method): `RNADECAY-S6-02`.

Auditor discretion list (`judgment=required`):
- `RNADECAY-S4-01`
- `RNADECAY-S5-01`
- `RNADECAY-S5-02`
- `RNADECAY-S6-03`

## Verification (Beat 5)
- Expected (Beat 3): complete S1-S6 claim table with constrained verdict vocabulary and reproducible claim-level attributions.
- Actual: 12 claims delivered across S1-S6 with only `VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`, plus aggregate counts and Priority-1 list.
- Beat-4 inversion check: allocator equivalence was not inferred from port names alone; request formulas and request/allocation ordering surfaces were separately audited.
- Verdict: matched.
