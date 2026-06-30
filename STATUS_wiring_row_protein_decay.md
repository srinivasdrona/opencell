# STATUS: ProteinDecay wiring row

Authored `data/schemas/per_process_wiring/ProteinDecay.yaml` as the per-process wiring DB row for `Process_ProteinDecay`.

What I captured:
- MATLAB identity, method spans, and the full `ProteinDecay.m` helper chain.
- OC identity for `ProteinDecayLightProcess`, including fixture loading, current-tick request wiring, and the direct `substrates` writeback path.
- Allocator mode split: Karr uses allocation; current OC behavior is bypass because `next_update` reads `states["substrates"]` directly and never consumes `substrates_allocated`.
- Canonical stoichiometry exemplars for ATP/H2O/H consumption and ADP/PI/amino-acid production.
- The global ordering constraint from `Simulation.evolveState` that keeps `tRNAAminoacylation` before `Translation`.

Uncertainties / judgment calls:
- `kb_version` is set to `karr_native_m1__v2` as the shared M1 fixture-family version. I did not find a separate ProteinDecay-specific version stamp in the OC init code.
- `calcResourceRequirements_LifeCycle` and `calcFluxBounds` are marked `not_implemented` because the OC light port does not expose dedicated analogues for them.
- The OC port is intentionally light: it covers complex decay and a partial latent monomer replay helper, but not the full MATLAB misfold/refold, aborted-polypeptide decay, or complete monomer-decay behavior.

Observed divergences:
- OC uses `ProteinDecayLightProcess`, not a full parity port.
- OC request handling is split into a separate request calculator and the process itself emits direct substrate deltas.
- OC request keying follows `karr_protein_decay_light`, with allocator aliasing from `protein_decay_light`.
- OC flattens Karr's compartmented ProteinDecay surfaces into a per-WID projection.

Validation status:
- YAML authored and ready for schema validation.
- I have not yet run the final `yaml.safe_load` check or the commit step.
