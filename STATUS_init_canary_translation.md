# STATUS — L2.2 Translation Init-Parity Canary (seed_000)

## Verdict

**Init parity is NOT the dominant issue.** The seed_000 canary uncovered a more fundamental problem: the L2.2 Translation gate is comparing different quantities for two of the four observables.

| Observable | Issue | Init contribution to drift | Real cause |
|---|---|---|---|
| `enzymes` | OK semantically | **97-99%** (entire drift) | Pure cold-start defect, fixable by fitted init |
| `boundEnzymes` | OK semantically | **95-99%** (entire drift) | Pure cold-start defect, fixable by fitted init |
| `substrates` | WID-width mismatch (Karr 26 ↔ OC 20) AND huge scale (Karr~165M, OC~scalar) | N/A — comparison invalid | Substrate-space cardinality mismatch + uniform-scalar default |
| `monomers` | **Different semantic** (Karr=per-tick synthesis events ~0-2; OC=absolute counts ~16180) | N/A — comparison invalid | Gate compares delta vs absolute — 100% definition mismatch |

## Per-tick measurements (seed_000)

Aggregate = `np.sum(vec)` per tick (same aggregator as `test_l2_2_translation.py`):

```
observable     tick      karr_sum    oc_cold_sum  oc_fitted_sum   |cold-K|   |fit-K|  init_contrib
enzymes           0       8.26e+02      0.000e+00     8.110e+02   8.26e+02  1.50e+01      8.11e+02
enzymes          50       7.94e+02      0.000e+00     8.110e+02   7.94e+02  1.70e+01      7.77e+02
enzymes          99       8.07e+02      0.000e+00     8.110e+02   8.07e+02  4.00e+00      8.03e+02
boundEnzymes      0       2.90e+02      0.000e+00     3.280e+02   2.90e+02  3.80e+01      2.52e+02
boundEnzymes     50       3.20e+02      0.000e+00     3.280e+02   3.20e+02  8.00e+00      3.12e+02
boundEnzymes     99       3.14e+02      0.000e+00     3.280e+02   3.14e+02  1.40e+01      3.00e+02
monomers          0       2.00e+00      1.618e+04     1.618e+04   1.62e+04  1.62e+04      0.00e+00
monomers         50       0.00e+00      1.618e+04     1.618e+04   1.62e+04  1.62e+04      0.00e+00
monomers         99       2.00e+00      1.618e+04     1.618e+04   1.62e+04  1.62e+04      0.00e+00
substrates        0       0.00e+00     -3.800e+01    -3.800e+01   3.80e+01  3.80e+01      0.00e+00 [width 26 vs 20]
substrates       99       0.00e+00     -3.871e+03    -3.871e+03   3.87e+03  3.87e+03      0.00e+00 [width 26 vs 20]
```

Note: `karr_sum=0` for substrates above is the sum of the FIRST 20 entries (truncated to OC width). Full 26-vector substrate sums are ~165M (see semantics probe below).

## Semantic probe (definitive)

Direct h5py read of `Translation_100ticks.mat` seed_000:

| Channel | `states_before[0]` sum | `states_after[0]` sum | `states_before[1]` sum | `before[1] == after[0]`? | Interpretation |
|---|---:|---:|---:|---|---|
| `monomers` (482) | 0.0 | 2.0 | 0.0 | **NO** (reset to 0 each tick) | **per-tick synthesis counter** (delta) |
| `enzymes` (16) | 811 | 826 | 826 | **YES** | absolute counts (snapshot) |
| `substrates` (26) | 164,690,336 | 164,692,923 | 152,695,498 | NO (other processes mutate shared pool) | absolute counts, shared metabolic pool |

The MATLAB extractor (`scripts/matlab/extract_translation_ensemble.m:307-315`) snapshots `proc.(propname)` before/after `evolveState()`. For `monomers`, Karr's Translation process resets to zero each tick and writes the synthesis event count — so what's stored is a delta, not an absolute. For `enzymes`/`boundEnzymes`, the process keeps absolute counts.

