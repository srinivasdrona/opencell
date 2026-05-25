# Fixture Pipeline Diagnosis

## Q1. What the extraction pipeline produces, and how

### Pipeline path found

1. MATLAB extractor reads Karr WholeCell test fixtures from:
   - `data/m1_sources/WholeCell/src_test/+.../+process/fixtures/*.mat`
   - `data/m1_sources/WholeCell/src_test/+.../+state/fixtures/*.mat`
   (`scripts/matlab/extract_per_process_fixtures.m:6-8`, `:71-78`).
2. For each source `.mat`, it loads `raw`, flattens with `flattenAny`, and writes `<Name>_flat.mat` containing top-level `data` (`scripts/matlab/extract_per_process_fixtures.m:107-109`, `:33-34`).
3. Python ingest then reads `<Name>_flat.mat` with `--from-flat`, recursively flattens `data` into arrays/scalars, and writes `<Name>.npz` + `<Name>.json` (`scripts/extract_per_process_fixtures.py:221-230`, `:271-280`, `:299-326`, `:402-405`).

### Where time-series is collapsed

- There is no explicit “collapse-to-1-tick” transform in the Python ingest path; it mostly preserves numeric arrays as found in `data.fixture` (`scripts/extract_per_process_fixtures.py:86-117`, `:271-280`, `:299-304`).
- The MATLAB flattening step is lossy for object graphs:
  - hard depth cap (`depth > 6` -> `'<MAX_DEPTH>'`) (`scripts/matlab/extract_per_process_fixtures.m:190-193`)
  - handle-object cycle cut (`<handle:...>` sentinel, no recursion) (`scripts/matlab/extract_per_process_fixtures.m:178-184`, `:304-309`).
- Net finding: these `_flat.mat` fixtures are snapshot-style process/state objects, not per-tick traces. So the practical “collapse” is upstream in source fixture type (single MCOS fixture instance) plus lossy flattening of handle links, not a dedicated tick-axis reducer.

### Direct `scipy.io.loadmat()` structure dumps (WSL)

```text
===== Cytokinesis_flat.mat =====
top['data'] shape=(1, 1) dtype=object type=ndarray
data.shape= (1, 1) data.dtype= object
data[0,0] class= mat_struct field_count= 1 fields_head= ['fixture']
fixture type= ndarray shape= (1, 1) dtype= object
fixture[0,0] class= mat_struct field_count= 117 fields_head= [...]
fixture.substrates: shape=(3, 1) dtype=int32 ndim=2
fixture.enzymes: shape=(4, 1) dtype=uint8 ndim=2
fixture.boundEnzymes: shape=(4, 1) dtype=uint8 ndim=2

===== Transcription_flat.mat =====
top['data'] shape=(1, 1) dtype=object type=ndarray
data.shape= (1, 1) data.dtype= object
data[0,0] class= mat_struct field_count= 1 fields_head= ['fixture']
fixture type= ndarray shape= (1, 1) dtype= object
fixture[0,0] class= mat_struct field_count= 129 fields_head= [...]
fixture.substrates: shape=(12, 1) dtype=int32 ndim=2
fixture.enzymes: shape=(6, 1) dtype=uint8 ndim=2
fixture.boundEnzymes: shape=(6, 1) dtype=uint8 ndim=2
```

Additional probe summary:
- All 44 `_flat.mat` files had `data[0,0]` fieldnames exactly `['fixture']` (no per-tick wrapper fields).
- No fixture field names matched `states_before`, `states_after`, `inputs`, `outputs`, `tick` (only incidental strings like `timeAveragedCellWeight`).

## Q2. What the Karr source `.mat` contains

### Local availability

- This worktree does **not** contain `data/m1_sources/WholeCell` (expected upstream source clone path), while scripts/readme clearly point there (`scripts/bootstrap.sh:47-63`, `data/karr_fixtures/per_process/README.md:9-15`).
- `matlab_extract_manifest.json` in committed fixtures still records source input paths under `src_test/.../fixtures/*.mat` and successful flatten outputs, so provenance is preserved (`scripts/matlab/extract_per_process_fixtures.m:101-104`, `:121`, `:125-139`).

