# ProteinFolding Convergence v2

## Design Summary
- v1 compared two OpenCell `KarrProteinFoldingProcess` instances with different RNG seeds, so it only tested OC-vs-OC consistency.
- The v1 "reference" was not Karr; it was the same Python port seeded with `REF_SEED_OFFSET`.
- v2 keeps the v1 state-building and `next_update` plumbing but removes the second OC process entirely.
- For each `(seed, tick)`, v2 will scale Karr `states_before.substrates` by `alpha`, run OC once, and compare against Karr-recorded `states_after.foldedMonomers`.
- The `alpha=1.0` row is the harness sanity check; lower `alpha` rows determine whether the prior green was genuine or regime-bounded.

## Thresholds
- PASS iff `per_tick_W1_mean < 0.5` and `per_tick_W1_max < 2.0`.
- These are intentionally loose trend-detection thresholds for single-process folded-count vectors, not bit-identity gates.

## Results Table

Run command:
`bin\oc-py.cmd tests/vivarium/_substrate_stress/pfolding_stress_v2.py > tests/vivarium/_substrate_stress/pfolding_stress_v2_results.txt`

| alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | total_karr_events | verdict |
| --- | --- | --- | --- | --- | --- |
| 1.00 | 0.000000 | 0.000000 | 933 | 933 | PASS |
| 0.50 | 0.000000 | 0.000000 | 933 | 933 | PASS |
| 0.10 | 0.000000 | 0.000000 | 933 | 933 | PASS |
| 0.05 | 0.000000 | 0.000000 | 933 | 933 | PASS |
| 0.01 | 0.000000 | 0.000000 | 933 | 933 | PASS |

Run notes:
- `alpha=1.0` reproduces Karr's recorded `states_after.foldedMonomers` exactly on the sampled ensemble, so the corrected harness passes its sanity check.
- The substrate perturbation is real: at `alpha=0.01`, scaling changed 161 substrate entries across 134 of the 500 sampled `(seed, tick)` inputs.
- Even under that perturbation, ProteinFolding emitted the same folded-count vectors and total event count as Karr's recorded `alpha=1.0` output.

## Verdict

Case A: confirmed biology green across regimes.

Rationale:
- The corrected harness compares OC directly against Karr-recorded `states_after.foldedMonomers`, not against a second OC instance.
- The `alpha=1.0` row is exact-match green (`per_tick_W1_mean = 0.0`, `per_tick_W1_max = 0.0`), so the harness sanity check holds.
- No tested substrate scaling crossed the loose stress threshold (`mean < 0.5`, `max < 2.0`); in fact all sampled rows stayed exactly at zero.
- Because `alpha=0.01` materially changed the input substrate vectors but left the per-tick folded-count outputs unchanged, the observed convergence is not just an artifact of an un-applied perturbation.

## Recommendation

Recommend a catalog follow-up note or upgrade to `confirmed_biology_validated` for ProteinFolding's convergence-green claim, with the caveat that this v2 check sampled `N_SEEDS = 5` (`s000`-`s004`) rather than the full 50-seed ensemble.
