# tRNAAminoacylation OC vs Karr Static Parity Audit

## DAP Intent

Contract:
- Required behavior: determine whether OpenCell's `KarrTRNAAminoacylationProcess` implements the same aminoacylation algorithm as Karr's `tRNAAminoacylation.evolveState`, using source-to-source evidence rather than runtime output.
- Why this matters: the L2.2 `regime_bounded` label should only remain if the code itself diverges, not if the stress comparison fed different substrate inputs to otherwise matching algorithms.
- Done = a line-cited audit that maps the algorithm steps, inventories every Karr RNG draw, traces the substrate-runout behavior, and reaches one of the mandated verdicts.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: declare parity after reading only `next_update` and missing the actual stochastic loop in `_compute_rna_fluxes`, or mistake the allocator-fed substrate boundary for an inner-loop algorithm difference.
- What would falsify the audit: any Karr RNG draw or substrate-depletion branch without an OC counterpart, or any OC step that changes reaction selection or state-update semantics under matched input vectors.

PM sanity-check:
- This audit assumes the canonical upstream WholeCell file at `src/+edu/+stanford/+covert/+cell/+sim/+process/tRNAAminoacylation.m` is the correct Karr authority because the requested local mirror is absent from this checkout.

## 2) Inventory of Existing Artifacts

- [A01] path=docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md | kind=doc | role=generic audit discipline; requires explicit contract, inversion, and verification framing.
- [A02] path=docs/prompts/DESIGN_TEMPLATE.md | kind=doc | role=section-shape authority for the inventory and baseline-facts portions of this audit.
- [A03] path=docs/prompts/COMPOSITION_MANDATE_v2.md | kind=doc | role=authoritative slot-composition rule for this deliverable.
- [A04] path=upstream:CovertLab/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/tRNAAminoacylation.m | kind=code | role=canonical Karr source for `evolveState`; used for all Karr line citations after the local mirror was found missing.
- [A05] path=opencell/vivarium/karr_trna_aminoacylation.py | kind=code | role=OpenCell implementation under audit; contains `next_update`, `_compute_rna_fluxes`, and RNG helper methods.
- [A06] path=data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat | kind=data | role=fixture supplying the matrices and indices the OC port executes against; content verified by loading named fields and resolved array shapes.
- [A07] path=scripts/matlab/serialize_chromosome_state.m | kind=code | role=reference serializer named in the task; checked to determine whether chromosome state participates in this process audit.
- [A08] path=docs/karr_extracts/process/14_tRNAAminoacylation.md | kind=doc | role=in-repo secondary corroboration of the Karr docstring/source path after the WholeCell source mirror proved absent.

Inventory Beat-4 inversion:
- What critical artifact could still be missing from this list? A different local snapshot of `tRNAAminoacylation.m`; that would supersede the upstream copy used here.
- What check reduced that risk? I checked the worktree and git object database for the exact requested path and for `tRNAAminoacylation.m` by filename before falling back to the upstream source.
- What could be wrong in the listed artifacts? The fixture could exist but contain placeholder or shape-mismatched data; that risk was reduced by loading the named fields and confirming resolved shapes for the matrices and index arrays the OC port reads.

## 4) Baseline Facts and Constraints

1. Hard constraints from session context
- No code edits, no MATLAB invocation, and no test execution were allowed; the deliverable is a markdown audit only.
- The requested local Karr source path is absent from this checkout, so Karr citations refer to the canonical upstream file at the same repo-relative path.

2. Fidelity constraints from the primary source
- Karr `evolveState` works over a single transient `species` vector built from substrates, catalytic enzymes, and free RNAs, and applies all state writes only after the stochastic loop finishes.
- Water and hydrogen are explicitly ignored in both the initial and iterative limit calculations.
- `isReactionInactive` is frozen from the initial reactant-only feasibility pass and then enforced throughout the loop.

