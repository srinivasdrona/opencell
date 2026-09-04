# STATUS — One-pass Cytokinesis + FtsZ division-window dual-tap extractor

Branch: `agent/dual-division-extractor-20260903`, worktree
`E:\opencell-worktrees\fasttrack-division-dual`, based on main `6ae2e88`.

## 1. Authoritative sources read (per COMPOSITION_MANDATE_v2 spec-authority rule)

Read before design, in this order: `SESSION_CONTEXT.md`,
`.github/copilot-instructions.md`, `docs/prompts/COMPOSITION_MANDATE_v2.md`,
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`, then the primary MATLAB
sources named in the task.

**Catalog entry (authoritative spec) — FtsZPolymerization**
(`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:341-357`):

```yaml
- name: FtsZPolymerization
  oc_module: opencell/vivarium/karr_ftsz_polymerization.py
  bucket: EVENT_CLASS
  harness_type: event_class
  in_scope_L2_2: true
  M_ticks: 200
  N_seeds: 50
  event_density: sparse                 # only active in pre-division window
  input_channels: [substrates, enzymes, monomers]
  output_channels: [substrates, monomers]
  primary_channel: monomers
  karr_artifact: per_process_traces_v2
  rationale_M: "sparse; need seeds that overlap pre-division window"
  seed_window:
    tick_range_from_division: [-200, 0]
    rationale: "FtsZ polymerization is biologically active only in the pre-division window"
```

**Catalog entry (authoritative spec) — Cytokinesis**
(`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:359-383`):

```yaml
- name: Cytokinesis
  oc_module: opencell/vivarium/karr_cytokinesis.py
  bucket: EVENT_CLASS
  harness_type: event_class
  in_scope_L2_2: true
  M_ticks: 4000
  N_seeds: 50
  event_density: sparse                 # only active during division
  input_channels: [substrates, enzymes, chromosome]
  output_channels: [substrates, chromosome]
  event_channels: [chromosome]
  primary_channel: substrates
  karr_artifact: per_process_traces_v2
  rationale_M: "2026-08-05 (Canary D closeout): the old M_ticks=100 'default' failed closed
    -- seed 0's real onset-to-completion span is 3871 ticks (onset_tick=27556,
    completion_tick=31427), not ~50-100. 4000 is the smallest validated seed-0
    LOWER BOUND ..."
  event_sweep_blocked_on: "N=50 sweep unauthorized until scripts/l2_event/survey_cytokinesis_onset_span.py
    reports a FULL (50/50 seed) survey ..."
  seed_window:
    tick_range_from_division: [-3999, 0]
    rationale: "Cytokinesis is biologically active only in late cell cycle around division. ..."
```

## 2. Primary-source investigation (why the duplication exists)

- `scripts/matlab/extract_per_process_traces_v2.m` (unmodified): its
  per-process loop (`for i = 1:numel(process_names) ... [sim, ...] =
  karr_bootstrap(); ...`) re-bootstraps and re-seeds a **fresh** `Simulation`
  for **every requested process name**, even within one call. Requesting
  `{'Cytokinesis','FtsZPolymerization'}` in one invocation still runs **two**
  full ~31k-tick trajectories, not one. `capture_anchor_window` (same file)
  free-runs the whole 28-process scheduler tick-by-tick with a rolling
  circular buffer of size `n_ticks`, stopping at the first observed
  `CellGeometry.pinchedDiameter` positive→zero completion — this is the
  mechanism this task's new extractor reuses (generalized to two taps).
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m:262,300`:
  **every** process (including FtsZPolymerization) gets `this.geometry =
  simulation.state('Geometry')` — a shared handle, so `pinchedDiameter` is
  readable from any process. But `ftsZRing` (`Cytokinesis.m:103`) and
  `chromosome` are **not** declared on the base `Process` class and are
  **absent** from `FtsZPolymerization.m` (confirmed by grep — zero matches
  for `ftsZRing`/`chromosome`/`segregated` in that file). This is exactly
  why anchoring directly on FtsZPolymerization's own tap (as
  `extract_ftsz_pre_division_window_seeds.m`'s **original** docstring
  assumed, commit `dff5c4f`) is structurally wrong.
