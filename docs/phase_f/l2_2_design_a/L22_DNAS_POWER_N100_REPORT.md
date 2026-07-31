# DNASupercoiling `linkingNumbers.delta_nnz` N=100 Power Diagnostic — Report

**Status:** diagnostic run complete. This report documents the outcome of the
plan pre-registered in
[`L22_DNAS_POWER_PREREG.md`](L22_DNAS_POWER_PREREG.md) (committed before any
seed-50-99 extraction). The decision rule stated there was applied
mechanically, unmodified, to the real result below.

**Branch:** `agent/l22-dnas-power` (worktree `E:\opencell-worktrees\l22-dnas-power`)
**Diagnostic artifacts:** `evidence_bundle/DNASupercoiling/diagnostic_n100/`
(`n50_reproduction/`, `n100_combined/`, `half_split_b/`, `POWER_DIAGNOSTIC_REPORT.json`)
— **not** the canonical `latest/` bundle; `evidence_index.json`, catalog `N_seeds`/`M_ticks`,
and the accepted seeds 0-49 raw traces were not touched.

## 1. Commits

| Commit | Contents |
|---|---|
| `29cbd35` | Pre-registration spec + `scripts/l22_dnas_power/` tooling (copy_baseline_seeds, diagnostic_runner, power_decision, validate_extension, build_report) + 29 unit tests. Landed **before** the MATLAB run, per pre-reg §6. |
| *(this commit)* | Real extension data provenance note (data itself is gitignored), diagnostic evidence report (`POWER_DIAGNOSTIC_REPORT.json`) + this Markdown summary. |

## 2. Extraction / runtime

- **Baseline seeds 0-49:** copied (not regenerated) from `l22-final-sweep`'s
  `data/m1_sources/karr_native/`, `DNASupercoiling_100ticks.mat` only, all 50
  files hash-verified bit-identical to source
  (`scripts/l22_dnas_power/copy_baseline_seeds.py`, `copied=50 skipped_identical=0`,
  no verification failures). Total 485.1 MB.
- **Extension seeds 50-99:** generated with the existing, unmodified
  `scripts/matlab/extract_per_process_traces_v2.m` via
  `scripts/l22_extraction/launcher.py` + `scripts/matlab/run_l22_seed_shards.ps1`,
  2 bounded MATLAB workers (25 seeds each, round-robin), **DNASupercoiling
  only**, 100 ticks. Wall time: **~9 minutes** (launched → both workers exited
  cleanly, 08:45:28 → ~08:54, no stderr output). All 50 output files present,
  matching the same size profile as seeds 0-49 (485.1 MB combined).
- **Validation** (`scripts/l22_dnas_power/validate_extension.py`, structural +
  schema-drift-vs-seed-0 + chromosome non-vacuity): **PASS**, zero blockers,
  for all seeds 50-99.
- **Loader diagnostic count:** widened oracle loader reports
  `canonical_seed_count == 100` for `DNASupercoiling` — confirmed.
- **Diagnostic `run_design_a` invocations** (`n50_reproduction`, `n100_combined`,
  `half_split_b`; unmodified harness, `bootstrap_B=1000` matching the harness's
  own default convention): **~156 minutes** wall time total (validation ~14 min
  + n50 run ~32 min + n100 run ~69 min + half_split_b run ~36 min; the harness's
  per-seed chromosome-oracle load is HDF5/sparse-triple-heavy, dominating
  runtime — this is compute cost of the *unmodified* metric at larger N, not a
  diagnostic-tooling inefficiency).

## 3. N=50 vs N=100 counts/metrics

| Component | Run | `n_nonzero_oc` | `n_nonzero_karr` | raw W1 | scale | verdict |
|---|---|---|---|---|---|---|
| `linkingNumbers.delta_nnz` | canonical N=50 (`latest/`) | 17 | 24 | 0.0140 | 2.0 | PASS (gated `PRIMARY_INSUFFICIENT_SAMPLES` by evidence-index, both sides < 30) |
| `linkingNumbers.delta_nnz` | `n50_reproduction` (this diagnostic) | 17 | 24 | 0.0140 | 2.0 | PASS — **exact bit-for-bit reproduction** of canonical bundle, confirming harness/baseline fidelity |
| `linkingNumbers.delta_nnz` | `n100_combined` (seeds 0-99) | **31** | **42** | 0.0100 | 2.0 | PASS, **both sides ≥ 30** |
| `linkingNumbers.delta_nnz` | `half_split_b` (seeds 50-99 alone) | 14 | 18 | 0.0120 | 2.0 | PASS |
| `linkingNumbers.delta_value_sum` | canonical N=50 | 4924 | 4961 | 50.386 | 92.0 | PASS |
| `linkingNumbers.delta_value_sum` | `n100_combined` | 9851 | 9920 | 50.840 | 94.0 | PASS |
| `linkingNumbers.delta_value_sum` | `half_split_b` | 4927 | 4959 | — | — | PASS |

`n100_combined` joint (chromosome-channel) verdict: **PASS** (both primary
components clear the unmodified, unchanged `scaled_distance_threshold=1.0`).

**Rate-projection consistency check** (Wilson-score 95% CI on the N=50-observed
per-tick nonzero rate, projected to N=100 trials, vs the actual N=100 count —
see §5 for why this analytic approach was used instead of the bootstrap
resampling described in the pre-reg text):

