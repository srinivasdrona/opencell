# L2.2 Evidence Index — Spec (schema v1)

Status: **integrity gate landed, acceptance gate NOT active.** This document
replaces the circular hand-written verdict dictionaries that used to live in
`tests/vivarium/test_l2_2_strict_rubric.py` (`EXPECTED_L2_2_VERDICTS`) and
`scripts/probe_l2_2_strict_audit.py` (`EMPIRICAL_VERDICTS`) with a
generator-only machine evidence index.

## 1. Why the old rubric was circular

The old `test_l2_2_strict_rubric.py` asserted that
`probe_l2_2_strict_audit.classify_l2_2(process)` returned a value pinned in
`EXPECTED_L2_2_VERDICTS` — but both dictionaries were hand-typed by the same
authoring process, from the same offline runs, with no machine-checked link
back to raw channel numbers, current catalog state, or artifact hashes. A
test asserting `A == A` where both sides are manually maintained by the same
hand is not evidence of anything; it only detects accidental edits to one
side without the other. Worse, `EMPIRICAL_VERDICTS` trusted the *stored*
`result.json["verdict"]` string from ad hoc offline runs, so a stale or
tampered artifact could silently keep reporting `VERIFIED_GENUINE` forever.

## 2. Two-stage model: integrity vs acceptance

This replacement introduces a hard split between two different questions,
which the old rubric conflated:

- **(A) Integrity/audit (landed now, `generator.py audit`).** "Is the
  tracked `evidence_index.json` a truthful, mechanically-derived reflection
  of the current catalog + evidence tree?" This can — and today, honestly
  does — PASS while every process row is `MISSING_EVIDENCE` and the
  aggregate verdict is `NON_GREEN`. Integrity is about *truthfulness*, not
  about whether the underlying biology has been validated yet.
- **(B) Acceptance gate (NOT active; `generator.py audit --require-all-pass`).**
  "Are all 22 in-scope processes GREEN with full hardening?" This flag
  exists today and returns nonzero (exit 2) unconditionally, because no
  process currently has real runner evidence. Wiring `--require-all-pass`
  into CI as a blocking check is an explicit **later** commit, made only
  after Karr oracle extraction closes out and real evidence is populated.
  No skipped/xfail placeholder acceptance test is added in this task.

## 3. Scope derivation (mechanical, catalog-driven)