- The **live** `genuine-l22-ftsz` worktree already discovered and fixed this
  (commit `4b0eac6`, "Fix FtsZ pre-division completion discovery"): its
  current `extract_ftsz_pre_division_window_seeds.m` runs
  `discover_division_completion_tick` — a **first full free-running
  simulation** (`sim.evolveState()` in a loop, no per-process tap at all,
  just watching `sim.state('Geometry').pinchedDiameter`) to find the real
  completion tick, **then** calls `extract_per_process_traces_v2(...,
  'fixed')` a **second time** (fresh `karr_bootstrap()`, fresh seed) with
  `tick_offset = completion − 200` to burn in and capture the final 200
  ticks, then rewrites that file's metadata from `tick_end`-form to
  `window_anchor`-form (`rebind_fixed_window_to_division_anchor`). Verified
  empirically against a real completed seed-3 log
  (`genuine-l22-ftsz\tmp\l22_ftsz_genuine_extract\l22-ftsz-genuine-r2-s003-a1.stdout.log`):
  `tick_start=30978, window_anchor=31177` — i.e. **two** full trajectories
  per seed, exactly the ~6h50m cost the task describes. This confirms the
  duplication is real, current, and structural (not a hypothetical).

## 3. Design

New, standalone, one-pass dual-tap extractor + driver
(`scripts/matlab/extract_dual_division_window.m` +
`extract_dual_division_window_seeds.m`):

- **One** `karr_bootstrap()` call, **one** `seed_simulation(sim, seed)` call,
  **one** per-tick scheduler loop (`evolve_state_with_dual_tap`) — a direct
  generalization of `evolve_state_with_tap` from one `target_idx` to two
  (`idx_a`=Cytokinesis, `idx_b`=FtsZPolymerization), preserving the exact
  `copyFromState → calcResourceRequirements_Current (all 28 processes) →
  proportional allocation → Karr's randperm-with-tRNAAminoacylation-before-
  Translation order → per-process copyFromState → evolveState → copyToState
  → metabolite pool reconciliation` sequence, byte-for-byte identical to the
  existing single-process loop.
- Two independently-sized rolling circular buffers:
  Cytokinesis = 4000 ticks (catalog `M_ticks`), FtsZPolymerization = 200
  ticks (catalog `M_ticks`) — bounded memory regardless of how long the
  search runs (`capture_dual_anchor_windows`).
- Division completion/onset are detected **solely** from process A's
  (Cytokinesis's) tap via `merge_event_observables`
  (`pinchedDiameter`/`ftsZRing_*`/`chromosome_segregated`, duplicated
  verbatim from `extract_per_process_traces_v2.m`) — **never** derived from
  or read off of process B's (FtsZPolymerization's) tap, which has no such
  witnesses of its own. Both windows end at the **same** absolute
  `completion_tick`.
- **Atomic fail-closed write**: both `.mat` files are written to sibling
  `.tmp-<pid>_<timestamp>-...` paths, each independently re-`load()`ed and
  checked (`verify_temp_output`: process_name/n_ticks/rng_seed/window-kind/
  full row-count for every snapshot property) **before** either `movefile`.
  A capture failure never reaches the metadata-building code at all (static
  proof: the `~ok` guard raises before the first `cyt_metadata = struct(...)`
  line). A **lone** existing output for a seed is refused outright
  (`extract_dual_division_window:partial_output_exists`), never silently
  reused or overwritten.
- Genuine-provider metadata (`mnrnd_provider_*` ×5 +
  `statistics_rng_provider_identity_json`) is written to **both** files from
  the **same** single `karr_bootstrap()` return value — provable-identical
  provenance, checked by the Python validator below.
