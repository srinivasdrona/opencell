# STATUS: ProteinFolding wiring row

## What I authored
- Added [`data/schemas/per_process_wiring/ProteinFolding.yaml`](/E:/opencell-worktrees/protein_folding/data/schemas/per_process_wiring/ProteinFolding.yaml) as the per-process wiring DB row for `ProteinFolding`.
- Captured class identity, allocator mode, request surface, direct substrate consumption, routing, dependency direction, source anchors, provenance, and known OC divergences.

## Notes
- The raw MATLAB `ProteinFolding.m` file was not present in this checkout, so the MATLAB-side anchors came from `docs/karr_extracts/process/19_ProteinFolding.md`, `docs/design/pb_final_chassis_v4_integration.md`, and downstream audit notes.
- I treated `ProteinFolding` as allocator-mode on both sides because the OC port reads from `states["substrates_allocated"][self.name]`.
- I kept the current OC request slice explicit: ATP, FE2, MG, and ZN are emitted by `RequestCalculatorProteinPathway`, while K is recorded as a Karr-only prosthetic-ion exemplar.
- I left `unfoldedComplexs` / `foldedComplexs` as a known OC omission because the current runtime does not wire those fixture channels.

## Uncertainties
- The exact MATLAB method body anchors are reconstructed rather than read from the missing `.m` file.
- The dependency block is conservative: it names the direct upstream state readers I could verify from the OC port and chassis notes, rather than over-claiming a full upstream process graph.
