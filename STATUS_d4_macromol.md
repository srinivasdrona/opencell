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
| `substrates` | yes | yes | 210 | 210 | PRIMARY_CANDIDATE_NONZERO_DIRECT_DELTA |
| `complexs` | yes (`complex.counts`) | yes | 147 | 147 | SECONDARY_CANDIDATE_ALL_ZERO_TRACE |
| `enzymes` | no | yes | 0 | 0 | EXPECTED_SUT_GAP_TRACE_ONLY |
| `boundEnzymes` | no | yes | 0 | 0 | EXPECTED_SUT_GAP_TRACE_ONLY |

Trace / replay observations:
- `data/karr_fixtures/per_process_replay/MacromolecularComplexation.npz` already exists and is the right Design-A oracle source, so the runner can follow the existing 5-process loader pattern.
- Replay fixture keys: `state_before__{substrates,complexs,enzymes,boundEnzymes}` and `states_after__{substrates,complexs,enzymes,boundEnzymes}`.
- Replay fixture change counts are all zero across 100 ticks: `substrates=0`, `complexs=0`, `enzymes=0`, `boundEnzymes=0`.
- Replay fixture nonzero elements: `substrates_before=14400`, `substrates_after=14400`, `complexs_before=0`, `complexs_after=0`.
- A tick-0 runner-shape probe showed `refresh_allocator_views()` supplies nonzero allocated substrates (`allocated_nonzero=144`, `allocated_sum=3532.0`), but the SUT still emits zero nonzero updates on tick 0. This is consistent with the oracle no-op and not with a harness starvation bug.

Duplicate-WID check:
- `substrates`: 210 total / 210 unique / 0 duplicate WIDs.
- `complexs`: 147 total / 147 unique / 0 duplicate WIDs.
- Decision: no positional shadow store is needed for D2.

Decision:
- PRIMARY channel: `substrates`.
- SECONDARY channels: `complexs`.
- SUT_BIOLOGY_GAP / not wired into `_PROCESS_OUTPUT_CHANNELS`: `enzymes`, `boundEnzymes`.
- Bucket: `ALGORITHMIC_SHALLOW`.
- Rationale: the process is stochastic (`_rng.choice`, `_rng.poisson`) but has no deep chromosome or long-range state dependency; it consumes only the current allocated subunit snapshot plus fixed stoichiometry.
- Primary-channel revision note: initial Beat-1 draft chose `complexs`, but the Beat-3 anticheat falsified that choice because the oracle is all-zero on `complexs`, so an all-zero cheat cannot be distinguished there. `substrates` stays no-op too (`before == after`) but remains nonzero and therefore provides a real W1 signal under adversarial zero-output tests.

Notes for Beat 2:
- The helper must overlay `oracle_before_substrates` and `oracle_before_complexs`.
- The helper must not overlay any `oracle_after_*` value on `substrates` (primary) or `complexs`.
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
- No `oracle_after_*` overlay is applied to the primary channel (`substrates`) or to the secondary channel (`complexs`).
- The helper explicitly disables `_maybe_replay_from_hint` if such an attribute ever appears on the process in the future, even though the current SUT has no such method.

Diff stat:
- `tests/vivarium/_l2_2_design_a_runner_helpers.py | 100 insertions`

## Beat 3 - runner wiring + anticheat tests

- 2026-06-07T11:36:41Z UTC: Wired `MacromolecularComplexation` into `tests/vivarium/l2_2_design_a_runner.py`.
- 2026-06-07T11:36:41Z UTC: Added `tests/vivarium/test_l2_2_design_a_runner_anticheat_macromol.py`.
- 2026-06-07T11:36:41Z UTC: Re-ran the full Design-A anticheat slice with `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a_runner_anticheat.py tests/vivarium/test_l2_2_design_a_runner_anticheat_rna_decay.py tests/vivarium/test_l2_2_design_a_runner_anticheat_macromol.py tests/vivarium/test_l2_2_design_a_runner_protein_decay_anticheat.py -q` -> `16 passed`.

Runner wiring:
- Added `MacromolecularComplexation` to `SUPPORTED_PROCESSES`.
- Added `MacromolecularComplexation` to `_PROCESS_BUCKET` as `ALGORITHMIC_SHALLOW`.
- Added `MacromolecularComplexation` to `_PROCESS_OUTPUT_CHANNELS` as `("substrates", "complexs")`.
- Added `MacromolecularComplexation` to `_PROCESS_PRIMARY_CHANNEL` with revised primary `substrates`.
- Added `MacromolecularComplexation` to `_PROCESS_ANALYTICAL_CHECK_REASON`.
- Added D2 cases to `_process_sample_process()`, `_observable_wids()`, and `run_design_a()` state assembly.

