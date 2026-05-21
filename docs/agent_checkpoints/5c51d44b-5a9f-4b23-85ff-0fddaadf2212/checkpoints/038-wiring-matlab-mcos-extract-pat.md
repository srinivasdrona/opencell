<overview>
OpenCell — open-source Python whole-cell M. genitalium simulation on vivarium-core, ported from Karr 2012's MATLAB WholeCell model. This compaction window picked up after the prior session checkpoint (D.2 design v1→v2 critique loop, p10 partition shipped, m1 MCOS blocker). User asked: (1) for an objective realistic estimate of distance to a complete Karr port, (2) to reconsider whether the m1-mcos-matlab block was actually a blocker given prior MATLAB extractions, then (3) to write a `.m` script for one-off MATLAB extraction of the 44 per-process MCOS fixtures on Windows host. Compaction triggered mid-way through wiring up that MATLAB+Python ingest pipeline.
</overview>

<history>

1. **User asked: "how far are we from implementing the complete Karr model in Python? be realistic."**
   - Gave a calibrated estimate (no calendar time per plan rules). Two definitions: (A) Karr-equivalent v1.0 = M7 target, ≥10/28 phenotypes; (B) full port = all 28 processes/phenotypes.
   - Process scoreboard: 1 real-mechanism (M1 metabolism), 2 prescribed-rate (M2v1, M3v1), 1 designed-not-implemented (D.2), 5-6 planned, ~18 not in any todo.
   - Estimated 6-10 ship-units to M7, 20-50 additional ship-units to full port. Flagged D.2's 3 design passes as cadence indicator and Karr "dark matter" + bound-heavy anchor blind spots as risk multipliers.

2. **User asked: "for m1-mcos-matlab, can't you use the json we extracted to get the complete MATLAB mapping?"**
   - Honest answer: schema yes (full_inventory.json + karr_archive.npz already give us global-state schema), payload no (per-process MCOS fixtures contain unique pre/post test pairs not derivable from anything else).
   - Reframed: we can probably proceed without per-process oracles for v1.0 (snapshot-as-oracle + conservation/topo/competition + integration testing substitute most of the value). Flipped recommendation toward (b3) drop with consolation (mark wontfix, keep scaffolding, design synthetic edge cases later).

3. **User pushed back: "no no, I want to understand why this is a blocker when you could extract .MAT files before. Even then, MATLAB was not available on WSL, so why is it an issue now?"**
   - Sharp clarification needed. Explained: previous extractions worked because source `.mat` files contained *plain structs/numeric arrays* (scipy can decode). Per-process fixtures contain *MCOS class instance serializations* (require MATLAB to deserialize the `__function_workspace__` blob).
   - Same .mat container format, fundamentally different payload type.
   - MATLAB has never been on WSL. Past extractions used pre-saved Karr-distribution data files OR were done on user's Windows host with R2026a — that's exactly the "bootstrap-only" model we already use.
   - So (b2) — one-off Windows MATLAB extract + Python ingest — is the same mechanism that produced the original archive. Not a new dependency.

4. **User: "sure, write the .m script for running on MATLAB"**
   - Surveyed existing `scripts/matlab/` — found `extract_karr_mats.m` already has full MCOS-flattening machinery via metaclass introspection (lines 222-284). Already walks `+process/fixtures/` and `+state/fixtures/` (lines 76-89), but has only ever been run targeted (`karr_flat/` contains only 10 top-level extracts, no fixtures).
   - Chose option #2: write a focused 100-line `extract_per_process_fixtures.m` that does ONLY the 44 fixtures, outputs directly to `data/karr_fixtures/per_process/` (avoids polluting karr_flat/, faster).
   - Created `scripts/matlab/extract_per_process_fixtures.m` (290+ lines) — self-contained, reuses the same `flattenAny()` recursive walker pattern, writes `<Name>_flat.mat` (v7) per fixture + `matlab_extract_manifest.json`. Safe for MATLAB Online Basic tier.
   - Updated `scripts/extract_per_process_fixtures.py`:
     - Added `extract_one_from_flat()` function — ingests `<Name>_flat.mat`, walks the `data` struct via existing `_flatten_struct()`, emits `.npz`/`.json` with `extraction_status: "extracted_from_matlab_flat"`.
     - Added `_json_default()` helper for numpy types in JSON serialization.
     - Added CLI flags: `--from-flat` and `--flat-dir` (defaults to `--out`).
     - Updated main loop to dispatch between MCOS-placeholder mode and from-flat mode.
   - Updated `data/karr_fixtures/per_process/README.md` with two-path documentation: Path A (MATLAB bootstrap → Python ingest) and Path B (pure-Python placeholder, current state). Updated regenerating commands to show both paths.
   - **STOPPED before:** committing changes in worktree, verifying ingestor by running it, drafting unblock notes for SQL todos. Compaction triggered.

