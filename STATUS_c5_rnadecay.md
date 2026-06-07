# STATUS C5 RNADecay

- 2026-06-06T12:37:09Z UTC Beat 1 complete: read `SESSION_CONTEXT.md` once; confirmed pre-stage commit `1da141d` already added `ALGORITHMIC_SHALLOW_K_ENG = 2.0` in `tests/vivarium/_l2_2_design_a_runner_helpers.py` and `_PROCESS_K_ENG["ALGORITHMIC_SHALLOW"]` in `tests/vivarium/l2_2_design_a_runner.py`; skimmed Transcription wiring in both files and will mirror that pattern for RNADecay with `RNAs` as the case-sensitive observable name.
- 2026-06-06T12:56:00Z UTC Beat 2 ready: verified the dirty helper diff already adds RNADecay oracle loading, cached process factory, `RNAs`-case-sensitive tick replay, dispatch registration, and `__all__` export in `tests/vivarium/_l2_2_design_a_runner_helpers.py`; committing that helper-only slice next.
- 2026-06-06T13:00:30Z UTC Beat 3 ready: patched `tests/vivarium/l2_2_design_a_runner.py` to admit `RNADecay` end-to-end, classify it as `ALGORITHMIC_SHALLOW`, use output channels `substrates` + `RNAs`, treat `RNAs` as primary, reuse the single-seed oracle warning path, and keep `TRIVIAL_RNG_LEAK` restricted to Metabolism only.
- 2026-06-06T13:10:00Z UTC Beat 4 in progress: resumed from existing Beat 2/3 commits on this branch, confirmed the RNADecay smoke artifact already runs end-to-end and currently fails on primary `RNAs`, then added a dedicated primary-channel oracle-laundering detector for `RNAs` plus a focused RNADecay anti-cheat test file.

## Final

- 2026-06-06T13:11:55Z UTC Beat 4 complete: committed `1cc9ac3` (`test(l2.2): RNADecay smoke + oracle-laundering anti-cheat`) after adding a primary-channel `RNAs` oracle-laundering detector in `tests/vivarium/l2_2_design_a_runner.py` and a focused RNADecay anti-cheat in `tests/vivarium/test_l2_2_design_a_runner_anticheat_rna_decay.py`.
- Commits for this task:
  - `6593dae` — `feat(l2.2): helpers support RNADecay oracle + tick dispatch (SHALLOW bucket)`
  - `8fe7ef0` — `feat(l2.2): runner supports RNADecay end-to-end (SHALLOW bucket)`
  - `1cc9ac3` — `test(l2.2): RNADecay smoke + oracle-laundering anti-cheat`
- Verification:
  - `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/l22-c5-rnadecay && python -m pytest -x tests/vivarium/test_l2_2_design_a_runner_anticheat_rna_decay.py -W error::UserWarning"` → PASS (`1 passed`)
  - `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/l22-c5-rnadecay && python tests/vivarium/l2_2_design_a_runner.py --process RNADecay --seeds 0,1,2 --ticks 5 --bootstrap-B 10 --output-dir tests/vivarium/artifacts/l2_2_design_a/RNADecay_smoke"` → exits 1 with `RNADecay FAIL substrates=SEED_NOISE@0.000000 RNAs=FAIL@3.729160`
- Smoke verdict (`tests/vivarium/artifacts/l2_2_design_a/RNADecay_smoke/result.json`, timestamp `2026-06-06T13:11:47.073365+00:00`):
  - Process verdict: `FAIL`
  - Warning: `KARR_SINGLE_SEED_REUSED` present, as expected for the 1-seed oracle
  - `substrates`: `W1=0.000000`, `q95=0.000000`, `threshold=1.000000`, verdict=`SEED_NOISE`
  - `RNAs` (primary/headline): `W1=3.729160`, `q95=0.000000`, `threshold=1.000000`, verdict=`FAIL`
- Anti-cheat outcome:
  - RNADecay `RNAs` oracle-laundering anti-cheat: PASS
  - The new test forces exact oracle replay on the primary `RNAs` channel and confirms the runner flips that channel to `FAIL` with `PRIMARY_CHANNEL_ORACLE_LAUNDERING`.
