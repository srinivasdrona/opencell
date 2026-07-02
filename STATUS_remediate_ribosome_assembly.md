# STATUS: RibosomeAssembly ROW_WRONG/MISSING Remediation

- Process: `RibosomeAssembly`
- Audit source: `docs/phase_f/audits/RibosomeAssembly_semantic_audit.md`
- Remediation scope: Priority-1 findings only (`ROW_WRONG`/`MISSING`)
- Result: `COMPLETE` (no partial items)

## Fixed Audit Entries

- `RIBASM-S1-01` (`MISSING`)
  - Pattern applied: `M1` (Add the missing entry / entries)
  - Change made in `data/schemas/per_process_wiring/RibosomeAssembly.yaml`:
    - Expanded `consume_stoichiometry` to include the full consumed set from composition-driven assembly:
      - rRNA consumed set now includes `MGrrnA16S`, `MGrrnA23S`, `MGrrnA5S`
      - monomer consumed set now includes all 52 consumed ribosomal monomer WIDs (including pre-existing `MG_417_MONOMER` plus 51 previously missing entries)
  - Notes:
    - No schema changes were made.
    - No OC or MATLAB code was modified.
    - No `CODE_DEVIATES` entries were changed.
    - No `VERIFIED` entries were changed.

## Unfixed / Deferred Items

- None.

## Verification Executed (in required order)

1. YAML parse check (WSL venv python): `PASS` (`OK dict len= 14`)
2. L1b row structural verification:
   - Command: `bin\oc-py scripts/l1b_verify_wiring.py --process RibosomeAssembly`
   - Result: `PASS` for `RibosomeAssembly`
3. Row/cross-row validate-only build:
   - Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
   - Result: `PASS` (no new row-level/cross-row failures)
