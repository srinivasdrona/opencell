# STATUS: remediate MacromolecularComplexation wiring row

Date: 2026-07-02
Process row: `data/schemas/per_process_wiring/MacromolecularComplexation.yaml`
Audit source: `docs/phase_f/audits/MacromolecularComplexation_semantic_audit.md`
Result: COMPLETE (no PARTIAL flag)

## Priority-1 entries fixed

- `MCX-S4-03` (`ROW_WRONG`) -> Pattern `R2`
  - Removed stale Poisson-multiplicity claims from method notes.
  - Updated method notes to reflect one-copy-per-iteration parity and left the cluster-1 fallback as the actual known deviation.

- `MCX-S5-01` (`ROW_WRONG`) -> Pattern `R2`
  - Corrected `deviations.shared_pool_projection_merges_compartments` from `false` to `true`.
  - Added explicit `known_deviations` note that MATLAB writes compartment-indexed complex counts while OC projects to flat `complex.counts[wid]`.

- `MCX-S6-02` (`ROW_WRONG`) -> Pattern `R2`
  - Updated allocator engagement note to state asymmetry explicitly: MATLAB consumes `this.substrates`, OC consumes `substrates_allocated` grants and can no-op on zero grants.
  - Added explicit allocator-gating divergence entry under `known_deviations`.

## Entries not fixed

- None. All Priority-1 entries listed in the audit were remediated in-row.

## Verification run (required sequence)

1. YAML parse:
   - `wsl -e bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -c "import yaml; d = yaml.safe_load(open(\"data/schemas/per_process_wiring/MacromolecularComplexation.yaml\")); print(\"OK dict len=\", len(d))"'`
   - Output: `OK dict len= 14`

2. L1b row check:
   - `bin\oc-py scripts/l1b_verify_wiring.py --process MacromolecularComplexation`
   - Output: `PASS` for `MacromolecularComplexation`

3. Cross-row validation:
   - `bin\oc-py scripts/build_wiring_db.py --validate-only`
   - Output: `PASS` with `0` reciprocal mismatches and `0` cyclic ordering.
