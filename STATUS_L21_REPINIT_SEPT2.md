# L2.1 ReplicationInitiation — Session N+7 (current-main rebuild, `integrate/l21-repinit-current`)

> This worktree's own status file. For the full Session N+1..N+6 narrative
> (tick-4/tick-13/tick-40/tick-41/tick-55 root causes, the real MATLAB RNG
> ledger construction, DEC-005/DEC-006, and the Session N+6 "portability
> fix + explicit no-ledger diagnostic" candidate that Opus **REJECTED**),
> see `integrate-l21-repinit-clean`'s `STATUS_L21_REPINIT_SEPT2.md` (Session
> N+5 "read this first" correction, then N+6). This session **rebuilds
> from current main** per plan.md's rejection notes rather than repairing
> the rejected clean branch in place, per explicit operator instruction.

## Session N+8 (curation after second Opus review — READ THIS FIRST)

Opus reviewed Session N+7's candidate (`7889449`) and **ACCEPTED the L2.1
code with a clean split**, but **REJECTED the whole branch as committed**
for one concrete, verified defect plus two honesty corrections. This
section documents exactly what was wrong, why, and what changed. Nothing
below is a silent rewrite of Session N+7's prose; it is an explicit,
dated correction.

**What was actually wrong:**

1. **Tracked `sweep_report.json`/`sweep_status.json` were mutually
   inconsistent.** Session N+7 ran `sweep.py run --processes
   ReplicationInitiation` (updating only RepInit's row in
   `sweep_report.json`, correctly preserved via the merge fix), then
   *separately* regenerated `sweep_status.json` from scratch against
   `evidence_bundle/` for **every** process. That second step reintroduced
   a real cross-file inconsistency for `DNASupercoiling`: the tracked
   `sweep_report.json` still recorded `RAN_EXIT_0` for it (correctly
   preserved, untouched), but the freshly regenerated `sweep_status.json`
   recorded `NOT_STARTED` for it (a pre-existing, unrelated stale `runner`
   sentinel hash on `DNASupercoiling`'s own evidence, nothing to do with
   RepInit). `test_committed_sweep_status_is_not_a_stale_pre_run_snapshot`
   exists on current main precisely to catch this class of mismatch and
   correctly failed against that candidate: **52/53 sweep tests passed,
   not 53/53 as Session N+7's table claimed.** The 53/53 number was true
   at an earlier point in that session (before the `sweep_status.json`
   regeneration step) and was never re-verified after that later step —
   a real process failure, not a fabrication, but a false claim as
   committed.
   - **Fix (this session):** both tracked files are held back from this
     L2.1 integration entirely and restored to current-main (`b016862`)
     bytes, byte-for-byte. The `write_sweep_report` merge-fix *code* and
     its new regression test (`test_write_sweep_report_process_scoped_
     rerun_preserves_other_processes`) are kept — the mechanism is real
     and independently re-verified (see below) — but no tracked snapshot
     produced by exercising that mechanism against this repo's live state
     is part of this integration. Regenerating a genuinely consistent
     `sweep_status.json` (and resolving `DNASupercoiling`'s own unrelated
     stale sentinel) is left to whichever future change actually touches
     `DNASupercoiling`, not bundled into an unrelated RepInit change.
2. **Session N+7's STATUS/plan/provenance claimed "no regressions" and
   "53/53"** without qualification. Both claims are corrected here. The
   provenance JSONL entry for Session N+7
   (`sha256:e8fb6b0eadb7c3c9bf1baa63f24e1eb8061651daedceb9eb634bb81793b1ab8c`)
   is **not rewritten** (append-only ledger); a new entry with
   `--supersedes` pointing at it has been appended instead, stating the
   correction plainly.
