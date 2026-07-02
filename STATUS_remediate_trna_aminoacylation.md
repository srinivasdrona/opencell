# STATUS: tRNAAminoacylation ROW_WRONG/MISSING Remediation

Date: 2026-07-02
Process row: `data/schemas/per_process_wiring/tRNAAminoacylation.yaml`
Audit source: `docs/phase_f/audits/tRNAAminoacylation_semantic_audit.md`

## Fixed Audit Entries

- `TRNA-S1-01` (`MISSING`) -> Applied **M2**
  - Added explicit exemplar-scope policy in `process.notes`:
    - row is exemplar-scoped for `consume_stoichiometry`/`produce_stoichiometry`/`allocator.requests`
    - canonical exemplars are listed, not exhaustive enumeration.
- `TRNA-S3-01` (`MISSING`) -> Applied **M2**
  - Covered by the same explicit exemplar-scope declaration.
- `TRNA-S6-02` (`MISSING`) -> Applied **M2**
  - Covered by the same explicit exemplar-scope declaration for `allocator.requests`.
- `TRNA-S6-03` (`ROW_WRONG`) -> Applied **R2**
  - Updated `ordering_constraints.note` to explicitly state asymmetry:
    - MATLAB enforces tRNAAminoacylation-before-Translation.
    - OC composite does not encode a corresponding hard process edge (CODE_DEVIATES).
  - Added matching one-line `deviations.known_deviations` entry documenting missing OC enforcement.

## Unfixed Entries

- None. All Priority-1 entries listed for this row were remediated.

## Validation Run (mandatory sequence)

1. YAML parse check: PASS (`OK dict len= 14`)
2. `bin\oc-py scripts/l1b_verify_wiring.py --process tRNAAminoacylation`: PASS
3. `bin\oc-py scripts/build_wiring_db.py --validate-only`: PASS (`0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows`)

## Scope / Out-of-scope Confirmation

- No `_schema.yaml` changes.
- No OC code changes.
- No MATLAB source changes.
- No cross-process row edits.
