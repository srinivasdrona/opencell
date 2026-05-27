# tRNA Aminoacylation Diagnose Status

- ticks_run: 200
- timestep_s: 1.0
- trna_calls: 200
- nonempty_updates: 1 (0.5%)
- nonzero_request_ticks: 200
- nonzero_grant_ticks: 200
- empty_reason_counts: {'guard_zero_flux': 199}
- tick_log_csv: `artifacts/trna_diagnose_200t/trna_diagnose_tick_log.csv`

## Hypothesis Fit
- classified_hypothesis: H2
- H1 check: process is called each tick when `trna_calls == ticks`.
- H2 check: calls happen, requests/grants are present, but updates are empty on most ticks.
- H3 check: allocator grant is always zero even though request is nonzero.
- H4 check: updates exist but trace exclusion drops them (runner-side).

## Interpretation
- Current evidence points to guard-driven empty updates after process invocation, not missing enrollment.
