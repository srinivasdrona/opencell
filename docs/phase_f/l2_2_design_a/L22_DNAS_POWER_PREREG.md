# DNASupercoiling `linkingNumbers.delta_nnz` N=100-Seed Power Diagnostic — Pre-Registration

**Status:** pre-registered BEFORE any seed-50-99 extraction was run. This document is
committed first; the diagnostic evidence/report that follows must not change the
decision rule stated here.

**Branch:** `agent/l22-dnas-power` (worktree `E:\opencell-worktrees\l22-dnas-power`)
**Companion tooling:** `scripts/l22_dnas_power/` (baseline copy, N=100 diagnostic runner, power decision)

## 1. Why this diagnostic exists

The frozen N=50/M=100 evidence bundle for `DNASupercoiling`
(`docs/phase_f/l2_2_design_a/evidence_bundle/DNASupercoiling/latest/`) is
mechanically `FAIL` in `evidence_index.json`
(`channel_verdicts.chromosome = "PRIMARY_INSUFFICIENT_SAMPLES"`), not because
the primary channel's distributional distance is bad, but because one of its
two primary projection components is under-sampled:

| Primary component (`chromosome`, `per_component_scaled`) | `n_nonzero_oc` | `n_nonzero_karr` | scaled W1 | verdict |
|---|---|---|---|---|
| `linkingNumbers.delta_nnz` | 17 | 24 | 0.007 | `PASS` (raw distance), but **both sides < `MIN_NONZERO_EVENTS=30`** &rarr; `PRIMARY_INSUFFICIENT_SAMPLES` (gating) |
| `linkingNumbers.delta_value_sum` | 4924 | 4961 | 0.548 | `PASS`, densely sampled (rate z ≈ 1.1) |

(Source: `evidence_bundle/DNASupercoiling/latest/result.json` `channels.chromosome.per_component`,
cross-checked against `evidence_index.json` row for `DNASupercoiling`, both read 2026-07-31.)

Per `EVIDENCE_INDEX_SPEC.md` §"Primary channel gating" (`MIN_NONZERO_EVENTS=30`,
either side, gating for the primary channel), the joint verdict is `FAIL` purely
on power, not on distributional mismatch. `delta_nnz` is a discrete per-tick
integer delta (number of distinct sparse `linkingNumbers` positions written that
tick); at N=50×M=100=5000 samples it is simply too sparse an event to clear 30
nonzero observations on both sides, while its sibling `delta_value_sum` (a
continuous per-tick sum) is dense enough to pass comfortably at the same N.

Because `delta_nnz` is a **tick-autocorrelated** count (Okazaki-fragment-style
polymerase events cluster in time within a seed), doubling ticks (M=200) does not
add as much independent information per added sample as doubling *seeds* does
(seeds are independent RNG streams; see `docs/phase_f/l2_2_design_a/L22_DEPTH200_REGEN_REPORT.md`
for the general M vs N tradeoff precedent). This diagnostic therefore extends
**N** (seeds 50-99), not **M**.

## 2. Explicit non-goals / hard constraints

This diagnostic **does not** and **must not**:
- modify `opencell/vivarium/karr_dna_supercoiling.py` (DNASupercoiling biology);
- modify any Design-A threshold, metric, or null-calibration code
  (`tests/vivarium/l2_2_design_a_runner.py`, `_l2_2_design_a_projections.py`,
  `_l2_2_design_a_runner_helpers.py`) — the diagnostic runner calls this code
  unmodified, only varying the seed count/list passed in;
- modify `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`'s `N_seeds: 50` /
  `M_ticks: 100` for `DNASupercoiling` (catalog N stays 50 pending a separate
  reviewer-approved integration decision; see §5);
- modify `evidence_index.json`, any process's `evidence_bundle/*/latest/` verdict,
  or write a new "latest"/canonical sentinel for `DNASupercoiling`;
- modify or delete the existing accepted seeds 0-49 raw `.mat` traces (they are
  copied read-only, hash-verified, from `l22-final-sweep`; see §3).

Every artifact this diagnostic produces is written under a clearly
non-canonical path: `docs/phase_f/l2_2_design_a/evidence_bundle/DNASupercoiling/diagnostic_n100/`.

## 3. Extraction plan (pre-registered)

