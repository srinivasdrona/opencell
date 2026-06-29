# ProteinActivation Wiring Row Status

Authored `data/schemas/per_process_wiring/ProteinActivation.yaml`.

What is covered:
- Process identity and canonical source/port paths.
- Method correspondence for `calcResourceRequirements_Current`, `evolveState`, and `calcFluxBounds`.
- Allocator mode, request formula, and direct-touch exemplars.
- Canonical consume/produce state-flip entries for the regulated proteins.
- Compartment routing, unit-conversion summary, dependencies, ordering constraints, source anchors, provenance, and deviations.

Notes and uncertainties:
- The raw MATLAB `.m` file was not present in this checkout, so the row is anchored to the verified verbatim extract at `docs/karr_extracts/process/20_ProteinActivation.md`.
- I treated `ProteinActivation` as allocator-free and rule-only because the extract and OC shim both describe boolean activation/deactivation with direct state flips.
- The provenance block records the required audit metadata in `notes` because the current schema only has `fixture_files`, `kb_version`, `extraction_date_utc`, and `notes`.
- `oc_commit_sha` has been filled with `61a5a06e8031af3159dffa436655ade330be1fd9`.

Observed divergences:
- No known MATLAB↔OC behavioral divergence was identified from the available source extract and current OC port.
- `deviations.lp_bounds_source` was left `unknown` because this process does not have a meaningful LP surface.
