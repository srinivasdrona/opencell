# STATUS: FtsZPolymerization wiring-row remediation (PARTIAL)

- Scope: Priority-1 ROW_WRONG/MISSING remediation for `data/schemas/per_process_wiring/FtsZPolymerization.yaml` per `docs/phase_f/audits/FtsZPolymerization_semantic_audit.md`.
- Result: PARTIAL (row remediation complete; global validation command has unrelated pre-existing failure outside this row).

## Fixed audit entries

1. `FTSZ-S4-02` (`ROW_WRONG`)
- Pattern applied: `R2` (asymmetric claim clarification).
- Changes made:
  - Updated `methods.calcResourceRequirements_Current.matlab.source` to raw MATLAB anchor `FtsZPolymerization.m:189-193`.
  - Replaced request-formula text with explicit MATLAB formula: `request_gtp = enzymes(FtsZ) + enzymes(FtsZ_GDP)`.
  - Updated `allocator.request_formula.note` to explicitly state asymmetry: MATLAB uses current enzyme counts; OC uses post-update `next_counts` (CODE_DEVIATES).

2. `FTSZ-S4-03` (`ROW_WRONG`)
- Pattern applied: `R2` (explicit asymmetry/deviation note).
- Changes made:
  - Added `known_deviations` line documenting OC-only defensive guards in clamp loops (`positive.size <= 0`, `FtsZ_GDP <= 0`) versus MATLAB loop body.
  - Updated `deviations.note` to explicitly include defensive-guard and request-timing divergences.

## Entries not fixed

- None.

## Validation summary

- Ran required checks in order after edit:
  1. YAML parse check
  2. `scripts/l1b_verify_wiring.py --process FtsZPolymerization`
  3. `scripts/build_wiring_db.py --validate-only`
- Outcomes:
  - Check 1: PASS (`OK dict len= 14`)
  - Check 2: PASS (`FtsZPolymerization: PASS`)
  - Check 3: FAIL on unrelated row `ReplicationInitiation` (`consume_stoichiometry[0].matlab_anchor/oc_anchor lines must match start-end`); no `FtsZPolymerization` failure was reported.
- Rationale for PARTIAL:
  - Cross-process fixes are out of scope for this task.
  - This remediation changed only `FtsZPolymerization` row content and did not introduce a new failure in that row.
