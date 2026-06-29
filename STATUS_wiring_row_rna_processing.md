# RNAProcessing wiring row status

Authored `data/schemas/per_process_wiring/RNAProcessing.yaml` for the Karr `RNAProcessing` process.

What I captured:
- Class identity and file mapping for MATLAB `RNAProcessing` and OC `KarrRNAProcessingProcess`.
- The major MATLAB methods `calcResourceRequirements_LifeCycle`, `calcResourceRequirements_Current`, `evolveState`, and the dependent getter `getDryWeight`.
- The current OC request path through `RequestCalculatorRNAPathway.next_update` and the replay process update path through `KarrRNAProcessingProcess.next_update`.
- The 7-substrate stoichiometry surface (`ATP`, `GTP`, `ADP`, `GDP`, `PI`, `H2O`, `H`) and the matching compartment routing.
- The allocator-backed mode, with `substrates_allocated[self.name]` on the OC side.
- Provenance for the OC fixture files and the current commit SHA.

Uncertainties and judgments:
- `calcFluxBounds` is not present in `RNAProcessing.m`, so I marked that schema slot `not_implemented` rather than inventing a flux-bound helper.
- The row schema does not allow extra provenance keys, so I encoded the requested audit metadata in `provenance.notes` instead of adding new top-level provenance fields.
- I used `karr_native_m1__v2` as the KB version label because this process belongs to the M1 fixture family, but the RNAProcessing fixture itself does not publish a separate version string.

Observed divergences:
- OC request handling is shared with RNAModification and is availability-based rather than a literal clone of the MATLAB resource-cap formula.
- OC reads from `substrates_allocated` rather than the local `substrates` store.
- OC omits MATLAB's `intergenicRNAs` state and uses `processed::` prefixes to avoid ID collisions in `rna.counts`.
- OC can fall back to `protein`/`complex` stores for enzyme counts when a dedicated `enzymes` store is absent.

Validation:
- I have not yet run the final YAML load check or commit.

