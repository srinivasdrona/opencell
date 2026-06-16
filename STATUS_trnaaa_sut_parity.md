# STATUS trnaaa SUT parity

## Scope

- Task: static SUT parity audit for `tRNAAminoacylation` (OC vs Karr)
- Branch: `investigate/trnaaa-sut-parity`
- Deliverables: `STATUS_trnaaa_sut_parity.md`, `docs/phase_f/sut_audits/trnaaa_oc_vs_karr.md`

## Beat 1 - Source read complete

Five-line source summary:

1. The requested local Karr source path `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/tRNAAminoacylation.m` is absent from this checkout, so Karr line citations in the audit use the canonical upstream WholeCell file at that same repo-relative path.
2. Karr `evolveState` is a greedy stochastic depletion loop: build a `[substrates; catalytic enzymes; free RNAs]` species vector, precompute permanently inactive reactions, repeatedly recompute feasible limits, sample weighted reactions, and subtract used resources.
3. OC `next_update` delegates the same core loop to `_compute_rna_fluxes`, then projects RNA-level fluxes back through `reactionModificationMatrix` and `reactionStoichiometryMatrix` to emit substrate and RNA deltas.
4. The Karr RNG surface has three draws to audit: stochastic rounding of enzyme limits, one weighted single-reaction draw, and weighted batched draws when the minimum feasible multiplicity exceeds one.
5. The main static differences are at the integration boundary, not the inner loop: OC reads `substrates_allocated[self.name]` instead of raw substrate state and adds a `max_stochastic_iterations = 50_000` safety cap.

## Beat 2 - Audit authored

- Authored [docs/phase_f/sut_audits/trnaaa_oc_vs_karr.md](/E:/opencell-worktrees/sut-parity-trnaaa/docs/phase_f/sut_audits/trnaaa_oc_vs_karr.md).
- Current static verdict: `FAITHFUL`.
- Key note: the inner stochastic depletion loop matches Karr; the main port-boundary differences are OC's `substrates_allocated` ingress and the `50_000` iteration safety cap.

## Beat 3 - Self-check

- Pending

## Notes

- `data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat` was content-verified before use. The fixture resolves the fields consumed by the OC port, including `reactionStoichiometryMatrix`, `reactionModificationMatrix`, `speciesReactantByproductMatrix`, `speciesReactantMatrix`, `speciesIndexs_enzymes`, `substrateIndexs_water`, and `substrateIndexs_hydrogen`.
