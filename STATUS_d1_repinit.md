# STATUS_d1_repinit

- 2026-06-07T11:59:43.7407169Z session start: read SESSION_CONTEXT.md and required prompt slots; beginning Beat 1 SUT/trace inspection for ReplicationInitiation.
- 2026-06-07T11:59:43.7407169Z probe note: prompt-referenced `data/m1_sources/karr_native/per_process_traces/ReplicationInitiation_100ticks.mat` is absent in this worktree; `data/karr_fixtures/per_process_replay/ReplicationInitiation.json` still points at it, so Beat 1 used the available replay artifacts plus `ReplicationInitiation_from_trajectory.npz` for non-noop channel inspection.

## Beat 1 - SUT inspection + wiring design

Beat 1 contract:
- Required behavior: add ReplicationInitiation to the L2.2 Design-A runner without laundering the oracle through `trace_hint`, following the existing helper/runner/anticheat pattern.
- Done means the harness evaluates a real SUT-driven ReplicationInitiation primary channel, or honestly reports that no such primary is reconstructible from the available trace surface.

Beat 1 observations:
- `KarrReplicationInitiationProcess.next_update()` real-path writes: `chromosome.dnaa_complex_count`, `chromosome.replication_state` (conditional), `protein.counts`, `substrates` (conditional), and `requests.karr_replication_initiation`.
- `KarrReplicationInitiationProcess.next_update()` real-path reads: `chromosome.dnaa_complex_count`, `chromosome.replication_state`, `chromosome.supercoiled`, `protein.counts`, and `substrates_allocated.karr_replication_initiation.{ATP,H2O}`.
- Oracle-bypass hazard present: `next_update()` has an early `trace_hint` branch and `_next_update_from_trace_hint()` method; if `trace_hint` includes `enzymes_next` or `boundEnzymes_next`, the SUT returns from the hint path instead of the biological path.
- Available replay fixtures in this worktree:
  - `ReplicationInitiation.npz`: noop on every exposed channel (`before == after` for all 100 ticks).
  - `ReplicationInitiation_from_trajectory.npz`: nontrivial on `substrates`, `enzymes`, and `boundEnzymes` and therefore the only viable Design-A oracle candidate here.
- Trace-visible channels from the available replay artifacts: `substrates`, `enzymes`, `boundEnzymes`.
- Duplicate-WID probe result: none found on `substrates`, `enzymes`, or the SUT's `all_dnaa_sites`; positional shadow-store handling is not needed.

Write-surface / trace crosswalk:

| channel | written_by_SUT? | in_trace? | n_wids_total | n_wids_unique | classification |
| --- | --- | --- | ---: | ---: | --- |
| `substrates` | yes, conditional | yes | 5 | 5 | PRIMARY candidate; only overlapping real write surface |
| `enzymes` | no on real path; yes only via `trace_hint` replay branch | yes | 15 | 15 | `expected_sut_gap`; never make primary |
| `boundEnzymes` | no on real path; yes only via `trace_hint` replay branch | yes | 15 | 15 | `expected_sut_gap`; never make primary |
| `chromosome.dnaa_complex_count` | yes | no | 2283 | 2283 | real SUT state, but not trace-visible in available replay artifacts |
| `protein.counts` | yes | no | 1 direct schema key (`MG_469_MONOMER`), but helper can inject ATP/ADP pool keys | 1 | real SUT state, but not trace-visible in available replay artifacts |

Decision:
- PRIMARY channel: `substrates`
- SECONDARY channels: none for runner gating; `enzymes` and `boundEnzymes` stay diagnostic-only because the real SUT path does not write them.
- SUT_BIOLOGY_GAP / harness-gap notes:
  - `enzymes` and `boundEnzymes` are trace-visible but only writable via the SUT's hint-replay branch, so projecting them as measured outputs would launder the oracle.
  - The available trace surface does not expose the per-site chromosome occupancy that the SUT needs for faithful ReplicationInitiation dynamics.
  - The plain `ReplicationInitiation.npz` oracle is a noop trap and would falsely trigger the legitimate-determinism warning without exercising the process.

Bucket choice:
- `ALGORITHMIC_DEEP`
- Rationale: ReplicationInitiation is stochastic (`_rng.random`, `_rng.binomial`, `_rng.choice`) and depends on deep hidden state (`_bound_atp`, `_bound_adp`, OriC site occupancy, and allocator grants) that is not fully reconstructible from the exposed aggregate replay channels.

## Beat 2 - tick dispatcher

## Beat 3 - runner wiring + anticheat tests

## Beat 4 - inversion

## Beat 5 - smoke gate
