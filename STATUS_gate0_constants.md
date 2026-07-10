# STATUS — Gate 0 constants

## Scope
- Additive only: create `scripts/matlab/gate0_dump_process_constants.m`
- Additive only: create `scripts/gate0_verify_constants.py`
- Additive only: generate `data/karr_input_spec/_gate0_source_constants.json`

## Files created
- `scripts/matlab/gate0_dump_process_constants.m`
- `scripts/gate0_verify_constants.py`
- `data/karr_input_spec/_gate0_source_constants.json`
- `STATUS_gate0_constants.md`

## Progress
- Read `SESSION_CONTEXT.md` and existing Gate 0 stoichiometry dumper/comparator patterns.
- Read `scripts/matlab/gate0_inventory_constants.m` and fixture extraction references for constant name handling.
- Worktree note: repo is on `main` with unrelated pre-existing dirty/untracked files; left untouched.
- Implemented the MATLAB dumper using live getter-resolved `fixedConstantNames` / `fittedConstantNames`, `local_leaf_name(class(p))` process keys, and exact numeric sparse nonzero encoding via `find(M)` / `M(idx)`.
- Sanity check on the generated JSON: `28` processes, `366` fixed names, `3` fitted names, `368` unique constants. The `369` raw-name total collapses to `368` unique constants because `Transcription.transcriptionUnitBindingProbabilities` appears in both fixed and fitted lists.
- Live-source variance from the prompt/inventory summary: three declared cell constants are not pure `cellstr` and were dumped as strict general cells (`DNADamage.reactionVulnerableMotifs`, `MacromolecularComplexation.complexNetworks`, `Replication.primaseBindingLocations`) to preserve source fidelity.

## MATLAB run
- Command:
  `& "E:\MATLAB\bin\matlab.exe" -batch "cd('E:\opencell'); addpath('E:\opencell\scripts\matlab'); gate0_dump_process_constants('data/karr_input_spec/_gate0_source_constants.json')"`
- Result: exit `0`.
- Output summary: dumped all `28` processes and wrote `data/karr_input_spec/_gate0_source_constants.json` with `368` unique constants.

## Comparator verdict
- Command:
  `bin\oc-py.cmd scripts/gate0_verify_constants.py`
- Ruff:
  `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && ruff check scripts/gate0_verify_constants.py"` -> clean
- Result: `FAIL — 122 finding(s)`
- Notes:
  - The comparator is implemented as an exit-coded gate (`main() -> int`, `raise SystemExit(main())`).
  - In this shell harness, the Windows/WSL wrapper did not propagate a nonzero process code back to the orchestration tool, but the script printed the expected fail verdict and findings list.
- Findings verbatim:

