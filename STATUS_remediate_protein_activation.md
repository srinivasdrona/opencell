# STATUS: ProteinActivation ROW_WRONG/MISSING Remediation

- Process: `ProteinActivation`
- Target row: `data/schemas/per_process_wiring/ProteinActivation.yaml`
- Audit source: `docs/phase_f/audits/ProteinActivation_semantic_audit.md`
- PARTIAL: `false`

## Fixed Audit Entries

- `PA-S1-00` (`ROW_WRONG`) -> **M2**
  - Added explicit scope contract in `process.notes`:
    - "This row is exemplar-scoped; canonical exemplars are listed and are not an exhaustive enumeration."

- `PA-S1-01` (`MISSING`) -> **M2**
  - Resolved by explicit exemplar-scope declaration (canonical consume entries are non-exhaustive by contract).

- `PA-S3-01` (`MISSING`) -> **M2**
  - Resolved by explicit exemplar-scope declaration (canonical produce entries are non-exhaustive by contract).

- `PA-S4-02` (`ROW_WRONG`) -> **R2**
  - Corrected `unit_conversion_chain` to state MATLAB concentration conversion/per-compartment evaluation versus OC raw flat-signal evaluation.
  - Added one-line `deviations.known_deviations` entry documenting the conversion/evaluation divergence.

- `PA-S5-01` (`ROW_WRONG`) -> **R1**
  - Corrected `compartment_routing` notes to reflect MATLAB compartmented tuple updates vs OC flat per-WID projection.
  - Set `deviations.shared_pool_projection_merges_compartments: true`.
  - Added one-line `deviations.known_deviations` entry documenting compartment projection flattening.

- `PA-S6-02` (`ROW_WRONG`) -> **R1**
  - Corrected `allocator.request_formula.matlab` to acknowledge existing `calcResourceRequirements_Current` with zero-return behavior.

## Unfixed Entries

- None. All Priority-1 fixes from the audit were applied.

## Mandatory Verification Results

1. YAML parse:
   - `OK dict len= 14`
2. L1b per-row check:
   - `L1b wiring conformance: PASS (1/1 rows PASS)`
   - `ProteinActivation: PASS`
3. Cross-row validate-only:
   - `[CROSS] 0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows`
   - `PASS`
