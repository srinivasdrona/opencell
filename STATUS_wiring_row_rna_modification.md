RNAModification wiring row authored in `data/schemas/per_process_wiring/RNAModification.yaml`.

What was captured:
- Process identity for `RNAModification` and the OC port `KarrRNAModificationProcess`.
- Method correspondence for `calcResourceRequirements_Current`, `evolveState`, and the schema-required `calcFluxBounds` slot.
- Allocator mode, request formula, representative allocator requests, direct enzyme bypasses, consume/produce stoichiometry, compartment routing, unit conversion, dependencies, ordering, source anchors, provenance, and deviations.
- OC wiring notes for the current `RequestCalculatorRNAPathway` and the split protein/complex enzyme inputs.

What I verified from source:
- MATLAB `RNAModification.m` in the WholeCell mirror has the relevant blocks at lines 81-362, including `calcResourceRequirements_Current` at 289-294 and `evolveState` at 297-362.
- OC `karr_rna_modification.py` reads `substrates_allocated[self.name]` and splits enzyme reads across `protein.counts` and `complex.counts`.
- The shared RNA-pathway request calculator is in `opencell/vivarium/karr_request_calculators.py:286-359`.
- The canonical hard ordering note I used is documented in `docs/phase_f/L2_5_HARNESS_DESIGN.md:83-89` as `tRNAAminoacylation < Translation`.

Uncertainties:
- `kb_version` is still inferred as `karr_native_m1__v2` from the shared M1 lineage; I did not find a process-specific version string in the local metadata.
- `calcFluxBounds` is not defined as a RNAModification-local routine in either MATLAB or OC, so that slot is recorded as `not_implemented`.
- The consume/produce stoichiometry entries are canonical exemplars, not an exhaustive enumeration of all 91 reactions.

Observed divergences:
- OC uses `substrates_allocated[self.name]` as the allocator-fed input surface, while MATLAB receives allocated substrate counts through its copy-from-state path.
- OC routes requests through `RequestCalculatorRNAPathway`, shared with RNAProcessing, rather than a RNAModification-local request method.
- OC adds explicit zero-fallback guards and a finite stochastic-iteration cap in the residual sampler.
- The provenance block is schema-compatible; the extra audit metadata requested by the task is encoded in `provenance.notes` because the row schema does not permit arbitrary additional provenance keys.
