# STATUS_h_validate_cpx_basis_flip

## INTENT
Validate at scale whether the operator's GLPK heuristic changes in `_solve_fba_glpk` (`glp_cpx_basis` + `GLP_RT_FLIP`) preserve test integrity and improve trajectory/audit fidelity, using the exact 3-step Day-43 protocol.

## Step 1 Result (Unit Tests)
- `tests/m1/test_karr_metabolism.py`: **7 passed, 0 failed**.
- Vivarium trio: **19 passed, 1 failed**.
- Only failure observed: `tests/vivarium/test_karr_metabolism_pools_throttle.py::test_throttle_on_with_starved_atp_freezes_m2_synthesis`.
- **Known failure pattern preserved; no new failures.**

## Step 2 Result (100-Tick Trajectory Probe)
- Tick-99 L1 (Day-43 run): **9,722,336**.
- Day-42 baseline tick-99 L1: **4,700,000**.
- Percent reduction vs Day-42 baseline: **-106.86%** (i.e., **106.86% increase**, worse).
- Headline classification per spec: **>2.5M => per-sample improvement did not scale to trajectory**.

## Step 3 Result (500-Sample L2.2 Audit)
- `result.json::channels.substrates.w1_oc_vs_karr` (Day-43 run): **161.380974358974**.
- Threshold check (`W1 < 102`): **FAIL**.
- Comparison:
  - Day-40 baseline (HiGHS): 171.39 -> Day-43: 161.380974 (**-10.009026**, -5.84%).
  - Day-41 (GLPK pricing=STD): 161.38 -> Day-43: 161.380974 (**+0.000974**, +0.0006%, effectively unchanged).

## Overall Verdict
**FALSIFIED**

Rationale: test gate remained stable, but trajectory behavior regressed strongly (tick-99 L1 far above baseline) and L2.2 W1 did not improve beyond Day-41 nor reach the pass threshold.

## VERIFICATION
Commands run (in order):
1. `bin\oc-pytest tests/m1/test_karr_metabolism.py -x --tb=short -q`
2. `bin\oc-pytest tests/vivarium/test_karr_metabolism_chassis.py tests/vivarium/test_karr_metabolism_l2_replay.py tests/vivarium/test_karr_metabolism_pools_throttle.py --tb=line -q`
3. `bin\oc-py scripts/probe_h_100tick_live_trajectory.py`
4. `bin\oc-py scripts/run_l2_2_metabolism_audit_day41.py`

Files modified/written:
- `tmp/h_100tick_live_trajectory.json` (overwritten by Step 2)
- `STATUS_h_100tick_live_trajectory.md` (written by Step 2 script)
- `tmp/l2_2_metabolism_audit_day41/` (written by Step 3, incl. `result.json`)
- `STATUS_h_validate_cpx_basis_flip.md` (this report)

Observed wall times:
- Step 1a test command: 89.8 s
- Step 1b test command: 238.5 s
- Step 2 probe command: 134.5 s
- Step 3 audit command: 1585.4 s
- Total (sum): 2048.2 s (~34.1 min)

## Self-audit
| # | Criterion | Pass |
|---|---|---|
| 1 | Ran Step 1 unit tests before any probes/audits | YES |
| 2 | Confirmed only known throttle failure (no extra failures) | YES |
| 3 | Ran Step 2 exactly once using specified script | YES |
| 4 | Reported tick-99 L1 and % reduction vs Day-42 baseline | YES |
| 5 | Ran Step 3 exactly once using specified audit script | YES |
| 6 | Extracted W1 from `channels.substrates.w1_oc_vs_karr` in `result.json` | YES |
| 7 | Compared Day-43 W1 against Day-40 and Day-41 baselines | YES |
| 8 | Emitted one of required verdict labels (VALIDATED/PARTIAL/FALSIFIED) | YES |
| 9 | Did not modify production code under `opencell/` | YES |
| 10 | Did not commit or push | YES |
