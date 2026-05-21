<overview>
The user is building OpenCell, an open-source whole-cell M. genitalium simulation in Python on vivarium-core, ported from Karr 2012's MATLAB WholeCell model. The current task is **MATLAB eviction**: package every Karr `.mat` field consumed by `karr_native_ingest_*.py` scripts into a single committed Python-native archive (`data/karr_archive/`) so that day-to-day Python workflows have zero MATLAB dependency. MATLAB becomes bootstrap-only — needed only when new fields must be extracted. User constraint (re-emphasised throughout): "Don't hardcode any values and all these changes should scale to our final whole cell model."
</overview>

<history>

1. **Earlier user request: "fix m2-counts and then do the MATLAB extraction"** (summarized prior context)
   - Shipped m2-counts-fix as commit `e6d748a` (599 + 3 xfail). Built initial archive infrastructure: `scripts/build_karr_archive.py`, `opencell/_karr_archive.py`, refactored `karr_native_ingest_m2.py` to use archive (proven byte-identical fixture).

2. **User: "You are not recoding to fix the tests, right?... should scale to our final whole cell model"**
   - Reverted one regression-hide test flip; pinned as xfail. Confirmed all m2 changes are structural/helper-based, not hardcoded.

3. **Continuing MATLAB eviction (current task — implicit continuation):**
   - Surveyed the 3 missing .mat files (`transcription_v2_targeted`, `translation_v2_targeted`, `metabolism_dynamics`).
   - Extended `ARCHIVE_SPEC` in `scripts/build_karr_archive.py` with 3 new entries:
     - `transcription_v2_targeted` (50 flat fields)
     - `translation_v2_targeted` (37 flat fields)
     - `metabolism_dynamics` (HDF5 v7.3, 19 datasets via h5py branch)
   - Added `format: "hdf5_v73"` marker plus h5py branch in `main()` of build script.
   - Extended `protein_complexes` spec to add 5 more nested struct arrays (subcomplexes, metabolites, prosthetic, chaperones, rnas — was only `monomers` before) plus 3 top-level metadata fields (`x_source_file`, `x_matlab_release`, `x_extract_timestamp_utc`).
   - Rebuilt archive: now 143 ndarrays + 124 string-keys, ~786KB total, covers all 8 .mat files.
   - Refactored all 7 remaining ingest scripts (`m1`, `compartmented`, `complexes`, `m3`, `m1_dynamics`, `m2v2`, `m3v2`) to use `load_karr_archive()` instead of `loadmat()`/`h5py.File()`. Removed all `MAT = ...` path constants. Updated JSON metadata to `source_archive` + `source_archive_files`.
   - For `karr_native_ingest_complexes.py`, full rewrite was required (old code used recursive `_to_dict` on mat_struct → list of dicts; new code uses `_StructArray` per-row + `_NestedStructArray.per_parent(i)` API).
   - Backed up all fixtures as `.bak2`, re-ran all 8 ingest scripts, diffed each against backup with `diff_all_fixtures.py`.
   - First diff round: complexes had 194 differences, all on `activation_rule` and `formation_compartment_wid` fields where MATLAB empty `[]` was being serialized as the string `"[]"` instead of `""`. Fixed with falsy-check. Re-ran complexes — 0 diffs.
   - Final state: ALL fixtures byte-identical except for `source_*` metadata labels.
   - Ran full `pytest -x -q`: **599 passed + 3 xfailed** in 803s — same as baseline. Verified end-to-end through the chassis.
   - Wrote `data/karr_archive/README.md` (archive is single source of truth; MATLAB is bootstrap-only).
   - Marked `scripts/matlab/README.md` as bootstrap-only at top.
   - Wrote `scripts/validate_karr_archive.py` — re-runs all ingest, hashes outputs, compares to committed `fixture_hashes.json` (with `--update` to seed).

</history>

<work_done>

**Files created (all in repo root unless noted):**
- `data/karr_archive/README.md` — bootstrap-only doc, usage examples, schema notes.
- `scripts/validate_karr_archive.py` — CI-friendly drift detector: re-runs all 8 ingest scripts, hashes fixtures (npz: array-content hash; JSON: payload minus `source_*` keys), compares to `data/karr_archive/fixture_hashes.json`. Supports `--update` and `--skip-rerun` flags.
- Scratch (delete at end): `diff_m1.py`, `diff_complexes.py`, `diff_all_fixtures.py`, `probe_archive2.py`, `probe_complexes.py`, `run_ingest_all.sh`.

