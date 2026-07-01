# Wiring DB L1b First-Run Verdict

Run date: 2026-07-01  
Command: `bin\oc-py scripts/l1b_verify_wiring.py --out tmp/l1b_first_run.txt --format md`

## Overall Verdict
- **FAIL**
- **1/28 rows PASS**
- **27/28 rows FAIL**
- Sole PASS row: `Metabolism`

## Per-Check Aggregate
- **Check 1 `check_matlab_anchors_resolve` failed on 27 rows**: `ChromosomeCondensation`, `ChromosomeSegregation`, `Cytokinesis`, `DNADamage`, `DNARepair`, `DNASupercoiling`, `FtsZPolymerization`, `HostInteraction`, `MacromolecularComplexation`, `ProteinActivation`, `ProteinDecay`, `ProteinFolding`, `ProteinModification`, `ProteinProcessingI`, `ProteinProcessingII`, `ProteinTranslocation`, `RNADecay`, `RNAModification`, `RNAProcessing`, `Replication`, `ReplicationInitiation`, `RibosomeAssembly`, `TerminalOrganelleAssembly`, `Transcription`, `TranscriptionalRegulation`, `Translation`, `tRNAAminoacylation`.
- **Check 2 `check_oc_anchors_resolve` failed on 26 rows**: `ChromosomeCondensation`, `ChromosomeSegregation`, `Cytokinesis`, `DNADamage`, `DNARepair`, `DNASupercoiling`, `FtsZPolymerization`, `HostInteraction`, `MacromolecularComplexation`, `ProteinActivation`, `ProteinDecay`, `ProteinFolding`, `ProteinModification`, `ProteinProcessingII`, `ProteinTranslocation`, `RNADecay`, `RNAModification`, `RNAProcessing`, `Replication`, `ReplicationInitiation`, `RibosomeAssembly`, `TerminalOrganelleAssembly`, `Transcription`, `TranscriptionalRegulation`, `Translation`, `tRNAAminoacylation`.
- **Check 3 `check_consume_produce_wids_in_schema_toml` failed on 0 rows** (warnings on 2 rows).
- **Check 4 `check_allocator_requests_wids_in_schema_toml` failed on 0 rows** (warnings on 6 rows).
- **Check 5 `check_unit_conversion_chain_coherent` failed on 20 rows**: `ChromosomeCondensation`, `DNARepair`, `DNASupercoiling`, `FtsZPolymerization`, `HostInteraction`, `MacromolecularComplexation`, `ProteinDecay`, `ProteinFolding`, `ProteinProcessingI`, `ProteinProcessingII`, `ProteinTranslocation`, `RNADecay`, `RNAModification`, `Replication`, `ReplicationInitiation`, `RibosomeAssembly`, `Transcription`, `TranscriptionalRegulation`, `Translation`, `tRNAAminoacylation`.
- **Check 6 `check_ordering_constraints_reference_valid_processes` failed on 0 rows**.
- **Check 7 `check_deviations_reference_valid_anchors` failed on 0 rows** (warnings on 5 rows: `Cytokinesis`, `Metabolism`, `ProteinFolding`, `ProteinProcessingI`, `Replication`).

## Recommended Remediation Priorities
- **P0: Anchor rot / placeholder anchor claims (Checks 1 and 2).**
  - Focus first on missing-file anchors, placeholder symbols (`NOT_IMPLEMENTED`, `n/a`), and non-UTF8 source file handling decisions for MATLAB anchors.
- **P1: WID drift and TOML alignment (Checks 3 and 4).**
  - No hard failures on first run, but non-substrate placement warnings should be triaged to confirm intentional grouping vs stale row assumptions.
- **P2: Warning hygiene and unit-chain cleanup (Check 5 + warning-only checks).**
  - Fix malformed/empty conversion chains and clear warning-only path references in `known_deviations` for higher signal-to-noise in future runs.
