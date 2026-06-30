# ReplicationInitiation Wiring Row Status

Authored `data/schemas/per_process_wiring/ReplicationInitiation.yaml` for `ReplicationInitiation`.

What I captured:

- Process identity and file mapping for the MATLAB `ReplicationInitiation` class and the OC `KarrReplicationInitiationProcess`.
- Allocator wiring:
  - Karr mode: `allocation`
  - OC current mode: `allocation`
  - Request tuples: `ATP`, `H2O`
  - Direct substrate bypasses: `ADP`, `PI`, `H`
- Per-tick stoichiometry for the shared substrate pool:
  - Consumes: `ATP`, `H2O`
  - Produces: `ADP`, `PI`, `H`
- Routing, dependencies, and the global ordering note from `Simulation.evolveState`.
- Source anchors for the MATLAB initialization, request, and evolve blocks plus the OC bootstrap, `next_update`, and helper blocks.

What is intentionally marked as incomplete:

- `calcFluxBounds` is marked `not_implemented` because this process file does not define a process-local flux-bound builder.
- `initializeStateBasedOnFinalConditions` and `initializeStateBasedOnTheory` are marked `not_implemented` on the OC side.
- `kb_version` is `unknown`; no explicit version string was obvious in the per-process fixture metadata.

Uncertainties and divergences:

- The OC port is request-driven inside `next_update` rather than through a separate request-calculator class.
- The OC bootstrap is fixture-backed and does not reproduce the MATLAB steady-state initialization solve.
- The current worktree did not contain the raw MATLAB tree at the expected path, so the MATLAB anchors were cross-checked against the full `E:\opencell` checkout.

Validation note:

- I have not yet run the requested WSL YAML-load command in this turn.
