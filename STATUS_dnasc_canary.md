# STATUS — DNASupercoiling CANARY (L2.5 CAUSE_5)

Date: 2026-06-19
Branch: current worktree

## Beat 1 — Deliberate Action Prefix
In the no-hints branch of `next_update`, compute `bound_next_effective` and `enzymes_next_effective` from sampled binding/release transitions so free/bound enzyme deltas are emitted as real transitions instead of zeros.

## Beat 2 — Probe Finding + MATLAB Anchor
Operator deep-probe finding (verbatim):

> OC's no-hints branch samples gyrase/topoIV events but NEVER updates `bound_next_effective` / `enzymes_next_effective` to reflect binding/release transitions. Karr does 3 free→bound DNA_GYRASE transitions at tick 0; OC does zero. The 3 missing bindings account for ~3 of the 4 missing ATP hydrolyses (each gyrase bind step costs `gyraseATPCost` ATP per the MATLAB doc; the 4th ATP off-by-1 likely comes from a topoIV transition not visible in the first-failure record).

MATLAB source anchor (`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNASupercoiling.m`):
- `evolveState` lines 381-389: release phase (topoIV legal-region release + gyrase processive release).
- `evolveState` lines 390-467: free-enzyme binding loop.
- `evolveState` lines 469-500: catalytic strand-passing and ATP accounting.

## Beat 3 — Plan Executed (smallest diff)
- Kept replay/hint override branch intact (`if replay_mode:` block unchanged in behavior).
- Added no-hints-only aggregate transition computation for gyrase/topoIV before catalytic sampling.
- Reused existing sampled-tick context; no extra RNG draws were introduced.
- Wired those computed next counts into `bound_next_effective` and `enzymes_next_effective` in the no-hints branch.
- Did not touch any other process file or the L2.5 harness.

## Beat 4 — Pre-mortem (Inversion)
- Way 1 (L2.1 replay regression): avoided by leaving replay-mode hint override path behavior intact.
- Way 2 (hint-path override regression): replay still sources `bound_next_effective`/`enzymes_next_effective` from `bound_next`/`enzymes_next` hints when present.
- Way 3 (ATP double-counting): no separate binding ATP term was added; ATP still comes from `_substrate_delta(atp_used)` where `atp_used` is derived from sampled catalytic events.
- Way 4 (RNG drift): no new random draws added; transition logic is deterministic from current sampled context.

## Beat 5 — Verification Protocol Run
Commands used (WSL venv per instruction):
- `wsl bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python scripts/probe_dna_supercoiling_full.py"`
- `wsl bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && pytest tests/vivarium/test_karr_dna_supercoiling_l2_replay.py -v"`
- `wsl bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && pytest tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k DNASupercoiling"`

Note: `bin/oc-pytest` is not present in WSL (`bin/oc-pytest.cmd` exists on Windows side), so `pytest` under the activated `.venv-wsl` was used.

## Probe-after (post-fix)
`python scripts/probe_dna_supercoiling_full.py` now reports exact tick-0 channel parity:
- `substrates`: total |diff| = 0
- `enzymes`: total |diff| = 0
- `boundEnzymes`: total |diff| = 0

## L2.5 Pair Outcome
`tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k DNASupercoiling`:
- `ChromosomeCondensation+DNASupercoiling`: FAIL (`CAUSE_4_UPSTREAM_STATE_POLLUTION`, ATP delta observed `-4` vs oracle `-60` in integrated composition; isolated replay for DNASupercoiling matches oracle).
- `ChromosomeSegregation+DNASupercoiling`: FAIL (`CAUSE_5_INTRINSIC_PROCESS_REPLAY_DIVERGENCE`, ATP off-by-2 molecules at tick 2: observed `-60` vs oracle `-62`).

## Files Changed
- `opencell/vivarium/karr_dna_supercoiling.py`
- `STATUS_dnasc_canary.md`

## Commit Intent
Single surgical commit for the no-hints free↔bound transition port (optional helper/test commit not used).
