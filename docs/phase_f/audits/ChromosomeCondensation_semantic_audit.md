# ChromosomeCondensation Semantic Audit

Process: `ChromosomeCondensation`
Authority: primary `ChromosomeCondensation.m` plus current
`karr_chromosome_condensation.py` and chassis-v6 topology.
Scope: strict documentation completeness; verdicts distinguish row defects from
implementation deviations.

## Classification correction

ChromosomeCondensation is **stochastic**, not deterministic. MATLAB calls
`bindProteinToChromosomeStochastically` (`ChromosomeCondensation.m:266-268`).
OC's literal-chromosome path makes explicit weighted region and position draws
through `ChromCondMcgRandStream`
(`karr_chromosome_condensation.py:1219-1258`). This process therefore requires
stochastic/distributional fidelity evidence; stochasticity is not itself a
deviation.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| CC-S1-01 | S1 | ATP and H2O are the complete consumed-substrate set; MATLAB decrements only those species (`ChromosomeCondensation.m:273-281`) and OC does the same (`karr_chromosome_condensation.py:786-800`). | VERIFIED |
| CC-S2-01 | S2 | The listed consume paths are executable and gated by the number actually bound, not merely requested. | VERIFIED |
| CC-S3-01 | S3 | ADP from free SMC-ADP dissociation plus PI/H from ATP hydrolysis are the complete produced-substrate set (`ChromosomeCondensation.m:241-244,282-283`; OC `:779-800`). | VERIFIED |
| CC-S4-01 | S4 | Both implementations cap binding by allocated ATP, allocated H2O, and free SMC after dissociation (`ChromosomeCondensation.m:247-250`; OC `:693-696,735-746`) and apply the same count stoichiometry. | VERIFIED |
| CC-S4-02 | S4 | The row now explicitly records affinity/region-weighted stochastic binding. MATLAB invokes the stochastic chromosome-binding helper; OC draws a weighted region and a random position with an explicit MCG stream (`karr_chromosome_condensation.py:1244-1252`). | VERIFIED |
| CC-S4-03 | S4 | The row discloses that OC also retains aggregate `smc_bound_count`/`condensation_level`, a trace-hint override, and a non-literal fallback (`karr_chromosome_condensation.py:646-689,741-760,856-861`). These are not MATLAB state/behavior. | CODE_DEVIATES |
| CC-S5-01 | S5 | MATLAB substrate writeback is compartment-indexed, while OC exposes a flat per-WID shared substrate surface. All five process substrates are cytosolic-only, so this merge is an accepted-equivalent projection for ChromosomeCondensation. | VERIFIED |
| CC-S6-01 | S6 | ATP/H2O grants are allocated-only in OC (`karr_chromosome_condensation.py:693-696`); the prior “fallback to global substrates” statement is absent. | VERIFIED |
| CC-S6-02 | S6 | MATLAB orders request → allocation → evolve in one tick. Empirical Vivarium probing shows OC's tick-1 request reaches allocation (`request=5`, `allocation=10`), but the process already observed `substrates_allocated=0`; it observes that grant only on tick 2 (`10`). This is a one-tick request-to-consumption lag, not a failure to reach the allocator. | CODE_DEVIATES |
| CC-S6-03 | S6 | MATLAB initializes with 20 stochastic warm-up calls under infinite ATP/H2O (`ChromosomeCondensation.m:220-230`); OC initializes from fixture/trace-derived state and seeded streams (`karr_chromosome_condensation.py:465-473`). | CODE_DEVIATES |
| CC-S6-04 | S6 | Chassis v5/v6 maps `enzymes` to canonical `complex.counts` and `boundEnzymes` to the existing root store, seeds free SMC/SMC-ADP/bound SMC-ADP from fixture/trace values, and rejects incompatible duplicate seeds (`karr_composite.py:139-183,2173-2178,2317-2323,2684-2688`). | VERIFIED |

## Aggregate counts

- VERIFIED: 8
- ROW_WRONG: 0
- CODE_DEVIATES: 3
- MISSING: 0

## Open implementation deviations

- Aggregate/fallback/trace-hint behavior outside the literal stochastic path.
- One-tick request-to-consumption lag: the allocation Step sees the request
  after the process has already read the prior grant.
- Initialization differs from MATLAB's 20-step stochastic warm-up.

## Iteration-1 integration status

- Live free/bound SMC wiring is resolved and independently reviewed.
- A real Engine stress canary derives the minimum fair-share request from one
  post-tick snapshot, receives a real allocator grant, binds SMC, and conserves
  free/bound counts and hydrolysis.
- The exact default source seed remains allocator-starved by unrelated request
  competition, and same-tick request consumption remains absent. Both are
  retained as strict diagnostics and are not counted as Iteration-1 repairs.

## Documentation corrections completed

- Removed the deterministic implication.
- Removed stale mixed/global-substrate fallback wording.
- Separated source-faithful stochastic binding from the five remaining
  implementation/integration deviations.