3. **`evidence_index.json`'s honest RepInit `PASS`->`FAIL` demotion must
   land in the *same* integration commit as the RepInit module's own
   behavior change**, not a separate commit, so a reader checking out any
   single commit of this integration never sees a stale green `PASS` next
   to the exact source change that invalidated it. Independently verified
   in this session that main's existing `PASS` row is **physically
   stale on two independent grounds**, not merely a sentinel-hash
   technicality:
   - `oc_module` (`karr_replication_initiation.py`) hash changed:
     recorded `0c428c473ded..` vs current `025a7b02f087..`.
   - The canonical oracle `.mat` input itself changed: the evidence's own
     `input_manifest.json` records
     `sha256=ab83714a0eb38b4b76931583d0d08a26de00ad52ae3f3f795dde0e0757033403`
     for `data/m1_sources/karr_native/per_process_traces_v2/
     ReplicationInitiation_100ticks.mat`; that file's *current* SHA-256 is
     `0c61c816e3903e771550e674db36fedaa76a546687891a99e46f163703550c0f`
     (the same hash verified elsewhere in this document as the correctly
     restored canonical 100-tick trace). The evidence was generated
     against a different physical oracle file than the one now on disk.
   Board after the fix, in this same commit: **18 PASS / 2 FAIL / 2
   MISSING_EVIDENCE**, generator `audit` reports `integrity: OK`.
4. **Test strengthening**: `test_replication_initiation_full_200_tick_
   chromosome_stream_ledger_bit_identity` previously asserted only
   `compared_tick_count == 200` and `honest is not None` — sufficient to
   prove the replay ran to completion, but not that it was actually
   bit-identical. It now asserts `bit_identity.pass_all_compared_ticks is
   True` and `bit_identity.first_mismatch_tick/observable/index is None`
   directly. It also no longer cites a nonexistent, never-committed
   `scripts/tmp_repinit_full_ledger_scan.py` scratch script as
   independent verification; the docstring now says plainly that this
   test's own assertions plus a direct, reproducible
   `scripts/diagnose_repinit_l21.py` invocation are the only verification
   (both are re-run and re-confirmed in this session; see below).

**What this session did NOT need to change:** the extractor, ledger
reconstruction, per-process registry, `karr_replication_initiation.py`
source fixes, `dec-006`, and the `write_sweep_report` merge fix itself
were all **ACCEPTED as-is** by Opus. Session N+7's narrative below (the
"Why a rebuild" and "What this session changed" sections) remains
accurate for those pieces and is preserved unedited.

## Why a rebuild instead of a repair

Opus rejected `integrate/l21-repinit-clean` @ `78ad334`'s shared
integration surface for four reasons:

1. `extract_per_process_traces_v2.m` had a MATLAB-illegal nested function.
2. It changed both public signatures of the extractor.
3. It omitted `dnadamage_overlay_required` from the unconditional metadata
   block.
4. It lacked the already-accepted Cytokinesis/HostInteraction shared-file
   logic (both landed on main after the clean branch was cut), and its
   `sweep_report.json` truncated 17 tracked jobs down to 1 (a real
   process-scoped `write_sweep_report` bug, not a data-entry mistake),
   predating `sweep_status.json`.

It also separately found that the real 100-tick canonical
`ReplicationInitiation` oracle trace had been accidentally replaced by a
200-tick file at some point before that review.

Given #4 alone required a structural fix (a merge, not an overwrite) to
`write_sweep_report`, and given #1-#3 required starting the extractor edit
from current main's actual shared metadata block (not the clean branch's
already-diverged copy), this session started this fresh worktree
(`integrate-l21-repinit-current`) from current main and reapplied only the
minimum required deltas, verifying each one against a concrete test before
moving to the next.

## What this session changed (surgical, current-main-based)

### 1. Extractor (`scripts/matlab/extract_per_process_traces_v2.m`)

The only change is: the five `dnadamage_source_*` / `dnadamage_overlay_
required` metadata assignments (previously written ONLY inside the
`if strcmp(window_contract, 'fixed') || strcmp(window_contract, 'anchor')`
guard) now live **unconditionally**, immediately after that guard's closing
`end`, so every trace — including a plain `window_contract=''` trace like
`ReplicationInitiation`'s canonical extraction — carries the exact
DNADamage.m source identity its trajectory resolved against. This is a
**pure additive relocation** of an already-computed value
(`karr_bootstrap()` computes `dnadamage_overlay` unconditionally on every
call already); it does not change any existing DNADamage
(`'fixed'`/`'anchor'`) trace's already-recorded values, does not touch the
genuine-mnrnd-provider metadata (which correctly stays inside the
fixed/anchor guard, since it is a real event-window-only concept), does
not introduce any nested function, and does not change either public
signature. Verified by `tests/scripts/test_extract_per_process_traces_v2_
static.py` (13/13 passed), including two updated assertions that now
require the five fields to live OUTSIDE the guard body and after its
closing `end`.

