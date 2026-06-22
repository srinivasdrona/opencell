# L2.5 Clean-vs-clean DS pair results (Day-35 EOD)

**Run:** `bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -k ChromosomeSegregation`
**Date:** 2026-06-22
**Total runtime:** ~100 s

## Why this set

Per `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md` (Day-35), 13 of 28 L2.5 processes
have hint-driven short-circuits that bypass their biology samplers when
`trace_hint` is present. L2.1 and L2.2 verdicts on those 13 processes are
oracle-leaked. L2.5 honest mode is the first gate that exposes the underlying
biology samplers.

`scripts/probe_clean_clean_pairs.py` cross-references the audit with the L2.5
in-scope shared-pool matrix to extract pairs where BOTH processes are clean
(no `trace_hint` usage anywhere). Of 256 shared-pool pairs, **67 are
clean-vs-clean**, of which **11 are deterministic-stochastic (DS)** and
therefore runnable today via the existing parametrized harness.

All 11 are `ChromosomeSegregation + X` because Seg is the only deterministic
clean process.

## Result (11 DS clean-vs-clean pairs)

| Pair                                    | Verdict   | Class           |
|-----------------------------------------|-----------|-----------------|
| ChromosomeSegregation + ProteinFolding         | ✅ PASS    | clean × clean   |
| ChromosomeSegregation + RNAProcessing          | ✅ PASS    | clean × clean   |
| ChromosomeSegregation + tRNAAminoacylation     | ✅ PASS    | clean × clean   |
| ChromosomeSegregation + ProteinProcessingI     | ✅ PASS    | clean × clean   |
| ChromosomeSegregation + ProteinProcessingII    | ✅ PASS    | clean × clean   |
| ChromosomeSegregation + ProteinTranslocation   | ❌ FAIL    | clean × clean   |
| ChromosomeSegregation + DNARepair              | ❌ FAIL    | clean × clean   |
| ChromosomeSegregation + RibosomeAssembly       | ⚪ SKIPPED | clean × clean   |
| ChromosomeSegregation + Cytokinesis            | ⚪ SKIPPED | clean × clean   |
| ChromosomeSegregation + DNADamage              | ⚪ SKIPPED | clean × clean   |
| ChromosomeSegregation + RNAModification        | ⚪ SKIPPED | clean × clean   |

**Of testable (PASS+FAIL=7): 5 PASS / 2 FAIL = 71% honest-green.**

## Reference: dirty-partner Seg DS results (10 pairs)

| Pair                                          | Verdict | Partner short-circuit class |
|-----------------------------------------------|---------|-----------------------------|
| Seg + Translation                             | ✅ PASS  | REPLAY_GUARD (benign here)  |
| Seg + DNASupercoiling                         | ❌ FAIL  | CHANNEL_OVERLAY             |
| Seg + FtsZPolymerization                      | ❌ FAIL  | CHEMISTRY_BYPASS            |
| Seg + Metabolism                              | ❌ FAIL  | CHEMISTRY_BYPASS (FBA off)  |
| Seg + ProteinDecay                            | ❌ FAIL  | CHEMISTRY_BYPASS            |
| Seg + ProteinModification                     | ❌ FAIL  | GATED_BIOLOGY               |
| Seg + RNADecay                                | ❌ FAIL  | CHEMISTRY_BYPASS            |
| Seg + Replication                             | ❌ FAIL  | FULL_BYPASS                 |
| Seg + ReplicationInitiation                   | ❌ FAIL  | FULL_BYPASS                 |
| Seg + Transcription                           | ❌ FAIL  | CHEMISTRY_BYPASS            |

**9 of 10 dirty-partner pairs fail** — strongly corroborates the audit's
prediction. The one outlier (Translation) suggests its REPLAY_GUARD is
benign for at least this composition.

## Interpretation

1. **The short-circuit audit predicts L2.5 outcomes well.** 9/10 dirty pairs
   fail; 5/7 testable clean pairs pass. The classifier earns its keep.

2. **Two genuine clean×clean failures need root-cause investigation:**
   - `Seg + ProteinTranslocation` — overlap 5 (substrates GTP/GDP/H/H2O/PI/...).
     Failure record (extracted): `CAUSE_4_UPSTREAM_STATE_POLLUTION`, ATP off by
     -14 at index 0, isolated replay matches oracle, composition diverges.
   - `Seg + DNARepair` — needs failure-record extraction tomorrow.

   These can't be blamed on `trace_hint`. Possible causes:
   - A real composition-time biology drift (allocator/order/parallelism)
   - A non-trace_hint short-circuit pattern the audit missed (e.g.,
     hint-derived state read via a different variable name)
   - A harness-level issue specific to deterministic + stochastic interleaving
     when both processes touch the same WIDs

3. **Skipped 4 pairs need to be unskipped** — they're skipped likely due to
   no-op trace or sparse-event criteria from earlier-day investigation, not
   biology. They're the cheapest unlock candidates.

## Next steps (Day-36 candidate)

1. Extract structured failure records for Seg+ProteinTranslocation and
   Seg+DNARepair. Determine if either is a hidden short-circuit (audit miss)
   or a real composition bug.
2. Re-run the 4 skipped clean-vs-clean Seg pairs with a forced sample range
   to see if they pass.
3. **The 56 SS clean-vs-clean pairs are the next big unlock surface** — they
   need either:
   - Extension of `test_l25_deterministic_stochastic_pairs.py` style harness
     to SS pairs (single new parametrized test file, similar pattern), OR
   - A codex delegation to wire each remaining SS clean-vs-clean pair to a
     dedicated test file (12 SS clean-vs-clean pairs already have a dedicated
     test per `probe_clean_clean_wiring.py`).

If clean×clean honest-green rate at ~71% holds across the 56 SS pairs, the
true L2.5 ceiling jumps from today's 8 honest PASS to **8 + ~40 = ~48 honest
PASS** without touching the 13 short-circuited processes. That's the most
useful number on the table.

## Provenance

- Audit source: `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md` (commit `73b254d`)
- Pair selection: `scripts/probe_clean_clean_pairs.py`, `scripts/probe_clean_clean_wiring.py`
- Pytest runtime: 99.88 s on Day-35 EOD, WSL venv, single seed (rng_seed_0)
- Harness: `tests/vivarium/test_l25_deterministic_stochastic_pairs.py`
- Pair list source: `data/schemas/l25_pair_list.toml`
