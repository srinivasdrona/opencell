# Gate 0 constants corrective pass

Started: 2026-07-10

Scope:
- Edit `scripts/matlab/gate0_dump_process_constants.m`
- Edit `scripts/gate0_verify_constants.py`
- Regenerate `data/karr_input_spec/_gate0_source_constants.json`

Progress:
- Read `SESSION_CONTEXT.md` and confirmed interpreter, commit cadence, and scope rules.
- Reset this status file at start for a fresh run.
- Inspected dumper/comparator and confirmed the three diagnosed artifact sites.
- Edited dumper to encode non-finite numeric `nz_val` entries as JSON string sentinels (`NaN`, `Inf`, `-Inf`).
- Re-ran MATLAB dump regeneration with exit 0:
  `& "E:\MATLAB\bin\matlab.exe" -batch "cd('E:\opencell'); addpath('E:\opencell\scripts\matlab'); gate0_dump_process_constants('data/karr_input_spec/_gate0_source_constants.json')"`
- Spot-checked regenerated JSON: `DNARepair.enzymeBounds.nz_val` now starts with `-Inf` tokens instead of `null`.
- Committed dumper + regenerated JSON chunk: `d6b0571` (`Preserve non-finite gate0 constant dumps`).
- Edited comparator to:
  - decode `NaN` / `Inf` / `-Inf` sentinels back to float64,
  - compare source vs fixture `nz_val` with `np.array_equal(..., equal_nan=True)`,
  - remove the resolved-vs-raw `fixedConstantNames__` / `fittedConstantNames__` set checks,
  - classify source-declared but fixture-unpersisted constants as INFO coverage gaps.
- Committed comparator + verification chunk: `5908beb` (`Correct gate0 constants comparison semantics`).
- Ruff clean:
  `bin\oc-py -m ruff check scripts/gate0_verify_constants.py`
- Gate verification pass:
  `bin\oc-py scripts/gate0_verify_constants.py`
- Final gate output:
  `GATE 0 (constants): PASS — 28 processes, 284 constants matched; 84 source constants not fixture-persisted (INFO).`
- INFO coverage note count = 84, matching the persisted-boundary pattern `28 processes × 3 compartment constants`.

Coverage boundary list:
- `ChromosomeCondensation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ChromosomeSegregation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `Cytokinesis.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `DNADamage.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `DNARepair.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `DNASupercoiling.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `FtsZPolymerization.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `HostInteraction.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `MacromolecularComplexation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `Metabolism.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ProteinActivation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ProteinDecay.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ProteinFolding.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ProteinModification.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ProteinProcessingI.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ProteinProcessingII.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ProteinTranslocation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `Replication.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `ReplicationInitiation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `RibosomeAssembly.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `RNADecay.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `RNAModification.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `RNAProcessing.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `TerminalOrganelleAssembly.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `Transcription.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `TranscriptionalRegulation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `Translation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`
- `tRNAAminoacylation.{stimuliCompartments, substrateCompartments, enzymeCompartments}`

Notes:
- Unrelated workspace changes are present; leaving them untouched.
