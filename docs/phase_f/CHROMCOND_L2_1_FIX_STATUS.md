# ChromosomeCondensation L2.1 fix — status + residual spec (2026-07-20)

**Verdict now:** L2.1 **FAIL** still (strict rubric unchanged). WIP fix `381ea0e`
committed on `agent/l2-0a-uncap`; compiles, does NOT regress
(`test_karr_chromosome_condensation_l2_replay.py` + `test_karr_chromosome_condensation.py`
= 7 passed), but not yet bit-identical.

## What `381ea0e` fixed (right direction, verified correct)
- Switched binding RNG `np.random.default_rng` → `_Mcg16807` (MCG16807 MatlabRandStream).
- Removed the scalar→sparse `_reconcile_complex_bound_count` step.
- Geometry-driven regions from `polymerizedRegions` + `complexBoundSites`.
- Per-binding draw sequence: `randsample_one(weights)` then `rand` offset
  (`ceil(u*(len-footprint+1))-1`), then single-strand region exclusion.
- Verified against Karr `ChromosomeCondensation.m` calcNewRegions (L286): exclusion
  offset = `bind_pos - smcSepNt/2 - smcSepProbCenter/2 + footprint/2`, length
  `smcSepNt+smcSepProbCenter`, strand = the binding region's strand (SINGLE strand —
  OC's single-strand loop exclusion is CORRECT). Weight `max(0, len-footprint+1)` matches.

## Residual divergence (localized)
Ticks 7-10: OC over-binds SMC by **+1-2** vs Karr (e.g. tick 8 OC bound 5, Karr 3),
and bound positions differ (sparse tuples mismatch). ATP/PI/H2O magnitude diffs are
downstream of the over-binding.

**Root-cause hypothesis (highest confidence):** OC's `_build_available_intervals`
excludes ONLY SMC `complexBoundSites` (line ~523 `if enzyme_idx != smc_adp_global_index:
continue`). Karr's binder samples from `getAccessibleRegions ∩ intersectRegions`, which
excludes ALL bound proteins/complexes (and other chromosome inaccessibility), not just
SMCs. So OC sees slightly more accessible DNA → fits 1-2 extra SMCs. That count drift
desynchronizes the MCG16807 stream → all subsequent positions shift.

Karr call path: `ChromosomeCondensation.m` evolveState L255-268 →
`ChromosomeProcessAspect.bindProteinToChromosomeStochastically` L80-105
(`getAccessibleRegions` L80, `intersectRegions` L83, `randsample` L96, `rand` L99).
Source: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/`.

## Next step to finish (unimplemented)
Make OC's available-region computation replicate Karr's `getAccessibleRegions`
(exclude ALL `complexBoundSites` + monomerBoundSites + inaccessible regions, then
intersect), so the binding count matches Karr — which should re-align the RNG stream
and the positions. Then re-run:
`bin/oc-pytest tests/vivarium/test_l2_1_strict_rubric.py -k ChromosomeCondensation -q -rs`
(a PASS here means computed==FAIL still; to confirm GENUINE, read the computed verdict
in `-rs` output or flip the pin and confirm the test then passes on GENUINE).

Diagnoses: `STATUS_chromcond_diag.md` (f0153bb), `STATUS_chromcond_rng.md` (f78682f).
Failed 520k-token attempt diff saved at `tmp/FAILED_chromcond_fix_520k.diff`.
