# STATUS: tRNAAminoacylation wiring row

Authored `data/schemas/per_process_wiring/tRNAAminoacylation.yaml` with:

- process identity and file mapping
- method bindings for the main MATLAB and OC surfaces
- allocator mode and request formula
- canonical consume/produce stoichiometry exemplars
- cytosolic compartment routing
- a count-based unit-conversion chain
- dependency direction notes
- ordering constraint `tRNAAminoacylation` before `Translation`
- provenance for the fixture/load path
- known MATLAB-to-OC deviations

Uncertainties and notes:

- Raw `Simulation.m` was not present in this checkout, so I anchored the ordering rule to `docs/karr_extracts/architecture/01_simulation_loop.md`.
- `calcFluxBounds` is not implemented as a process-local method in either the MATLAB class or the OC port; I marked it `not_implemented`.
- `kb_version` is inferred as `karr_native_m1__v2` from the shared fixture lineage.
- I left `allocator.bypasses` empty because the current OC process update reads `substrates_allocated` only; there is no current direct-substrate bypass in the update path.

Observed divergences:

- The OC request calculator is an availability-based shim and does not reproduce the MATLAB request formula literally.
- The OC solver uses a max-iteration guard and `np.rint` post-processing.
- The OC port keeps legacy RNA-vector fallbacks for older snapshot shapes.
- MATLAB's `initializeState` split is not re-applied in the OC process file; initial state comes from fixture/chassis setup.
