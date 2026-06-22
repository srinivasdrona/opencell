# L2.5 honest-mode finding: pre-existing L2.1 trace-hint short-circuits hid no-hints biology drift

## The pattern (discovered 2026-06-22 Day-35)

Three OC processes (karr_rna_decay.py, karr_protein_decay_light.py, karr_transcription.py)
have an EXPLICITLY DOCUMENTED L2.1 short-circuit: when 	race_hint.substrates_next
is present, the entire biology computation (Poisson sampler, etc.) is bypassed and
substrate deltas are read VERBATIM from the trace.

karr_rna_decay.py:304-314 docstring:
> "L2.1 replay short-circuit: if a substrates trace hint is present, emit exactly
> the per-tick substrate deltas the karr trace recorded for this process. This
> makes the Poisson decay sampler a no-op for the L2.1 harness (which only asserts
> substrates/enzymes/boundEnzymes) while leaving the biology path intact for
> L1 / production use."

## What this means

- L2.1 + L2.2 passed because the trace hint provided ground-truth deltas, hiding
  any drift in the underlying biology sampler.
- L2.5 with Day-34 Fix #2 (decoupling trace_hint from oracle_type) is the FIRST
  validation that exercises the no-hints biology samplers.
- Discovered scale: 14 of 28 processes reference trace_hint; at least 3 have
  documented short-circuits; many more likely have less-explicit hint paths.

## Concrete evidence (RNADecay tick 0)

| WID | Karr produced | OC composition | OC isolated (no-hints biology) |
|---|---:|---:|---:|
| AMP | 20 | 21 | **124 (6.2x over)** |
| ALA | 22 | 17 | **65 (3x over)** |
| FMET | 19 | 16 | **79 (4.2x over)** |
| GLN | 76 | 74 | **387 (5.1x over)** |
| SER | 13 | 19 | **120 (9.2x over)** |

OC's RNADecay Poisson sampler decays 3-9x more RNAs than Karr did. The L2.1
short-circuit replaced this with the exact trace delta, hiding the bug.

## Why composition is closer to Karr than isolation

Composition (Seg ran first): RNADecay's emit is much closer to Karr (off by 1-6).
Isolation (just RNADecay): wildly over.

Hypothesis: composition's overlay or H6 mutation-preservation logic happens to
write some RNA counts that suppress RNADecay's sampler activity. Need to verify.

## Attack surface implications

The 11 Seg-pair-failure list (scripts/probe_seg_pair_audit.py, commit 678928c)
is now the L2.5 attack surface. Each entry needs honest-mode validation of its
biology sampler. Many likely need Karr-faithful biology ports (like the DNAS
canary on Day-33). A few may just need calibration tuning.

## Recommended next-day plan

1. Survey all 14 trace_hint-using processes for "short-circuit" patterns. Document
   in a table: per-process, what does the no-hints branch actually compute?
2. For each, classify: TINY-DRIFT (RNG/calibration), MEDIUM (missing channels),
   BIG (no biology at all, just hint-driven), CORRECT (no-hints sampler matches Karr).
3. Prioritize fixes by pair-unlock yield (Metabolism unlocks 3 pairs, Transcription unlocks ~4, etc.).

This is a multi-day effort. Don't expect to flip many pairs in one session.
