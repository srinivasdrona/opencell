# MacromolecularComplexation Convergence v3

## Design Summary
- `tests/vivarium/_substrate_stress/macromol_stress_v3.py` is the v2 harness copied forward with one added gate.
- Sub-gate A keeps the v2 threshold: `per_tick_W1_mean < 0.5` and `per_tick_W1_max < 2.0`.
- Sub-gate B is new: `abs(total_oc_events - total_karr_events) / max(1, total_karr_events) < 0.10`.
- A row is `PASS` only if both sub-gates pass.

## Results Table

Run command:
`bin\oc-py.cmd tests/vivarium/_substrate_stress/macromol_stress_v3.py > tests/vivarium/_substrate_stress/macromol_stress_v3_results.txt`

| alpha | per_tick_W1_mean | per_tick_W1_max | total_oc_events | total_karr_events | event_rel_diff | subgate_a | subgate_b | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.00 | 0.000000 | 0.000000 | 97 | 97 | 0.000000 | PASS | PASS | PASS |
| 0.50 | 0.001320 | 0.020408 | 0 | 97 | 1.000000 | PASS | FAIL | FAIL |
| 0.10 | 0.001320 | 0.020408 | 0 | 97 | 1.000000 | PASS | FAIL | FAIL |
| 0.05 | 0.001320 | 0.020408 | 0 | 97 | 1.000000 | PASS | FAIL | FAIL |
| 0.01 | 0.001320 | 0.020408 | 0 | 97 | 1.000000 | PASS | FAIL | FAIL |

## Verdict

Case B: regime-bounded.

Rationale:
- The harness sanity check passes at `alpha=1.0`: both sub-gates pass and OC matches Karr exactly on the sampled ensemble.
- Sub-gate A still passes at every lower alpha, reproducing the v2 false-confidence pattern where sparse `complexs` vectors keep per-tick W1 small.
- Sub-gate B fails at every tested alpha below `1.0`: OC forms `0` total complexation events while Karr's recorded original-regime oracle still contains `97`.
- The relative event-count miss is `1.0` at `alpha=0.50`, `0.10`, `0.05`, and `0.01`, which is far outside the allowed `< 0.10` band.
- Under the tightened gate, MacromolecularComplexation is not a confirmed biology green. The honest classification is that the prior v2 Case A was a sparse-event dilution artifact and the process is only green at the unperturbed regime.

## Commit Trail
- `9eb2ebe` — `macromol-convergence-v3: tightened threshold (add Sub-gate B total events within 10%)`
- `8b8f7d3` — `macromol-convergence-v3: results`
- This STATUS file is the Beat 3 verdict artifact.