</history>

<work_done>

**Files created:**
- `E:\opencell-worktrees\m1-per-process-fixtures\scripts\matlab\extract_per_process_fixtures.m` (~290 lines, 11187 chars). Standalone MATLAB script, runs from repo root, reuses metaclass-introspection pattern from `extract_karr_mats.m`. Outputs `data/karr_fixtures/per_process/<Name>_flat.mat` + `matlab_extract_manifest.json`.

**Files modified (in worktree, NOT committed):**
- `E:\opencell-worktrees\m1-per-process-fixtures\scripts\extract_per_process_fixtures.py`:
  - Module docstring updated with `--from-flat` usage.
  - New `extract_one_from_flat(flat_mat, out_dir, kind) -> dict` function (~70 lines).
  - New `_json_default(o)` helper for numpy/bytes JSON encoding.
  - New CLI args: `--from-flat`, `--flat-dir` (default = `--out`).
  - Main loop now dispatches between `extract_one()` and `extract_one_from_flat()` based on `args.from_flat`. OK statuses extended to include `"extracted_from_matlab_flat"`.
- `E:\opencell-worktrees\m1-per-process-fixtures\data\karr_fixtures\per_process\README.md`:
  - Status section retitled to indicate MATLAB extract path is now wired.
  - Replaced "We therefore commit a best-effort payload here" framing with two-path explanation: Path A (MATLAB bootstrap, recommended) + Path B (pure-Python placeholder, current state).
  - Path A section documents 3-step workflow: run MATLAB script → ingest with `--from-flat` → commit regenerated payloads.
  - "Regenerating" section updated to show both paths.

**Pre-existing context (from earlier in session, before this compaction window):**
- Branch `agent/m1-per-process-fixtures @ 1a4f92f` already has scaffolding committed: extract+validate scripts, 44 placeholder json+npz pairs flagged `extraction_status: unparsed_mcos_payload`, manifest, README, fixture_hashes.json. My new changes are uncommitted on top of that.
- Worktree state: clean before this compaction window's work (just the original 1a4f92f commit).

**Work completed in this window:**
- [x] Wrote `extract_per_process_fixtures.m` with full MCOS support
- [x] Added `--from-flat` ingest mode to Python extractor
- [x] Updated README with two-path workflow
- [ ] **NOT committed yet** — changes are in working tree of `agent/m1-per-process-fixtures` worktree
- [ ] **NOT verified** — haven't run the Python extractor in `--from-flat` dry-mode (would fail without `_flat.mat` inputs but should at least parse args cleanly)
- [ ] **NOT updated** — SQL todos `m1-extract-per-process-fixtures` (currently blocked) and `m1-mcos-decision` (currently pending) still reflect the (b1/b2/b3) decision-pending state, not the chosen-(b2)-and-wired state

</work_done>

<technical_details>

- **MCOS = MATLAB Class Object System.** Karr's per-process fixtures (44 files) were saved via `save('Transcription.mat', 'this')` where `this` is an instance of `edu.stanford.covert.cell.sim.process.Transcription`. MATLAB serializes the object using MCOS into a binary `__function_workspace__` blob inside the .mat container. scipy can read the OUTER container but cannot decode the MCOS payload (deserialization is undocumented). pymatreader and mat4py both explicitly document MCOS as unsupported.

- **MATLAB CAN decode MCOS when class definitions are on path.** That's why `addpath(genpath('data/m1_sources/WholeCell/src'))` is critical in the .m script — without it, MATLAB itself can't deserialize even though the format is native.

- **MATLAB availability model:** never on WSL. User has MATLAB R2026a on Windows host. Existing `scripts/matlab/` directory is "bootstrap-only" per README banner — used for one-off extractions like the Karr archive bootstrap. `extract_per_process_fixtures.m` follows this same model.

- **Two-stage pipeline by design:** MATLAB stage flattens MCOS to plain v7 .mat structs (`<Name>_flat.mat`); Python stage (`--from-flat`) ingests those into the canonical `<Name>.{npz,json}` scheme. This keeps day-to-day Python workflow MATLAB-free and makes the bootstrap reproducible.