- Both outputs land at the **exact existing paths** the live validators
  already look for:
  `data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/
  {Cytokinesis_4000ticks.mat, FtsZPolymerization_200ticks.mat}`.
- **Existing single-process scripts are untouched.**
  `extract_per_process_traces_v2.m` and
  `extract_ftsz_pre_division_window_seeds.m` remain valid, unmodified
  fallback paths (statically proven: a test diffs their on-disk content
  against `git show HEAD:<path>`).

## 4. Validation reuse (no new validation logic written)

`scripts/l2_event/validate_dual_division_canary.py` calls, unmodified:

- **Cytokinesis**: `scripts.l2_event.launcher.validate_existing_event_window`
  against an `AnchorWindowSpec(process="Cytokinesis", n_ticks=4000,
  required_observables=survey_cytokinesis_onset_span.REQUIRED_OBSERVABLES,
  scalar_finite_observables=launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES)`
  — the exact spec `prepare_cytokinesis_cohort.py`'s `_anchor_spec` builds.
  This checks: process_name/rng_seed/n_ticks match; on-disk window kind is
  `anchor` (no `tick_end`); `signal_kind`/`signal_property`/`signal_field`/
  `max_search_ticks`/`event_observable_projection_version` match; genuine
  mnrnd/Statistics-RNG provider identity (kind, MATLAB release, toolbox
  version, path, SHA-256, full JSON identity) matches the **current local**
  MathWorks install; `onset_tick` present for `diameter_decrease`.
- **FtsZPolymerization**:
  `scripts.l2_event.ftsz_pre_division_evidence.validate_seed_window` — loads
  via the shared `window_loader.load_event_window` (stride-1/M4 contract),
  checks `process_name`, `rng_seed` == directory-seed, `n_ticks == 200`,
  `window_anchor`/`tick_start` present, and the exact span
  `window_anchor − tick_start + 1 == 200`.
- **New, dual-tap-specific cross-checks** (neither single-process validator
  has any reason to check these on its own): distinct paths, distinct
  byte content, **same `window_anchor`** between the two files (the task's
  explicit "same real geometry pinchedDiameter completion tick"
  requirement), and matching `mnrnd_provider_sha256` between the two files
  (proves both taps came from the same `karr_bootstrap()` call).
- Fail-closed: `validate_dual_division_canary` only returns `"PASS"` if
  **every** check above holds; any single failure — including a **missing**
  file — is reported as `"FAIL"` with the exact reason(s), never partially
  promoted.

## 5. Tests (all green)

- `tests/scripts/test_extract_dual_division_window_static.py` (23 tests):
  file existence/parse sanity, block-keyword balance, **existing
  single-process scripts unchanged** (diffs against `git show HEAD:`, with
  a WSL-gitdir-translation fallback mirroring
  `scripts/l2_event/evidence.py::_translate_windows_gitdir`), exactly one
  `karr_bootstrap()`/`seed_simulation()` call, never calls
  `extract_per_process_traces_v2`, both taps captured in one scheduler loop
  (`if proc_idx == idx_a ... elseif proc_idx == idx_b`), completion/onset
  detection reads **only** process A's tap, hardcoded catalog window
  lengths (4000/200), both windows share `completion_tick`, span
  self-checks present, provider metadata written from the same provider
  variable for both outputs, atomic-write ordering (`verify_temp_output`
  before **either** `movefile`, both `movefile`s in order), no metadata
  built before the `~ok` guard, driver skip/force/aggregate-failure
  behavior, plus a real Octave parse-only probe (Octave is installed and
  both extractor files parsed successfully).
- `tests/scripts/test_validate_dual_division_canary.py` (7 tests): PASS on a
  matched synthetic pair; FAIL (never partial-PASS) on a missing FtsZ file;
  FAIL on mismatched `window_anchor`; FAIL on mismatched
  `mnrnd_provider_sha256` even though each file individually still passes
  its own single-process validator; FAIL on byte-identical outputs;
  `main()` CLI exit-code parity with `status`.
