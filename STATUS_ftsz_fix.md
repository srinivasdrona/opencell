## FtsZ faithful-port status

- 2026-06-16T15:00:46Z UTC - Read `SESSION_CONTEXT.md`, current Python/tests surfaces, fixture metadata, and the extracted Karr doc. The local checkout did not contain `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/FtsZPolymerization.m`, so I fetched the canonical CovertLab `FtsZPolymerization.m` source to mirror `evolveState`, `integrateODEs`, `discretizeEnzymes`, and `applySubstrateLimits` faithfully.
- 2026-06-16T15:11:39Z UTC - Replaced the stochastic/homeostasis implementation in `opencell/vivarium/karr_ftsz_polymerization.py` with a faithful Karr-style ODE flow: `solve_ivp(method="BDF")`, last all-nonnegative accepted state, monomer-mass-preserving enzyme discretization, and `applySubstrateLimits` substrate clamping while keeping the Vivarium GTP allocation surface.
- 2026-06-16T15:11:39Z UTC - Rewrote `tests/vivarium/test_karr_ftsz_polymerization.py` around source-level invariants. Narrow verification is green: `bin/oc-pytest.cmd tests/vivarium/test_karr_ftsz_polymerization.py -x -v` (8 passed) and `bin/oc-pytest.cmd tests/vivarium/test_karr_ftsz_polymerization_l2_replay.py -x -v` (1 passed).
- 2026-06-16T15:12:22Z UTC - Committed checkpoint `c1d9e2f` on `fix/ftsz-polymerization-faithful-port`.

### Final block

- Files changed: `opencell/vivarium/karr_ftsz_polymerization.py`, `tests/vivarium/test_karr_ftsz_polymerization.py`, `STATUS_ftsz_fix.md`
- Test results: `bin/oc-pytest.cmd tests/vivarium/test_karr_ftsz_polymerization.py -x -v` => 8 passed; `bin/oc-pytest.cmd tests/vivarium/test_karr_ftsz_polymerization_l2_replay.py -x -v` => 1 passed
- Blockers: none
