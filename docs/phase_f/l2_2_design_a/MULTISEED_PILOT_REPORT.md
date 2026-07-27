# L2.2 Bounded Multi-Seed Karr Oracle Pilot — Manifest &amp; Report

**Status:** pilot complete, evidence committed. Full 50-seed × 22-process production
extraction has **not** been started (explicit non-goal of this pass).

**Branch:** `agent/l22-multiseed` (worktree `E:\opencell-worktrees\l22-multiseed`)
**Companion machine-readable manifest:** [`multiseed_pilot_manifest.json`](./multiseed_pilot_manifest.json)
(sha256 + structural-validity + non-vacuity + loader-compatibility per file; regenerate with
`bin\oc-py scripts/verify_multiseed_pilot.py`).

## 1. Why this pilot exists

Local inventory audit (per source-selection discipline in
`.github/copilot-instructions.md`) found:

- `data/m1_sources/karr_native/per_process_traces_v2/` — 28 canonical **seed-0**
  traces (one per in-scope process), the primary Karr oracle per
  `TRAPS.md` (`per_process_traces_v2` is ground truth, not `phase_f_*`,
  not `ensembles/`, not `karr_archive/`).
- `data/m1_sources/karr_native/per_process_traces_v2_s001/` — only 2 files
  (`DNASupercoiling`, `Translation`) in the canonical repo (`E:\opencell`);
  the worktree itself only had 1 (`Translation`, committed accidentally in
  `45c67165` alongside the seed-parameter feature commit — the only MAT blob
  ever tracked in git for this subtree).
- `data/m1_sources/karr_native/ensembles/{transcription,translation}/` — two
  **specialized** 50-seed ensembles already exist (a separate extractor,
  `extract_transcription_ensemble.m` / `extract_translation_ensemble.m`), used
  in the historical 62-minute full-scale gate run noted in `TRAPS.md`.
- The Design-A runner (`tests/vivarium/l2_2_design_a_runner.py` +
  `_l2_2_design_a_runner_helpers.py`) therefore had, for every process **except**
  Transcription/Translation, at most one usable seed → `load_karr_oracle`
  fell back to a legacy single-seed `.npz` (`KARR_LEGACY_SINGLE_SEED_FALLBACK`)
  or a single `_s00N` file (`canonical_seed_count == 1`), and any Design-A run
  requesting >1 OC seed emitted `KARR_SINGLE_SEED_REUSED`. No genuine
  distributional (multi-seed) L2.2 verdict was possible for those processes.

## 2. The loader gap (root cause), precisely

`_l2_2_design_a_runner_helpers._v2_seed_mat_path()` only looks for
`per_process_traces_v2_s{seed:03d}/<Process>_100ticks.mat` (seed-padded
directories). The 28 canonical seed-0 files live in the **unsuffixed**
`per_process_traces_v2/` directory — a different, non-seed-padded name — so
`_load_v2_ensemble()` (which scans `s000..s049`) **never sees seed 0 at all**
for any process, regardless of how many higher seeds are later extracted.
This is confirmed directly by the existing unit test
`test_l2_2_design_a_ensemble_loader.py::test_load_v2_ensemble_loads_single_seed`,
which writes its synthetic fixture to `per_process_traces_v2_s000/`, not
`per_process_traces_v2/`.

We did **not** patch this generically (see §6.1 for why): a blanket fix would
change `canonical_seed_count` for many of the 22 in-scope processes at once,
which is exactly the kind of systemic verdict-affecting change this task's
non-goals prohibit. Instead, for the 3 pilot processes only, we materialized
seed 0 under the seed-padded name the loader already expects — see §4.

## 3. Pre-registered pilot design

