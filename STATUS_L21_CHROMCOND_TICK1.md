# STATUS: L21 ChromosomeCondensation tick-1 complexBoundSites carryover

Result: CARRYOVER FIXED; NEXT HIDDEN MISMATCH IDENTIFIED

Current finding:

- The hidden tick-1 `complexBoundSites` mismatch is not a new ChromosomeCondensation mutation. In the oracle trace, tick 1 `states_before/chromosome` and `states_after/chromosome` are identical for `complexBoundSites` with length `206`.
- The replay/application bug is in the shared replay applier: `apply_count_update(...)` accumulated count ports but ignored the top-level `chromosome` port, so tick-0 sparse replacements were dropped from carried state.
- I reproduced that locally:
  - tick 0 emitted `complexBoundSites` replacement length `197`
  - after count-only apply, carried state stayed at length `194`
  - after full chromosome apply, carried state moved to length `197`

Planned fix:

- patch the shared replay applier to accumulate chromosome scalars (`smc_bound_count`, `condensation_level`) while replacing sparse chromosome payloads such as `complexBoundSites`
- add a focused regression that replays hidden tick 0 and tick 1 and compares the applied chromosome state against oracle `states_after`

Green chunk:

- patched `tests/vivarium/l2_replay_common.py::apply_count_update(...)` so replay carryover now applies top-level `chromosome` updates
- added `test_hidden_chromosome_replay_applies_sparse_replacements()` in `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py`
- validation so far:
  - `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -q` -> `2 passed`
  - `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation.py -q` -> `7 passed`
  - `bin\oc-py.cmd -m ruff check tests/vivarium/l2_replay_common.py tests/vivarium/test_karr_chromosome_condensation_l2_replay.py STATUS_L21_CHROMCOND_TICK1.md` -> PASS

## Exact carryover conclusion

The hidden tick-1 failure was a replay/application bug, not a production tick-1 biology bug.

- Oracle proof:
  - tick `0`: hidden `complexBoundSites` changes from length `194` to `197`
  - tick `1`: hidden `states_before/chromosome` and `states_after/chromosome` are identical for `complexBoundSites`, both length `206`
- Therefore tick 1 is a pure carryover surface. A zero direct `complexBoundSites` update is valid only if the replay applier preserves the earlier sparse replacement.
- The shared replay applier did not do that: it accumulated count ports but ignored the top-level `chromosome` port, so hidden sparse replacements were silently dropped from carried state.

## Implemented fix

- `tests/vivarium/l2_replay_common.py`
  - `apply_count_update(...)` now applies top-level `chromosome` updates:
    - accumulate numeric chromosome deltas such as `smc_bound_count` / `condensation_level`
    - replace sparse payload dicts such as `complexBoundSites`
- `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py`
  - added `test_hidden_chromosome_replay_applies_sparse_replacements()`
  - replays hidden tick `0` and tick `1`
  - applies the emitted update into state
  - asserts applied `complexBoundSites` equals oracle `states_after`
- `scripts/probe_l2_1_strict_rubric.py`
  - now injects the declared hidden read surface before classifying a process, matching the real strict-rubric test harness
- `tests/vivarium/test_l2_1_strict_rubric.py`
  - updated `ChromosomeCondensation` expected verdict from `FAIL` to `GENUINE`

## Verification

Green:

- corrected hidden replay over 100 ticks for applied `complexBoundSites`
  - tick `1` carryover now passes
  - first deeper hidden mismatch moves to tick `7`
- `bin\oc-py.cmd tmp/chromcond_nohint_probe.py`
  - `NO_MISMATCH`
- strict rubric (real classifier)
  - `_classify('ChromosomeCondensation')` -> `GENUINE`
  - `bit_identity_failures=0`
  - `karr_active=66/100`
  - `oc_fired_on_karr_active=66/100`
  - `fire_rate_when_karr_active=1.0`
- `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -q`
  - `2 passed`
- `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation.py -q`
  - `7 passed`
- `bin\oc-pytest.cmd tests/vivarium/test_l2_1_strict_rubric.py -k ChromosomeCondensation -q`
  - `1 passed`
- Ruff:
  - `tests/vivarium/l2_replay_common.py`
  - `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py`
  - `scripts/probe_l2_1_strict_rubric.py`
  - `tests/vivarium/test_l2_1_strict_rubric.py`
  - `STATUS_L21_CHROMCOND_TICK1.md`

Still failing / pre-existing:

- `bin\oc-py.cmd scripts/l1b_verify_wiring.py --process ChromosomeCondensation --strict-anchors --format plain`
  - still fails only `check_oc_anchors_resolve`
  - this is the same dirty `data/schemas/per_process_wiring/ChromosomeCondensation.yaml` anchor issue called out in the prior handoff, untouched here

## Next exact deeper hidden-state mismatch

After the carryover/applier fix, the next hidden mismatch is no longer tick 1. The first applied hidden `complexBoundSites` mismatch is:

- tick `7`
- lengths still match: `oc_len=212`, `karr_len=212`
- one site is shifted:
  - missing from OC: `(357086, 0, 82)`
  - extra in OC: `(355990, 0, 82)`

That is the next exact deeper hidden-state mismatch after the requested carryover boundary was fixed.
