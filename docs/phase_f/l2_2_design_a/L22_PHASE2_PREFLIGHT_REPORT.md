# L2.2 Full Extraction — Phase 2 Seed-1 Schema Preflight Report

Companion evidence to `docs/phase_f/l2_2_design_a/L22_FULL_EXTRACTION_SCOPE.md`
(Phase 1). Produced by `scripts/l22_extraction/report.py preflight`, backed
by the tracked JSON at
`artifacts/l22_full_extraction/phase2_preflight_report.json` (gitignored
alongside all other `artifacts/`, regenerable from the steps below; this
markdown captures the durable conclusion).

## Method

1. Copied the 16 production processes' canonical seed0 `.mat` files
   (unmodified) from the primary checkout
   (`E:\opencell\data\m1_sources\karr_native\per_process_traces_v2\`) into
   this worktree's `data/m1_sources/karr_native/per_process_traces_v2/`.
   Also copied the (gitignored, untracked) WholeCell MATLAB source tree
   (`data/m1_sources/WholeCell/`) from the primary checkout, since it was
   absent from this worktree and is required by
   `extract_per_process_traces_v2.m` to run at all.
2. Generated seed 1 for all 16 production processes with the current,
   unmodified `extract_per_process_traces_v2.m`:
   ```
   scripts\matlab\run_l22_seed_shards.ps1 -Processes <16-list> -Seeds "1" -Workers 2
   ```
   (single seed shard, so this ran as one sequential MATLAB `-batch`
   session; see §4 for the worker-parallelism bug found and fixed while
   doing this.)
3. Ran `bin\oc-py scripts/l22_extraction/report.py preflight` — for every
   production process, compares canonical seed0 vs. the freshly generated
   seed1 via the existing loader's own
   `_l2_2_design_a_runner_helpers._seed_schema_preflight` (channel key-set +
   per-channel width match), and separately confirms Transcription/
   Translation's specialized 50-seed ensembles are still healthy via the
   real `load_karr_oracle()`.

## Result: 11 of 16 production processes PASS; 5 BLOCKED (genuine schema drift)

### Pass (11) — seed1 schema matches canonical seed0 exactly; cleared for Phase 3

DNARepair, DNASupercoiling, MacromolecularComplexation, Metabolism,
ProteinModification, ProteinProcessingI, ProteinTranslocation,
RNAModification, Replication, ReplicationInitiation, tRNAAminoacylation.

For each: `schema_preflight.ok = true`, `loader.canonical_seed_count = 2`
(seed0 + seed1), `loader.warnings = []`.

### Specialized ensembles (2) — confirmed healthy, untouched per hard policy

Transcription: `canonical_seed_count = 50`, `specialized_ensemble_healthy =
true`. Translation: `canonical_seed_count = 50`,
`specialized_ensemble_healthy = true`. Neither was regenerated; this audit
is the required proof that the hard-policy exclusion in
`L22_FULL_EXTRACTION_SCOPE.md` §1.2 remains correct.

(Note: their own canonical seed0 files were deliberately *not* copied into
this worktree — see §5, "unrelated finding".)

### BLOCKED (5) — canonical seed0 schema does not match a freshly generated seed1

Per hard policy ("If canonical seed0 does not match a freshly generated
seed1 schema, STOP that process before launching further seeds... do not
patch around it"), **seeds 2-49 are NOT generated for these 5 processes.**
The freshly generated seed1 file for each was retained on disk (gitignored,
not committed) as diagnostic evidence but must not be used as part of a
50-seed oracle for these processes until resolved.

| Process | Canonical seed0 `states_before` channels | Fresh seed1 `states_before` channels | Extra channel(s) in seed1 |
|---|---|---|---|
| ProteinDecay | boundEnzymes, complexs, enzymes, monomers, substrates | + RNAs | `RNAs` |
| ProteinFolding | boundEnzymes, enzymes, foldedMonomers, substrates, unfoldedMonomers | + foldedComplexs, unfoldedComplexs | `foldedComplexs`, `unfoldedComplexs` |
| ProteinProcessingII | boundEnzymes, enzymes, processedMonomers, substrates, unprocessedMonomers | + signalSequenceMonomers | `signalSequenceMonomers` |
| RNADecay | boundEnzymes, enzymes, substrates | + RNAs | `RNAs` |
| RNAProcessing | boundEnzymes, enzymes, processedRNAs, substrates, unprocessedRNAs | + intergenicRNAs | `intergenicRNAs` |

In every case the *fresh* seed1 file (generated just now with the current,
unmodified extractor) has **more** channels than the canonical seed0 file —
never fewer. This is consistent with the prior pilot's finding
(`MULTISEED_PILOT_REPORT.md` §6.2/§3) that `extract_per_process_traces_v2.m`'s
`pick_snapshot_properties()` snapshot allowlist has grown since these five
processes' canonical seed0 files were generated (their timestamps in the
primary checkout are 5/22-5/30/2026; the current extractor script is
unmodified in this task but reflects allowlist growth that happened after
those particular seed0 files were captured).

**Recommended source-faithful repair (not performed by this task — outside
this task's authority):** canonical seed0 for these 5 processes is itself
stale relative to the current extractor and would need to be regenerated
*together with* the full seed range under the current schema for these
processes to be usable in the 50-seed oracle. Per hard policy this task
must not generate or retain a competing seed0
("Canonical unsuffixed seed0 is authoritative; do NOT generate or retain a
competing `_s000`") — so resolving this requires an explicit decision by
the project maintainers (Opus/human review) on whether to regenerate these
5 processes' canonical seed0 under the current extractor, which is a
decision this task defers rather than making unilaterally.

## Loader dispatch details

For each blocked process, `load_karr_oracle(process)` itself raises the
same schema-drift `ValueError` (not just the standalone preflight check) —
confirming that "passes preflight" and "loads cleanly in production" are,
by construction, the same code path (`preflight.py` reuses
`_seed_schema_preflight` directly, and `_load_v2_ensemble` invokes the same
function internally via `_load_seeded_mat_channels`).

## Unrelated finding: canonical seed0 for specialized-excluded processes must not be copied

While first running this preflight, copying **all 28** processes' canonical
seed0 files (including Transcription/Translation, which are specialized-
ensemble-excluded and never need generic-v2 generation) caused
`load_karr_oracle("Transcription")` to fail with:

```
Transcription RNA oracle width does not match nascentRNAGeneComposition: 525 vs 335
```

Root cause: `load_karr_oracle()` unconditionally calls `_load_v2_ensemble(process)`
first (before comparing seed counts against the specialized ensemble), and
merely the *presence* of a canonical seed0 file is enough for that generic
v2 candidate-build to run an eager RNA-channel-width cross-check
(`_project_transcription_rna_cube` vs. a fixture's `nascentRNAGeneComposition`)
that is unrelated to, and was never exercised by, any seed range this task
generates. This is a latent robustness gap in `_load_v2_ensemble` (it
doesn't guard that eager cross-check so a specialized-ensemble comparison
can never even be reached for Transcription if any canonical seed0 file for
it happens to exist) — **not modified by this task**, since it lives in the
shared, heavily-reused oracle loader
(`tests/vivarium/_l2_2_design_a_runner_helpers.py`) and touching it is
outside this task's scope (reuse, not modify). The practical fix applied
here: this worktree only ever copies canonical seed0 for the 16 *production*
processes, never for Transcription/Translation (or any event-class/
out-of-scope process) — they are audited via `loader_report()` alone, which
is all Phase 2/3 require of them.

## Tooling bug found and fixed during this phase

`scripts/matlab/run_l22_seed_shards.ps1` originally called
`Start-Process -ArgumentList @("-batch", $combined)`. PowerShell's
`Start-Process` does not quote array elements before joining them into the
child process's raw command line, so MATLAB silently received only the
substring up to the first space in `$combined` (effectively just
`addpath('scripts/matlab');`) and exited having done nothing — no error, no
diary output, no trace files, exit code 0. Fixed by building one pre-quoted
`-ArgumentList` string (`"-batch `"$combined`""`) instead of an array; a
guard now throws if `$combined` ever contains a literal double-quote (which
would break that quoting) rather than silently mis-invoking MATLAB again.
Verified via a single-process direct-`Start-Process` repro and confirmed
fixed by the full 16-process seed1 run in this phase's evidence above.

## Next: Phase 3 scope

Phase 3 (seeds 2-49) proceeds only for the **11 passing production
processes**. The 5 blocked processes and the 2 specialized-ensemble
processes are excluded from Phase 3 generation (blocked: STOP per hard
policy; specialized: already have 50 valid seeds, must not be regenerated).
