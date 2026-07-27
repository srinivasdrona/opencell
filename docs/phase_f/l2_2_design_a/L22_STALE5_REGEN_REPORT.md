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

## 7. Out of scope / unaffected

This regeneration touches only local worktree copies of the five named
processes' traces. It does not modify: the primary checkout's canonical
files, the extractor script, the loader (`_l2_2_design_a_runner_helpers.py`),
any process biology/model code, metrics, verdict pins, or `plan.md`/status
files. The other 11 processes' seeds 2-49 extraction (running in the sibling
worktree `l22-full-extract`) is untouched and unblocked by this work.