- **`extract_karr_mats.m` already exists and could do the same job** — it walks the same fixture dirs (lines 76-89) and uses the same metaclass introspection pattern (lines 222-284). Chose to write a focused script anyway because: (a) faster to run (44 fixtures vs everything), (b) outputs directly to `data/karr_fixtures/per_process/` instead of `karr_flat/`, (c) keeps the per-process workflow self-contained.

- **`.npz` key sanitization:** MATLAB-flattened structs use `/`-delimited paths; npz keys can't contain `/`, so `extract_one_from_flat()` replaces `/` with `__` when writing to npz. JSON `array_keys` field preserves the original `/`-delimited form for downstream lookup.

- **Worktree convention:** each background agent gets its own `E:\opencell-worktrees\<name>` worktree. `m1-per-process-fixtures` worktree is currently uncommitted; main checkout is on `36636f6` (with `70a869d` plan.md checkpoint on top). Active worktrees: `d2-design-v2`, `m1-per-process-fixtures`. `agent/m1-mcos-matlab` was deleted earlier in session.

- **Relevant SQL todos to update once committed:**
  - `m1-mcos-decision` (pending) → `done` with note "chose (b2): wired MATLAB extract + Python ingest pipeline; user runs .m script on Windows host once".
  - `m1-extract-per-process-fixtures` (blocked) → unblock once `m1-mcos-decision` is done; mark `in_progress` until user actually runs the MATLAB script and we ingest the results. Then `done`.

- **Known unverified assumptions in the code I just wrote:**
  - MATLAB `struct(obj)` may fail on some MCOS classes that override convertibility — fallback metaclass walk should handle these but not field-tested.
  - `flattenAny()` at depth>25 returns `'<MAX_DEPTH>'`. Fixtures may have deeper nesting; depth limit may need raising.
  - `extract_one_from_flat()` assumes the MATLAB-side wraps everything in a single top-level struct named `'data'`. The .m script does `save(outPath, 'data', '-v7')` which guarantees this — so the contract holds.
  - `_flatten_struct()` (existing helper) was originally written for sparse MCOS-pointer structures; haven't verified it handles deeply-nested real structs gracefully.

- **Critique loop now standard practice** for non-trivial design work: write → adversarial critique (Sonnet rubber-duck or GPT-5.4 cross-model) → rework. D.2 has gone v1 → v2 → v3 needed. Pattern works but adds 1-2 ship-units of latency per major design.

- **Current test suite state:** 602 passed + 4 xfailed on main (`36636f6` + `70a869d` plan.md checkpoint). p10 mass partition shipped this session.

- **D.2 design v3 still pending** (separate todo `d2-design-v3-rework`, not in this work window). 4 BLOCKERs from GPT-5.4 critique of v2 documented in todo description and plan.md.

</technical_details>

<important_files>

- **`E:\opencell-worktrees\m1-per-process-fixtures\scripts\matlab\extract_per_process_fixtures.m`** (NEW)
  - The MATLAB-side bootstrap script. User runs this once on Windows MATLAB.
  - Walks `data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/{+process,+state}/fixtures/*.mat` (28 + 16 = 44 files).
  - Outputs `data/karr_fixtures/per_process/<Name>_flat.mat` per fixture + `matlab_extract_manifest.json`.
  - Self-contained (no helper-shared dependency on `extract_karr_mats.m`). Safe for MATLAB Online Basic tier.
  - Key sections: lines 1-50 (header/usage), 53-67 (path setup), 70-90 (input discovery), 100-130 (per-fixture loop with `flattenAny()`), 150-300 (helpers: `appendDir`, `flattenAny` recursive walker, `sha256OfFile`).

- **`E:\opencell-worktrees\m1-per-process-fixtures\scripts\extract_per_process_fixtures.py`** (MODIFIED, uncommitted)
  - Python ingestor. Now has dual mode: pure-Python placeholder (default, current state) OR `--from-flat` MATLAB-output ingest (new).
  - `extract_one_from_flat()` is the new function (~70 lines). Loads `<Name>_flat.mat`, walks via existing `_flatten_struct()`, emits per_process/<Name>.{npz,json}.
  - CLI changes around line ~225: added `--from-flat` and `--flat-dir`.
  - Main loop dispatch around line ~250.

- **`E:\opencell-worktrees\m1-per-process-fixtures\data\karr_fixtures\per_process\README.md`** (MODIFIED, uncommitted)
  - User-facing doc. Now documents Path A (MATLAB bootstrap, recommended) and Path B (pure-Python placeholder, current state).
  - Updated "Status" section (lines ~17-75) and "Regenerating" section (around line ~80-95).