3. Existing implementation facts (single-component only)
- OC loads `reactionStoichiometryMatrix`, `reactionModificationMatrix`, `speciesReactantByproductMatrix`, `speciesReactantMatrix`, `speciesIndexs_enzymes`, `substrateIndexs_water`, and `substrateIndexs_hydrogen` from `tRNAAminoacylation_flat.mat` ([opencell/vivarium/karr_trna_aminoacylation.py](/E:/opencell-worktrees/sut-parity-trnaaa/opencell/vivarium/karr_trna_aminoacylation.py:117)).
- The verified fixture resolves to `reactionStoichiometryMatrix (30 x 39)`, `reactionModificationMatrix (39 x 37)`, `speciesReactantByproductMatrix (37 x 88)`, `speciesReactantMatrix (37 x 88)`, and `speciesIndexs_enzymes (21 x 1)`.
- The fixture's non-enzyme coefficients are integer-valued in both species matrices, so OC's `draws = floor(n_rxns)` behaves as a no-op under the checked artifact.
- Neither implementation reads or writes chromosome state, so `serialize_chromosome_state.m` is not part of the active algorithmic surface for this audit.

4. Known failure modes and anti-patterns
- A false divergence would result from comparing OC's allocator-reduced `substrates_allocated` vector against Karr's full `this.substrates` vector and calling the input mismatch an algorithm mismatch.
- A false equivalence would result from auditing `next_update` alone and ignoring `_compute_rna_fluxes`, where the stochastic depletion loop actually lives.

Baseline Beat-4 inversion:
- Which baseline "fact" is inferred rather than proven? The claim that OC's iteration cap is not hit in the regime of interest is inferred from static structure, not proven by execution.
- What would invalidate it? Evidence that realistic low-substrate runs exceed 50,000 loop iterations would make the cap a material behavior difference.

## 1. Algorithm Summary

Karr `evolveState` performs a greedy stochastic aminoacylation loop over 37 RNA targets. It exits immediately if no free RNA exists, constructs a transient species vector from current substrates, catalytic enzymes, and free RNAs, computes permanently inactive reactions from the reactant-only matrix, then repeatedly recomputes feasible per-RNA limits from the byproduct-aware matrix. Each iteration stochastically rounds enzyme-limited capacity, intersects that with non-enzyme availability, samples one or many RNA aminoacylation events with weights proportional to the feasible limits, decrements the transient species vector by the selected stoichiometry, and stops when no reaction remains feasible. It then projects the accumulated RNA-level fluxes back to reaction-level substrate stoichiometry and updates substrates, free RNAs, and aminoacylated RNAs.

OC `next_update` reconstructs the same state vectors from Vivarium stores, then delegates the stochastic core to `_compute_rna_fluxes`. That helper builds the same transient species vector, performs the same initial inactivity mask, the same water/hydrogen exclusions, the same enzyme stochastic-rounding and non-enzyme limit intersection, and the same weighted single-draw or batched-draw depletion logic. After fluxes return, `next_update` maps them through the same reaction-modification and reaction-stoichiometry matrices to emit substrate and RNA deltas. The port-specific differences are that OC reads its substrate vector from `substrates_allocated[self.name]`, supports split Vivarium enzyme/RNA stores, and adds a 50,000-iteration safety cap.

## 2. Step-by-Step Mapping

