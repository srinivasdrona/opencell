# Phase E.1 Scaffold — chassis_v4 vs Karr (first 1000 s)

- Generated: `2026-05-23T02:47:21Z`
- Horizon: `1000` s
- Snapshot interval: `100` s
- Note: large mismatches are expected in this scaffold stage (chassis_v4 is partial vs full Karr WCM).

| observable | opencell_value | karr_value | rel_err | status |
|---|---:|---:|---:|---|
| `atp_pool` | -4.3164e+05 | 2.0000 | 9383.4674 | FAIL |
| `cell_dry_mass_g` | 4.8179e-17 | 3.9519e-15 | 0.0039 | PASS |
| `division_event_timestamp_s` | NaN | 3.2400e+04 | NaN | FAIL |
| `dntp_pool_total` | 4.0000 | 6.9194e+04 | 0.9999 | FAIL |
| `fork_position_norm` | 0 | 0 | 0 | PASS |
| `gtp_pool` | -4.3164e+05 | 1.0000 | 1.0791e+05 | FAIL |
| `mrna_total_count_estimate` | 908.8454 | 16.6690 | 26.7571 | FAIL |
| `protein_total_count_estimate` | 2.9728e+04 | 1.6289e+04 | 0.8250 | FAIL |
| `replication_state_code` | 0 | 0 | 0 | PASS |

## Diff Summary

```text
Diff 'opencell' vs 'karr': FAIL
  Level 1 STRUCTURAL: 10 ok, 0 warn, 0 fail
  Level 2 INVARIANT (A): 4 viol
  Level 2 INVARIANT (B): 3 viol
  Level 3 TRAJECTORY:  3 ok, 0 warn, 6 fail
  Level 4 PHENOTYPE:   0 ok, 0 warn, 0 fail
    L3 FAIL: trajectory_norm — ('observables', 'atp_pool'): L_inf_abs=4.316e+05 (tol 0.0), L_inf_rel=9.383e+03 (tol 0.05)
    L3 FAIL: trajectory_norm — ('observables', 'division_event_timestamp_s'): L_inf_abs=nan (tol 0.0), L_inf_rel=nan (tol 0.1)
    L3 FAIL: trajectory_norm — ('observables', 'dntp_pool_total'): L_inf_abs=7.274e+04 (tol 0.0), L_inf_rel=9.999e-01 (tol 0.05)
    L3 FAIL: trajectory_norm — ('observables', 'gtp_pool'): L_inf_abs=4.316e+05 (tol 0.0), L_inf_rel=1.079e+05 (tol 0.05)
    L3 FAIL: trajectory_norm — ('observables', 'mrna_total_count_estimate'): L_inf_abs=8.922e+02 (tol 0.0), L_inf_rel=2.676e+01 (tol 0.5)
    L3 FAIL: trajectory_norm — ('observables', 'protein_total_count_estimate'): L_inf_abs=1.344e+04 (tol 0.0), L_inf_rel=8.250e-01 (tol 0.5)
```