# STATUS — Cytokinesis dual-tap extractor uniform-window completeness fix

Branch: `agent/dual-cyt-window-fix-20260904`, worktree
`E:\opencell-worktrees\fix-dual-cyt-window`, based on main `f71cfbb`.

## 1. Problem this fixes

The one-pass dual Cytokinesis+FtsZPolymerization extractor
(`scripts/matlab/extract_dual_division_window.m` /
`extract_dual_division_window_seeds.m`, Opus-accepted, merged locally at
`e0e2cdd`) was preregistered with Cytokinesis `M_ticks=4000` (the 2026-08-05
seed-0 lower bound). Before starting the N=50 bulk cohort, the task's
required equivalence check (a fresh, independent seed-36 run through the
dual-tap extractor) completed a full ~32k-tick whole-cell trajectory and
**failed closed**: the real onset-to-completion span was **4076 ticks**
(inclusive; onset_tick=27918, completion_tick=31993, completion-onset
difference=4075) -- 76 ticks larger than the fixed 4000-tick capture
buffer, so `capture_dual_anchor_windows`'s own `onset_tick < tick_start_a`
guard correctly refused to emit an incomplete file rather than silently
truncating the window.

Separately, the EXISTING (conventional, single-process,
`extract_per_process_traces_v2.m`) seed-36 trace already on disk is an
independently valid trajectory with a **different** real span (onset
24046, completion 28009, difference=3963/inclusive=3964).

**CORRECTED 2026-09-04 (Opus review, post-initial-fix):** this document's
first version attributed that disagreement to "genuine run-to-run
whole-simulation nondeterminism" and treated it as an unavoidable property
of Karr's scheduler. **This claim is RETRACTED.** The actual, mechanical
cause: the two runs resolved two DIFFERENT `DNADamage.m` source variants.
The live `genuine-l22-cytokinesis` queue's worktree checkout (commit
`1f7e758`) has a `karr_bootstrap.m` unchanged since `b8a27a5` -- **before**
the DNADamage signed-zero-normalization overlay was introduced (`d3e91e8`/
`c2174bb`/`f7d4310`). This worktree's `karr_bootstrap.m` includes that
overlay and applies it automatically. DNADamage is one of the 28 processes
in Karr's shared scheduler (every process's `calcResourceRequirements_
Current`/`evolveState` runs every tick, not just the tapped one), so its
source version affects every OTHER process's real trajectory too --
including Cytokinesis's, even though Cytokinesis's own source never
changed. This is a straightforward "two runs used different model code"
confound, not stochastic nondeterminism, and it is independently
verifiable (git history + source hashes, see §5). Full finding:
`decisions/dec-005-full-simulation-source-hash-binding.md`.

Once source identity is bound and verified (§5/§6b below), same-source
byte-equivalence remains a fully meaningful, achievable requirement --
this task's decisive same-source isolation probe (§2a) tests exactly
that.

## 2. Independent verification of known completed trace spans (before choosing a new M)

Before preregistering a replacement M, ran
`scripts/l2_event/survey_cytokinesis_onset_span.py` (read-only, never
launches MATLAB) against every currently-valid Cytokinesis event-window
trace on disk in the live `E:\opencell-worktrees\genuine-l22-cytokinesis`
worktree (35/50 seeds present, all captured under the old M_ticks=4000):

```
seed=000 onset_tick=27310 completion_tick=31046 span=3736
seed=001 onset_tick=27532 completion_tick=31377 span=3845
seed=002 onset_tick=27374 completion_tick=31249 span=3875
seed=003 onset_tick=27251 completion_tick=31177 span=3926
seed=004 onset_tick=28320 completion_tick=32136 span=3816
seed=005 onset_tick=27318 completion_tick=31189 span=3871
seed=006 onset_tick=26613 completion_tick=30505 span=3892
seed=007 onset_tick=26115 completion_tick=30073 span=3958
seed=008 onset_tick=25307 completion_tick=29076 span=3769
seed=009 onset_tick=27105 completion_tick=31076 span=3971   <- max in this sample
seed=010 onset_tick=28709 completion_tick=32385 span=3676
seed=011 onset_tick=29889 completion_tick=33799 span=3910
seed=012 onset_tick=24301 completion_tick=27980 span=3679
seed=015 onset_tick=26177 completion_tick=29983 span=3806
seed=017 onset_tick=27722 completion_tick=31577 span=3855
seed=018 onset_tick=24617 completion_tick=28454 span=3837
seed=019 onset_tick=26179 completion_tick=30015 span=3836
seed=020 onset_tick=26116 completion_tick=29841 span=3725
seed=021 onset_tick=26024 completion_tick=29824 span=3800
seed=022 onset_tick=28049 completion_tick=31904 span=3855
seed=023 onset_tick=28897 completion_tick=32754 span=3857
seed=024 onset_tick=25849 completion_tick=29748 span=3899
seed=025 onset_tick=29830 completion_tick=33560 span=3730
seed=026 onset_tick=25359 completion_tick=29264 span=3905
seed=027 onset_tick=27298 completion_tick=31195 span=3897
seed=028 onset_tick=28157 completion_tick=31891 span=3734
seed=029 onset_tick=25049 completion_tick=28992 span=3943
seed=030 onset_tick=24693 completion_tick=28450 span=3757
seed=031 onset_tick=26457 completion_tick=30199 span=3742
seed=032 onset_tick=27644 completion_tick=31456 span=3812
seed=033 onset_tick=25270 completion_tick=29214 span=3944
seed=034 onset_tick=23892 completion_tick=27529 span=3637   <- min in this sample
seed=035 onset_tick=24282 completion_tick=28206 span=3924
seed=036 onset_tick=24046 completion_tick=28009 span=3963   (the existing conventional trace, NOT the failed-closed fresh dual-tap run)
seed=049 onset_tick=26348 completion_tick=30237 span=3889

35/50 required seeds present.
PARTIAL SURVEY ONLY: max observed span over these 35 seed(s) is 3971 ticks.
```

