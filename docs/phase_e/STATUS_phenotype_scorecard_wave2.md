# STATUS — phenotype scorecard wave2 baseline

## 4-seed PASS counts

| Seed | Trajectory | PASS | FAIL | BLOCKED |
|---|---|---:|---:|---:|
| 42 | artifacts/ensemble_wave2_20260527_023611/seed_42/trajectory.pkl | 6 | 14 | 8 |
| 43 | artifacts/ensemble_wave2_20260527_023611/seed_43/trajectory.pkl | 6 | 14 | 8 |
| 44 | artifacts/ensemble_wave2_20260527_023611/seed_44/trajectory.pkl | 6 | 14 | 8 |
| 45 | artifacts/ensemble_wave2_20260527_023611/seed_45/trajectory.pkl | 6 | 14 | 8 |

## Pre-fix -> wave2 wins

- No KP moved from FAIL/BLOCKED to PASS in this wave2 baseline snapshot.
- Net movement versus pre-fix baseline: KP20 regressed from PASS to FAIL (`threshold_max exceeded`).

## Still FAIL or BLOCKED (seed 43 baseline)

- KP01 FAIL: tolerance exceeded.
- KP02 FAIL: extractor returned NaN/non-finite value.
- KP03 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP03-FLUX-ORACLE).
- KP04 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP04-TX_GLCPTS).
- KP06 FAIL: tolerance exceeded.
- KP10 FAIL: tolerance exceeded.
- KP11 FAIL: extractor returned NaN/non-finite value.
- KP12 FAIL: extractor returned NaN/non-finite value.
- KP13 FAIL: ratio out of [0.4, 2.5].
- KP14 FAIL: below minimum threshold.
- KP15 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP15-DNA-OCCUPANCY).
- KP16 FAIL: tolerance exceeded.
- KP17 FAIL: tolerance exceeded.
- KP18 FAIL: tolerance exceeded.
- KP19 FAIL: tolerance exceeded.
- KP20 FAIL: threshold_max exceeded.
- KP21 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP21-ENERGY-LEDGER).
- KP22 FAIL: qualitative boolean mismatch.
- KP25 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP25-KO-SWEEP).
- KP26 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP26-KO-CLASS).
- KP27 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP27-HOST-ADHESION).
- KP28 BLOCKED: extractor unavailable for emitted schema (E2-V1_1-KP28-HOST-IMMUNE-CASCADE).

## Stability across seeds

- Stable (status): all 28 KPs are status-stable across seeds 42-45 (no PASS/FAIL/BLOCKED flips).
- Swingy (numeric, but status-stable): KP07 varied from 0.000595 to 0.00227 (~3.81x spread) and stayed PASS under threshold_max 0.1.

## Files changed and commits

- `b3089b8` — `opencell/validation/phenotype_scorecard.py` (`--trajectory` CLI override).
- `bbc8cf1` — `docs/phase_e/E2_scorecard_wave2.md` (seed-43 post-wave2 baseline table).
- `b53acf0` — `docs/phase_e/E2_scorecard_wave2.md` (cross-seed comparison addendum).
- `HEAD` — `STATUS_phenotype_scorecard_wave2.md` (this STATUS summary commit).

## Methods-paper claim recommendation

The wave2 baseline currently reproduces 6 of 28 Karr-linked phenotypes within the published scorecard tolerances, consistently across all four ensemble seeds. This run is therefore useful as a post-wave2 reproducibility baseline, but not yet as evidence of broad phenotype closure. The paper should claim stable baseline behavior and transparent gap accounting, and treat the remaining 22 FAIL/BLOCKED KPs as explicit follow-on work items.
