# STATUS wiring_row_protein_translocation

## What I authored

- Created [`data/schemas/per_process_wiring/ProteinTranslocation.yaml`](/E:/opencell-worktrees/protein_translocation/data/schemas/per_process_wiring/ProteinTranslocation.yaml) as a single per-process wiring row for `ProteinTranslocation`.
- Captured the process identity, the allocator-wired request path, the OC `next_update` path, stoichiometry, routing, dependencies, ordering constraints, source anchors, provenance, and the known Karr ↔ OC deviations.
- Used the checked-in Karr process extract and the parity-audit docs because this worktree does not contain a local raw `ProteinTranslocation.m` file.

## Uncertainties

- The exact raw MATLAB `calcResourceRequirements_Current` body was not available in this checkout, so the request formula is a carefully stated inference from the extract + fixture scalars + OC port.
- The exact raw MATLAB `evolveState` body was not available locally either, so the MATLAB source anchors point at the parity audit rather than a raw local `.m` file.
- I left the ordering constraints empty because the only explicit scheduler constraint I found is the global `tRNAAminoacylation < Translation` rule in `Simulation.evolveState`, not a ProteinTranslocation-specific exception.

## Deviations observed

- OC uses `substrates_allocated[self.name]` plus a current-pool floor in `RequestCalculatorPTransloc`, while Karr's request side is allocator-facing but not documented in the local extract as that floor behavior.
- OC batches per species and phase, while Karr's executable translocation loop is per-copy and mixed-randomized.
- OC tracks moved proteins with `protein.location` and `protein.unprocessed_counts` instead of the compartment-resolved monomer matrix used by Karr.
- OC drops two terminal-organelle monomers at fixture load time rather than remapping all non-cytosolic monomers through the process loop.

## Validation

- Validation command used: `wsl -e bash -lc 'cd /mnt/e/opencell-worktrees/protein_translocation && python3 - <<PY ... PY'`
- Actual result: `OK dict 13`
- The row now parses as expected; the remaining limitation is provenance depth, not YAML shape.
