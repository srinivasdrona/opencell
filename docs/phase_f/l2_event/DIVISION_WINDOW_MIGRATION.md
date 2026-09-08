# Division-window cohort-censoring contract — migration/backfill plan

Preregistered 2026-09-08, revised 2026-09-09 (Opus implementation
re-review), branch `fix/division-censor-contract`, base `701b991`
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
and the spec's `authoritative_operational_root` field). It also
automatically searches every sibling worker worktree
(`default_search_roots()`) and **hard-fails** (`CohortContractError`) if
any two roots disagree about the same seed — never silently trusts
whichever root is listed first.

Operational note (this session): running this command with search roots
that reach across the WSL↔NTFS filesystem boundary (`/mnt/e/...` against
an `E:` drive) was observed to take longer than a reasonable interactive
wait in this environment, likely DrvFS overhead on ~27 MB-per-seed HDF5
reads. Run it from **native WSL against a native-filesystem copy**, or
budget for a multi-minute wait, before treating a long-running invocation
as a bug.

## Fast filesystem-existence snapshot (this session, 2026-09-09 ~02:25 IST)

Directory listing only (`Get-ChildItem`, no content read) of the
authoritative root
(`main-integrate/data/m1_sources/karr_native/dual_division_cohort_current`):

| Seeds | Contents |
|---|---|
| 0, 1, 2, 3, 4, 5, 17, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47 | `Cytokinesis_5000ticks.mat` + `FtsZPolymerization_200ticks.mat` (20 seeds — seed 47 completed and banked since the last review pass) |
| 18 | `division_window_attempt.json` only (RIGHT_CENSORED — backfilled this session, see below) |
| 6 | absent (see "Seed 6" below — a live 100000-tick attempt is still running elsewhere as of this snapshot) |

Mechanically, per `division_cohort_selector`'s contiguity rule (verified
against this exact shape by
`tests/scripts/test_division_cohort_selector.py::test_genuine_gap_stops_contiguity_and_reports_next_seed`):
the contiguous prefix from `candidate_seed_start=0` still ends at seed 5
(seed 6 has no record of any kind), so `next_seed_to_attempt=6`, and only
seeds 0-5 (6 completions) count toward `required_completed_windows=50`
today. Seeds 17, 34-47 (21 seeds) are genuine `COMPLETED` evidence,
preserved and never invalidated, but remain "premature" — not yet
selectable — until seeds 6-16 and 19-33 are attempted in ascending order.
Seed 18 is now `RIGHT_CENSORED` (see below) rather than a gap, but a
single censored seed inside a still-open gap range does not by itself
close the gap around it.

**Run the command above for the current, hash-and-identity-verified
count** — do not treat "6" as a permanent number; it changes every time a
gap seed is attempted.

## Outstanding backfill (honest — nothing fabricated)

### 1. Seeds 0-5, 17, 34-47 (20 completed pairs): mechanically backfillable

Every one of these seeds has a real, on-disk, dual-tap-produced trace pair
that `scripts.l2_event.validate_dual_division_canary.validate_dual_division_canary`
independently validates (hash, source-binding, margin-gate, same-
completion-tick cross-check, and — since the 2026-09-09 horizon-plumbing
fix — a monotone-minimum `max_search_ticks >= n_ticks` check that no
longer breaks on these seeds' legacy 50000-tick recorded horizon).
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
this branch for these 20 seeds because they live in shared worker
worktrees or the shared consolidated root, and a bulk sidecar-writing pass
across all of them is a separate, larger, independently-reviewable
operational action from the code fix this branch delivers.

### 2. Seeds 7-16, 19-33 (25 seeds): never attempted under this contract

No worker range ever covered these seeds (the historical 3-parallel-worker
methodology assigned disjoint seed *ranges* — 0-2/17/34-47-ish — never one
ascending stream). They are genuine gaps, not censored. The next real
extraction work (once separately authorized) must attempt them, starting
with seed 6 (`next_seed_to_attempt`), via the now-fixed driver (which reads
`max_search_ticks` from the selection contract by default — no need to
pass it explicitly unless overriding):

```bash
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(6, 16)"
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(19, 33)"
```

Both calls now default to `max_search_ticks=100000` (the selection
contract's horizon) automatically — see
`scripts/matlab/extract_dual_division_window.m`'s
`division_window_selection_contract().max_search_ticks` default — and both
accept an explicit 4th `opts` argument (e.g.
`struct('max_search_ticks', 150000)`) for a sanctioned override.

### 3. Seed 6: reported 100000-tick diagnostic (`dual-a-seed6-100k`) is CONFIRMED STILL RUNNING

`bulk-division-a/artifacts/seed6_100k_probe.status` reads `RUNNING
seed=6 max_search_ticks=100000` as of this session (log
`bulk-division-a/artifacts/seed6_100k_probe.log`, MATLAB script
`dual_a_s006_100k_probe_20260908_221616_27040`, actively appending new
warning lines during this session). **Do not touch or kill this process.**
Its outcome is genuinely unknown — not failed, not censored, not
completed. Once it finishes:

* if it completes, its trace pair becomes selectable via the normal path
  (no special handling needed);
* if it right-censors, re-run it once more (or a fresh attempt) through
  the now-instrumented extractor so a real
  `division_window_attempt.json` is written automatically:

```bash
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window(uint32(6), struct('max_search_ticks', 100000))"
```

If the CURRENTLY-RUNNING process's own log later shows the exact
"division-completion signal did not fire within max_search_ticks=100000
ticks" text with a mechanically re-verifiable DNADamage-overlay hash (the
same evidence chain used for seed 18 below), it can be backfilled the
same way without a fresh re-run:

```bash
python scripts/l2_event/backfill_right_censored_from_log.py \
  --log-path /path/to/seed6_100k_probe.log \
  --karr-native-root /mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native/dual_division_cohort_current
```

### 4. Seed 18: BACKFILLED this session — mechanically source-bound, not fabricated

`bulk-division-b/artifacts/seed18_100k_probe.log` (job
`dual_b_s018_100k_probe_20260908_092734_24856`, status file `FAILED
seed=18 max_search_ticks=100000 ... exit code 1`) contains the exact real
extractor error text:

```
Error using extract_dual_division_window (line 207)
seed 18: division-completion signal did not fire within max_search_ticks=100000 ticks -- refusing to fabricate a window_anchor; either raise anchor_opts.max_search_ticks or this seed genuinely does not complete in that many ticks
```

This session independently re-verified (not merely trusted) two source
identity claims:

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
| Premature COMPLETED (real traces, pending gap-fill) | 17, 34-47 | 21 |
| Genuine gaps, never attempted | 7-16, 19-33 | 25 |
| Backfilled RIGHT_CENSORED (mechanically source-bound) | 18 | 1 |
| In progress (do not touch) | 6 | 1 |
| **Total accounted for** | 0-47 | **48** |

`selection_satisfied = False` (6 of 50 required completions currently
certifiable under the contiguous-attempt rule). Closing the gap seeds
(6-16, 18-33 — noting 18 is now resolved) in ascending order is the only
path to unlocking the 21 premature completions already on disk toward the
N=50 requirement — no additional re-extraction of seeds 17 or 34-47
themselves is required.
