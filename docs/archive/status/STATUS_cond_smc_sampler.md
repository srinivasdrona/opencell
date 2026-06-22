# STATUS: ChromosomeCondensation SMC Sampler Port (L2.5 unlock cascade)

## Beat 1
In `opencell/vivarium/karr_chromosome_condensation.py` `next_update`, I added a no-hints SMC binding branch that computes `n_bound` without `trace_hint.boundEnzymes_next`, using chromosome-region sampling logic and energy/free-SMC limits so ATP hydrolysis can fire in honest mode.

## Beat 2
### (a) Tick-0 forensics anchor
Observed baseline failure (before edit) matched the operator report: OC emitted ADP-only chemistry when no hints were provided (`ATP/H2O` not consumed; `PI/H` not produced) because `n_bound` was derived from empty hint deltas.

### (b) MATLAB authority used
Port target was `ChromosomeCondensation.m evolveState` lines 240-284:
- Dissociate free SMC-ADP first.
- Compute `nBindingMax = min(ATP, H2O, free SMC)`.
- Build bindable regions from chromosome polymerized regions minus excluded windows around bound SMC-ADP.
- Stochastically bind up to `nBindingMax`.
- Apply molecule updates (`SMC/SMC-ADP`, `ATP/H2O/PI/H`).

## Beat 3 (plan executed)
- Preserved hint-path replay behavior (L2.1 path untouched in semantics).
- Added explicit no-hints sampling path for `n_bound`.
- Added chromosome sparse-field schema (`polymerizedRegions`, `complexBoundSites`) and `ChromosomeStore` parsing/fallback.
- Added no-hints region exclusion + stochastic binding helpers using process RNG (`self._rng`) only.
- Kept hydrolysis stoichiometry lines intact; only changed `n_bound` source in no-hints mode.
- Added internal synthetic complex-site reconciliation for no-hints runs where chromosome sparse fields are absent/empty.

## Beat 4 (pre-mortem results)
### Way 1: L2.1 replay regression
Signal checked: `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py`.
Result: PASS (no hint-path regression observed).

### Way 2: chromosome payload shape/availability issues
Signal checked: no-hints DD run + instrumentation of incoming chromosome state.
Result: state includes `polymerizedRegions`/`complexBoundSites` keys but both are empty defaults in this harness path; no-hints branch currently relies on synthetic fallback.

### Way 3: RNG nondeterminism
Signal checked: repeated seeded runs remain deterministic in failure location/tick.
Result: deterministic; sampling uses `self._rng` only.

## Beat 5 verification protocol results
1. `bin\oc-pytest tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -v`
- PASS (1 passed).

2. `bin\oc-pytest tests/vivarium/test_karr_chromosome_condensation.py -v`
- PASS (6 passed).

3. `bin\oc-pytest tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py -v`
- FAIL (still diverges in honest mode; latest observed first divergence at tick 9, ATP path over-binding by 2 in current revision).

4. `bin\oc-pytest tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "ChromosomeCondensation" --tb=no -q`
- FAIL summary: 17 failed, 4 skipped, 22 deselected.

5. `bin\oc-pytest tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v --tb=no -q`
- FAIL summary: 29 failed, 6 passed, 8 skipped.

## Tick-0 verification
- Baseline (pre-fix) no-hints Cond+Seg tick-0 mismatch reproduced ADP-only chemistry.
- Current revision no-hints Cond+Seg tick-0 ATP hydrolysis does fire; earliest divergence moved later (tick 9 in latest run), indicating partial fix but not bit-identical completion.

## Files changed
- `opencell/vivarium/karr_chromosome_condensation.py`
- `STATUS_cond_smc_sampler.md`

## Outcome vs success criteria
- Criterion 1 (STATUS file): ✅
- Criterion 2 (L2.1): ✅
- Criterion 3 (Cond unit tests): ✅
- Criterion 4 (Cond+Seg DD): ❌ (still failing)
- Criterion 5 (>=6/10 Cond DS flips): ❌ (not achieved)
- Criterion 6 (surgical commit): ❌ (not committed because DD is red)

## Residual blocker
No-hints harness path provides empty chromosome sparse fields for this pair; synthetic fallback improves early chemistry but still diverges at later ticks. Additional work is needed to close full bit-identity under no-hints composition.
