# L2.2 Stale Canonical Seed-0 Regeneration — Rationale, Evidence, and Plan

**Scope:** ProteinDecay, ProteinFolding, ProteinProcessingII, RNADecay,
RNAProcessing (the "stale5" subset of the 16-process L2.2 production set).

**Decision reference:** `regenerate-stale-l22-seed-zero`,
`D:\OneDrive - Microsoft\.pm-os\DECISIONS.md`, ratified 2026-07-28
(Opus 4.8 independent adjudication, session `5c51d44b-5a9f-4b23-85ff-0fddaadf2212`).

**Worktree:** `E:\opencell-worktrees\l22-stale5-regen`,
branch `agent/l22-stale5-regen`.

This report documents why these five processes' canonical (unsuffixed)
seed-0 traces are being regenerated together with seeds 1-49, what evidence
grounds that decision, and what is and is not knowable about the files being
superseded. It is written and committed *before* the long MATLAB
regeneration run, per the task's required commit cadence.

## 1. Root cause: allowlist growth, not an extractor bug

`scripts/matlab/extract_per_process_traces_v2.m`'s `pick_snapshot_properties(proc)`
selects which of a MATLAB process object's properties to snapshot via
`intersect(properties(proc), {<hardcoded allowlist>})`. A channel appears in
the output `.mat` file only if it is **both** a real MATLAB-declared property
on that process class **and** present in the hardcoded allowlist. The
allowlist has grown over time as new processes were brought into the v2
multi-seed extraction effort; two commits added the five channels at issue
here, both **after** the five stale canonical seed-0 files were generated:

| Commit | Date | Channels added |
|---|---|---|
| `2073647caf93989b4fcb983bb38b0591c3812041` | 2026-06-02 17:12:52 +05:30 | `'RNAs'` (capitalized) |
| `5c316642f37f7b785c04598f7fc9d9133d7cbf46` | 2026-06-06 16:20:39 +05:30 | `'intergenicRNAs'`, `'signalSequenceMonomers'`, `'unfoldedComplexs'`, `'foldedComplexs'` (+7 other properties for other processes) |

The extractor script itself was introduced in commit
`e4cd4ef31f0c090f996dac5ff7f6d2d5d3a24b45` (2026-05-29 01:13:31 +05:30);
`git show e4cd4ef3:scripts/matlab/extract_per_process_traces_v2.m` confirms
its `pick_snapshot_properties()` allowlist at that point genuinely lacks all
five channels below.

## 2. The five "extra" channels are genuine MATLAB-declared properties

Verified directly against the primary MATLAB source
(`data/m1_sources/WholeCell/src/+edu/.../+process/*.m`, copied into this
worktree — see §4):

| Process | Extra channel(s) | Source citation |
|---|---|---|
| ProteinDecay | `RNAs` | `ProteinDecay.m:245` |
| ProteinFolding | `unfoldedComplexs`, `foldedComplexs` | `ProteinFolding.m:247` (`unfoldedComplexs`), `ProteinFolding.m:249` (`foldedComplexs`) |
| ProteinProcessingII | `signalSequenceMonomers` | `ProteinProcessingII.m:164` |
| RNADecay | `RNAs` | `RNADecay.m:136` |
| RNAProcessing | `intergenicRNAs` | `RNAProcessing.m:275` |

Each is a `properties`-block-declared field on the corresponding process
class — not a typo, not a dynamically-injected field, and not an artifact of
extractor logic. This confirms the five canonical seed-0 files are **stale
relative to the current, source-faithful extractor** (missing real channels
the class has always exposed), not that the current extractor is
over-capturing spurious data.

## 3. Provenance dating: why these five files specifically

All five old canonical seed-0 files' on-disk modification timestamps fall
strictly between the extractor's introduction commit and the first
allowlist-growth commit:

| Process | Old file mtime (UTC) |
|---|---|
| ProteinDecay | 2026-05-30 09:27:11 |
| ProteinFolding | 2026-05-30 01:46:48 |
| ProteinProcessingII | 2026-05-28 19:48:25 |
| RNADecay | 2026-05-28 19:49:25 |
| RNAProcessing | 2026-05-28 19:49:55 |

