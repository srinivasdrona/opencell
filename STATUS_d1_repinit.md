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

- 2026-06-07T12:03:20.5803142Z helper edit: added `_run_repinit_tick()` and ReplicationInitiation state-reconstruction helpers in `tests/vivarium/_l2_2_design_a_runner_helpers.py`.

Beat 2 implementation notes:
- Added `_replication_initiation_process()` cache factory.
- Added `_repinit_species_descriptor()` to parse DnaA species WIDs into `(mer_length, ATP_moieties)`.
- Added `_prime_repinit_state_from_trace()` to reconstruct the SUT's hidden state from before-side trace aggregates:
  - free ATP/ADP DnaA monomer pools from `oracle_before_enzymes`
  - per-site chromosome occupancy arrays from `oracle_before_bound_enzymes`
  - non-OriC sites filled first to avoid inventing an OriC trigger that the trace does not expose
- Added `_run_repinit_tick()`:
  - overlays before-side `substrates`, `enzymes`, and `boundEnzymes`
  - primes process internals and `chromosome.dnaa_complex_count`
  - gives the SUT explicit before-side ATP/H2O grants via `substrates_allocated`
  - clears `trace_hint` so `_next_update_from_trace_hint()` cannot become the measurement path
  - projects only `substrates` on the output side

Beat 2 diff stat:
```text
tests/vivarium/_l2_2_design_a_runner_helpers.py | 162 ++++++++++++++++++++++++
1 file changed, 162 insertions(+)
```

Beat 2 verification:
- `bin\oc-pytest tests/vivarium/test_l2_2_design_a_runner_anticheat.py -q`
- Result: `6 passed`

## Beat 3 - runner wiring + anticheat tests

- 2026-06-07T12:08:07.6664258Z runner wiring: added ReplicationInitiation to helper oracle dispatch, runner process tables, sample-process lookup, and a new anticheat file.

Beat 3 implementation notes:
- Helper wiring:
  - added `_REPLICATION_INITIATION_ORACLE_PATH`
  - added `_load_replication_initiation_oracle()`
  - `load_karr_oracle("ReplicationInitiation")` now sources `ReplicationInitiation_from_trajectory.npz`, not the noop `ReplicationInitiation.npz`
- Runner wiring in `tests/vivarium/l2_2_design_a_runner.py`:
  - added `ReplicationInitiation` to `SUPPORTED_PROCESSES`
  - bucketed as `ALGORITHMIC_DEEP`
  - output channels set to `("substrates",)` only
  - primary channel set to `substrates`
  - added analytical-check reason and sample-process dispatch entry
- New anticheat file: `tests/vivarium/test_l2_2_design_a_runner_anticheat_repinit.py`
  - `test_repinit_primary_fixture_is_nontrivial`
  - `test_repinit_tick_ignores_cheated_trace_hint_payload`
  - `test_repinit_constant_zero_primary_channel_fails`

Beat 3 diff stat (tracked edits before staging the new file):
```text
tests/vivarium/_l2_2_design_a_runner_helpers.py | 38 +++++++++++++++++++++++++
tests/vivarium/l2_2_design_a_runner.py          | 10 ++++++-
2 files changed, 47 insertions(+), 1 deletion(-)
```

Beat 3 verification:
- `bin\oc-pytest tests/vivarium/test_l2_2_design_a_runner_anticheat.py tests/vivarium/test_l2_2_design_a_runner_anticheat_rna_decay.py tests/vivarium/test_l2_2_design_a_runner_protein_decay_anticheat.py tests/vivarium/test_l2_2_design_a_runner_anticheat_repinit.py -q`
- Result: `16 passed`

## Beat 4 - inversion

- 2026-06-07T12:10:12.6995635Z inversion pass: recorded rejected alternatives and the evidence that would have flipped each design choice.

Falsifiers considered and rejected:
- PRIMARY channel choice:
  - Chosen: `substrates`
  - Rejected alternative: `enzymes` or `boundEnzymes` as primary
  - Falsifier that would have moved `substrates` to secondary: evidence that the real `next_update()` path writes `enzymes` or `boundEnzymes` without going through `trace_hint`. The source review found the opposite: those channels are only writable through `_next_update_from_trace_hint()`, so they cannot be an honest primary.
- Oracle selection:
  - Chosen: `ReplicationInitiation_from_trajectory.npz`
  - Rejected alternative: the plain `ReplicationInitiation.npz`
  - Falsifier that would have justified the plain oracle: at least one tick with `before_substrates != after_substrates` on the plain fixture. Probe result was `before == after` on all exposed channels for all 100 ticks, so using it would have converted ReplicationInitiation into a noop false-pass.
