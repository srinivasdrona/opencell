## RibosomeAssembly wiring row status

Authored and refreshed `data/schemas/per_process_wiring/RibosomeAssembly.yaml` for the Karr `RibosomeAssembly` process, grounded in the mirrored MATLAB source and the current OC port.

What is captured:
- Class identity and file mapping for `RibosomeAssembly` and `KarrRibosomeAssemblyProcess`.
- Method correspondences for `initializeConstants`, `initializeState`, `calcResourceRequirements_LifeCycle`, `calcResourceRequirements_Current`, `evolveState`, and the schema-required `calcFluxBounds` slot.
- Allocator mode as `allocation`, with `GTP` and `H2O` as the allocator-facing requests.
- Direct wiring examples for RNA, monomer, enzyme, and complex state touches.
- Consume/produce stoichiometry, compartment routing, unit conversion, dependencies, ordering constraint, source anchors, provenance, and known deviations.

Uncertainties / placeholders:
- `deviations.lp_bounds_source` is set to `unknown` on both sides because `RibosomeAssembly` does not define a process-local flux-bounds path in either MATLAB or OC.
- The stoichiometry and bypass exemplars are representative rather than exhaustive. They are enough to show the wiring shape, but the process touches many ribosomal protein monomers and the full set is larger.
- The MATLAB source was read from the mirrored WholeCell checkout at `E:\opencell-mirrors\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\RibosomeAssembly.m` and `E:\opencell-mirrors\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\@Simulation\evolveState.m`.

Observed divergences:
- OC splits request generation into `RequestCalculatorRibAsm` instead of keeping it on the process class.
- MATLAB hardcodes `getGtpPerComplex(2)` in `calcResourceRequirements_Current`, while OC uses the actual per-particle GTPase counts.
- OC folds `initializeState` into construction-time fixture loading.
- OC returns early when allocated `GTP` or `H2O` is non-positive; MATLAB only short-circuits on `GTP`.

Validation:
- YAML parse check passed with `OK dict 13` against the refreshed row file.