| Karr line(s) + step | OC line(s) + step | Verdict |
|---|---|---|
| `L388-L390` - return immediately when `freeRNAs` is all zero. | `L256-L257` - return `{}` or an explicit noop update when `free_rna.sum() <= 0`. | EQUIVALENT |
| `L393-L398` - build the transient `species = [substrates; catalytic enzymes; freeRNAs]`. | `L215-L254`, `L366-L369` - reconstruct substrates/free RNA/aminoacylated RNA/enzyme vectors from Vivarium stores, then build the same concatenated species vector. | DIVERGENT |
| `L400-L408` - initialize `reactionFluxes`, set `anyFlux = false`, compute initial reactant-only limits, ignore water/hydrogen, and freeze `isReactionInactive`. | `L365-L374` - initialize `reaction_fluxes`, compute the same initial reactant-only limits via `_limits_from_species`, ignore water/hydrogen, and freeze `is_reaction_inactive`. | EQUIVALENT |
| `L410-L418` - recompute current limits from `speciesReactantByproductMatrix`, stochastic-round enzyme limits, intersect with non-enzyme limits, and zero inactive / invalid / `< 1` reactions. | `L378-L391`, `L439-L446` - recompute limits from `species_reactant_byproduct_matrix`, stochastic-round enzyme limits, intersect with non-enzyme limits, and zero inactive / invalid / `< 1` reactions. | EQUIVALENT |
| `L420-L424` - stop when no reaction can proceed; otherwise mark that flux occurred. | `L393-L395`; no `anyFlux` flag, but `next_update` later returns early when `reaction_fluxes` is all zero (`L264-L265`). | EQUIVALENT |
| `L426-L427` - build cumulative probability edges from feasible limits and choose `nRxns` as the minimum positive limit. | `L397-L401` - build the same cumulative probability edges and the same minimum positive `n_rxns`. | EQUIVALENT |
| `L428-L436` - when `nRxns <= 1`, draw one uniform random value, pick one reaction by weighted binning, increment that flux by 1, and subtract one row of `speciesReactantByproductMatrix`. | `L403-L407`, `L450-L452` - when `n_rxns <= 1.0`, draw one uniform random value, pick one reaction by weighted binning, increment that flux by 1, and subtract one row of `species_reactant_byproduct_matrix`. | EQUIVALENT |
| `L437-L448` - when `nRxns > 1`, draw `nRxns` weighted reaction selections, aggregate counts per reaction, add them to `reactionFluxes`, and subtract the batched stoichiometry. | `L409-L424`, `L455-L459` - when `n_rxns > 1.0`, draw `floor(n_rxns)` weighted reaction selections, aggregate counts per reaction, add them to `reaction_fluxes`, and subtract the batched stoichiometry. | EQUIVALENT |
| `L452-L455` - if the loop never produced flux, return without touching state. | `L264-L265` - if `reaction_fluxes` is all zero, return `{}` or an explicit noop update. | EQUIVALENT |
| `L457-L459` - update substrates via `reactionStoichiometryMatrix * reactionModificationMatrix * reactionFluxes`. | `L267-L282` - compute `reaction_events_by_rxn = reaction_modification @ reaction_fluxes`, then `substrate_delta = reaction_stoich @ reaction_events_by_rxn`, and emit substrate deltas. | EQUIVALENT |
| `L461-L463` - decrement `freeRNAs` and increment `aminoacylatedRNAs` by `reactionFluxes`. | `L272-L301` - emit `rna.counts` and `rna.aminoacylated_counts` deltas equal to `-reaction_fluxes` and `+reaction_fluxes`. | EQUIVALENT |
| No Karr counterpart inside `evolveState`. | `L376-L377` - cap the stochastic loop at `max_stochastic_iterations` (default `50_000`). | OC_SIMPLIFIED |

Notes on the divergent ingress row:
- Karr reads the process-owned substrate state directly.
- OC reads the allocator-provided substrate slice for this process and clamps negatives to zero before entering the otherwise matching loop.

## 3. RNG Draw Inventory

| Karr draw | OC draw | Match |
|---|---|---|
| `L416` - `this.randStream.stochasticRound(...)` applies stochastic rounding to enzyme-limited reaction capacities before intersecting them with non-enzyme limits. Distribution: one Bernoulli decision per reaction, based on the fractional part of the enzyme limit. | `L383-L385`, `L439-L446` - `_stochastic_round(enzyme_limits)` applies the same floor-plus-Bernoulli rounding using `self._rng.random(vals.shape)`. | YES |
| `L430` - `rand(this.randStream, 1, 1)` draws one uniform variate to pick a single reaction when `nRxns <= 1`. Distribution: `U[0,1)`. | `L403-L405` - `self._rng.random()` draws one uniform variate to pick a single reaction when `n_rxns <= 1.0`. Distribution: `U[0,1)`. | YES |
| `L440` - `rand(this.randStream, nRxns, 1)` draws `nRxns` independent uniform variates for the batched weighted-selection branch. Distribution: `nRxns` IID `U[0,1)` draws. | `L409-L418` - `self._rng.random(draws)` draws `draws = floor(n_rxns)` IID uniform variates for the same batched weighted-selection branch. | YES |

