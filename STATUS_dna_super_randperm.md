# STATUS — dna_super_randperm (2026-06-02)

## Beat 1 — Contract
- Port MATLAB per-tick `randperm` enzyme ordering from `DNASupercoiling.m` line 391 and line 470 into `opencell/vivarium/karr_dna_supercoiling.py`, consuming from one shared replay stream in MATLAB call order.
- Done target: replay test GREEN (`1 passed`) or honest RED with a changed fingerprint plus named structural reason.

## Beat 2 — Surface
- Read:
  - `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`
  - `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`
  - `opencell/vivarium/karr_dna_supercoiling.py`
  - `opencell/util/matlab_rng.py`
  - `tests/util/test_matlab_rng.py`
  - `tests/vivarium/test_karr_dna_supercoiling_l2_replay.py`
  - `docs/phase_f/matlab_rng_shim_notes.md`
  - MATLAB source body (`evolveState`) lines 300-510 from `E:\opencell-mirrors\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\DNASupercoiling.m` (worktree copy was not present under `data/m1_sources/...`).
- Wrote:
  - `opencell/vivarium/karr_dna_supercoiling.py`
  - `tests/vivarium/test_karr_dna_supercoiling_rng_audit.py` (created and extended)
  - `docs/phase_f/matlab_rng_shim_notes.md` (append note)
  - `STATUS_dna_super_randperm.md`
- Suspect patterns called out pre-edit:
  - Replay RNG still on NumPy stream in this worktree (pre-sister wiring state).
  - No `randperm` consumption in per-tick enzyme path.

## Beat 3 — Expected outcome
- Primary falsifier command:
  - `wsl bash -c "cd /mnt/e/opencell-worktrees/dna-super-randperm && /mnt/e/opencell/.venv-wsl/bin/python -m pytest tests/vivarium/test_karr_dna_supercoiling_l2_replay.py -v --tb=short 2>&1 | tail -40"`
- Expected: GREEN (`1 passed`) or at minimum changed mismatch tuple (tick/index/diff) relative to baseline.

## Beat 4 — Inversion pre-mortem
- Failure mode A: consume extra draws without actually threading order through catalytic logic.
- Failure mode B: wrong 1-based→0-based conversion for MATLAB `randperm`.
- Failure mode C: wrong stream (second RNG instance) or wrong call order breaks downstream alignment.
- Failure mode D: trace-cribbing or new oracle reads in production code.

## Beat 5 — Act then verify
1. Baseline replay (pre-edit): FAILED with `tick=11, observable=substrates, index=0, diff=-2.0`.
2. Confirmed MATLAB scopes:
   - line 391 `randperm(length(this.enzymes))` controls outer enzyme-binding loop order.
   - line 470 `randperm(length(enzProps))` controls enzyme-property order in linking-number/substrate loop.
3. Implemented in `karr_dna_supercoiling.py`:
   - sister-branch replay stream wiring (`MatlabRandStream` usage for replay stream sites).
   - first per-tick `randperm(len(self.enzyme_wids))` (binding-order site).
   - second per-tick `randperm(len(self.enzyme_wids))` (catalytic-order site).
   - replay catalytic event application in permuted order under ATP budget.
4. Extended audit harness (`test_karr_dna_supercoiling_rng_audit.py`) to assert call pattern includes both `randperm` draws + value-level stream alignment.
5. Post-edit replay falsifier: FAILED with `tick=3, observable=substrates, index=0, diff=+2.0`.
6. Vivarium smoke (`-x --no-header`): first failure unchanged and outside dna_super (`test_karr_central_dogma_chassis.py::test_central_dogma_states_stable_at_ss`).
7. Rule-8 lint test: PASSED.
8. Shim goldens: `15 passed, 3 xpassed`.
9. RNG audit harness: PASSED.
10. Rule-8 grep over added vivarium lines: empty.

## Draw-count Table (ticks 3 / 11 / 50)
Replay tick draw counts measured against pre-edit code vs post-edit code:

| tick | pre total | pre methods | post total | post methods |
|---|---:|---|---:|---|
| 3 | 1 | `{'random': 1}` | 3 | `{'randperm': 2, 'rand': 1}` |
| 11 | 1 | `{'random': 1}` | 3 | `{'randperm': 2, 'rand': 1}` |
| 50 | 1 | `{'random': 1}` | 3 | `{'randperm': 2, 'rand': 1}` |

## Verification Outputs (summary)
- Replay pre-edit:
  - `FAILED ... tick=11 ... diff=-2.0`
- Replay post-edit:
  - `FAILED ... tick=3 ... diff=+2.0`
- `tests/vivarium/test_karr_dna_supercoiling_rng_audit.py`:
  - `1 passed`
- `tests/prompts/test_rule8_no_oracle_reads.py`:
  - `1 passed`
- `tests/util/test_matlab_rng.py`:
  - `15 passed, 3 xpassed`
- `tests/vivarium/ -x --no-header`:
  - stops at unrelated central-dogma failure after `29 passed, 2 skipped, 1 failed`
- Rule-8 self-audit grep:
  - command: `git diff opencell/vivarium/ | Select-String -Pattern '^\\+[^+].*(open\\(|loadmat|h5py\\.File|np\\.load|read_csv|Path.*read_)'`
  - output: empty

## Verdict
HONEST RED (changed fingerprint, not GREEN).  
The mismatch moved from `tick=11, diff=-2` (pre-edit branch state) to `tick=3, diff=+2` (post-edit), and per-tick draw pattern now includes both required `randperm` calls. Residual error is consistent with remaining algorithmic divergence category **(b)/(c)** from the directive: the replay Python bulk approximation still does not fully match MATLAB’s per-region enzyme loop semantics even with draw-order parity.
