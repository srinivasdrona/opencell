# DNASupercoiling Wiring Row Status

Authored `data/schemas/per_process_wiring/DNASupercoiling.yaml` for `Process_DNASupercoiling` / `KarrDNASupercoilingProcess`.

What is in the row:
- Process identity and source anchors for the MATLAB class and the OC port.
- Method correspondence for the allocator request, per-tick evolution, lifecycle allocator helper, initialization hook, transcription-coupling helper, and enzyme-property builder.
- Allocator mode set to `allocation`, with ATP/H2O as the requested vector and ADP/PI/H as direct downstream hydrolysis products.
- Compartment routing, unit-conversion chain, dependencies, ordering constraints, provenance, and known deviations.

What I verified:
- The MATLAB source in `E:/opencell-mirrors/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNASupercoiling.m` contains `calcResourceRequirements_Current`, `evolveState`, `calcRNAPolymeraseBindingProbFoldChange`, and `buildEnzymeProperties` with the expected ATP/H2O and LK/sigma logic.
- The OC port in `opencell/vivarium/karr_dna_supercoiling.py` reads allocated ATP/H2O from `substrates_allocated[self.name]`, emits the request vector in `next_update`, and writes ATP/H2O consumption plus ADP/PI/H production directly.
- The allocator wiring is backed by `opencell/vivarium/karr_allocation_step.py` and the composite enrollment in `opencell/vivarium/karr_composite.py`.

Uncertainties and limitations:
- `calcFluxBounds` is a schema-required placeholder for this row; the DNASupercoiling MATLAB class does not define an LP-style flux-bounds method.
- The OC port does not mirror the MATLAB `calcRNAPolymeraseBindingProbFoldChange` helper as a separate output surface.
- The MATLAB and OC request/update control flow are not a literal 1:1 clone: OC combines the request and update halves into one `next_update` controller.

Observed deviations:
- OC uses a sparse chromosome-store representation and replay hints instead of the MATLAB `doubleStrandedRegions` / `monomerBoundSites` / `complexBoundSites` surface.
- OC makes the timestep explicit in the request/update controller, while the MATLAB current-request helper is effectively tied to the simulation tick and fixture step size.
- OC folds the broader request controller into `next_update`, so its request formula is a superset of the MATLAB `calcResourceRequirements_Current` helper.

Commit metadata:
- `oc_commit_sha`: `61a5a06e8031af3159dffa436655ade330be1fd9`
- `last_audited`: `2026-06-29`
- `audited_by`: `gpt-5.4-mini (codex; row authored Day-43 EOD)`