(extractor introduced 2026-05-29 01:13:31 +05:30 = 2026-05-28 19:43:31 UTC;
first allowlist growth 2026-06-02 17:12:52 +05:30 = 2026-06-02 11:42:52 UTC —
all five mtimes fall in that window.)

**This is an mtime-correlation inference, not a certified provenance
record.** No historical manifest pinning the exact extractor commit or
WholeCell source-tree hash used at generation time exists anywhere in this
repository. The full honest statement of what is and is not knowable is
recorded programmatically in `scripts/l22_extraction/archive_stale5.py` and
its output manifest (§5) — this report does not repeat every caveat, but
none of the above should be read as more certain than "high-confidence
inference from timestamp correlation."

## 4. WholeCell source tree

`data/m1_sources/WholeCell/` is gitignored and untracked; no hash of the
tree that produced the May 2026 stale files was ever recorded at generation
time, so its exact historical identity is **unknowable** from this
repository. What can be verified: the tree copied into this worktree for the
regeneration run (`robocopy` from the primary checkout, 859 files, byte- and
count-identical) is the tree that will produce seed 0 and seeds 1-49 for all
five processes in this regeneration, so every seed in this run shares one
single, internally-consistent source tree — even though we cannot prove it
is identical to whatever tree produced the old stale files.

## 5. Archive of the old files being superseded

Before any old file was deleted, it was copied (never modified) to:
- Live worktree location (temporarily, until replaced by regeneration):
  `data/m1_sources/karr_native/per_process_traces_v2/<Process>_100ticks.mat`
- Durable archive copy: `artifacts/l22_stale5_regen/archive_old_seed0/<Process>_100ticks.mat`

Both copies were hashed and cross-checked against the primary checkout's
originals; the full manifest (`artifacts/l22_stale5_regen/archive_manifest.json`,
gitignored — raw `.mat` bytes are never committed, only this report and any
tracked JSON summaries) confirms `archive_matches_primary: true` for all
five files. Summary (SHA256, size, original mtime):

| Process | SHA256 | Size (bytes) | Original mtime (UTC) |
|---|---|---|---|
| ProteinDecay | `2c458214a6d08e60a72206a6c52ddd15721b8bf0cf7ae3d3bf1d8bc9f1fe1aca` | 2,237,999 | 2026-05-30T09:27:11.821071 |
| ProteinFolding | `b4a9c1d1b7ddb41abe905029477a60f5dcc1c5ed6591258b4cb2c723150e8410` | 1,957,392 | 2026-05-30T01:46:48.028737 |
| ProteinProcessingII | `1cbcb450d706f12c4724ef345c915509761a2477f46b8e42d7d6e373824e5a11` | 1,938,368 | 2026-05-28T19:48:25.704497 |
| RNADecay | `81639bda0f756e4953548245929f57da09f5b89cf8141691fbd8b50aa98d213b` | 300,192 | 2026-05-28T19:49:25.891630 |
| RNAProcessing | `8f2d87d42b6b02518d20750c44c9188d158e41283df0794f5d6e337a20b44f0a` | 1,500,000 | 2026-05-28T19:49:55.850221 |

Extractor blob identity (git SHA1 of `scripts/matlab/extract_per_process_traces_v2.m`):
- Current HEAD: `4a40e3938f5c66d126576f10582c48db861ea950`
- Historical (commit `e4cd4ef3`, inferred per §3, not a certified pin): `8f4277fdb749f476016946f6675ac2520ac81858`

MATLAB version: probed now as `26.1.0.3251617 (R2026a) Update 2` (trial
license), matching the only MATLAB install/version ever referenced in this
project's dated records (`docs/phase_f`, `docs/agent_checkpoints`,
`MULTISEED_PILOT_REPORT.md`) — a strong circumstantial match for the
historical run, but again not a per-run pin that was ever recorded.

## 6. Regeneration plan

1. Use `scripts/l22_extraction/seed0_regen.py` (new, minimal, closed to
   exactly `STALE5_PROCESSES`) to plan and apply canonical seed-0
   invalidation/regeneration — the general launcher's
   `SeedZeroForbiddenError` policy is deliberately *not* relaxed for any
   other process or caller.
