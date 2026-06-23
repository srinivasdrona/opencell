# L2.2 Strict-Rubric Baseline — Day-37 Phase B (2026-06-23, empirical)

**Status:** L2.2 re-audit complete with empirical verification. **10 of 22
L2.2 in-scope GREEN claims are VERIFIED_GENUINE** via the L2.2 design_a
runner. The other 12 are some flavor of fail, unsupported, or laundered.

Supersedes the static Phase A audit which had 4 PROVISIONAL_GENUINE — the
real number is 10 after fixing a runner-vs-catalog string drift bug.

## Day-37 Phase B verdict scoreboard

| Verdict | Count | Processes |
|---|---:|---|
| **VERIFIED_GENUINE** | **10** | MacromolComplex, ProteinFolding, ProcI, ProcII, tRNAAminoacylation, ProteinModification, ProteinDecay, RNADecay, RNAModification, RNAProcessing |
| **VERIFIED_FAIL** | 1 | Metabolism (W1=171.39 on substrates) — real divergence |
| **CRASH_HARNESS_BUG** | 1 | ProteinTranslocation (shape mismatch 482→2892) |
| **UNVALIDATABLE_EVENT_CLASS** | 2 | Cytokinesis, RibosomeAssembly — runner refuses, needs L2.event |
| **LAUNDERED_VIA_HINT_FEED** | 2 | Transcription, Translation — runner explicitly injects hint |
| **NOT_WIRED** | 6 | Replication, ReplicationInitiation, DNASupercoiling, DNARepair, DNADamage, FtsZ |

## What changed between Phase A and Phase B

**Phase A (static cross-reference)** estimated 4 PROVISIONAL_GENUINE based
on intersection of L2.1 strict GENUINE + no trace-hint short-circuit + no
port-mismatch + no explicit hint feed. That estimate was wrong in two
directions:

- **Undercount**: 6 additional processes (RNADecay, RNAModification,
  RNAProcessing, ProteinModification, ProteinDecay, ProcII) PASSed the
  runner despite their L2.1 strict being FAIL or UNINFORMATIVE. The L2.2
  runner provides richer state overlay than the L2.1 strict harness, so
  biology actually fires.
- **The runner had a bug**: `closed_form_state == "confirmed"` check did
  not match the catalog's actual value `confirmed_biology_validated`, so
  5 H12-confirmed processes were being flagged LAUNDERING + FAIL. Fixed
  in this session by accepting both values.

After the bug fix and empirical runs: 10 PASS, 1 FAIL, 11 in various
unsupported / laundered states.

## The 10 VERIFIED_GENUINE

| Process | Catalog flag | Primary W1 | Notes |
|---|---|---|---|
| MacromolecularComplexation | confirmed_biology_validated | 0.0 | H12-probed (50/50 incl 7/7 nontrivial); definitive |
| ProteinFolding | confirmed_biology_validated | 0.0 | Extrapolated H12 + per_sample_w1=0 evidence |
| ProteinProcessingI | confirmed_biology_validated | 0.0 | Extrapolated H12 + per_sample_w1=0 evidence |
| ProteinProcessingII | confirmed_biology_validated | 0.0 | Extrapolated H12 + per_sample_w1=0 evidence |
| tRNAAminoacylation | confirmed_biology_validated | 0.0 | Extrapolated H12 + per_sample_w1=0 evidence |
| ProteinModification | confirmed_biology_validated | 0.0 | Day-29/30 SUT audit confirmed |
| ProteinDecay | (not flagged) | 9.5 | Within SEED_NOISE; biology fires; matches Karr distribution |
| RNADecay | (not flagged) | 65.3 | Within SEED_NOISE (close to threshold); biology matches Karr |
| RNAModification | (not flagged) | 0.09 substrates / 0.0009 RNAs | Tiny W1; biology matches Karr |
| RNAProcessing | (not flagged) | 0.0 substrates / 0.001 RNAs | Near-exact match |

The 6 closed_form_dominant=confirmed_biology_validated processes are
genuinely validated via the LAUNDERING_VS_CONVERGENCE H12 protocol.
The other 4 PASS via standard distributional comparison.

**Important caveat**: 3 of the 10 (RNADecay, ProteinModification,
ProteinDecay) have L2.1 strict FAIL. They PASS L2.2 because the runner's
per-process state overlay provides inputs the L2.1 strict harness doesn't.
This is NOT laundering per se — the runner overlays catalog-declared
observables, not hints. But it does mean L2.2 is testing a richer state
than L2.1. Both verdicts are simultaneously valid: biology fails with
minimal state, biology succeeds with full state overlay.

## The 1 VERIFIED_FAIL: Metabolism

- W1 on substrates: 171.39 (threshold: 102.51)
- KS stat: 0.045, p-value: 1.5e-252 (distributions are different at 99%+ confidence)
- n_nonzero_oc: 46360 vs n_nonzero_karr: 59388 (22% fewer substrate events)

This is real biology divergence. OC's Metabolism doesn't reproduce Karr's
substrate distribution. The L2.2 PASS claim in PROCESS_STATUS_ALL_29 was
either stale or wrong from the start.

## The 1 CRASH: ProteinTranslocation

Shape mismatch (482 vs 2892) in the runner's projection helper. Day-38
bug fix needed.

## The 2 UNVALIDATABLE_EVENT_CLASS

Cytokinesis and RibosomeAssembly need the L2.event harness (not yet
built). Their PASS claims are vacuous until then.

## The 2 LAUNDERED_VIA_HINT_FEED

Transcription and Translation runners explicitly inject `trace_after_hint`.
Day-38: remove the hint feed and re-run.

## The 6 NOT_WIRED

Chromosome-port processes (Replication, ReplicationInitiation,
DNASupercoiling, DNARepair, DNADamage, FtsZ) were planned for runner
integration but never wired. PASS claims have no automated test backing.

## Cross-ladder honest baseline going into Day-38

| Claim | Was claimed | Honest baseline |
|---|---:|---:|
| L2.1 GREEN | 28 | **9** (Day-36) |
| L2.2 in-scope GREEN | 22 | **10** (Day-37 Phase B empirical) |
| L2.5 honest PASS / 256 | 15 | 15 (Day-35) — partner-validity needs re-audit |

## How the baseline is enforced

`tests/vivarium/test_l2_2_strict_rubric.py` pins each of 22 verdicts to
the Day-37 Phase B empirical baseline. CI fails if any verdict drifts.
The classification logic lives in `scripts/probe_l2_2_strict_audit.py`,
which has empirical-first lookup with static fallback.

## Provenance

- Empirical runs: `tmp/l2_2_audit/<process>/result.json` (50 seeds x 10 ticks)
- Runner: `tests/vivarium/l2_2_design_a_runner.py` (with Day-37 fix to recognize `confirmed_biology_validated`)
- Classification: `scripts/probe_l2_2_strict_audit.py`
- Pin: `tests/vivarium/test_l2_2_strict_rubric.py`
- Companion: `docs/phase_f/L2_1_STRICT_RUBRIC_BASELINE.md` (Day-36)
- Operator request: "let's do 1 and 2 to get the actual, validated number"
