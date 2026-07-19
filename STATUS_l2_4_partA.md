# L2.4 Part A Status

## Files Created

- `scripts/l2_4_verify_conservation.py`
  - Part A checker for the uncapped v6 chassis.
  - Structure left for Batch 2 seams:
    - `load_exchange_wids()` handles the D2-rev exchange boundary set.
    - `evaluate_tick_part_a()` isolates integer-validity + residual checks for non-exchange WIDs.
    - `run_seed_horizon()` owns one seed's runtime/accounting loop.
    - `summarize_gate_runs()` + `write_report()` aggregate verdicts/artifacts cleanly so Part B checks can bolt in without reshaping the CLI.
- `tests/integration/test_l2_4_conservation_gate.py`
  - Planted-leak anti-vacuity test plus one-tick uncapped chassis smoke verdict check.
- `.progress_l2_4_partA.md`
  - Heartbeat milestones for the orchestrator.
- `STATUS_l2_4_partA.md`
  - This running status record.

## Exchange-WID Set

- Count: `124`.
- Loaded from `data/karr_fixtures/per_process/Metabolism_flat.mat`.
- Mapping source reused from:
  - `scripts/l1b_verify_wiring.py:1212-1250`
  - `opencell/m1/karr_metabolism_writeback.py:49-87`
- Runtime report source string:
  - `data/karr_fixtures/per_process/Metabolism_flat.mat via Metabolism.substrateIndexs_externalExchangedMetabolites / KarrWritebackFixture.sub_idx_external`

## Self-Test Result

- Command: `bin\oc-pytest tests/integration/test_l2_4_conservation_gate.py -q -rs`
- Result: `2 passed, 2 warnings`
- Planted-leak FAIL confirmed:
  - Synthetic non-exchange WID `SYNTH_INTERNAL` changed by `+1` without process attribution.
  - Checker returned `CONSERVATION_FAIL` with `failure_kind=unattributed`, `wid=SYNTH_INTERNAL`, `tick=1`, `seed=7`, `unattributed=1`.
- Clean-path verdict:
  - One-tick uncapped chassis smoke run returned `PASS`.
  - Assertions pinned the real runtime verdict rather than weakening the checker.

## First Real Verdict On The Uncapped Chassis

- Command:
  - `bin\oc-py scripts/l2_4_verify_conservation.py --ticks 100 --seeds 0,1,2,3 --out-dir tmp/l2_4_partA --fresh`
- Honest verdict: `PASS`
- Requested horizon: `100` ticks for seeds `0,1,2,3`
- Horizon completion:
  - seed `0`: `100/100`
  - seed `1`: `100/100`
  - seed `2`: `100/100`
  - seed `3`: `100/100`
- Stability:
  - no `STABILITY_FAIL`
- Conservation:
  - `total_failures=0`
  - `max_abs_unattributed=0`
  - `top_failures=[]`
- Exchange skips:
  - `exchange_wid_count=124`
  - `exchange_wids_skipped=12400` per seed (`124 * 100`)

## Commits

- Green implementation chunk committed before the real verdict run:
  - `593038b` `Add L2.4 Part A conservation gate`

## Protected Files Check

- `git status --short -- opencell/vivarium/karr_allocation_step.py opencell/vivarium/karr_transcription_v3.py`
- Result: empty output; both protected files remained untouched.