- **`E:\opencell-worktrees\m1-per-process-fixtures\scripts\validate_per_process_fixtures.py`** (existing, NOT modified)
  - Will need a `--seed` flag invocation after `--from-flat` ingest to re-seed `fixture_hashes.json`. Already supports this per README.

- **`E:\opencell\plan.md`** (committed earlier as `70a869d` on main)
  - Canonical plan, just synced at session checkpoint. Reflects state through the GPT-5.4 critique of D.2 v2 and m1 MCOS blocker. Will need a small follow-up update once m1 (b2) wiring lands.

- **`scripts/matlab/extract_karr_mats.m`** (existing reference, not modified)
  - The original MATLAB extractor. Source of the `flattenAny()` pattern reused in the new script. Read-only reference.

- **`data/m1_sources/karr_flat/`** (existing data dir)
  - Contains 10 prior-extracted top-level files, NOT including the per-process fixtures. Confirms previous MATLAB extraction was run via `extract_karr_targeted.m` not the full `extract_karr_mats.m`.

</important_files>

<next_steps>

**Immediate next steps (resume from here):**

1. **Verify the Python `--from-flat` mode at least parses cleanly** by running a dry-run:
   ```
   wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/e/opencell-worktrees/m1-per-process-fixtures && .venv-wsl/bin/python scripts/extract_per_process_fixtures.py --name Transcription --from-flat 2>&1 | head -20"
   ```
   Expected: should print a clean `[WARN] process Transcription -> missing_flat_input` (since no MATLAB run has produced `Transcription_flat.mat` yet). If it crashes, the `extract_one_from_flat()` impl needs fixing.

2. **Commit the changes** in the worktree:
   ```
   cd /mnt/e/opencell-worktrees/m1-per-process-fixtures
   git add scripts/matlab/extract_per_process_fixtures.m scripts/extract_per_process_fixtures.py data/karr_fixtures/per_process/README.md
   git commit -m "M1: wire MATLAB MCOS extract path (option b2)
   
   Adds scripts/matlab/extract_per_process_fixtures.m (one-off MATLAB
   bootstrap) and --from-flat mode to scripts/extract_per_process_fixtures.py
   (Python ingest of MATLAB-flattened outputs). README documents both Path A
   (MATLAB bootstrap) and Path B (pure-Python placeholder, current state).
   
   User runs the .m script once on Windows MATLAB host; agents in WSL then
   ingest the _flat.mat outputs via --from-flat. Same bootstrap pattern as
   the existing Karr archive.
   
   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
   ```

3. **Hand off to user** with concise instructions to run the .m script on Windows:
   ```matlab
   >> cd <opencell repo root>
   >> run('scripts/matlab/extract_per_process_fixtures.m')
   ```
   Then user reports back, agent ingests via `--from-flat` and re-seeds hashes.

4. **Update SQL todos:**
   - `m1-mcos-decision` → `done` with note "chose (b2); wired in PR on agent/m1-per-process-fixtures".
   - `m1-extract-per-process-fixtures` → `pending` (no longer `blocked`; awaiting user to run MATLAB script and report `_flat.mat` files committed).

5. **Optional follow-up commits in same worktree** once user ships `_flat.mat` files:
   - Run `python scripts/extract_per_process_fixtures.py --all --from-flat` to regenerate per_process/<Name>.{json,npz} with real data.
   - Run `python scripts/validate_per_process_fixtures.py --seed` to re-seed `fixture_hashes.json`.
   - Commit regenerated fixtures + flat .mats + new hashes.
   - Consider whether to commit the `_flat.mat` files (intermediate format) or only the canonical `.npz/.json` (probably commit both — flats are a useful audit trail and not huge).

**Open decisions / unknowns:**
- Whether to merge `agent/m1-per-process-fixtures` to main now (with placeholder data + working scripts) or wait until real data lands. Probably wait — the README makes the placeholder state visible but it's confusing to ship.
- Whether `extract_one_from_flat()` correctly handles MATLAB-flattened sentinel strings (`<function_handle:...>`, `<unhandled:...>`). They'll come through as char arrays via `_flatten_struct`, end up in scalars dict — should be fine.
- D.2 design v3 rework is still queued (separate critical-path todo). Not part of this work window but is the binding constraint on Karr-equivalent v1.0.

**Do NOT:**
- Commit anything to main directly. All work stays in `agent/m1-per-process-fixtures` worktree.
- Try to install MATLAB in WSL.
- Run the Python extractor in `--from-flat` mode against missing inputs and treat the warnings as failures — that's expected pre-MATLAB-run state.

</next_steps>