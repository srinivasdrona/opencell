# STATUS — L2.2 Translation v1 Refire (C1/C2/C3)

## Live Log (UTC)
- 2026-06-04T20:00:43Z — Loaded required context (`SESSION_CONTEXT.md`, `DELIBERATE_ACTION_PREFIX_v2.md`, `FIX_TEMPLATE_L2_REPLAY.md`) and completed Beat-1 reads of v1 process, runner, and distributional test.
- 2026-06-04T20:00:43Z — Attr-mapping note captured before edits: v3 ribosome internals (`_ribosome_state_active`, `_ribosome_bound_mrnas`, `_ribosome_mrna_positions`) do not exist on v1 `KarrTranslationProcess`; runner preserves summary fields and emits `NaN` for these channels.
- 2026-06-04T20:06:49Z — Beat-3 smoke: `bin\\oc-py.cmd tests/vivarium/_l2_2_ensemble_runner.py --seeds 0:0 --force` succeeded; NPZ contains 4 core observables + 3 summary fields.
- 2026-06-04T20:06:49Z — Missing Karr ensemble seed MATs in this worktree were sourced from sibling `/mnt/e/opencell-worktrees/l22-translation/data/m1_sources/karr_native/ensembles/translation/seed_000..seed_049` for local gate execution.
- 2026-06-04T20:08:25Z — Full C1 extraction: `bin\\oc-py.cmd tests/vivarium/_l2_2_ensemble_runner.py --seeds 0:49 --force` regenerated OpenCell ensemble `seed_000..seed_049`.
- 2026-06-04T20:09:32Z — C2 prep edit: `tests/vivarium/test_l2_2_translation.py` now asserts OC manifest class is `KarrTranslationProcess` and writes class metadata into `comparison_report.json`.
- 2026-06-04T20:11:59Z — C2 gate run: `bin\\oc-pytest.cmd -x tests/vivarium/test_l2_2_translation.py -q` => **FAIL** with `ks_failure_count=400`, `wasserstein_failure_count=400`; refreshed report artifacts written.

## Beat 1 — Contract
- Required behavior: swap L2.2 Translation distributional SUT from v3 internals to v1 `KarrTranslationProcess`, regenerate OpenCell ensemble seeds 0..49, and rerun gate.
- Done criterion: committed C1/C2/C3 checkpoints; OC manifest class string is `KarrTranslationProcess`; status includes per-observable v1-vs-v3 delta table and verdict.

## Beat 2 — Surface (Read/Write)
- Read: `opencell/vivarium/karr_translation.py`, `tests/vivarium/_l2_2_ensemble_runner.py`, `tests/vivarium/test_l2_2_translation.py`, generated report CSV/JSON artifacts.
- Write: `tests/vivarium/_l2_2_ensemble_runner.py`, `data/opencell_ensembles/translation/seed_*/(Translation_100ticks.npz, metadata.json)`, `data/opencell_ensembles/translation/MANIFEST.json`, `tests/vivarium/test_l2_2_translation.py`, `comparison_report.json`, `ks_failures.csv`, `wasserstein_failures.csv`, this STATUS file.
- v3→v1 summary mapping note (implemented in runner):
  - `_ribosome_state_active` -> `ribosome_state_active_count`
  - `_ribosome_bound_mrnas` -> `ribosome_bound_mrnas_nonzero_count`
  - `_ribosome_mrna_positions` -> `ribosome_mrna_positions_sum`
  - v1 has no equivalent exposed arrays; preserved fields are emitted as `NaN` (runner lines 72-95).

## Beat 3 — Verify
- Single-seed smoke command: `bin\\oc-py.cmd tests/vivarium/_l2_2_ensemble_runner.py --seeds 0:0 --force` (pass).
- Full extraction command: `bin\\oc-py.cmd tests/vivarium/_l2_2_ensemble_runner.py --seeds 0:49 --force` (pass, seed_count=50).
- Gate command: `bin\\oc-pytest.cmd -x tests/vivarium/test_l2_2_translation.py -q` (fail).
- Fail line: `AssertionError: ... ks_failure_count=400, wasserstein_failure_count=400`.

