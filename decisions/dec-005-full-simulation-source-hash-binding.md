# DEC-005: Full-simulation source-hash binding for Cytokinesis event-window traces

**Status:** Active
**Date:** 2026-09-04
**Decision:** Every Cytokinesis (and, via the dual-tap extractor, paired
FtsZPolymerization) event-window trace must record the exact DNADamage.m
source variant (`dnadamage_source_resolved_sha256`, plus
`dnadamage_source_original_sha256`/`dnadamage_source_patched_sha256`/
`dnadamage_source_resolved_path`/`dnadamage_overlay_required`) that was
resolved for its whole-simulation trajectory, and every validator that
accepts a Cytokinesis trace into the authoritative cohort must require
that hash to match the CURRENT worktree's `karr_bootstrap.m` resolution
(`scripts.l2_event.launcher.current_genuine_dnadamage_source`). Two traces
(or two taps of one dual-tap run) with disagreeing DNADamage source hashes
are never comparable evidence and must never be silently treated as
run-to-run stochastic variation.

## Context

While preparing the Cytokinesis M_ticks=5000 preregistration
(`docs/phase_f/l2_event/division_window_spec.json`), a fresh dual-tap
seed-36 re-run (span 4076 inclusive, onset 27918, completion 31993) was
compared against a pre-existing "conventional" single-process seed-36
trace (span 3964 inclusive, onset 24046, completion 28009). The prior
STATUS/spec writeup (now corrected) attributed this disagreement to
"genuine run-to-run whole-simulation nondeterminism" and to survivorship
bias in a 35-trace M_ticks=4000 cohort survey. **This was wrong.**

Opus review identified the actual, mechanical cause: the two runs
resolved two DIFFERENT `DNADamage.m` source variants.

- The live `genuine-l22-cytokinesis` queue's worktree checkout is at
  commit `1f7e758`, whose `scripts/matlab/karr_bootstrap.m` is unchanged
  since `b8a27a5` -- **before** the DNADamage signed-zero overlay was
  introduced (`d3e91e8` "Fix DNADamage signed-zero overlay", `c2174bb`
  "fix dnadamage per-reaction rate law", `f7d4310` "karr_bootstrap.m:
  hash/patch/write raw bytes for DNADamage signed-zero overlay"). Its
  conventional seed-36 trace was produced against the ORIGINAL,
  un-patched `DNADamage.m` (independently verified: this repo's own
  `E:\opencell\data\m1_sources\WholeCell\src\...\DNADamage.m`, hashed
  with the exact LF-normalized SHA-256 `karr_bootstrap.m` uses, is
  `6c8cfb07cbf84d7296861f97c6105a8b57a8d16e90f633784ea28855d3687d2a`).
- This worktree (`fix-dual-cyt-window`, base main `f71cfbb`) has all
  three overlay commits, so its `karr_bootstrap.m` automatically detects
  the un-patched source and applies the generated signed-zero-normalized
  overlay before every bootstrap. The dual-tap seed-36 re-run therefore
  ran against the PATCHED `DNADamage.m` (independently verified: hashing
  this worktree's own generated overlay file
  `tmp/wcm_source_overlay/src/...DNADamage.m` with the same algorithm
  gives `86d8b3c2d2ed42df03e1b9ea14f06efc4b645a4e6aeaa3ef938b9ea41ad27e7e`).
- The reviewer's own citation used abbreviated identifiers ("SHA
  `30ecbc14`" for the conventional run, "SHA `c5cb9e07`" for the dual run)
  for the same two variants; this decision's independently-computed full
  hashes above are offered as VERIFIED corroborating evidence for the
  same underlying finding (two different source variants were in effect),
  not asserted to be byte-identical to the reviewer's own abbreviated
  citation, whose exact computation method is not reproducible from this
  worktree alone.

DNADamage is one of the 28 processes in Karr's shared scheduler
(`calcResourceRequirements_Current`/`evolveState` run for every process
every tick, not just the one being tapped), so its source version affects
every OTHER process's real trajectory too, including Cytokinesis's and
FtsZPolymerization's, even though neither process's OWN source file
changed. This is not run-to-run nondeterminism at all -- it is a
straightforward "two runs used different model code" confound, and
byte-equivalence between two SAME-SOURCE runs remains a fully meaningful,
achievable requirement once source identity is verified and controlled.

## Decision

1. `scripts/matlab/extract_dual_division_window.m` captures
   `karr_bootstrap()`'s third return value (`dnadamage_overlay`, previously
   discarded via `~`) and writes `dnadamage_source_original_sha256`,
   `dnadamage_source_patched_sha256`, `dnadamage_source_resolved_sha256`,
   `dnadamage_source_resolved_path`, and `dnadamage_overlay_required` into
   BOTH the Cytokinesis and FtsZPolymerization output metadata structs
   unconditionally (not gated on "is this process DNADamage itself", unlike
   `extract_per_process_traces_v2.m`'s pre-existing, narrower gate -- see
   "Alternatives Considered").