- **Result**: 30/30 new tests pass. Re-verified 152 related existing tests
  green (`test_l2_event_launcher.py`, `test_l2_event_window_loader.py`,
  `test_prepare_cytokinesis_cohort.py`,
  `test_extract_per_process_traces_v2_static.py`, both new files) — 4
  skipped because optional real MAT fixtures were absent locally; the
  Octave probes ran. `ruff check` clean on all new Python files.

## 6. Canary state (seed 49)

**PASS.** The corrected canary ran from 2026-09-04 12:15:30 to 13:54:39
(99.15 minutes) on an otherwise idle host. One seeded trajectory produced:

- Cytokinesis: `tick_start=26238`, `window_anchor=30237`,
  `onset_tick=26348`, SHA-256
  `39b0ee3a551dc772eb9e690d61b62fd41fa39ad39418cb9f864efd45a3bf5f68`.
- FtsZPolymerization: `tick_start=30038`, `window_anchor=30237`, SHA-256
  `7a254129a27979dbe13b65a04d3e9e28426a8e148e6e203d559b556888232c70`.

Both existing process validators passed, the outputs are distinct, and both
carry the same genuine provider SHA-256
`d68e8ff78af266ad4977e80cd5366cc59984ada5f73ab591a9c08350bc4471dc`.
The machine-readable result is committed at
`tmp/dual_division_canary_seed49/CANARY_RESULT.json`.

Root cause of the discrepancy: `scripts\tools\run_matlab_slot.ps1`'s slot
lock pool is **scoped per-`-Worktree` argument**, and every live queue
(`genuine-l22-cytokinesis`, `genuine-l22-ftsz`, the five L2.1
active-window lanes) invokes it with **its own** worktree path — there is
no single shared lock directory across worktrees despite `plan.md`'s
narrative describing "the common four-slot pool." Each lane's own 4-slot
cap is real and locally enforced, but the **aggregate** across
independently-locked lanes is not bounded by any single mechanism. This
worktree's own `artifacts\matlab_slots\` pool is empty/unused, so calling
`run_matlab_slot.ps1 -Worktree <this worktree> -Slots 4` directly would
have been granted immediately and become a **9th** concurrent real MATLAB
session on an already-100%-CPU host — unacceptable per the task's explicit
"two recent FtsZ engine deaths make blind oversubscription unacceptable"
guidance, and the "do not disturb the live queues" requirement.

The initial waiter correctly held while the host was oversubscribed. Its
first post-restart launch exposed a relative-`addpath` defect because
MATLAB's `run()` changes directory to the scratch script; commit `725dc14`
uses the absolute worktree MATLAB path. The second launch completed and
validated successfully.

- Script: `tmp/dual_division_canary_seed49/wait_and_run_seed49.ps1`
  (committed). Adds an outer host-wide gate
  (`Get-Process matlab,MATLAB` count, ceiling-divided into sessions) in
  front of the existing `scripts\tools\run_matlab_slot.ps1 -Slots 4` call;
  proceeds only when host-wide sessions drop below 3, polling every 300s,
  giving up after 72h. Dry-run verified (`-MaxWaitHours 0`): correctly
  detected 8 sessions ≥ threshold and refused to proceed, exit 1, before
  being launched for real.
- Log: `tmp/dual_division_canary_seed49/wait_and_run_seed49.log`
- Status marker (single line, machine-readable):
  `tmp/dual_division_canary_seed49/STATUS.txt`
- The successful run invoked
  `extract_dual_division_window_seeds(49, 49)` via
  `scripts\tools\run_matlab_slot.ps1 -Slots 4 -Tag
  dual_division_canary_seed49`, then automatically run
  `python scripts/l2_event/validate_dual_division_canary.py --seed 49` via
  the WSL venv and write its JSON verdict to
  `tmp/dual_division_canary_seed49/CANARY_RESULT.json`.