## Beat 4 — INVERT (Pre-mortem + Diagnosis)
- Pre-mortem failure mode considered: test could "pass" summary channels while wrong if runner emits `NaN` and comparison math never treats non-finite values as explicit failures.
- Dominant observed signal for FAIL:
  - **(d) Initial-condition/state-surface mismatch + non-Karr analytical dynamics** is dominant.
  - Evidence:
    - `build_state_template` seeds state from process schema defaults (`tests/vivarium/l2_replay_common.py:125-127`).
    - v1 translation schema defaults `substrates`, `enzymes`, and `boundEnzymes` to zeros (`opencell/vivarium/karr_translation.py:197-231`).
    - v1 update path is analytical/stochastic rounding (`opencell/vivarium/karr_translation.py:266-296`) rather than a Karr-native ribosome-state replay surface.
    - Immediate tick-level divergence: `ks_d=1.0` and huge W1 already at tick 0 in refreshed CSVs.
- Non-dominant hypotheses ruled down:
  - (a) trace-hint short-circuit: not used by v1 path (`next_update` has no `trace_hint` branch in `karr_translation.py:266-296`).
  - (b) missing per-process trace fixture read path: v1 process does not load trace files on update path.
  - (c) stochastic accumulation alone: not sufficient explanation because divergence is already maximal at earliest ticks.
- Additional caveat:
  - Runner emits `NaN` for the 3 ribosome summary fields (`_l2_2_ensemble_runner.py:72-95`), and comparator lacks non-finite guards (`test_l2_2_translation.py:218-250`), so those rows appear as `W1=0/p=1` in rollup even though semantically they are unavailable for v1.

## Beat 5 — Per-observable Rollup (v1 vs v3)

| observable | v1 W1_max | v1 threshold | v1 p_bonf | v3 W1_max | delta W1_max (v1-v3) |
|---|---:|---:|---:|---:|---:|
| substrates | 164692961.10 | 15367829.53 | 1.39e-26 | 164692922.06 | +39.04 |
| enzymes | 826.08 | 4.69 | 1.39e-26 | 770.08 | +56.00 |
| boundEnzymes | 334.44 | 4.52 | 1.39e-26 | 334.44 | +0.00 |
| monomers | 16175.52 | 1.01 | 1.39e-26 | 16405.00 | -229.48 |
| ribosome_state_active_count | NaN* | 0.79 | NaN* | 11.02 | NaN |
| ribosome_bound_mrnas_nonzero_count | NaN* | 0.77 | NaN* | 11.02 | NaN |
| ribosome_mrna_positions_sum | NaN* | 1396.22 | NaN* | 18873.24 | NaN |

`*` Runner outputs `NaN` for these v1-missing summary channels. `comparison_report.json` raw rollup shows `W1=0`/`p=1` for these rows due non-finite handling gap in the comparator; interpret as unavailable (`NaN`), not genuine agreement.

## Aggregate
- v1 aggregate (this run): KS **400/700 fail**, W1 **400/700 fail**.
- v3 aggregate (reference `c0c3a03`): KS **700/700 fail**, W1 **700/700 fail**.

## Interpretation
v1 does **not** meet the L2.2 distributional gate: all 4 core observables fail at every tick, with W1 magnitudes still orders above thresholds. Relative to prior v3 numbers, v1 is broadly in the same failure regime (slightly worse on enzymes/substrates, slightly better on monomers, unchanged boundEnzymes). The 3 ribosome summary channels are structurally unavailable in v1 and are currently represented as `NaN`; they should be treated as non-comparable rather than evidence of agreement.

## Commits
- `452a119` — `feat(l2.2-translation-v1): swap runner to KarrTranslationProcess (v1)`
- `e5b5b14` — `feat(l2.2-translation-v1): point distributional gate at v1 ensemble`
