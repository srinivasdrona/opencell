# L2.5 SS clean-vs-clean pair results (Day-35 EOD)

**Test file:** `tests/vivarium/test_l25_stochastic_stochastic_clean_pairs.py`
**Run:** 56 pairs, single seed (rng_seed_0), 2:39 wall-time
**Date:** 2026-06-22 14:35 IST

## Top-line numbers

| Verdict | Count | % |
|---|---:|---:|
| ✅ PASS | **7** | 13% |
| ❌ FAIL | **15** | 27% |
| ⚪ SKIPPED | **34** | 61% |
| **Total** | **56** | 100% |

Testable today (PASS+FAIL=22): **7 PASS / 15 FAIL = 32% honest-green rate**.

Significantly lower than the DS clean-vs-clean (71% green). The SS sweep
surfaces real composition-time bugs that didn't appear in DS because the
deterministic ChromosomeSegregation runs first under the canonical
composition order and doesn't conflict with the protein/RNA biology samplers.

## The 7 PASSes

- ProteinFolding + ProteinProcessingI
- ProteinFolding + RNAProcessing
- ProteinFolding + tRNAAminoacylation
- ProteinProcessingI + tRNAAminoacylation
- ProteinProcessingI + RNAProcessing
- ProteinProcessingII + RNAProcessing
- ProteinProcessingII + tRNAAminoacylation

Notable: **none involve DNARepair, ProteinTranslocation, MacromolecularComplexation, or DNADamage**.

## The 15 FAILs — grouped by hidden-broken process

| Process suspected of hidden honest-mode bug | # FAIL pairs | Pairs |
|---|---:|---|
| **ProteinTranslocation** | 6 | F+T, ProcI+T, ProcII+T, T+RNAProc, T+tRNA, DNARepair+T |
| **DNARepair** | 6 | DNARepair+{tRNA, F, T, RNAProc, ProcI, ProcII} |
| Other | 3 | MacromolComplex+F, ProcI+ProcII, F+ProcII, RNAProc+tRNA |

## Concrete bug signature: ProteinFolding + ProteinTranslocation

Failure record extracted from `oc-pytest --tb=line`:

```json
{
  "cause_code": "CAUSE_4_UPSTREAM_STATE_POLLUTION",
  "process": "ProteinTranslocation",
  "upstream_processes": ["ProteinFolding"],
  "isolated_replay_result": "matches_oracle",  ← KEY
  "oc_counterfactual_compare": [0,0,0,0,0,0,0],  ← ALSO KEY
  "tick": 21,
  "observable": "substrates",
  "diff": -14.0,
  "oc_compare": [-14, 0, +14, 0, +14, -14, +14],
  // ordered [ATP, GTP, ADP, GDP, H, H2O, PI]
}
```

**Reading:**
- ProteinTranslocation's biology runs correctly in isolation (`matches_oracle`).
- When ProteinFolding runs first in composition, ProteinTranslocation
  produces **14 extra ATP hydrolyses** at tick 21.
- The delta vector `[-14, 0, +14, 0, +14, -14, +14]` is a canonical
  ATP hydrolysis: `ATP + H2O → ADP + PI + H`, 14 events.
- This is NOT a sampler bug. It's an **allocator-shared-pool composition
  bug**: the allocator is giving ProteinTranslocation a different ATP
  budget in composition than in isolation.

This is exactly the bug class the short-circuit audit could not predict —
it requires composition + honest mode + a specific ordering to surface.

## The 34 SKIPs

A 61% skip rate is high. Pattern: most skips involve Cytokinesis,
DNADamage, or RibosomeAssembly. These are typically "no-op trace /
sparse-event" skips from the harness — the trace window has too few events
of the relevant type to make a distributional comparison meaningful.

**Action**: walk the 34 skips to identify which can be unblocked by widening
the event-window scan or adjusting skip thresholds. Each unblocked SKIP is
a candidate for a new honest PASS or a newly-discovered FAIL.

## Comparison to predictions

| Prediction | Reality |
|---|---|
| ~63% honest-green rate (DS extrapolation) | 32% on the testable SS subset |
| ~40 more PASSes | 7 PASSes (15 if skips are unblocked at same 32% rate) |
| Total L2.5 ceiling ~48 | Today 15 (8 prior + 7 new); ceiling closer to 25-30 once skips clear |

The discrepancy says: **composition-time bugs are real and the audit only
caught the easy ones (short-circuits).** The honest L2.5 gate is exposing
a new class of bugs that were always there but invisible under L2.1/L2.2.

## Next-step priorities

1. **Diagnose ProteinTranslocation composition bug** — single root cause may
   unlock 6 SS pairs (and the prior Seg+ProteinTranslocation DS fail).
   Allocator-side investigation, not biology port.
2. **Diagnose DNARepair composition bug** — same shape; another 6+1 unlock
   if the bug class is similar.
3. **Unblock the 34 SKIPs** — walk the harness skip path; likely a single
   threshold parameter or event-window adjustment.
4. **Then** the 3 stragglers: MacromolComplex+F, ProcI+ProcII, F+ProcII,
   RNAProc+tRNA — these need per-pair analysis.

If steps 1+2 unlock ~12 pairs and the skip walk unlocks half the SKIPs at
the same 32% green rate, the total L2.5 honest PASSes could reach
**25-30 / 256** without porting any of the 13 short-circuited samplers.

## Provenance

- Test file: `tests/vivarium/test_l25_stochastic_stochastic_clean_pairs.py`
- Source of pair list: `docs/phase_f/L2_5_CLEAN_CLEAN_PAIRS.md` (Day-35 audit)
- Harness: `tests/vivarium/l2_2_replay_common_v2.py::run_integrated_replay_v2`
- Skip cause: harness-level (`l25_no_op_trace` / `sparse_event` paths)
