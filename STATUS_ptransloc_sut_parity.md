# STATUS_ptransloc_sut_parity

## Beat 1 - source read complete
- Karr `evolveState` iterates individual cytosolic translocating monomer copies in one global random permutation over the total copy count.
- For each selected copy, Karr computes per-monomer translocase, SRP, ATP, GTP, and water costs, then `break`s on the first insufficient-resource check.
- OC `next_update` permutes species lists, splits execution into SRP and direct phases, and bulk-translocates as many copies of each species as current minima allow.
- OC reads ATP/GTP/H2O from `substrates_allocated` and enzyme availability from raw count stores, rather than Karr's rate-scaled `translocases` / `SRPs` capacities.
- Early read verdict: the two implementations are not line-by-line equivalent; the audit needs to document several structural divergences, not just input-scaling differences.

## Beat 2 - audit authored
- Wrote `docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md` with algorithm summaries, a line-ranged mapping table, RNG inventory, substrate-insufficiency trace, overall verdict, and regime-label recommendation.
- Current verdict: `DIVERGENT_DOCUMENTED`.
