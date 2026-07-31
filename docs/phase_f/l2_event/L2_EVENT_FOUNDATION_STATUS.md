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

7 new files under `tests/scripts/test_l2_event_*.py`, **107 tests, all
passing**:

| File | Count | Covers |
|---|---|---|
| `test_l2_event_schema.py` | 7 | `EventObservation`/`EventTimeline` invariants, atomic JSON round-trip |
| `test_l2_event_window_loader.py` | 16 | Every D1 refusal branch (synthetic HDF5 fixtures) + real RA seed-0 load + real standard-trace refusal |
| `test_l2_event_registry.py` | 12 | Registry↔catalog cross-check, schema/version/timing-model validation, v4-scope correctness for all 4 processes |
| `test_l2_event_metrics.py` | 29 | Count/timing/payload gates (PASS/FAIL/SEED_NOISE/NO_KARR_SUPPORT), no-zero==zero-PASS, C6 spurious-fire detection, bootstrap sanity, `_safe_wasserstein` edge cases |
| `test_l2_event_evidence.py` | 14 | Write/bundle/index/audit round-trip, tamper + stale-content-hash detection, fresh-clone (bundle-only) audit, Windows-worktree-`gitdir` fallback (§5.1) |
| `test_l2_event_adapters.py` | 10 | Fakes, adapter-mismatch, anti-laundering signature checks, real RA seed-0 adapter + end-to-end structural smoke |
| `test_l2_event_runner.py` | 26 | Full refusal gauntlet, `evaluate_gate()` wiring, CLI-level dispatch for all 4 processes, real-data smoke + evidence-writing round trip |

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