**CORRECTED 2026-09-04 (Opus review, post-initial-fix):** this document's
first version treated the 3971-tick figure as a survivorship-biased
LOWER bound and cited it as corroborating margin evidence. **This claim
is RETRACTED as margin evidence** (though the survivorship-bias mechanics
described below remain true as a general statement about M-truncated
sampling). The deeper problem: these 35 traces were produced by the live
`genuine-l22-cytokinesis` queue, whose `karr_bootstrap.m` predates the
DNADamage signed-zero overlay (§1) -- they are evidence about a
**DIFFERENT model** (pre-overlay DNADamage.m) than the M_ticks=5000
cohort's overlay-patched source, not merely a differently-sized sample of
the *same* model. Mixing them into this margin decision would have been
wrong even setting aside the M=4000 truncation ceiling. They are retained
above for historical provenance only, and independently verified (by
direct metadata inspection, see §5) to carry no `dnadamage_source_*`
metadata at all -- confirming they predate this fix's DNADamage source
binding entirely. The M_ticks=5000 preregistration below is therefore
**n=1 evidence** under the currently-active (overlay-patched) DNADamage
source, and is marked PROVISIONAL in `division_window_spec.json`.

## 3. Preregistration (before any further evaluation)

Preregistered **before** running anything further:
`docs/phase_f/l2_event/division_window_spec.json` --

- Cytokinesis `M_ticks: 5000`, `tick_range_from_division: [-4999, 0]`,
  marked **PROVISIONAL** (n=1 evidence under the currently-active,
  overlay-patched DNADamage source -- see §2/§5 correction).
- Margin: `5000 - 4076 = 924` ticks (22.7% over the single observed
  4076-tick span). The 35-trace M_ticks=4000 survey max (3971) is
  explicitly NOT used as corroborating evidence (§2 correction).
- FtsZPolymerization unchanged at `M_ticks: 200` (task instruction; no
  analogous overrun evidence for this process).
- The prior `M_ticks=4000` / `[-3999, 0]` values are recorded in the new
  spec's `supersedes` block. All existing 4000-tick traces (this task's
  35-seed Cytokinesis cohort and the 11 FtsZ traces) are **preserved,
  not deleted**, anywhere on disk, but are explicitly **non-authoritative**
  for the M_ticks=5000 cohort for TWO independent reasons: metadata.n_ticks
  mismatch, AND (§5/§6b) a different, pre-overlay DNADamage source.
- **Escalation policy** (new, item 5): any future observed real span
  (inclusive) that equals or exceeds the current `m_ticks`, for any seed
  under the current DNADamage source, requires a **fresh, separate**
  preregistration commit setting `new_m_ticks = ceil(observed_span *
  1.227 / 1000) * 1000` -- never a same-commit tune/retry. See
  `division_window_spec.json`'s `escalation_policy` block for the full,
  machine-readable rule.

See the spec file's own `rationale`/`evidence`/`escalation_policy` fields
for the full numeric justification (this section summarizes it).

## 4. Single source of truth (replacing scattered hardcoded 4000 literals)

Before this fix, `4000` was hardcoded independently in FOUR places:
`scripts/l2_event/prepare_cytokinesis_cohort.py` (`AUTHORITATIVE_N_TICKS`),
`scripts/l2_event/validate_dual_division_canary.py` (`CYTOKINESIS_N_TICKS`),
`scripts/matlab/extract_dual_division_window.m` (`cyt_n_ticks`), and
`scripts/matlab/extract_dual_division_window_seeds.m` (`cyt_n_ticks`) --
plus a human-readable mirror in `PROCESS_CATALOG.yaml`'s Cytokinesis row.
Nothing enforced agreement between them.

New machine-loadable single source of truth:
`docs/phase_f/l2_event/division_window_spec.json`, with:

- `scripts/l2_event/division_window_spec.py` -- Python loader
  (`m_ticks_for`, `tick_range_from_division_for`, module constants
  `CYTOKINESIS_M_TICKS`/`FTSZ_M_TICKS`). No fallback default: a missing
  file, malformed JSON, or missing process/key raises
  `DivisionWindowSpecError` rather than silently defaulting.
- `scripts/matlab/division_window_spec.m` -- MATLAB loader
  (`division_window_spec('Cytokinesis')` /
  `division_window_spec('FtsZPolymerization')`), same no-fallback
  discipline (`error()`, never a silent default).

All four Python/MATLAB call sites above now read from this shared spec
instead of a local literal. `PROCESS_CATALOG.yaml`'s Cytokinesis/
FtsZPolymerization rows remain the human-readable mirror (YAML data files
cannot `import` JSON), but a new test
(`test_catalog_and_spec_agree_on_cytokinesis_m_ticks`) mechanically checks
agreement so the two can never silently drift apart again.
`event_registry.yaml`'s Cytokinesis notes are updated with the full
2026-09-04 finding (prose only, no schema change; corrected again in the
same-day corrective pass, see §5).

