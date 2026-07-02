# STATUS: Remediate TerminalOrganelleAssembly Wiring Row

- Status: COMPLETE
- Target row: `data/schemas/per_process_wiring/TerminalOrganelleAssembly.yaml`
- Audit source: `docs/phase_f/audits/TerminalOrganelleAssembly_semantic_audit.md`

## Priority-1 Entries Fixed

1. TOA-S1-01 (`MISSING`) - Pattern `M1`
- Added missing `consume_stoichiometry` entries for:
  - `MG_192_MONOMER` (`membrane`)
  - `MG_312_MONOMER` (`cytosol`)
  - `MG_317_MONOMER` (`cytosol`)

2. TOA-S3-01 (`MISSING`) - Pattern `M1`
- Added missing `produce_stoichiometry` entries for:
  - `MG_192_MONOMER` (`membrane`)
  - `MG_312_MONOMER` (`cytosol`)
  - `MG_317_MONOMER` (`cytosol`)

3. TOA-S4-01 (`ROW_WRONG`) - Pattern `R1` (schema-compatible narrative correction)
- Updated consume/produce formula narratives and OC anchor notes to explicitly encode asymmetry:
  - MATLAB side: full-pool transfer from unincorporated to incorporated.
  - OC side: trace-hint override path or one-copy-per-tick fallback transfer.
- Added explicit `known_deviations` line documenting this formula-path divergence.

4. TOA-S5-01 (`ROW_WRONG`) - Pattern `R1` (projection semantics correction)
- Corrected `compartment_routing` tuples to stop claiming same consume/produce compartment labels.
- For all listed substrates, set `produce_compartment: null` and `mismatch: true` with notes that:
  - MATLAB routes unincorporated -> incorporated terminal-organelle compartments.
  - Schema compartment enum lacks terminal-organelle labels.
  - OC projection is `compartment_1 -> compartment_0`.
- Added explicit `known_deviations` line documenting label-projection divergence.

## Entries Not Fixed

- None. All Priority-1 entries in the audit were remediated in-row.

## Verification Run (required sequence)

1. YAML parse check:
- Command: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python ...yaml.safe_load(...)"`
- Result: `OK dict len= 14`

2. L1b process check:
- Command: `bin\oc-py scripts/l1b_verify_wiring.py --process TerminalOrganelleAssembly`
- Result: `PASS (1/1 rows PASS)` and row `TerminalOrganelleAssembly: PASS`

3. Cross-row validation:
- Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
- Result: `[CROSS] 0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows` and `PASS`