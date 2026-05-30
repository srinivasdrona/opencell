1. Residue WID(s): original fingerprint `substrates[0] = ATP` (tick 0, +3) shifted; current first failure is `enzymes[1] = MG_213_214_298_6MER_ADP` (tick 0, +3).
2. MATLAB file:line: `/mnt/e/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeCondensation.m:252-269` (`nBindingMax` and stochastic bind loop) and `:273-283` (substrate updates during binding).
3. Root cause: OC was anchored to legacy trace path and used Poisson relaxation throttling in `_sample_binding_events`; MATLAB evolves by binding up to `nBindingMax` each tick, so OC under-consumed ATP at tick 0.
4. Diff size in lines (<=15): 9 lines (`3` insertions, `6` deletions) in `opencell/vivarium/karr_chromosome_condensation.py`.
5. L2.1 result: shifted-failure (`[wip]`), pytest tail:
   F                                                                        [100%]
   =================================== FAILURES ===================================
   E   Failed: L2a mismatch record: tick=0, observable=enzymes, index=1, oc_val=3.0, karr_val=0.0, diff=3.0
   /mnt/e/opencell-worktrees/wave9-chromcond/tests/vivarium/l2_replay_common.py:537: Failed: L2a mismatch record: tick=0, observable=enzymes, index=1, oc_val=3.0, karr_val=0.0, diff=3.0
   1 failed in 39.99s
6. L1 chassis result: PASSED (`tests/vivarium/test_karr_chromosome_condensation.py`), tail:
   ......                                                                   [100%]
   6 passed in 44.24s
7. Commit hash: <pending>
8. Wall-time spent: ~54 minutes.
