A3.3 Turn 5 completed at 2026-05-22 21:45 IST

Implemented
- Added `build_karr_chassis_v3(...)` in `opencell/vivarium/karr_composite.py`
- Added new request calculator module: `opencell/vivarium/karr_request_calculators.py`
  - `RequestCalculatorD2(Step)` (zero requests for `karr_d2_real`)
  - `RequestCalculatorPD(Step)` (ATP/H2O request from expected decay)
- Added integration suite: `tests/integration/test_karr_chassis_v3.py` (8 tests)

Verification
1) Import check (worktree code)
- `wsl -e bash -lc "cd /mnt/e/opencell-worktrees/a33-integration && PYTHONPATH=/mnt/e/opencell-worktrees/a33-integration /mnt/e/opencell/.venv-wsl/bin/python -c 'from opencell.vivarium.karr_composite import build_karr_chassis_v3'"`
- Result: PASS

2) New integration tests
- `wsl -e bash -lc "cd /mnt/e/opencell-worktrees/a33-integration && PYTHONPATH=/mnt/e/opencell-worktrees/a33-integration /mnt/e/opencell/.venv-wsl/bin/pytest tests/integration/test_karr_chassis_v3.py -v"`
- Result: 8 passed
  - test_chassis_v3_builds: PASSED
  - test_chassis_v3_10_ticks: PASSED
  - test_chassis_v3_ratchet_closure_steady_state: PASSED
  - test_v2_chassis_still_works: PASSED
  - test_chassis_v3_all_writers_accumulate: PASSED
  - test_allocation_step_constrains_under_scarcity: PASSED
  - test_d2_and_decay_both_active: PASSED
  - test_emit_step_records_complex_trajectories: PASSED

3) A3.3 Turn 1-4 regression set
- `wsl -e bash -lc "cd /mnt/e/opencell-worktrees/a33-integration && PYTHONPATH=/mnt/e/opencell-worktrees/a33-integration /mnt/e/opencell/.venv-wsl/bin/pytest tests/vivarium/test_karr_m2_v3.py tests/vivarium/test_karr_m3_v3.py tests/vivarium/test_karr_allocation_step.py tests/vivarium/test_karr_d2_real.py tests/vivarium/test_karr_protein_decay_light.py -v"`
- Result: 32 passed

Performance + Ratchet headline
- 1000 ticks measured via 100 batches of `engine.update(10.0)`
- elapsed_s=16.211921
- chassis tick rate=61.683 ticks/s
- ratchet steady-state outcome=PASS
- worst top-10 drift=1.26% (wid=RNA_POLYMERASE, mid=34.433, late=34.000)