`scripts/l22_evidence/catalog.py::in_scope_processes()` reads
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` (reusing
`scripts/l22_extraction/derive_scope.py`'s parsing, so scope can never drift
between the raw-extraction tooling and the evidence index) and returns
**every** process flagged `in_scope_L2_2: true`, regardless of
`harness_type`. As of this commit that is exactly 22 processes: 18
`design_a_per_tick` + 4 `event_class` (`Cytokinesis`, `DNADamage`,
`FtsZPolymerization`, `RibosomeAssembly`). Processes with
`in_scope_L2_2: false` (6 processes: `ChromosomeCondensation`,
`ChromosomeSegregation`, `HostInteraction`, `ProteinActivation`,
`TerminalOrganelleAssembly`, `TranscriptionalRegulation`) are excluded from
the index entirely — "deterministic out-of-scope is excluded by catalog".

The generator emits **exactly one row per in-scope process, never zero,
never duplicated, never extra.**

## 4. Authoritative evidence location

Mirrors the runner-native output layout already documented in
`L2_2_DESIGN_A_SPEC.md` section 13 (the same file names
`tests/vivarium/l2_2_design_a_runner.py` already writes: `result.json`,
`input_manifest.json`, `provenance.json`, plus optional sidecars
`thresholds.json`, `null_calibration.json`, `SUMMARY.json`,
`allocator_inputs.json`, `analytical_check.json`), simplified to a single
`latest/` directory per process instead of timestamped run directories plus
a `latest` symlink/junction (Windows junctions are a known operational trap
on this project's host; see the PM OS `TRAPS.md`).

```
artifacts/l2_2_gates/
├── <Process>/
│   ├── latest/            # design_a_per_tick harness evidence
│   │   ├── result.json            # required (authority)
│   │   ├── input_manifest.json    # required (authority)
│   │   ├── provenance.json        # required (authority)
│   │   ├── thresholds.json        # optional sidecar
│   │   ├── null_calibration.json  # optional sidecar
│   │   ├── SUMMARY.json           # optional sidecar
│   │   ├── allocator_inputs.json  # optional sidecar
│   │   └── analytical_check.json  # optional sidecar
│   └── latest_event/      # event_class harness evidence (L2.event; not yet built)
```

`artifacts/` is gitignored (regeneratable); the raw evidence directories are
NOT expected to be committed. `docs/phase_f/l2_2_design_a/evidence_index.json`
(this generator's output) IS the tracked artifact — it records artifact
hashes and status, not the raw channel data itself.

**Event-class routing**: processes with `harness_type: event_class` look for
evidence under `latest_event/`, not `latest/`, because the L2.event harness
does not exist yet. Until it is built this directory is empty for all 4
event-class processes, which the generator reports as explicit
`MISSING_EVIDENCE` — never silently excluded, never a vacuous PASS.

## 5. Row schema (schema_version 1)

```json
{
  "process": "Metabolism",
  "bucket": "TRIVIAL_RNG",
  "harness_type": "design_a_per_tick",
  "catalog_soft_flags": {
    "harness_type": "design_a_per_tick",
    "N_seeds": 50,
    "M_ticks": 20,
    "primary_channel": "substrates",
    "closed_form_dominant": "false",
    "primary_distance": "per_tick_vector_w1_mean",
    "in_scope_L2_2": true
  },
  "evidence_dir": "artifacts/l2_2_gates/Metabolism/latest",
  "artifact_hashes": {"result.json": "...", "input_manifest.json": "...", "provenance.json": "..."},
  "channel_verdicts": {"substrates": "PASS"},
  "provenance_git_sha": "...",
  "reasons": [],
  "mechanical_verdict": "PASS",
  "green": true
}
```

`catalog_soft_flags` are **soft**: hashing `PROCESS_CATALOG.yaml`
(`catalog_sha256` at the index root) proves the catalog text hasn't changed,
but it does NOT prove `harness_type`, `N_seeds`/`M_ticks`, `primary_channel`,
or `closed_form_dominant` are *correct* or *supported by real evidence*.
Supporting (or contradicting) evidence for each soft flag is surfaced via
`reasons[]` and the N/M-mismatch / sentinel-warning / H12-support checks
below — a row is never green merely because the catalog hash matches.

`reasons` is a multi-label list (the same "multiple simultaneous causes,
name them all" convention already used by the L2.2 divergence taxonomy in
`L2_2_DESIGN_A_SPEC.md` section 9.3). `mechanical_verdict` is one of:

| Value | Meaning | Green? |
|---|---|---|
| `PASS` | Evidence present, schema valid, hashes current, N/M match, every gateable channel mechanically re-derives to `PASS`/`SEED_NOISE`, no sentinel warnings, no unsupported `DEFERRED`/H12 claims. | **yes** |
| `MISSING_EVIDENCE` | One or more of `result.json`/`input_manifest.json`/`provenance.json` absent. | no |
| `SCHEMA_INVALID` | An authority file exists but is not parseable JSON, or `result.json` has no channel marked `is_primary`. | no |
| `NO_GATEABLE_CHANNELS` | Every channel is `EVENT_CHANNEL_DEFERRED` or `INSUFFICIENT_SAMPLES`. | no |
| `FAIL` | Any other non-green condition (raw `w1 > threshold`, `NM_MISMATCH`, `STALE_VS_TREE`, `SENTINEL_FAIL`, `MISSING_EVALUATOR`, `PRIMARY_CHANNEL_VACUOUS`, `PROCESS_NAME_MISMATCH`, `DEFERRED`). See `reasons[]` for exactly which. | no |

## 6. Mechanical verdict re-derivation (`scripts/l22_evidence/verdict.py`)

**Stored verdict strings inside `result.json` are never trusted.** Every
channel's verdict is recomputed from raw fields only. The evaluator
dispatches on the channel's own `aggregation` string; four aggregations are
mechanically re-derivable today:

### 6.1 `per_tick_vector_w1_mean` (the generic count-vector channels)

- Missing raw fields (`w1_oc_vs_karr`, `threshold`, `q95_null`,
  `n_nonzero_oc`, `n_nonzero_karr`) → `MISSING_EVALUATOR`.
- Primary channel with zero nonzero observations on **both** sides →
  `PRIMARY_CHANNEL_VACUOUS` (non-vacuous primary channel requirement).
- `n_nonzero < 30` (either side) → `INSUFFICIENT_SAMPLES` (non-gating).
- `w1 <= q95_null` → `SEED_NOISE`; `w1 <= threshold` → `PASS`; else `FAIL`.

### 6.2 `per_component_scaled` (chromosome-primary; `Replication`, `DNASupercoiling`)

Raw source: `channels[c]["per_component"]`, written by
`per_component_scaled_distance()` in
`tests/vivarium/_l2_2_design_a_projections.py`. Required raw fields:
`component_raw_w1`, `component_scales`, `scaled_distance_threshold`,
`component_n_nonzero_oc`, `component_n_nonzero_karr` (all keyed by the same
set of component names; the last three were added to the runner's output as
part of this evaluator so re-derivation never has to trust the runner's own
`component_verdicts`/`joint_verdict` strings). Any missing field, mismatched
component-name sets, or a non-finite/non-positive `raw_w1`/`scale` →
`MISSING_EVALUATOR`.

For each component: `scaled_w1 = raw_w1 / max(scale, 1e-12)`; component
verdict is `PASS` iff `scaled_w1 <= scaled_distance_threshold`, else `FAIL`
(exactly the runner's own formula, independently recomputed here rather than
read from the stored `component_verdicts` dict). If the channel is primary
and **every** component has zero nonzero observations on both OC and Karr
→ `PRIMARY_CHANNEL_VACUOUS` (a single trivial-always-zero component
alongside otherwise-real components is not vacuous by itself). Otherwise:
any component `FAIL` → channel `FAIL`; all components `PASS` → channel
`PASS`.

### 6.3 `hurdle_event_rate_plus_conditional_scaled_distance` (chromosome-primary; `DNARepair`)

Raw source: `channels[c]["hurdle"]`, written by
`hurdle_event_rate_plus_conditional_distance()` in the same projections
module. Required raw fields: `event_rate_diff`, `event_rate_threshold`,
`conditional_w1_per_component`, `conditional_component_scales`,
`conditional_scaled_distance_threshold`, `n_events_oc`, `n_events_karr` (the
last three added alongside `per_component_scaled`'s additions for the same
reason). Missing/malformed → `MISSING_EVALUATOR`.

Event-rate verdict is `PASS` iff `event_rate_diff <= event_rate_threshold`.
Each conditional component is independently re-scored exactly like
`per_component_scaled` above (`conditional_w1_per_component[name] /
max(conditional_component_scales[name], 1e-12)` vs
`conditional_scaled_distance_threshold`), never from the stored
`component_verdicts`. If the channel is primary and `n_events_oc == 0 and
n_events_karr == 0` (the event never fired on **either** side across the
whole ensemble) → `PRIMARY_CHANNEL_VACUOUS`: the runner's own
`per_component`/`hurdle` calculation forces every conditional distance to a
trivial `0.0` in that case (there is nothing to compare), so its
`joint_verdict` is a vacuous `PASS` that this re-derivation refuses to
launder into green. Otherwise the channel verdict is `PASS` iff the
event-rate check and every conditional component all pass.

### 6.4 `fva_feasibility` (Metabolism substrates, when FVA-gated)

Raw source: the channel payload's own `fva_feasible_pairs`,
`fva_pairs_total`, `fva_threshold`, `fva_tolerance`,
`fva_feasibility_fraction` fields (all pre-existing runner output; no
schema addition needed). Missing field → `MISSING_EVALUATOR`; negative or
non-finite counts → `MISSING_EVALUATOR`; `fva_pairs_total <= 0` → `FAIL`
(feasibility is undefined, never a vacuous pass); `fva_feasible_pairs >
fva_pairs_total` → `FAIL`. The stored `fva_feasibility_fraction` is never
trusted directly for the gate -- it is independently recomputed as
`fva_feasible_pairs / fva_pairs_total`, and a stored value that disagrees
with the recomputation (outside floating-point tolerance) → `FAIL` (an
inconsistent stored fraction is itself treated as untrustworthy evidence,
not silently ignored). Otherwise: `PASS` iff the recomputed fraction
`>= fva_threshold`.

### 6.5 Any other aggregation string

→ `MISSING_EVALUATOR`, naming the unrecognized aggregation. No mechanical
re-derivation evaluator has been implemented for it yet; the row is
non-green rather than falling back to whatever the runner claimed. (As of
this writing this only affects `DNADamage`, whose `event_class` harness
does not exist yet -- see gap #2 in section 9 -- so it never reaches this
evaluator with real evidence in the first place.)

Process-level re-derivation additionally checks, independent of any stored
verdict:

- **N/M mismatch**: `len(result.seeds)` vs catalog `N_seeds`, and
  `result.ticks` vs catalog `M_ticks`. This is the mechanism that catches an
  old evidence directory generated at `M=10` being presented against a
  catalog that now specifies `M=100` for that process.
- **Sentinel warnings**: any warning string starting with
  `KARR_SINGLE_SEED_REUSED`, `TRIVIAL_RNG_LEAK`, or
  `PRIMARY_CHANNEL_ORACLE_LAUNDERING` unconditionally demotes to non-green.
- **Deterministic-convergence demotion**: a
  `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` warning (the runner's
  FAIL→informational demotion when `closed_form_dominant` is `confirmed*`)
  is treated as non-green **unless** `result.json["h12_evidence_ref"]` points
  at a real file whose `nontrivial_sample_count` is a positive number. The
  catalog's `closed_form_dominant` flag alone is never sufficient.
- **DEFERRED**: if the process or any channel verdict is `DEFERRED`, the row
  requires `result.json["decision_ref"]` and a resolvable
  `result.json["alternate_evidence_ref"]`; regardless, a `DEFERRED` row is
  **always** non-green. No `DEFERRED` counts as `PASS`.
- **Current-tree staleness**: every `input_manifest.json["inputs"]` entry's
  recorded sha256 is recompared against the file's *current* sha256 on disk;
  drift → `STALE_VS_TREE`, naming the exact path.

## 7. `evidence_index.json` top-level schema

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "content_hash": "sha256 over the full payload, EXCLUDING generated_at and content_hash itself",
  "catalog_path": "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
  "catalog_sha256": "...",
  "evidence_root": "artifacts/l2_2_gates",
  "n_in_scope": 22,
  "aggregate_verdict": "GREEN | NON_GREEN",
  "tally": {"MISSING_EVIDENCE": 22},
  "rows": [ /* one per in-scope process, see section 5 */ ]
}
```

