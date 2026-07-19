# ChromosomeCondensation L2.1 diagnosis

## Current failure signature

- `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py` currently passes, but it does so with `trace_after` hints for `enzymes` and `boundEnzymes`.
- The strict-rubric path in `tests/vivarium/test_l2_1_strict_rubric.py` is the failing surface for this process: inside `_classify()`, the per-tick bit-identity check (`np.array_equal(oc_after, karr_after)`) breaks on the first tick.
- First strict-rubric divergence localized by `tmp/probe_chromcond_divergence.py`:
  - tick `0`
  - first observable: `substrates`
  - first index/WID: `ATP`
  - Karr before/after: `75 -> 72`
  - OC before/after: `75 -> 67`

## Localized divergence

Tick `0` is the first real divergence. The surfaced count mismatch is already visible, and the hidden chromosome sparse-field payload explains it:

- `substrates.ATP`: OC `67` vs Karr `72` (`before=75`)
- `substrates.PI`: OC `8` vs Karr `3` (`before=0`)
- `substrates.H2O`: OC `756710` vs Karr `756715` (`before=756718`)
- `enzymes.MG_213_214_298_6MER`: OC `0` vs Karr `5` (`before=5`)
- `boundEnzymes.MG_213_214_298_6MER_ADP`: OC `86` vs Karr `81` (`before=78`)

Hidden chromosome state on the same tick:

- injected `states_before.chromosome.complexBoundSites` contains `194` sparse edges
- injected `states_before.boundEnzymes[SMC_ADP]` is only `78`
- raw OC `next_update["chromosome"]["complexBoundSites"]` is a replacement sparse payload with `86` edges
- Karr `states_after.chromosome.complexBoundSites` has `197` edges
- first concrete sparse mismatch from the probe:
  - field: `chromosome.complexBoundSites`
  - OC tuple: `(31714, strand 1, value 82)`
  - Karr tuple: `(25015, strand 0, value 82)`

The same pattern persists immediately after tick 0:

- ticks `1-4`: Karr leaves the surfaced counts unchanged, but OC still emits an extra bind of `5` SMCs each tick
- visible effect each of those ticks:
  - `ATP`: OC `before-5`, Karr unchanged
  - `PI`: OC `before+5`, Karr unchanged
  - free SMC enzyme count: OC `5 -> 0`, Karr stays `5`
  - `boundEnzymes[SMC_ADP]`: OC `81 -> 86`, Karr stays `81`
  - raw OC `complexBoundSites` replacement remains `86` edges while Karr keeps `205-206` edges

## Bug class

Primary bug class: `wrong index/projection` / cardinality mismatch between the hidden chromosome sparse field and the surfaced `boundEnzymes` count.

How it manifests:

- `wrong index/projection` on `chromosome.complexBoundSites` (OC emits an 86-edge replacement map that does not match Karr’s 197-edge map on tick 0)
- `magnitude` error on tick 0 surfaced molecule counts (OC binds `8`, Karr binds `3`)
- repeated `extra-write` on ticks `1-4` (OC keeps binding `5` SMCs when Karr is unchanged)

This does **not** look like an RNG-only issue or a clipping issue. The divergence is structural before any stochastic parity discussion matters.

## Root-cause hypothesis

Most likely root cause: the OC no-hints path is using the surfaced `boundEnzymes` scalar as the authoritative occupancy count and then forcibly reconciling the chromosome sparse map to that scalar before choosing new bind positions, whereas Karr’s `evolveState` uses the chromosome’s actual bound-site geometry directly.

Grounding in Karr `ChromosomeCondensation.m`:

- docstring: “`The chromosomes property represents the specific base positions where the chromosome-bound SMC complexes are located.`”
- `evolveState` then does:
  - `smcPosStrands = find(c.complexBoundSites == this.enzymeGlobalIndexs(...));`
  - `[posStrnds, lens] = c.excludeRegions(..., smcPosStrands, ...);`
  - `nBound = this.bindProteinToChromosomeStochastically(..., nBindingMax, posStrnds, lens, ..., @this.calcNewRegions);`

In other words, Karr computes bindable regions from the existing `complexBoundSites` geometry itself. The OC port instead does this in the no-hints path:

- reads `current_bound_smc` from `boundEnzymes[SMC_ADP]`
- calls `_reconcile_complex_bound_count(... desired_count=current_bound_smc)`
- replaces the sparse chromosome map with that reconciled count before sampling new bindings

On tick 0, that means the OC path takes a `complexBoundSites` map with `194` edges, forces it toward the surfaced count `78`, and emits an `86`-edge replacement map. Karr starts from the original geometry and ends at `197` edges. That explains both the wrong sparse positions and the over-consumption / over-binding on the surfaced count ports.

## Unimplemented fix direction

If approved later, the fix should be in the OC no-hints binding path, not in the test. Port `evolveState` more literally: treat `chromosome.complexBoundSites` as the authoritative occupancy geometry used to build/exclude candidate binding regions, and remove the synthetic “reconcile sparse edge count to boundEnzymes scalar” step unless the representation mapping is first proven equivalent to Karr. The operator should specifically review how a Karr `complexBoundSites` occupancy projects to OC’s `boundEnzymes[SMC_ADP]`; until that mapping is correct, `n_bound`, ATP/H2O consumption, and the emitted sparse positions will keep diverging.

## Artifacts

- Probe: `tmp/probe_chromcond_divergence.py`
- Production code modified: `none` (`opencell/` untouched)
- Commit SHA: `72f4afc` (probe commit; this STATUS file is gitignored, so it is recorded in the follow-up status-only commit)
