# OC vs Karr LP diff probe status

- JSON: `tmp/oc_vs_karr_lp_diff.json`
- Sample: `(s=0, t=1)`
- Karr bounds source: `data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat`
- Inferred `cellDryMass`: `3.944640855678535e-15`

## Summary
- S: match (max_abs_diff=0.000e+00)
- RHS: match (count_gt_1e_9=0)
- objective: match (count_gt_1e_9=0)
- bounds: mismatch (raw match; post-clip differs only where OC clips +/-inf to +/-1e6)
- karr_flux_under_oc_lp: match (Karr flux feasibility in OC LP)
- oc_flux_under_karr_lp: match (OC flux feasibility in Karr bounds)
- objective_values: match (rel_diff_oc_objective=6.09891305e-12)
- flux_comparison: mismatch (max_abs_diff=1.031e+06)
- warm_start: match (warm-start reaches same optimum (delta=-7.286e-16))

## Self-audit
| # | Criterion | Verified |
|---|---|---|
| 1 | Script reads only the 5 named files | [x] |
| 2 | Karr's bounds sourced from metab_flux_allocated_state_s000_tick1.mat | [x] |
| 3 | OC's bounds use exact KarrMetabolismProcess._dynamic_update flags | [x] |
| 4 | swiglpk used for all LP solves with V4-aligned options | [x] |
| 5 | All 9 sections present in JSON | [x] |
| 6 | Warm-start uses glp_set_col_stat (not obj coef changes) | [x] |
| 7 | Match-table summary with one row per section | [x] |
| 8 | INTENT block emitted | [x] |
| 9 | VERIFICATION block emitted | [x] |