`content_hash` is deterministic: computed over a canonical
(`sort_keys=True`, no extra whitespace) JSON dump of the payload with
`generated_at` and `content_hash` itself removed first, so regenerating
against an unchanged tree/catalog produces a byte-identical hash even though
the timestamp differs between runs.

## 8. Integrity (`generator.py audit`) vs acceptance (`--require-all-pass`)

`audit` does **not** trust anything already written to `evidence_index.json`
— it rebuilds the index from scratch (mechanically re-deriving every
verdict per section 6) and diffs the result against the tracked file
(ignoring `generated_at`). Any hand-edit, stale commit, forged
`content_hash`, or missing/extra row shows up as a diff. This is the sole
tamper defense; there is no code path where the stored index's own claims
about itself are trusted.

- **Exit 0**: tracked index matches a fresh regeneration. Aggregate verdict
  may legitimately be `NON_GREEN` — that is today's honest state, not a
  failure of this test.
- **Exit 1**: tracked index does NOT match a fresh regeneration (hand-edit /
  stale / tamper). Fix by running `generate` and committing the refresh.
- **Exit 2** (only with `--require-all-pass`): integrity is fine, but the
  aggregate verdict is not `GREEN`. This is the acceptance gate. It is
  **expected to fail today** and is not wired into CI as a blocking check
  yet — activating it is a separate, later commit made only after Karr
  oracle extraction closes and real per-process evidence is generated.

