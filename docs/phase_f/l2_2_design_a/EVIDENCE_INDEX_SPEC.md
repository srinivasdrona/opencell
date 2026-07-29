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
│   │   ├── thresholds.json        # required sidecar (runner writes unconditionally)
│   │   ├── null_calibration.json  # required sidecar (runner writes unconditionally)
│   │   ├── SUMMARY.json           # required sidecar (runner writes unconditionally)
│   │   ├── analytical_check.json  # required sidecar ({"applicable": false, ...} when N/A)
│   │   ├── sweep_provenance.json  # required completion sentinel -- written by sweep.py, NOT the runner (see Section 13.1)
│   │   └── allocator_inputs.json  # informational only -- never required, never bundled, never hashed (see Section 13.7)
│   └── latest_event/      # event_class harness evidence (L2.event; not yet built)
```

`artifacts/` is gitignored (regeneratable); the raw evidence directories are
NOT expected to be committed. `docs/phase_f/l2_2_design_a/evidence_index.json`
(this generator's output) IS the tracked artifact — it records artifact
hashes and status, not the raw channel data itself. Since `artifacts/` is
gitignored, a fresh clone has no authority files at all under this path;
`docs/phase_f/l2_2_design_a/evidence_bundle/` is a tracked, portable
mirror that closes this gap — see Section 12.

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
  "artifact_hashes": {"result.json": "...", "provenance.json": "...", "thresholds.json": "...", "null_calibration.json": "...", "SUMMARY.json": "...", "analytical_check.json": "...", "sweep_provenance.json": "..."},
  "channel_verdicts": {"substrates": "PASS"},
  "warnings": [],
  "provenance_git_sha": "...",
  "sweep_provenance": {"git_sha": "...", "git_dirty": false, "evaluator_schema_version": 1},
  "reasons": [],
  "mechanical_verdict": "PASS",
  "green": true
}
```

