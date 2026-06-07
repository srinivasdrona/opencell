# STATUS_d5_cytokinesis

## Progress Log

- 2026-06-07T12:52:06Z UTC: Read `SESSION_CONTEXT.md`, `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`, and `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`; started Cytokinesis L2.2 wiring audit.
- 2026-06-07T12:52:06Z UTC: Loaded `opencell/vivarium/karr_cytokinesis.py`, `tests/vivarium/_l2_2_design_a_runner_helpers.py`, `tests/vivarium/l2_2_design_a_runner.py`, existing anticheat tests, and probe templates to establish the write surface and harness pattern.
- 2026-06-07T13:00:32Z UTC: Probed Cytokinesis replay artifacts and raw trace metadata via WSL Python; established channel coverage, duplicate-WID counts, no-op replay behavior, and PRIMARY-channel choice.
- 2026-06-07T13:04:57Z UTC: Added Cytokinesis helper loader/process/dispatcher; verified the helper avoids production-side oracle file I/O by forcing a non-resolving `trace_path` override and still returns the honest no-op substrate vector.

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
| `substrates` | yes, but only `GTP` | yes | 3 | 3 | PRIMARY_CANDIDATE |
| `enzymes` | no | yes | 4 | 4 | SUT_BIOLOGY_GAP |
| `boundEnzymes` | no | yes | 4 | 4 | SUT_BIOLOGY_GAP |
| `cell.division_progress` | yes | no | n/a | n/a | UNOBSERVABLE_TO_RUNNER |
| `cell.division_complete` | yes | no | n/a | n/a | UNOBSERVABLE_TO_RUNNER |
| `requests.karr_cytokinesis.GTP` | yes | no | n/a | n/a | INPUT_SIDE_ONLY |

Decision:
- PRIMARY channel: `substrates`
- SECONDARY channels: none
- `expected_sut_gap`: `enzymes`, `boundEnzymes`
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

Pending.

## Beat 4 - inversion

Pending.

## Beat 5 - smoke gate

Pending.
