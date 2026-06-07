# STATUS_d2_replication

## Progress log
- 2026-06-07T12:25:40.7361569Z UTC — Read `SESSION_CONTEXT.md`, Deliberate Action Prefix, Fix Template, helper/runner templates, and `karr_replication.py`.
- 2026-06-07T12:36:00Z UTC — Confirmed `KarrReplicationProcess.next_update()` has a `trace_hint` replay branch (`_next_update_from_trace_hint`) and that the real path writes `requests`, `chromosome`, and `substrates`.
- 2026-06-07T12:52:00Z UTC — Probed available Replication replay artifacts. Prompt-named `data/m1_sources/karr_native/per_process_traces/Replication_100ticks.mat` is absent in this worktree; `data/karr_fixtures/per_process_replay/Replication.json` still references that missing MAT as its source.
- 2026-06-07T13:08:00Z UTC — Inspected `Replication.npz`, `Replication_from_flat.npz`, and `Replication_from_trajectory.npz`; ran duplicate-WID and honest-path viability probes for candidate primary channels.
- 2026-06-07T12:38:23.7154965Z UTC — Added Replication helper loader/dispatcher path using canonical `Replication.npz` projected to the 5 real-path substrate WIDs and verified `_run_replication_tick()` returns the tick-0 oracle vector with `trace_hint` held empty.
- 2026-06-07T12:44:03.5816061Z UTC — Wired Replication into the Design-A runner and added `test_l2_2_design_a_runner_anticheat_replication.py`; narrow anticheat suite is green (`19 passed`).
- 2026-06-07T12:46:00Z UTC — Recorded Beat 4 inversion/falsifiers before the smoke gate.

## Beat 1 — SUT inspection + wiring design

### Contract notes
- `KarrReplicationProcess.next_update()` real path writes:
  - `requests.karr_replication.<DATP/DCTP/DGTP/DTTP/ATP>` on every non-idle tick
  - `chromosome.fork_position_bp.{left,right}` during elongation
  - `chromosome.replication_state` and `chromosome.events.replication_complete` at state transitions / completion
  - `substrates.<DATP/DCTP/DGTP/DTTP/ATP>` depletion on productive ticks
- `KarrReplicationProcess.next_update()` real path does **not** write `enzymes` or `boundEnzymes`.
- `_next_update_from_trace_hint()` exists and is selected when `trace_hint` contains `boundEnzymes_next` or `enzymes_next`; that path emits `enzymes` / `boundEnzymes` deltas and a replay-style substrate delta. This is an anti-laundering hazard for L2.2 primary measurement.

### Available trace/oracle artifacts
- Missing in worktree: `data/m1_sources/karr_native/per_process_traces/Replication_100ticks.mat`
- Available replay exports:
  - `data/karr_fixtures/per_process_replay/Replication.npz`
  - `data/karr_fixtures/per_process_replay/Replication_from_trajectory.npz`
  - `data/karr_fixtures/per_process_replay/Replication_from_flat.npz`
- `Replication.json` manifest says the default replay export came from the missing MAT and carries snapshot properties `boundEnzymes`, `enzymes`, `substrates`.
- Empirical trace-channel check on available replay exports:
  - `Replication.npz`: `state_before/state_after` for `substrates`, `enzymes`, `boundEnzymes`, but all three channels are exact no-ops (`before == after` everywhere).
  - `Replication_from_trajectory.npz`: same three vector channels, nontrivial on all three (`substrates` 626 changed entries, `enzymes` 40, `boundEnzymes` 2 across 323 snapshots), metadata `source=trajectory`, `effective_dt_sec=100.0`.

### Channel table

