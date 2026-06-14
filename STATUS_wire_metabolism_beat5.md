# STATUS: wire-metabolism Beat 5

## Scope

Target process:

```yaml
  - name: Metabolism
    oc_module: opencell/vivarium/karr_metabolism.py
    bucket: TRIVIAL_RNG
    in_scope_L2_2: true
    M_ticks: 20
    N_seeds: 50
    event_density: dense
    input_channels: [substrates, enzymes]
    output_channels: [substrates]
    primary_channel: substrates
    karr_artifact: per_process_traces_v2
```

## Beat 1 - Rebase + baseline

- Merge commit: `5973448` (`Merge branch 'main' into exec/l22-wire-metabolism`).
- Baseline verification after merge:
  - `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
  - Result: `56 passed, 4 warnings`.
- The literal Beat 5 smoke command did **not** reproduce the historical broadcast error in this checkout after the merge.
  - `Get-ChildItem -Recurse -File data\m1_sources\karr_native, data\opencell_ensembles | Where-Object { $_.Name -eq 'Metabolism_100ticks.mat' -or $_.FullName -match '[\\/\\\\]ensembles[\\/\\\\]metabolism[\\/\\\\]' }`
  - Result: `0`
  - Consequence: the runner falls back to `data/karr_fixtures/per_process_replay/Metabolism.npz`, so the smoke exercises the legacy 585-wide oracle surface instead of the missing v2 1755-wide ensemble surface.

## Beat 2 - Shape adapter

- Code commit: `74e1181` (`wire-metabolism-beat5: substrate compartment-shape adapter`).
- File changed: `tests/vivarium/_l2_2_design_a_runner_helpers.py`
- Projection choice: **select cytosolic compartment (`compartment 0`)**, not sum across compartments.
- Why:
  - `opencell/vivarium/karr_metabolism.py` declares `_CYTOSOL_COMPARTMENT_0 = 0`.
  - In `_dynamic_update`, the shared `substrates` store is read into `self._sub_state[idx, _CYTOSOL_COMPARTMENT_0]` (`lines 385-406` in the merged file).
- Synthetic adapter proof on 1755-wide input:
  - Command: integrated `_format_ensemble_oracle(...)` check with synthetic `(seed=1, tick=2, dim=1755)` substrate input.
  - Result: `(1, 2, 585) 0.0 0.0 1755.0`
  - Interpretation:
    - projected oracle shape is `(1, 2, 585)`
    - first projected value matches the cytosolic slice value `0.0`
    - first cross-compartment sum would have been `1755.0`, so the adapter is not summing

## Beat 3 - Smoke verdict

- Command:
  - `bin\oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process Metabolism --seeds 50 --ticks 20 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/Metabolism_beat5_smoke`
- Console verdict:
  - `Metabolism PASS substrates=SEED_NOISE@0.000000`
- `result.json` highlights:
  - verdict: `PASS`
  - primary channel: `substrates`
  - primary channel verdict: `SEED_NOISE`
  - `w1_oc_vs_karr`: `0.0`
  - `per_sample_w1_max`: `0.0`
  - `n_nonzero_oc`: `89000`
  - `n_nonzero_karr`: `89000`
  - `canonical_seed_count`: `1`
- Warnings:
  - `KARR_LEGACY_SINGLE_SEED_FALLBACK`
  - `KARR_SINGLE_SEED_REUSED`
  - `TRIVIAL_RNG_LEAK`
  - `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE`

## Beat 4 - Inversion

- Failure mode: **"The projection silently zero-fills via wrong-direction projection and the smoke shows trivial match."**
  - Evidence against:
    - The synthetic 1755-wide adapter proof returned nonzero projected values immediately: `(2, 585) True [0.0, 1.0, 2.0, 3.0, 4.0]`.
    - The smoke reported `n_nonzero_oc = 89000` and `n_nonzero_karr = 89000`, not a collapsed or zero-filled OC surface.
- Failure mode: **"The projection direction (sum vs select) is wrong and the substrate trajectory differs by a constant factor."**
  - Evidence against:
    - Integrated `_format_ensemble_oracle(...)` proof returned `(1, 2, 585) 0.0 0.0 1755.0`.
    - The projected first entry equals the cytosol slice (`0.0`), while the 3-compartment sum for that same position would have been `1755.0`.
    - `karr_metabolism.py` reads the shared pool into `_CYTOSOL_COMPARTMENT_0` (`lines 385-406`), so cytosol-select matches the SUT read surface and sum would be structurally wrong.
- Failure mode: **"The adapter works for the smoke window but breaks on other (seed, tick) ranges where compartment distribution differs."**
  - Evidence against:
    - The adapter is a pure per-tick reshape/select function with no seed- or tick-dependent branching.
    - `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q` stayed green (`56 passed`), including the ensemble-loader coverage that exercises single-seed and multi-seed stacking paths.
  - Residual limitation:
    - This checkout has no Metabolism `per_process_traces_v2` or `ensembles/metabolism` `.mat` files, so I could not falsify this on real Metabolism ensemble data across varied seed/tick ranges.

## Verification

- Expected Beat 3 outcome:
  - Metabolism Beat 5 smoke should produce a normal verdict instead of a broadcast/ndim exception.
- Actual measured outcome:
  - Smoke verdict: `Metabolism PASS substrates=SEED_NOISE@0.000000`
  - Primary `W1`: `0.0`
  - `per_sample_w1_max`: `0.0`
- Commands:
  - `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
  - `bin\oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process Metabolism --seeds 50 --ticks 20 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/Metabolism_beat5_smoke`
  - `wsl -e bash -lc "cd '/mnt/e/opencell-worktrees/wire-metabolism' && source /mnt/e/opencell/.venv-wsl/bin/activate && python - <<'PY' ... PY"`
- Verdict:
  - matched, with the caveat that the local smoke used the legacy single-seed replay oracle because the Metabolism v2 ensemble `.mat` sources are absent in this worktree.
