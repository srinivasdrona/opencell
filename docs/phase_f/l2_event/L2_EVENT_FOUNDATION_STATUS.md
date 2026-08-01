# L2.event Foundation — Implementation Status & Spec-Correction Report

**Scope of this report:** the shared L2.event framework built in
`E:\opencell-worktrees\l2-event-foundation` (branch `agent/l2-event-foundation`
@ base `514a696`), per `docs/phase_f/L2_EVENT_GATE_SPEC_v4.md` (v4.1). This is
**not** a process-branch report — no process (Cytokinesis, RibosomeAssembly,
DNADamage, FtsZPolymerization) has a gating-ready adapter in this task, and
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` was not modified.

## 1. Ground-truth inventory audit

The ratified spec (v4.1) was read in full. Two of its inventory assumptions
were stale as of this task and are corrected here rather than silently
assumed:

1. **No event runner existed** prior to this task. `scripts/l2_event/` did
   not exist; the only event-related code in the repo was the per-tick L2.2
   replay tests (`tests/vivarium/test_karr_ribosome_assembly_l2_replay.py`,
   `test_karr_rna_modification_l2_replay.py`) and their shared helper module
   `tests/vivarium/l2_replay_common.py`.
2. **Event-window raw data is far sparser than assumed.** Only **2** event
   MAT files exist on disk anywhere in this repo's data tree, both for
   **seed 000 only**, under
   `data/m1_sources/karr_native/per_process_traces_v2_event_s000/`:
   `RibosomeAssembly_100ticks.mat` and `RNAModification_100ticks.mat`. There
   are **not** 50 seeds for any process. `RNAModification` is not one of the
   four EVENT_CLASS target processes this task governs and is noted only as
   an incidental finding.
3. **Standard mid-cycle traces are event-uninformative.** The tracked
   `per_process_traces_v2[_s*]/` traces (stride-1, dense, but mid-cycle) lack
   the `metadata/tick_offset` key entirely and must be refused by the loader,
   not silently treated as event windows — verified empirically against a
   real tracked standard trace (`per_process_traces_v2_s001/Translation_100ticks.mat`).

### 1.1 Exact missing-data matrix (the four EVENT_CLASS target processes)

| Process | In v4 scope (spec §8) | Event-window traces on disk | Seeds available / required | Adapter status | Notes |
|---|---|---|---|---|---|
| **Cytokinesis** | Yes | **0** | 0 / 50 | `not_implemented` | No event-window extraction has ever run for this process. `event_timing_model: single_firing`, `magnitude_gateable: false` per D6 (no non-redundant payload channel exists on the OC port yet). |
| **RibosomeAssembly** | Yes | **1** (seed 000) | 1 / 50 | `structural_smoke_only` | Only process with any adapter at all, and it is explicitly read-only/non-gating. `event_timing_model: repeated_firing`, `magnitude_gateable: true`. |
| **DNADamage** | **No** (deferred, spec §8 out-of-scope #2) | 0 | 0 / 50 | `not_implemented` | Deferred to a future L2.stress gate: baseline Karr cycles do not spontaneously exercise DNA damage. |
| **FtsZPolymerization** | **No** (deferred, spec §8 out-of-scope #1) | 0 | 0 / 50 | `not_implemented` | Gradient/continuous polymerization, not a binary firing event; v0.3 already deferred it and v4 does not reopen the decision. |

This table is also encoded machine-readably in
`docs/phase_f/l2_event/event_registry.yaml` (see
`EVENT_REGISTRY_SCHEMA.md`), which is the tracked source of truth going
forward — this markdown table is a human-readable snapshot of it, not a
second independent source.

## 2. False/misleading status claims in `PROCESS_CATALOG.yaml` — corrected here, not by editing the catalog

Per this task's explicit constraint, `PROCESS_CATALOG.yaml` was **not**
modified (its content hash gates Design-A's own staleness checks). Two of
its per-process `notes:` fields make claims that this audit found to be
misleading when read as "this process's event-class gate is green":

* **RibosomeAssembly** (`PROCESS_CATALOG.yaml` line ~338): *"Day-32
  (2026-06-18): event-window test
  test_karr_ribosome_assembly_l2_event_replay PASSES on seed=0 event traces
  (extracted at tick_offset=200). ... L2.2 GREEN."* — This is a **single-seed
  per-tick identity-replay test passing**, not a calibrated ensemble gate
  verdict. It is the same seed-0 window this task's structural smoke also
  exercises (§3 below) and produces the same result (2 Karr fires, 2 OC
  fires) — genuinely encouraging for a future gating adapter, but 1/50
  required seeds cannot support a D3/D4 statistical gate. The event registry
  (`event_registry.yaml`) records `adapter_status: structural_smoke_only`,
  never `gating_ready`, for exactly this reason.
* **DNADamage** (`PROCESS_CATALOG.yaml` line ~409): *"L2 replay test PASSES
  (radiation-gated quiescent: both OC and Karr produce 0 events under
  no-stimulus conditions, which is correct biology). L2.2 GREEN."* — This is
  precisely the **vacuous zero==zero pattern** this spec's D3 precedence
  rule (`T_karr == 0` ⇒ `NO_KARR_SUPPORT`, never a PASS) exists to prevent
  from being reported as a gate PASS. Biologically, "no radiation → no
  damage" may well be correct, but a test that never observes a single
  firing event cannot validate firing *count*, *timing*, or *payload*
  distributional fidelity — those are exactly the three channels
  `scripts/l2_event/metrics.py` computes, and all three would report
  `NO_KARR_SUPPORT`, not `PASS`, if run against this data.

Neither correction required editing the catalog. Both are recorded in
`event_registry.yaml`'s per-process `notes` field and here.

## 3. What was built

`scripts/l2_event/` — generic, process-adapter-based event evidence
framework. No process-specific gating logic beyond one optional read-only
smoke adapter (§4).

| Module | Purpose |
|---|---|
| `schema.py` | Versioned dataclass schema for every L2.event artifact (`EventObservation`, `EventTimeline`, `GateChannelResult`, `ResultDoc`, `InputManifest`, `NullCalibrationDoc`, `ProvenanceDoc`) + atomic JSON I/O. Separate from `scripts/l22_evidence/schema.py` (Design-A) by design — event-class results must never be silently folded into the per-tick scoreboard. |
| `window_loader.py` | Stride-1, fully-enumerated event-window loader (D1). Refuses missing files (`MISSING_WINDOW`), non-event-window traces including all mid-cycle standard traces (`NOT_EVENT_WINDOW_TRACE`, keyed off the real `metadata/tick_offset` structural discriminator, not a filename heuristic), and sparse/partial grids (`INCOMPLETE_WINDOW`). |
| `registry.py` + `docs/phase_f/l2_event/event_registry.yaml` | The versioned event registry (schema doc: `EVENT_REGISTRY_SCHEMA.md`), validated read-only against `PROCESS_CATALOG.yaml` — never edits it. |
| `adapters/base.py`, `adapters/fakes.py` | The `EventAdapter` protocol (D7) + synthetic test-only adapters exercising every gating path without any real biology port. |
| `adapters/ribosome_assembly_smoke.py` | The **one** process-specific adapter this task ships: RibosomeAssembly seed-0 **read-only structural smoke**, never used for a gate verdict. |
| `metrics.py` | Count/timing/payload W1 gates (D2/D3/D4), Karr-only clustered seed bootstrap, C6 spurious-OC-only-firing detector. No zero==zero PASS anywhere in this module. |
| `evidence.py` | Portable evidence index/sidecar writer: live gitignored `artifacts/l2_event/<Process>/<run_id>/`, tracked `docs/phase_f/l2_event/evidence_bundle/<Process>/`, tracked `docs/phase_f/l2_event/evidence_index.json`. Fresh-clone audit works from the tracked bundle alone. |
| `runner.py` | CLI + refusal gauntlet (`RunnerRefusal` with stable reason codes) + `evaluate_gate()` (pure orchestration over synthetic-or-real `EventTimeline`s, decoupled from how they were produced) + `run_structural_smoke()` (the one real RibosomeAssembly seed-0 pipeline). |

### 3.1 RibosomeAssembly seed-0 structural smoke — confirmed working

Ran end-to-end against the real copied `RibosomeAssembly_100ticks.mat` (seed
000) and the real `KarrRibosomeAssemblyProcess` OC port, using only Karr's
`states_before` conditioned into a fresh OC state template (never
`states_after` into the SUT):

```
STRUCTURAL SMOKE OK: process=RibosomeAssembly seed=0 n_ticks=100 tick_offset=200.0
karr_fires=2 oc_fires=2 (mode=structural_smoke, no gate verdict computed)
```

This proves the loader → adapter → OC-port round-trip works, and nothing
more. `result.json` for this run records `mode: structural_smoke`,
`verdict: NOT_APPLICABLE`, and an empty `channels` list — it is structurally
impossible to mistake this for a gate PASS/FAIL, and the runner's `--mode
gate` path independently and separately refuses to run for any process in
this task (§4).

## 4. Refusal gauntlet (requirement 4) — verified behaviors

| Condition | Reason code | Verified via |
|---|---|---|
| Missing event-window file | `MISSING_WINDOW` | `window_loader`/`runner` unit tests |
| Sparse/partial per-observable grid | `INCOMPLETE_WINDOW` | synthetic HDF5 fixture test |
| Standard mid-cycle trace (no `tick_offset`) | `NOT_EVENT_WINDOW_TRACE` | real tracked `Translation_100ticks.mat` |
| Single seed where ensemble required | `SINGLE_SEED_ENSEMBLE_REQUIRED` | CLI + unit test (RibosomeAssembly, 1 vs 50 seeds) |
| Empty event support (Karr never fires, OC also silent) | `EMPTY_EVENT_SUPPORT` | unit test — refuses rather than reporting a vacuous PASS |
| Wrong adapter for process | `ADAPTER_PROCESS_MISMATCH` | unit test (`WrongProcessAdapter`) |
| Adapter not `gating_ready` | `ADAPTER_NOT_GATING_READY` | CLI test — **every** process refuses gate-mode today, by design |
| Out-of-v4-scope process | `REGISTRY_OUT_OF_V4_SCOPE` | CLI test (DNADamage, FtsZPolymerization) |
| Unknown process | `REGISTRY_PROCESS_UNKNOWN` | CLI test |

Exit codes: `0` = OK (smoke success or, in principle, a computed gate),
`1` = reserved for a computed gate FAIL (not reachable today — no
gating-ready adapter exists), `2` = REFUSED. Exit codes propagate from
`main()` to the process return code.

## 5. Test suite

7 new files under `tests/scripts/test_l2_event_*.py`, **133 tests, all
passing** (107 at initial foundation review; +26 added in the M1–M6
hardening round, §8):

| File | Count | Covers |
|---|---|---|
| `test_l2_event_schema.py` | 7 | `EventObservation`/`EventTimeline` invariants, atomic JSON round-trip |
| `test_l2_event_window_loader.py` | 16 | Every D1 refusal branch (synthetic HDF5 fixtures) + real RA seed-0 load + real standard-trace refusal + M4 stride/window-boundary contract (stride/tick_start/tick_end/window_anchor) |
| `test_l2_event_registry.py` | 14 | Registry↔catalog cross-check, schema/version/timing-model validation, v4-scope correctness for all 4 processes, M5 harness_type-gated-on-in_scope_v4 + FtsZ-reclass-does-not-brick-RA |
| `test_l2_event_metrics.py` | 39 | Count/timing/payload gates (PASS/FAIL/SEED_NOISE/NO_KARR_SUPPORT/INSUFFICIENT_KARR_SUPPORT/DEGENERATE_NULL/NO_OC_SUPPORT), no-zero==zero-PASS, C6 spurious-fire detection, bootstrap sanity, `_safe_wasserstein` edge cases, M1 support floors |
| `test_l2_event_evidence.py` | 16 | Write/bundle/index/audit round-trip, tamper + stale-content-hash detection, fresh-clone (bundle-only) audit, Windows-worktree-`gitdir` fallback (§5.1), M6 incomplete-row audit problem, git_sha-tamper-via-content_hash |
| `test_l2_event_adapters.py` | 13 | Fakes, adapter-mismatch, anti-laundering signature checks, real RA seed-0 adapter + end-to-end structural smoke, M3 `complex_index_by_wid` payload mapping + fire_count-is-tick-incidence |
| `test_l2_event_runner.py` | 28 | Full refusal gauntlet, `evaluate_gate()` wiring (M2: full gauntlet runs inside `evaluate_gate` itself, not just the CLI), CLI-level dispatch for all 4 processes, real-data smoke + evidence-writing round trip, M1 direct-API-bypass reproduction |

Pre-existing regression check: `tests/vivarium/test_karr_ribosome_assembly_l2_replay.py`
and `test_karr_rna_modification_l2_replay.py` still pass/skip identically
(1 pass + 1 skip each) — no accidental `sys.path` collision from this
package's reuse of `tests/vivarium/l2_replay_common.py`.

A pre-existing, **unrelated** local-environment flake was observed in 4
`scripts/l22_evidence` (Design-A) tests during this session
(`test_l22_evidence_portability.py`, `test_l22_evidence_generator.py`);
`git diff 514a696 -- scripts/l22_evidence docs/phase_f/l2_2_design_a` is
empty for this branch, confirming this task made no changes there — the
discrepancy tracks local `artifacts/l2_2_gates/` sweep-output drift, not
anything introduced by this task.

### 5.1 Bug found and fixed: `current_git_sha()` returned `null` under every WSL invocation in this worktree

`evidence.py`'s `current_git_sha()` shelled out to `git rev-parse HEAD`
with `cwd=_REPO_ROOT`. This worked from a Windows shell but returned
`None` for **every** run launched via `bin\oc-py`/`bin\oc-pytest` (i.e.
every real execution in this project, per the mandatory WSL-execution
rule) — silently, since the function swallows all exceptions.

Root cause: this worktree's `.git` gitlink file contains
`gitdir: E:/opencell/.git/worktrees/l2-event-foundation` — a
Windows-style absolute path, written by Windows-hosted
`git worktree add`. A Linux-hosted `git` binary (the one on PATH inside
WSL) cannot resolve `E:/...` as a path at all, so
`git rev-parse HEAD` fails with "not a git repository" every time it is
invoked from WSL in this worktree, even though the exact same command
works fine from a native Windows/PowerShell shell. This is a general
WSL + Windows-created-worktree interaction, not specific to this
package — any tool in this repo that shells out to `git` from a WSL
subprocess in a worktree hits it.

Fix: `current_git_sha()` now falls back, on primary-command failure, to
reading the `.git` gitlink, translating a `gitdir:` line matching
`<drive>:/...` to its `/mnt/<drive>/...` WSL-mount equivalent (helper
`_translate_windows_gitdir()`), and re-invoking
`git --git-dir=<translated> rev-parse HEAD` explicitly. Verified fix
end-to-end: re-ran the RA seed-0 structural smoke CLI after the fix and
confirmed `provenance.json`/`evidence_index.json` now record the real
commit SHA instead of `null` (audit still reports zero problems). 4 new
regression tests added (`test_translate_windows_gitdir_*`,
`test_current_git_sha_*`) in `test_l2_event_evidence.py`.

## 6. Process-branch split recommendation

1. **RibosomeAssembly-branch**: highest readiness. The structural smoke
   already proves the full loader/adapter/OC-port pipeline works on real
   data. The remaining work is (a) extracting 49 more event-window seeds
   (MATLAB/Octave extraction — explicitly out of scope for this task), (b)
   promoting `ribosome_assembly_smoke.py` into a real gating adapter (likely
   renamed/versioned, e.g. `ribosome_assembly.v1`), and (c) flipping
   `adapter_status: gating_ready` in the registry once a full 50-seed
   ensemble backs a real `count_gate`/`timing_gate_repeated_firing`/
   `payload_gate` run. This should be its own branch, not folded into this
   foundation.
2. **Cytokinesis-branch**: needs event-window extraction from scratch (0
   traces exist today) before any adapter work is meaningful. Should start
   with the MATLAB/Octave extraction step, then build a
   `single_firing`-model adapter analogous to `ribosome_assembly_smoke.py`
   but is NOT gateable on payload per D6 — count + timing are its two real
   gating channels.
3. **DNADamage and FtsZPolymerization**: remain **explicitly out of v4
   scope** per spec §8 and should **not** be branched under this spec
   version. DNADamage's catalog "L2.2 GREEN" note should not be read as
   readiness for an event gate (see §2); any future work on it belongs to a
   later L2.stress-gate spec, not a v4 process branch.

## 7. What this task deliberately did not do

* No MATLAB/Octave extraction of any kind.
* No edits to `PROCESS_CATALOG.yaml` (corrections live in this report + the
  registry's `notes` fields only).
* No gating-ready adapter for any of the four processes — `--mode gate`
  refuses for all of them today, by design.
* No promotion of any L2.event result into the Design-A catalog/gate
  scoreboard (`docs/phase_f/l2_2_design_a/evidence_index.json` was not
  touched; `scripts/l2_event/evidence.py` writes to a fully separate tracked
  index at `docs/phase_f/l2_event/evidence_index.json`).

## 8. Opus5 review round 2 (M1–M6 hardening + metric corrections)

Opus5's foundation review returned **architecture ACCEPT, metrics/gating
REJECT**. This section documents the required fixes, implemented as new
commits on top of the original 5 (never amending them), plus the explicit
"reproduce Opus's false greens" test scenarios that must now fail/refuse.

### M1 — support/null refusals inside the core evaluator

`metrics.py` now enforces, before any PASS/FAIL/SEED_NOISE determination:

* **RA repeated-firing**: refuses `INSUFFICIENT_KARR_SUPPORT` unless the
  pooled Karr fire-tick count across all seeds is `>= 50`
  (`DEFAULT_MIN_KARR_FIRE_TICKS`).
* **Cytokinesis single-firing** (spec C2): refuses
  `INSUFFICIENT_KARR_SUPPORT` unless `>= 45/50` seeds show a Karr fire
  (`DEFAULT_MIN_KARR_FIRED_SEED_FRACTION = 0.9`).
* **Any channel**: `DEGENERATE_NULL` when the Karr-only clustered bootstrap
  null collapses to `q95_null == 0.0` — a zero-spread null cannot
  discriminate SEED_NOISE from PASS, so neither verdict is reachable; the
  channel is REFUSED instead. `count_gate()`'s D3 support-window guard is
  checked (and can hard-`FAIL`) *before* the degenerate-null check, since a
  guard violation is unconditionally wrong regardless of null quality — see
  `metrics.py` inline comments for the precedence rationale.
* **New `NO_OC_SUPPORT` verdict** (`payload_gate`): fires when Karr has a
  non-empty payload component set but every OC-side payload dict is
  structurally empty (`[{}] * n`, the shape an allocation-starved OC tick
  actually produces) — previously this fell through to a per-component
  bootstrap and reported the far-less-informative `DEGENERATE_NULL`.
* These floors are currently **code-level defaults** in `metrics.py`
  (`DEFAULT_MIN_KARR_FIRE_TICKS`, `DEFAULT_MIN_KARR_FIRED_SEED_FRACTION`),
  not registry YAML fields — a deliberate, narrower reading of "generic
  registry-configured floors" for this round; promoting them to
  `EventRegistryEntry` fields is a small, mechanical follow-up if a future
  process branch needs a non-default floor.

### M2 — `evaluate_gate()` runs the full gauntlet itself

`evaluate_gate()` no longer takes bare `adapter_id`/`event_timing_model`/
`magnitude_gateable` strings that a caller could hand-assemble to skip a
check. It now takes `registry_entry: EventRegistryEntry` and
`adapter: EventAdapter` objects and internally calls the same
ensemble-size, `check_adapter` (registered / process-match /
`gating_ready`), window-metadata/stride, and support checks the CLI path
already ran — so **calling `evaluate_gate()` directly can no longer bypass
any refusal the CLI would have applied**. `main()`'s gate-mode block calls
the same `evaluate_gate()` path; there is exactly one gauntlet, not a
CLI-only one and a laxer programmatic one.

### M3 — RA payload mapping uses real component keys, not raw positions

`RibosomeAssemblySmokeAdapter` now accepts an explicit
`complex_index_by_wid: dict[int, str] | None` constructor mapping. When
supplied (as `run_structural_smoke()` now does, building it once from
tick-0's inferred wids via `build_karr_conditioned_state`), payload keys
are the real complex names (e.g. `RIBOSOME_30S`/`RIBOSOME_50S`) instead of
positional `complex_0`/`complex_1` placeholders — closing the risk of two
differently-ordered but same-length payloads silently comparing as
"matching" components. `payload_gate()` separately asserts the Karr/OC
component key spaces are exactly equal before computing any metric
(`disjoint component key spaces` → hard `FAIL`, never silently ignored).
The adapter's docstring now explicitly declares RA's `fire_count`
semantics: **tick incidence** (how many ticks show a fire), never a
particle/molecule count — verified by a dedicated test constructing a
multi-particle single-tick fire and asserting `fire_count == 1`.

### M4 — stride/window-boundary metadata contract

`window_loader.py`'s `load_and_check_window()` now requires, by default
(`require_stride_contract=True`), that trace metadata carry `stride == 1`,
`tick_start`, and at least one of `tick_end`/`window_anchor` — see the new
`docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md` for the full
contract (documentation-only; no extraction performed or proposed).
Neither real event MAT on disk today satisfies this contract, so:

* the RA seed-0 structural smoke explicitly opts out
  (`require_stride_contract=False`) and surfaces the incompleteness as a
  non-fatal `stride_contract_ok=False` field plus a `reasons` entry in the
  written evidence (see the regenerated `result.json`, §3.1) — it never
  silently passes;
* any real (non-smoke) gate computation attempted against either file with
  the default strict contract raises
  `EventWindowRefused("INCOMPLETE_WINDOW", ...)`.

### M5 — catalog cross-check scope correction

`registry.validate_against_catalog()`'s `harness_type` consistency check
is now gated on `in_scope_v4` — it only enforces agreement for registry
rows the v4 spec actually governs, checked bidirectionally (every
`in_scope_v4` registry row must appear in the spec's required set, and
vice versa). This was necessary because `FtsZPolymerization`'s registry
entry (`event_registry.yaml`) has been reworded per this review: it
**should leave the event-class profile entirely** (a gradient/continuous
polymerization process was never a good fit for a binary-firing event
gate) but that catalog-owning decision is **pending**, so the row is kept
for now, with `in_scope_v4: false` already reflecting v4's own exclusion.
A dedicated regression test
(`test_validate_against_catalog_ftsz_reclassification_does_not_brick_ribosome_assembly`)
confirms that reclassifying/removing FtsZ's row can never break
RibosomeAssembly's cross-check or smoke path — the two are fully
independent registry rows.

### M6 — audit correctness for incomplete/empty evidence

`evidence.audit_index()` previously had nothing to iterate for a row with
`mode: INCOMPLETE` and empty `artifact_hashes` (e.g. a bundle missing a
mandatory file) — the per-file hash-comparison loop simply ran zero times,
so the row contributed **zero problems**, indistinguishable from a
genuinely clean audit. `audit_index()` now explicitly flags any
`INCOMPLETE`/empty-`artifact_hashes` row as a problem in its own right —
verified by
`test_audit_index_flags_incomplete_row_as_a_problem_not_a_silent_pass`.

### Metric-correctness items (bundled into this round per Opus5's request)

* **Payload null is per-component, seed-cluster bootstrapped, and matched
  to the worst-component statistic** — no pooling of heterogeneous
  components into one null, and no naive per-fire (rather than per-seed)
  resampling, which would pseudo-replicate within a seed and understate the
  null's spread. Timing's null remains seed-cluster preserved (unchanged
  from the original foundation, re-verified under the new floor logic).
* **`DEFAULT_K_ENG` is now explicitly documented as provisional** —
  `ProvenanceDoc`/registry carry a `k_eng_provenance` field so a future
  ratified value is never silently indistinguishable from this placeholder.
* **Explicit one-sided empty behavior**: an empty event support case
  refuses (`EMPTY_EVENT_SUPPORT`/`NO_KARR_SUPPORT`/`NO_OC_SUPPORT`
  depending on which side is empty) rather than reporting any capped or
  "silent" green.
* **RA `fire_count` semantics** (tick incidence, not particle count) are
  now declared in both the adapter docstring and a dedicated test (M3,
  above).
* **`git_sha` is now part of `_content_hash()`'s stable dict** — tampering
  with a row's recorded `git_sha` without recomputing `content_hash` is
  caught as a `content_hash mismatch`, the same mechanism that already
  catches a forged `content_hash` field itself
  (`test_audit_index_detects_tampered_git_sha_via_content_hash`). Full
  provenance linkage (e.g. binding to a specific upstream commit chain) is
  left for later work, per Opus5's "where practical" scoping.

### Reproducing Opus5's false-green scenarios — all now fail/refuse

| Scenario | Old (false-green) behavior | New behavior |
|---|---|---|
| `n_seeds=1` ensemble | Could reach a computed verdict | `INSUFFICIENT_KARR_SUPPORT` / `SINGLE_SEED_ENSEMBLE_REQUIRED` |
| 3 Karr fire-ticks (RA repeated) | Could reach PASS/FAIL | `INSUFFICIENT_KARR_SUPPORT` (< 50 pooled fire ticks) |
| `q95_null == 0` (degenerate null) | Could report PASS/SEED_NOISE | `DEGENERATE_NULL`, REFUSED |
| Direct `evaluate_gate()` call, bypassing CLI checks | Could skip adapter/ensemble/window checks | `evaluate_gate()` runs the identical gauntlet internally; no bypass possible |
| Disjoint payload component key spaces | Could silently compare mismatched components | Hard `FAIL` on key-space mismatch |
| `stride=2` (or missing stride contract) window | Could load as if fully enumerated | `EventWindowRefused("INCOMPLETE_WINDOW", ...)` (strict default); smoke path surfaces it non-fatally, never as PASS |
| Incomplete/empty-hash audit row | Zero problems reported | Explicit problem reported |
| FtsZ reclassification | (untested risk of bricking RA's registry row) | Dedicated test proves RA is unaffected |

All eight scenarios above are covered by dedicated regression tests (see
the per-file breakdown in §5); the full suite is **133/133 passing**
(`bin\oc-pytest tests/scripts -k l2_event`), including a re-verified
zero-problem `audit_index()` run against the regenerated RA seed-0 evidence
bundle (git_sha now bound to this round's commits, `stride_contract_ok`
field present and `False`, per M4).