| channel | written_by_SUT? | in_trace? | n_wids_total | n_wids_unique | classification |
| --- | --- | --- | --- | --- | --- |
| `substrates` full trace vector | partial | yes | 16 | 16 | trace has full 16-wide vector; real SUT writes only `DATP/DCTP/DGTP/DTTP/ATP` and does not emit byproduct/product legs (`PPI/H2O/H/NAD/NMN/ADP/AMP/PI`) |
| `substrates` written subset (`DATP/DCTP/DGTP/DTTP/ATP`) | yes | yes (projected from `states_after__substrates`) | 5 | 5 | only viable primary candidate |
| `enzymes` | no (real path) | yes | 13 | 13 | `expected_sut_gap`; only replay branch writes this surface |
| `boundEnzymes` | no (real path) | yes | 13 | 13 | `expected_sut_gap`; only replay branch writes this surface |
| `chromosome` | yes | no clean vector trace channel available | n/a | n/a | real SUT write surface but not wireable from available replay vectors |

### Duplicate-WID probe
- `substrates`: 16 total / 16 unique / 0 duplicate WIDs
- `enzymes`: 13 total / 13 unique / 0 duplicate WIDs
- `boundEnzymes`: 13 total / 13 unique / 0 duplicate WIDs
- Decision: no positional shadow store required for Replication.

### Primary / secondary / gaps decision
- PRIMARY channel: projected `substrates` written subset on `DATP`, `DCTP`, `DGTP`, `DTTP`, `ATP`
- Canonical Design-A oracle source for wiring: `data/karr_fixtures/per_process_replay/Replication.npz`
  - justification: this export is the direct replay artifact pointing back to the prompt-named per-process MAT source and is a legitimate no-op (`before == after`) on the written substrate subset; `Replication_from_trajectory.npz` is retained only as a diagnostic active-window probe because it is trajectory-derived (`effective_dt_sec=100`) and not the direct per-process replay export.
- SECONDARY diagnostic channels to document only, not wire as gateable runner outputs:
  - `enzymes` (`expected_sut_gap`)
  - `boundEnzymes` (`expected_sut_gap`)
- SUT_BIOLOGY_GAP / topology gap:
  - full 16-wide substrate trace contains byproduct/product terms the real SUT does not emit
  - real path also depends on chromosome state (`replication_state`, fork positions) that is absent from available replay vectors

### Bucket choice
- Bucket: `ALGORITHMIC_DEEP`
- Rationale:
  - stochastic rounding via `self._rng`
  - deep dependence on hidden chromosome state / fork progression
  - replay-branch coupling to enzyme/bound-enzyme state confirms nontrivial internal state coupling

### Beat 1 viability probe notes
- Honest-path probe against `Replication_from_trajectory.npz`:
  - default/bootstrap chromosome state (`idle`) yields pure no-op and huge substrate mismatch
  - forcing a plausible minimal real-path state (`replication_state='elongating'`) produces nonzero depletion on the 5 written substrate WIDs, but still misses the trajectory substantially
  - first-20 snapshot mean W1 on written 5-WID subset:
    - `idle_dt1`: `35.93`
    - `elongating_dt1`: `37.05`
    - `elongating_dt100`: `37.05`
- Interpretation: there is a candidate measurable primary surface (`substrates` written subset), but the honest path is currently far from the trajectory export. Beat 5 will need to decide whether this stays a documented FAIL/block or whether a better honest seeding exists inside the allowed harness surface.

## Beat 2 — tick dispatcher
- Changes:
  - added `_REPLICATION_ORACLE_PATH` and `_load_replication_oracle()` using `Replication.npz`
  - projected the raw 16-wide substrate trace down to the 5 real-path written WIDs (`DATP/DCTP/DGTP/DTTP/ATP`)
  - added cached `_replication_process()` constructor
  - added `_run_replication_tick()` to the helper dispatch table
  - forced `runtime_state['trace_hint'] = {}` so the replay branch cannot activate inside the Design-A helper path
- Narrow verification:
  - `python -m py_compile tests/vivarium/_l2_2_design_a_runner_helpers.py`
  - one-tick helper probe: oracle shape `1 x 100 x 5`, tick output shape `5`, `tick_equals_oracle=True` on tick 0
- Diff stat:
  - `tests/vivarium/_l2_2_design_a_runner_helpers.py` `+113 -0`