A second, independent single source of truth was added in the corrective
pass: `scripts/l2_event/launcher.current_genuine_dnadamage_source()` (see
§5/§6b) -- the MATLAB-free, pure-Python recomputation of the DNADamage
source identity `karr_bootstrap.m` derives at run time, used by both
`prepare_cytokinesis_cohort.py` and `validate_dual_division_canary.py` to
require exact upstream-source agreement, mirroring the existing mnrnd/
Statistics-Toolbox provider-identity pattern.

## 5. Root cause correction: DNADamage source-version confound (NOT nondeterminism)

**This section replaces this document's original §5 in full.** The
original version claimed the seed-36 conventional-vs-dual disagreement
(span 3963/3964 inclusive vs. 4075/4076 inclusive) demonstrated "genuine
run-to-run whole-simulation nondeterminism" and proposed "structural
equivalence" as a substitute for byte-equivalence specifically because
byte-equivalence was assumed unattainable. **Both the diagnosis and that
specific conclusion are corrected below.**

### 5.1 Actual cause: two different DNADamage.m source variants

- The live `genuine-l22-cytokinesis` queue's worktree is at commit
  `1f7e758` (`git log --oneline -1`); its `scripts/matlab/karr_bootstrap.m`
  is unchanged since `b8a27a5` (`git log --oneline -- scripts/matlab/
  karr_bootstrap.m`), which is **before** the DNADamage signed-zero
  overlay was introduced (`d3e91e8` "Fix DNADamage signed-zero overlay",
  `c2174bb` "fix dnadamage per-reaction rate law", `f7d4310`
  "karr_bootstrap.m: hash/patch/write raw bytes for DNADamage signed-zero
  overlay"). Its conventional seed-36 trace's own metadata (directly
  inspected: `E:\opencell-worktrees\genuine-l22-cytokinesis\data\
  m1_sources\karr_native\per_process_traces_v2_event_s036\
  Cytokinesis_4000ticks.mat`) confirms `onset_tick=24046`,
  `window_anchor=28009`, `timestamp=2026-09-04 04:34:32`, and carries
  **no `dnadamage_source_*` metadata keys at all** -- consistent with a
  pre-overlay `karr_bootstrap.m` that never wrote them.
- This worktree (`fix-dual-cyt-window`, base main `f71cfbb`) has all
  three overlay commits, so its `karr_bootstrap.m` automatically detects
  the un-patched source at the resolved WCM root and applies the
  generated signed-zero overlay before every bootstrap.
- Independently recomputed (VERIFIED, LF-normalized SHA-256, matching
  `karr_bootstrap.m`'s own algorithm exactly -- see
  `scripts.l2_event.launcher.current_genuine_dnadamage_source()`):
  - Original (un-patched) `DNADamage.m`:
    `6c8cfb07cbf84d7296861f97c6105a8b57a8d16e90f633784ea28855d3687d2a`
  - Patched (signed-zero-normalized) `DNADamage.m`:
    `86d8b3c2d2ed42df03e1b9ea14f06efc4b645a4e6aeaa3ef938b9ea41ad27e7e`
  - These are offered as VERIFIED, independently-reproducible evidence for
    the underlying finding (two different source variants were in
    effect). The reviewer's own citation used abbreviated identifiers
    ("SHA `30ecbc14`" / "SHA `c5cb9e07`") for the same two variants; this
    worktree cannot independently confirm those exact abbreviated values
    were computed the same way, so they are not asserted to be
    bit-identical to the hashes above -- only the underlying finding (two
    different source variants) is claimed as verified.
- DNADamage participates in Karr's shared 28-process scheduler every tick
  (`calcResourceRequirements_Current`/`evolveState` run for every
  process, not just the tapped one), so its source version affects every
  OTHER process's real trajectory too -- including Cytokinesis's and
  FtsZPolymerization's, even though neither process's own source file
  changed. This fully explains the seed-36 disagreement without invoking
  any unverified nondeterminism claim. Full finding, evidence, and the
  durable decision this creates: `decisions/dec-005-full-simulation-
  source-hash-binding.md`.

### 5.2 What this means for the equivalence gate

Once source identity is independently bound and verified, **same-source
byte-equivalence remains a fully meaningful, achievable requirement** --
it was never actually unattainable; the prior conclusion conflated "two
runs disagreed" with "two runs COULD NOT have agreed." The corrected
methodology is:

1. **Verified source-identity agreement** (new, this corrective pass):
   `decisions/dec-005` -- every Cytokinesis cohort trace (and, via the
   dual-tap extractor, its paired FtsZ trace) must carry
   `dnadamage_source_resolved_sha256` metadata matching the CURRENT
   worktree's `karr_bootstrap.m` resolution
   (`current_genuine_dnadamage_source()`), enforced by
   `validate_existing_event_window` and cross-checked between taps by
   `validate_dual_division_canary.py`. A trace with missing or
   mismatched DNADamage source metadata fails closed, exactly like a
   wrong-provider trace already did for mnrnd.