2. `scripts/l2_event/launcher.py` gains
   `current_genuine_dnadamage_source()`, a MATLAB-free, pure-Python
   recomputation of the same identity `karr_bootstrap.m` derives at run
   time (mirrors `current_genuine_statistics_rng_provider`'s existing
   "recompute the expected identity from canonical files on disk, no
   MATLAB required" pattern), plus a new optional
   `AnchorWindowSpec.required_dnadamage_source_sha256` field:
   `validate_existing_event_window` fails closed (missing or mismatched
   metadata) whenever a spec sets this field.
3. `scripts/l2_event/prepare_cytokinesis_cohort.py` and
   `scripts/l2_event/validate_dual_division_canary.py` both set this field
   from `current_genuine_dnadamage_source()`, so every Cytokinesis cohort
   validation and every dual-tap canary validation now requires exact
   upstream-source identity agreement against the CURRENT worktree.
4. `validate_dual_division_canary.py`'s combined report gains a
   `dnadamage_source_match` cross-check (both taps'
   `dnadamage_source_resolved_sha256` must agree), mirroring the existing
   `mnrnd_provider_sha256` cross-check exactly.
5. `scripts/matlab/karr_bootstrap.m`'s overlay write is made atomic
   (temp file + `movefile`) as defense-in-depth against a torn read if two
   MATLAB processes ever run concurrently in the same worktree -- see
   "Concurrency policy" below.

## Concurrency policy (item 6)

`karr_bootstrap.m`'s generated overlay path
(`<repo_root>/tmp/wcm_source_overlay/src/...DNADamage.m`) is **shared
per-worktree, not per-PID**. **Running more than one bulk-extraction
MATLAB job concurrently in the same worktree is unsupported** -- every
concurrent `karr_bootstrap()` call in that worktree races to (re)write the
same file. The atomic-write hardening in this decision only prevents a
torn READ; it does not make concurrent same-worktree jobs a supported
configuration. Use one worktree (or, in a future change, a distinct
per-PID overlay path) per concurrent bulk worker.

## Arguments For

1. **Matches the actual evidence.** Two independently-checkable facts
   (git history showing the live queue's worktree predates the overlay
   commits; independently-recomputed SHA-256 hashes of both DNADamage.m
   variants) fully explain the seed-36 discrepancy without invoking any
   unverified nondeterminism claim.
2. **Restores byte-equivalence as a meaningful gate.** Once source
   identity is bound and checked, two same-source runs SHOULD be
   byte-identical (or structurally equivalent per the existing dual-tap
   acceptance), and a future disagreement under matched source hashes
   would be a real, actionable bug -- not explained away.
3. **Machine-checkable, not just documented.** The prior (retracted)
   explanation was pure prose; this decision is enforced by
   `validate_existing_event_window` and `validate_dual_division_canary.py`
   failing closed on any hash mismatch or missing metadata.

## Arguments Against (and rejected reasons)

1. **"Just fix the live queue's karr_bootstrap.m instead"** -- out of
   scope for this task (this worktree does not own the live
   `genuine-l22-cytokinesis` queue) and orthogonal: source-hash binding is
   needed regardless of which queue is "correct", so future drift (a
   third karr_bootstrap.m variant, a fourth) is caught mechanically.
2. **"Apply the same unconditional metadata write to
   `extract_per_process_traces_v2.m`, not just the dual extractor"** --
   Not done in this task: the task's evidence and hard-rules ("write ...
   into BOTH dual output metadata structs") scope this fix to the dual-tap
   extractor's own outputs. `extract_per_process_traces_v2.m`'s narrower
   `if strcmp(canonical_name, 'DNADamage')` gate is a known, separate
   blind spot for every OTHER process's single-process extraction, left
   as a candidate follow-up, not fixed here (see Revisit Triggers).

## Revisit Triggers

- `extract_per_process_traces_v2.m`'s single-process extractor is ever
  asked to write this metadata unconditionally too (closing its own
  narrower blind spot).
- The live `genuine-l22-cytokinesis` (or any other) queue's worktree is
  updated to include the DNADamage signed-zero overlay commits, at which
  point its own traces would carry matching resolved hashes and could be
  directly compared/reused.
- A same-source isolation probe (this task's item 2) that should show
  byte-identical arrays under matched DNADamage source hashes instead
  shows a real divergence -- would indicate a genuine dual-tap-vs-
  single-process structural bug, not a source confound, and must be
  investigated as such.

## Empirical Foundation

- `git log --oneline -- scripts/matlab/karr_bootstrap.m` (this worktree):
  `f7d4310`/`c2174bb`/`d3e91e8` (overlay) after `b8a27a5` (pre-overlay).
- `git log --oneline -1` in `E:\opencell-worktrees\genuine-l22-cytokinesis`:
  `1f7e758`, whose `karr_bootstrap.m` is unchanged since `b8a27a5`.
- Independently computed SHA-256 (LF-normalized, matching
  `karr_bootstrap.m`'s own algorithm) of the original vs. patched
  DNADamage.m: `6c8cfb07...` vs. `86d8b3c2...` (full hashes above).
- `E:\opencell-worktrees\genuine-l22-cytokinesis\data\m1_sources\karr_native\per_process_traces_v2_event_s036\Cytokinesis_4000ticks.mat`
  metadata inspected directly: no `dnadamage_source_*` keys present at
  all (the pre-fix blind spot), `onset_tick=24046`, `window_anchor=28009`.
- `STATUS_DUAL_CYT_WINDOW_FIX.md` (this repo, corrected in this commit).

## External Review Context

- Opus review (this task) rejected the prior bulk-authorization request
  and identified the exact source confound above, requiring this decision
  and the corrective STATUS/spec/registry rewrite.

## Related Decisions

- None prior specific to full-simulation source provenance; this is the
  first decision file for the DNADamage overlay/source-binding mechanism.

## Provenance

- Drafted in Copilot CLI session, worktree
  `E:\opencell-worktrees\fix-dual-cyt-window`, branch
  `agent/dual-cyt-window-fix-20260904`, base main `f71cfbb`.