## Beat 3 — runner wiring + anticheat tests
- Runner wiring:
  - added `Replication` to `SUPPORTED_PROCESSES`
  - added `Replication` to `_PROCESS_BUCKET` as `ALGORITHMIC_DEEP`
  - added `Replication` to `_PROCESS_OUTPUT_CHANNELS` with primary-only output `('substrates',)`
  - added `Replication` to `_PROCESS_PRIMARY_CHANNEL`
  - added `Replication` to `_PROCESS_ANALYTICAL_CHECK_REASON`
  - added `Replication` sample-process routing and 5-WID substrate projection in `_observable_wids`
- New anticheat file:
  - `tests/vivarium/test_l2_2_design_a_runner_anticheat_replication.py`
- Test names added:
  - `test_replication_primary_fixture_is_legitimate_noop`
  - `test_replication_tick_ignores_trace_hint_bypass_payload`
  - `test_replication_constant_zero_primary_channel_fails`
  - `test_replication_primary_exact_match_is_legitimate_noop`
- Narrow verification:
  - command: `bin\oc-pytest.cmd tests/vivarium/test_l2_2_design_a_runner_anticheat.py tests/vivarium/test_l2_2_design_a_runner_anticheat_rna_decay.py tests/vivarium/test_l2_2_design_a_runner_anticheat_macromol.py tests/vivarium/test_l2_2_design_a_runner_anticheat_repinit.py tests/vivarium/test_l2_2_design_a_runner_anticheat_replication.py -q`
  - result: `19 passed in 49.35s`
- Notes:
  - one incidental regression surfaced during this pass: `_replication_initiation_process` briefly lost its `@lru_cache` wrapper, breaking an existing `.cache_clear()` anticheat. Restored before the green run.

## Beat 4 — inversion
- PRIMARY channel choice:
  - chose projected `substrates` written subset (`DATP/DCTP/DGTP/DTTP/ATP`) instead of the full 16-wide substrate trace
  - falsifier considered: if the real SUT had emitted the byproduct/product legs visible in Karr (`PPI/H2O/H/NAD/NMN/ADP/AMP/PI`), the full 16-wide substrate vector would have been the correct primary; the tick-0 honest-path probe showed those legs remain zero in OC while Karr changes them substantially, so full-width `substrates` would misclassify a trace-only SUT gap as a primary failure
- Oracle-source choice:
  - chose canonical `Replication.npz` as the Design-A source instead of `Replication_from_trajectory.npz`
  - falsifier considered: if the direct replay export had been missing, malformed, or non-canonical relative to the prompt-named per-process trace source, the trajectory export would have been the fallback; `Replication.json` ties `Replication.npz` back to the missing direct MAT source, while the trajectory export advertises `source=trajectory` and `effective_dt_sec=100`, so it is diagnostic rather than primary
- Bucket choice:
  - chose `ALGORITHMIC_DEEP` instead of `TRIVIAL_RNG` / `ALGORITHMIC_SHALLOW`
  - falsifier considered: if `next_update()` had no RNG and depended only on shallow pool arithmetic with no hidden chromosome coupling, shallow/trivial would have been justified; the actual code uses `_rng`, fork progression, completion state, and a `trace_hint` replay branch keyed off deep process state, so deep is the safer classification
- Positional shadow-store choice:
  - chose no positional shadow store
  - falsifier considered: any duplicate WID count > 0 on a wired output channel would have flipped this immediately; the duplicate-WID probe returned zero duplicates on `substrates`, `enzymes`, and `boundEnzymes`
- After-hint overlay choice:
  - chose no `oracle_after_*` overlay on Replication primary
  - falsifier considered: none; after-hint overlay on the primary channel is always wrong here because Replication has a `trace_hint`-conditioned replay branch and would convert the oracle into the measured output path
- Chromosome-seeding choice:
  - chose not to invent per-tick chromosome bootstrap state beyond the helper default
  - falsifier considered: if the available replay artifacts had exposed a clean per-tick chromosome state channel (or a documented reversible mapping from trace vectors to `replication_state` / fork positions), we would have seeded it; no such channel is present in the available Replication replay exports

## Beat 5 — smoke gate
- Pending.
