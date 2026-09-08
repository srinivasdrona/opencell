# Division-window cohort-censoring contract — migration/backfill plan

Preregistered 2026-09-08, branch `fix/division-censor-contract`, base
`701b991` (`docs: preregister division censoring direction`).

See `docs/phase_f/l2_event/division_window_spec.json`'s `selection_contract`
for the machine-loadable contract this document explains the current
migration state against, and `scripts/l2_event/division_cohort_selector.py`
for the enforcing implementation (`audit_cohort()` / CLI).

## Why this document exists

Seeds 6 and 18 produced no Cytokinesis division-completion signal within
the pre-existing per-call `max_search_ticks=50000` default under the
patched (dec-005-bound) source; no partial trace files were emitted for
either. Seed 18 additionally failed a reported non-counting 100000-tick
diagnostic. Left uncorrected, silently skipping/resampling either seed
would condition the `N=50` cohort on completion — outcome cherry-picking.
The new contract instead requires every seed to be attempted exactly once,
ascending from `candidate_seed_start=0`, with each attempt recording either
`COMPLETED` (paired trace files) or `RIGHT_CENSORED` (no trace files) in a
per-seed `division_window_attempt.json`.

**This document reports what the contract's own auditor mechanically finds
against the CURRENT on-disk state — it does not fabricate any record the
auditor cannot itself derive from real files.**

## Current on-disk state (surveyed 2026-09-08, this session)

Real trace-file presence was surveyed directly (filesystem existence only,
not full HDF5 re-validation — that additional step is called out
separately below) across every worktree known to hold patched-source
(dec-005-bound) Cytokinesis+FtsZPolymerization dual-tap output:

| Worktree | Seeds with a complete `Cytokinesis_5000ticks.mat` + `FtsZPolymerization_200ticks.mat` pair | Empty (no files) |
|---|---|---|
| `main-integrate` | 0,1,2,3,4,5,17,34,35 (36 Cytokinesis-only, stale local copy) | — |
| `bulk-division-a` | 0,1,2,3,4,5 | 6 |
| `bulk-division-b` | 17 | 18 |
| `bulk-division-c` | 34,35,36,37,38,39,40,41,42,43,44,45,46 | 47 (in progress) |
| `fix-dual-cyt-window` | 36 | — |

Union of patched-source COMPLETED pairs across all worktrees: **seeds
0,1,2,3,4,5,17,34,35,36,37,38,39,40,41,42,43,44,45,46 (20 seeds)**.
Seeds 6 and 18 have empty output directories in every worktree searched —
no trace files, and (because this contract's attempt-record writer did not
exist until this branch) **no `division_window_attempt.json` either**.

## What `division_cohort_selector.audit_cohort()` mechanically reports against this state

Feeding the above file layout through the auditor (verified against an
equivalent synthetic ledger by
`tests/scripts/test_division_cohort_selector.py::test_genuine_gap_stops_contiguity_and_reports_next_seed`,
which reproduces exactly this "gap before later out-of-order completions"
shape) yields:

* `contiguous_prefix_end = 5` — seeds 0-5 are the only ones forming an
  unbroken ascending run from `candidate_seed_start=0`.
* `next_seed_to_attempt = 6`.
* `gap_seeds = [6, 7, 8, ..., 16, 18, 19, ..., 33]` — every seed in this
  range has neither a trace pair nor an attempt record. **This is the
  direct, mechanical consequence of the historical 3-parallel-worker
  extraction methodology** (Worker A: seeds 0-2, Worker B: seed 17, Worker
  C: seeds 34-46), which assigned each worker a disjoint seed *range*
  rather than following one ascending stream — a real, load-bearing finding
  this contract surfaces for the first time.
* `premature_seeds = [17, 34, 35, ..., 46]` (21 seeds) — genuinely
  COMPLETED trace pairs that exist on disk and are **not deleted or
  invalidated**, but do not yet count toward the cohort because seeds
  6-16, 18-33 have not yet been attempted.
* `completed_seeds = [0, 1, 2, 3, 4, 5]` (only the contiguous prefix).
* `completed_count = 6`, `required_completed_windows = 50`,
  `selection_satisfied = False`.
* `censored_seeds = []` — seeds 6 and 18 are **not yet mechanically
  recorded as censored** (see below); they currently resolve to gaps, not
  censored attempts.

## Outstanding backfill (honest — nothing fabricated)

### 1. Seeds 0-5, 17, 34-46 (20 completed pairs): mechanically backfillable

Every one of these seeds has a real, on-disk, dual-tap-produced trace pair
that `scripts.l2_event.validate_dual_division_canary.validate_dual_division_canary`
can independently validate (hash, source-binding, margin-gate, same-
completion-tick cross-check). `division_cohort_selector.resolve_seed_attempt`
synthesizes a `backfilled=True` `COMPLETED` `AttemptRecord` for these
automatically **without writing anything or rewriting any trace bytes** —
backfill here is read-only inference, safe to run repeatedly.

