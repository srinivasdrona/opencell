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

Pending.

## Beat 4 - Verdict + recommendation

Pending.