New anticheat tests:
- `test_macromol_tick_ignores_cheated_after_payload`
- `test_macromol_constant_zero_primary_fails`
- `test_macromol_primary_exact_match_is_legitimate_noop`

Pass count:
- Existing runner anticheat slice: `13` tests before this work.
- Added MacromolecularComplexation tests: `3`.
- Current runner anticheat slice total: `16 passed`.

Beat-3 falsifier caught early:
- Falsifier: "If `complexs` is the primary channel but the oracle is identically zero there, a zero-output cheat will not move W1 and the anticheat becomes toothless."
- Result: falsified. Primary moved from `complexs` to `substrates` before the Beat-3 commit.

## Beat 4 - inversion

- 2026-06-07T11:39:47Z UTC: Wrote explicit falsifiers after the Beat-3 primary-channel revision.

Falsifiers considered and rejected:
- Primary channel choice: `substrates` is primary, not `complexs`.
  Falsifier: if `complexs` had any nontrivial support in the replay fixture (`n_nonzero_karr >= 30` or even just a nonzero all-zero-cheat W1), it would be the more direct D2-owned primary.
  Rejection evidence: Beat-3 anticheat plus the probe showed `complexs_before=0`, `complexs_after=0`, so `complexs` cannot discriminate a cheated zero-output path.
- Secondary channel choice: `complexs` stays secondary, not dropped.
  Falsifier: if `complexs` were absent from the SUT write surface or absent from the trace, it would move from SECONDARY to SUT_GAP / unwired.
  Rejection evidence: `next_update()` does write `complex.counts`, and both the raw trace and replay fixture expose `complexs`; it is real, just all-zero on this oracle slice.
- Bucket choice: `ALGORITHMIC_SHALLOW`, not `TRIVIAL_RNG` and not `ALGORITHMIC_DEEP`.
  Falsifier for `TRIVIAL_RNG`: if `_rng.choice` / `_rng.poisson` were absent and the process reduced to pure deterministic arithmetic, the bucket would drop to `TRIVIAL_RNG`.
  Falsifier for `ALGORITHMIC_DEEP`: if the tick needed chromosome state, RNAP occupancy, replication state, or other deep cross-process stores to compute its delta, it would move to `ALGORITHMIC_DEEP`.
  Rejection evidence: the SUT only uses stoichiometry, the current allocated substrate snapshot, and its own RNG.
- Positional shadow store: no positional shadow store.
  Falsifier: any duplicate WID count greater than zero on a wired output channel would have forced an i3-style positional store.
  Rejection evidence: `substrates=210/210 unique`, `complexs=147/147 unique`, so dict overlay is safe.
- After-hint overlay: none on the primary channel.
  Falsifier: none. An `oracle_after_*` overlay on a measured primary channel is always wrong because it launders the oracle.
  Rejection evidence: `_run_macromol_tick()` uses only before-state overlays, and the cheated-after-payload anticheat stays invariant.
- Trace-only channels: `enzymes` and `boundEnzymes` remain unwired.
  Falsifier: if the SUT exposed nonzero enzyme WIDs and `next_update()` returned deltas on either channel, they would move into `_PROCESS_OUTPUT_CHANNELS`.
  Rejection evidence: the SUT exposes zero enzyme WIDs and writes neither channel.

## Beat 5 - smoke gate

- 2026-06-07T11:39:47Z UTC: Ran the small-scale Design-A gate with:
  `bin\oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process MacromolecularComplexation --seeds 3 --ticks 5 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/MacromolecularComplexation_smoke`

Observed CLI summary:
- `MacromolecularComplexation PASS substrates=SEED_NOISE@0.000000 complexs=INSUFFICIENT_SAMPLES@0.000000`

Primary channel result:
- Channel: `substrates`
- Verdict: `SEED_NOISE`
- `w1_oc_vs_karr = 0.0`
- `w1_oc_vs_karr_ci95 = [0.0, 0.0]`
- `q95_null = 0.0`
- `threshold = 1.0`
- Warning: `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE`

Secondary channel result:
- Channel: `complexs`
- Verdict: `INSUFFICIENT_SAMPLES`
- `w1_oc_vs_karr = 0.0`
- `n_nonzero_oc = 0`
- `n_nonzero_karr = 0`
- Interpretation: documented all-zero oracle slice; retained as diagnostic visibility only.

Follow-up probes:
- No additional duplicate-WID / oc-equals-before / write-surface probes were needed after the smoke gate because the chosen primary already passed and the legitimate-determinism warning matched the Beat-1 replay audit.

Artifacts:
- `tests/vivarium/artifacts/l2_2_design_a/MacromolecularComplexation_smoke/result.json`
- `tests/vivarium/artifacts/l2_2_design_a/MacromolecularComplexation_smoke/SUMMARY.json`

verdict: PASS_PRIMARY_WITH_DOCUMENTED_GAPS