```text
GATE 0 (constants): FAIL — 122 finding(s):
  - ChromosomeCondensation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ChromosomeCondensation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ChromosomeCondensation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ChromosomeCondensation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ChromosomeSegregation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ChromosomeSegregation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ChromosomeSegregation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ChromosomeSegregation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - Cytokinesis.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - Cytokinesis.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - Cytokinesis.substrateCompartments: present in SOURCE, ABSENT in fixture
  - Cytokinesis.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - DNADamage.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeBounds', 'enzymeCompartments', 'enzymeMolecularWeights', 'reactionBounds', 'reactionCatalysisMatrix', 'reactionCoenzymeMatrix', 'reactionModificationMatrix', 'reactionNames', 'reactionStoichiometryMatrix', 'reactionTypes', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - DNADamage.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - DNADamage.substrateCompartments: present in SOURCE, ABSENT in fixture
  - DNADamage.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - DNADamage.enzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - DNARepair.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeBounds', 'enzymeCompartments', 'enzymeMolecularWeights', 'reactionBounds', 'reactionCatalysisMatrix', 'reactionCoenzymeMatrix', 'reactionModificationMatrix', 'reactionNames', 'reactionStoichiometryMatrix', 'reactionTypes', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - DNARepair.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - DNARepair.substrateCompartments: present in SOURCE, ABSENT in fixture
  - DNARepair.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - DNARepair.enzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - DNASupercoiling.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - DNASupercoiling.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - DNASupercoiling.substrateCompartments: present in SOURCE, ABSENT in fixture
  - DNASupercoiling.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - FtsZPolymerization.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - FtsZPolymerization.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - FtsZPolymerization.substrateCompartments: present in SOURCE, ABSENT in fixture
  - FtsZPolymerization.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - HostInteraction.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - HostInteraction.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - HostInteraction.substrateCompartments: present in SOURCE, ABSENT in fixture
  - HostInteraction.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - MacromolecularComplexation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - MacromolecularComplexation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - MacromolecularComplexation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - MacromolecularComplexation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - Metabolism.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeBounds', 'enzymeCompartments', 'enzymeMolecularWeights', 'reactionBounds', 'reactionCatalysisMatrix', 'reactionCoenzymeMatrix', 'reactionModificationMatrix', 'reactionNames', 'reactionStoichiometryMatrix', 'reactionTypes', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - Metabolism.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - Metabolism.substrateCompartments: present in SOURCE, ABSENT in fixture
  - Metabolism.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - Metabolism.fbaReactionBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - Metabolism.fbaEnzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - Metabolism.enzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - Metabolism.reactionBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - ProteinActivation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ProteinActivation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ProteinActivation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ProteinActivation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ProteinDecay.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ProteinDecay.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ProteinDecay.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ProteinDecay.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ProteinFolding.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ProteinFolding.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ProteinFolding.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ProteinFolding.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ProteinModification.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeBounds', 'enzymeCompartments', 'enzymeMolecularWeights', 'reactionBounds', 'reactionCatalysisMatrix', 'reactionCoenzymeMatrix', 'reactionModificationMatrix', 'reactionNames', 'reactionStoichiometryMatrix', 'reactionTypes', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ProteinModification.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ProteinModification.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ProteinModification.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ProteinModification.enzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - ProteinProcessingI.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ProteinProcessingI.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ProteinProcessingI.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ProteinProcessingI.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ProteinProcessingII.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ProteinProcessingII.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ProteinProcessingII.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ProteinProcessingII.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ProteinTranslocation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ProteinTranslocation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ProteinTranslocation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ProteinTranslocation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - Replication.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - Replication.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - Replication.substrateCompartments: present in SOURCE, ABSENT in fixture
  - Replication.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - ReplicationInitiation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - ReplicationInitiation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - ReplicationInitiation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - ReplicationInitiation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - RibosomeAssembly.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - RibosomeAssembly.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - RibosomeAssembly.substrateCompartments: present in SOURCE, ABSENT in fixture
  - RibosomeAssembly.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - RNADecay.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - RNADecay.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - RNADecay.substrateCompartments: present in SOURCE, ABSENT in fixture
  - RNADecay.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - RNAModification.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeBounds', 'enzymeCompartments', 'enzymeMolecularWeights', 'reactionBounds', 'reactionCatalysisMatrix', 'reactionCoenzymeMatrix', 'reactionModificationMatrix', 'reactionNames', 'reactionStoichiometryMatrix', 'reactionTypes', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - RNAModification.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - RNAModification.substrateCompartments: present in SOURCE, ABSENT in fixture
  - RNAModification.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - RNAModification.enzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - RNAProcessing.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - RNAProcessing.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - RNAProcessing.substrateCompartments: present in SOURCE, ABSENT in fixture
  - RNAProcessing.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - TerminalOrganelleAssembly.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeBounds', 'enzymeCompartments', 'enzymeMolecularWeights', 'reactionBounds', 'reactionCatalysisMatrix', 'reactionCoenzymeMatrix', 'reactionModificationMatrix', 'reactionNames', 'reactionStoichiometryMatrix', 'reactionTypes', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - TerminalOrganelleAssembly.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - TerminalOrganelleAssembly.substrateCompartments: present in SOURCE, ABSENT in fixture
  - TerminalOrganelleAssembly.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - TerminalOrganelleAssembly.enzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
  - Transcription.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - Transcription.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - Transcription.substrateCompartments: present in SOURCE, ABSENT in fixture
  - Transcription.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - TranscriptionalRegulation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - TranscriptionalRegulation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - TranscriptionalRegulation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - TranscriptionalRegulation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - Translation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeCompartments', 'enzymeMolecularWeights', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - Translation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - Translation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - Translation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - tRNAAminoacylation.fixedConstantNames__: FIXED NAME-SET mismatch (only_in_source=['enzymeBounds', 'enzymeCompartments', 'enzymeMolecularWeights', 'reactionBounds', 'reactionCatalysisMatrix', 'reactionCoenzymeMatrix', 'reactionModificationMatrix', 'reactionNames', 'reactionStoichiometryMatrix', 'reactionTypes', 'stimuliCompartments', 'substrateCompartments', 'substrateMolecularWeights'] only_in_fixture=[])
  - tRNAAminoacylation.stimuliCompartments: present in SOURCE, ABSENT in fixture
  - tRNAAminoacylation.substrateCompartments: present in SOURCE, ABSENT in fixture
  - tRNAAminoacylation.enzymeCompartments: present in SOURCE, ABSENT in fixture
  - tRNAAminoacylation.enzymeBounds: VALUE mismatch at nz#0 (src=nan fixture=-inf)
```

## Commits
- Checkpoint 1: `3b44888` (`Add Gate 0 constants source dump`)
- Checkpoint 2: pending
