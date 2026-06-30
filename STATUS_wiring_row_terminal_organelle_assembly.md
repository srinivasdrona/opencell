# STATUS: wiring row for `TerminalOrganelleAssembly`

- Last audited: `2026-06-29`
- Audited by: `gpt-5.4-mini (codex; row authored Day-43 EOD)`
- OC commit SHA: `61a5a06e8031af3159dffa436655ade330be1fd9`

## Authored

- Added `data/schemas/per_process_wiring/TerminalOrganelleAssembly.yaml`.
- Mirrored the MATLAB `TerminalOrganelleAssembly` class against the OC `KarrTerminalOrganelleAssemblyProcess` port.
- Captured the allocator hook as a degenerate zero request, with the OC runtime marked as bypassing allocator mediation.
- Recorded representative consume/produce stoichiometry for membrane-localized and cytosol-localized terminal-organelle proteins.
- Added source anchors for class setup, localization rule construction, per-tick assembly, and the OC trace/fallback helpers.

## Uncertainties

- The compartment labels in the fixture are inferred from the MATLAB remapping logic plus the extracted compartment-index matrix, not from a separate human-readable fixture legend.
- `calcResourceRequirements_Current` exists in MATLAB but returns an all-zero matrix; the OC port has no dedicated request calculator.
- `calcFluxBounds` is absent in this class, so the row marks the bounds stage as not implemented.

## Observed Deviations

- The OC port is Karr-light: it tracks assembled counters in `cell.*` rather than the full MATLAB substrate-matrix loop.
- The OC port includes a trace-hint override and a compartment-transfer fallback for substrate deltas.
- The OC port bypasses allocator mediation entirely for this process.