To materialize a real `division_window_attempt.json` sidecar next to each
trace pair (never overwriting the `.mat` files themselves), a future
authorized pass should extend `extract_dual_division_window.m`'s
`write_division_window_attempt_record` helper into a small standalone
backfill script, or invoke it once per legacy seed via a thin MATLAB/Python
wrapper that only computes the two trace hashes and writes the JSON
sidecar. This branch intentionally does **not** perform that write against
`main-integrate`/`bulk-division-*` — those are shared worktrees with other
concurrent work in flight (see plan.md's "Concurrency rule"), and writing
into them is outside this branch's own history/reviewability.

**Exact command to run this branch's read-only backfill/audit against the
real data** (from any worktree with access to the listed roots):

```bash
python scripts/l2_event/division_cohort_selector.py \
  --search-root /mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native \
  --search-root /mnt/e/opencell-worktrees/bulk-division-a/data/m1_sources/karr_native \
  --search-root /mnt/e/opencell-worktrees/bulk-division-b/data/m1_sources/karr_native \
  --search-root /mnt/e/opencell-worktrees/bulk-division-c/data/m1_sources/karr_native \
  --search-root /mnt/e/opencell-worktrees/fix-dual-cyt-window/data/m1_sources/karr_native
```

Operational note: this command performs full HDF5 validation (including
sha256 hashing of every ~27MB Cytokinesis trace) for each candidate seed.
Observed in this session: this can take on the order of tens of minutes
when the search roots are accessed cross-filesystem (Windows NTFS via
WSL's `/mnt/e/...` DrvFS mount) rather than natively. Run it from within
native WSL against a native-filesystem copy, or budget accordingly, before
treating a hang as a bug.

### 2. Seeds 7-16, 19-33 (25 seeds): never attempted under this contract

No worker range ever covered these seeds. They are genuine gaps, not
censored — the next real extraction work (once authorized) must attempt
them, starting with seed 6 (`next_seed_to_attempt`), via:

```bash
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(6, 16)"
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window_seeds(19, 33)"
```

(Each call passes `max_search_ticks` implicitly via
`extract_dual_division_window`'s own default of 50000 unless overridden;
per the selection contract's `horizon_vs_existing_traces` note, a fresh
COMPLETED outcome at any horizon below 100000 remains valid, but a
RIGHT_CENSORED outcome only counts if attempted at the full 100000-tick
horizon — pass `struct('max_search_ticks', 100000)` explicitly, e.g. via
a one-off `extract_dual_division_window(uint32(N), struct('max_search_ticks', 100000))`
call, for any seed where a right-censored outcome under the OLD 50000
default is suspected.)

### 3. Seed 6: reported 100000-tick diagnostic (`dual-a-seed6-100k`) not bindable

`plan.md` (commit `701b991`) records that seed 6's matching 100000-tick
diagnostic was launched (`dual-a-seed6-100k`) at the time of this
preregistration. **No mechanically-verifiable artifact for that run** (no
log file, no `division_window_attempt.json`, no dnadamage-source-hash
binding) was found anywhere in this session's search (main checkout,
`main-integrate`, `bulk-division-a/b/c`, or the session's persisted
`files/` directory). Its outcome (if it completed) is therefore
**UNKNOWN under this contract** — status remains an open gap, not
inferred either way.

**Backfill command** (re-attempt from scratch, cleanly, under the
instrumented extractor so a real `division_window_attempt.json` is
produced regardless of outcome):

```bash
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window(uint32(6), struct('max_search_ticks', 100000))"
```

### 4. Seed 18: reported 100000-tick diagnostic also not bindable

Same situation as seed 6: `plan.md` records that seed 18's 100000-tick
diagnostic (`dual-b-seed18-100k`) also found no completion, but no
mechanically-verifiable log/hash-bound artifact for it exists in any
searched location. Per the task's own instruction, this is represented
here **only as an open gap with a clear backfill command — never
fabricated as a `RIGHT_CENSORED` record** from the unbindable narrative
alone:

```bash
matlab -batch "addpath(genpath('scripts/matlab')); extract_dual_division_window(uint32(18), struct('max_search_ticks', 100000))"
```

If this re-attempt again finds no completion within 100000 ticks, the
extractor (as modified on this branch) will now automatically write a
proper `division_window_attempt.json` with `status=RIGHT_CENSORED`,
`max_search_ticks=100000`, and the current `dnadamage_source_resolved_sha256`
— at that point seed 18 becomes a valid, mechanically-recorded censored
seed under this contract for the first time.

## Summary

| Category | Seeds | Count |
|---|---|---|
| Contiguous, mechanically backfillable COMPLETED | 0-5 | 6 |
| Premature COMPLETED (real traces, pending gap-fill) | 17, 34-46 | 21 |
| Genuine gaps, never attempted | 7-16, 19-33 | 25 |
| Reported-but-unbindable, open gap | 6, 18 | 2 |
| **Total accounted for** | | **54** (0-46 plus 47 in progress not yet counted) |

`selection_satisfied = False` (6 of 50 required completions currently
certifiable under the contiguous-attempt rule). Closing `gap_seeds`
(seeds 6-16, 18-33) in ascending order is the only path to unlocking the
21 premature completions already on disk toward the N=50 requirement —
no additional re-extraction of seeds 17 or 34-46 themselves is required.
