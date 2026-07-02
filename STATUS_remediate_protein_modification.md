# STATUS: ProteinModification Wiring Remediation

- Flag: PARTIAL
- Scope: `data/schemas/per_process_wiring/ProteinModification.yaml` only
- Audit source: `docs/phase_f/audits/ProteinModification_semantic_audit.md`

## Fixed Priority-1 Entries

1. `PM-S4-01` (`ROW_WRONG`) - Pattern `R2`
- Change: Updated `allocator.request_formula.matlab` to executable MATLAB formula:
  `max(0, -reactionStoichiometryMatrix) * min(ceil(reactionCatalysisMatrix * enzymes * stepSizeSec), reactionModificationMatrix * unmodifiedMonomers)`.
- Rationale: Row previously claimed an availability-based request formula for MATLAB, which was incorrect.

2. `PM-S4-04` (`ROW_WRONG`) - Pattern `R1`
- Change: Updated all `consume_stoichiometry` and `produce_stoichiometry` `formula_or_constant` entries to include reaction-to-protein projection:
  `reactionStoichiometryMatrix(row,:) * reactionModificationMatrix(:,monomerIndexs_modified) * reactionFluxes`.
- Rationale: Previous formulas omitted the projection term and were dimensionally incomplete versus executable MATLAB/OC path.

3. `PM-S4-05` (`ROW_WRONG`) - Pattern `R1`
- Change: Replaced stale MATLAB `plan.md` anchors with direct `ProteinModification.m` anchors in:
  - `methods.calcResourceRequirements_Current.matlab.source` (`324-327`)
  - `methods.evolveState.matlab.source` (`359-379`)
  - MATLAB anchors for ATP/ADP/H/PI stoichiometry entries (`387-389`)
  - `source_anchors.matlab_blocks.request_formula` (`324-327`)
  - `source_anchors.matlab_blocks.stochastic_update` (`359-379`)
- Rationale: Audit identified anchor rot; direct executable anchors are now used.

## Not Fixed / Deferred

- None.

## Verification Summary

- YAML parse check: PASS (`OK dict len= 14`)
- `l1b_verify_wiring` for `ProteinModification`: PASS
- `build_wiring_db --validate-only`: FAIL due to pre-existing unrelated row error:
  `[FAIL row=Translation] consume_stoichiometry[0].oc_anchor: expected mapping; consume_stoichiometry[1].oc_anchor: expected mapping`
  with `[CROSS] 0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows`.
- Interpretation: no ProteinModification row failure and no cross-row mismatch introduced by this change; global validate-only remains blocked by `Translation` row issues outside requested scope.