## 9. What still needs to happen before real GREEN rows (known gaps)

None of this is done by this task, and none of it is faked here:

1. **Populate real evidence.** Two sub-steps:
   (a) merge the now-complete raw Karr oracle extraction (was split across
   sibling worktrees) into `data/m1_sources/karr_native/` via
   `scripts/l22_evidence/populate.py --apply` — **done (2026-07-28)**: all
   16 generic `design_a_per_tick` processes (11 clean + 5 stale-regenerated)
   are now populated at 50 seeds each, plus the pre-existing 2 specialized
   Transcription/Translation ensembles, for the full 18; see Section 10 for
   detail and provenance.
   (b) run `tests/vivarium/l2_2_design_a_runner.py` for each of the 18
   `design_a_per_tick` processes against
   `artifacts/l2_2_gates/<Process>/latest/` to produce actual
   `result.json`/`input_manifest.json`/`provenance.json` evidence —
   **partially done (2026-07-28)**: 14/18 processes now have real evidence
   (7 mechanically PASS, 7 mechanically FAIL); see Section 11 for the full
   sweep execution, per-process breakdown, and what remains open
   (`Metabolism` still executing; `DNARepair`/`ProteinDecay`/
   `ReplicationInitiation` blocked on a real oracle-tick-depth shortfall).
2. **Build the L2.event harness** for the 4 `event_class` processes; until
   then they remain `MISSING_EVIDENCE` by construction.
3. **Mechanical evaluators for projection-distance primary channels** —
   **done (2026-07-28)**: `per_component_scaled` (`Replication`,
   `DNASupercoiling`) and `hurdle_event_rate_plus_conditional_scaled_distance`
   (`DNARepair`) are now mechanically re-derived from raw metric/threshold
   fields per section 6.2/6.3, once real evidence exists for those
   processes (still blocked on gap #1(b) above). `DNADamage` remains
   `MISSING_EVIDENCE` until the `event_class` harness in gap #2 exists —
   its projection aggregation was never run through this evaluator with
   real evidence either way.
4. **Null-control-must-fail canary, pre-registered/null-derived thresholds,
   H12 evidence generation, hint-off proof, reproducibility canary** — the
   schema has fields ready for these (`h12_evidence_ref`, `decision_ref`,
   `alternate_evidence_ref`, sentinel warning re-derivation) but no process
   has them populated yet.
5. **CI wiring of `--require-all-pass`** as a blocking acceptance gate —
   deliberately deferred to a follow-up activation commit, per this task's
   explicit two-stage requirement.

## 10. Raw oracle population (`scripts/l22_evidence/populate.py`)

**Status (2026-07-28): real population EXECUTED.** Full Design-A Karr
oracle extraction was split across two raw-extraction sibling worktrees
(`clean11` = `E:\opencell-worktrees\l22-full-extract`, `stale5` =
`E:\opencell-worktrees\l22-stale5-regen`), plus the pre-existing specialized
Transcription/Translation ensembles already present in the current tree.
That raw oracle data has now been merged into the current repo's fixed
oracle location (`data/m1_sources/karr_native/`, the same path
`tests/vivarium/_l2_2_design_a_runner_helpers.py::load_karr_oracle` reads
from) -- a distinct, earlier step from actually running the runner and
generating `result.json`/etc evidence (still open, see Section 9 #1(b)).

`populate.py` performs that merge, conservatively:

- Accepts named source worktree roots explicitly via repeated
  `--source NAME=PATH` (e.g. `--source clean11=E:\opencell-worktrees\l22-full-extract
  --source stale5=E:\opencell-worktrees\l22-stale5-regen`). The current repo
  tree is always an implicit source named `current` -- no flag needed for
  data that's already in place (e.g. the specialized Transcription/
  Translation ensembles).
- **Per-source process allowlist scoping (`SourceRoot.allowed_processes`,
  CLI `--source-scope NAME=Proc1,Proc2,...`).** A source with no scope is
  unrestricted (appropriate only for the implicit `current` source); any
  accepted-oracle worktree source MUST be scoped explicitly so it can never
  silently supply data for a process outside its mechanically-derived
  accepted set -- this is what prevents e.g. clean11's own stale, pre-regen
  canonical seed0 for a stale5-owned process from ever being selected, even
  though the file is physically present in clean11's tree (both worktrees
  independently extracted canonical seed0 for all 16 generic processes
  before the 5-process schema-drift blocker was discovered; only stale5's
  copies of those 5 are authoritative post-regen). Scoped-out sources are
  dropped entirely before any file is even observed for a given process.