### 2. Ledger reconstruction (`scripts/matlab/reconstruct_chromosome_draw_
ledger.m`)

Generalized from "DNADamage-only" to process-agnostic (used by both
DNADamage's own L2.1 lane and ReplicationInitiation's), and added
first-class **quiescent-tick** handling: when `state_before(t) ==
state_after(t)` for a tick, the target process made zero chromosome-owned
draws that tick — recorded literally as `n_draws=0`/`draws=[]`, not
inferred by walking an LCG looking for a coincidental return to the same
state (which would require ~2^31 draws for a modulus-`2^31-1` generator,
far beyond `max_draws_per_tick`). Report now also carries
`n_quiescent_ticks` and a corrected log line reporting total draws instead
of a per-tick array dump.

### 3. Per-process chromosome-ledger stream registry (`scripts/l21_active_
window_audit.py`)

Added `_CHROMOSOME_LEDGER_STREAM_CLS: dict[str, type]` mapping
`"DNADamage" -> KarrLedgerReplayStream` and `"ReplicationInitiation" ->
_ReplicationInitiationChromosomeLedgerRandStream`. `_honest_replay` now
looks up the stream class by `process_name` via this registry (fail-closed
`KeyError` if a `_ProcessSpec.chromosome_rand_stream_ledger_attr` entry has
no matching registry entry) instead of hardcoding `KarrLedgerReplayStream`
for every consuming process. This is additive: DNADamage's existing
behavior is unchanged (same class, same call site), and
ReplicationInitiation gets its own call-shape-appropriate stream class.

### 4. `_ProcessSpec` / `_build_context` (`tests/vivarium/l2_2_replay_
common_v2.py`)

- `ReplicationInitiation`'s spec now declares
  `chromosome_rand_stream_ledger_attr="_chromosome_rng"`.
- `_build_context` gained an explicit, opt-in
  `disable_chromosome_rand_stream_ledger: bool = False` parameter (default
  False = zero behavior change for every existing caller). When True, the
  companion ledger sidecar is never even looked up, making the resulting
  replay an **honest, explicit** non-ledger diagnostic — added after Opus's
  Session N+5 finding that `diagnose_repinit_l21.py`'s prior default
  behavior (silently auto-loading an adjacent sidecar whenever present) had
  been mistaken for an independent non-ledger confirmation when it was not.

### 5. Scalar-draws normalization (`tests/vivarium/chromosome_rand_stream_
ledger.py`)

MATLAB's `jsonencode` collapses a length-1 numeric array to a bare scalar
(`jsonencode([1.5])` -> `1.5`, not `[1.5]`). The loader now normalizes a
bare-scalar `draws` value back into a 1-element list **only when** that
same tick's own `n_draws` field is exactly 1; any other bare-scalar
`draws` (i.e. `n_draws != 1`, a genuinely malformed/truncated ledger)
still fails closed unchanged.

### 6. `write_sweep_report` merge fix (`scripts/l22_evidence/sweep.py`)

`write_sweep_report` now **merges** `results` into any existing report at
`path`, keyed by `process`, instead of unconditionally overwriting the
whole file. A `--processes ReplicationInitiation`-scoped rerun therefore
only replaces RepInit's own row; every other tracked process's row from
the prior full sweep is carried forward untouched, in stable
process-name-sorted order. This is the direct fix for rejection reason #4
above. New regression test
`test_write_sweep_report_process_scoped_rerun_preserves_other_processes`
reproduces the exact 17-jobs-collapsed-to-1 failure mode and asserts it no
longer happens.

### 7. `decisions/dec-006-shared-chromosome-randstream-input-oracle.md`
(new, non-colliding id)

Documents that the shared `Chromosome.randStream` state captured
before/after a tick is a captured **input oracle**, not RNG-output
leakage — the same epistemic status as `states_before` already restoring
substrate/enzyme/chromosome counts. `dec-005`'s index entry gets an
informational note (not a supersession) cross-referencing dec-006's
unconditional-metadata fulfillment of one of its own invalidation
triggers.

### 8. `opencell/vivarium/karr_replication_initiation.py` and `data/schemas/
per_process_wiring/ReplicationInitiation.yaml`

The process module itself carries the accumulated Session N+1..N+4
source-fidelity fixes (aggregate ordered R1-4/R5/9mer/8mer bind-then-
polymerize matching MATLAB's combined `bindProteinToChromosome` +
`polymerize` semantics; a faithful port of
`initializeStateBasedOnFinalConditions`; the `_second_copy_site_mask`
source-fidelity fix that closed the tick-41/55 residual). The wiring YAML
is a pure line-number/symbol-name re-anchor to match. **No public method
signature changed**; 21/21 unit tests in
`tests/vivarium/test_karr_replication_initiation.py` pass.

## Genuine current-tree verification (this session, this worktree)

All commands run via `bin\oc-pytest` / `bin\oc-py` (WSL venv), per project
convention.

| Check | Result |
|---|---|
| Extractor static tests | 13/13 passed |
| RepInit process unit tests | 21/21 passed |
| Active-window-audit chromosome-ledger tests (DNADamage + RepInit cases) | 20 passed, 16 skipped (DNADamage canonical seed2000 trace/ledger not populated in this worktree — data-dependent skip, expected) |
| `test_l22_evidence_sweep.py` (incl. new merge-preservation regression) | 53/53 passed against **restored current-main tracked sweep_report.json/sweep_status.json** (see Session N+8 above — this integration does not carry a regenerated pair) |
| `test_l2_1_strict_rubric.py` (active rubric — regression check on shared replay_common) | 28/28 passed |
| `test_l1b_verify_wiring.py` + `test_l2_no_oracle_dependency.py` | 57/57 passed |
| `test_l21_active_window_audit_chromosome_activity.py` + `..._host_custom_surfaces.py` | 10/10 passed |
| ChromCond/ChromSeg L2 replay (shared `l2_2_replay_common_v2.py` consumers) | 4 passed, 1 skipped (unrelated pre-existing data-dependent skip) |
| Ruff on every touched/new Python file | 3 pre-existing `SIM105` findings in `sweep.py` at lines untouched by this diff, confirmed present on `HEAD` before any edit (not a regression) |
| 100-tick canonical trace SHA-256 | `0c61c816e3903e771550e674db36fedaa76a546687891a99e46f163703550c0f` — matches both `main-integrate`'s copy and the task's specified hash |

### Honest L2.1 claim (ledger-restored 200/200 vs explicit no-ledger mismatch)

Ran `scripts/diagnose_repinit_l21.py` directly against the corrected,
re-extracted `ReplicationInitiation_200ticks.mat` + regenerated
`.chromosome_rand_stream_ledger.json` sidecar:

- **Ledger-restored** (default, restores Karr's real shared-Chromosome-
  stream input state each tick): `bit_identity_pass=true`,
  `compared_tick_count=200`, `first_mismatch_tick=null`. Genuine 200/200
  bit-identical replay.
- **Explicit `--no-ledger`** (honest non-ledger diagnostic, sidecar never
  loaded): `bit_identity_pass=false`, `compared_tick_count=200`,
  `first_mismatch_tick=15` (`enzymes[0]`, OC=0.0 vs Karr=1.0). This is the
  accepted, documented, non-blocking gap under DEC-005/DEC-006's own
  input-oracle scope: the shared stream's real tick-to-tick position is
  not independently reconstructable from a single-process trace by
  architecture, not by omission.

Both numbers are reproducible by rerunning the same two commands; neither
is asserted from memory of a prior session.

## L2.2 process-scoped regeneration: mechanism verified in isolation, tracked snapshot excluded

See **Session N+8** above for why the tracked `sweep_report.json`/
`sweep_status.json` pair is **excluded from this integration** and
restored to current-main bytes. The `write_sweep_report` merge-fix
mechanism itself was verified live in a prior session by actually running
`sweep.py run --processes ReplicationInitiation --max-workers 1`:

- `sweep_report.json` **preserved all 17 tracked jobs** (16 untouched +
  ReplicationInitiation's own row updated) — the merge fix works, not just
  in its unit test.
- ReplicationInitiation's own row: `RAN_NONZERO_EXIT`, reason `"Requested
  200 ticks, but oracle only provides 100."` This is an **honest,
  reproducible result**, not a regression this session introduced:
  - `PROCESS_CATALOG.yaml` requires `M_ticks: 200` for ReplicationInitiation
    (also DNARepair, ProteinDecay).
  - The generic v2 ensemble loader (`_v2_seed_mat_path` /
    `_v2_canonical_seed0_mat_path`) hardcodes the legacy filename
    `{Process}_100ticks.mat` for **both** the canonical single-seed L2.1
    oracle trace **and** the seed-0 slot of any 50-seed L2.2 ensemble — the
    same physical path serves two different purposes.
  - A genuine 50-seed/200-tick ensemble for these three processes *was*
    produced once before (see `scripts/l22_extraction/archive_depth200.py`
    and its regenerated files preserved in worktree `l22-depth200`), but
    populating it here would require overwriting
    `per_process_traces_v2/ReplicationInitiation_100ticks.mat` with 200-tick
    content — **exactly the accidental-canonical-file-replacement bug this
    task explicitly required fixing** (the file is verified above at the
    correct 100-tick SHA `0c61c816...`). This session will not reintroduce
    that regression to manufacture a green L2.2 row.