2. Regenerate canonical (unsuffixed) seed 0 for all five processes in one
   MATLAB `-batch` invocation, using the current unmodified
   `extract_per_process_traces_v2.m` and the WholeCell source copied into
   this worktree.
3. Regenerate seeds 1-49 via the existing, unmodified
   `scripts/l22_extraction/launcher.py` + `scripts/matlab/run_l22_seed_shards.ps1`
   (no changes needed — they already support seeds ≥ 1 for an explicit
   process list).
4. Validate: atomic canary (one process, all 50 seeds) before running the
   remaining four; then full final validation (schema consistency across
   all 50 seeds, extra-channel presence, non-vacuity, `load_karr_oracle`
   `canonical_seed_count=50`/`warnings=[]`, no `_s000` directories anywhere).

Never create or retain any `per_process_traces_v2_s000/` directory for any
of the five processes — canonical seed 0 is always the unsuffixed directory.

## 7a. Canonical seed-0 regeneration results

Ran once, all five processes in a single MATLAB `-batch` session (1 worker,
`E:\MATLAB\bin\matlab.exe`, R2026a Update 2, ~a few seconds total), targeting
the canonical unsuffixed output directory explicitly (`extract_per_process_traces_v2({...}, 'per_process_traces_v2', 100, uint32(0))`).
All five old stale files had already been deleted by `seed0_regen.py`'s
`apply_seed0_invalidations` (§6) before this call, so the extractor's own
existence-only skip check could not silently keep a stale file.

| Process | Snapshot properties (per MATLAB stdout) | Required channel present |
|---|---|---|
| ProteinDecay | RNAs, boundEnzymes, complexs, enzymes, monomers, substrates | RNAs ✅ |
| ProteinFolding | boundEnzymes, enzymes, foldedComplexs, foldedMonomers, substrates, unfoldedComplexs, unfoldedMonomers | foldedComplexs, unfoldedComplexs ✅ |
| ProteinProcessingII | boundEnzymes, enzymes, processedMonomers, signalSequenceMonomers, substrates, unprocessedMonomers | signalSequenceMonomers ✅ |
| RNADecay | RNAs, boundEnzymes, enzymes, substrates | RNAs ✅ |
| RNAProcessing | boundEnzymes, enzymes, intergenicRNAs, processedRNAs, substrates, unprocessedRNAs | intergenicRNAs ✅ |

All five new seed-0 files independently re-validated via
`trace_validation.validate_structural` (structurally sound, `ok=True`,
zero errors) and confirmed to carry their required extra channel(s) in
**both** `states_before` and `states_after` groups (not just one side).

## 7b. Atomic canary: RNADecay, all 50 seeds

Per the task's canary requirement, ran one full process (RNADecay — the
smallest file, chosen for fastest turnaround) through canonical seed 0
(above) plus seeds 1-49 (`scripts/matlab/run_l22_seed_shards.ps1
-Processes RNADecay -Seeds "1-49" -Workers 1`, unmodified launcher/driver,
run tag `stale5_canary_RNADecay`), then validated with the existing report
machinery scoped to this one process:

```
bin\oc-py scripts/l22_extraction/report.py final --seeds 1-49 \
    --processes RNADecay --skip-specialized \
    --out artifacts/l22_stale5_regen/canary_RNADecay_final_report.json
```

Result (full JSON gitignored/regenerable under `artifacts/l22_stale5_regen/`,
per existing `artifacts/` convention — key fields excerpted here):

- Worker exit code: `0`. Duration: ~24 minutes for 49 seeds (single worker,
  smallest of the five files).
- `report.py final`: `"result": "PASS"`, `"missing_or_failing": []`.
- Real `load_karr_oracle` dispatch (`loader_results.RNADecay`): `"ok": true`,
  `"canonical_seed_count": 50`, `"warnings": []`.
- Seed independence / non-vacuity: sampled SHA256 of seeds {0, 1, 2, 3, 25,
  49} are all pairwise distinct (no seed silently reusing another seed's
  trace).
- No `per_process_traces_v2_s000/` directory exists anywhere in this
  worktree (confirmed via directory listing) — canonical seed 0 stayed in
  the unsuffixed `per_process_traces_v2/` directory throughout.

