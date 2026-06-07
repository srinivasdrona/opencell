# STATUS_d5_cytokinesis

## Progress Log

- 2026-06-07T12:52:06Z UTC: Read `SESSION_CONTEXT.md`, `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`, and `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`; started Cytokinesis L2.2 wiring audit.
- 2026-06-07T12:52:06Z UTC: Loaded `opencell/vivarium/karr_cytokinesis.py`, `tests/vivarium/_l2_2_design_a_runner_helpers.py`, `tests/vivarium/l2_2_design_a_runner.py`, existing anticheat tests, and probe templates to establish the write surface and harness pattern.
- 2026-06-07T13:00:32Z UTC: Probed Cytokinesis replay artifacts and raw trace metadata via WSL Python; established channel coverage, duplicate-WID counts, no-op replay behavior, and PRIMARY-channel choice.
- 2026-06-07T13:04:57Z UTC: Added Cytokinesis helper loader/process/dispatcher; verified the helper avoids production-side oracle file I/O by forcing a non-resolving `trace_path` override and still returns the honest no-op substrate vector.
- 2026-06-07T13:11:11Z UTC: Wired Cytokinesis into the Design-A runner and added Cytokinesis anticheat coverage; focused anticheat suite passed (`23 passed`).
- 2026-06-07T13:12:27Z UTC: Ran the Cytokinesis smoke gate and a follow-up write-surface probe; the runner artifact is green, but the trace-visible channels are pass-through only, so the final beat verdict is `BLOCKED_NO_VIABLE_PRIMARY`.

## Beat 1 - SUT inspection + wiring design

Contract:
- Add Cytokinesis to the L2.2 Design-A runner without laundering the PRIMARY channel from oracle-after data.
- Choose a PRIMARY channel only where the SUT actually writes and the replay oracle exposes an `after_*` vector; anything else is a documented SUT biology gap.

Evidence:
- `KarrCytokinesisProcess.next_update()` writes only `requests.karr_cytokinesis.GTP` unconditionally, plus conditional `cell.division_progress`, `cell.division_complete`, and `substrates[GTP]`.
- `_maybe_replay_from_hint` is absent and the production file contains no `trace_hint` branch.
- The raw MATLAB trace path in the worktree is stale, but the sibling repo contains both `per_process_traces/Cytokinesis_100ticks.mat` and `per_process_traces_v2/Cytokinesis_100ticks.mat`.
- `scipy.io.loadmat` fails on those raw traces because they are MATLAB v7.3/HDF5; `h5py` enumeration shows `states_before` and `states_after` contain only `substrates`, `enzymes`, and `boundEnzymes`.
- `data/karr_fixtures/per_process_replay/Cytokinesis.npz` contains only `state_before__{substrates,enzymes,boundEnzymes}` and `states_after__{substrates,enzymes,boundEnzymes}`.
- Replay oracle is a legitimate no-op window: for all 100 ticks, `before == after` on `substrates`, `enzymes`, and `boundEnzymes`.
- Cytokinesis replay substrate WIDs are `PI`, `H2O`, `H` (3 total). The SUT exposes `GTP`, `H`, `H2O`, `PI`; `GTP` is an extra internal allocator-facing substrate absent from the replay oracle.
- Duplicate-WID probe result: none. `substrates` 3 total / 3 unique, `enzymes` 4 total / 4 unique, `boundEnzymes` 4 total / 4 unique.

Write-surface table:

| channel | written_by_SUT? | in_trace? | n_wids_total | n_wids_unique | classification |
| --- | --- | --- | ---: | ---: | --- |
| `substrates` | store yes, trace-visible WIDs no (`GTP` is absent from oracle vector) | yes | 3 | 3 | RUNNER_DIAGNOSTIC_ONLY |
| `enzymes` | no | yes | 4 | 4 | SUT_BIOLOGY_GAP |
| `boundEnzymes` | no | yes | 4 | 4 | SUT_BIOLOGY_GAP |
| `cell.division_progress` | yes | no | n/a | n/a | UNOBSERVABLE_TO_RUNNER |
| `cell.division_complete` | yes | no | n/a | n/a | UNOBSERVABLE_TO_RUNNER |
| `requests.karr_cytokinesis.GTP` | yes | no | n/a | n/a | INPUT_SIDE_ONLY |

