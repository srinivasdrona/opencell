# DNASupercoiling `linkingNumbers.delta_nnz` N=100 Power Diagnostic — Report

**Status:** diagnostic run complete and reviewed by Opus5. **ACCEPTED as
supplemental, non-gating evidence (Option C)**: the `POWERED_AT_N100` result
below is a genuine, mechanically-applied power finding, but it does **not**
change the canonical evidence-index verdict. The canonical `DNASupercoiling`
row (frozen N=50/M=100, `n_oc=17`/`n_karr=24` on `linkingNumbers.delta_nnz`)
**remains `FAIL` / `PRIMARY_INSUFFICIENT_SAMPLES`** in `evidence_index.json`.
No catalog `N_seeds`, evidence-index, or evidence-bundle sentinel change was
made, and no rerun of the canonical evidence is required or implied by this
diagnostic. This report documents the outcome of the plan pre-registered in
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
| `3954034` | Real extension data provenance note (data itself is gitignored), diagnostic evidence report (`POWER_DIAGNOSTIC_REPORT.json`) + this Markdown summary. |
| *(this commit)* | Opus5-review corrections: fixed `n100_combined` `delta_nnz` raw W1 transcription (0.0100 → 0.0130), added `half_split_b` `delta_value_sum` raw W1, corrected extraction/runtime timestamps from logs, added the Wilson i.i.d.-tick empirical support check, the rate-ratio test, and the W1-insensitivity/`PRIMARY_ACTIVITY_MISSING` discussion. No change to `POWER_DIAGNOSTIC_REPORT.json` (its underlying numbers were already correct; only this Markdown's transcription/discussion was fixed). Removed the 3 untracked `allocator_inputs.json` scratch files. |

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
  only**, 100 ticks. Wall time (from `artifacts/l22_full_extraction/run_state_20260731_074528.json`
  `started_at` and the worker stdout log mtimes, both corrected from the
  original transcription): **07:45:28 → 07:57:41 local (~12.2 min)**, both
  workers exited cleanly, no stderr output. All 50 output files present,
  matching the same size profile as seeds 0-49 (485.1 MB combined).
- **Validation** (`scripts/l22_dnas_power/validate_extension.py`, structural +
  schema-drift-vs-seed-0 + chromosome non-vacuity): **PASS**, zero blockers,
  for all seeds 50-99. Wall time **07:57:41 → 08:11:55 local (~14.2 min)**
  (extraction-end to `POWER_DIAGNOSTIC_REPORT.json`'s `generated_at`, which
  `build_report.py` stamps at invocation start before running the three
  `run_design_a` stages below).
- **Loader diagnostic count:** widened oracle loader reports
  `canonical_seed_count == 100` for `DNASupercoiling` — confirmed.
- **Diagnostic `run_design_a` invocations** (`n50_reproduction`, `n100_combined`,
  `half_split_b`; unmodified harness, `bootstrap_B=1000` matching the harness's
  own default convention). Exact wall times, derived from each stage's
  `result.json` `timestamp` (write-on-completion) chained against the prior
  stage's completion:

  | Stage | Window (local) | Duration |
  |---|---|---|
  | `n50_reproduction` | 08:11:55 → 08:57:53 | ~46.0 min |
  | `n100_combined` | 08:57:53 → 10:07:15 | ~69.4 min |
  | `half_split_b` | 10:07:15 → 10:43:10 | ~35.9 min |
  | **Total (validation + all 3 runs)** | **07:57:41 → 10:43:10** | **~165.5 min** |

  The harness's per-seed chromosome-oracle load is HDF5/sparse-triple-heavy,
  dominating runtime — this is compute cost of the *unmodified* metric at
  larger N, not a diagnostic-tooling inefficiency. (The original report's
  "~9 min" extraction and "~156 min" total figures were transcription
  errors from an earlier, unlogged estimate; the figures above are derived
  directly from `run_state_20260731_074528.json`, worker/seed log mtimes,
  and each stage's `result.json`/`POWER_DIAGNOSTIC_REPORT.json` timestamps.)

## 3. N=50 vs N=100 counts/metrics

| Component | Run | `n_nonzero_oc` | `n_nonzero_karr` | raw W1 | scale | verdict |
|---|---|---|---|---|---|---|
| `linkingNumbers.delta_nnz` | canonical N=50 (`latest/`) | 17 | 24 | 0.0140 | 2.0 | PASS (gated `PRIMARY_INSUFFICIENT_SAMPLES` by evidence-index, both sides < 30) |
| `linkingNumbers.delta_nnz` | `n50_reproduction` (this diagnostic) | 17 | 24 | 0.0140 | 2.0 | PASS — **exact bit-for-bit reproduction** of canonical bundle, confirming harness/baseline fidelity |
| `linkingNumbers.delta_nnz` | `n100_combined` (seeds 0-99) | **31** | **42** | 0.0130 | 2.0 | PASS, **both sides ≥ 30** |
| `linkingNumbers.delta_nnz` | `half_split_b` (seeds 50-99 alone) | 14 | 18 | 0.0120 | 2.0 | PASS |
| `linkingNumbers.delta_value_sum` | canonical N=50 | 4924 | 4961 | 50.386 | 92.0 | PASS |
| `linkingNumbers.delta_value_sum` | `n100_combined` | 9851 | 9920 | 50.840 | 94.0 | PASS |
| `linkingNumbers.delta_value_sum` | `half_split_b` | 4927 | 4959 | 51.293 | 94.0 | PASS |

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

## 4. Wilson i.i.d.-tick assumption: empirical support, rate ratio, and W1 insensitivity

The analytic Wilson-score CI used in §3/§5 treats every one of the
`n_seeds × m_ticks = 10000` `(seed, tick)` pairs as an i.i.d. Bernoulli trial
with a single fixed per-tick nonzero-rate — i.e. it assumes ticks within the
same seed are no more likely to co-occur with an event than ticks across
different seeds. This assumption is checked empirically below rather than
asserted.

**Empirical per-seed clustering check** (Karr-side `linkingNumbers.delta_nnz`,
`n100_combined`, seeds 0-99, recomputed read-only via the existing,
unmodified `load_chromosome_oracle_for_process` / `chromosome_projection_matrix`
helpers — `scripts/l22_dnas_power/verify_n100_empirical_diagnostics.py`):

- **42 total nonzero-tick events**, distributed across **37 of the 100
  seeds** (32 seeds with exactly 1 event, 5 seeds with 2 events: seeds 5, 36,
  46, 47, 90).
- Under the i.i.d.-per-tick Bernoulli(p) null with `p = 42/10000 = 0.0042`
  (the same rate the Wilson CI itself uses), the expected number of seeds
  with ≥1 event is **34.35** and with ≥2 events is **6.67** (exact Binomial(100,
  0.0042) calculation, `iid_tick_clustering_expectation`) — vs. the observed
  **37** and **5**. Both observed counts fall within ordinary sampling
  variation of the null expectation (no excess within-seed clustering
  detected), which **supports** treating the per-tick trials as
  approximately i.i.d. for the purpose of the analytic CI used in §5.

**Rate ratio (OC vs. Karr, `n100_combined` `linkingNumbers.delta_nnz`):**
with `n_oc=31`, `n_karr=42` over the same 10000 trials on each side, the
log-rate-ratio Wald test (`rate_ratio_stats`) gives:

- **ratio = 0.738** (95% CI **[0.464, 1.174]**), **z = −1.28**, **p = 0.20**
  (two-sided, H0: rate ratio = 1). Not statistically significant at α=0.05 —
  consistent with no detectable OC/Karr rate difference, matching the
  sibling `delta_value_sum` channel's own no-difference story (rate z≈1.1).

**W1 insensitivity bound.** The joint verdict passing at N=100 should *not*
be read as strong evidence of OC/Karr equivalence on this component, because
the raw-W1 pass/fail is nearly insensitive to whether OC has *any* activity
at all: for two equal-size (N=10000) 1D empirical distributions, the
sorted-to-sorted (quantile) coupling is W1-optimal, so if OC were
identically zero on this component (`n_nonzero_oc = 0`, a fully degenerate
case), `W1(OC, Karr)` would equal exactly `mean(|karr_delta_nnz values|) =
84.0 / 10000 = 0.0084` — **≈238× below** the raw pass threshold of `2.0`
(`component_scales.linkingNumbers.delta_nnz = 2.0` × `scaled_distance_threshold
= 1.0`). The joint verdict would therefore still read **PASS** even with
**zero** OC-side activity on this component. This is why the real
load-bearing guard against that degenerate case is **not** the W1
threshold — it is `PRIMARY_ACTIVITY_MISSING`
(`scripts/l22_evidence/schema.py:615`, `scripts/l22_evidence/verdict.py`),
which is checked **before** the distance computation
(`EVIDENCE_INDEX_SPEC.md` §13.14) and fires whenever a primary component has
zero nonzero observations on OC while Karr has any. `PRIMARY_ACTIVITY_MISSING`
did not fire here (OC has 31/17 nonzero events at N=100/N=50 respectively),
but the bound above shows the W1 pass by itself carries little discriminating
power at this event density — `PRIMARY_INSUFFICIENT_SAMPLES` (the actual
canonical-gate reason) is the correct, more conservative guard for this
sample regime, and remains in force in the canonical N=50 evidence-index row.

**Explicit conclusion:** `POWERED_AT_N100` is a real, mechanically-applied
diagnostic result — supplemental only. It does not supersede or weaken the
canonical evidence-index verdict: the `DNASupercoiling` row **remains `FAIL`
/ `PRIMARY_INSUFFICIENT_SAMPLES`** at the frozen N=50/M=100 catalog. No
catalog `N_seeds` change and no rerun of the canonical evidence are made or
implied by this diagnostic.

## 5. Power decision (pre-reg §4, applied mechanically)

- `n100_combined.linkingNumbers.delta_nnz`: `n_nonzero_oc=31 >= 30` **and**
  `n_nonzero_karr=42 >= 30` → **rule 1 satisfied**.
- Per rule 1, the unmodified metric/threshold/null was then evaluated: joint
  verdict **PASS**.

**Decision: `POWERED_AT_N100`, mechanical metric verdict `PASS`.**

## 6. Disclosed deviation from pre-reg §4's descriptive text

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

## 7. Recommended integration mechanism — Opus5 decision: Option C (accepted)

Per pre-reg §5, since the primary channel is now powered and passes at N=100,
two integration options were originally proposed (not implemented):

- **(a) Bump `DNASupercoiling`'s catalog `N_seeds: 50 → 100`** with a
  process-scoped catalog-hash/evidence-hash update, i.e. a change that is
  auditably scoped to this one process's row and does not implicitly re-stale
  every other process's evidence in `PROCESS_CATALOG.yaml`.
- **(b) Publish this diagnostic as a supplemental power artifact** referenced
  from `DNASupercoiling`'s catalog `notes` field, without changing `N_seeds`
  at all.

**Opus5 review outcome: neither (a) nor (b) as originally scoped — Option C,
supplemental/non-gating, is ACCEPTED.** This diagnostic (this report +
`POWER_DIAGNOSTIC_REPORT.json` + the underlying `diagnostic_n100/` evidence)
stands as a committed, reviewed supplemental power artifact. Concretely:

- **No catalog `N_seeds` change** — `PROCESS_CATALOG.yaml`'s `DNASupercoiling`
  row is untouched (option (a) is explicitly **not** adopted at this time).
- **No `evidence_index.json` change** — the canonical verdict for
  `DNASupercoiling` remains `FAIL` / `PRIMARY_INSUFFICIENT_SAMPLES`.
- **No rerun of canonical evidence** — `evidence_bundle/DNASupercoiling/latest/`
  and its sentinel are untouched.
- The diagnostic is retained under `evidence_bundle/DNASupercoiling/diagnostic_n100/`
  as an auditable, reproducible artifact (this is closer to option (b) in
  effect, but is not itself referenced from a catalog `notes` field as a
  gating-adjacent annotation — that linkage, if wanted, is a separate future
  decision for the planner, not made here).

This diagnostic is now **closed**. Any future change to the canonical
catalog/evidence-index status for `DNASupercoiling` requires a new,
explicit planner/reviewer decision — it is not implied or pre-authorized by
this report.

## 8. Tests

29 new unit tests (5 files under `tests/scripts/test_l22_dnas_power_*.py`,
covering `power_decision`, `copy_baseline_seeds`, `validate_extension`,
`diagnostic_runner`, `build_report`), all passing under `bin\oc-pytest`.
`tests/scripts --collect-only` (668 tests total) confirms no import-time
regressions from the new `scripts/l22_dnas_power/` package.

This Opus5-review correction adds a 6th test file,
`tests/scripts/test_l22_dnas_power_empirical_diagnostics.py` (7 tests),
covering the pure math in `scripts/l22_dnas_power/verify_n100_empirical_diagnostics.py`
(i.i.d.-tick clustering expectation, the exact zero-side W1 bound, and the
log-rate-ratio Wald test/CI) — including regression tests that pin the
exact figures cited in §4 above against the real N=100 data. 36 tests total
across the package, all passing.

## 9. Constraints honored

No edits were made to: `opencell/vivarium/karr_dna_supercoiling.py` (DNASupercoiling
biology), Design-A metric/threshold/null code
(`tests/vivarium/l2_2_design_a_runner.py`, `_l2_2_design_a_projections.py`,
`_l2_2_design_a_runner_helpers.py`), `PROCESS_CATALOG.yaml`,
`evidence_index.json`, the canonical `evidence_bundle/DNASupercoiling/latest/`
bundle/sentinel, or the existing accepted seeds 0-49 raw `.mat` traces (copied
read-only, hash-verified). All diagnostic artifacts live under
`evidence_bundle/DNASupercoiling/diagnostic_n100/`.
