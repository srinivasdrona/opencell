## DNADamage event-window replay status

- Full-cycle trace: `data/m1_sources/karr_native/dnadamage_fullcycle/DNADamage_32400ticks.mat`
- Metadata: `n_ticks=32400`, `rng_seed=0`
- New test: `tests/vivarium/test_karr_dna_damage_l2_replay.py::test_karr_dna_damage_l2_event_replay`

## What the full-cycle extract actually exposes

- Within-tick firing-tick count on the captured replay surface: `0`
- Within-tick Karr mapped sparse delta totals (`states_before[t] -> states_after[t]`):
  - `intrastrandCrossLinks=0`
  - `damagedBases=0`
  - `abasicSites=0`
- Within-tick mutated observable counts on the captured replay channels:
  - `substrates=0`
  - `enzymes=0` and `boundEnzymes=0` are pass-through in this harness and showed no replay-surface activity
- Cross-cycle chromosome activity is real, but it is only visible across stored steps, not within a captured before/after pair:
  - sampled `states_before/chromosome.damagedBases` edge counts were `760 -> 977 -> 1210 -> 1451 -> 1520` at ticks `0, 8000, 16000, 24000, 32399`

## Verdict

- Honest verdict from this extract: `NOT_WIRED`, not `GENUINE` or `COINCIDENTAL`
- Reason: the 32400-tick extract remains vacuous on the actual replay surface. `states_before[t]` and `states_after[t]` are identical for the captured DNADamage replay channels, so there is no honest firing-window oracle to compare against per tick.
- Per-tick RNG-replay identity therefore could not be evaluated: there are no within-tick Karr firing ticks on the captured surface.
- Temporary OC full-cycle diagnostic totals (run against the same `states_before` sequence to populate this status report) were:
  - `OC intrastrandCrossLinks=0`
  - `OC damagedBases=0`
  - `OC abasicSites=3`
- Those OC totals were intentionally **not** promoted into the committed pytest assertion because the Karr within-tick oracle totals are all zero; comparing OC against that surface would measure trace wiring failure, not a valid GENUINE-vs-COINCIDENTAL replay outcome.

## Tests

- Final committed replay file run:
  - `bin\oc-pytest tests/vivarium/test_karr_dna_damage_l2_replay.py -q -s`
  - Result: `2 passed, 0 skipped`
- This confirms:
  - existing `test_karr_dna_damage_l2_replay_identity_per_tick` still passes
  - new `test_karr_dna_damage_l2_event_replay` passes and pins the full-cycle trace semantics regression

## Commits

- Implementation commit: `1d21ad5` — `Add DNADamage full-cycle trace semantics regression`

## Guardrails

- Confirmed untouched: `opencell/vivarium/karr_allocation_step.py`
- Confirmed untouched: `opencell/vivarium/karr_transcription_v3.py`