1. **Baseline (seeds 0-49):** copy `DNASupercoiling_100ticks.mat` only (not the
   other 15 in-scope production processes' trace files) for seeds 0-49 from
   `E:\opencell-worktrees\l22-final-sweep\data\m1_sources\karr_native\` into this
   worktree's `data/m1_sources/karr_native/`, hash-verified
   (`scripts/l22_dnas_power/copy_baseline_seeds.py`). This is the exact data
   underlying the frozen, already-accepted N=50 evidence bundle — reused, not
   regenerated, so the N=50 baseline in this diagnostic is bit-identical to the
   canonical one.
2. **Extension (seeds 50-99):** generate with the existing, unmodified MATLAB
   extractor `scripts/matlab/extract_per_process_traces_v2.m`, 100 ticks,
   `DNASupercoiling` only, via the existing generic full-extraction launcher
   (`scripts/l22_extraction/launcher.py` + `scripts/matlab/run_l22_seed_shards.ps1`,
   bounded to 2 parallel MATLAB workers per that tooling's documented default).
   Output directories follow the launcher's existing, enforced convention:
   `per_process_traces_v2_s050/` … `per_process_traces_v2_s099/` — **never**
   `per_process_traces_v2_s000/` (seed 0 is canonical/unsuffixed; the launcher's
   `SeedZeroForbiddenError` already enforces this and is not touched).
3. **Validation:** every generated seed-50-99 file passes
   `scripts/l22_extraction/trace_validation.validate_structural` (schema/hash/tick-count)
   and `scripts/l22_extraction/preflight.schema_preflight` (no schema drift vs
   canonical seed 0), plus a non-vacuity check (seed's chromosome projection is
   not all-zero for both `delta_nnz` and `delta_value_sum` — i.e. the new seeds
   actually exercise the same event, not a degenerate/empty run).
4. **Loader diagnostic count:** the real (unmocked) oracle loader
   (`_l2_2_design_a_runner_helpers.load_karr_oracle`-equivalent path, invoked
   with an explicit seed-count override rather than its shared default of 50 —
   see `scripts/l22_dnas_power/diagnostic_runner.py`) must report
   `canonical_seed_count == 100` for `DNASupercoiling` once seeds 50-99 exist.

## 4. Evaluation plan and decision rule (pre-registered, no tuning after the fact)

Run the existing, unmodified `run_design_a(process="DNASupercoiling", ...)`
entry point (`tests/vivarium/l2_2_design_a_runner.py`) three ways, all writing
into `evidence_bundle/DNASupercoiling/diagnostic_n100/` (never `latest/`):

- `n50_reproduction/` — seeds 0-49 (must reproduce the canonical bundle's
  `component_n_nonzero_*` / `component_raw_w1` values exactly, as a harness
  sanity check that the copied baseline and the harness invocation are faithful);
- `n100_combined/` — seeds 0-99 (the diagnostic of interest);
- `half_split_a/` (seeds 0-49) and `half_split_b/` (seeds 50-99) — computed
  **independently** (not combined) as a stability check: if the two halves give
  materially different `component_raw_w1`/verdict for either primary component,
  that is evidence against combining them into one N=100 estimate.

For each run, record: primary-component `n_nonzero_oc`/`n_nonzero_karr`, scaled
W1 vs the existing fixed threshold (`_SCALED_DISTANCE_THRESHOLD=1.0`, unchanged),
the existing null-calibration `substrates` channel (unchanged, reported for
context only — it is not part of the DNASupercoiling primary-channel decision),
and a bootstrap CI on `linkingNumbers.delta_nnz`'s raw W1 (resampling seeds with
replacement, B=1000, matching the existing `bootstrap_B` convention used
elsewhere in this harness) to characterize N=100's residual uncertainty.

**Decision rule, fixed in advance:**

1. If `n100_combined`'s `linkingNumbers.delta_nnz` has **both**
   `n_nonzero_oc >= 30` **and** `n_nonzero_karr >= 30`: the primary channel is
   adequately powered at N=100. Then, and only then, evaluate PASS/FAIL using
   the exact same unmodified metric/threshold/null as the frozen N=50 bundle
   (`per_component_scaled_distance`, scale = max(p95(nonzero abs values), 1.0),
   threshold = 1.0) — **no threshold, scale, or metric-formula tuning** based on
   whether this makes the component pass or fail.
2. If either side is still `< 30` at N=100: report `STILL_UNDERPOWERED_AT_N100`
   verbatim; do not extend further within this diagnostic (a further extension,
   e.g. to N=150+, is a separate, explicitly re-pre-registered follow-up, not an
   ad hoc continuation of this one).
3. Regardless of outcome, this diagnostic's result **does not** by itself change
   `evidence_index.json`, the catalog N, or any sentinel — see §5 for the
   integration decision this feeds into (which requires separate sign-off).

## 5. Integration decision (deferred, not implemented by this diagnostic)

If §4 rule 1 is satisfied and the primary channel joint-verdict is `PASS` at
N=100: propose (do not implement) the minimum honest integration — either (a)
bump `DNASupercoiling`'s catalog `N_seeds: 50 -> 100` with a **process-scoped**
catalog-hash/evidence-hash update (i.e. a change that is auditably scoped to
this one process's row, not a blanket re-hash of `PROCESS_CATALOG.yaml` that
would implicitly re-stale every other process's evidence), or (b) publish this
diagnostic as a supplemental power artifact referenced from
`DNASupercoiling`'s catalog `notes` field without changing `N_seeds` at all.
Which of (a)/(b) is adopted, and any accompanying catalog/evidence-bundle edit,
requires planner/reviewer (Opus5) sign-off and is out of scope for this
diagnostic's own commits.

If §4 rule 2 applies (still underpowered): report as `STILL_UNDERPOWERED_AT_N100`
with the measured counts/CI; no integration proposal.

## 6. Commit sequencing

1. This pre-registration + all tooling (`scripts/l22_dnas_power/`) + tests,
   committed **before** the seed-50-99 MATLAB run starts.
2. The N=50/N=100/half-split diagnostic evidence artifacts + the final report
   (comparison table, decision, recommended integration mechanism),
   committed **after** the run completes, as a separate commit.
