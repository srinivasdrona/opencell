# Division-window cohort-censoring contract — migration/backfill plan

Preregistered 2026-09-08, revised 2026-09-09 (Opus implementation
re-review, then a second Opus re-review, then this final backfill/
accounting round), branch `fix/division-censor-contract`, base `701b991`
(`docs: preregister division censoring direction`). Not merged/pushed.

See `docs/phase_f/l2_event/division_window_spec.json`'s `selection_contract`
for the machine-loadable contract (including the formal estimand,
non-adaptive stopping rule, and monotone-minimum `max_search_ticks`
validation policy this document assumes) and
`scripts/l2_event/division_cohort_selector.py` for the enforcing
implementation (`audit_cohort()` / CLI).

## Get the live, mechanically-verified state yourself — never trust a number in this doc as frozen truth

This document intentionally does **not** hardcode a "the cohort currently
has N selectable seeds" claim as settled fact, per the 2026-09-09 Opus
re-review ("update backfill tooling to discover actual files rather than
hardcode reviewer-era counts"). The counts below are what a **fast
filesystem-existence survey** (`Get-ChildItem`, no HDF5 content
validation) found in this session, presented as a snapshot with an exact
timestamp — not a claim about what the code will report weeks from now.
**Always re-run the real tool** for a current, integrity-checked answer:

```bash
python scripts/l2_event/division_cohort_selector.py \
  --search-root /mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native/dual_division_cohort_current
```

This performs full HDF5 validation (hashing every trace, cross-checking
source/provider identity, checking the contiguous-attempt/censor-horizon/
identity-binding rules) against the **authoritative operational root**
(`dual_division_cohort_current` — see `authoritative_karr_native_root()`
and the spec's `authoritative_operational_root` field). Second Opus
re-review (2026-09-09): by default this NEVER also scans every sibling
worker worktree (`default_search_roots()` returns the authoritative root
ONLY, or an empty list if it cannot be found anywhere, in which case the
CLI fails closed with an actionable message asking for an explicit
`--search-root` rather than silently broadening the scan). A caller that
explicitly wants the broader scan may pass multiple `--search-root`
arguments, or call `division_cohort_selector.broad_search_roots()`
directly. When multiple roots ARE searched (whether via explicit
`--search-root` or `broad_search_roots()`), every root is inspected for
every seed and any two roots' VALID records that disagree hard-fail
(`CohortContractError`) — a non-authoritative root's INVALID/superseded
trace (no explanatory attempt record, or any other resolution failure) is
instead caught and reported in the audit's `rejected_root_traces` list,
never fatal; the same failure in the authoritative root itself remains
fatal.

Operational note (this session): running this command with search roots
that reach across the WSL↔NTFS filesystem boundary (`/mnt/e/...` against
an `E:` drive) was observed to take longer than a reasonable interactive
wait in this environment, likely DrvFS overhead on ~27 MB-per-seed HDF5
reads. Run it from **native WSL against a native-filesystem copy**, or
budget for a multi-minute wait, before treating a long-running invocation
as a bug. A real, unmodified no-arg invocation (`python scripts/l2_event/
division_cohort_selector.py`, no flags) was run against this exact
machine layout this session (see "Real no-arg CLI proof" below) and
completed cleanly with a real report and exit code 2 — no traceback.

## Fast filesystem-existence snapshot (this session, 2026-09-09 ~07:xx IST, final Opus review round)

Directory listing (`Get-ChildItem`, no content read) of the authoritative
root
(`main-integrate/data/m1_sources/karr_native/dual_division_cohort_current`):
**25 seed directories** total — worker C finished seeds 34-49 (up from
34-47 last round) since the previous snapshot, and seed 6's live
100000-tick diagnostic finished (FAILED — genuine right-censoring, not a
crash) since then too.

| Seeds | Contents |
|---|---|
| 0, 1, 2, 3, 4, 5, 17, 34-49 | `Cytokinesis_5000ticks.mat` + `FtsZPolymerization_200ticks.mat` — **23 COMPLETED pairs** |
| 6, 18 | `division_window_attempt.json` only — **2 RIGHT_CENSORED** (seed 18 backfilled two rounds ago; seed 6 backfilled THIS session, see below) |

Breaking the 23 COMPLETED pairs down by contiguity role: seeds 0-5 (6
seeds) are the CONTIGUOUS prefix (currently selectable, alongside seed 6's
now-resolved censor); seeds 17, 34-49 (17 seeds) are PREMATURE completions
(real evidence, preserved, not yet selectable because seeds 7-16/19-33 are
still unattempted gaps). Seed 18 is a separate, PREMATURE **censored**
observation (also blocked by the same gap).

### Real no-arg CLI proof (this session, native WSL Python against the real E: drive data via `bin/oc-py`)

```
$ python scripts/l2_event/division_cohort_selector.py
{
  "attempted_count": 7, "completed_count": 6, "completion_fraction": 0.857...,
  "contiguous_prefix_end": 6, "next_seed_to_attempt": 7,
  "completed_seeds": [0, 1, 2, 3, 4, 5],
  "censored_seeds": [6], "invalid_censor_seeds": [],
  "gap_seeds": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23,
                24, 25, 26, 27, 28, 29, 30, 31, 32, 33],
  "premature_seeds": [17, 18, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
                       45, 46, 47, 48, 49],
  "rejected_root_traces": [],
  "selected_seeds": [0, 1, 2, 3, 4, 5], "selection_satisfied": false,
  "source_hash_mismatches": [], "duplicate_trace_hashes": []
}
next_seed_to_attempt=7 completed=6 required=50 selection_satisfied=False
gap_seeds=[7..16, 19..33] premature_seeds=[17, 18, 34..49] rejected_root_traces=0
$ echo $?
2
```

No traceback, a real report, exit code 2 (matches `main()`'s documented
`0 if selection_satisfied else 2` convention). This run independently
re-validated every one of the 23 real COMPLETED pairs via
`validate_dual_division_canary` (that is why the invocation takes several
minutes — full HDF5 hash + margin-gate + horizon re-check per pair, not a
directory listing) — zero `CohortContractError`s, zero
`rejected_root_traces`, zero `invalid_censor_seeds`. `premature_seeds`
includes seed 18 (censored) alongside 17/34-49 (completed) because that
field does not itself distinguish status within the premature bucket —
see `censored_seeds`/`completed_seeds` (both scoped to the contiguous
prefix only) for the status breakdown.

Mechanically, per `division_cohort_selector`'s contiguity rule: the
contiguous prefix from `candidate_seed_start=0` now extends through seed 6
(a valid, horizon/identity-verified `RIGHT_CENSORED` record — contiguity
does not require `COMPLETED`, only *some* valid attempt record), so
`next_seed_to_attempt=7`. Only seeds 0-5 (6 completions) count toward
`required_completed_windows=50` today; seed 6's censor contributes zero
completions but does extend the contiguous "attempted" prefix past it.
Seeds 17, 34-49 (17 seeds) are genuine `COMPLETED` evidence, preserved and
never invalidated, but remain "premature" until seeds 7-16 and 19-33 are
attempted in ascending order. Seed 18 is `RIGHT_CENSORED` (backfilled two
rounds ago) rather than a gap, but a single censored seed inside a
still-open gap range does not by itself close the gap around it.

**Run the command above for the current, hash-and-identity-verified
count** — do not treat any number in this document as a permanent claim;
it changes every time a gap seed is attempted.

## Outstanding backfill (honest — nothing fabricated)

### 1. Seeds 0-5, 17, 34-49 (23 completed pairs): mechanically backfillable

Every one of these seeds has a real, on-disk, dual-tap-produced trace pair
that `scripts.l2_event.validate_dual_division_canary.validate_dual_division_canary`
independently validates (hash, source-binding, margin-gate, same-
completion-tick cross-check, and — since the 2026-09-09 horizon-plumbing
fix, tightened in the second re-review round — a monotone-minimum
`max_search_ticks >= window.window_anchor` check, never the looser
`n_ticks` floor a first fix attempt used, and never an exact match
against the contract's 100000 horizon) that no longer breaks on these
seeds' legacy 50000-tick recorded horizon. All 23 were independently
re-validated end-to-end this session under the corrected check, via the
real no-arg `division_cohort_selector.py` invocation above (which calls
`resolve_seed_attempt`/`validate_dual_division_canary` for every seed
directory it discovers, not just the contiguous prefix) — 23/23 PASS,
zero `CohortContractError`s.
`division_cohort_selector.resolve_seed_attempt` synthesizes a
`backfilled=True` `COMPLETED` `AttemptRecord` for these automatically,
read-only, without writing anything or rewriting any trace bytes.

To materialize a real `division_window_attempt.json` sidecar next to each
trace pair (never overwriting the `.mat` files themselves), a future
authorized pass should extend the existing atomic-write helper
(`extract_dual_division_window.m`'s `write_division_window_attempt_record`)
into a small standalone Python backfill script analogous to
`scripts/l2_event/backfill_right_censored_from_log.py`'s design — compute
both trace hashes and write the JSON sidecar, refusing if one already
exists (mirroring that script's overwrite-refusal contract). Not done in
this branch for these 21 seeds because they live in shared worker
worktrees or the shared consolidated root, and a bulk sidecar-writing pass
across all of them is a separate, larger, independently-reviewable
operational action from the code fix this branch delivers.

### 2. Seeds 7-16, 19-33 (25 seeds): never attempted under this contract

No worker range ever covered these seeds (the historical 3-parallel-worker
methodology assigned disjoint seed *ranges* — 0-2/17/34-49-ish — never one
ascending stream). They are genuine gaps, not censored. The next real
extraction work (once separately authorized) must attempt them, starting
with seed 7 (`next_seed_to_attempt`, now that seed 6 is resolved as
genuinely `RIGHT_CENSORED` — see item 3 below), via the now-fixed driver
(which reads `max_search_ticks` from the selection contract by default —
no need to pass it explicitly unless overriding):

```bash
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(7, 16)"
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(19, 33)"
```

Both calls now default to `max_search_ticks=100000` (the selection
contract's horizon) automatically — see
`scripts/matlab/extract_dual_division_window.m`'s
`division_window_selection_contract().max_search_ticks` default — and both
accept an explicit 4th `opts` argument (e.g.
`struct('max_search_ticks', 150000)`) for a sanctioned override.

### 3. Seed 6: BACKFILLED this session — mechanically source-bound, not fabricated

`bulk-division-a/artifacts/seed6_100k_probe.status` finished this session
(`FAILED seed=6 max_search_ticks=100000 MATLAB exited with code 1`, job
`dual_a_s006_100k_probe_20260908_221616_27040`) with no `.mat` output
files ever emitted for seed 6 — genuine right-censoring, not a crash. The
job log
(`bulk-division-a/artifacts/matlab_jobs/dual_a_s006_100k_probe_20260908_221616_27040.log`)
contains the exact real extractor error text:

```
Error using extract_dual_division_window (line 207)
seed 6: division-completion signal did not fire within max_search_ticks=100000 ticks -- refusing to fabricate a window_anchor; either raise anchor_opts.max_search_ticks or this seed genuinely does not complete in that many ticks
```

This session independently re-verified (not merely trusted) two source
identity claims, exactly as for seed 18:

* the log's own `[karr_bootstrap] using generated DNADamage overlay:
  E:\opencell-worktrees\bulk-division-a\tmp\wcm_source_overlay\src` line
  names a directory whose `DNADamage.m` file still exists on disk and
  whose LF-normalized SHA-256 is
  `86d8b3c2d2ed42df03e1b9ea14f06efc4b645a4e6aeaa3ef938b9ea41ad27e7e` —
  **byte-for-byte identical** to this worktree's CURRENT
  `launcher.current_genuine_dnadamage_source()['patched_sha256_lf_normalized']`
  (the same hash seed 18's backfill independently verified — both worker
  worktrees' overlays resolve to the same dec-005-patched source as
  current main);
* the log's `[karr_bootstrap] mnrnd provider: E:\MATLAB\toolbox\stats\stats\mnrnd.m
  (R2026a, toolbox 26.1)` line names the same path/release/toolbox
  version this worktree's `launcher.current_genuine_mnrnd_provider()`
  currently resolves.

Backfilled this session via the reviewed tool (never fabricated):

```bash
python scripts/l2_event/backfill_right_censored_from_log.py \
  --log-path /mnt/e/opencell-worktrees/bulk-division-a/artifacts/matlab_jobs/dual_a_s006_100k_probe_20260908_221616_27040.log \
  --karr-native-root /mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native/dual_division_cohort_current
```

producing
`main-integrate/data/m1_sources/karr_native/dual_division_cohort_current/per_process_traces_v2_event_s006/division_window_attempt.json`
(seed 6, `status=RIGHT_CENSORED`, `max_search_ticks=100000`, both hashes
verified as above, no trace files present — mutual exclusivity intact).
Re-running the same command is idempotent-safe: it refuses to overwrite
an existing record without `--force`.

### 4. Seed 18: BACKFILLED two rounds ago — mechanically source-bound, not fabricated

`bulk-division-b/artifacts/seed18_100k_probe.log` (job
`dual_b_s018_100k_probe_20260908_092734_24856`, status file `FAILED
seed=18 max_search_ticks=100000 ... exit code 1`) contains the exact real
extractor error text:

```
Error using extract_dual_division_window (line 207)
seed 18: division-completion signal did not fire within max_search_ticks=100000 ticks -- refusing to fabricate a window_anchor; either raise anchor_opts.max_search_ticks or this seed genuinely does not complete in that many ticks
```

This session (this backfill was performed in the immediately prior
implementation round, 2026-09-09, and independently re-confirmed still
present and intact at the start of this second re-review round)
independently re-verified (not merely trusted) two source identity
claims:

* the log's own `[karr_bootstrap] using generated DNADamage overlay:
  E:\opencell-worktrees\bulk-division-b\tmp\wcm_source_overlay\src` line
  names a directory whose `DNADamage.m` file **still exists on disk**
  (timestamped `2026-09-08 09:27:43`, matching the run) and whose
  LF-normalized SHA-256 (`scripts.l2_event.launcher.
  lf_normalized_sha256_hex`, the same algorithm `karr_bootstrap.m` itself
  uses) is `86d8b3c2d2ed42df03e1b9ea14f06efc4b645a4e6aeaa3ef938b9ea41ad27e7e`
  — **byte-for-byte identical** to this worktree's CURRENT
  `launcher.current_genuine_dnadamage_source()['patched_sha256_lf_normalized']`;
* the log's `[karr_bootstrap] mnrnd provider: E:\MATLAB\toolbox\stats\stats\mnrnd.m
  (R2026a, toolbox 26.1)` line names the same path/release/toolbox
  version this worktree's `launcher.current_genuine_mnrnd_provider()`
  currently resolves.

This is sufficient, mechanically source-bound evidence (never the
plan.md narrative alone) for a real `RIGHT_CENSORED`
`division_window_attempt.json`. It was generated and written this session
via:

```bash
python scripts/l2_event/backfill_right_censored_from_log.py \
  --log-path /mnt/e/opencell-worktrees/bulk-division-b/artifacts/seed18_100k_probe.log \
  --karr-native-root /mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native/dual_division_cohort_current
```

producing
`main-integrate/data/m1_sources/karr_native/dual_division_cohort_current/per_process_traces_v2_event_s018/division_window_attempt.json`
(seed 18, `status=RIGHT_CENSORED`, `max_search_ticks=100000`, both hashes
verified as above, no trace files present — mutual exclusivity intact).
Re-running the same command is idempotent-safe: it refuses to overwrite
an existing record without `--force`.

## Summary (fast filesystem-existence snapshot; re-run the CLI for a verified answer)

| Category | Seeds | Count |
|---|---|---|
| Contiguous, mechanically backfillable COMPLETED | 0-5 | 6 |
| Contiguous, backfilled RIGHT_CENSORED (mechanically source-bound) | 6 | 1 |
| Premature COMPLETED (real traces, pending gap-fill) | 17, 34-49 | 17 |
| Premature, backfilled RIGHT_CENSORED (mechanically source-bound) | 18 | 1 |
| Genuine gaps, never attempted | 7-16, 19-33 | 25 |
| **Total accounted for** | 0-49 | **50** |

`selection_satisfied = False` (6 of 50 required completions currently
certifiable under the contiguous-attempt rule; seed 6's censor extends the
contiguous prefix but contributes zero completions). Closing the gap seeds
(7-16, 19-33) in ascending order is the only path to unlocking the 17
premature completions already on disk toward the N=50 requirement — no
additional re-extraction of seeds 17 or 34-49 themselves is required.