| Axis | Choice | Rationale |
|---|---|---|
| Seeds | `{0, 1}` | Smallest set that proves seed-to-seed independence; matches the seed semantics already implemented in `extract_per_process_traces_v2.m` (`seed_simulation` → `applyOptions('seed', ...)` + `seedRandStream()`). |
| Processes | `Transcription`, `RNADecay`, `ProteinDecay` | All three are flagship **stochastic** processes named in the historical full-scale gate run (`TRAPS.md`, Day-20 2026-06-06: "50 seeds × 100 ticks × B=1000 for Transcription/Translation/RNADecay/ProteinDecay"). RNADecay and ProteinDecay have **no** specialized ensemble (`ensembles/` only has `transcription/` and `translation/`), so they are the two processes where this pilot's data is what the loader actually dispatches to — a genuine, checkable end-to-end change. Transcription is included as a third representative class (RNA synthesis, chromosome-bearing snapshot) specifically to prove the pipeline **does not disturb** a process that already has a richer, unrelated oracle (the 50-seed specialized ensemble must keep winning). |
| Excluded: Translation | — | Already covered by the 50-seed specialized ensemble (wins over any 2-seed v2 addition); also the pre-existing committed `per_process_traces_v2_s001/Translation_100ticks.mat` (2026-06-05) has an **older, narrower** snapshot-property schema (`substrates, enzymes, boundEnzymes, monomers`) than what the *current* extractor produces for Translation (`+ mRNAs, freeTRNAs, aminoacylatedTRNAs, freeTMRNA, boundTMRNA, aminoacylatedTMRNA`). Materializing a fresh seed-0 Translation file alongside the old seed-1 file triggers `_load_seeded_mat_channels`'s schema-drift `ValueError` ("Observable schema drift across ensemble seeds"). We deliberately left Translation's existing (working, shadowed-by-ensemble) state untouched rather than resolve this drift as a side effect of an unrelated pilot — see §6.2. |
| Ticks | 100 (n_ticks=100, tick_offset=0) | Matches the existing canonical/legacy fixtures exactly; no new tick-window semantics introduced. |
| Extractor | Unmodified `scripts/matlab/extract_per_process_traces_v2.m` | No biology/algorithm changes; only invoked with different (seed, output_subdir) arguments already supported by its existing signature. |

## 4. What was actually run

