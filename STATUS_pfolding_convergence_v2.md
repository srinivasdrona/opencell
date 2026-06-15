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

Pending run.

## Verdict

Pending.

## Recommendation

Pending.
