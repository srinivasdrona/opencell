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
channel's verdict is recomputed from raw fields only:

- `aggregation != "per_tick_vector_w1_mean"` (chromosome-primary
  `per_component_scaled` / `hurdle_event_rate_plus_conditional_scaled_distance`
  channels, e.g. `DNARepair`, `Replication`, `DNASupercoiling`, `DNADamage`)
  → `MISSING_EVALUATOR`. No mechanical re-derivation exists for these metric
  types yet; the row is non-green with a named missing evaluator rather than
  falling back to whatever the runner claimed.
- Missing raw fields (`w1_oc_vs_karr`, `threshold`, `q95_null`,
  `n_nonzero_oc`, `n_nonzero_karr`) → `MISSING_EVALUATOR`.
- Primary channel with zero nonzero observations on **both** sides →
  `PRIMARY_CHANNEL_VACUOUS` (non-vacuous primary channel requirement).
- `n_nonzero < 30` (either side) → `INSUFFICIENT_SAMPLES` (non-gating).
- `w1 <= q95_null` → `SEED_NOISE`; `w1 <= threshold` → `PASS`; else `FAIL`.

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

1. **Populate real evidence.** Run `tests/vivarium/l2_2_design_a_runner.py`
   for each of the 18 `design_a_per_tick` processes against
   `artifacts/l2_2_gates/<Process>/latest/`, once full multi-seed Karr
   oracle extraction closes (tracked separately; see
   `L22_FULL_EXTRACTION_SCOPE.md`).
2. **Build the L2.event harness** for the 4 `event_class` processes; until
   then they remain `MISSING_EVIDENCE` by construction.
3. **Mechanical evaluators for projection-distance primary channels**
   (`per_component_scaled`, `hurdle_event_rate_plus_conditional_scaled_distance`)
   — currently `MISSING_EVALUATOR` for `DNARepair`, `Replication`,
   `DNASupercoiling`, `DNADamage`.
4. **Null-control-must-fail canary, pre-registered/null-derived thresholds,
   H12 evidence generation, hint-off proof, reproducibility canary** — the
   schema has fields ready for these (`h12_evidence_ref`, `decision_ref`,
   `alternate_evidence_ref`, sentinel warning re-derivation) but no process
   has them populated yet.
5. **CI wiring of `--require-all-pass`** as a blocking acceptance gate —
   deliberately deferred to a follow-up activation commit, per this task's
   explicit two-stage requirement.

## 10. Files

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