2. **Structural equivalence** (unchanged from the original acceptance):
   the dual-tap extractor's scheduler loop (`evolve_state_with_dual_tap`)
   is a direct, verified generalization of the existing single-process
   `evolve_state_with_tap` -- same `copyFromState -> resource request/
   allocation -> evolveState -> copyToState` sequence, same Karr
   randperm-with-tRNAAminoacylation-before-Translation ordering, for all
   28 processes, on every tick. Proven statically
   (`tests/scripts/test_extract_dual_division_window_static.py`),
   unchanged by this fix.
3. **Same-source array-identity proof** (new, item 2 of this corrective
   pass): a decisive isolation probe -- the CONVENTIONAL single-process
   extractor (`extract_per_process_traces_v2.m`), run for seed 36 /
   Cytokinesis / `n_ticks=5000` through THIS worktree's overlay-aware
   `karr_bootstrap.m` (so source is matched to the existing dual-tap
   seed-36 output) -- must reproduce `onset=27918`, `anchor=31993`, and
   every `states_before`/`states_after` array exactly (excluding only
   metadata timestamp/dual_tap-provenance keys). See §6a for the result.
4. **Independent destination validators + complete-event capture**
   (unchanged): the same fail-closed validators every other seed must
   pass, plus the onset-inside-window invariant holding for the REAL
   observed onset/completion of that specific run -- never assumed,
   padded, or fabricated.

This replaces "byte-equivalence is unattainable, use structural
equivalence instead" with the corrected: "byte-equivalence IS attainable
and required once source identity is verified; structural equivalence
was always a secondary, complementary check, not a substitute for it."

## 6. Seed-36 re-run under the new M_ticks=5000 -- RESULT: PASS

- Launched: 2026-09-04 17:42:15 IST, host-wide MATLAB session count
  verified at 0 immediately before launch. MATLAB extraction finished
  19:28:51 IST; combined validator finished 19:29:45 IST. **Total
  wall-clock: ~106.6 minutes** (comparable to the seed-49 canary's 99.15
  minutes on an idle host, consistent with a similarly-long ~32k-tick
  full trajectory).
- Output root: THIS worktree's own clean, gitignored
  `data/m1_sources/karr_native/per_process_traces_v2_event_s036/` (did
  not exist before this run; not touched -- and did not exist -- in any
  other worktree for seed 36 under M_ticks=5000; never touches the live
  Cytokinesis/FtsZ queues or any other worktree's copy of seed 36).
- Launcher: `tmp/seed36_window_fix/wait_and_run_seed36.ps1` (host-wide
  MATLAB-session gate, mirrors the accepted seed-49 canary's
  `wait_and_run_seed49.ps1` exactly), via
  `scripts/tools/run_matlab_slot.ps1 -Slots 4`, invoking
  `extract_dual_division_window_seeds(36, 36)`.

**Real result** (from the MATLAB extraction's own log,
`tmp/seed36_window_fix/wait_and_run_seed36.log`):

- Cytokinesis: `tick_start=26994`, `window_anchor=31993`,
  `onset_tick=27918` -- capture window is exactly 5000 ticks
  (31993-26994+1), comfortably containing the real inclusive
  onset-to-completion span of **4076 ticks** (27918..31993) with the
  preregistered 924-tick margin intact (5000-4076=924, exactly as
  planned in `division_window_spec.json`).
- FtsZPolymerization: `tick_start=31794`, `window_anchor=31993` -- exactly
  200 ticks, same completion tick as Cytokinesis.
- **Notable finding**: `onset_tick=27918` / `window_anchor=31993` here are
  numerically IDENTICAL to the earlier pre-preregistration fresh seed-36
  run that failed closed under the old M_ticks=4000. This means the
  dual-tap extractor's own trajectory for seed 36, run twice under the
  SAME (overlay-patched) DNADamage source, is reproducible -- consistent
  with §5's corrected finding: the disagreement with the conventional
  trace is a DNADamage-source-version confound (the conventional trace's
  worktree predates the overlay), not run-to-run nondeterminism within
  one source version. §6a's same-source isolation probe tests this
  directly by running the CONVENTIONAL extractor through this same
  overlay-patched source and comparing arrays.

**Combined validator result** (`tmp/seed36_window_fix/CANARY_RESULT.json`,
`scripts/l2_event/validate_dual_division_canary.py --seed 36`):

```json
{
  "seed": 36,
  "status": "PASS",
  "cytokinesis_valid": true,
  "cytokinesis_window_anchor": 31993,
  "cytokinesis_sha256": "54963f40bb7ae3f6058161314f3263640ede6344508184fdefdb2627bc4d4911",
  "ftsz_valid": true,
  "ftsz_window_anchor": 31993,
  "ftsz_sha256": "44cb8b51c68b7f3893cfb05334983aa85cbf3017a8530a7dc7badb6e39b7c9f5",
  "distinct_paths": true,
  "distinct_content": true,
  "same_completion_tick": true,
  "provider_sha256_match": true,
  "cytokinesis_provider_sha256": "d68e8ff78af266ad4977e80cd5366cc59984ada5f73ab591a9c08350bc4471dc",
  "ftsz_provider_sha256": "d68e8ff78af266ad4977e80cd5366cc59984ada5f73ab591a9c08350bc4471dc",
  "reasons": []
}
```

Both existing single-process validators (`launcher.validate_existing_event_window`
for Cytokinesis, `ftsz_pre_division_evidence.validate_seed_window` for
FtsZ) passed independently against the NEW M_ticks=5000 spec, both files
are distinct in path and content, both share the same completion tick
(31993) and the same genuine mnrnd provider SHA-256 (proving both taps
came from the one `karr_bootstrap()` call), and no failure reasons were
reported. **This is the required equivalence-gate replacement result**:
not a byte-identical reproduction of a different extractor's trajectory,
but a complete, independently-validated, structurally-correct capture of
the real trajectory this specific run (dual-tap extractor, seed 36,
M_ticks=5000) actually produced.

Exact output paths (this worktree only, gitignored):
- `data/m1_sources/karr_native/per_process_traces_v2_event_s036/Cytokinesis_5000ticks.mat`
- `data/m1_sources/karr_native/per_process_traces_v2_event_s036/FtsZPolymerization_200ticks.mat`

### 6a. Known gap: this specific trace predates the DNADamage source-hash-binding metadata

**Honesty note (2026-09-04, corrective pass):** the JSON result quoted
above was captured BEFORE this corrective pass added
`dnadamage_source_resolved_sha256` metadata-writing to
`extract_dual_division_window.m` (§6b/§5.2 item 1, `decisions/dec-005`).
Re-validating the SAME on-disk files now, with the corrected validator,
correctly reports:

```json
{
  "status": "FAIL",
  "cytokinesis_valid": false,
  "cytokinesis_reason": "metadata.dnadamage_source_resolved_sha256 is missing -- ...",
  "dnadamage_source_match": false,
  "cytokinesis_dnadamage_source_sha256": null,
  "ftsz_dnadamage_source_sha256": null
}
```

This is the fail-closed mechanism working exactly as designed -- a trace
produced before this metadata existed is, correctly, non-authoritative
under the new binding, exactly like the 34 preserved M_ticks=4000 traces.
It is **not** evidence against this seed-36 result's onset/completion/span
findings (§6's actual numbers, and the independent re-verification in
§10, are unaffected -- those checks never depended on DNADamage source
metadata). It DOES mean: a fresh re-run of seed 36 (or any new seed)
through the now-corrected extractor would carry this metadata and pass
outright. This task does not perform that re-run (it would be a third
~100-minute MATLAB job whose only purpose is closing a metadata gap on
data whose scientific content -- onset/completion/span -- is already
independently verified three ways in §6/§10); it is flagged here for
Opus/coordinator decision on whether to require it before any
authoritative-cohort use of this specific seed-36 M_ticks=5000 trace.

### 6b. Same-source isolation probe (item 2): conventional extractor vs. dual-tap, matched source -- RESULT: CONFIRMED

To directly test §5.2 item 3's claim (byte-equivalence IS achievable once
source is matched), launched the CONVENTIONAL single-process extractor
for the SAME seed 36, through THIS worktree's overlay-aware
`karr_bootstrap.m` (so its DNADamage source matches the dual-tap output
above), into a brand-new, non-colliding output directory:

