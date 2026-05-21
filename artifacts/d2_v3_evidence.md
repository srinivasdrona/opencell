# D.2 v3 Evidence Extraction

## Inputs
- `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`
- `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat`
- `data/karr_fixtures/per_process/ProteinComplex_flat.mat`
- `data/karr_fixtures/per_process/Metabolite_flat.mat`

## BLOCKER #1 (Ribosome costs)
- status: `extracted`
- substrates: `GTP, GDP, PI, H2O, H`
- 30S assembly GTPases: `MG_387_MONOMER, MG_143_MONOMER`
- 50S assembly GTPases: `MG_329_MONOMER, MG_335_MONOMER, MG_384_MONOMER, MG_442_MONOMER`
- rule: use per-step split (2 vs 4), not blanket 6x shortcut.

## BLOCKER #2 (Scope ownership)
- status: `extracted`
- formation process histogram (named):
  - `Process_MacromolecularComplexation`: 882
  - `Process_Metabolism`: 96
  - `Process_ReplicationInitiation`: 84
  - `Process_FtsZPolymerization`: 66
  - `Process_Replication`: 42
  - `Process_RibosomeAssembly`: 12
  - `Process_Translation`: 12
  - `Process_ChromosomeCondensation`: 6
  - `Process_Transcription`: 6
- D.2 whitelist: `Process_MacromolecularComplexation`, `Process_RibosomeAssembly`

## BLOCKER #3 (Emit conservation)
- status: `unknown`
- reason: Design-level check; emit schema must include +product and -consumed-subcomplex deltas.

## BLOCKER #4 (Oracle target)
- status: `extracted`
- mature-only mass target (g): `1.1549598107588903e-15`
- all-forms total mass (g): `1.5052832188811208e-15`
- rule: mature-to-mature for D.2; mature+bound for integration-stage checks.

## Output JSON
- `artifacts/d2_v3_evidence.json`
