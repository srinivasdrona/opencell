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

Pending.

## Recommendation

Pending.