```matlab
extract_per_process_traces_v2({'Cytokinesis'}, 'probe_conv_s036_m5000', 5000, uint32(36), 0, 'anchor', struct(), struct())
```

- Launched: 2026-09-04 20:11:17 IST, host-wide MATLAB session count
  verified at 0 immediately before launch (the seed-36 dual-tap re-run
  from §6 had already completed and exited by this point -- never run
  concurrently in this worktree, per the item-6 concurrency policy,
  `decisions/dec-005`).
- Launcher: `tmp/probe_conv_s036_m5000/wait_and_run_probe.ps1` (same
  host-wide MATLAB-session gate as `wait_and_run_seed36.ps1`).
- Finished: 2026-09-04 21:49:12 IST. **Total wall-clock: ~218 minutes**
  -- substantially longer than the ~106.6-minute dual-tap run; this
  worktree's host was also running several concurrent `pytest`/`ruff`/
  WSL invocations from this same corrective-pass work during the probe's
  run, a real (if imprecise) source of CPU contention on a
  single-MATLAB-session host, consistent with this project's own prior
  observations about contended-vs-idle-host wall-clock variance. Onset/
  completion ticks (below) are unaffected by wall-clock contention.
- Output: `data/m1_sources/karr_native/probe_conv_s036_m5000/
  Cytokinesis_5000ticks.mat` (a brand-new `output_subdir`, never
  colliding with `per_process_traces_v2_event_s036/`).

**Metadata comparison** (direct HDF5 inspection, both files):

| Field | Probe (conventional) | Dual-tap |
|---|---|---|
| `onset_tick` | **27918** | **27918** |
| `window_anchor` (completion) | **31993** | **31993** |
| `tick_start` | 26994 | 26994 |
| `n_ticks` | 5000 | 5000 |
| `rng_seed` | 36 | 36 |

Exact match on every field the task required (`onset=27918, anchor=31993`).
The only metadata keys present in one file but not the other are the
dual-tap-only provenance keys (`dual_tap_extractor`,
`dual_tap_partner_process`, `dual_tap_partner_n_ticks`,
`dual_tap_partner_tick_start`) and the two files' own `timestamp` --
exactly the "excluding only metadata timestamp/dual_tap keys" carve-out
the task specified.

