# STATUS: ProteinTranslocation Wiring Remediation

- Scope: `data/schemas/per_process_wiring/ProteinTranslocation.yaml`
- Audit source: `docs/phase_f/audits/ProteinTranslocation_semantic_audit.md`
- Result: COMPLETE (no PARTIAL flag)

## Fixed Audit Entries

1. `PT-S4-01` (`ROW_WRONG`) - Pattern `R2`
- Updated `methods.evolveState.oc.note` and `methods.evolveState.note` to match current OC behavior (copy-level randperm + rate-scaled capacity checks + break-on-first-insufficient-copy).
- Removed stale `known_deviations` lines that incorrectly claimed species-phase batching and raw-enzyme-count semantics.

2. `PT-S4-02` (`ROW_WRONG`) - Pattern `R1`
- Corrected `allocator.request_formula.matlab` to include MATLAB capacity clipping terms:
  - `min(translocases, ...)` for ATP demand
  - `min(SRPs, ...)` for GTP demand
- Updated allocator note to explicitly state MATLAB-side capacity clipping.

## Not Fixed / Deferred

- None. No additional Priority-1 `ROW_WRONG`/`MISSING` entries were listed for this row.

## Verification Evidence

1. YAML parse:
- Command: `wsl -e bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c "import yaml; d = yaml.safe_load(open(\"data/schemas/per_process_wiring/ProteinTranslocation.yaml\")); print(\"OK dict len=\", len(d))"'`
- Result: `OK dict len= 14`

2. L1b row conformance:
- Command: `bin\oc-py scripts/l1b_verify_wiring.py --process ProteinTranslocation`
- Result: `PASS` for `ProteinTranslocation`

3. Cross-row validation:
- Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
- Result: `PASS` with `0` reciprocal mismatches, `0` cyclic ordering, `0` missing rows.
