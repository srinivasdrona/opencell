# DNASupercoiling N=200 Sparse-Event Gate Pre-Registration

**Status:** pre-registered before reading any N=200 DNAS report or tensor in
this task. This document is written from project rules, the 2026-08-11
checkpoint, the frozen N=50 canonical bundle, and the accepted N=100 power
diagnostic only. The gate below is fixed before the N=200 verdict is seen.

## 1. Why a new gate is required

`DNASupercoiling`'s primary channel is `chromosome`, with primary projection
`[linkingNumbers.delta_value_sum, linkingNumbers.delta_nnz]`. The dense
`delta_value_sum` component already behaves well under the shared
`per_component_scaled` metric. The problem is the sparse `delta_nnz`
component:

- canonical N=50 failed on support (`n_nonzero_oc=17`, `n_nonzero_karr=24`);
- the N=100 diagnostic raised those counts to `31` and `42`;
- the N=100 report also showed why the discarded `0.10` occurrence-rate guard
  is not credible: the shared raw-W1 threshold can still pass even if OC has
  zero `delta_nnz` activity, so a sparse-event gate must explicitly reject
  zero or strongly underactive OC support.

The new gate therefore targets `linkingNumbers.delta_nnz` only. It does not
change shared Design-A metrics, thresholds, catalog entries, or the canonical
evidence index.

## 2. Hard constraints

This task must not:

- perform new MATLAB extraction;
- edit `PROCESS_CATALOG.yaml`, `evidence_index.json`, or shared evaluator files
  under `scripts/l22_evidence/` or `tests/vivarium/`;
- read any N=200 DNAS report or raw tensor before this preregistration is
  committed;
- tune any threshold after seeing N=200 outcomes.

The evaluation must use the already-frozen 200-seed artifacts once.

## 3. Catalog entry (authoritative spec)

```yaml
name: DNASupercoiling
bucket: ALGORITHMIC_SHALLOW
M_ticks: 100
N_seeds: 50
primary_channel: chromosome
primary_projection: [linkingNumbers.delta_value_sum, linkingNumbers.delta_nnz]
```

## 4. Sparse-event summaries used by the gate

For the `linkingNumbers.delta_nnz` tensor, let a "nonzero event" mean a
tick with `delta_nnz != 0`. From the `(seed, tick)` matrix for one side
(OC or Karr), define:

- `pooled_nonzero_ticks`: total number of nonzero `(seed, tick)` cells;
- `active_seeds`: number of seeds with at least one nonzero tick;
- `clustered_seeds`: number of seeds with at least two nonzero ticks.

These three summaries jointly cover pooled support, distinct-seed support, and
within-seed clustering.

## 5. Statistical contract

### 5.1 Familywise error control

The underactivity family is controlled at **FWER alpha = 0.05** across exactly
three one-sided tests:

1. pooled nonzero ticks,
2. active seeds,
3. clustered seeds.

Each raw p-value is an exact conditional binomial test under equal exposure:

- null: OC and Karr support counts are exchangeable on that axis;
- alternative: OC support is smaller than Karr support.

Operationally, for observed `(oc_count, karr_count)`, compute
`BinomTest(k=oc_count, n=oc_count + karr_count, p=0.5, alternative="less")`
and apply **Holm correction** across the three axes. Any rejected axis makes
the sparse component fail as underactive.

### 5.2 Support adequacy floors

The gate only evaluates the underactivity family if Karr itself provides enough
support on all three axes:

- `pooled_nonzero_ticks_karr >= 31`
- `active_seeds_karr >= 31`
- `clustered_seeds_karr >= 6`

These floors are fixed from the exact-test contract, not from N=200
convenience:

- `31` is the smallest Karr floor for which the Holm-level one-sided exact
  test (`alpha/3 = 0.0167`) rejects any OC count at or below half the Karr
  count on that axis for all larger counts as well. Example at the floor:
  `oc=15`, `karr=31` gives `p=0.01295`.
- `6` is the smallest Karr clustered-seed floor for which zero clustered OC
  support is rejectable at the same corrected level, because `P(Bin(6, 0.5)=0)
  = 2^-6 = 0.015625 < 0.0167`.

If any Karr floor fails, the sparse component verdict is
`PRIMARY_INSUFFICIENT_SAMPLES`.

### 5.3 Sparse component decision rule

`linkingNumbers.delta_nnz` passes only if all of the following are true:

1. Karr support adequacy passes on all three axes in 5.2.
2. None of the three Holm-corrected exact tests rejects OC underactivity.
3. The existing shared `per_component_scaled_distance` verdict for
   `linkingNumbers.delta_nnz` is still `PASS` under its unchanged threshold.

If step 2 fails, the sparse component verdict is `PRIMARY_UNDERACTIVE`.
If step 3 fails, the sparse component verdict is `FAIL`.

### 5.4 Process decision rule

`DNASupercoiling` gets a process-level PASS only if:

- `linkingNumbers.delta_value_sum` remains `PASS` under the unchanged shared
  `per_component_scaled_distance` metric, and
- `linkingNumbers.delta_nnz` passes the sparse gate in 5.3.

Otherwise the process-level verdict is the first non-green sparse verdict
(`PRIMARY_INSUFFICIENT_SAMPLES`, `PRIMARY_UNDERACTIVE`, or `FAIL`), or the
dense-component `FAIL` if `delta_value_sum` itself fails.

## 6. Pre-registered sensitivity controls

The final report must include, but not gate on, the following diagnostics:

- the exact hypothetical raw W1 if OC were identically zero on
  `delta_nnz` (`mean(abs(karr_delta_nnz))`), to show why W1 alone is not a
  credible sparse-activity guard;
- the raw and Holm-adjusted p-values for all three underactivity axes;
- two stricter clustering-floor sensitivity reads:
  - `clustered_seeds_karr >= 11` (enough to reject `oc_clustered <= 2`);
  - `clustered_seeds_karr >= 14` (enough to reject `oc_clustered <= 4`).

These stricter cluster floors are descriptive sensitivities only. The frozen
binary rule is the gate in section 5.

## 7. Artifacts this prereg authorizes

Process-specific artifacts only:

- evaluator code under `scripts/l22_dnas_rare_event/`;
- tests under `tests/scripts/test_l22_dnas_rare_event_*.py`;
- evaluation output under
  `docs/phase_f/l2_2_design_a/evidence_bundle/DNASupercoiling/diagnostic_n200_review/`;
- root status file `STATUS_L22_DNAS.md`.

No shared catalog, shared evaluator, or canonical `latest/` bundle is touched.

## 8. Commit sequence

1. Commit this preregistration, the process-specific evaluator module, and its
   tests.
2. Only after that commit, open the frozen N=200 DNAS report/tensor artifacts,
   run the evaluation once, and write the final `STATUS_L22_DNAS.md`.