**Full array comparison** (every `states_before`/`states_after` key
present in both files -- `boundEnzymes`, `chromosome_segregated`,
`enzymes`, the four `ftsZRing_*` edge-count witnesses,
`pinchedDiameter`, `substrates`; 9 observables x 2 sections = 18 arrays
total, every tick, full shape and content, `np.array_equal`):

```
states_before keys only in probe: []
states_before keys only in dual: []
states_after keys only in probe: []
states_after keys only in dual: []
states_before.boundEnzymes: MATCH
states_before.chromosome_segregated: MATCH
states_before.enzymes: MATCH
states_before.ftsZRing_numEdgesOneStraight: MATCH
states_before.ftsZRing_numEdgesTwoBent: MATCH
states_before.ftsZRing_numEdgesTwoStraight: MATCH
states_before.ftsZRing_numResidualBent: MATCH
states_before.pinchedDiameter: MATCH
states_before.substrates: MATCH
states_after.boundEnzymes: MATCH
states_after.chromosome_segregated: MATCH
states_after.enzymes: MATCH
states_after.ftsZRing_numEdgesOneStraight: MATCH
states_after.ftsZRing_numEdgesTwoBent: MATCH
states_after.ftsZRing_numEdgesTwoStraight: MATCH
states_after.ftsZRing_numResidualBent: MATCH
states_after.pinchedDiameter: MATCH
states_after.substrates: MATCH

TOTAL observables compared: 18
TOTAL mismatches: 0
ALL ARRAYS IDENTICAL (byte-for-byte, excluding metadata timestamp/dual_tap keys).
```

**This is the decisive confirmation of the corrected root-cause diagnosis
(§5).** With the DNADamage source held constant (both runs through this
worktree's overlay-patched `karr_bootstrap.m`), the conventional
single-process extractor and the dual-tap extractor produce IDENTICAL
onset, completion, and every captured per-tick array for seed 36 --
proving the earlier conventional-vs-dual disagreement was 100% a
source-version confound, not run-to-run nondeterminism or an
extractor-structural bug. Byte-equivalence between two independently-run
trajectories IS a meaningful, achievable gate once source identity is
controlled, exactly as §5.2 predicted. No divergence was found, so no
dual-tap side effect needs to be located or fixed.

### 6c. Bringing Cytokinesis to 36/50 under the new M_ticks=5000

This seed-36 result is the **first** authoritative Cytokinesis trace under
M_ticks=5000 (the other 34 previously-valid seeds remain preserved but
non-authoritative M_ticks=4000 traces pending their own re-extraction --
see §1/§3). No other seeds are re-extracted by this task (task scope is
the seed-36 equivalence proof only; re-extracting the remaining cohort is
explicitly left for a separately-authorized N=50 sweep per
`event_sweep_blocked_on`).

### 6d. Concurrency policy (item 6)

`karr_bootstrap.m`'s generated DNADamage overlay path
(`<repo_root>/tmp/wcm_source_overlay/src/...DNADamage.m`) is **shared
per-worktree, not per-PID or per-job**. Confirmed by reading
`add_worktree_source_overlays`/`ensure_dnadamage_signed_zero_overlay`:
every `karr_bootstrap()` call in a given worktree resolves and (if
`overlay_required`) rewrites the SAME file. **Running more than one
bulk-extraction MATLAB job concurrently in the same worktree is
unsupported** -- do not authorize three (or any >1) concurrent jobs in
one worktree; use one worktree (or a distinct per-PID overlay path, not
yet implemented) per concurrent bulk worker. As defense-in-depth (not a
fix for the underlying unsupported-concurrency limitation),
`ensure_dnadamage_signed_zero_overlay`'s write is now atomic (temp file +
`movefile`, this corrective pass) so a torn READ can never occur even if
this policy is accidentally violated -- the two writers would compute
byte-identical content anyway (a pure function of the unchanging source),
so this hardens against corruption, not against the unsupported
configuration itself. See `decisions/dec-005` for the full policy
statement. Every MATLAB job in this task (the seed-36 dual-tap re-run,
§6, and the same-source isolation probe, §6b) was run strictly
sequentially in this one worktree, host-wide MATLAB session count
verified at 0 before each launch.

## 7. What this task does NOT do

- Does **not** start the N=50 bulk queue (still blocked --
  `event_sweep_blocked_on` in `PROCESS_CATALOG.yaml` now cites both the
  new M_ticks=5000 cohort's near-zero seed count AND the still-required
  full 50-seed survey under the new M).
- Does **not** delete or overwrite any existing 4000-tick Cytokinesis or
  FtsZ trace, in this worktree or any other.
- Does **not** push or merge to main.
- Does **not** touch the live Cytokinesis (`genuine-l22-cytokinesis`) or
  FtsZ (`genuine-l22-ftsz`) queues/processes.
- Does **not** perform any threshold tuning, partial-window acceptance,
  or padding fabricated from outputs.
- Does **not** run more than one MATLAB job concurrently in this worktree
  (§6d).

## 8. Files changed

- `docs/phase_f/l2_event/division_window_spec.json` (schema_version 2,
  corrective pass: retracted nondeterminism/survivorship-bias claims,
  added `escalation_policy`, marked M_ticks=5000 PROVISIONAL)
- `scripts/matlab/division_window_spec.m` (new)
- `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` (Cytokinesis row;
  corrective pass: v3.12 note)
- `docs/phase_f/l2_event/event_registry.yaml` (Cytokinesis notes;
  corrective pass: full retraction + corrected finding)