**Files modified:**
- `scripts/build_karr_archive.py`:
  - Added `import h5py` (with try/except).
  - Extended `ARCHIVE_SPEC` for `protein_complexes`: added 6 more top-level fields and 5 more nested struct arrays.
  - Added 3 new ARCHIVE_SPEC entries: `transcription_v2_targeted`, `translation_v2_targeted`, `metabolism_dynamics`.
  - In `main()`, added an `if spec.get("format") == "hdf5_v73":` branch that uses `h5py.File` to walk top-level datasets and store under same `{basename}__{path}` key scheme.
- `scripts/karr_native_ingest_m1.py` — replaced `loadmat()` block with `load_karr_archive()`; updated JSON metadata.
- `scripts/karr_native_ingest_compartmented.py` — same refactor.
- `scripts/karr_native_ingest_complexes.py` — full rewrite using `_StructArray` per-row iteration + `_NestedStructArray.per_parent(i)`. Added `"[]"`→`""` normalization.
- `scripts/karr_native_ingest_m3.py` — same refactor.
- `scripts/karr_native_ingest_m1_dynamics.py` — replaced `h5py.File()` block with archive access; kept transpose semantics (`.T` to restore column-major).
- `scripts/karr_native_ingest_m2v2.py` — same refactor.
- `scripts/karr_native_ingest_m3v2.py` — same refactor.
- `scripts/matlab/README.md` — added bootstrap-only banner at top.
- `data/karr_archive/karr_archive.npz` — 151KB, 143 arrays.
- `data/karr_archive/karr_archive_strings.json` — 634KB, 124 keys.
- `data/karr_archive/karr_archive_manifest.json` — refreshed.

**Tasks completed (this session segment):**
- [x] Extend `build_karr_archive.py` with v2 + HDF5 branch + complexes nested expansion
- [x] Refactor all 7 remaining ingest scripts to use the archive
- [x] All 8 fixtures byte-identical to pre-eviction (modulo `source_*` metadata labels)
- [x] Full test suite: 599 passed + 3 xfailed (= baseline)
- [x] `data/karr_archive/README.md`
- [x] `scripts/matlab/README.md` bootstrap-only banner
- [x] `scripts/validate_karr_archive.py`

**Tasks remaining:**
- [ ] Run `python scripts/validate_karr_archive.py --update` to seed `fixture_hashes.json`
- [ ] Delete scratch files: `diff_m1.py`, `diff_complexes.py`, `diff_all_fixtures.py`, `probe_archive2.py`, `probe_complexes.py`, `run_ingest_all.sh`, all `*.bak`/`*.bak2` files in `data/karr_fixtures/`
- [ ] Commit MATLAB-eviction as a single commit
- [ ] Update plan.md "MATLAB Eviction" section: mark done with commit ref
- [ ] Surface remaining backlog items: `e2-decision-point`, `m2-per-condition-snapshots`

</work_done>

<technical_details>

**Archive design:**
- **Consumed-fields whitelist** (~100 paths) not exhaustive dump — KB has 1411 fields, sim_fitted has 2876.
- **scipy.io.loadmat reads .mat without MATLAB**; h5py reads HDF5 v7.3 without MATLAB. MATLAB is only needed to *produce* new .mat files.
- **Struct arrays flattened to parallel columns** with per-row iteration via `_StructArrayRow` views.
- **Nested struct arrays use offsets array** for parent slicing: `complexes.monomers.per_parent(i)` returns child `_StructArray`.

**Quirks discovered/resolved this session:**
- **HDF5 v7.3 transposes 2D arrays vs MATLAB's column-major** — preserved by storing raw shape and consumers calling `.T` (e.g., `snapshot_substrates`, `bounds_dynamic_*`).
- **MATLAB empty `[]` serialization gotcha**: `_StructArray` returns the string `"[]"` for empty MATLAB arrays in object columns. Original `_to_dict`-based ingest produced `""` because Python `[]` is falsy. Fix in complexes ingest: explicit `"[]"`→`""` normalization for `activation_rule` and `formation_compartment_wid`.
- **NaN equality** (from prior session, still relevant): `np.array_equal` requires `equal_nan=True` to validate NaN-containing arrays.
- **PowerShell + WSL + bash quoting hell**: avoid inline `python -c` with quotes; write probe code to a file and run it. Also: bash scripts created from Windows have CRLF; need `sed -i 's/\r$//'` before running.
- **PowerShell + WSL `for $s in ...`**: PowerShell eats `$s`. Solution: write a `.sh` file and `bash run.sh`.

**Validation strategy:**
- `diff_all_fixtures.py` verified all 16 fixture files (8 JSON + 7 NPZ + 1 vocab) — only `source_*` metadata keys differ; all numeric arrays and string lists are bit-identical.
- `scripts/validate_karr_archive.py` is the persistent CI-friendly version (hashes computed insensitive to `source_*` metadata).

