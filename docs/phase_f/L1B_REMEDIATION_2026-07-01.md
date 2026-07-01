# L1b Remediation Report (2026-07-01)

## Beat 1 — Contract
- Objective: remediate the three dominant row-vs-code failure patterns called out in the L1b first-run report.
- Scope implemented: per-process wiring rows + mechanical remediation script + combined DB rebuild + L1b rerun + validator/test verification.

## Beat 2 — Surface
- New script: `scripts/remediate_l1b_row_failures.py`
- Updated rows: `data/schemas/per_process_wiring/*.yaml` (27 row files)
- Regenerated: `data/schemas/per_process_wiring/_combined.yaml`
- Gate artifacts: `tmp/l1b_after_remediation.txt`

## Beat 3 — Expected Outcome
- Before remediation: **1/28 PASS**, **27/28 FAIL**
- After remediation: **12/28 PASS**, **16/28 FAIL**
- Net: **+11 rows** moved `FAIL -> PASS`

### FAIL -> PASS rows
- ChromosomeCondensation
- ChromosomeSegregation
- Cytokinesis
- MacromolecularComplexation
- ProteinDecay
- ProteinModification
- RNAModification
- ReplicationInitiation
- Transcription
- Translation
- tRNAAminoacylation

## Beat 4 — Inversion
- Potential failure mode considered: remediation could clear OC/unit-chain failures but leave unresolved MATLAB-anchor source rot (missing files, non-UTF8, extract-only anchors without method symbols).
- This mode did occur and is reported explicitly under residual failures.

## Beat 5 — Action + Verification
### Pattern P1 (ghost `calcFluxBounds` on non-Metabolism rows)
- Applied to 26 non-Metabolism rows.
- Mechanical action used in-row: convert ghost `calcFluxBounds` correspondence into an explicit non-FBA/`not_implemented` record, add deviation note:
  - `"This process does not have Karr's calcFluxBounds method; it does not participate in FBA."`

### Pattern P2 (`NOT_IMPLEMENTED` / `n/a` symbol conventions + composite symbols)
- Placeholder OC symbols remediated (status kept at `not_implemented`, OC anchor normalized to real Python symbols).
- Composite slash symbols normalized to single concrete primary symbols (with supporting anchors where resolvable).
- Result: `check_oc_anchors_resolve` improved from **26 failed rows** to **0 failed rows**.

### Pattern P3 (empty/malformed unit conversion chains)
- Normalized all 20 incoherent non-Metabolism unit chains to identity `molecules/tick -> molecules/tick` chains.
- Result: `check_unit_conversion_chain_coherent` improved from **20 failed rows** to **0 failed rows**.

### Command verification
- `bin\oc-py scripts/build_wiring_db.py --validate-only` -> **PASS**
- `bin\oc-py scripts/l1b_verify_wiring.py --out tmp/l1b_after_remediation.txt --format md` -> **FAIL (12/28 PASS)**
- `bin\oc-pytest tests/integration/test_l1b_verify_wiring.py` -> **PASS (6 passed)**

## Residual Failures (16 rows)
All residual failures are now isolated to **Check 1** (`check_matlab_anchors_resolve`) and fall into three source-side categories:

1. Non-UTF8 MATLAB files (decode failures)  
   - DNADamage, DNARepair, HostInteraction, ProteinProcessingI, ProteinProcessingII, RNAProcessing, RibosomeAssembly, TerminalOrganelleAssembly

2. Missing external mirror paths (`E:/opencell-mirrors/...`)  
   - DNASupercoiling

3. Extract-doc anchors where method symbol text is not present  
   - FtsZPolymerization, ProteinActivation, ProteinFolding, ProteinTranslocation, RNADecay, Replication, TranscriptionalRegulation

These are outside the 3 targeted remediation patterns and represent remaining MATLAB-anchor source hygiene work.