Decision:
- Diagnostic runner slot (required by current harness): `substrates`
- Viable biological PRIMARY: none
- SECONDARY channels: none
- `expected_sut_gap`: `substrates[PI,H2O,H]`, `enzymes`, `boundEnzymes`
- Positional shadow store: not needed; no duplicate WIDs on any trace-visible channel.

Bucket choice:
- `TRIVIAL_RNG`
- Rationale: `KarrCytokinesisProcess` has no stochastic branch in `next_update()` and no RNG-conditioned update path. The replay window is a deterministic no-op on the only trace-visible writable channel.

## Beat 2 - tick dispatcher

Files changed:
- `tests/vivarium/_l2_2_design_a_runner_helpers.py`

What landed:
- Added `_CYTOKINESIS_ORACLE_PATH` and `_load_cytokinesis_oracle()` using `data/karr_fixtures/per_process_replay/Cytokinesis.npz`.
- Added cached `_cytokinesis_process(seed)` factory under `forbid_sut_oracle_file_io()`.
- Added `_run_cytokinesis_tick(seed, tick, state)` to overlay only oracle-before inputs (`substrates`, `enzymes`, `boundEnzymes`), call `next_update()`, and project only the PRIMARY channel (`substrates`) back out.
- Added Cytokinesis entry to `_tick_dispatch()`.

Anti-laundering / anti-oracle notes:
- No `oracle_after_*` overlay is used on the PRIMARY channel.
- `_maybe_replay_from_hint` is checked and would be disabled if present; current SUT does not define it.
- `KarrCytokinesisProcess.__init__()` tries to inspect its default trace path via `_optional_trace_ticks()`, which would violate the L2 oracle-file guard. The helper factory therefore passes a deliberately missing `trace_path`, letting the SUT fall back to its built-in `100` tick default without touching production code.

Quick verification:
- `_run_cytokinesis_tick(0, 0, ...)` returns `substrates` equal to both oracle-before and oracle-after for tick 0.
- `trace_n_ticks` on the helper-instantiated process is `100`.

Diff stat:
- `tests/vivarium/_l2_2_design_a_runner_helpers.py | 98 insertions`

## Beat 3 - runner wiring + anticheat tests

Files changed:
- `tests/vivarium/l2_2_design_a_runner.py`
- `tests/vivarium/test_l2_2_design_a_runner_anticheat_cytokinesis.py`

Runner wiring:
- Added `Cytokinesis` to `SUPPORTED_PROCESSES`.
- Added `Cytokinesis` to `_PROCESS_BUCKET` as `TRIVIAL_RNG`.
- Added `Cytokinesis` to `_PROCESS_OUTPUT_CHANNELS` as `("substrates",)`.
- Added `Cytokinesis` to `_PROCESS_PRIMARY_CHANNEL` as `substrates` because the current runner requires a primary slot; Beat 5 documents that this is diagnostic-only and not a viable biological gate channel.
- Added `Cytokinesis` to `_PROCESS_ANALYTICAL_CHECK_REASON`.
- Added `_process_sample_process("Cytokinesis") -> runner_helpers._cytokinesis_process(0)`.
- Hardened `_observable_wids()` so fixture-backed processes can source WIDs from `fixture_substrate_wids` / `fixture_enzyme_wids`; this is required for Cytokinesis because the process does not expose `substrate_wids` / `enzyme_wids`.

Anticheat file:
- Added `tests/vivarium/test_l2_2_design_a_runner_anticheat_cytokinesis.py`