| Component / side | Observed @N=50 | Projected @N=100 (95% CI) | Actual @N=100 | Within CI? |
|---|---|---|---|---|
| `delta_nnz` / OC | 17 | 34 (21.2 – 54.4) | 31 | **Yes** |
| `delta_nnz` / Karr | 24 | 48 (32.3 – 71.3) | 42 | **Yes** |
| `delta_value_sum` / OC | 4924 | 9848 (9810.2 – 9878.4) | 9851 | Yes |
| `delta_value_sum` / Karr | 4961 | 9922 (9893.6 – 9942.9) | 9920 | Yes |

All four actual N=100 counts fall inside the rate-projected 95% interval from
N=50 — consistent with i.i.d. seed extension (no schema drift, no anomalous
generation batch effect between seeds 0-49 and 50-99).

**Seed half-split stability** (`half_split_a` == `n50_reproduction`, seeds
0-49, vs `half_split_b`, seeds 50-99, each run **independently**, not
combined): `delta_nnz` raw W1 is 0.0140 (half A) vs 0.0120 (half B) — both
`PASS`, same order of magnitude, no discontinuity between the two seed
batches.

## 4. Power decision (pre-reg §4, applied mechanically)

- `n100_combined.linkingNumbers.delta_nnz`: `n_nonzero_oc=31 >= 30` **and**
  `n_nonzero_karr=42 >= 30` → **rule 1 satisfied**.
- Per rule 1, the unmodified metric/threshold/null was then evaluated: joint
  verdict **PASS**.

**Decision: `POWERED_AT_N100`, mechanical metric verdict `PASS`.**

## 5. Disclosed deviation from pre-reg §4's descriptive text

The pre-reg's §4 narrative mentions "a bootstrap CI on `linkingNumbers.delta_nnz`'s
raw W1 (resampling seeds with replacement, B=1000)" as a supplementary
uncertainty characterization (this is *not* part of the binary decision rule
itself, which only requires the `n_nonzero >= 30` mechanical check in rule 1/2,
applied above unchanged). In practice, `power_decision.py` implements an
**analytic Wilson-score CI on the per-tick nonzero rate/count** (§3 table
above) instead of literally resampling seeds and re-running `run_design_a` per
bootstrap replicate. This substitution was made because `run_design_a` does
not expose the raw `(seed, tick, component)` tensors externally, and
reimplementing the harness's internal tick-loop/tensor extraction to support
resampling risked silently diverging from the real, unmodified metric — which
the task and pre-reg both forbid. The analytic approach is a standard,
defensible substitute for the same purpose (characterizing whether the
observed count growth from N=50 to N=100 is consistent with i.i.d. seed
extension) and required no re-simulation. `run_design_a`'s own unmodified
`bootstrap_B=1000` null-calibration (used elsewhere in the harness, e.g. the
`substrates` channel) was still invoked unchanged for every run in this
diagnostic. **Flagging this as a documented deviation for Opus5 review**, since
it is a change in *how uncertainty was characterized*, not in the pre-registered
go/no-go decision rule or the underlying metric/threshold.

## 6. Recommended integration mechanism

Per pre-reg §5, since the primary channel is now powered and passes at N=100,
the two proposed (not implemented) options are:

- **(a) Bump `DNASupercoiling`'s catalog `N_seeds: 50 → 100`** with a
  process-scoped catalog-hash/evidence-hash update, i.e. a change that is
  auditably scoped to this one process's row and does not implicitly re-stale
  every other process's evidence in `PROCESS_CATALOG.yaml`.
- **(b) Publish this diagnostic as a supplemental power artifact** referenced
  from `DNASupercoiling`'s catalog `notes` field, without changing `N_seeds`
  at all.

**Recommendation: (a)**, because the underpowering was on a genuinely
under-sampled primary component (not a borderline distributional call), the
N=100 extension is a clean seed-count increase using the same unmodified
extractor/metric with no schema drift (§3), and the frozen N=50 evidence is
otherwise sound (raw W1/verdict essentially unchanged, `0.0140 → 0.0100`) — a
catalog bump is the more durable fix than a supplemental-artifact footnote,
provided it is implemented as a process-scoped hash update rather than a
blanket `PROCESS_CATALOG.yaml` re-hash. **This recommendation is not
implemented by this diagnostic** and requires Opus5/planner sign-off before
any catalog, evidence-bundle, or evidence-index edit is made.

## 7. Tests

29 new unit tests (5 files under `tests/scripts/test_l22_dnas_power_*.py`,
covering `power_decision`, `copy_baseline_seeds`, `validate_extension`,
`diagnostic_runner`, `build_report`), all passing under `bin\oc-pytest`.
`tests/scripts --collect-only` (668 tests total) confirms no import-time
regressions from the new `scripts/l22_dnas_power/` package.

## 8. Constraints honored

No edits were made to: `opencell/vivarium/karr_dna_supercoiling.py` (DNASupercoiling
biology), Design-A metric/threshold/null code
(`tests/vivarium/l2_2_design_a_runner.py`, `_l2_2_design_a_projections.py`,
`_l2_2_design_a_runner_helpers.py`), `PROCESS_CATALOG.yaml`,
`evidence_index.json`, the canonical `evidence_bundle/DNASupercoiling/latest/`
bundle/sentinel, or the existing accepted seeds 0-49 raw `.mat` traces (copied
read-only, hash-verified). All diagnostic artifacts live under
`evidence_bundle/DNASupercoiling/diagnostic_n100/`.
