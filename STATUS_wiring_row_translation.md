# STATUS: Translation wiring row

Authored `data/schemas/per_process_wiring/Translation.yaml` for the Karr `Translation` process.

What I captured:
- MATLAB class identity, major initialization/state-copy blocks, `calcResourceRequirements_Current`, and `evolveState`.
- The current OC wiring split across `KarrTranslationV3Process`, `RequestCalculatorTranslation`, and the v6 chassis wiring that instantiates the translation process with `use_allocator_budget=True`.
- Mixed allocator behavior: AA demand is allocator-mediated in OC, while GTP/H2O remain direct substrate reads.
- Direct source anchors for the MATLAB process, the MATLAB ordering exception in `Simulation.evolveState`, the OC translation wrapper, the request calculator, and the fixture loaders.
- Provenance for the committed translation model, AA vocab sidecar, v2 mechanism inputs, and the optional replay archive seed.

Uncertainties / approximations:
- `calcFluxBounds` is absent as a standalone Translation method, so it is marked `not_implemented`.
- The MATLAB `calcResourceRequirements_Current` water line is overwritten multiple times; the row records the final written expression.
- The current OC runtime is not a line-for-line MATLAB port. It uses an AA allocator surrogate plus direct GTP/H2O gating, and it emits `protein.unprocessed_counts` rather than the MATLAB mature-monomer writeback shape.

Observed divergences:
- MATLAB requests GTP/H2O; current OC requests the 20 amino acids.
- MATLAB includes `FMET`; current OC does not expose a separate FMET pool and uses MET as the initiator-residue surrogate.
- MATLAB substrate byproducts GDP/PI/H are not emitted by the current OC wrapper.