- For each of the 18 `design_a_per_tick` processes, walks the two known raw
  layouts (`per_process_traces_v2[_s{NNN}]/` and
  `ensembles/<process_lower>/seed_{NNN}/` + `MANIFEST.json`) across every
  *eligible* (scope-passing) source, and classifies:
  - `RESOLVED`: the merged file set (combining sources is fine -- e.g. seeds
    0-24 from one root and 25-49 from another) reaches the catalog's
    required seed count with no disagreement.
  - `SPLIT_CONFLICT`: the same relative path exists in more than one
    eligible source with **different** content -- named explicitly (path +
    source names + hash prefixes), never silently resolved by picking one
    side. Byte-identical duplicates across sources are fine (deterministic
    lexicographically-first-source selection).
  - `MANIFEST_MISMATCH`: an `ensembles/.../MANIFEST.json` disagrees with the
    actual merged seed-file count -- never trusted at face value.
  - `INSUFFICIENT_DATA`: fewer seeds than the catalog requires even after
    merging every eligible source.
- `--apply` is the only mode that copies files and writes the tracked
  `oracle_population_manifest.json` (source names/paths/git SHAs -- resolved
  for every source, including linked worktrees whose `.git` is a Windows-style
  `gitdir:` pointer file (e.g. `gitdir: E:/opencell/.git/worktrees/<name>`):
  `_git_sha` translates that pointer to its WSL `/mnt/<drive>/...` mount
  equivalent and reads the worktree-specific gitdir directly via
  `git --git-dir=<resolved> rev-parse HEAD`, falling back to plain
  `git -C <path> rev-parse HEAD` for ordinary (non-worktree) repos; `git_sha`
  is `null` only when `path` genuinely isn't a git repository at all -- and
  per process: layout, seed count, and per-file source attribution + hash).
  It refuses outright unless
  **every** requested process is `RESOLVED` -- no partial population -- and
  refuses to overwrite an existing destination file whose content differs
  from the resolved source (never silently clobbers local data). Without
  `--apply` it is a pure dry-run/readiness report with no side effects,
  still exiting nonzero if anything is unresolved.
- **Destination-matrix validation (`validate_destination()`, CLI
  `--check-destination`).** Verifies the v2-layout destination directories
  (canonical `per_process_traces_v2/` for seed 0 -- the sole authoritative
  location, per the hard no-competing-`_s000` policy -- plus
  `per_process_traces_v2_s{001..049}/`) contain EXACTLY the expected
  process x seed matrix: no missing files, and no extra/unexpected `.mat`
  files (the "do not copy whole seed directories blindly" failure mode,
  where a stray wrong-process file leaks in). One known, pre-existing,
  tracked, harmless exception is named explicitly and ignored rather than
  silently excluded from the check entirely:
  `per_process_traces_v2_s001/Translation_100ticks.mat`, a single stray
  file committed during the Phase 2 seed-1 schema preflight (commit
  `cc66914`) that is inherited unchanged into every worktree descended from
  it (current tree, clean11, stale5 alike) -- it is harmless because
  `load_karr_oracle` always prefers Translation's 50-seed `ensembles/`
  layout over this lone v2 file by seed count, and this task must not
  delete/modify tracked raw MAT evidence. Runs standalone (read-only) or,
  combined with `--apply`, immediately after the copy to confirm the
  result.

