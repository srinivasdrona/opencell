# STATUS: DNASupercoiling wiring-row remediation

- Scope: `data/schemas/per_process_wiring/DNASupercoiling.yaml`
- Audit source: `docs/phase_f/audits/DNASupercoiling_semantic_audit.md`
- Result: COMPLETE (no PARTIAL flag)

## Fixed Priority-1 entries

1. `DNASUP-S2-01` (`ROW_WRONG`) - Pattern `R1`
- Change: corrected ATP consume `oc_anchor` from request-emission path to the executed consume/writeback path.
- Updated row location: `consume_stoichiometry` entry for `wid: ATP`.
- New OC evidence: `karr_dna_supercoiling.py:1024-1035` with note that emission occurs via `update["substrates"]` in `next_update`.

2. `DNASUP-S6-02` (`MISSING`) - Pattern `M1` + ordering/deviation note update (`R2`-style wording)
- Change: added explicit allocator-coupled ordering claim in `ordering_constraints.note`:
  MATLAB per-tick `calcResourceRequirements_Current -> allocation injection -> evolveState` versus OC in-process request emission with no explicit equivalent composite dependency edge.
- Change: added matching one-line `deviations.known_deviations` entry documenting missing OC explicit edge from DNASupercoiling request emission to `karr_allocation_step`.

## Entries not fixed

- None. All Priority-1 items listed in the audit for this row were remediated.

## Verification run (required order)

1. YAML parse: PASS (`OK dict len= 14`)
2. `bin\oc-py scripts/l1b_verify_wiring.py --process DNASupercoiling`: PASS
3. `bin\oc-py scripts/build_wiring_db.py --validate-only`: PASS (no new row-level/cross-row failures)
