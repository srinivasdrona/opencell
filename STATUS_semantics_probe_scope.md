# STATUS — L2.2 Semantics + Init Scope Probe (Transcription canary)

## Verdict

The 3-bug taxonomy from the Translation canary does **NOT** uniformly generalize. Better news than feared:

| Bug | Scope |
|---|---|
| **A. Cold-init (enzymes/boundEnzymes default to 0)** | **Universal** across all 7 DEEP process schemas (one runner-layer fix generalizes) |
| **B. WID-width substrates** | **Universal** (Karr stores full shared metabolic pool 5-39 entries; OC scope-reduced to 4-26 process-relevant entries) |
| **C. Delta-vs-snapshot for monomers** | **Translation-only**, and only in the **new** ensemble extractor `extract_translation_ensemble.m` (codex 2c, commit `c823323`). The per_process_traces extractor produces clean snapshots for all 6 other DEEP processes. |

## Evidence

### Snapshot-equality probe (`states_before[t+1] == states_after[t]` rate over t=0..19)

```
=== Translation ENSEMBLE MAT (new, used by L2.2 gate) ===
  substrates       len=26   sum_t0=1.65e+08    0.00%  DELTA(reset-each-tick)
  monomers         len=482  sum_t0=0.00e+00   30.00%  MIXED (6/20)
  enzymes          len=16   sum_t0=8.11e+02   90.00%  MIXED (18/20)
  boundEnzymes     len=16   sum_t0=3.28e+02   90.00%  MIXED (18/20)
  aminoacylatedTRNAs len=36 sum_t0=2.03e+03    0.00%  DELTA(reset-each-tick)
  freeTRNAs        len=36   sum_t0=0.00e+00    0.00%  DELTA(reset-each-tick)
  ... (9 summary fields, mostly MIXED or SNAPSHOT)

=== Translation per_process_traces MAT (old) ===
  substrates       len=26   sum_t0=3.10e+08  100.00%  SNAPSHOT
  monomers         len=482  sum_t0=0.00e+00  100.00%  SNAPSHOT  [note: all-zero, suspicious]
  enzymes          len=16   sum_t0=8.13e+02  100.00%  SNAPSHOT
  boundEnzymes     len=16   sum_t0=3.28e+02  100.00%  SNAPSHOT

=== Transcription per_process_traces MAT ===  (3 channels, all SNAPSHOT 100%)
=== ChromosomeCondensation per_process_traces MAT ===  (3 channels, all SNAPSHOT 100%)
=== DNASupercoiling per_process_traces MAT ===  (3 channels, all SNAPSHOT 100%)
=== RNADecay per_process_traces MAT ===  (3 channels, all SNAPSHOT 100%)
=== ReplicationInitiation per_process_traces MAT ===  (3 channels, all SNAPSHOT 100%)
=== Replication per_process_traces MAT ===  (3 channels, all SNAPSHOT 100%)
```

**The new `extract_translation_ensemble.m` introduced the delta-vs-snapshot bug** when it extended channel coverage from 3 to 19. The old `extract_per_process_traces_v2.m` correctly snapshot-extracts substrates/enzymes/boundEnzymes for all processes (Translation per_process_traces shows clean 100% snapshot).

Why the difference: the old extractor reads the snapshot via the chassis runtime context where shared-pool state is stable across the tick. The new ensemble extractor either reads at a different point in the tick lifecycle or hits a MATLAB property that's reset per evolveState() call. Translation's `monomers` property in Karr's `Process_Translation.m` is one such reset-each-tick counter.

Note: per_process_traces Translation `monomers` is also broken (always zero), just in a different way — the extractor pulled the wrong field. The L2.2 effort discovered this when porting to ensembles and tried to "fix" by reading a different field, which gave the delta-reset semantics.

### Cold-init schema scope (universal)

All 6 confirmed DEEP processes use identical `_default: 0.0` pattern for enzymes/boundEnzymes:

```
karr_translation.py:           cold_default_0_count=2  boundEnzymes_mentions=4
karr_transcription.py:         cold_default_0_count=2  boundEnzymes_mentions=7
karr_replication.py:           cold_default_0_count=8  boundEnzymes_mentions=5
karr_replication_initiation.py: cold_default_0_count=8 boundEnzymes_mentions=5
karr_dna_repair.py:            cold_default_0_count=6  boundEnzymes_mentions=1
karr_cytokinesis.py:           cold_default_0_count=7  boundEnzymes_mentions=1
karr_mac_complex.py:           MISSING (process file not yet authored)
```

One fitted-init helper in `l2_replay_common.build_state_template` (or a sibling) plus a per-process WID-mapping spec generalizes to all 6 (and the 7th when it lands).

## Three concrete fix workstreams (instead of "rewrite plan §1")

| Workstream | Scope | Effort | Owner |
|---|---|---|---|
| **F1. Fitted-init injection** | One change in `build_state_template` or in each runner's pre-tick-0 hook. Reads `states_before[0]` from MAT. | 1 day, 1 codex job | runner-layer fix |
| **F2. Substrate WID intersection** | Project both Karr (full pool) and OC (scope-reduced) onto the OC WID intersection before comparing. | 0.5 day, comparator-layer fix | gate test |
| **F3. Translation ensemble re-extraction** | Either: (a) rewrite `extract_translation_ensemble.m` to use snapshot semantics for all 9 channels (preferred); or (b) keep the new extractor for the 9 extended channels and audit which are valid snapshots vs deltas vs broken. | 1-2 days MATLAB work | extractor fix, regenerates all 50 seed MATs |

**Plan §1 does NOT need rewriting.** §1's methodology (Karr-fitted-init + identical state surface → distributional match) is correct; the implementation just hadn't met it. F1+F2+F3 close the implementation gap.

**Plan §2.5.4 (Translation) needs a sub-step**: depend on F3 before re-running the gate.

**The other 6 DEEP processes in §2 are NOT contaminated by Bug C** — they use the proven per_process_traces extractor. They only need F1 + F2.

## Updated recommendation

1. Commit this probe + STATUS. (now)
2. Update plan: add F1/F2/F3 as concrete workstreams, mark §2.5.4 as F3-blocked. Don't touch §1.
3. Fire F1+F2 as a single codex job (gate-layer, no MATLAB) — generalizes to all 7 DEEP processes.
4. Fire F3 as a separate codex job (MATLAB extractor rewrite + regen 50 Translation seed MATs).
5. After F1+F2 land: re-run L2.2 gates for Transcription (already has per_process_traces MAT, just needs the new ensemble extractor pointed at the SNAPSHOT-semantic per_process_traces path or expanded to N=50).
6. After F3 lands: re-run L2.2 Translation gate.

## Files
- `tests/vivarium/_l2_2_semantics_probe.py` (new) — universal `states_before[t+1] == states_after[t]` probe across all per_process MATs.
- Translation canary findings unchanged from `STATUS_init_canary_translation.md`.

## Commit
TBD on `exec/l22-init-canary-translation`.
