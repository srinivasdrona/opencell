# KP20 Regression Investigation

## KP20 spec recap
KP20 (`extract_kp20`) computes the mean absolute `log10(latest_metabolite_pool / baseline_metabolite_pool)` across emitted `state.metabolite_pools` entries with positive baseline and current values, and fails `threshold_max` when this mean exceeds `1.0`.

## Pre-fix vs wave-2 observed values
| Baseline | Seed | KP20 observed |
|---|---:|---:|
| Pre-fix (`E2_scorecard_post_strip.md`) | ee52141 | 0.0239602 |
| Wave-2 (`ensemble_wave2_20260527_023611`) | 42 | 3.0513607 |
| Wave-2 (`ensemble_wave2_20260527_023611`) | 43 | 3.0787977 |
| Wave-2 (`ensemble_wave2_20260527_023611`) | 44 | 3.1943074 |
| Wave-2 (`ensemble_wave2_20260527_023611`) | 45 | 3.0855180 |

## Metabolite under threshold violation
KP20 is a whole-pool aggregate (mean over metabolites), not a single-metabolite threshold. At `t=32400 s`, 22/27 metabolites have `abs(log10(final/baseline)) > 1` in all four seeds:

- `AA_ALA`, `AA_ARG`, `AA_ASN`, `AA_ASP`, `AA_CYS`, `AA_GLN`, `AA_GLU`, `AA_GLY`, `AA_HIS`, `AA_ILE`, `AA_LEU`, `AA_LYS`, `AA_MET`, `AA_PHE`, `AA_PRO`, `AA_SER`, `AA_THR`, `AA_TRP`, `AA_TYR`, `AA_VAL`, `ATP`, `GTP`

The amino-acid pools are the dominant deterministic driver (all 20 AAs collapse to exactly `1.0`), with `GTP` also collapsing strongly; `ATP` adds seed-dependent late severity.

Metabolites that did **not** cross >10x: `DATP`, `DCTP`, `DGTP`, `DTTP`, `dNTP_total`.

## Trajectory shape
Using `key_substrates.csv` (1 s resolution) per seed:

- KP20 crosses `>1.0` at about `t=166 s` in all seeds.
- Shape is effectively monotonic increasing (seed 43 has one single-tick dip); no spike-and-recover pattern.
- Representative seed-43 checkpoints: `t=100: 0.350`, `t=150: 0.649`, `t=200: 1.845`, `t=500: 2.746`, `t=32400: 3.079`.
- Amino-acid pools hit floor `1.0` between `t=99 s` and `t=571 s` and stay pinned there for the rest of the run.
- `GTP` crosses >10x around `t=904..941 s` and ends at `0.555..0.909`.
- `ATP` crosses >10x only late (`t=27402..32352 s`), with seed-44 collapsing to `0.614` by end.

## Seed-44 cross-correlation
KP20 regression is **not** seed-44-only:

- All four seeds fail (`3.051..3.194` vs threshold `1.0`).
- The same 22 metabolites exceed >10x in every seed.
- If energy carriers are removed from the aggregate, the mean over non-ATP/GTP metabolites is still `~3.071` in all seeds and still crosses near `t=166 s`.

Seed-44 is worse because ATP collapses much harder late-run (`abslog10 ATP=4.771` vs `1.004/1.536/1.797` in seeds 42/43/45), but the core KP20 failure is deterministic across seeds.

## Suspected wave-2 commit(s)
1. `9a677b7` (`A6: enroll ProteinTranslocation in allocator (v3/v4)`)
- Also wires v5 path used by v6 and adds `RequestCalculatorPTransloc` in `karr_request_calculators.py`, where ATP/GTP/H2O requests are `max(need, current_pool)`; seed-43 traces show near-full ATP/GTP requests from early ticks (for example tick 10: ATP `36139`, GTP `35870`).

2. `82ae251` (`A4: L3 vector members for DNASupercoiling + ProteinTranslocation`)
- Expands allocator vector completeness (`ATP/GTP/ADP/GDP/PI/H2O/H` for translocation), increasing energy-coupled allocation competition scope.

3. `b2863dc` (`A3: key normalization + zero-demand writeback guard`)
- Normalizes and merges request keys in `karr_allocation_step`; any previously dropped alias demand is now counted, which can increase effective substrate pressure.

I cannot isolate a single culprit commit from trajectory-only evidence; these likely interact.

## Hypothesis
Wave-2 allocator/request-path changes increased early shared-substrate pressure (especially energy-coupled demand), and AA pools are rapidly driven to the `1.0` floor while `GTP` continues collapsing, pushing the KP20 mean far above threshold by ~166 s in every seed. Seed-44's ATP crash further amplifies KP20 but is not required for failure.

## Recommended fix path
**Fix producing process** (recommended): audit and cap allocator request generation rather than changing KP20 threshold or extractor. First target is `RequestCalculatorPTransloc` request magnitude semantics (`max(need, current_pool)`), then verify allocation fairness/normalization effects so AA pools are no longer pinned at `1.0` across all seeds.

## Open questions
- Is AA pool floor-at-`1.0` an intentional numerical guardrail or an unintended allocator artifact?
- Should v6 KP20 be evaluated on full 1 s substrate series or only scorecard snapshot stride (`trajectory.pkl` at 100 s cadence)?
- Which exact request producer contributes the largest AA depletion share in the first 600 s (needs targeted per-process ablation or request-ledger instrumentation)?
