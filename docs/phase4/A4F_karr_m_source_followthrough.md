# A4-followthrough: Karr `.m` source + parameter ingestion path

**Status:** complete (2026-04-25)
**Predecessor:** `docs/phase4/A4_karr_extraction_spike.md`
**Outcome:** **M-phase ingestion path proven and de-risked.**

## TL;DR

The original A4 spike opened a `.mat` test fixture and got opaque
`uint32` leaves (first leaf `3707764736` — almost certainly a MATLAB
object handle). A4-followthrough fixed two unknowns:

1. **Why `.mat` looks opaque** — `src_test/.../CellStateFixture.m` saves
   *MATLAB CellState class instances* via `save('-v7', f, 'fixture')`
   then rewrites the header. scipy.io can read the struct shell but
   cannot reconstruct MATLAB classes. The `s0/s1/s2/arr` fields are
   `SparseMat` object internals, not biology. **`.mat` fixtures are
   state snapshots, not parameter tables — wrong source for ingestion.**

2. **Where the parameters actually live** — `data/parameters.json`
   (5238 B) is a complete, organised, human-readable manifest of every
   process and state parameter Karr's MATLAB simulator boots from. Units
   are NOT in the JSON; they are recovered from the matching
   `src/+state/*.m` and `src/+process/*.m` source files.

A4-followthrough ingested 18 real Karr parameters into the A3 store
through that recovered path, with the bounded-tuning policy honoured.

## Evidence

`scripts/karr_a4f_compare.py` confirmed the `.mat` opacity is structural,
not file-specific: 3 different state classes (`MetabolicReaction`,
`Time`, `Host`) with declared field counts of 2 / 1 / 4 all surface as
the same `s0/s1/s2/arr` quartet to scipy. Quantitative dump in
`artifacts/karr_a4_comparison.json`.

`CellStateFixture.m` lines 24-27 show the save+header-rewrite sequence
that explains why scipy sees the top-level key as the empty string.

`scripts/_find_karr_params.py` enumerated `data/`:

| File | Size | Role |
|---|---|---|
| `data/parameters.json` | **5.2 KB** | **the manifest, JSON, trivially parseable** |
| `data/knowledgeBase.mat` | 3.95 MB | the deep KB (likely also opaque MATLAB object dump; deferred) |
| `data/runSingleGeneDeletionSimulations.xml` | 245 KB | XML config (KO experiments) |
| `data/singleGeneDeletions.xls` | xlsx | KO experimental data (validation oracle) |

`src/+kb/Parameter.m` defines the schema MATLAB-side: each parameter
has `wid, wholeCellModelID, name, index, defaultValue, units,
experimentallyConstrained, comments, crossReferences, process, state,
reactions, proteinMonomers, proteinComplexs`. Our A3 store schema is a
near-superset (we add transformation lineage and content-addressed
event ids).

## Demonstrated ingestion (18 events into A3)

- **`scripts/karr_a4f_ingest.py`** — reads `parameters.json`, walks
  `data/karr_fixtures/karr_parameters_unit_map.yaml` (the unit map
  recovered from `.m` source), records each parameter via
  `ProvenanceStore.record_measured` with full lineage and the SHA-256
  of the parameters.json blob.
- **Output:** `artifacts/karr_a4f_provenance.jsonl` — 18 immutable
  events. First event id `29450d4986b57917`.

Confidence buckets:

| Bucket | Count | Meaning |
|---|---|---|
| **verified** | 4 | unit comment in `.m` source (all four `Time.*` fields say `(s)`) |
| **inferred** | 1 | universal convention + cross-check passes |
| **UNVERIFIED** | 13 | unit guessed by name; must be reviewed before any kinetic use |

**Mutual-consistency cross-check** (mechanically verified at ingest):
`ln(2) / MetabolicReaction.meanInitialGrowthRate = 32 400.7 s` versus
`Time.cellCycleLength = 32 400.0 s` — agreement 0.00%. Two independent
parameters in two different sections of `parameters.json` agree to four
significant figures. Strong evidence the JSON manifest is internally
consistent and that our unit recovery for these two fields is correct.

## What we explicitly did not solve

- **`knowledgeBase.mat`** — not opened. Likely also a MATLAB object
  dump. Deferred until M1+ hits a kinetic constant (e.g., enzyme
  `Vmax`, `Km`) that is not in `parameters.json`. At that point options
  are: (a) Octave + a `.m` extraction script, (b) targeted re-derivation
  from the cited primary literature in the unit map.
- **Karr "dark matter" weights** — the fudge factors warned about in
  external critique are likely in either `knowledgeBase.mat` or
  hardcoded inside `+process/*.m` step methods. We will discover them
  as failed phenotype matches in M2-M4, by design (the A5 multi-level
  diff is the detector).

## Implications for Phase 5

- **M-phase ingestion is no longer a research question.** The path is
  `parameters.json` → unit map → `ProvenanceStore.record_measured`.
- **Expand `karr_parameters_unit_map.yaml`** subsystem-by-subsystem as
  M1..M7 land. Every value upgraded from UNVERIFIED to verified must
  cite either an `.m`-source comment or a primary literature DOI.
- **The unit map IS our source-of-truth contract** with Karr's manifest;
  it is git-tracked and human-reviewable.
- **`knowledgeBase.mat` is a `bug` only when we hit it.** Don't pre-spend
  effort on Octave parsing.
- **Bounded-tuning policy unaffected.** A4F surfaces parameters into the
  store; tuning still requires biological-range citations recorded
  *before* the tuning step.

## Files

| Path | Purpose |
|---|---|
| `data/karr_fixtures/parameters.json` | Karr's manifest, sha256-tracked |
| `data/karr_fixtures/karr_parameters_unit_map.yaml` | unit recovery, source-cited |
| `data/karr_fixtures/m_source/{Time,MetabolicReaction,Host,Parameter,CellStateFixture,CircularSparseMat}.m` | source evidence |
| `scripts/karr_a4f_compare.py` | proves `.mat` opacity is structural |
| `scripts/karr_a4f_ingest.py` | the ingestion driver |
| `artifacts/karr_a4f_comparison.json` | quantitative `.mat` evidence |
| `artifacts/karr_a4f_provenance.jsonl` | 18 ingested A3 events |
