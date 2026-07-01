# STATUS — L1b Remediation (2026-07-01)

## Verdict
- **PARTIAL**
- Target requested: `24-28/28` PASS
- Achieved: **12/28 PASS** (`+11` rows from baseline)

## Beat 1 — Contract
- Remediate three dominant row-vs-code patterns (P1/P2/P3) across per-process wiring rows.

## Beat 2 — Surface
- Added: `scripts/remediate_l1b_row_failures.py`
- Updated: 27 row YAML files under `data/schemas/per_process_wiring/`
- Regenerated: `data/schemas/per_process_wiring/_combined.yaml`
- Updated gate artifact: `tmp/l1b_after_remediation.txt`
- Added report: `docs/phase_f/L1B_REMEDIATION_2026-07-01.md`

## Beat 3 — Results
- `check_oc_anchors_resolve`: **26 failed rows -> 0**
- `check_unit_conversion_chain_coherent`: **20 failed rows -> 0**
- `check_matlab_anchors_resolve`: **27 failed rows -> 16**
- Overall: **1/28 -> 12/28 PASS**

## Beat 4 — Inversion
- Failure mode: unresolved MATLAB-anchor source quality (decode/missing-file/extract-symbol issues) could dominate after P1/P2/P3 fixes.
- Outcome: this mode materialized; all residual failures are in Check 1 only.

## Beat 5 — Verification
- `bin\oc-py scripts/build_wiring_db.py --validate-only` => PASS
- `bin\oc-py scripts/l1b_verify_wiring.py --out tmp/l1b_after_remediation.txt --format md` => FAIL (12/28 PASS)
- `bin\oc-pytest tests/integration/test_l1b_verify_wiring.py` => PASS (6 passed)

## Residual FAIL Rows (Check 1 only)
- DNADamage
- DNARepair
- DNASupercoiling
- FtsZPolymerization
- HostInteraction
- ProteinActivation
- ProteinFolding
- ProteinProcessingI
- ProteinProcessingII
- ProteinTranslocation
- RNADecay
- RNAProcessing
- Replication
- RibosomeAssembly
- TerminalOrganelleAssembly
- TranscriptionalRegulation

## Residual Cause Summary
- Non-UTF8 MATLAB file decode failures.
- Missing absolute mirror-source path (`E:/opencell-mirrors/...`).
- Extract-doc anchors lacking method symbol text.
