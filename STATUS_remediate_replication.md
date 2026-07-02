# STATUS: Replication Wiring Row Remediation

- Date: 2026-07-02
- Process: `Replication`
- Row file: `data/schemas/per_process_wiring/Replication.yaml`
- Audit source: `docs/phase_f/audits/Replication_semantic_audit.md`
- Status: COMPLETE

## Priority-1 Audit Entries Fixed

1. `REP-S1-02` (`MISSING`) - Pattern `M1`
- Added `H2O` to `consume_stoichiometry` with MATLAB/OC anchors and formula.
- Added matching `compartment_routing` entry.
- Documented OC non-hint gap under `deviations.known_deviations`.

2. `REP-S1-03` (`MISSING`) - Pattern `M1`
- Added `NAD` to `consume_stoichiometry` with MATLAB/OC anchors and formula.
- Added matching `compartment_routing` entry.
- Documented OC non-hint gap under `deviations.known_deviations`.

3. `REP-S3-01` (`MISSING`) - Pattern `M1`
- Added `AMP` to `produce_stoichiometry` with MATLAB/OC anchors and formula.
- Added matching `compartment_routing` entry.

4. `REP-S3-02` (`ROW_WRONG`) - Pattern `R1`
- Corrected OC produce attribution from non-hint path to trace-hint-gated branch.
- Updated produce entry notes to state non-hint OC does not emit byproducts.
- Added explicit known-deviation line for byproduct gating divergence.

5. `REP-S4-01` (`ROW_WRONG`) - Pattern `R1`
- Updated dNTP consume formulas/notes to explicitly distinguish MATLAB sequence-exact `subsequenceBaseCounts(...)` from OC `partition_counts(...)` approximation.
- Added explicit known-deviation line for this formula-family divergence.

6. `REP-S4-02` (`ROW_WRONG`) - Pattern `R1`
- Updated `H` produce formula from `atp_events` to `atp_events + ligations`.
- Updated anchors/notes to reflect ATP-hydrolysis + ligation hydrogen contribution.

7. `REP-S5-01` (`ROW_WRONG`) - Pattern `R1`
- Corrected `deviations.shared_pool_projection_merges_compartments` from `false` to `true`.

8. `REP-S6-01` (`MISSING`) - Pattern `M1`
- Added `H2O` and `NAD` to `allocator.requests` as MATLAB request-set members.
- Kept OC bypass semantics and clarified branch-specific behavior in notes.
- Added known-deviation line for OC request-set omission.

9. `REP-S6-03` (`ROW_WRONG`) - Pattern `R2`
- Rewrote `allocator.mode.note` to remove false raw-substrate-fallback claim for OC non-hint path.
- Added known-deviation line documenting absent OC non-hint fallback.

## Entries Not Fixed

- None. All Priority-1 items listed in the audit were remediated in-row.

## Required Verification Run

1. YAML parse check (WSL/Python): PASS (`OK dict len= 14`)
2. `bin\oc-py scripts/l1b_verify_wiring.py --process Replication`: PASS
3. `bin\oc-py scripts/build_wiring_db.py --validate-only`: PASS
