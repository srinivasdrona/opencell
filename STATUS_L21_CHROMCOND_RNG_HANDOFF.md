# STATUS: L21 ChromosomeCondensation RNG Handoff

Result: HANDOFF FIXED; NEXT EXACT DIVERGENCE IDENTIFIED

The warmup-to-tick0 RNG handoff is now traced to the real extraction boundary and mirrored in production. WholeCell replay extraction does not carry the `initializeState()` warmup endpoint `randStream.state=1279689633` into tick 0. It loads an already initialized fitted snapshot, then reseeds the simulation and every process back to the seed-local `mcg16807` stream before capture. Production now preserves the loaded chromosome / pool surface but starts replay ticks from the same seeded process-local state `931316785`. That moved the first hidden mismatch off tick 0 and exposed the next exact divergence at tick 1.

## What I read

- `SESSION_CONTEXT.md`
- prior ChromCond status trail:
  - `STATUS_L21_CHROMCOND.md`
  - `STATUS_L21_CHROMCOND_FOLLOWUP.md`
  - `STATUS_L21_CHROMCOND_RESTART.md`
  - `STATUS_L21_CHROMCOND_POSTWARMUP.md`
  - `STATUS_L21_CHROMCOND_RNG_FIX.md`
  - `STATUS_L21_CHROMCOND_GEOMETRY_FIX.md`
- primary WholeCell source:
  - `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m`
  - `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/initializeState.m`
  - `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/Simulation.m`
- extraction helpers:
  - `scripts/matlab/karr_bootstrap.m`
  - `scripts/matlab/extract_per_process_traces_v2.m`
  - `scripts/matlab/extract_translation_ensemble.m` (`seed_simulation`)
- replay/fix harnesses under `tests/vivarium`

## Exact source call/order behind the reset to `931316785`

1. WholeCell process streams are private `mcg16807` streams, and `Process.seedRandStream()` resets a process stream from `this.seed`.
   - `Process.m:282-290`

2. A fresh full simulation run does seed once, then calls each process `copyFromState() -> initializeState() -> copyToState()` in init order.
   - `@Simulation/initializeState.m:61`
   - `@Simulation/initializeState.m:267-273`

3. But the extraction path used for replay does not start from a fresh `initializeState()` run. `scripts/matlab/karr_bootstrap.m` loads `data/Simulation_fitted.mat` and returns that already initialized simulation object.
   - `scripts/matlab/karr_bootstrap.m:41-49`

4. `scripts/matlab/extract_per_process_traces_v2.m` then calls `seed_simulation(sim, seed)` before capture.
   - `scripts/matlab/extract_per_process_traces_v2.m:145-150`

5. `seed_simulation` applies the seed and calls `sim.seedRandStream()`.
   - `scripts/matlab/extract_translation_ensemble.m:387-392`

6. `Simulation.seedRandStream()` resets the simulation stream, every state stream, and every process stream from that seed.
   - `@Simulation/Simulation.m:430-459`

Therefore the replay capture boundary is:

- preserve the fitted snapshot's chromosome / molecule surface
- reseed the `ChromosomeCondensation` process-local `mcg16807` stream to the seed-default state
- begin tick 0 from that reseeded process stream

For seed `0`, the real process-local starting state is `931316785`, not the warmup endpoint `1279689633`.

## Production change

Updated `opencell/vivarium/karr_chromosome_condensation.py`:

- constructor now initializes `_rng` as `MatlabRandStream(seed, generator="mcg16807")`
- removed `_restore_validated_postwarmup_rng(...)`
- retained `_load_postwarmup_state(...)` and `_restore_validated_postwarmup_pools()` so the loaded replay surface still matches the warmup-produced chromosome / molecule state

Added focused regression coverage in `tests/vivarium/test_karr_chromosome_condensation.py`:

- `test_replay_rng_starts_from_seeded_process_stream()`
- asserts replay starts from seeded `mcg16807` state `931316785`
- asserts that seeded tick 0 does not reuse the saved warmup endpoint state

## Verification

Green:

- `bin/oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation.py -q`
  - `7 passed`
- `bin/oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -q`
  - `1 passed`
- `bin/oc-py.cmd tmp/chromcond_nohint_probe.py`
  - `NO_MISMATCH` over the 100-tick observable replay
- `bin/oc-py.cmd tmp/chromcond_hidden_mismatch_probe.py`
  - first hidden mismatch is now tick `1`, not tick `0`
- `bin/oc-py.cmd -m ruff check opencell/vivarium/karr_chromosome_condensation.py tests/vivarium/test_karr_chromosome_condensation.py`
  - PASS

Not green:

- `bin/oc-py.cmd scripts/probe_l2_1_strict_rubric.py --process ChromosomeCondensation`
  - still `FAIL`
  - `Karr 66%`, `OC 71%`, `OC|Karr 95%`
- `bin/oc-py.cmd scripts/l1b_verify_wiring.py --process ChromosomeCondensation --strict-anchors --format plain`
  - still fails only `check_oc_anchors_resolve`
  - this matches the pre-existing dirty `data/schemas/per_process_wiring/ChromosomeCondensation.yaml`, not the handoff patch

## Exact next divergence after the handoff fix

`bin/oc-py.cmd tmp/chromcond_hidden_mismatch_probe.py` now reports:

- first hidden mismatch: tick `1`
- `karr_len 206`
- `oc_len 0`
- `extra []`
- missing examples:
  - `(24, 3, 50)`
  - `(2553, 1, 200)`
  - `(3342, 0, 82)`
  - `(7911, 0, 1)`
  - `(9947, 0, 82)`
  - `(18502, 0, 82)`

That is the exact subsequent process-semantic divergence requested by the prompt. It indicates the warmup-to-tick0 RNG boundary is no longer the load-bearing bug. The next real issue is hidden chromosome `complexBoundSites` carryover/application between tick 0 and tick 1.

## Bottom line

I did not reach bit identity / strict-rubric `GENUINE` in this turn. But I did close the focused RNG handoff task honestly:

- traced the real source call/order that resets the process RNG to `931316785`
- implemented the matching production boundary
- proved the first hidden mismatch moved from tick 0 to the next exact divergence at tick 1

That satisfies the task's alternate done condition: one exact subsequent process-semantic divergence after the handoff is fixed.