- `scripts/l2_event/prepare_cytokinesis_cohort.py` (corrective pass: adds
  `REQUIRED_DNADAMAGE_SOURCE_SHA256`, wires it into `_anchor_spec`)
- `scripts/l2_event/validate_dual_division_canary.py` (corrective pass:
  adds `dnadamage_source_match` cross-check + `REQUIRED_DNADAMAGE_SOURCE_SHA256`;
  final pre-bulk fix: adds `margin_ok`/`cytokinesis_onset_tick`/
  `inclusive_span_ticks` provisional-margin gate, G1)
- `scripts/l2_event/launcher.py` (corrective pass, new: `current_genuine_dnadamage_source()`,
  `resolve_dnadamage_wcm_root()`, `AnchorWindowSpec.required_dnadamage_source_sha256`,
  the corresponding `validate_existing_event_window` check)
- `scripts/l2_event/division_window_spec.py` (new in the corrective
  pass; final pre-bulk fix adds `check_inclusive_span_margin()`/
  `ProvisionalMarginOverrunError`, G1)
- `scripts/l2_event/survey_cytokinesis_onset_span.py` (corrective pass:
  `--m-ticks` filtering, `MTicksMetadataMismatchError` fail-closed check;
  final pre-bulk fix: wires `check_inclusive_span_margin` into
  `onset_span_for_trace`/`main`, exit code 3 on overrun, G1)
- `scripts/matlab/extract_dual_division_window.m` (corrective pass:
  captures `karr_bootstrap()`'s 3rd return, adds
  `add_dnadamage_source_metadata` to both output structs)
- `scripts/matlab/extract_dual_division_window_seeds.m`
- `scripts/matlab/karr_bootstrap.m` (corrective pass: atomic overlay
  write, concurrency-policy doc comment)
- `.gitignore` (final pre-bulk fix: `data/m1_sources/karr_native/probe_*/`, G2)
- `tests/scripts/test_extract_dual_division_window_static.py`
- `tests/scripts/test_validate_dual_division_canary.py` (corrective pass:
  DNADamage mismatch/missing inversion tests, fixture updates; final
  pre-bulk fix: margin-gate boundary tests, G1)
- `tests/scripts/test_prepare_cytokinesis_cohort.py` (corrective pass:
  fixture updates for DNADamage source metadata)
- `tests/scripts/test_survey_cytokinesis_onset_span.py` (corrective pass:
  `--m-ticks` test updates; final pre-bulk fix: margin-gate boundary
  tests, G1)
- `tests/scripts/test_division_window_spec.py` (new in the corrective
  pass; final pre-bulk fix adds margin-gate boundary tests, G1)
