# STATUS: ProteinProcessingI ROW_WRONG/MISSING Remediation

- Process: `ProteinProcessingI`
- Date: `2026-07-02`
- Scope: Priority-1 fixes from `docs/phase_f/audits/ProteinProcessingI_semantic_audit.md`
- Overall status: `COMPLETE`

## Fixed Audit Entries

1. `PPI-S6-03` (`ROW_WRONG`)
- Pattern applied: `R2` (ordering-claim remediation)
- Changes made in `data/schemas/per_process_wiring/ProteinProcessingI.yaml`:
  - Removed unsupported runtime claim `ordering_constraints.soft_after: ["Translation"]` and set `soft_after: []`.
  - Updated `ordering_constraints.note` to state executable semantics: MATLAB runtime process ordering is randomized except `tRNAAminoacylation < Translation`, and OC has no explicit `Translation -> ProteinProcessingI` edge.
  - Added a `deviations.known_deviations` line documenting that the class prose says "following translation" but this is not an enforced runtime process-order edge in MATLAB or OC.

## Unfixed / Partial Items

- None. The audit listed no Priority-1 `MISSING` entries for this row.

## Validation Summary

- YAML parse: PASS
  - Command: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python - <<'PY' ... PY"`
  - Output: `OK dict len= 14`
- `l1b_verify_wiring --process ProteinProcessingI`: PASS
  - Command: `bin\\oc-py scripts/l1b_verify_wiring.py --process ProteinProcessingI`
  - Output: `L1b wiring conformance: PASS (1/1 rows PASS)` and `ProteinProcessingI: PASS`
- `build_wiring_db --validate-only`: PASS
  - Command: `bin\\oc-py scripts/build_wiring_db.py --validate-only`
  - Output: `[CROSS] 0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows` then `PASS`
