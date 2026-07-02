# STATUS: Translation wiring row remediation

- Date: 2026-07-02
- Process: `Translation`
- Row file: `data/schemas/per_process_wiring/Translation.yaml`
- Audit source: `docs/phase_f/audits/Translation_semantic_audit.md`
- Status: COMPLETE (not PARTIAL)

## Priority-1 audit entries remediated

1. `TL-S2-02` (`ROW_WRONG`) - Pattern `R1`
- Kept `consume_stoichiometry` entries for `GTP` and `H2O` anchored to MATLAB formulas.
- Updated OC side to explicit non-consume semantics (read-side gating only, no OC consume writeback) and aligned notes accordingly.
- Added explicit `known_deviations` entry documenting MATLAB decrement vs OC read-only gating for `GTP/H2O`.

2. `TL-S5-01` (`ROW_WRONG`) - Pattern `R2`
- Corrected compartment-projection claim by setting `deviations.shared_pool_projection_merges_compartments: true`.
- Updated `compartment_routing` prose/flags to reflect OC flat shared-substrate surface (no compartment axis).
- Added `known_deviations` entry documenting MATLAB compartment-indexed routing vs OC merged per-WID projection.

3. `TL-S5-02` (`ROW_WRONG`) - Pattern `R1`
- Updated `compartment_routing` for `GDP/PI/H` from `mismatch: false` to `mismatch: true`.
- Updated notes to state MATLAB produces cytosolic byproducts while OC Translation has no corresponding metabolite route.
- Existing byproduct absence deviation retained; no schema changes.

4. `TL-S6-03` (`ROW_WRONG`) - Pattern `R2`
- Updated `ordering_constraints.note` to disambiguate enforcement: MATLAB enforces `tRNAAminoacylation -> Translation`; OC composite has no explicit matching hard process edge (`CODE_DEVIATES`).
- Added corresponding `known_deviations` entry for missing OC hard-edge enforcement.

## Items not fixed

- None.

## Mandatory verification run (in order)

1. YAML parse:
- Command: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c 'import yaml; d = yaml.safe_load(open(\"data/schemas/per_process_wiring/Translation.yaml\")); print(\"OK dict len=\", len(d))'"`
- Result: `OK dict len= 14`

2. L1b row verification:
- Command: `bin\oc-py scripts/l1b_verify_wiring.py --process Translation`
- Result: `PASS` for Translation

3. Row-level/cross-row validation:
- Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
- Result: `PASS` with `0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows`
