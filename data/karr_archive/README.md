# Karr Archive — Python-Native Snapshot of Karr 2012 .mat Data

This directory is the **single source of truth** for every datum the
`opencell` ingestion scripts pull out of Karr's MATLAB `.mat` files. After
this archive is built once, **MATLAB is no longer required** for any
day-to-day Python workflow (running ingest scripts, running tests,
running the chassis).

## Contents

| File | Purpose |
|---|---|
| `karr_archive.npz` | All numeric ndarrays from the consumed-fields whitelist (compressed). |
| `karr_archive_strings.json` | All string arrays + scalar values. |
| `karr_archive_manifest.json` | Per-field provenance: source `.mat`, dotted path, dtype, shape, sha256, struct-array layout. |

## What's covered

The archive packages **only the fields actually consumed** by
`scripts/karr_native_ingest_*.py` (about 100 leaves out of ~4300 total
across the 8 source `.mat` files). It is not an exhaustive dump — adding
new fields requires editing `ARCHIVE_SPEC` in
`scripts/build_karr_archive.py` and re-running.

| Source `.mat` | Consumer ingest script(s) |
|---|---|
| `proteins_targeted.mat` | `karr_native_ingest_m3.py` |
| `rnas_targeted.mat` | `karr_native_ingest_m2.py` |
| `protein_complexes.mat` | `karr_native_ingest_complexes.py` |
| `sim_fitted_targeted.mat` | `karr_native_ingest_m1.py`, `karr_native_ingest_m2.py`, `karr_native_ingest_compartmented.py` |
| `knowledgeBase_targeted.mat` | `karr_native_ingest_m2.py` |
| `transcription_v2_targeted.mat` | `karr_native_ingest_m2v2.py` |
| `translation_v2_targeted.mat` | `karr_native_ingest_m3v2.py` |
| `metabolism_dynamics.mat` (HDF5 v7.3) | `karr_native_ingest_m1_dynamics.py` |

## How to use the archive (Python)

```python
from opencell._karr_archive import load_karr_archive

arc = load_karr_archive()
S = arc["sim_fitted_targeted"].metabolism.fbaReactionStoichiometryMatrix  # (376, 504)
gene_ids = arc["knowledgeBase_targeted"].knowledgeBase.genes.wholeCellModelID  # length-525 list
for g in arc["knowledgeBase_targeted"].knowledgeBase.genes:
    g.halfLife  # per-row attribute access on the struct array
```

Struct arrays (e.g. `genes`, `complexes`) are stored as parallel columns;
the loader exposes both column-views (`genes.wholeCellModelID` →
length-525 list) and per-row iteration (`for g in genes: g.halfLife`).
Nested struct arrays (e.g. `complexes[i].monomers`) use offsets-based
flattening; access a child slice via `complexes.monomers.per_parent(i)`.

## Bootstrap-only: when you need to regenerate the archive

You only need MATLAB if you want to **add new fields** to the archive
(e.g., a downstream subsystem requires a property nobody has extracted
before).

```bash
# 1. Run Karr's WholeCell sim in MATLAB to produce the .mat files.
#    See scripts/matlab/README.md.

# 2. Extend ARCHIVE_SPEC in scripts/build_karr_archive.py with the new
#    field paths.

# 3. Rebuild the archive (Python only after step 1):
python scripts/build_karr_archive.py

# 4. Commit data/karr_archive/{karr_archive.npz, *.json}.
```

## Validation

`scripts/karr_native_ingest_*.py` were re-run after the archive replaced
direct `.mat` reads. Output fixtures in `data/karr_fixtures/` are
byte-identical to the pre-eviction versions (modulo `source_*` metadata
labels). The full test suite (599 passed + 3 xfailed) passes unchanged.

## Schema

`karr_archive__v1` — see `karr_archive_manifest.json` for full per-field
metadata.