- That prior session's *separate, unfiltered* `sweep_status.json`
  regeneration against the tracked `evidence_bundle` is the exact step
  that introduced the `DNASupercoiling` cross-file inconsistency described
  in Session N+8 above. This integration does **not** carry that
  regenerated `sweep_status.json`; the tracked file is current-main's
  original byte-for-byte. `evidence_index.json` (a *different*, separately
  audited tracked file — see Session N+8 point 3) is still correctly
  updated in this same commit, since its own generator re-derivation is
  self-consistent and independently audited (`integrity: OK`), unlike the
  `sweep.py status` snapshot mechanism.

**Explicit no-ledger-mismatch-style honesty statement for L2.2:** this
session does **not** claim a fresh RepInit L2.2 PASS. The sweep
infrastructure fix (merge-preserving `write_sweep_report`, full-catalog
`sweep_status` regeneration) is verified end-to-end against real files.
Producing genuine new L2.2 evidence for ReplicationInitiation requires
either (a) a redesigned M-tick-aware seed-file naming convention that lets
a 200-tick ensemble coexist with the 100-tick L2.1 canonical trace at
different paths (a real, scoped follow-up, not done here), or (b) a fresh
50-seed/200-tick extraction under that redesigned convention. Neither is
in scope for this rebuild task's checklist, which asked for the *sweep
merge mechanism* to be fixed and verified, not for a new ensemble.

## Status as of Session N+8 (this integration)

This is the final curated integration commit set for a lightweight Opus
re-review:

1. `evidence_index.json`'s honest `PASS`->`FAIL` demotion for
   ReplicationInitiation lands in the **same commit** as the
   `karr_replication_initiation.py` behavior change (Session N+8 point 3).
2. Tracked `sweep_report.json`/`sweep_status.json` are **excluded**
   (restored to current-main `b016862` bytes byte-for-byte); only the
   `write_sweep_report` merge-fix code and its test are part of this
   integration.
3. Current published main (`b016862`) is merged into this branch; no
   conflicts (only `plan.md` differed, and this integration's own
   `plan.md` edit is a concise status update, not a wholesale carry-over
   of this worktree's prior long-form narrative).
4. Full targeted regression suite re-run against this exact commit set
   (extractor static/exact/no-ledger diagnostics, full ledger tests,
   preserved-process replays, active windows, L1b/oracle-dependency, full
   `test_l22_evidence_sweep.py` with the restored tracked files, generator
   `audit`, Ruff) — see the corrected results table above and the
   commit message for exact counts.
