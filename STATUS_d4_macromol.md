# STATUS_d4_macromol

## Beat 1 - SUT inspection + wiring design

- 2026-06-07T11:25:38Z UTC: Created STATUS scaffold.
- 2026-06-07T11:25:38Z UTC: Read `SESSION_CONTEXT.md`, `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`, `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`, the D2 SUT, the L2.2 helper/runner, existing anticheat tests, and probe templates.
- 2026-06-07T11:25:38Z UTC: Added and ran `scripts/probe_d4_macromol_inspect.py` with `bin/oc-py.cmd` to inspect the canonical replay fixture plus the raw v7.3 trace metadata.

Beat-1 contract:
- Required behavior: wire `MacromolecularComplexation` into the L2.2 Design-A runner using only channels `MacromolecularComplexationProcess.next_update()` actually mutates, with no primary-channel oracle laundering.
- Done looks like: the runner can evaluate a real D2 primary channel end-to-end, and any exact match on that primary channel is explainable by the oracle being unchanged rather than by a trace-hint replay path.

SUT inspection:
- `MacromolecularComplexationProcess.next_update()` writes only `substrates` and `complex.counts`.
- No `_maybe_replay_from_hint`, no `trace_hint`, and no after-oracle replay branch exists in `opencell/vivarium/karr_macromolecular_complexation.py`.
- Exposed WIDs by channel: `substrates=210`, `complexs=147`, `enzymes=0`.
- The canonical raw trace (`MacromolecularComplexation_100ticks.mat`) has `states_before/after` datasets for `substrates`, `complexs`, `enzymes`, and `boundEnzymes`.

Channel table:

| channel | written_by_SUT? | in_trace? | n_wids_total | n_wids_unique | classification |
| --- | --- | --- | ---: | ---: | --- |
| `complexs` | yes (`complex.counts`) | yes | 147 | 147 | PRIMARY_CANDIDATE_DIRECT_OUTPUT |
| `substrates` | yes | yes | 210 | 210 | SECONDARY_CANDIDATE_DERIVED_DELTA |
| `enzymes` | no | yes | 0 | 0 | EXPECTED_SUT_GAP_TRACE_ONLY |
| `boundEnzymes` | no | yes | 0 | 0 | EXPECTED_SUT_GAP_TRACE_ONLY |

Trace / replay observations:
- `data/karr_fixtures/per_process_replay/MacromolecularComplexation.npz` already exists and is the right Design-A oracle source, so the runner can follow the existing 5-process loader pattern.
- Replay fixture keys: `state_before__{substrates,complexs,enzymes,boundEnzymes}` and `states_after__{substrates,complexs,enzymes,boundEnzymes}`.
- Replay fixture change counts are all zero across 100 ticks: `substrates=0`, `complexs=0`, `enzymes=0`, `boundEnzymes=0`.
- A tick-0 runner-shape probe showed `refresh_allocator_views()` supplies nonzero allocated substrates (`allocated_nonzero=144`, `allocated_sum=3532.0`), but the SUT still emits zero nonzero updates on tick 0. This is consistent with the oracle no-op and not with a harness starvation bug.

Duplicate-WID check:
- `substrates`: 210 total / 210 unique / 0 duplicate WIDs.
- `complexs`: 147 total / 147 unique / 0 duplicate WIDs.
- Decision: no positional shadow store is needed for D2.

Decision:
- PRIMARY channel: `complexs`.
- SECONDARY channels: `substrates`.
- SUT_BIOLOGY_GAP / not wired into `_PROCESS_OUTPUT_CHANNELS`: `enzymes`, `boundEnzymes`.
- Bucket: `ALGORITHMIC_SHALLOW`.
- Rationale: the process is stochastic (`_rng.choice`, `_rng.poisson`) but has no deep chromosome or long-range state dependency; it consumes only the current allocated subunit snapshot plus fixed stoichiometry.

Notes for Beat 2:
- The helper must overlay `oracle_before_substrates` and `oracle_before_complexs`.
- The helper must not overlay any `oracle_after_*` value on `complexs` (primary) or `substrates`.
- The loader should normalize `enzymes` / `boundEnzymes` to zero-width arrays or ignore them entirely for runner wiring, because the SUT exposes zero enzyme WIDs while the replay fixture stores MATLAB-empty arrays with shape `(100, 2)`.

## Beat 2 - tick dispatcher

- 2026-06-07T11:30:31Z UTC: Added D2 support to `tests/vivarium/_l2_2_design_a_runner_helpers.py`.
- 2026-06-07T11:30:31Z UTC: Verified no regressions in the existing generic anticheat file with `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a_runner_anticheat.py -q` -> `6 passed`.

Changes:
- Added `_MACROMOL_ORACLE_PATH`.
- Added `_load_macromol_oracle()` using the existing replay fixture `data/karr_fixtures/per_process_replay/MacromolecularComplexation.npz`.
- Normalized D2 `enzymes` to zero-width arrays in the loader because the SUT exposes zero enzyme WIDs.
- Added `_macromol_process(seed)`.
- Added `_run_macromol_tick(seed, tick, state)`.
- Added `MacromolecularComplexation` to helper oracle/tick dispatch tables.

Primary-channel anti-laundering notes:
- `_run_macromol_tick()` overlays only `oracle_before_substrates` and `oracle_before_complexs`.
- No `oracle_after_*` overlay is applied to the primary channel (`complexs`) or to the secondary channel (`substrates`).
- The helper explicitly disables `_maybe_replay_from_hint` if such an attribute ever appears on the process in the future, even though the current SUT has no such method.

Diff stat:
- `tests/vivarium/_l2_2_design_a_runner_helpers.py | 100 insertions`

## Beat 3 - runner wiring + anticheat tests

Pending.

## Beat 4 - inversion

Pending.

## Beat 5 - smoke gate

Pending.
