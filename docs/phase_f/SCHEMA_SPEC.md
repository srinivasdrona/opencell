# Per-Process Schema Spec (Phase F)

## Canonical Inputs

The extractor is anchored to MATLAB artifacts only:

1. Process MATLAB source  
   `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/<Process>.m`
2. Compartment definitions (indirect wid resolution)  
   `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+constant/Compartment.m`  
   plus wid constants dereference from  
   `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+kb/KnowledgeBase.m` (constant `*CompartmentWholeCellModelIDs`)
3. Per-process trace file  
   `data/m1_sources/karr_native/per_process_traces_v2/<Process>_100ticks.mat`
4. Optional fixture file  
   `data/m1_sources/karr_native/per_process_fixtures_v2/<Process>_fixture.mat` (if absent, schema stores `"MISSING"`)

Python process source is not used for extraction.

## Failure Contract

If a field cannot be extracted without guessing, the field stores an inline failure marker:

```toml
field_name = { EXTRACTOR_FAILED = "<reason>" }
```

## Field Anchors

| Field | Source File | Source Pointer | Extraction Rule | Validation Rule |
|---|---|---|---|---|
| `process.name` | Process `.m` | MATLAB filename basename | basename of `<Process>.m` (no extension) | Re-extract and compare exact string |
| `process.class` | Process `.m` | `classdef` line (regex `classdef\s+(\w+)\s*<`) | parse class symbol before `<` | Re-extract and compare exact string |
| `process.matlab_source` | Process `.m` | canonical relative path | write canonical relative path (not host-absolute path) | Re-extract and compare exact string |
| `process.trace_file` | Trace `.mat` | canonical relative path | write canonical relative trace path | Re-extract and compare exact string |
| `process.fixture_file` | Fixture `.mat` | `<Process>_fixture.mat` existence check | if present write canonical relative path, else `"MISSING"` | Re-extract and compare exact string |
| `substrates.wids` | Process `.m` | assignments matching `substrateWholeCellModelIDs*` | parse MATLAB assignment blocks (`{...}`, `unique({...})`, or append blocks) preserving order; if runtime-dependent and incomplete -> `EXTRACTOR_FAILED` | Re-extract and compare full list / failure marker |
| `substrates.count` | Process `.m` + Trace `.mat` | `substrates.wids` and trace shape | `len(substrates.wids)` when available; if wids fail -> `EXTRACTOR_FAILED` | Re-extract and compare exact scalar / failure marker |
| `substrates.shape` | Trace `.mat` | HDF5 path `states_after/substrates` first tick cell content shape | read first matrix from object-ref cell and store shape list | Re-extract and compare exact list |
| `substrates.compartments` | Process `.m` or Trace `.mat` | `substrateCompartments` assignment if present; else `states_before/substrates` + `states_after/substrates` all ticks | primary: parse numeric `substrateCompartments`; fallback: infer compartment axis and nonzero-scan over 100 ticks (before/after union) | Re-extract and compare exact list / failure marker |
| `substrates.compartment_wids` | `Compartment.m` + `KnowledgeBase.m` + Process `.m` + Trace `.mat` | `Compartment.m` knowledge-base index use, KB constants `*CompartmentWholeCellModelIDs`, optional `compartmentIndexs_*` locals | map compartment indices to wid constants when index mapping is available; for process-local pseudo-compartments use `compartmentIndexs_*` labels; if no safe map -> `EXTRACTOR_FAILED` | Re-extract and compare exact list / failure marker |
| `enzymes.free.wids` | Process `.m` | assignments matching `enzymeWholeCellModelIDs*` | parse MATLAB assignment blocks preserving order; if unresolved runtime dependency -> `EXTRACTOR_FAILED` | Re-extract and compare exact list / failure marker |
| `enzymes.free.count` | Process `.m` + Trace `.mat` | `enzymes.free.wids` and `states_after/enzymes` shape | `len(enzymes.free.wids)` when available; else `EXTRACTOR_FAILED` | Re-extract and compare exact scalar / failure marker |
| `enzymes.free.shape` | Trace `.mat` | HDF5 path `states_after/enzymes` first tick cell content shape | read first matrix shape | Re-extract and compare exact list |
| `enzymes.bound.wids` | Process `.m` + Trace `.mat` | derived from `enzymes.free.wids` | copy `enzymes.free.wids` when available; else `EXTRACTOR_FAILED` | Re-extract and compare exact list / failure marker |
| `enzymes.bound.count` | Trace `.mat` and/or free wids | HDF5 path `states_after/boundEnzymes` shape | if free wids available: `len(free_wids)`; else infer item axis from bound shape | Re-extract and compare exact scalar |
| `enzymes.bound.shape` | Trace `.mat` | HDF5 path `states_after/boundEnzymes` first tick cell content shape | read first matrix shape | Re-extract and compare exact list |
| `mutation_profile.bound_mutated_ticks` | Trace `.mat` | `states_before/boundEnzymes` vs `states_after/boundEnzymes` (all ticks) | exact tickwise `np.array_equal` diff count | Re-extract and compare exact integer |
| `mutation_profile.enzymes_mutated_ticks` | Trace `.mat` | `states_before/enzymes` vs `states_after/enzymes` | exact tickwise diff count | Re-extract and compare exact integer |
| `mutation_profile.substrates_mutated_ticks` | Trace `.mat` | `states_before/substrates` vs `states_after/substrates` | exact tickwise diff count | Re-extract and compare exact integer |
| `mutation_profile.monomers_mutated_ticks` | Trace `.mat` | `states_before/monomers` vs `states_after/monomers` (if present) | exact tickwise diff count; absent -> `0` | Re-extract and compare exact integer |
| `mutation_profile.per_observable` | Trace `.mat` | all observables under `states_before/*` and `states_after/*` | build map `{observable_name: mutated_tick_count}` | Re-extract and compare exact map |
| `trace_hint_keys` | Derived from mutation profile | mutated observables map | include `<obs>_next` for sigma-gated channels with mutations (`boundEnzymes`, `enzymes`) | Re-extract and compare exact ordered list |
| `pass_through` | Derived from mutation profile | mutated observables map | observables with `0` mutated ticks across all 100 ticks | Re-extract and compare exact sorted list |

## Round-Trip Correctness Gate

`scripts/validate_per_process_schema.py` is the gate:

1. Load each TOML.
2. Re-run extractor for that process.
3. Re-render canonical TOML text.
4. Assert field-by-field equality and bytewise TOML equality.
5. Report failing field paths.

A schema is valid only if it can be regenerated exactly.
