# STATUS: L21 ChromosomeCondensation tick-1 complexBoundSites carryover

Result: IN PROGRESS

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

Next:

- run hidden replay, 100-tick no-hint replay, strict rubric, L1b anchors, focused tests, and Ruff