New tests:
- `test_cytokinesis_fixture_substrates_are_noop_window`
- `test_cytokinesis_tick_ignores_cheated_after_payload`
- `test_cytokinesis_constant_zero_primary_channel_fails`
- `test_cytokinesis_trace_visible_substrates_are_pass_through_on_smoke_window`

Pass count:
- `bin\oc-pytest tests/vivarium/test_l2_2_design_a_runner_anticheat.py tests/vivarium/test_l2_2_design_a_runner_anticheat_rna_decay.py tests/vivarium/test_l2_2_design_a_runner_anticheat_macromol.py tests/vivarium/test_l2_2_design_a_runner_anticheat_replication.py tests/vivarium/test_l2_2_design_a_runner_anticheat_repinit.py tests/vivarium/test_l2_2_design_a_runner_anticheat_cytokinesis.py -q`
- Result: `23 passed in 53.27s`

## Beat 4 - inversion

Falsifiers considered:
- Why not accept `substrates` as a real PRIMARY? Falsifier: if the trace-visible substrate WIDs did not intersect the SUT's actual writes, then the projected channel would be pass-through and therefore invalid as a gate. This falsifier fired: oracle WIDs are `PI/H2O/H`, but the SUT only writes `substrates[GTP]`.
- Why `TRIVIAL_RNG` and not `ALGORITHMIC_SHALLOW` or `ALGORITHMIC_DEEP`? Falsifier: any RNG draw, stochastic branch, or persistent random state affecting `next_update()` would have moved Cytokinesis out of `TRIVIAL_RNG`. Source inspection found none.
- Why no positional shadow store? Falsifier: any duplicate trace WID on `substrates`, `enzymes`, or `boundEnzymes` would have forced positional slot preservation. Duplicate-WID probe found `3/3`, `4/4`, and `4/4` unique respectively, so the shadow store would add complexity without guarding a real failure mode.
- Why no oracle-after overlay on PRIMARY? Falsifier: none. Even before the no-viable-primary conclusion, after-hint overlay on the compared channel would still be laundering and therefore wrong.
- Why is the smoke result not sufficient evidence of success? Falsifier: if the SUT actually emitted one of the trace-visible channels during the smoke window, then `w1=0` plus the no-op warning could have been a legitimate gate pass. The follow-up write-surface probe rejected that: ticks `0..4` return only `requests`, with no trace-visible substrate writes.

## Beat 5 - smoke gate

Command:
- `bin\oc-py tests/vivarium/l2_2_design_a_runner.py --process Cytokinesis --seeds 3 --ticks 5 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/Cytokinesis_smoke`

Runner artifact:
- CLI summary: `Cytokinesis PASS substrates=SEED_NOISE@0.000000`
- `result.json` primary-channel details: `w1_oc_vs_karr=0.0`, `ci95=[0.0, 0.0]`, `q95_null=0.0`, `threshold=1.0`, runner verdict `SEED_NOISE`
- Runner warnings: `KARR_SINGLE_SEED_REUSED`, `PRIMARY_CHANNEL_ORACLE_DETERMINISM_LEGITIMATE`

Follow-up probes:
- Duplicate-WID probe: not needed after Beat 1; all trace-visible channels are unique-WID.
- `oc_equals_before` / write-surface probe over ticks `0..4`:
  - trace substrate WIDs = `PI`, `H2O`, `H`
  - SUT substrate WIDs = `GTP`, `H`, `H2O`, `PI`
  - `next_update()` returns only `requests` on all five ticks
  - `update["substrates"]` is empty on all five ticks
  - projected runner `substrates` vector equals both oracle-before and oracle-after on all five ticks

Interpretation:
- The smoke artifact is honest but not gateable: the compared `substrates` vector is pass-through on the replay window because the current SUT never writes the trace-visible substrate WIDs.
- This is an i4-class SUT biology gap, not a harness laundering bug.
- No trace-visible channel satisfies the Beat 1 PRIMARY contract for Cytokinesis in the current SUT.

verdict: BLOCKED_NO_VIABLE_PRIMARY