**Real population executed (2026-07-28), commit `<see git log>`:** ran
`populate.py --source clean11=... --source stale5=... --source-scope
clean11=<11 clean process names> --source-scope stale5=<5 stale process
names> --processes <all 16> --apply --check-destination` against the real
`clean11`/`stale5` worktrees. Result: all 16 processes `RESOLVED` (50/50
seeds each) from their scoped sources with zero `SPLIT_CONFLICT`/
`MANIFEST_MISMATCH`/`INSUFFICIENT_DATA`; 800 files copied (16 x 50);
post-apply `--check-destination` reported `OK: exact matrix present, no
unexpected extras` (with the one known Translation stray correctly
ignored, not silently unchecked). Independently re-verified by calling the
real `load_karr_oracle()` for all 18 `design_a_per_tick` processes (16
generic + Transcription + Translation): every one reports
`canonical_seed_count=50`, `warnings=None`. The 11 clean process names:
`DNARepair, DNASupercoiling, MacromolecularComplexation, Metabolism,
ProteinModification, ProteinProcessingI, ProteinTranslocation,
RNAModification, Replication, ReplicationInitiation, tRNAAminoacylation`.
The 5 stale-regenerated process names: `ProteinDecay, ProteinFolding,
ProteinProcessingII, RNADecay, RNAProcessing`. The populated `.mat` data is
git-ignored (`.gitignore` lines 35-40) and therefore not committed; only
`docs/phase_f/l2_2_design_a/oracle_population_manifest.json` (per-file
hash/source provenance) is tracked.

Running `generate`/`audit` against the tree at the time this population
step landed (before the sweep in Section 11) correctly reported
`MISSING_EVIDENCE` for all 22 in-scope processes and aggregate
`NON_GREEN` — raw oracle population makes the runner *able* to execute; it
does not itself produce `result.json`/`input_manifest.json`/
`provenance.json` runner evidence. See Section 11 for the runner sweep
that followed.

