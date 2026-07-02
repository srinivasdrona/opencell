# STATUS: ChromosomeSegregation Wiring Row Remediation

- Date: 2026-07-02
- Target row: `data/schemas/per_process_wiring/ChromosomeSegregation.yaml`
- Audit source: `docs/phase_f/audits/ChromosomeSegregation_semantic_audit.md`
- Status: COMPLETE (no PARTIAL flag)

## Priority-1 entries fixed

1. `CHRSEG-S4-02` (ROW_WRONG)
- Applied pattern: `R2` (asymmetric gating claim remediation)
- Change made:
  - Updated `allocator.request_formula.matlab` to remove unsupported `supercoiled` gate term.
  - Updated `allocator.request_formula.note` to explicitly state MATLAB-vs-OC gate asymmetry.
  - Added explicit `deviations.known_deviations` entry documenting: MATLAB request gate does not require supercoiling; OC default does.

2. `CHRSEG-S6-03` (ROW_WRONG)
- Applied pattern: `R2` (asymmetric gate membership/flag claim remediation)
- Change made:
  - Updated bypass entry for `MG_203_204_TETRAMER` from `source: oc` to `source: both`.
  - Updated note to state MATLAB requires TopoIV while OC default makes TopoIV optional.
  - Added explicit `deviations.known_deviations` entry documenting MATLAB-required vs OC-default-optional TopoIV gating.

## Entries not fixed

- None. No `MISSING` entries were listed for Priority-1 in this audit.

## Scope guardrails honored

- `_schema.yaml` unchanged.
- No OC or MATLAB code modified.
- No `CODE_DEVIATES` or `VERIFIED` audit entries altered beyond required row-truth corrections for the two Priority-1 `ROW_WRONG` claims.
