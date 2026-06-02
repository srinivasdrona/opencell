# Beat 1-5

### Beat 1 — Pause and name the contract
- Required behavior: replace NumPy RNG usage in `opencell/vivarium/karr_protein_modification.py` with `MatlabRandStream` at the replay draw sites (constructor + stochastic round + weighted reaction pick), while preserving Rule-8 constraints and no tick-targeted branches.
- Done as a system property: either L2.1 pmod replay turns GREEN, or if still RED, we produce an honest residue classification with structural cause and explicit randStream-site coverage.

### Beat 2 — Point at the surface
- Read surfaces: `opencell/vivarium/karr_protein_modification.py`, `opencell/util/matlab_rng.py`, `tests/util/test_matlab_rng.py`, `tests/vivarium/test_karr_protein_modification_l2_replay.py`, `docs/phase_f/matlab_rng_shim_notes.md`, and MATLAB source lines 350-385 from `E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\ProteinModification.m`.
- Write surfaces: `opencell/vivarium/karr_protein_modification.py`, `tests/vivarium/test_karr_protein_modification_rng_audit.py`, `docs/phase_f/matlab_rng_shim_notes.md`, `STATUS_pmod_shim_retest.md`.
- Suspect patterns called out before editing: `_RANDSAMPLE_STREAM_BURN` NumPy-era burn compensation, scalar/vector shape mapping from `random_sample` to shim `.rand`, and possible non-RNG arithmetic collapse in `_limit_over_requirements`.

### Beat 3 — Verbalize the expected outcome
- Falsifier command: `pytest tests/vivarium/test_karr_protein_modification_l2_replay.py -v --tb=short`.
- Expected change: RED (`tick=19, substrates[0], diff=-1`) should flip to GREEN, or at minimum shift fingerprint if RNG divergence is the root cause.

### Beat 4 — Invert (pre-mortem)
- Failure mode 1: trace-cribbing (adding oracle file reads in production path) could fake replay correctness.
- Failure mode 2: tick-targeted/call-count-targeted branching could force local agreement without true stochastic equivalence.
- Failure mode 3: superficial stream-object swap while leaving stale RNG semantics (burn hacks or wrong shape calls) could make tests pass for the wrong reason.

### Beat 5 — Act, then verify
- Applied changes:
  - Swapped process RNG to `MatlabRandStream(seed, generator='mt19937ar')`.
  - Removed `_RANDSAMPLE_STREAM_BURN` and NumPy burn loop.
  - Replaced scalar draw with `self._rng.rand()` and vector draw with `self._rng.rand(*fractional.shape)`.
  - Added pmod RNG audit test asserting per-tick call-pattern stability (25 ticks) and tick-0 value equality vs standalone `MatlabRandStream(0)`.
- Verification results are logged below with command outputs and verdict.

## Draw Count Table (Replay Path)

| Tick | Pre (RandomState path) | Post (MatlabRandStream path) |
|---|---:|---:|
| 5 | 0 | 0 |
| 19 | 1 | 1 |
| 50 | 1 | 1 |

Commands:
- Pre script output: `PRE_COUNTS {5: 0, 19: 1, 50: 1}`
- Post script output: `POST_COUNTS {5: 0, 19: 1, 50: 1}`

## RandStream Site Coverage (Honest RED Accounting)

- MATLAB loop call sites (ProteinModification.m lines 363, 374):
  - `this.randStream.stochasticRound(...)` (line 363): emulated by `_stochastic_round_vector` using `MatlabRandStream.rand(*fractional.shape)`.
  - `this.randStream.randsample(..., true, reactionLimits)` (line 374): emulated by `_weighted_index_sample` weighted CDF selection driven by `MatlabRandStream.rand()`.
- Missing randStream call sites: none identified in the MATLAB while-loop surface for this process.
- Structural gap still observed: at failing tick 19, OC loop computes zero feasible reactions (`reaction_limits` all zero / total limit 0), so the `randsample` site is never reached. The residue persists before and after RNG swap because the divergence manifests upstream of reaction selection.
- Evidence:
  - `TICK19_WEIGHTED_CALLS 0`
  - `TICK19_REACTION_LIMITS_NONZERO 0 []`
  - `TICK19_TOTAL_LIMIT 0.0`

What would need to change to close residue:
- Fix the upstream feasibility arithmetic in `_sample_protein_fluxes` / `_limit_over_requirements` (NaN/zero-requirement handling) so tick-19 reaches the same nonzero feasible reaction set MATLAB reaches; only then can the RNG-equivalent `randsample` path influence outcome.

## VERIFICATION

- Beat 3 expected outcome: pmod L2 replay should flip GREEN or at least shift mismatch fingerprint.
- Actual measured outcome: still RED at the same fingerprint.
- Command:
  - `wsl bash -c "cd /mnt/e/opencell-worktrees/pmod-shim-retest && /mnt/e/opencell/.venv-wsl/bin/python -m pytest tests/vivarium/test_karr_protein_modification_l2_replay.py -v --tb=short -p no:cacheprovider"`
  - Output summary: `Failed: L2a mismatch record: tick=19, observable=substrates, index=0, oc_val=0.0, karr_val=1.0, diff=-1.0`.

Additional verification commands and outcomes:
- Pre-edit suite baseline (environment drift noted):
  - `wsl bash -c "... pytest tests/vivarium/ -v --no-header -p no:cacheprovider 2>&1 | tail -80"`
  - Output summary: `49 failed, 345 passed, 5 skipped, 1 xfailed`.
- Post-edit suite smoke:
  - `wsl bash -c "... pytest tests/vivarium/ -v --no-header -p no:cacheprovider 2>&1 | tail -80"`
  - Output summary: `49 failed, 346 passed, 5 skipped, 1 xfailed` (no new broad failure explosion attributable to this patch).
- Rule 8 lint:
  - `wsl bash -c "... pytest tests/prompts/test_rule8_no_oracle_reads.py -v -p no:cacheprovider"`
  - Output summary: `1 passed`.
- Shim goldens:
  - `wsl bash -c "... pytest tests/util/test_matlab_rng.py -v -p no:cacheprovider"`
  - Output summary: `15 passed, 3 xpassed`.
- New RNG audit harness:
  - `wsl bash -c "... pytest tests/vivarium/test_karr_protein_modification_rng_audit.py -v -p no:cacheprovider"`
  - Output summary: `1 passed`.
- Rule-8 self-audit (added lines only):
  - `git diff opencell/vivarium/ | rg -n "^\+.*(open\(|loadmat|h5py\.File|np\.load|read_csv|Path.*read_)"`
  - Output: *(empty)*.

Beat 4 inversion checks:
- Trace-cribbing did not materialize: no new production-side oracle reads; Rule-8 test passes and added-lines grep is empty.
- Tick-targeted patch did not materialize: no `tick == N` or call-count branch introduced.
- Wrong-shape RNG mapping did not materialize: new audit test validates replay call-shape stability and tick-0 seed-0 draw-value equivalence against standalone shim stream.

Verdict: **did-not-match** (honest RED). RNG swap landed cleanly, but matrix entry #4 is not validated by this patch alone; the residue remains `tick=19/substrates[0]/-1` with structural evidence that feasibility collapse prevents entry into MATLAB-equivalent reaction-selection draw path.