**`git_sha` fix and manifest regeneration (2026-07-28):** every worktree in
this repo (main checkout and all `E:\opencell-worktrees\*` linked
worktrees, including `clean11`/`stale5`) has a `.git` FILE containing an
absolute Windows-style `gitdir: E:/opencell/.git/worktrees/<name>` pointer.
Native Windows git resolves this transparently; WSL/Linux git cannot (it
treats `E:/...` as a relative fragment and fails with "not a git
repository"), so `_git_sha()` originally recorded `null` for every source
when invoked from WSL. Fixed by translating the pointer's target to its
WSL `/mnt/<drive>/...` mount equivalent and reading it directly via
`git --git-dir=<resolved> rev-parse HEAD`, falling back to the original
`git -C <path> rev-parse HEAD` for ordinary (non-worktree) repositories;
`git_sha` remains explicitly `null` only when `path` genuinely isn't a git
repository. The tracked manifest was regenerated against the
already-populated destination (idempotent re-run: 0 files copied, all 16
processes still `RESOLVED` 50/50, destination check still `OK`) with
`--source-scope current=Transcription,Translation` added so the
already-copied `current`-tree bytes cannot out-rank `clean11`/`stale5` in
the per-file source-attribution tie-break now that the destination already
holds identical copies -- preserving the original, correct provenance
attribution while only changing `git_sha`/`generated_at`. Resulting
non-null SHAs: `clean11` = `a7233a5a7fcc9a50310dcc6620828a192d01b7f5`,
`stale5` = `2d8f06a6bdce84ff24ff94e141f67713814211a3`, `current` = HEAD at
generation time.

## 11. Real Design-A runner sweep (2026-07-28)

**Tooling:** `scripts/l22_evidence/sweep.py` drives the existing,
unmodified `tests/vivarium/l2_2_design_a_runner.py` across the 18
`design_a_per_tick` processes at their real catalog `M_ticks`/`N_seeds`
(never a reduced count), writing to `artifacts/l2_2_gates/<Process>/latest/`
— the exact layout the generator already reads. `plan_sweep()` derives jobs
mechanically from the catalog; `evidence_is_valid()` resumes only by
parsing and matching `result.json`/`input_manifest.json` fields against the
request (never existence-only); `run_job()`/`run_sweep()` execute a bounded
number of runner subprocesses concurrently via `ThreadPoolExecutor`, with
disjoint per-process output/log paths and real captured exit codes;
`status_snapshot()`/`write_status_snapshot()` are a read-only inspector
(never touches a running process) used for honest interim progress
reporting on a sweep that spans multiple sessions. CLI: `sweep.py plan`,
`sweep.py run [--max-workers N] [--force]`, `sweep.py status`.

**Execution:** ran with `--max-workers 2` initially (per instructions),
confirmed stable (load average ~2.1, 27 GiB free RAM on a 16-core WSL2
box), then escalated to `--max-workers 4` (confirmed stable: load average
~4.25, memory usage stayed under 3 GiB). `Metabolism` was deliberately left
in the same run as the other 17 so its single worker slot runs in the
background without blocking the rest.

**Results as of this commit** (14/18 processes have real evidence; see
`docs/phase_f/l2_2_design_a/sweep_status.json` for the live interim
snapshot and `docs/phase_f/l2_2_design_a/evidence_index.json` for the
mechanically re-derived verdicts):

| Process | Real result | Mechanical verdict | Note |
|---|---|---|---|
| DNASupercoiling | ran, stored PASS | `FAIL` | `MISSING_EVALUATOR` — a real `per_component_scaled` re-derivation evaluator now exists (`29749df`), but this process's `result.json` predates the additive raw fields (`scaled_distance_threshold`, `component_n_nonzero_oc/karr`) it needs, so it is honestly non-green pending a re-run |
| Replication | ran, stored PASS | `FAIL` | same stale-artifact gap as DNASupercoiling |
| MacromolecularComplexation | ran, stored PASS | `FAIL` | `SENTINEL_FAIL` — demoted `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` warning with no linked H12 evidence |
| ProteinFolding | ran, stored PASS | `FAIL` | same H12-less demotion |
| ProteinProcessingI | ran, stored PASS | `FAIL` | same H12-less demotion |
| ProteinProcessingII | ran, stored PASS | `FAIL` | same H12-less demotion |
| tRNAAminoacylation | ran, stored PASS | `FAIL` | same H12-less demotion |
| ProteinModification | ran, stored PASS | `PASS` | real mechanical PASS, no demotion warning |
| ProteinTranslocation | ran, stored PASS | `PASS` | real mechanical PASS |
| RNADecay | ran, stored PASS | `PASS` | real mechanical PASS |
| RNAModification | ran, stored PASS | `PASS` | real mechanical PASS |
| RNAProcessing | ran, stored PASS | `PASS` | real mechanical PASS |
| Transcription | ran, stored PASS | `PASS` | real mechanical PASS (specialized ensemble path) |
| Translation | ran, stored PASS | `PASS` | real mechanical PASS (specialized ensemble path) |
| DNARepair | **runner exited before writing evidence** | `MISSING_EVIDENCE` | real data gap: `Requested 200 ticks, but oracle only provides 100` — catalog M_ticks=200, populated oracle only has 100 ticks |
| ProteinDecay | same runner exit | `MISSING_EVIDENCE` | same 200-vs-100-tick oracle shortfall |
| ReplicationInitiation | same runner exit | `MISSING_EVIDENCE` | same 200-vs-100-tick oracle shortfall |
| Metabolism | **still executing** | `MISSING_EVIDENCE` | FVA (LP-per-sample) metric is a severe cost outlier; empirically >16h estimated for 50x20 samples; left running in the background (see Section 11.1) |

Aggregate: `NON_GREEN` (`PASS: 7`, `FAIL: 7`, `MISSING_EVIDENCE: 8` — the 8
includes the 3 oracle-shortfall processes, `Metabolism`, and the 4
out-of-scope `event_class` processes). Nothing here was patched: every
`FAIL`/`MISSING_EVIDENCE` above is the generator's honest mechanical
re-derivation from raw channel data and catalog scope, not a hand edit.

**Known gaps this sweep surfaces (not fixed by this task):**

1. **Oracle tick-depth shortfall for 3 processes** (`DNARepair`,
   `ProteinDecay`, `ReplicationInitiation`, all catalog `M_ticks=200`): the
   currently-populated `.mat` oracle data only has 100 ticks per seed. This
   needs a re-extraction/re-population of these 3 processes at the correct
   tick depth in a follow-up task — it is a raw-data availability gap, not
   a catalog or runner bug, and neither the catalog nor the runner should
   be changed to paper over it.
2. **`DNASupercoiling`/`Replication` artifacts are stale relative to the now
   -implemented `per_component_scaled` evaluator.** `29749df` (cherry-picked
   from local `main` into this branch) implements real mechanical
   re-derivation for `per_component_scaled` (also
   `hurdle_event_rate_plus_conditional_scaled_distance` for `DNARepair` and
   `fva_feasibility` for `Metabolism`), additively extending
   `tests/vivarium/_l2_2_design_a_projections.py` to emit the raw fields
   (`scaled_distance_threshold`, `component_n_nonzero_oc/karr`, and the
   `DNARepair`-side `conditional_scaled_distance_threshold`/`n_events_oc/karr`
   equivalents) the evaluator needs to avoid trusting the stored
   `joint_verdict` string. `DNASupercoiling` and `Replication` ran under this
   sweep *before* that additive schema change, so their `result.json` lacks
   these fields; the evaluator correctly reports a named
   `MISSING_EVALUATOR` reason (missing raw fields) rather than silently
   falling back to the stale stored `PASS`. Per this task's explicit
   constraint ("do not rewrite already-generated runner artifacts"), these
   two processes were not re-run in this commit — a follow-up re-run of just
   these two (fast: ~20-30 min each per Section 11's original sweep timing)
   will pick up the new fields and let the real evaluator produce an actual
   PASS/FAIL. `fva_feasibility` needed no schema change, so once `Metabolism`
   finishes its current run its raw fields will already support real
   re-derivation without a second run. This is unrelated to the still
   -unbuilt `DNADamage` event_class harness gap tracked in Section 9 #3.
3. **5 processes are blocked on H12 evidence** for their demoted
   `PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` warning
   (`MacromolecularComplexation`, `ProteinFolding`, `ProteinProcessingI`,
   `ProteinProcessingII`, `tRNAAminoacylation`) — this is the contract
   working exactly as designed (Section 8's later-hardening requirement),
   not a bug.
4. **`Metabolism`'s FVA metric is a severe cost outlier** — see Section
   11.1.
5. **Runner's own `provenance.json["git_sha"]` reads `"unknown"`** for
   every process run in this sweep: `tests/vivarium/l2_2_design_a_runner.py`
   has the same Windows-worktree-`.git`-pointer resolution bug already
   fixed in `populate.py` (Section 10), but the runner is explicitly
   off-limits to modify in this task ("store runner-native outputs
   unchanged") — flagged here as a known, separate, pre-existing runner
   bug, not silently patched.

### 11.1 Metabolism: a real, unresolved cost outlier

`Metabolism`'s primary metric path uses flux-variability analysis (FVA) —
an LP solve per (seed, tick) sample via GLPK — which is drastically more
expensive than the vector-W1-distance metric every other process uses. A
timing probe (2 seeds x 20 ticks = 40 samples) did not complete in 40+
minutes of real wall-clock time (confirmed alive via `ps aux`, ~97% CPU,
not hung), implying the real 50-seed x 20-tick = 1000-sample run is on the
order of 16+ hours. This is inherent to the metric definition, not
something to work around by reducing seeds/ticks below the catalog values
or by algorithmic shortcuts — the task's requirements explicitly anticipate
this class of process may need to run past a single session. As of this
commit `Metabolism` is running under PID (WSL) tracked in
`artifacts/l2_2_gates/_sweep_logs/Metabolism.log` (gitignored, regenerable)
and is safely resumable: re-running `sweep.py run` will skip every already
-valid process and only continue `Metabolism` (or, if it crashed, restart
it cleanly — `evidence_is_valid()` never trusts partial/missing output).

## 12. Files

- `scripts/l22_evidence/catalog.py` — catalog access (scope derivation).
- `scripts/l22_evidence/schema.py` — versioned constants (paths, required
  files, status vocabulary).
- `scripts/l22_evidence/verdict.py` — mechanical per-channel/per-process
  verdict re-derivation.
- `scripts/l22_evidence/generator.py` — `build_evidence_index()`, `audit()`,
  CLI (`generate`, `audit [--require-all-pass]`).
- `docs/phase_f/l2_2_design_a/evidence_index.json` — the one tracked
  generator output. **Never hand-edit.**
- `tests/vivarium/test_l2_2_strict_rubric.py` — now asserts index integrity
  + honest current non-green state (replaces `EXPECTED_L2_2_VERDICTS`).
- `scripts/probe_l2_2_strict_audit.py` — now a thin human-readable reporter
  over the evidence index (replaces `EMPIRICAL_VERDICTS`/`classify_l2_2`).
- `scripts/l22_evidence/populate.py` — raw oracle source-root
  merge/validation tool with per-source process allowlist scoping
  (`--source-scope`) and destination-matrix validation
  (`--check-destination`); `--apply` copies + writes
  `docs/phase_f/l2_2_design_a/oracle_population_manifest.json` (see
  Section 10). **Executed against real data 2026-07-28** (16 processes,
  800 files, all `RESOLVED`, destination check OK).
- `tests/scripts/test_l22_evidence_populate.py` — synthetic-fixture tests
  for `populate.py` (28 tests, including source-scoping and
  destination-validation coverage).
- `docs/phase_f/l2_2_design_a/oracle_population_manifest.json` — tracked
  per-file hash/source-attribution provenance from the real population run.
  Not hand-edited; regenerated by `populate.py --apply`.
- `scripts/l22_evidence/sweep.py` — resumable, bounded-parallel Design-A
  runner sweep launcher (`plan`/`run`/`status` CLI); see Section 11.
  **Executed against real data 2026-07-28** (14/18 processes with real
  evidence; `Metabolism` still running).
- `tests/scripts/test_l22_evidence_sweep.py` — 27 tests: real-catalog
  `plan_sweep()` derivation, resume-by-validation semantics, bounded
  parallelism, exit-code capture, compact report/status writers, CLI
  smoke tests — all against fake fast command builders, never the real
  slow runner.
- `docs/phase_f/l2_2_design_a/sweep_status.json` — tracked, compact,
  read-only interim progress snapshot (one row per process: valid/log
  state, stored verdict for human context). Regenerate with
  `sweep.py status`; safe to run while a real sweep is still executing.
