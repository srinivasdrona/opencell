# Metabolism honest-FAIL investigation

## Scope

Single-hypothesis investigation from the task brief:

- Hypothesis: `cytosol-select` is the wrong projection for Metabolism's `(3, 585)` substrate cube.
- Allowed code change: `tests/vivarium/_l2_2_design_a_runner_helpers.py`, function `_project_metabolism_substrate_cube`.
- Out of scope: all other hypotheses and any production-code edits under `opencell/**`.

## Execution note

The first baseline run on this worktree degraded to the legacy single-seed
`per_process_replay/Metabolism.npz` oracle because the worktree did not have the
full `per_process_traces_v2_s000..s049` Metabolism files locally visible. To make
Beat 1 faithful to the task, I created local hardlinks in this worktree that point
to the existing external `E:\opencell\data\m1_sources\karr_native\per_process_traces_v2_sNNN\Metabolism_100ticks.mat`
files. No repository-tracked code was changed for this setup step.

## Beat 1 - Baseline confirmation

Command:

```powershell
bin\oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process Metabolism --seeds 50 --ticks 20 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/Metabolism_baseline_repro
```

Observed result from `tests/vivarium/artifacts/l2_2_design_a/Metabolism_baseline_repro/result.json`:

- verdict: `FAIL`
- primary channel: `substrates`
- W1: `9.758299145299116`
- threshold: `7.327495897435871`
- q95_null: `3.6637479487179356`
- n_nonzero_oc: `17026`
- n_nonzero_karr: `46035`
- warnings: `[]`
- per_sample_w1_summary:
  - mean: `9.758299145299116`
  - max: `22.724786324786244`
  - min: `4.555555555555562`

Conclusion: the honest FAIL from the task brief reproduced once the runner read
the real 50-seed `per_process_traces_v2` Metabolism oracle rather than the
legacy single-seed fallback.

## Beat 2 - Switch projection to sum-over-compartments

Code change:

- Edited `tests/vivarium/_l2_2_design_a_runner_helpers.py`,
  `_project_metabolism_substrate_cube`.
- Kept the `1755 -> (3, 585)` reshape unchanged.
- Changed only the final projection from single-compartment select to
  `arr.sum(axis=1)`.

Verification command:

```powershell
bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q
```

Observed result:

- `56 passed, 4 warnings in 329.31s`
- Warnings were existing `RuntimeWarning: Precision loss occurred in moment calculation`
  reports from `test_l2_2_design_a_runner_protein_processing_anticheat.py`;
  no Metabolism-specific failures or new regressions appeared.

## Beat 3 - Re-smoke

Command:

```powershell
bin\oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process Metabolism --seeds 50 --ticks 20 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/Metabolism_sum_smoke
```

Observed result from `tests/vivarium/artifacts/l2_2_design_a/Metabolism_sum_smoke/result.json`:

- verdict: `PASS`
- primary channel: `substrates`
- channel verdict: `PASS`
- W1: `168.42970769230706`
- threshold: `222.0369670085462`
- q95_null: `111.0184835042731`
- n_nonzero_oc: `93060`
- n_nonzero_karr: `119229`
- warnings: `[]`
- per_sample_w1_summary:
  - mean: `168.42970769230706`
  - max: `234.63760683760606`
  - min: `130.89743589743546`

Interpretation:

- The sum projection materially changes the Metabolism substrate comparison.
- The raw W1 does not get smaller; it gets much larger in absolute terms because the
  summed channel itself is much larger-scale.
- The Karr-only null also grows substantially under the summed representation, and the
  primary channel passes cleanly with no `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE`
  warning and no `PRIMARY_CHANNEL_ORACLE_LAUNDERING` / laundering warning.

## Beat 4 - Verdict + recommendation

Selected case: **Case A - sum-projection PASS (no warnings)**

Reason:

- Baseline `cytosol-select` reproduced the honest FAIL:
  `W1=9.758299145299116 > threshold=7.327495897435871`.
- Sum-over-compartments changed the comparison surface and produced a clean PASS:
  `W1=168.42970769230706 <= threshold=222.0369670085462`.
- The warnings list stayed empty on the sum smoke, so this is not
  `PASS_VIA_CONVERGENCE` and not `PASS_VIA_ORACLE_LAUNDERING`.

Recommendation:

- Keep the sum-over-compartments projection in
  `_project_metabolism_substrate_cube` as the correct Design-A oracle projection
  for Metabolism's compartmented substrate cube.
- Do not revert to the prior single-compartment projection.
- In follow-up work outside this delegation, update the Metabolism catalog notes
  to document why Design-A must compare the summed compartment view.
- Treat Metabolism as an honest green under the sum projection, subject to the
  operator's normal merge review.

Out-of-scope note:

- I did not modify the catalog or any production code under `opencell/**`, per the
  task's hard rules.