RNG notes:
- No additional `mnrnd`, `poissrnd`, `randperm`, or other random draws appear in Karr `evolveState`.
- The audit is about distributional parity, not seed-for-seed identity; MATLAB `randStream` and NumPy `default_rng` are different engines, so exact trajectories are not expected to match.

## 4. Substrate-Availability Handling

Karr handles substrate insufficiency by turning it into shrinking `reactionLimits`, not by branching on a separate "substrate exhausted" flag. The initial reactant-only pass (`L403-L408`) permanently marks reactions impossible at the starting state via `isReactionInactive`. Inside the loop, Karr recomputes limits from the current transient `species` vector (`L412-L418`), zeroes any reaction whose current limit is invalid or `< 1`, and subtracts consumed substrate immediately after each single event (`L435-L436`) or batched event (`L447-L448`). Once all current limits are zero, the loop breaks (`L420-L422`). There is no special mid-batch recheck; instead, the batch size is `nRxns = min(reactionLimits(reactionLimits > 0))` (`L427`), so a batch never asks for more total events than the smallest currently feasible reaction can support.

OC handles substrate insufficiency the same way inside `_compute_rna_fluxes`. It begins from `substrates_allocated[self.name]` (`L215-L219`) rather than a raw substrate store, then computes the same initial inactivity mask (`L371-L374`), recomputes current limits from the transient species vector each iteration (`L378-L391`), subtracts consumed substrate after each single event (`L405-L406`) or batched event (`L423-L424`), and stops when no feasible reaction remains (`L393-L395`). Like Karr, it does not special-case "substrate ran out mid-iteration"; substrate exhaustion is expressed entirely through the recomputed limits.

Verdict: EQUIVALENT. For the regime-bounded question itself, both implementations deplete substrate through the same limit-recompute-and-stop mechanism (`Karr L410-L448`; `OC L377-L424`). The only boundary difference is that OC's starting substrate vector comes from `substrates_allocated[self.name]` (`OC L215-L219`) instead of Karr's process-owned `this.substrates` (`Karr L395-L398`).

## 5. Overall Verdict

**FAITHFUL**

Static source comparison found no algorithmic divergence in the aminoacylation loop itself. OC reproduces Karr's reaction-feasibility calculation, stochastic rounding, weighted reaction selection, transient species depletion, and final substrate/RNA updates (`Karr L400-L463`; `OC L259-L301`, `L365-L446`). The observed differences are port-boundary adaptations rather than a different aminoacylation algorithm: OC reads allocator-provided substrate counts at ingress (`OC L215-L219`), supports Vivarium store normalization and legacy-vector fallback (`OC L205-L254`), and adds a 50,000-iteration safety cap (`OC L376-L377`).

On static inspection, the Day-29 low-substrate divergence is therefore more consistent with comparing different input vectors than with OC implementing a different tRNAAminoacylation algorithm. In particular, comparing OC under substrate allocation/scaling against Karr under full-state `alpha = 1` would be expected to diverge even if the inner algorithm matches.

## 6. Implications for Regime-Bounded Label

Recommend upgrading this process from `regime_bounded` to `confirmed_biology_validated`.

Reason:
- The static audit did not find an inner-loop algorithm mismatch between OC and Karr.
- The stress-test discrepancy is better explained by an input-matching problem than by a process bug.
- Future parity tests should compare matched substrate vectors: OC should be judged against the same effective substrate counts Karr receives, not against an allocator-scaled OC state versus an unscaled Karr state.
