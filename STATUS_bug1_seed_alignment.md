# STATUS - Bug 1 Seed Alignment

## Beat 1 - confirm the bug

Bug confirmed in [tests/vivarium/l2_2_design_a_runner.py](/E:/opencell-worktrees/bug1-seed-alignment/tests/vivarium/l2_2_design_a_runner.py:944): the runner appends the warning and then executes `"if seed_alignment_warning is not None and process_verdict == \"PASS\": process_verdict = \"FAIL\""` at [tests/vivarium/l2_2_design_a_runner.py](/E:/opencell-worktrees/bug1-seed-alignment/tests/vivarium/l2_2_design_a_runner.py:955), so any shifted-seed win can overturn an otherwise passing primary-channel result. That diagonal-alignment assumption is wrong for cross-engine ensembles because OpenCell's `numpy.random.Generator` and Karr's MATLAB `rand` do not produce meaningfully aligned seed-`N` trajectories for the same integer seed. The Day-23 Translation smoke evidence supplied for this bug matches the failure mode exactly: `observed_w1=0.006041` vs `shifted_w1=0.005502` triggered a warning-driven PASS-to-FAIL flip even though the gap is within the expected noise regime for a 50-seed, 49-shift minimum search. Pre-fix baseline: `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q` -> `33 passed in 738.07s (0:12:18)`.

verdict: PASS

## Beat 2 - implement the fix

Implemented in [tests/vivarium/l2_2_design_a_runner.py](/E:/opencell-worktrees/bug1-seed-alignment/tests/vivarium/l2_2_design_a_runner.py:416) by documenting `_seed_alignment_warning(...)` as informational-only for cross-engine ensembles, renaming the emitted identifier from `SEED_ALIGNMENT_MISMATCH` to `SEED_ALIGNMENT_DIAGNOSTIC`, and removing the PASS-to-FAIL override after `process_verdict = _process_verdict(...)` so the warning remains appended without gating the result. Existing behavior was preserved otherwise; the only literal-sensitive test was updated in [tests/vivarium/test_l2_2_design_a_runner_anticheat.py](/E:/opencell-worktrees/bug1-seed-alignment/tests/vivarium/test_l2_2_design_a_runner_anticheat.py:233) to assert the new diagnostic token.

verdict: PASS

## Beat 3 - regression test

Added [tests/vivarium/test_l2_2_design_a_seed_alignment.py](/E:/opencell-worktrees/bug1-seed-alignment/tests/vivarium/test_l2_2_design_a_seed_alignment.py:1) with 50-seed, 10-tick, 5-dimensional synthetic ensemble coverage: one test drives the real `run_design_a(...)` path with an off-by-one seed roll so `SEED_ALIGNMENT_DIAGNOSTIC` fires while the process verdict remains `PASS`, and a second test calls `_seed_alignment_warning(...)` on the same shape with diagonal-aligned vectors to confirm no seed-alignment warning fires when no shifted index beats the diagonal.

verdict: PASS

## Beat 4 - inversion

Falsifier 1: the verdict flip should only be re-enabled if a future on-OC-only ensemble harness establishes that OC seed `N` has a deterministic, semantically meaningful correspondence to OC seed `N`; that can justify diagonal seed alignment inside one engine, but it does not hold for today's cross-engine numpy-vs-MATLAB comparison. Falsifier 2: the diagnostic should only be deleted outright if we can confirm no current or future harness will ever want shifted-seed detection as a non-gating debugging aid; that is a much stronger claim than this bug fix needs, so rename-and-demote is the narrower change. Falsifier 3: the diagnostic would become statistically meaningful even cross-engine if it were paired with an explicit multiple-comparisons correction, such as a Bonferroni-style threshold calibrated against the expected minimum-over-49-shifts baseline at `N=50`, rather than treating any lower shifted mean W1 as evidence.

verdict: PASS

## Beat 5 - synthetic smoke

Command run: `bin\oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process Translation --seeds 50 --ticks 10 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/Translation_bug1_smoke`. Measured output from [tests/vivarium/artifacts/l2_2_design_a/Translation_bug1_smoke/result.json](/E:/opencell-worktrees/bug1-seed-alignment/tests/vivarium/artifacts/l2_2_design_a/Translation_bug1_smoke/result.json:1): `verdict: "PASS"`, `canonical_seed_count: 50`, primary channel `monomers` remained `PASS`, and `warnings` contains `SEED_ALIGNMENT_DIAGNOSTIC: OC outputs align better to a shifted Karr seed index on channel=monomers (shift=+37, observed_w1=0.006041, shifted_w1=0.005502).` No `KARR_SINGLE_SEED_REUSED` warning was emitted.

verdict: PASS