**Test status:** 599 passed + 3 xfailed in 803s (~13.4 min) — exactly matches baseline `e6d748a`.

**Environment:** WSL `Ubuntu-22.04`, venv `.venv-wsl`. HEAD = `e6d748a` (m2-counts-fix). Archive build runs cleanly; h5py installed.

</technical_details>

<important_files>

- `scripts/build_karr_archive.py`
  - Single source of truth for what gets extracted. `ARCHIVE_SPEC` dict at top defines per-mat: `fields`, `struct_arrays` (with `scalars`, `nested_struct_arrays`), `format` marker for HDF5.
  - HDF5 branch in `main()` uses `h5py.File` and walks `spec["fields"]` as flat top-level datasets.
  - 8 entries total covering all .mat files.

- `opencell/_karr_archive.py`
  - Public API: `load_karr_archive()` returns `{basename: _Namespace}` dict (cached via `lru_cache`).
  - `_Namespace` (nested attribute walker), `_StructArray` (column-view + per-row iteration), `_NestedStructArray.per_parent(i)` (offsets-based slice).
  - **Did not need changes this session** — manifest-driven; both new flat-field entries (v2) and HDF5 entries work via existing `kind: ndarray` path.

- `scripts/karr_native_ingest_complexes.py`
  - **Most-rewritten script.** Old code used recursive `_to_dict` on mat_struct producing nested Python lists/dicts. New code iterates `_StructArray` rows directly and uses `_NestedStructArray.per_parent(i)` for monomers/subcomplexes/metabolites/prosthetic/chaperones/rnas.
  - Key gotcha at lines for `activation_rule`/`formation_compartment_wid`: `"[]"`→`""` normalization needed.

- `scripts/karr_native_ingest_m1_dynamics.py`
  - Reference for how to consume HDF5 fields from the archive — `np.asarray(arc["metabolism_dynamics"].snapshot_substrates).T` etc.

- `data/karr_archive/`
  - 4 files: `karr_archive.npz` (151KB, 143 arrays), `karr_archive_strings.json` (634KB, 124 keys), `karr_archive_manifest.json`, `README.md`.

- `data/karr_fixtures/*.bak2`
  - Pre-eviction backups. **Delete before commit.**

- `scripts/validate_karr_archive.py`
  - CI-friendly drift detector. Needs initial seeding via `--update` to create `fixture_hashes.json`.

- Scratch files in repo root (DELETE before commit): `diff_m1.py`, `diff_complexes.py`, `diff_all_fixtures.py`, `probe_archive2.py`, `probe_complexes.py`, `run_ingest_all.sh`. Also pre-existing scratch from prior session: `probe_sim_struct.py`, `probe_archive.py`, `probe_v2_mats.py`, `test_archive_loader.py`, `diff_fixtures.py`, `check_nan.py`.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`
  - "MATLAB Eviction (in progress)" section. Update when committing.

</important_files>

<next_steps>

**Immediate (in order):**

1. **Seed expected hashes:**
   ```
   wsl bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python scripts/validate_karr_archive.py --update --skip-rerun'
   ```

2. **Clean up scratch files** in repo root:
   - This session: `diff_m1.py`, `diff_complexes.py`, `diff_all_fixtures.py`, `probe_archive2.py`, `probe_complexes.py`, `run_ingest_all.sh`
   - Prior session leftovers: `probe_sim_struct.py`, `probe_archive.py`, `probe_v2_mats.py`, `test_archive_loader.py`, `diff_fixtures.py`, `check_nan.py`
   - All `data/karr_fixtures/*.bak` and `*.bak2` files

3. **Update plan.md**: change "MATLAB Eviction (in progress)" → "MATLAB Eviction (DONE — commit <sha>)" with summary stats: 8 ingest scripts refactored, archive at 786KB, all fixtures byte-identical, 599+3 tests pass.

4. **Single commit** with all changes:
   - 8 ingest scripts refactored
   - `scripts/build_karr_archive.py` extended
   - `data/karr_archive/` (4 files)
   - `scripts/validate_karr_archive.py` new
   - `scripts/matlab/README.md` bootstrap banner
   - Co-authored-by trailer required
   - Suggested message: `MATLAB eviction: archive all consumed Karr .mat fields into data/karr_archive/`

5. **Surface to user**: remaining backlog priorities are `e2-decision-point` (D.2 complex assembly vs M5 replication vs v2 mechanics), `m2-per-condition-snapshots` (the xfail TODO from m2-counts-fix), and the per-AA mapping deferral.

**Open / blockers:** None. Eviction is complete and verified.

</next_steps>