- This waiter never touches, stops, or races the live Cytokinesis (PID
  `18600`) or FtsZ (PID `22568` / watchdog `7904`) processes or worktrees.
  It only reads the host-wide process list and, once clear, runs a fresh
  seed-49 extraction into **this worktree's own**
  `data/m1_sources/karr_native/` (gitignored, not shared with any other
  worktree's copy).

**Exact output paths** (seed 49):

- `data/m1_sources/karr_native/per_process_traces_v2_event_s049/Cytokinesis_4000ticks.mat`
- `data/m1_sources/karr_native/per_process_traces_v2_event_s049/FtsZPolymerization_200ticks.mat`
- `tmp/dual_division_canary_seed49/CANARY_RESULT.json` (combined verdict)

After independent review, seed 49 was copied byte-for-byte into both live
worktrees and revalidated there. Destination counts are now Cytokinesis
35/50 and FtsZ 11/50 valid/present.

## 7. Runtime comparison

| Path | Trajectories run | Approx. wall-clock/seed |
|---|---|---|
| Existing Cytokinesis queue (`extract_per_process_traces_v2.m`, anchor mode) | 1 full ~31k-tick trajectory | ~105 min in recent contended runs |
| Existing FtsZ queue (`extract_ftsz_pre_division_window_seeds.m`, current 2-pass) | 2 full ~31k-tick trajectories (discovery + burn-in/capture) | ~240-280 min |
| **This dual-tap extractor (seed 49, idle host)** | **1** full trajectory | **99.15 min** |

The measured canary confirms the second tap adds no material per-tick cost.
The speedup is principally the removal of FtsZ's duplicated discovery and
burn-in trajectory.

## 8. 6-slot throughput canary — evaluated, NOT activated

Per task instruction, this is an evaluation only; no slot increase is
requested or performed.

**Real 4-slot (stated policy) baseline is not currently available** — the
host is presently running 8 real sessions (§6), not 4, so no clean
per-session CPU/memory measurement at the *intended* baseline exists yet.
Measured at 8 real concurrent sessions (2026-09-03 ~08:15 IST):

- Memory: ~1.3 GB working set per real `MATLAB` engine process (the paired
  `matlab` launcher process uses ~0.01 GB, negligible) → ~10.4 GB total for
  8 sessions, on a 63.8 GB host with 27 GB still free. Memory is **not**
  the binding constraint even at 8 concurrent sessions, let alone 6.
- CPU: **100% load** (`Win32_Processor.LoadPercentage`) on 16 logical
  processors (8 physical cores) at 8 concurrent sessions. This is the
  binding constraint, and it is already saturated **below** a hypothetical
  6-slot target — the host is currently running 2x the stated 4-slot
  policy already.

**Implication**: raising to 6 slots without first (a) actually reconciling
the aggregate host-wide session count back down to the intended 4 (§6 root
cause — the per-worktree lock-pool scoping bug means "4 slots" is not
currently enforced in aggregate) and (b) measuring real per-seed wall-clock
throughput at that true 4-session baseline, would be adding oversubscription
on top of oversubscription. Given "two recent FtsZ engine deaths" per the
task's own caution, and CPU already reading 100% at the *current*
(unintentionally 8-wide) concurrency, this evaluation's conclusion is: **do
not raise slots on this evidence**. A defensible one-wave 6-slot benchmark,
if the coordinator authorizes it after independent review, should be
specified as:

1. **Precondition**: first bring the host-wide real MATLAB session count
   back down to exactly 4 (drain or fix the per-worktree lock-pool scoping
   so "Slots 4" is enforced in aggregate, not per-worktree), and record a
   clean baseline: seeds/hour at N=4 across a fixed, representative job mix
   (e.g. 2 Cytokinesis + 1 FtsZ + 1 active-window seed, matching the current
   real lane composition) for at least one full wave (all 4 slots occupied
   start-to-finish).
2. **One-wave 6-slot trial**: launch exactly 6 jobs (same representative
   mix, scaled by 1.5x, e.g. 3 Cytokinesis + 2 FtsZ + 1 active-window),
   let all 6 run to completion with no new launches until the wave
   finishes, and record: wall-clock of the slowest job in the wave, total
   validated seeds produced by the wave, peak CPU load, and peak/steady
   memory.
3. **Decision metric**: `validated_seeds_per_hour = (validated seeds
   produced by the wave) / (wave wall-clock in hours)`, compared directly
   against the N=4 baseline's own `validated_seeds_per_hour` from step 1 —
   **not** a raw process-count comparison. Only raise the standing policy
   to 6 if the 6-slot wave's validated-seeds/hour is measurably higher
   (not just "more processes running") than the 4-slot baseline's; if CPU
   contention makes per-seed wall-clock increase by more than the
   slot-count ratio (i.e., 6-slot throughput ≤ 4-slot throughput), reject
   the increase.
4. Given the CPU-saturation evidence in this section, the a priori
   expectation is that 6 slots on this 16-logical-processor host will
   **not** beat 4-slot throughput once the aggregate is honestly measured
   at 4 first — this benchmark should be run to confirm or refute that
   expectation with real numbers, not skipped in either direction.

## 9. Safe promotion / queue-transition plan (for coordinator review — not performed here)

This task does **not** copy anything into live worktrees or stop any queue.
Once the seed-49 canary's `CANARY_RESULT.json` reports `"status": "PASS"`
from both existing validators plus all four dual-tap cross-checks, the
recommended (coordinator-executed) next steps are:

1. Independently re-run `validate_dual_division_canary.py --seed 49`
   against the file **copies** (never move/delete the originals) in a
   read-only review pass, and separately spot-check
   `compute_seed_evidence`/`audit_pre_division_evidence` (full FtsZ
   OC-vs-Karr replay) and a manual `survey_cytokinesis_onset_span`-style
   onset/completion sanity check against seed 49's own numbers.
2. If independently accepted: do **not** yet retarget the live Cytokinesis
   (PID `18600`) or FtsZ (PID `22568`/`7904`) queues. Instead, run the dual
   extractor for a **second, independent** seed (e.g. the next seed both
   cohorts are missing) as a **replication** check before trusting a single
   seed's PASS as representative.
3. Only after ≥2 independent seed PASSes: plan a controlled cutover —
   let the current Cytokinesis/FtsZ queues finish their **in-flight**
   seeds (do not kill mid-seed), then redirect the *next* queued seeds to
   `extract_dual_division_window_seeds.m` instead of launching a fresh
   single-process job for them. This halves the remaining wall-clock for
   every seed not yet started, without discarding any in-progress work.
4. Re-run the full `docs/phase_f/l2_event/` evidence/index regeneration
   (`scripts/l2_event/prepare_cytokinesis_cohort.py`,
   `scripts/l2_event/ftsz_pre_division_evidence.py`) once N=50 is reached
   via the combined path, and reconcile `event_sweep_blocked_on` in
   `PROCESS_CATALOG.yaml` (Cytokinesis row) only after the full 50-seed
   survey — never from a partial sample (existing hard rule, unchanged).

## 10. Exact next actions

1. Run the dual extractor for seed 36 in a clean output worktree and
   bit-compare the Cytokinesis state arrays against the existing
   single-process seed-36 trace. Do not start bulk extraction unless this
   equivalence gate is green.
2. Then run the 14 both-missing seeds
   `13,14,16,37,38,39,40,41,42,43,44,45,46,48` through disjoint dual
   workers, capped at three concurrent MATLAB sessions.
3. Fill Cytokinesis-only seed 47 and FtsZ-only seeds
   `1,2,11,12,15,17-36` through clean dual-output worktrees, copying only
   the missing destination half after byte-hash and destination-validator
   checks.
4. Do not raise concurrency to six until a clean four-session throughput
   benchmark is green and the prior clustered MATLAB engine exits are
   understood.
