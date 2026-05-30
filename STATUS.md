# Phase F schema-extract status

## Round-trip validator result
- Run command: `/mnt/e/opencell/.venv-wsl/bin/python scripts/validate_per_process_schema.py`
- Output: `28/28 round-trip pass`
- Failing processes: none

## Probe cross-check
- bound_mutated_ticks per process matches PROBE_BOUND_MUTATIONS.json: probe file not found (`C:/Users/sdrona/.copilot/session-state/5c51d44b-5a9f-4b23-85ff-0fddaadf2212/files/PROBE_BOUND_MUTATIONS.json`)

## TOA hand-audit (Rule C)
- substrates.count: `8` (from MATLAB `TerminalOrganelleAssembly.m` line `127`, `substrateWholeCellModelIDs__`)
- substrates.shape: `[2, 8]` (from trace HDF5 observable `states_after/substrates`, first tick cell matrix shape)
- compartment_wids: `["incorporated", "unincorporated"]` (extraction method: trace axis inference + process-local `compartmentIndexs_*` constants)
- Match expected (2,8): yes (shape matches `(2, 8)` exactly)

## Hard-rule compliance
- extractor source contains "opencell/vivarium/karr_": `0` matches (`rg -n "opencell/vivarium/karr_|karr_translation" scripts/extract_per_process_schema.py`)
- karr_*.py modified: `0` (must be 0)
- tests/ modified: `0`
- hand-edited TOMLs: `0` (all 28 TOMLs start with autogen header)
- TOMLs with EXTRACTOR_FAILED markers:
  - `DNADamage`: `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `DNARepair`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `HostInteraction`: `substrates.wids`, `substrates.count`, `substrates.compartments`, `substrates.compartment_wids`
  - `MacromolecularComplexation`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `Metabolism`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `ProteinActivation`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `ProteinDecay`: `substrates.compartment_wids`
  - `ProteinFolding`: `substrates.compartment_wids`
  - `ProteinModification`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `RNADecay`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`
  - `RNAModification`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `TerminalOrganelleAssembly`: `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `TranscriptionalRegulation`: `substrates.wids`, `substrates.count`, `substrates.compartments`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - `tRNAAminoacylation`: `substrates.wids`, `substrates.count`, `substrates.compartment_wids`, `enzymes.free.wids`, `enzymes.free.count`, `enzymes.bound.wids`
  - Note: `extractor_diagnostics.axis_inference.local_compartment_indexs` is diagnostic-only and frequently reports `EXTRACTOR_FAILED` when no `compartmentIndexs_*` constants exist in MATLAB source.

## Python-drift report summary (informational)
- Total processes audited: `28`
- Total drifts found: `224`
- Top 5 drifts by severity:
  - `ChromosomeCondensation` `process.class`: schema=`ChromosomeCondensation`, python=`KarrChromosomeCondensationProcess` (`value_mismatch`)
  - `ChromosomeSegregation` `process.class`: schema=`ChromosomeSegregation`, python=`KarrChromosomeSegregationProcess` (`value_mismatch`)
  - `Cytokinesis` `process.class`: schema=`Cytokinesis`, python=`KarrCytokinesisProcess` (`value_mismatch`)
  - `DNADamage` `enzymes.free.count`: schema=`{EXTRACTOR_FAILED: enzymeWholeCellModelIDs assignment not found}`, python=`0` (`value_mismatch`)
  - `DNADamage` `enzymes.free.wids`: schema=`{EXTRACTOR_FAILED: enzymeWholeCellModelIDs assignment not found}`, python=`[]` (`value_mismatch`)