OpenCell's `_l2_2_ensemble_runner.py::project_observable_from_state("monomers")` reads `state["protein"]["counts"]` snapshot (~16000 absolute). Hence the 16000× W1 isn't a fidelity gap — it's the gate comparing apples to oranges.

## Implications for L2.2

The bug taxonomy is now:

1. **Definition mismatch (monomers, possibly summary fields).** The MATLAB extractor's per-tick reset/write semantic was not propagated into the OpenCell observable projection. **No process-side fix can close this gap.** Options:
   - (a) Change OC observable to emit per-tick synthesis delta (matching Karr semantic). Requires hooking `next_update["protein"]["counts"]` deltas.
   - (b) Change Karr extractor to emit absolute counts (requires MATLAB regen of all 50 seeds, ~hours).
   - (c) Drop `monomers` from the L2.2 gate; rely on enzymes/boundEnzymes as the fidelity surface.
   - **(a) is the canonical fix.** It matches the spirit of "L2.2 measures the Translation process's per-tick output distribution".

2. **WID-space mismatch (substrates).** Karr substrates = 26 entries (full metabolic pool including ATP/H2O/ions), OC substrates = 20 entries (AAs only). Comparing sums is invalid even when both are absolute. Either:
   - Project both onto the 20-AA intersection.
   - Drop substrates from the L2.2 gate (matches scope-reduced philosophy).

3. **Cold-start init (enzymes, boundEnzymes).** Real, dominant, fixable. Fitted-init from `states_before[0]` brings drift from 100% (cold = 0) to <5% residual. This IS the methodology bug we hypothesized — but only for 2 of the 4 channels.

## Three-data-point picture (init-parity question)

Cold-start v1 vs fitted-init v1 vs Karr, expressed as |sum-drift| at tick 99:

| Observable | Karr | OC cold | OC fitted | cold drift | fitted drift | init contribution |
|---|---:|---:|---:|---:|---:|---:|
| enzymes | 807 | 0 | 811 | 807 | 4 | **99.5%** |
| boundEnzymes | 314 | 0 | 328 | 314 | 14 | **95.5%** |
| monomers | 2 | 16180 | 16180 | 16178 | 16178 | 0% (semantic mismatch) |
| substrates (head-20) | 0 | -3871 | -3871 | 3871 | 3871 | 0% (semantic + WID mismatch) |

## What this tells us about the §1 methodology

The L2.2 ensemble-gate plan §1 assumed: identical RNG + identical fitted init + identical state surface → distributional match. The seed_000 probe shows three independent assumption failures:

- **Identical state surface fails for monomers.** Extractor stores Karr's per-tick delta; runner stores OC's absolute snapshot.
- **Identical WID space fails for substrates.** 26 vs 20.
- **Identical fitted init fails for enzymes/boundEnzymes.** OC schema defaults to 0 instead of loading Karr's `states_before[0]`.

Only the third is what we originally suspected ("init parity"). The first two are observable-projection bugs that don't get fixed by injecting tick-0 state.

## Recommendation

1. **Don't rewrite plan §1 around "load fitted init".** That's a partial fix.
2. **Treat L2.2 observable projection as the actual workstream.** Open a focused investigation:
   - For each DEEP process, audit per-observable: (a) is the MATLAB extractor recording delta or snapshot? (b) does the OC projection match? (c) do WID spaces align?
   - Fix the projection layer in the runner, not the process source.
3. **Re-run L2.2 Translation only after** the monomers projection is fixed (delta-emission) AND fitted-init is loaded AND substrates are intersected-or-dropped.
4. **Validation:** repeat this single-seed canary on Transcription (already has v1 cold data from prior work) to test whether the same three-bug pattern repeats — that determines whether the projection audit is a Translation-only one-off or a 7-process workstream.

## Files

- New: `tests/vivarium/_l2_2_init_canary.py` — single-seed canary harness.
- New: `data/init_canary/translation_seed000.json` — full per-tick table.
- New: this file.

## Commit
- TBD on `exec/l22-init-canary-translation` (branched off `exec/l22-translation-v1` @ `ddeaf05`).
