# STATUS: Wiring Row - ChromosomeSegregation

## What I authored

- Created `data/schemas/per_process_wiring/ChromosomeSegregation.yaml`.
- Kept the row schema-shaped to `data/schemas/per_process_wiring/_schema.yaml` and mirrored the `Metabolism.yaml` nesting style.
- Captured the current OC port as an allocation-gated `KarrChromosomeSegregationProcess` with inlined request and update logic.
- Recorded the Karr gate, substrate use, compartment routing, dependencies, ordering note, source anchors, fixture provenance, and classified deviations.

## Important limitation

- The canonical MATLAB file `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeSegregation.m` was not physically present in this checkout.
- Because of that, the MATLAB anchors in the row are reconstructed from:
  - `docs/karr_extracts/process/08_ChromosomeSegregation.md`
  - `docs/karr_extracts/architecture/01_simulation_loop.md`
  - `opencell/validation/swarm/l5/karr_zero_grant_behavior.md`
  - `docs/design/pc-t5-segregation.md`
- I preserved the canonical MATLAB path in the row and documented the limitation in `provenance.notes`.

## Uncertainties

- I could not directly verify a literal MATLAB `calcResourceRequirements_Current` body from source in this checkout, so the request formula is a symbolic reconstruction from the documented gate and the zero-grant audit.
- I treated `Cytokinesis` and `Metabolism` as the clearest downstream dependency examples, but those are not exclusive substrate-only edges.

## Divergences observed

- OC is not a literal boolean-only mirror of the MATLAB description:
  - it projects segregation into continuous `segregation_progress` and pole-position outputs,
  - it adds an optional topoIV gate,
  - and it keeps request/update logic inline in `next_update()` rather than a separate request-calculator class.
- Allocator wiring itself matches the Karr contract: the OC process reads from `substrates_allocated[self.name]` and does not fall back to the global substrate store.