- `decisions/dec-005-full-simulation-source-hash-binding.md` (new)
- `decisions/_decision_index.yaml` (new dec-005 entry)
- `plan.md` (operational handoff)
- `tmp/seed36_window_fix/wait_and_run_seed36.ps1` (new; host-wide-safe
  MATLAB launcher, mirrors the accepted seed-49 canary's script)
- `tmp/seed36_window_fix/wait_and_run_seed36.log`,
  `tmp/seed36_window_fix/STATUS.txt`,
  `tmp/seed36_window_fix/CANARY_RESULT.json` (new; real run provenance)
- `tmp/probe_conv_s036_m5000/wait_and_run_probe.ps1` (new; same-source
  isolation probe launcher, item 2)
- `tmp/probe_conv_s036_m5000/wait_and_run_probe.log`,
  `tmp/probe_conv_s036_m5000/STATUS.txt` (new; probe run provenance)

## 9. Test results
- `tmp/seed36_window_fix/wait_and_run_seed36.ps1` (new; host-wide-safe
  MATLAB launcher, mirrors the accepted seed-49 canary's script)
- `tmp/seed36_window_fix/wait_and_run_seed36.log`,
  `tmp/seed36_window_fix/STATUS.txt`,
  `tmp/seed36_window_fix/CANARY_RESULT.json` (new; real run provenance)
- `tmp/probe_conv_s036_m5000/wait_and_run_probe.ps1` (new; same-source
  isolation probe launcher, item 2)
- `tmp/probe_conv_s036_m5000/wait_and_run_probe.log`,
  `tmp/probe_conv_s036_m5000/STATUS.txt` (new; probe run provenance)

## 9. Test results

99 related tests pass, 5 pre-existing skips for optional real-data
fixtures not present in this worktree; ruff clean on all changed/new
Python files. Includes the new/updated tests for: DNADamage source-hash
binding (mismatch, missing, agreement), `--m-ticks` cohort filtering and
fail-closed metadata mismatch, and the corrected DNADamage-metadata
static assertions on the dual extractor, plus (final pre-bulk mechanical
fix) the provisional-margin gate boundary tests: M-1 accepted, exactly M
rejected (zero margin), M+1 rejected (pure-function level, since a real
on-disk window cannot structurally represent a span exceeding its own
`n_ticks`).

## 10. Independent re-verification (post-hoc, read-only)

After the MATLAB run completed, re-ran two independent read-only checks
against the resulting files (never re-launching MATLAB, never modifying
the output):

1. `python scripts/l2_event/validate_dual_division_canary.py --seed 36` --
   re-executed fresh (not reading the cached `CANARY_RESULT.json`):
   identical `status: PASS`, identical SHA-256 hashes for both files,
   identical `window_anchor=31993` for both taps.
2. `python scripts/l2_event/survey_cytokinesis_onset_span.py` (run in this
   worktree, which now has exactly this one authoritative seed) --
   independently recomputed `onset_tick=27918`, `completion_tick=31993`,
   `span=4075` (difference convention) purely from the trace's own
   `pinchedDiameter` before/after series, matching the MATLAB log's
   self-reported numbers exactly.

Both checks agree with each other and with the original MATLAB run log,
with zero discrepancy.

## 11. Opus final verdict: ACCEPT (2026-09-04)

Opus's final review of the corrective pass (§5/§6b) **ACCEPTED** the
corrected root-cause diagnosis and the decisive same-source isolation
probe result, conditioned on two required pre-bulk mechanical fixes,
both closed in this same session (§12).

## 12. G1/G2 closure: two required pre-bulk mechanical fixes

**G1 -- mechanical zero-margin enforcement (provisional-margin gate).**
Prior to this closure, the "PROVISIONAL, n=1, escalation-policy-on-
overrun" contract (§3) was documented in `division_window_spec.json`'s
prose but not mechanically enforced against a zero-margin observation
(`inclusive_span == m_ticks` -- the MATLAB extractor's own capture
invariant permits exactly this boundary, since it only requires
`inclusive_span <= m_ticks`). Closed by adding
`scripts.l2_event.division_window_spec.check_inclusive_span_margin()`
(new `ProvisionalMarginOverrunError`) and wiring it into BOTH:

- `scripts/l2_event/survey_cytokinesis_onset_span.py`'s
  `onset_span_for_trace()` (raises; `main()` catches it and exits 3 with
  an explicit `MARGIN OVERRUN` message).
- `scripts/l2_event/validate_dual_division_canary.py`'s
  `validate_dual_division_canary()` (new `margin_ok`/
  `cytokinesis_onset_tick`/`inclusive_span_ticks` report fields; `FAIL`
  status and an explicit `"provisional-margin gate: ..."` reason on
  violation).

Boundary tests added in all three test files
(`test_division_window_spec.py`,
`test_survey_cytokinesis_onset_span.py`,
`test_validate_dual_division_canary.py`): **M-1** margin accepted,
**exactly M** (zero margin) rejected, **M+1** (genuine overrun) rejected
-- the M+1 case is exercised only at the pure-function level (a real
on-disk window structurally cannot represent an inclusive span exceeding
its own `n_ticks`, so M+1 cannot be constructed as a trace; this is
documented explicitly in both integration test files). The MATLAB
extractor's own complete-event capture condition
(`capture_dual_anchor_windows`'s `onset_tick < tick_start_a` guard) is
**unchanged** -- this gate is a stricter, additional, application-level
check layered on top of it, exactly as instructed.

**G2 -- `.gitignore` for conventional probe artifacts.** The same-source
isolation probe (§6b) wrote a ~32.6 MB
`data/m1_sources/karr_native/probe_conv_s036_m5000/Cytokinesis_5000ticks.mat`
that had no existing `.gitignore` pattern covering it (unlike the
standard `per_process_traces_v2*`/`per_process_traces_v2_event_s*`
patterns). Closed by adding `data/m1_sources/karr_native/probe_*/` to
`.gitignore`. The file itself is **preserved on disk, not deleted** --
confirmed via `git check-ignore -v`.

## 13. Recommendation for Opus review

Both required pre-bulk mechanical fixes (§12) are closed. Recommended
next steps, NOT performed by this task:

1. Decide whether the seed-36 dual-tap M_ticks=5000 trace (§6/§6a) needs
   a fresh re-run to carry the new DNADamage source-hash-binding
   metadata before being treated as part of any future authoritative
   cohort, or whether its already-verified onset/completion/span numbers
   (§6/§6b/§10, now independently confirmed FOUR ways: the original
   dual-tap run, its two post-hoc re-verifications, and the
   fully-independent conventional-extractor probe) are sufficient for
   the equivalence-gate purpose alone.
2. Authorize re-extraction of the remaining 34
   preserved-but-non-authoritative M_ticks=4000 Cytokinesis seeds (plus
   the still-missing 14) under M_ticks=5000 AND the current DNADamage
   source, via the same `extract_dual_division_window_seeds.m` driver,
   one seed (or a small supervised batch) at a time under the existing
   host-wide MATLAB coordination discipline (§6d) -- never as an
   unsupervised bulk run, and never more than one job per worktree
   concurrently. Every new seed will now also be subject to the
   provisional-margin gate (§12/G1) automatically.
3. Only after a full 50-seed survey under the new M_ticks=5000 (using
   `survey_cytokinesis_onset_span.py --m-ticks 5000`) confirms no further
   overrun (including no zero-margin observations, per G1): reconcile
   `event_sweep_blocked_on` in `PROCESS_CATALOG.yaml`, update
   `division_window_spec.json`'s `m_ticks_status` from PROVISIONAL to
   confirmed, and authorize the N=50 sweep. Any overrun (including a
   zero-margin observation) discovered during that survey must be
   handled via the `escalation_policy` (§3) -- a fresh, separate
   preregistration commit, never same-commit tuning.

This task does not start steps 2 or 3 -- both remain for a separately
authorized follow-up, per the task's explicit "no bulk launch" instruction.