MATLAB: `E:\MATLAB\bin\matlab.exe` (R2026a Update 2, `26.1.0.3251617`, trial
license; recorded in [`_matlab_version_probe.txt`](./_matlab_version_probe.txt)).
WholeCell source resolved via the extractor's existing fallback to
`E:\opencell\data\m1_sources\WholeCell` (worktree has no local copy; this is
the extractor's pre-existing, unmodified fallback path, not a new mechanism).

```powershell
# Seed 1 (Transcription, RNADecay) — worktree per_process_traces_v2_s001
matlab -batch "addpath('scripts/matlab'); extract_per_process_traces_v2({'Transcription','RNADecay'}, 'per_process_traces_v2_s001', 100, uint32(1));"
# duration: < 3 min for 2 files

# Seed 0 (Transcription, RNADecay, ProteinDecay) — worktree per_process_traces_v2_s000
# (explicit non-default output_subdir so seed 0 is regenerated fresh, with the
#  *current* extractor code, avoiding the schema-drift issue in §3/§6.2 that
#  would arise from reusing the older committed canonical seed-0 file)
matlab -batch "addpath('scripts/matlab'); extract_per_process_traces_v2({'Transcription','RNADecay','ProteinDecay'}, 'per_process_traces_v2_s000', 100, uint32(0));"
# duration: 109.4 s for 3 files (~36 s/file)

# Seed 0 + Seed 1 (ProteinDecay)
matlab -batch "addpath('scripts/matlab'); extract_per_process_traces_v2({'ProteinDecay'}, 'per_process_traces_v2_s000', 100, uint32(0)); extract_per_process_traces_v2({'ProteinDecay'}, 'per_process_traces_v2_s001', 100, uint32(1));"
# duration: 57.8 s for 2 files (~29 s/file)
```

Observed per-file cost: **~29-36 s**. Extrapolated full-scale cost (50 seeds ×
22 in-scope processes = 1100 files) ≈ **9-11 hours**, consistent with
`RUN_EXTRACTION.md`'s own P0 estimate ("~9-24 hours total"). This is
evidence for planning the (not-yet-started) full extraction, not a
recommendation to start it.

Resulting pilot inventory (all under
`data/m1_sources/karr_native/`, gitignored, sha256 in the JSON manifest):

| Process | seed 0 (`_s000/`) | seed 1 (`_s001/`) |
|---|---|---|
| Transcription | fresh (this pilot) | fresh (this pilot) |
| RNADecay | fresh (this pilot) | fresh (this pilot) |
| ProteinDecay | fresh (this pilot) | fresh (this pilot) |

## 5. Verification results

### 5.1 Structural validity
All 6 files load cleanly via `h5py` with `states_before`/`states_after` groups,
consistent tick counts (100), and metadata (`process_name`, `rng_seed`,
`n_ticks`, `timestamp`). Verified by `scripts/verify_multiseed_pilot.py` and
`tests/vivarium/test_multiseed_pilot_manifest.py::test_pilot_trace_is_structurally_valid`
(6/6 parametrized cases pass).

### 5.2 Non-vacuous seed independence
For each process, the `after/substrates` channel differs between seed 0 and
seed 1 (not a no-op seed):

| Process | identical across seeds? | max abs diff |
|---|---|---|
| Transcription | No | 2,697,814.0 |
| RNADecay | No | 33,777,312.0 |
| ProteinDecay | No | 169,616,910.0 |

Verified by `test_pilot_seeds_are_non_vacuously_independent` (3/3 pass).

### 5.3 Loader compatibility (the real `load_karr_oracle`, unmocked)

| Process | Before this pilot | After this pilot |
|---|---|---|
| RNADecay | `canonical_seed_count=1` (legacy npz fallback, `KARR_LEGACY_SINGLE_SEED_FALLBACK`) | `canonical_seed_count=2`, oracle_path = `per_process_traces_v2_s000/RNADecay_100ticks.mat`, **no warnings** |
| ProteinDecay | `canonical_seed_count=1` (legacy npz fallback) | `canonical_seed_count=2`, **no warnings** |
| Transcription | `canonical_seed_count=50` (specialized ensemble; unaffected) | unchanged: `canonical_seed_count=50`, ensemble still wins (correctly not disturbed) |

Verified by `test_rna_decay_and_protein_decay_are_genuinely_multiseed_via_loader`
and `test_transcription_pilot_data_does_not_disturb_specialized_ensemble`.

### 5.4 End-to-end Design-A dry run (informational only — not a verdict pin)
```
RNADecay    verdict=PASS warnings=[]   (seeds=[0,1], m_ticks=20, bootstrap_B=200)
ProteinDecay verdict=PASS warnings=[]  (seeds=[0,1], m_ticks=20, bootstrap_B=200)
```
Run with a deliberately small `m_ticks`/`bootstrap_B` for a fast smoke check;
output written to gitignored `artifacts/l22_multiseed_pilot/<process>/` (not
committed — regenerate via `run_design_a(...)` in
`tests/vivarium/l2_2_design_a_runner.py` if needed). **This is not a
production L2.2 gate run** and does not pin any threshold or verdict.

## 6. Remaining work before any full-scale (50×22) extraction

1. **Generalize the seed-0 discovery fix.** Either (a) extend
   `_v2_seed_mat_path`/`_load_v2_ensemble` to also treat the unsuffixed
   `per_process_traces_v2/` directory as seed 0, or (b) bulk-materialize all
   28 canonical seed-0 files into `per_process_traces_v2_s000/` (as done here
   for 3 processes). Option (b) is zero-code-risk but duplicates ~tens of MB
   of gitignored data; option (a) is a 1-function code change but will
   change `canonical_seed_count` (and therefore `KARR_SINGLE_SEED_REUSED`
   presence) for most of the 22 in-scope processes simultaneously — **this
   needs its own reviewed change with L2.2 verdicts explicitly re-pinned**,
   which is out of scope for this pilot.
2. **Audit schema consistency across existing fixtures before mass re-extraction.**
   This pilot discovered that the extractor's snapshot-property allowlist has
   grown since some already-extracted fixtures were generated (e.g. the
   committed `per_process_traces_v2_s001/Translation_100ticks.mat` from
   2026-06-05 lacks `mRNAs`/tRNA channels that current code emits). A
   50-seed run mixing old and newly-extracted seeds for the same process
   will hit `_load_seeded_mat_channels`'s "Observable schema drift" error at
   load time, not extraction time — worth a pre-flight schema audit across
   all `per_process_traces_v2_s*` directories, or a policy of regenerating
   full seed ranges together per process.
3. **Git hygiene.** Closed the `.gitignore` gap that let
   `per_process_traces_v2_s001/Translation_100ticks.mat` get committed in
   `45c67165` (now covered by `per_process_traces_v2_s*/` /
   `per_process_traces_v2_event_s*/` patterns). The already-tracked blob
   itself was left in git history/index as-is (removing a tracked file was
   not part of this task's scope); a follow-up housekeeping pass could
   `git rm --cached` it if the team wants it out of the tree.
4. **Unrelated pre-existing test failures noted, not fixed (out of scope).**
   `tests/vivarium/test_l2_2_design_a_ensemble_loader.py::test_load_v2_ensemble_loads_single_seed`
   and `::test_load_v2_ensemble_stacks_multiple_present_seeds_in_order` fail
   on this branch before and after this change (`_metabolism_substrate_cube`
   rejects the tests' synthetic 2-element substrate vectors because it now
   requires exactly 585 metabolites). This is orthogonal to Transcription/
   RNADecay/ProteinDecay and was not introduced by this pilot; flagged for
   separate triage.
5. **Full 50×22 extraction itself has not been started** (explicit non-goal).
   Use §4's measured per-file cost (~30-40 s) to plan the real run via the
   existing `scripts/matlab/extract_everything_v1.m` orchestrator, which
   already supports `(seedFirst, seedLast, tickFirst, tickLast, dataTypes)`
   and idempotent skip-on-exist — no new launcher is needed for that future
   step either.