### Spot-check from actual source fixtures

Since local clone is absent, I downloaded 2 upstream source fixtures directly from CovertLab/WholeCell (same paths referenced above) and ran `scipy.io.loadmat`:

```text
===== source Cytokinesis.mat =====
top['None'] shape=(1,) dtype=[('s0','O'),('s1','O'),('s2','O'),('arr','O')] type=MatlabOpaque
dtype.names= ('s0', 's1', 's2', 'arr')
field s0: shape=() dtype=|S7      -> "fixture"
field s1: shape=() dtype=|S4      -> "MCOS"
field s2: shape=() dtype=|S48     -> "edu.stanford.covert.cell.sim.process.Cytokinesis"
field arr: shape=(6, 1) dtype=uint32
top['__function_workspace__'] shape=(1, 68668256) dtype=uint8 nbytes=68668256
keys_nonmeta ['None']

===== source Transcription.mat =====
top['None'] shape=(1,) dtype=[('s0','O'),('s1','O'),('s2','O'),('arr','O')] type=MatlabOpaque
field s2 -> "edu.stanford.covert.cell.sim.process.Transcription"
field arr: shape=(6, 1) dtype=uint32
top['__function_workspace__'] shape=(1, 68716184) dtype=uint8 nbytes=68716184
keys_nonmeta ['None']
```

Interpretation:
- Source fixtures are MCOS object blobs, not directly exposed tick tables in scipy.
- In raw scipy view, there is no explicit `n_ticks`, `inputs`, or `outputs` key.
- Any richer structure lives in `__function_workspace__` and requires MATLAB/MCOS decoding (consistent with script comments: `scripts/extract_per_process_fixtures.py:8-11`, `:35-40`; `data/karr_fixtures/per_process/README.md:19-27`).

### Can we get source fixtures if missing locally?

Yes:
- `scripts/bootstrap.sh` clones WholeCell into `data/m1_sources/WholeCell` (`scripts/bootstrap.sh:61-62`).
- README documents same source location and MATLAB re-extract path (`data/karr_fixtures/per_process/README.md:9-15`, `:36-58`).

## Q3. What replay harness consumes

### Expected fixture shape

Replay reads companion `.npz` arrays and tries to infer:
- `n_ticks` from JSON keys (`n_ticks`/`nticks`/`num_ticks`) or tick-hinted arrays (`opencell/validation/replay.py:120-145`).
- input/output channels from key-name hints (`state_before`, `states_after`, `input`, `output`, etc.) (`opencell/validation/replay.py:25-43`, `:172-207`).
- tick-major slicing at replay time (`opencell/validation/replay.py:264-275`, `:325-342`).

### Why current fixtures fail replay utility

- For current fixtures, companion arrays have no tick-hint keys and no manifest `n_ticks`, so `_infer_n_ticks` falls back to `1` (`opencell/validation/replay.py:120-145`).
- With `n_ticks == 1`, `_split_inputs_outputs` does not apply the multi-tick fallback that auto-fills outputs (`opencell/validation/replay.py:202-206`), leaving `inputs={}` and `outputs={}` in practice.
- Integration smoke test explicitly xfails in this condition (`tests/integration/test_replay_smoke.py:46-50`).

### Would harness work with multi-tick fixtures as-is?

Mostly yes.
- Synthetic probe (temp fixture) with `manifest.n_ticks=3` and keys `state_before/...` + `states_after/...` loaded as:
  - `n_ticks 3`
  - `inputs {'state_before/substrates': (3, 2)}`
  - `outputs {'states_after/substrates': (3, 2)}`
- This matches current harness design (`opencell/validation/replay.py:120-145`, `:172-207`, `:325-342`).

## Diagnosis summary

- Gap is a **data-shape mismatch**: committed per-process fixtures are snapshot object dumps, not replay traces with explicit per-tick input/output channels.
- Replay harness is not fundamentally blocked by code architecture; it is blocked by fixture content/schema.