Canary PASSED on every dimension required before proceeding to the
remaining four processes' seeds 1-49.

## 7c. Remaining four processes (ProteinDecay, ProteinFolding,
ProteinProcessingII, RNAProcessing), seeds 1-49

See the final manifest/report (commit C) for full results. At the time this
section was written (commit B), the sibling worktree `l22-full-extract`'s
own Phase-3 run had already finished (0 active MATLAB processes elsewhere),
so this run's worker count was chosen consistent with the task's bounded-
load policy (≤4 total active compute MATLAB processes system-wide).

## 7d. Remaining four processes: results and final validation (commit C)

Ran `scripts/matlab/run_l22_seed_shards.ps1 -Processes
"ProteinDecay,ProteinFolding,ProteinProcessingII,RNAProcessing" -Seeds
"1-49" -Workers 2 -NoWait` (run tag `stale5_remaining4`), unmodified
launcher/driver, using 2 workers since the sibling worktree
`l22-full-extract` had 0 active MATLAB processes at launch time (confirmed
via `Get-Process matlab` immediately before launch) — well within the
task's ≤4-total-active-compute-processes budget. PIDs 22792 (worker 0, odd
seeds 1,3,...,49) and 16372 (worker 1, even seeds 2,4,...,48). Both workers
exited with empty stderr logs (no errors) after ~21 minutes wall clock
(launched ~04:34 UTC, all 196 files present by ~04:55 UTC). No license
contention or FlexLM errors observed at either 1 or 2 concurrent workers.

Final validation, all five processes together, all 50 seeds each:

```
bin\oc-py scripts/l22_extraction/report.py final --seeds 1-49 \
    --processes ProteinDecay,ProteinFolding,ProteinProcessingII,RNADecay,RNAProcessing \
    --skip-specialized --out artifacts/l22_stale5_regen/final_report.json
```

Result: **`"result": "PASS"`, `"missing_or_failing": []`**. Per-process real
`load_karr_oracle` dispatch (`loader_results`), all five identical shape:

| Process | ok | canonical_seed_count | warnings |
|---|---|---|---|
| ProteinDecay | true | 50 | [] |
| ProteinFolding | true | 50 | [] |
| ProteinProcessingII | true | 50 | [] |
| RNADecay | true | 50 | [] |
| RNAProcessing | true | 50 | [] |

Additional independent checks (beyond `report.py final`'s structural +
loader validation), sampling seeds {0, 1, 2, 3, 25, 49} per process:

- **Required-channel presence**: every process's required extra channel(s)
  (§2 table) present in **both** `states_before` and `states_after` at
  every sampled seed, not merely seed 0.
- **Non-vacuity / seed independence**: SHA256 of each sampled seed's `.mat`
  file is pairwise distinct within every process (30 hashes total across
  the 5 processes, all unique) — no seed silently reused another seed's
  trace, and no seed is a degenerate/empty duplicate.
- **File count**: exactly 49 seed-suffixed files (`per_process_traces_v2_s001`
  through `_s049`) per process, plus exactly 1 canonical unsuffixed file
  (`per_process_traces_v2/<Process>_100ticks.mat`) — 50 distinct Karr seeds
  per process, 250 files total across the five processes.
- **No `_s000` anywhere**: `Get-ChildItem -Recurse -Directory -Filter
  "*_s000"` under `data/m1_sources/karr_native/` returns nothing, for the
  entire worktree, not just these five processes.

All five processes fully satisfy the task's completion criteria: 50
distinct Karr seeds, exact schema consistency, required channels present
where applicable, biological non-vacuity, real loader
`canonical_seed_count=50`/`warnings=[]`, no missing/corrupt files, no
`_s000`.

## 8. Out of scope / unaffected

This regeneration touches only local worktree copies of the five named
processes' traces. It does not modify: the primary checkout's canonical
files, the extractor script, the loader (`_l2_2_design_a_runner_helpers.py`),
any process biology/model code, metrics, verdict pins, or `plan.md`/status
files. The other 11 processes' seeds 2-49 extraction (running in the sibling
worktree `l22-full-extract`) is untouched and unblocked by this work.