- Bucket choice:
  - Chosen: `ALGORITHMIC_DEEP`
  - Rejected alternatives: `TRIVIAL_RNG`, `ALGORITHMIC_SHALLOW`
  - Falsifier that would have moved bucket down: a source review showing no RNG usage and no hidden state beyond directly exposed before-vectors. Instead the SUT uses `_rng.random`, `_rng.binomial`, `_rng.choice`, plus hidden per-site arrays `_bound_atp/_bound_adp`, so shallow/trivial classification would understate the reconstruction risk.
- Duplicate-WID handling:
  - Chosen: no positional shadow store
  - Rejected alternative: RNADecay-style slot shadow store
  - Falsifier that would have flipped this: any duplicate WIDs on `substrates`, `enzymes`, `boundEnzymes`, or `all_dnaa_sites`. Probe result was zero duplicates on all inspected channels, so positional shadow storage would add complexity without protecting a real failure mode.
- Site reconstruction policy:
  - Chosen: fill non-OriC sites first when expanding aggregate `boundEnzymes` into per-site chromosome occupancy
  - Rejected alternative: allow the helper to invent OriC occupancy from aggregate counts
  - Falsifier that would have justified filling OriC first: trace-visible per-site occupancy data, or a SUT/fixture source showing that the aggregate bound counts are guaranteed to be OriC-local. Neither exists in the available replay artifacts, so populating OriC first would be an unjustified way to trigger initiation.
- After-hint overlay policy:
  - Chosen: never overlay `oracle_after_*` or incoming `trace_hint` onto the primary ReplicationInitiation path
  - Rejected alternative: use `trace_hint` to populate `enzymes_next` / `boundEnzymes_next` and let the helper project from that
  - Falsifier that would have justified an after-hint overlay on the primary: none. Any such overlay would route through `_next_update_from_trace_hint()` and launder the oracle by construction.

## Beat 5 - smoke gate

- 2026-06-07T12:12:17.451288+00:00 smoke gate run: `bin\oc-py tests/vivarium/l2_2_design_a_runner.py --process ReplicationInitiation --seeds 3 --m-ticks 5 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/ReplicationInitiation_smoke`
- 2026-06-07T12:12:17.451288+00:00 smoke gate outcome: `ReplicationInitiation FAIL substrates=FAIL@7531.520000`

Smoke-gate summary:
- Primary channel: `substrates`
- Result: `FAIL`
- `w1_oc_vs_karr`: `7531.52`
- `w1_oc_vs_karr_ci95`: `[7531.52, 7531.52]`
- `q95_null`: `0.0`
- Threshold: `1.0`
- Artifact dir: `tests/vivarium/artifacts/l2_2_design_a/ReplicationInitiation_smoke/`

Follow-up probes after primary fail:
- Duplicate-WID probe on primary:
  - reused Beat 1 result
  - `substrates`: 5 total WIDs, 5 unique, 0 duplicates
  - Conclusion: not an i3 duplicate-WID collapse
- `oc_equals_before` probe on the 5 smoke ticks:
  - ticks `0..4`: `oc_equals_before == True`
  - ticks `0..4`: `oc_equals_after == False`
  - per-tick `w1(oc, after)` exactly matched `w1(before, after)`
  - Conclusion: the current RepInitiation primary path is a pure pass-through on `substrates`
- Write-surface probe on the 5 smoke ticks:
  - every tick returned update keys `["chromosome", "protein", "requests"]`
  - every tick had `writes_substrates == False`
  - Conclusion: under the best available before-side reconstruction from the exposed oracle channels, the real SUT path never emits a `substrates` delta on the smoke window
- Anti-laundering sanity:
  - the RepInit anticheat `test_repinit_tick_ignores_cheated_trace_hint_payload` is green
  - Conclusion: this is not a primary-channel after-hint overlay bug

Interpretation:
- This is not a duplicate-WID issue and not an oracle-laundering false pass.
- The only trace-visible primary candidate that the real SUT path can honestly gate on is `substrates`, but the available replay surface (`substrates`, `enzymes`, `boundEnzymes`) does not expose enough chromosome/protein state to drive a non-pass-through `substrates` update.
- The other trace-visible channels (`enzymes`, `boundEnzymes`) are only writable through `_next_update_from_trace_hint()`, so promoting them to primary would launder the oracle.
- Therefore this task reaches the prompt's "no viable primary" branch with the current SUT/trace contract.

Handoff / next-step recommendation:
- Commission a v2 ReplicationInitiation replay surface or SUT interface that exposes a real primary channel:
  - either add trace-visible `chromosome.dnaa_complex_count` / free DnaA pool state needed to drive the biological path
  - or teach the replay oracle to expose the exact before-side chromosome occupancy required for RepInitiation without using any `after_*` hint
- Until then, ReplicationInitiation can be wired in the harness, but it cannot honestly PASS a Design-A primary gate.

verdict: BLOCKED_NO_VIABLE_PRIMARY
