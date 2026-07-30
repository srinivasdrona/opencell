# H12 Evidence Report: 5 `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` rows

Worktree `E:\opencell-worktrees\l22-h12`, branch `agent/l22-h12`, frozen
baseline `0e6ddaf`. This report accompanies the commits adding
`scripts/l22_evidence/h12.py`, its tests, the 5 generated H12 evidence
artifacts, the `h12_evidence_index.json` side-index wiring, and the
strengthened `verdict.py` gate. See
`docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md` Section 13.14 for the
full technical writeup this report summarizes.

## Task

Five catalog rows (`MacromolecularComplexation`, `ProteinFolding`,
`ProteinProcessingI`, `ProteinProcessingII`, `tRNAAminoacylation`) carry a
hand-set `closed_form_dominant=confirmed_biology_validated` flag with no
machine-checked producer. The evidence gate correctly demotes their
`PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` warning to non-green without
one. This task's job: produce that producer honestly, or report failure.

## Method summary (anti-laundering)

For each process, the closed-form prediction is transcribed directly from
the Karr MATLAB source (`data/m1_sources/WholeCell/src/+edu/.../+process/*.m`)
plus static fixture parameters (`data/karr_fixtures/per_process/*_flat.mat`)
plus `states_before` only — never from the OC vivarium port, the runner,
`states_after`, or any `result.json`/oracle output. Predictions are frozen
in memory (and in the artifact's `raw_prediction_hash`) before `after` is
touched at all; a separate `compare_predictions()` function is the sole
reader of `states_after`, invoked only in a distinct comparison phase.
This is enforced by a static AST guard
(`tests/scripts/test_h12_anticheat.py`, 15 tests) over every predictor
function's source — not just a convention.

## Results — all 5 processes: `H12_CONFIRMED`, 100% exact match, no tolerance

Run against real oracle `.mat` trace data at each process's actual catalog
`N_seeds`/`M_ticks`, in the task's mandated highest-risk-first order:

| Process | seeds × ticks | total samples | nontrivial samples | exact matches | match rate | verdict |
|---|---|---|---|---|---|---|
| tRNAAminoacylation | 50 × 50 | 2500 | 2500 | 2500 | 100% | H12_CONFIRMED |
| ProteinProcessingII | 50 × 20 | 1000 | 560 | 560 | 100% | H12_CONFIRMED |
| ProteinFolding | 50 × 100 | 5000 | 2639 | 2639 | 100% | H12_CONFIRMED |
| MacromolecularComplexation | 50 × 100 | 10000 | 814 | 814 | 100% | H12_CONFIRMED |
| ProteinProcessingI | 50 × 20 | 1000 | 635 | 635 | 100% | H12_CONFIRMED |

"Nontrivial" samples are those where the closed-form regime's guard
conditions hold (i.e., where the catalog's determinism claim actually
applies at that tick/seed); "trivial" samples (guard fails, e.g. no
substrate available) are still predicted and still compared, they simply
fall outside the regime the catalog claims is closed-form. No tolerance
was applied anywhere — even a single mismatch out of hundreds would be a
hard `H12_FAIL` (verified directly:
`test_h12_artifact.py::test_compare_predictions_single_mismatch_out_of_100_fails_no_tolerance`).
None of the 5 processes' MATLAB source defines a pre-registered
integer/float tolerance, so none was assumed.

## Methodology caveats

1. **MacromolecularComplexation's genuinely-stochastic branch is
   formula-complete but empirically unexercised.** The predictor handles
   three regimes: network-size-1 (closed-form exact), network-size-≥2
   with all-zero sampling bounds (deterministic by construction), and
   network-size-≥2 with a nonzero sampling bound (genuinely Monte-Carlo,
   excluded from the "nontrivial" count by design, since no closed-form
   prediction is claimed there). In the available 50-seed oracle dataset,
   the third regime never fires — every sample lands in one of the first
   two. This means the 100% match result, while real and honestly
   reported, does not exercise the boundary the catalog's determinism
   claim is most likely to be doubted at. A future oracle re-run with
   different substrate/seed conditions could, in principle, land samples
   in that third regime; the predictor correctly excludes them from
   "nontrivial" if it ever does.
2. **These 5 rows do not turn green in `evidence_index.json` as a direct
   result of this work.** Strengthening `h12_support_reason()` required
   bumping `EVALUATOR_SCHEMA_VERSION` 2→3 (adding hash-freshness checks on
   the H12 artifact's recorded predictor/fixture paths). This correctly
   stales every already-generated `sweep_provenance.json` in the repo
   (all 22 in-scope processes), so all rows — including these 5 — now
   read `STALE_SWEEP_PROVENANCE` rather than their prior reason, pending
   an actual `sweep.py run` re-execution. That rerun is out of this
   task's scope ("no expensive OC sweeps"). What *is* proven, mechanically
   and reproducibly, is that the H12-support half of the gate is now
   genuinely satisfied for all 5 rows — the `SENTINEL_FAIL: ... without a
   machine-checked h12_evidence_ref` reason that applied to all 5 before
   this work is gone.
3. **Pre-existing, unrelated bug (not introduced, not fixed):**
   `tRNAAminoacylation`'s row independently fails `PRIMARY_CHANNEL_VACUOUS`
   — the catalog's declared `primary_channel` (`rnas`) doesn't match the
   actual channel key in its `result.json` (`RNAs`, different casing).
   Confirmed present on the untouched pristine baseline via `git stash`.
   Flagged for the maintainer; not fixed here (catalog edit, out of
   scope).
4. **Pre-existing, unrelated baseline test drift (not introduced, not
   fixed):** 4 tests across `test_l22_evidence_generator.py`/
   `test_l22_evidence_portability.py` fail with hardcoded-tally mismatches
   against the real committed `evidence_bundle`/`evidence_index.json`
   tree — confirmed present on pristine `0e6ddaf` via `git stash`, before
   any change in this session. Not touched.

## Catalog demotion recommendation

Based on these results (100% exact match, no tolerance, across all
nontrivial samples at full catalog scale, for all 5 processes), **no
`closed_form_dominant` demotion appears warranted**. This is a
non-binding observation only — per the task's explicit instruction, any
actual demotion decision is left to the reviewer/maintainer, and no
catalog file was edited in this work.

## What was NOT done (explicitly out of scope)

- No `PROCESS_CATALOG.yaml`, runner, biology, or threshold edits.
- No OC sweep re-run (would clear `STALE_SWEEP_PROVENANCE` but is an
  "expensive OC sweep").
- No fix to the pre-existing `tRNAAminoacylation` casing bug or the
  pre-existing baseline test drift (both unrelated, both flagged above).
- No `git push` (worktree-local commits only, per task instruction).

## Verification performed

- All 5 processes re-run against real oracle data end-to-end
  (`H12_CONFIRMED`, 100% match) — see the 5 tracked JSON artifacts.
- `tests/scripts/test_h12_anticheat.py` (15), `test_h12_formulas.py` (11),
  `test_h12_artifact.py` (6), `test_h12_evidence_wiring.py` (11) — new,
  all passing.
- `tests/scripts/test_l22_evidence_verdict.py` (73, including 5 new + 2
  rewritten H12 tests) — all passing.
- `tests/scripts/test_l22_evidence_anticheat.py` (50, including 1 fixed
  pre-existing test whose fixture used the old, weaker H12 payload shape)
  — all passing (full run takes ~15 minutes due to heavy per-test I/O;
  confirmed genuinely progressing, not hung).
- Verified via `git stash` isolation that: (a) the `SENTINEL_FAIL:
  ...h12_evidence_ref` reason is present for all 5 rows on pristine
  baseline and absent after wiring; (b) the 4 generator/portability test
  failures and the tRNAAminoacylation casing bug both pre-exist on
  pristine baseline, unrelated to this work.
- Verified the `decide_verdict()` refactor (verdict-decision logic
  extracted out of `run_h12` into a standalone testable function) is
  behavior-preserving by diffing a fresh re-run's verdict/
  `raw_prediction_hash`/`nontrivial_sample_count`/`exact_match_rate`
  against the already-committed `tRNAAminoacylation` artifact — identical.
