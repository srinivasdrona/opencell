# STATUS: ChromosomeCondensation ROW_WRONG/MISSING Remediation

Date: 2026-07-02
Process row: `data/schemas/per_process_wiring/ChromosomeCondensation.yaml`
Audit source: `docs/phase_f/audits/ChromosomeCondensation_semantic_audit.md`

## Fixed Audit Entries

1. `CC-S5-02` (`ROW_WRONG`)  
Pattern applied: `R2`  
Changes:
- Set `deviations.shared_pool_projection_merges_compartments` to `true` to match OC flat per-WID shared substrate representation.
- Added explicit `known_deviations` text documenting MATLAB compartment-indexed routing/writeback vs OC merged compartment projection.

2. `CC-S6-01` (`ROW_WRONG`)  
Pattern applied: `R1`  
Changes:
- Updated `allocator.mode.oc_current` from `mixed` to `allocation`.
- Removed stale OC ATP/H2O bypass entries that claimed fallback-to-global reads.
- Rewrote allocator/helper notes to reflect allocated-only non-negative clamp behavior in `_allocated_or_state`.
- Added/updated `known_deviations` wording so divergence is explicit and truthful.

3. `CC-S6-02` (`MISSING`)  
Pattern applied: `M1` (with explicit asymmetric-enforcement wording per `R2` style)  
Changes:
- Added explicit allocator-coupled timing claim in `ordering_constraints.note`:
  - MATLAB enforces per-tick request -> allocation -> evolve sequence.
  - OC request emission is in-process and equivalent same-tick request/grant timing is not explicitly encoded in composite flow.
- Added matching `known_deviations` line documenting missing explicit OC enforcement edge.

## Not Fixed / Partial

- None. All Priority-1 entries listed in the audit were remediated in-row.

## Scope Guardrails Followed

- No schema (`_schema.yaml`) edits.
- No OC/MATLAB code edits.
- No cross-process row edits.
- No CODE_DEVIATES entry rewrites; only row-truth alignment for Priority-1 ROW_WRONG/MISSING findings.
