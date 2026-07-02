# STATUS: RNADecay wiring-row remediation

- Scope: `data/schemas/per_process_wiring/RNADecay.yaml`
- Audit source: `docs/phase_f/audits/RNADecay_semantic_audit.md`
- Outcome: PARTIAL (verification blocker is pre-existing and outside RNADecay scope)

## Fixed Priority-1 entries

1. `RNADECAY-S3-01` (`MISSING`)  
   Pattern: `M2` (declare exemplar scope)  
   Change: Updated top-level `process.notes` to explicitly declare exemplar scope: canonical exemplars listed, not exhaustive enumeration.

2. `RNADECAY-S4-03` (`ROW_WRONG`)  
   Pattern: `R1` (structural/formula correction)  
   Change: Corrected MATLAB request formula attribution under `allocator.request_formula.matlab` to executable `calcResourceRequirements_Current` semantics, including aborted-transcript water term. Updated `methods.calcResourceRequirements_Current.matlab` anchor to `RNADecay.m:282-294` and aligned method notes.

3. `RNADECAY-S5-02` (`ROW_WRONG`)  
   Pattern: `R1` (structural contradiction correction)  
   Change: Set `deviations.shared_pool_projection_merges_compartments: true` to reflect OC flat per-WID substrate projection. Added explicit `known_deviations` line documenting MATLAB compartment-indexed routing vs OC merged projection.

4. `RNADECAY-S6-03` (`MISSING`)  
   Pattern: `R2` (ordering/flag asymmetry explicit)  
   Change: Updated `ordering_constraints.note` to explicitly state MATLAB same-tick `calcResourceRequirements_Current -> allocations -> evolveState` enforcement and that OC lacks a corresponding RNADecay-specific hard ordering edge (`CODE_DEVIATES`). Added matching `known_deviations` line.

## Entries not fixed

- None.

## Notes

- No schema changes.
- No OC code or MATLAB code changes.
- No cross-process row edits.

## Verification

1. YAML parse check (required command #1): PASS  
   Result: `OK dict len= 14`

2. L1b row check (required command #2): PASS  
   Result: `L1b wiring conformance: PASS (1/1 rows PASS)` for `RNADecay`.

3. Cross-row validation (required command #3): FAIL (pre-existing, unrelated)  
   Result: `[FAIL row=ChromosomeCondensation] source_anchors.matlab_blocks.simulation_ordering: lines must match start-end`  
   Assessment: No new RNADecay row-level or cross-row mismatch was reported; failure is an existing blocker in another row.