`input_manifest.json` is deliberately EXCLUDED from `artifact_hashes` (see
Section 13.4 for why) even though it is still read and mechanically
checked for current-tree staleness like every other input. `warnings` is
the verbatim `result.json["warnings"]` list, always present (possibly
empty) regardless of whether any warning is gating — see Section 13.3.
`sweep_provenance` is an informational sub-object surfacing the sentinel's
own fields (not itself gating beyond what Section 13 already checks; see
13.7 for which of its fields are gating vs. purely informational).

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
| `PASS` | Evidence present, schema valid, hashes current, N/M match, every gateable channel mechanically re-derives to `PASS`/`SEED_NOISE`, no sentinel warnings, no unsupported `DEFERRED`/H12 claims, and `sweep_provenance.json` is present/current (see Section 13). | **yes** |
| `MISSING_EVIDENCE` | One or more of the mandatory files (`result.json`/`input_manifest.json`/`provenance.json`/`thresholds.json`/`null_calibration.json`/`SUMMARY.json`/`analytical_check.json`/`sweep_provenance.json`) is absent -- including evidence generated before the provenance hardening landed, which never wrote `sweep_provenance.json` and is therefore honestly demoted here rather than grandfathered in. | no |
| `SCHEMA_INVALID` | A mandatory file exists but is not parseable JSON, or `result.json` has no channel marked `is_primary`. | no |
| `NO_GATEABLE_CHANNELS` | Every channel is `EVENT_CHANNEL_DEFERRED` or `INSUFFICIENT_SAMPLES`. | no |
| `FAIL` | Any other non-green condition (raw `w1 > threshold`, `NM_MISMATCH`, `STALE_VS_TREE`, `STALE_SWEEP_PROVENANCE` (see Section 13), `SENTINEL_FAIL`, `MISSING_EVALUATOR`, `PRIMARY_CHANNEL_VACUOUS`, `PROCESS_NAME_MISMATCH`, `DEFERRED`). See `reasons[]` for exactly which. | no |

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
   **partially done (2026-07-28), then demoted by the Section 13 hardening**:
   14/18 processes had real evidence (9 mechanically PASS, 5 mechanically
   FAIL) as of the 2026-07-28 sweep (see Section 11 for the execution
   narrative and per-process breakdown), but none of that evidence carries
   a `sweep_provenance.json` completion sentinel (it predates the sentinel's
   existence), so as of the Section 13 hardening **all 22 rows are honestly
   `MISSING_EVIDENCE`** — this is a deliberate, correct demotion (per this
   task's "if not provable, mark stale and schedule rerun rather than
   infer" requirement), not a regression. Re-running each process through
   the hardened `sweep.py run_job` (which writes the sentinel atomically
   after validating all mandatory sidecars) is the remaining Phase B work;
   `Metabolism` was still executing as a raw (non-sweep-wrapped) subprocess
   at the time of this hardening commit and must also be re-run through
   `sweep.py` (or have its evidence re-validated and a provable sentinel
   attached) once it completes; `DNARepair`/`ProteinDecay`/
   `ReplicationInitiation` remain additionally blocked on a real
   oracle-tick-depth shortfall independent of the sentinel gap.
2. **Build the L2.event harness** for the 4 `event_class` processes; until
   then they remain `MISSING_EVIDENCE` by construction.
3. **Mechanical evaluators for projection-distance primary channels** —
   **done (2026-07-28)**: `per_component_scaled` (`Replication`,
   `DNASupercoiling`) and `hurdle_event_rate_plus_conditional_scaled_distance`
   (`DNARepair`) are now mechanically re-derived from raw metric/threshold
   fields per section 6.2/6.3. `Replication`/`DNASupercoiling` were
   re-run 2026-07-28 with the additive raw fields and produced a real
   mechanical `PASS` at the time — however, per gap #1(b) above, that
   evidence now reads as `MISSING_EVIDENCE` pending a sentinel-carrying
   rerun through the hardened sweep; the evaluator logic itself is
   unaffected and remains correct. `DNARepair` remains `MISSING_EVIDENCE`
   pending gap #1(b)'s oracle-tick-depth shortfall. `DNADamage` remains
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
6. **Oracle `.mat` file portability across clones** — the raw
   `data/m1_sources/karr_native/` oracle data remains gitignored by
   pre-existing project convention (large raw data). **Partially closed
   (Section 13.8, R3):** a genuinely fresh clone's `audit()` no longer
   needs the oracle data physically present — `_check_current_tree_
   staleness` classifies each `input_manifest.json["inputs"]` entry as
   `"oracle_data"` vs `"code"` and, by default, trusts the one-time
   `sweep_provenance.json["inputs_verified"]` attestation (recorded when
   the data WAS mounted, at generation time) for the oracle-data entries
   instead of requiring them on disk; `"code"` entries (runner/helpers/
   projections/catalog) are always rehashed regardless. `--verify-input-
   files`/`strict_input_files=True` opts back into physically requiring
   and rehashing the oracle data when it genuinely is mounted (e.g. local
   dev with the full oracle checked out). What remains open: the *default*
   audit still cannot prove oracle-content drift when the data is absent —
   it is trusting the attestation, not re-verifying it; only strict mode
   re-verifies.

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

**Results as of the 2026-07-28 sweep execution** (14/18 processes had real
evidence at that time; see `docs/phase_f/l2_2_design_a/sweep_status.json`
for the interim snapshot from that run). **This table is now historical
narrative, not the current state of `evidence_index.json`.** The Section
13 provenance hardening (added in a later commit) requires every row to
carry a `sweep_provenance.json` completion sentinel written atomically by
`sweep.py run_job`; none of the runs below were launched through that
sentinel-writing code path (it did not exist yet), so as of the hardening
commit **all 18 in-scope rows below (plus the 4 out-of-scope `event_class`
rows) honestly read `MISSING_EVIDENCE`** in the live `evidence_index.json`,
regardless of what the table says the mechanical verdict was at the time.
Re-running each process through the hardened `sweep.py` (Phase B, not yet
done) is required to re-earn a real `PASS`/`FAIL` row; the table is
retained to document the runner behavior, timings, and per-process
oracle/evaluator findings from that execution, which remain valid:

| Process | Real result | Mechanical verdict | Note |
|---|---|---|---|
| DNASupercoiling | rerun 2026-07-28 (post-`29749df`), stored PASS | `PASS` | targeted re-run with the cherry-picked `per_component_scaled` evaluator schema now produces a real mechanical PASS (see gap #2 resolution below) |
| Replication | rerun 2026-07-28 (post-`29749df`), stored PASS | `PASS` | same targeted re-run, same real mechanical PASS |
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

Aggregate at the time of that sweep: `NON_GREEN` (`PASS: 9`, `FAIL: 5`,
`MISSING_EVIDENCE: 8` — the 8 includes the 3 oracle-shortfall processes,
`Metabolism`, and the 4 out-of-scope `event_class` processes). Nothing here
was patched: every `FAIL`/`MISSING_EVIDENCE` above was the generator's
honest mechanical re-derivation from raw channel data and catalog scope,
not a hand edit. As noted above, the *current* live aggregate is
`NON_GREEN` (`MISSING_EVIDENCE: 22`) pending the Phase B sentinel-carrying
reruns.

**Known gaps this sweep surfaces (not fixed by this task):**

1. **Oracle tick-depth shortfall for 3 processes** (`DNARepair`,
   `ProteinDecay`, `ReplicationInitiation`, all catalog `M_ticks=200`): the
   currently-populated `.mat` oracle data only has 100 ticks per seed. This
   needs a re-extraction/re-population of these 3 processes at the correct
   tick depth in a follow-up task — it is a raw-data availability gap, not
   a catalog or runner bug, and neither the catalog nor the runner should
   be changed to paper over it.
2. **RESOLVED 2026-07-28: `DNASupercoiling`/`Replication` artifacts were
   stale relative to the newly-implemented `per_component_scaled`
   evaluator.** `29749df` (cherry-picked from local `main` into this
   branch) implements real mechanical re-derivation for
   `per_component_scaled` (also
   `hurdle_event_rate_plus_conditional_scaled_distance` for `DNARepair` and
   `fva_feasibility` for `Metabolism`), additively extending
   `tests/vivarium/_l2_2_design_a_projections.py` to emit the raw fields
   (`scaled_distance_threshold`, `component_n_nonzero_oc/karr`, and the
   `DNARepair`-side `conditional_scaled_distance_threshold`/`n_events_oc/karr`
   equivalents) the evaluator needs to avoid trusting the stored
   `joint_verdict` string. `DNASupercoiling` and `Replication` originally
   ran under this sweep *before* that additive schema change, so their
   `result.json` lacked these fields; the evaluator correctly reported a
   named `MISSING_EVALUATOR` reason (missing raw fields) rather than
   silently falling back to the stale stored `PASS`. A **targeted re-run of
   just these two processes** (`sweep.py run --processes
   DNASupercoiling,Replication --max-workers 2 --force`, at catalog
   `N=50`/`M=100`, without touching the still-running `Metabolism` job) was
   executed 2026-07-28; both completed (`RAN_EXIT_0`, ~37 min and ~32 min
   respectively — see `sweep_report.json`) and their new `result.json`
   files carry the additive raw fields, so the real evaluator now produces
   an actual mechanical `PASS` for both, not a fallback (again, historical:
   per the Section 13 hardening note above, this evidence itself has since
   been demoted to `MISSING_EVIDENCE` pending a sentinel-carrying rerun — the
   evaluator's correctness demonstrated here is unaffected). `fva_feasibility`
   needed no schema change, so once `Metabolism` finishes its current run
   its raw fields will already support real re-derivation without a second
   run. This is unrelated to the still-unbuilt `DNADamage` event_class
   harness gap tracked in Section 9 #3.
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

## 12. Portable evidence bundle (fresh-clone audit)

**Problem this closes:** `EVIDENCE_ROOT` (`artifacts/l2_2_gates`, Section 4)
is fully gitignored — it is the *live* directory the sweep launcher writes
runner-native output to. That is correct for the compact authority files
(cheap to regenerate by re-running the sweep), but it means a fresh clone
that never ran the sweep locally has **no** `result.json`/
`input_manifest.json`/`provenance.json` anywhere, so `generator.py audit`
would see every row as `MISSING_EVIDENCE` regardless of what
`evidence_index.json` claims — the tracked index would not actually be
verifiable from the tracked repo alone.

**Fix:** `docs/phase_f/l2_2_design_a/evidence_bundle/` is a tracked
mirror (same `<Process>/<latest|latest_event>/` layout as `EVIDENCE_ROOT`)
of every mandatory authority + sidecar file (`result.json`,
`input_manifest.json`, `provenance.json`, `thresholds.json`,
`null_calibration.json`, `SUMMARY.json`, `analytical_check.json`,
`sweep_provenance.json`), deliberately **excluding**
`schema.INFORMATIONAL_ONLY_FILES`/`BUNDLE_EXCLUDE_FILES` (currently just
`allocator_inputs.json`, the large raw per-seed/tick array sidecar —
~0.3–1.9 MB per process, never read by `verdict.py` for verdict
re-derivation; its hash+size is instead recorded inside the tracked
`sweep_provenance.json` — see Section 13.1). Every file is a byte-for-byte
copy EXCEPT `input_manifest.json`, whose `inputs[*]["path"]` entries are
normalized to repo-relative POSIX paths before being written into the
bundle (see Section 13.1) — its content (`resolved_seeds`/`m_ticks`) is
still exactly preserved and mechanically checked, only its raw bytes
legitimately differ from the live copy. Populated/refreshed via:

```
bin\oc-py scripts/l22_evidence/generator.py bundle
```

`bundle_process_evidence()` (`generator.py`) never deletes an existing
bundle entry for a process that happens to be locally unavailable in the
current `EVIDENCE_ROOT` — it only adds/overwrites, so a partial local sweep
never regresses a previously-committed, more-complete bundle.

**Fallback resolution:** `schema.default_evidence_root()` is what
`generate`/`audit` use whenever no explicit `--evidence-root` is given: it
prefers the live `EVIDENCE_ROOT` when that directory exists and is
non-empty (the unmodified, pre-existing behavior for local dev iterating
against a real sweep), and falls back to the tracked `BUNDLE_ROOT`
otherwise (the fresh-clone case). Both roots hold byte-identical copies of
every file `generate` actually reads, so this choice never changes which
verdict is produced — only where the bytes are physically read from for a
given invocation.

Because the bytes are identical either way, `content_hash()`/`audit()`
deliberately **exclude** the top-level `evidence_root` field and each row's
`evidence_dir` field from comparison (`_scrub_environment_relative()`):
these record *where this invocation happened to read from*, not durable
evidence identity, and including them would make the same underlying
evidence produce a spuriously different hash/audit result purely because
one invocation read from `artifacts/` and another from
`evidence_bundle/`. For the same reason, `artifact_hashes` never includes
an entry for any `BUNDLE_EXCLUDE_FILES` name (even when the live tree has
it) — otherwise a live-tree-generated row would carry an extra hash a
bundle-sourced regeneration of the identical evidence could never
reproduce. The `MISSING_EVIDENCE` reason string also intentionally omits
the (environment-relative) `evidence_dir` path, naming the process instead.

**Current-tree staleness across clones/worktrees:** separately,
`input_manifest.json["inputs"][*]["path"]` records *absolute* paths rooted
in whatever worktree the runner happened to execute in (off-limits to
change — the runner's own recording behavior). `generator._resolve_input_path()`
tries the recorded absolute path as-is first (same worktree, unmoved —
preserves exact prior staleness-detection behavior); only if that path does
not exist does it fall back to matching the longest path suffix that
resolves to a real file under the *current* `catalog.REPO_ROOT`, so
staleness-checking keeps working when the evidence bundle is read from a
different clone/worktree root than the one that generated it, as long as
the same oracle `.mat`/source files exist somewhere under that root. This
is a generator-side robustness fix only; it never touches the runner's own
path-recording. Note the oracle `.mat` files themselves remain gitignored
by pre-existing project convention (large raw data, not evidence-index
scope) — this fix does not attempt to make them portable, only to keep
staleness-checking from raising a false alarm purely because of *which*
worktree/clone root ran the check.

**Verification:** `tests/scripts/test_l22_evidence_portability.py` proves:
the bundle never contains `BUNDLE_EXCLUDE_FILES` and stays small (compact
JSON only); every process with real live evidence has a bundle entry whose
`result.json`/`provenance.json` are byte-identical and whose
`input_manifest.json` matches semantically with repo-relative paths only;
`audit()` succeeds — with the identical tally/aggregate as the real local
audit — from an isolated temp root containing *only* a copy of the tracked
bundle + tracked index and no `artifacts/l2_2_gates` anywhere under it (the
literal fresh-clone scenario); `default_evidence_root()` falls back to the
bundle when the live tree is absent and still reproduces the identical
tally as the live tree; `default_evidence_root()` still prefers the live
tree when present (no behavior change for local dev); and
`_resolve_input_path()` both prefers an exact still-existing absolute match
and correctly falls back to suffix-matching under a different `REPO_ROOT`
otherwise.

## 13. Provenance hardening: `sweep_provenance.json`, mandatory sidecars, atomic/locked sweep

This section documents the hardening that closed three gaps an earlier
review found in the sweep launcher + evidence bundle: (1) an evidence
directory could look "complete" while never having been checked against
the CURRENT runner/helpers/projections/catalog source files or evaluator
schema version, (2) `sweep.py run` could relaunch and clobber a process a
second, concurrent invocation was already running, and a crash mid-rerun
could destroy previously-valid evidence, and (3) `input_manifest.json`'s
absolute worktree paths would otherwise leak into the tracked bundle.

### 13.1 Mandatory sidecars and `sweep_provenance.json`

`schema.MANDATORY_SIDECAR_FILES` (`thresholds.json`, `null_calibration.json`,
`SUMMARY.json`, `analytical_check.json`) are no longer optional: the runner
unconditionally writes all four for every process (`analytical_check.json`
is `{"applicable": false, ...}` when not applicable, never omitted), so
requiring them is a simplification, not a new obligation on the runner.
Missing any one of them — like missing an authority file — is
`MISSING_EVIDENCE`.

`schema.SWEEP_PROVENANCE_FILE` (`sweep_provenance.json`) is a NEW sidecar,
written by `scripts/l22_evidence/sweep.py` itself (never the runner, and
never hand-edited) only after a run's output passes
`_authority_and_sidecars_match`, and written **last** — its mere presence
in a validated evidence directory is the completion sentinel. It carries:

- `git_sha` / `git_dirty` — the REAL current worktree git state (via
  `populate._git_sha`/`populate._git_dirty`, reusing the already-accepted
  WSL/Windows-linked-worktree gitdir resolution), since the runner's own
  `provenance.json["git_sha"]` is permanently `"unknown"` in this project's
  environment and can never be trusted for staleness. Recorded for human
  inspection; **not itself gating** (see Section 13.7 — scope-corrected:
  `source_hashes`/`evaluator_schema_version` below are the gating
  authority, since Windows-linked-worktree git plumbing is inherently more
  fragile than a plain content-hash comparison).
- `source_hashes` — sha256 of the runner script, the runner helpers
  module, the projections module, and `PROCESS_CATALOG.yaml`
  (`schema.SWEEP_PROVENANCE_SOURCE_FILES`) AS THEY EXISTED when the run
  completed. `evidence_is_valid()`/the generator's
  `_check_sweep_provenance_staleness()` both recompute these RIGHT NOW and
  flag any individually-named drift — e.g. a projection-evaluator fix
  landing after a process's evidence was generated makes that evidence
  stale, without needing a manual audit sweep.
- `evaluator_schema_version` — `verdict.EVALUATOR_SCHEMA_VERSION`, bumped
  whenever `verdict.py`'s mechanical re-derivation logic changes in a way
  that could change a prior verdict; a mismatch is stale.

`allocator_inputs.json` is deliberately NOT tracked or hashed anywhere
(not even here): no verdict calculation ever reads it (it is large
diagnostic bulk, `schema.INFORMATIONAL_ONLY_FILES`), so recording a hash
for it would be authority theater, not evidence — see Section 13.7.

A git-dirty working tree is recorded but NOT gating — active
development on a dirty tree is normal and would otherwise make it
impossible to ever produce valid evidence pre-commit. An unknown/missing
git SHA is likewise non-gating on its own, as long as `source_hashes` and
`evaluator_schema_version` still match the current tree.

### 13.2 Atomicity and per-process locking (`sweep.py run_job`)

Every (re)run writes to a freshly-created TEMP sibling output directory and
log (never the real `<process>/latest/` path directly). Only after the
child exits 0 AND its output passes `_authority_and_sidecars_match` is
`sweep_provenance.json` written into the temp directory and the whole temp
directory atomically swapped into place (`_atomic_replace_dir`); on ANY
failure — nonzero exit, failed-to-start, or exit-0-but-invalid-evidence
(`JOB_STATUS_RAN_INVALID_EVIDENCE`) — the real output directory and log are
left completely untouched, so a crashed or failed rerun never destroys
prior valid evidence. The failed attempt's raw output/log are preserved at
their temp paths for postmortem, referenced in the job result's `reason`.

Because POSIX cannot atomically replace a non-empty directory in one
syscall, the swap is a two-step rename (old dir → `<dir>.prev` backup, then
temp dir → final dir, best-effort backup cleanup). `_recover_crashed_swap()`
runs at the top of both `evidence_is_valid()` and `run_job()`: if the final
directory is missing but its `.prev` backup still exists (a crash between
the two renames), it restores the backup automatically, so a crash mid-swap
never silently loses the last-known-good evidence.

A per-process `O_EXCL` lock file (`.{output_dir.name}.sweep.lock`, disjoint
per process by construction) is held for the duration of a rerun attempt.
A second, independently-launched `sweep.py run` invocation targeting the
SAME process gets `JOB_STATUS_LOCKED_SKIPPED` immediately — it never blocks
and never relaunches the process concurrently; existing evidence (valid or
not) is left completely untouched.

`_cmd_run()`'s exit code: `JOB_STATUS_START_ERROR`, `JOB_STATUS_RAN_FAIL`,
and `JOB_STATUS_RAN_INVALID_EVIDENCE` are ALL hard failures — nonzero exit
regardless of which occurred. `JOB_STATUS_SKIPPED_VALID` and
`JOB_STATUS_LOCKED_SKIPPED` are both legitimate "nothing needed to happen"
outcomes and never cause a nonzero exit on their own.

### 13.3 Warnings are always carried verbatim

`row["warnings"]` is the verbatim `result.json["warnings"]` list, always
present (possibly empty) regardless of whether any entry matches a
gating sentinel prefix. `verdict.rederive_process` only ever *acts* on the
sentinel-matching subset (`KARR_SINGLE_SEED_REUSED`,
`PRIMARY_CHANNEL_ORACLE_LAUNDERING`, etc.) for verdict purposes; a
non-gating warning (e.g. a Translation seed-shift note) must still be
visible in the tracked index rather than silently dropped once it stops
affecting the verdict.

### 13.4 `input_manifest.json` path normalization and the `artifact_hashes` exclusion

`bundle_process_evidence()` normalizes `input_manifest.json["inputs"][*]
["path"]` to repo-relative POSIX paths (via
`generator._normalize_input_manifest_paths`) before mirroring it into the
tracked bundle, so no tracked file ever embeds this machine's absolute
worktree path. Because this legitimately changes the file's raw bytes
between the live tree and the bundle for byte-identical underlying
evidence, `artifact_hashes` excludes `input_manifest.json` entirely (same
precedent as excluding `INFORMATIONAL_ONLY_FILES`) — its content
(`resolved_seeds`/`m_ticks`/`inputs`) remains read and mechanically checked
via `_check_current_tree_staleness()` regardless, so no tamper-evidence is
lost, only a redundant raw-byte hash that would otherwise make
`content_hash` diverge between a live-tree-sourced and a bundle-sourced
generation of the SAME evidence.

### 13.5 Audit content-hash bug fix

`generator.audit()` now unconditionally validates the stored
`content_hash` field against the stored payload, before/outside the
`_strip_volatile(stored) != _strip_volatile(fresh)` branch. Previously this
check was nested inside that branch (and additionally guarded by `if
recorded_hash and ...`), so a payload hand-tampered ONLY in its
`content_hash` field (with everything else still equal to a fresh
regeneration) passed through uncaught. See
`test_l22_evidence_anticheat.py::test_audit_rejects_content_hash_tampered_alone_with_everything_else_untouched`.

### 13.6 Transitional state as of this commit

Every evidence directory currently on disk predates this hardening (none
of it carries `sweep_provenance.json`), so ALL 22 in-scope rows are
honestly `MISSING_EVIDENCE` immediately after this commit — a deliberate,
correct demotion (per this project's "unprovable prior launches must be
marked stale and scheduled for rerun, never inferred as valid" rule), NOT
a regression. Re-populating real PASS/FAIL rows by rerunning the sweep
through the hardened `run_job` is the next (Phase-B) step, tracked
separately from this hardening commit.

### 13.7 Scope correction: content hashes, not git plumbing, are gating authority

A follow-up operator review judged the initial cut of this hardening
over-scoped in two specific ways, and this section documents the
walk-back (implemented in the same commit series, immediately after
13.1–13.6 above landed):

- **git SHA/dirty are informational, not gating.** The original design
  hard-failed any row/job whose `sweep_provenance.json` had an
  unknown/missing real git SHA, independent of whether its recorded
  source hashes matched the current tree. This over-weighted a fragile,
  environment-specific plumbing step (resolving a Windows-linked
  worktree's real HEAD under WSL git) as if it were necessary evidence,
  when the actual proof that evidence matches the code now on disk is the
  `source_hashes`/`evaluator_schema_version` comparison, which does not
  depend on git at all. `git_sha`/`git_dirty` are still recorded on every
  sentinel and still surfaced on every row for human inspection — they
  are simply no longer part of `evidence_is_valid()`'s or
  `_check_sweep_provenance_staleness()`'s pass/fail logic.
- **`allocator_inputs.json` is not tracked or hashed at all.** The
  original design recorded its sha256+size inside `sweep_provenance.json`
  "for tamper-evidence", but no verdict calculation in `verdict.py` ever
  reads this file — it is large raw per-seed/tick diagnostic bulk, not
  gating authority. Tracking a hash nothing ever checks is authority
  theater dressed up as rigor, so `build_sweep_provenance()` no longer
  computes it and the field has been removed from the schema.

Both changes preserve every anti-false-green property this hardening
exists for (tampered/stale evidence is still caught via content hashes;
`allocator_inputs.json` was never part of any verdict computation, so
dropping its tracking removes zero real coverage) while removing gating
surface that mapped to no observed failure mode. Everything else in
13.1–13.6 (mandatory sidecars, the completion sentinel, atomic/locked
force-rerun, warnings-verbatim, the audit content-hash fix,
`source_hashes`/`evaluator_schema_version` staleness) is retained
unchanged.

### 13.8 Sentinel binding, per-process SUT hash, and oracle input-manifest verification (schema v2)

A further review (R1–R3) found `sweep_provenance.json` still had three
gaps even after 13.1–13.7: (R1) it never checked its OWN `process`/
`n_seeds`/`m_ticks`/`completion_status` fields, nor hashed the OTHER
mandatory sidecars (`result.json`/`input_manifest.json`/`provenance.json`/
`thresholds.json`/`null_calibration.json`/`SUMMARY.json`/
`analytical_check.json`) it was meant to attest for — so a sentinel
mechanically copied from a different, already-valid process's evidence
directory (or a hand-edited stored `process`/verdict field with the
sentinel left untouched) was not reliably rejected; (R2) `source_hashes`
covered only the 4 shared runner/helpers/projections/catalog files, never
the per-process `karr_<process>.py` biology module itself, so editing one
process's implementation never staled that process's evidence; (R3)
`_check_current_tree_staleness` never required `input_manifest.json
["inputs"]` to be non-empty or to cover all `n_seeds`, and — since the raw
oracle `.mat` files are gitignored — would always report every input
missing in a fresh clone regardless of whether the evidence was actually
sound. `SWEEP_PROVENANCE_SCHEMA_VERSION` is bumped 1→2 to force every
pre-existing sentinel (none of which carry the new fields) to be honestly
re-evaluated as stale rather than silently grandfathered.

- **R1 — sentinel binds to itself and to every sidecar's bytes.**
  `sweep_provenance.json` now also records `process`, `n_seeds`,
  `m_ticks`, `completion_status` (`"COMPLETE"`), and `sidecar_hashes`: a
  sha256 of every file in `schema.SWEEP_PROVENANCE_SIDECAR_FILES`
  (`REQUIRED_AUTHORITY_FILES + MANDATORY_SIDECAR_FILES`) as they existed
  the instant the sentinel was written. `evidence_is_valid()`/
  `_check_sweep_provenance_staleness()` both check the sentinel's own
  `process`/`n_seeds`/`m_ticks`/`completion_status` against the job/entry
  being validated, AND recompute every `sidecar_hashes` entry against the
  file currently on disk. A sentinel copied verbatim from another process
  fails on the `process` mismatch (and, if that field is hand-edited to
  match, on the `result.json` sidecar hash mismatch — that file's real
  content differs per-process by construction). Any missing/mismatched
  entry is stale, never silently accepted.
  - **`input_manifest.json` normalization moved to generation time.**
    `sidecar_hashes["input_manifest.json"]` initially reintroduced exactly
    the byte-divergence problem Section 13.4 already documents and works
    around for `artifact_hashes`: `run_job` originally wrote
    `input_manifest.json` with the runner's real absolute worktree paths,
    so the R1 sentinel hash was computed from those un-normalized bytes —
    which could never match the bundle's later-normalized (repo-relative)
    copy produced by `bundle_process_evidence()`, permanently failing a
    bundle-sourced audit even for a genuinely valid run. Fixed by adding
    `sweep._normalize_input_manifest_file()`, called in `run_job`
    immediately after `_verify_input_manifest()` succeeds (which still
    needs the original absolute paths, since the oracle data is guaranteed
    mounted at that point) but before `_sanitize_dangling_temp_refs()`/
    `build_sweep_provenance()` compute sidecar hashes. This makes the
    live tree's `input_manifest.json` already repo-relative from the
    moment the sentinel is written, so the bundle's later normalization
    pass is a no-op and `sidecar_hashes["input_manifest.json"]` agrees
    between live tree and bundle from generation onward.
- **R2 — per-process `oc_module` hash.** `catalog.ProcessEntry.oc_module`
  (the catalog row's biology-module path, e.g.
  `opencell/vivarium/karr_dna_repair.py`) is now hashed under a dedicated
  `"oc_module"` key, kept OUT of the shared 4-entry `SWEEP_PROVENANCE_
  SOURCE_FILES` dict and merged in per-call instead — so editing one
  process's `karr_<process>.py` stales ONLY that process's evidence, never
  all 18.
- **R3 — oracle input-manifest verification, default vs strict.**
  `_verify_input_manifest()` (`sweep.py`) rehashes every declared input at
  RUN TIME (while the oracle data is guaranteed mounted) and requires the
  list to be non-empty; the result is recorded as `sweep_provenance.json
  ["inputs_verified"]`. At audit time, `generator._check_current_tree_
  staleness()` classifies each input as `"oracle_data"` (under
  `schema.ORACLE_DATA_PATH_PREFIX`, i.e. `data/...`) or `"code"`. In the
  DEFAULT mode, `"code"` inputs are always rehashed against the current
  tree (catching a source-file edit); `"oracle_data"` inputs are trusted
  via the `inputs_verified` attestation instead of being required on disk
  — this is what makes a fresh clone's `audit()` succeed without the
  gitignored `.mat` files present. `--verify-input-files` (CLI on both
  `generate` and `audit`) sets `strict_input_files=True`, which instead
  requires oracle-data inputs to be physically present and rehashes them
  for real — for local dev where the oracle data genuinely is mounted and
  a stronger, no-attestation-trusted guarantee is wanted. An empty
  `inputs` list, or a manifest missing `path`/`sha256` on any entry, is
  `schema.STATUS_EMPTY_INPUT_MANIFEST`/stale in BOTH modes. Seed coverage
  (`resolved_seeds == range(entry.n_seeds)`) is checked the same way in
  both modes.
- **Lock handling refinements.** `_acquire_lock` now reads the PID written
  into an existing lock file and, via `os.kill(pid, 0)`, distinguishes a
  genuinely live holder (raises `FileExistsError`, unchanged behavior)
  from a stale lock left by a crashed invocation (silently unlinked and
  retried once, so a crash can never permanently block all future reruns
  of that process). `_cmd_run` now treats ANY `JOB_STATUS_LOCKED_SKIPPED`
  result as a hard failure (nonzero exit) — previously it was excluded
  from the hard-failure set, which meant a genuinely concurrent, in-
  progress process could be silently reported as sweep success.
- **Dangling absolute temp-dir refs.** Because `run_job` always executes
  the child in a freshly-created temp rebuild directory (Section 13.2),
  any self-referential absolute path the runner bakes into its own output
  (`result.json["allocator_inputs_ref"/"provenance_ref"]`,
  `provenance.json["oracle_path"]`) would otherwise point at a directory
  deleted the instant the atomic swap completes. `_sanitize_dangling_
  temp_refs()` rewrites these three fields to repo-relative logical paths
  (resolved against the FINAL, post-swap location) before the sentinel is
  written, so no tracked sidecar ever embeds a worktree-specific or
  already-deleted absolute path.

These checks are duplicated (not shared/imported) between `sweep.py`
(launcher resume-decisions) and `generator.py` (read-only audit), per the
pre-existing 13.x precedent of keeping the audit module independent of the
execution-launcher module.

### 13.9 Per-process metric-evaluation dependency modules (beyond `oc_module`)

R2 (13.8) hashes a process's own `opencell/vivarium/karr_<process>.py`
implementation under `"oc_module"`, but a further review found this
insufficient for at least one process: **Metabolism**'s `fva_feasibility`
channel (`verdict._rederive_fva_channel`) is actually computed by
`_metabolism_fva_sample_feasibility()` in `l2_2_design_a_runner.py`
(already hashed as `"runner"`), which calls
`opencell.m1.calc_flux_bounds.compute_bounds`,
`opencell.m1.fva.fva_range`/`substrate_delta_range_from_fva`, and
`opencell.m1.karr_metabolism.solve_fba`/`load_default` (via
`_l2_2_design_a_runner_helpers.py`'s `_metabolism_model()`, already hashed
as `"helpers"`) — none of which is `opencell/vivarium/karr_metabolism.py`
(Metabolism's `oc_module`, already hashed) or one of the four shared
`SWEEP_PROVENANCE_SOURCE_FILES`. A code change to any of these three
`opencell/m1/*.py` modules would silently change Metabolism's actual FVA
feasibility computation without staling its evidence at all.

`PROCESS_CATALOG.yaml` does not declare which metric_type/aggregation a
process's channels use — that is an opt-in choice made by the runner's
process factory (`process.l2_2_metric_type = "fva_feasibility"`, set only
for Metabolism in `_l2_2_design_a_runner_helpers.py`), not a catalog field
— so there is no mechanical rule to derive this registry from the catalog
today (unlike `oc_module`, which IS a catalog field). `schema.
METRIC_DEPENDENCY_FILES` is therefore a small, explicit, hand-maintained
`dict[process_name, dict[hash_key, Path]]` registry (currently one entry:
`"Metabolism": {"fva_module": ..., "calc_flux_bounds_module": ...,
"m1_karr_metabolism_module": ...}`), populated only after tracing the
runner's actual call graph to confirm a module genuinely feeds a metric
computation — never speculatively, and never duplicating a module already
covered by `SWEEP_PROVENANCE_SOURCE_FILES` or `oc_module`.

`sweep.current_source_hashes(oc_module=..., process=...)` and
`generator._current_source_hashes(entry)` both merge
`schema.METRIC_DEPENDENCY_FILES.get(<process name>, {})`'s hashes into the
SAME `source_hashes` dict `oc_module` already lives in — no new gating
code path was needed: the existing R2 staleness loop (in both
`evidence_is_valid` and `_check_sweep_provenance_staleness`) already
iterates `source_hashes.items()` generically and flags any named entry
whose current hash no longer matches, so adding new named entries to that
dict is sufficient to gate them, and copying a sentinel from one process
to another (or a different process's `karr_*.py` module) still fails on
`oc_module`/`process` mismatch as before. A code change to
`opencell/m1/fva.py` (or the other two registered modules) now stales only
Metabolism's row; every other process is unaffected, since none of them
has an entry in `METRIC_DEPENDENCY_FILES`. See
`test_l22_evidence_anticheat.py::test_metric_dependency_module_change_stales_only_that_process`
and `::test_metabolism_source_hashes_include_real_fva_dependency_modules`.

Per the operator's explicit "do not rerun until FVA + generic cache
commits integrate/freeze" instruction, this is a code-and-tests-only
commit: no process was rerun, and `evidence_index.json`'s tally/content
(only `generated_at` differs) is unchanged, since Metabolism currently has
no `sweep_provenance.json` in this worktree to newly stale or validate
against the expanded registry.

### 13.10 F1–F4: registry completeness, unconditional manifest canonicalization, primary-channel exactly-once (schema v2 evaluator)

> **Amended by Section 13.11 (F5).** The mechanical,
> single-level-`ast.parse`-of-`oc_module` derivation described below
> (`schema.mechanical_dependency_hashes`/`MECHANICAL_DEPENDENCY_CANDIDATES`)
> was reviewed and **rejected**: any code path that decides runtime
> staleness gating by parsing source at generation/sweep time is exactly
> the kind of "clever" derivation this project's evidence-integrity work
> is trying to eliminate, even when scoped to a single file and a fixed
> candidate list. It has been removed from `sweep.py`/`generator.py`
> entirely and replaced by additional explicit, hand-maintained
> `schema.PROCESS_DEPENDENCY_FILES` entries, with AST-parsing retained
> ONLY as a test-only, never-imported-by-runtime-code completeness audit.
> This subsection is kept for historical record of what F1–F4 actually
> shipped and why; **13.11 is the current design.**

A final review of 13.9 found the `METRIC_DEPENDENCY_FILES` registry (and
the surrounding provenance code) still had four gaps:

**F1 — the dependency registry did not cover every runtime numeric
dependency.** Three more real call-graph edges existed but were not
hashed anywhere in `source_hashes`:

- Every `design_a_per_tick` job's `output_dir`/`result.json` is actually
  produced through
  `tests/vivarium/l2_replay_common.py` (imported by
  `_l2_2_design_a_runner_helpers.py` for its state/projection/update
  functions) — a change here can silently change EVERY design_a_per_tick
  process's evidence, not just one, so this is now a **harness-scoped**
  dependency (`schema.HARNESS_DEPENDENCY_FILES["design_a_per_tick"] =
  {"l2_replay_common": ...}`), merged in by `harness_type`, not by
  process name.
- `opencell/m1/karr_metabolism_writeback.py` is imported by
  Metabolism's own `oc_module`
  (`opencell/vivarium/karr_metabolism.py`) and was missing from
  `METRIC_DEPENDENCY_FILES["Metabolism"]` alongside the three modules
  13.9 already added.
- `opencell/m3/translation.py` is imported by Translation's `oc_module`
  (`opencell/vivarium/karr_translation.py`) and had no
  `METRIC_DEPENDENCY_FILES` entry at all.

A further, structurally different gap: the chromosome-coupled processes
(`DNARepair`, `DNASupercoiling`, `Replication`, `ReplicationInitiation`,
and the event-class `DNADamage`) each import
`opencell/state/chromosome_store.py` and/or
`opencell/vivarium/chromosome_views.py` directly from their own
`oc_module` — but WHICH processes import which of these two files is not
a catalog field and was not previously registered anywhere, unlike the
Metabolism/Translation case where the process name alone determines the
dependency set. Hand-maintaining "DNARepair imports both,
DNASupercoiling/Replication/ReplicationInitiation import only
chromosome_store" as another static `dict[process_name, ...]` table would
silently drift the next time an import is added or removed from a
`karr_*.py` file. Instead, `schema.mechanical_dependency_hashes(oc_module)`
does a **single-level, non-recursive** `ast.parse` of the ONE given
`oc_module` source file, checking only whether it contains a top-level
`import X` / `from X import ...` statement naming one of a small FIXED
candidate list (`schema.MECHANICAL_DEPENDENCY_CANDIDATES`, currently just
`chromosome_store`/`chromosome_views`) — this is deliberately NOT a
generalized transitive-closure import-graph hasher (the operator's
explicit "prefer explicit small registry + documented call graph, not
recursive import hashing"); it only ever looks one file deep, at a fixed
candidate list, so its cost and behavior are as predictable as the
hand-written registries it complements.

`sweep.current_source_hashes()` and `generator._current_source_hashes()`
now merge THREE dependency sources into the same `source_hashes` dict (no
new gating code path, same as 13.9): `schema.METRIC_DEPENDENCY_FILES.get(process,
{})` (hand-maintained, process-keyed), `schema.mechanical_dependency_hashes(oc_module)`
(mechanically derived from the process's own `oc_module` AST, process-keyed
via its own import graph), and `schema.harness_dependency_hashes(harness_type)`
(hand-maintained, harness-keyed — currently only `design_a_per_tick`).
`SweepJob` gained an explicit `harness_type: str = "design_a_per_tick"`
field (the only value `plan_sweep()` ever constructs, since it filters
catalog entries to `harness_type == "design_a_per_tick"` before building
jobs) so this is passed explicitly rather than assumed.

Verified today's real catalog/tree state matches exactly:
`mechanical_dependency_hashes` → `{chromosome_store_module,
chromosome_views_module}` for DNARepair; `{chromosome_store_module}` for
DNASupercoiling/Replication/ReplicationInitiation; `{}` for
Transcription/Translation/Metabolism/ProteinDecay.
`harness_dependency_hashes("design_a_per_tick")` → `{l2_replay_common}`;
`harness_dependency_hashes("event_class")` → `{}` (no registered entry).
See `test_l22_evidence_anticheat.py::test_mechanical_dependency_hashes_reflects_real_current_import_graph`
and the four other new F1 tests (`test_karr_metabolism_writeback_and_m3_translation_are_registered_and_hashed`,
`test_l2_replay_common_change_stales_every_design_a_process_but_not_event_class`,
`test_chromosome_store_change_mechanically_stales_only_importing_processes`,
`test_chromosome_views_change_stales_dnarepair_but_not_dnasupercoiling`).

**Direct consequence for the currently-tracked bundle:** DNARepair and
ReplicationInitiation's existing `sweep_provenance.json` sentinels (from
the 13.8/R1-R3-hardened rerun) do not carry these new hash keys and
therefore now correctly fail `evidence_is_valid`/the generator's
staleness check — going from `PASS` to non-green until they are rerun
under this expanded registry. This is the intended, honest consequence of
closing a real gap, not a regression; see Section 13.6-style transitional
notes and the tally reported in the commit this section was introduced
in.

**F2 — `_normalize_input_manifest_file` only rewrote the file `if
changed`** (i.e. only when at least one `path` value was actually
absolute and got rewritten to relative). A manifest whose paths were
ALREADY relative, but serialized with different whitespace or
key-ordering than the canonical `json.dumps(..., indent=2, sort_keys=True)
+ "\n"` form `generator.bundle_process_evidence` itself always produces,
would silently keep those non-canonical bytes forever — breaking the
live-tree/bundle byte-identity guarantee this function exists for. Fixed
by removing the guard: the file is now ALWAYS rewritten to the canonical
form, unconditionally. See the new
`test_l22_evidence_sweep.py::test_normalize_input_manifest_file_always_rewrites_canonical_bytes_even_when_already_relative`
and `::test_normalize_input_manifest_file_is_idempotent_on_a_second_call`.

**F3 — `rederive_process` only checked that SOME channel was marked
`is_primary=true`**, not that it was the catalog's actual declared
`primary_channel`, and not that only one channel claimed it. Two vacuous
cases previously passed through undetected: (a) two or more channels both
marked `is_primary=true` (ambiguous — which one is authoritative?), and
(b) exactly one channel marked `is_primary=true`, but a DIFFERENT channel
than the catalog's `entry.primary_channel` (a "vacuous primary-channel
substitution": e.g. a decoy channel claims primacy while the real primary
channel silently sits at `is_primary=false`, letting the existing
per-channel non-vacuity check evaluate the wrong channel entirely).
`rederive_process` now collects every channel name with `is_primary=true`
into a list and requires exactly one entry, further requiring that single
name to equal `entry.primary_channel` when the catalog declares one; zero,
many, or a name-mismatch are all `STATUS_PRIMARY_VACUOUS`/non-green (the
existing zero-case message is unchanged; the many/mismatch cases are new
`STATUS_PRIMARY_VACUOUS` reasons). Because this changes what verdict the
SAME raw `result.json` payload can mechanically produce,
`verdict.EVALUATOR_SCHEMA_VERSION` was bumped `1 → 2`; any sentinel
recorded under the old evaluator (`evaluator_schema_version == 1`) is
therefore explicitly staled by the existing schema-version check in
`evidence_is_valid`/`_check_sweep_provenance_staleness`, independent of
the F1 hash-key changes above. See the three new
`test_l22_evidence_verdict.py` tests:
`test_process_primary_channel_name_mismatch_is_vacuous_substitution`,
`test_process_multiple_channels_marked_is_primary_is_non_green`,
`test_process_primary_channel_matching_catalog_name_exactly_once_is_clean`.
Also decoupled `test_l22_evidence_portability.py`'s
`test_audit_succeeds_from_a_temp_root_with_no_local_artifacts_tree` "real"
comparison side from `gen.audit()`'s own ambient default-argument
resolution, passing explicit `index_path`/`evidence_root` on both sides so
the test is purely about the portable/tracked-bundle path, not an
incidental re-test of default-argument resolution (already covered
elsewhere).

**F4 — trivial:** improved the `--verify-input-files`-requested-but-
oracle-not-mounted message in `generator._check_current_tree_staleness`
to explain this is expected in a fresh clone/bundle-only checkout and to
suggest omitting the flag, rather than a single terse parenthetical.

Per the operator's explicit "do not rerun DNARepair/RepInit; their
current sentinels should become stale after new hashes (expected)"
instruction, this is again a code-and-tests-only commit: no process was
rerun. The tracked `evidence_index.json`/bundle is regenerated in a
separate, immediately-following commit once this one is green, and its
new tally reflects DNARepair/ReplicationInitiation going non-green for
the reasons above (their old evidence is real and their next rerun will
almost certainly pass again against the same raw numbers — the concern
F1/F3 protect against is a change in code silently going undetected, not
a claim that the old rows were ever incorrect).

### 13.11 F5: explicit-registry-only correction (mechanical AST derivation removed from runtime), bidirectional staleness, empty-`primary_channel` hardening

13.10's `schema.mechanical_dependency_hashes(oc_module)` — a single-level,
fixed-candidate-list `ast.parse` of one process's own `oc_module`, run at
sweep/generation time to decide which of `chromosome_store`/
`chromosome_views` that process's `source_hashes` should include — was
reviewed and **rejected**. Even tightly scoped, letting the staleness-
gating code itself decide its own dependency set by parsing source is the
wrong shape for this project: the whole point of `source_hashes` is that
a human can read `schema.py` and know exactly, unconditionally, which
files gate which process, with zero code-path variability. The fix has
two independent halves that must not be conflated:

**(a) Runtime authority is now 100% explicit.** `MECHANICAL_DEPENDENCY_CANDIDATES`,
`mechanical_dependency_hashes()`, and `_module_imports_any()` are deleted
from `schema.py`; `sweep.current_source_hashes()` and
`generator._current_source_hashes()` no longer call anything
AST-based — they merge exactly two dependency sources per job:
`schema.PROCESS_DEPENDENCY_FILES.get(process, {})` (renamed from
`METRIC_DEPENDENCY_FILES`, now covering every process with a first-party
runtime numeric dependency beyond its own `oc_module`, not only
Metabolism/Translation) and `schema.harness_dependency_hashes(harness_type)`
(unchanged from 13.10). The full registry, verified against the real
current import graph of every in-scope `oc_module` (see (c) below):

| process | dependency keys → real file |
| --- | --- |
| `Metabolism` | `fva_module` → `opencell/m1/fva.py`; `calc_flux_bounds_module` → `opencell/m1/calc_flux_bounds.py`; `m1_karr_metabolism_module` → `opencell/m1/karr_metabolism.py`; `karr_metabolism_writeback_module` → `opencell/m1/karr_metabolism_writeback.py`; `karr_protein_decay_light_module` → `opencell/vivarium/karr_protein_decay_light.py` (MCG RNG) |
| `Translation` | `m3_translation_module` → `opencell/m3/translation.py`; `karr_translation_v3_module` → `opencell/vivarium/karr_translation_v3.py` (imported inside a function body, not module scope — registered defensively; see (c)) |
| `Transcription` | `m2_transcription_module` → `opencell/m2/transcription.py` |
| `ProteinProcessingI` | `karr_trna_aminoacylation_module` → `opencell/vivarium/karr_trna_aminoacylation.py` |
| `RNAProcessing` | `karr_trna_aminoacylation_module` → `opencell/vivarium/karr_trna_aminoacylation.py` |
| `ProteinTranslocation` | `util_module` → `opencell/util/__init__.py`; `util_matlab_rng_module` → `opencell/util/matlab_rng.py` |
| `DNARepair` | `chromosome_store_module` → `opencell/state/chromosome_store.py`; `chromosome_views_module` → `opencell/vivarium/chromosome_views.py` |
| `DNASupercoiling` | `chromosome_store_module`; `m_gen_constants_module` → `opencell/m_gen_constants.py` |
| `Replication` | `chromosome_store_module` |
| `ReplicationInitiation` | `chromosome_store_module` |
| `DNADamage` (event_class — no `design_a_per_tick` sweep row exists yet, so this entry has zero effect on the current tally) | `chromosome_store_module`; `chromosome_views_module`; `m_gen_constants_module` |

`opencell.util` is a **package**, not a bare module:
`opencell/util/__init__.py` is a one-line `from .matlab_rng import
MatlabRandStream` re-export. Both the package `__init__.py` (the direct
import target of `from opencell.util import MatlabRandStream`) and
`opencell/util/matlab_rng.py` (the file with the actual RNG logic) are
registered, mirroring the existing Metabolism precedent of registering
both a process's direct import and that import's own one-hop dependency
(`karr_metabolism_writeback_module`).

**(b) Bidirectional staleness.** Both `sweep.evidence_is_valid()` and
`generator._check_sweep_provenance_staleness()` previously only checked
that every file the CURRENT registry expects is present and hash-matched
in the recorded `sweep_provenance.json["source_hashes"]` — a recorded
dict with EXTRA keys beyond what's currently expected silently passed.
Both functions now additionally compute
`extra_keys = sorted(set(recorded_hashes) - set(current_hashes))` and
fail/report non-green when non-empty. This closes a real gap: a sentinel
copied from a process with a larger dependency set (or recorded against a
registry that later shrinks) previously could not be caught by the
existing "missing/mismatched key" check alone, since it only iterated the
current side.

**(c) Test-only AST completeness audit.** `tests/scripts/_l22_ast_import_audit.py`
is a NEW module, never imported by any `scripts/l22_evidence/*.py` runtime
file, that resolves every module-scope first-party import
(`import a.b.c`, aliases, `from pkg import X`/submodule-or-package-
re-export disambiguation, relative imports at any level) in a given
source file to its file path, without recursing into what THAT file
imports (no transitive closure — deliberately matching the operator's
"no recursive dependency platform" instruction). It raises
`ImportAuditError` on read/parse failure rather than silently returning
empty. `tests/scripts/test_l22_evidence_ast_completeness.py` (14 tests)
uses it to assert, over the REAL current tree, that every in-scope
process's `oc_module` has zero first-party module-scope imports that are
neither its own `oc_module`/a globally-registered common source nor
explicitly covered by `PROCESS_DEPENDENCY_FILES` — with a small,
documented exclusion list (`_DOCUMENTED_EXCLUSIONS`) for the one known
function-body-scoped import (Translation → `karr_translation_v3`, out of
the audit's module-scope-only detection surface by construction, but
registered anyway per (a)). This audit runs ONLY in CI/test time; it can
never affect what a real sweep or generator run gates on.

**(d) Empty-`primary_channel` hardening.** `verdict.rederive_process`'s
F3 exactly-once check (13.10) required the single `is_primary=true`
channel name to equal `entry.primary_channel`, but only when
`entry.primary_channel` was itself truthy — a catalog entry with an
empty/missing `primary_channel` field silently skipped the check
entirely (a latent vacuous-substitution gap distinct from the F3 cases).
A new `elif not entry.primary_channel:` branch now explicitly flags this
as `STATUS_PRIMARY_VACUOUS`/non-green. A new catalog-level sanity test
(`test_every_real_in_scope_catalog_entry_has_nonempty_primary_channel`)
confirms all 22 real in-scope catalog entries currently declare a
non-empty `primary_channel`, so this hardening causes **zero change** to
the current tally — it only closes the gap for a future catalog edit.
This was not explicitly requested by the F5 instructions but was
discovered as a directly adjacent, zero-risk gap while implementing (a)–(c)
and is included in the same commit for review.

Per the operator's explicit "no reruns until code/tests committed" /
"no process reruns" instruction, this is again a code-and-tests-only
change functionally, with `evidence_index.json`/`evidence_bundle/`
regenerated in the same commit purely to reflect the renamed/expanded
registry: regeneration is byte-identical except `generated_at`
(`content_hash` unchanged), confirming the tally
(`MISSING_EVIDENCE: 20, FAIL: 2`) and every row's reasons are unaffected —
expected, since no `sweep_provenance.json` in this worktree currently
carries the old mechanical-derivation keys to newly stale, and no process
was rerun.

## 14. Files

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
  runner sweep launcher (`plan`/`run`/`status` CLI); see Sections 11, 13.
  Now atomic/locked with mandatory-sidecar + `sweep_provenance.json`
  staleness checks (Section 13).
- `tests/scripts/test_l22_evidence_sweep.py` — 40 tests: real-catalog
  `plan_sweep()` derivation, resume-by-validation/staleness semantics
  (source-hash drift, evaluator-schema-version drift, missing
  `sweep_provenance.json`; unknown/missing git SHA is accepted when hashes
  still match -- Section 13.7), bounded parallelism, atomic/locked
  force reruns (crash-mid-swap recovery, concurrent-lock exclusion),
  exit-code capture (including `RAN_EXIT_0_INVALID_EVIDENCE`), compact
  report/status writers, CLI smoke tests including nonzero-exit-on-
  hard-failure — all against fake fast command builders, never the real
  slow runner.
- `tests/scripts/_l22_evidence_fixtures.py` — shared fixture helpers
  (`write_mandatory_sidecars`, `write_valid_sweep_provenance`,
  `write_full_valid_evidence`) used by the sweep/anticheat test suites,
  built from the REAL current `sweep.current_source_hashes()`/
  `populate._git_sha`/`populate._git_dirty`/`verdict.EVALUATOR_SCHEMA_VERSION`
  so tests exercise the real staleness-detection code path.
- `docs/phase_f/l2_2_design_a/sweep_status.json` — tracked, compact,
  read-only interim progress snapshot (one row per process: valid/log
  state, stored verdict for human context). Regenerate with
  `sweep.py status`; safe to run while a real sweep is still executing.
- `docs/phase_f/l2_2_design_a/sweep_report.json` — tracked, compact
  per-job run report (`process`, `status`, `exit_code`, timestamps,
  `duration_s`, `output_dir`, `log_path`); written by
  `sweep.py run --report-out ...`.
- `docs/phase_f/l2_2_design_a/evidence_bundle/` — tracked, portable mirror
  of mandatory per-process authority + sidecar files (excludes
  `INFORMATIONAL_ONLY_FILES`/`allocator_inputs.json`); see Sections 12–13.
  Regenerate with `generator.py bundle`.
- `tests/scripts/test_l22_evidence_portability.py` — proves the tracked
  bundle is sufficient for `audit()` to succeed with no local
  `artifacts/l2_2_gates` tree at all; see Section 12.
