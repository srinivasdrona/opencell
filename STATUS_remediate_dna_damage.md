# STATUS: DNADamage wiring-row remediation

- Scope: Priority-1 `ROW_WRONG` / `MISSING` items from `docs/phase_f/audits/DNADamage_semantic_audit.md`
- Target row: `data/schemas/per_process_wiring/DNADamage.yaml`
- Result: COMPLETE (no PARTIAL flags)

## Fixed audit entries

1. `DNADAMAGE-S2-01` (`ROW_WRONG`) - Pattern `R1`
- Removed `UVB_radiation` and `gamma_radiation` from `consume_stoichiometry` (they are non-consumptive gating inputs, not decremented stoichiometric consumes).
- Added explicit `known_deviations` note documenting non-consumptive gating behavior.

2. `DNADAMAGE-S3-01` (`MISSING`) - Pattern `M1`
- Added missing MATLAB-produced substrates `CO2`, `H`, and `NH3` to `produce_stoichiometry` with MATLAB anchors.
- OC anchors are retained with explicit notes that OC does not emit substrate stoichiometry deltas; this divergence is documented in `known_deviations`.

3. `DNADAMAGE-S3-02` (`ROW_WRONG`) - Pattern `R1`
- Removed `DR5P` from `produce_stoichiometry` and removed corresponding `compartment_routing` production claim.
- Added `known_deviations` note clarifying DR5P is DNA-factorized in MATLAB and not emitted by small-molecule writeback.

4. `DNADAMAGE-S4-02` (`ROW_WRONG`) - Pattern `R2`
- Corrected `methods.calcResourceRequirements_Current` MATLAB metadata to the implemented MATLAB method/formula anchor.
- Updated method-level note to state MATLAB enforces allocator request formula while OC does not implement the corresponding path.

5. `DNADAMAGE-S5-01` (`ROW_WRONG`) - Pattern `R2`
- Updated compartment/routing notes to state radiation inputs are gating semantics, not consumptive routing claims.
- Set `deviations.shared_pool_projection_merges_compartments: true` and documented OC flat-projection semantics in `known_deviations`.

6. `DNADAMAGE-S5-02` (`ROW_WRONG`) - Pattern `R2`
- Updated OC routing wording to align with current composite topology (`karr_dna_damage` mapped only to `chromosome`).
- Added explicit `known_deviations` entry documenting that process-local substrate/stimulus reads are not active in that composition.

7. `DNADAMAGE-S6-01` (`ROW_WRONG`) - Pattern `R2`
- Corrected allocator mode to `karr: allocation`, `oc_current: bypass`.
- Updated request formula metadata/note to acknowledge MATLAB request/grant engagement vs OC allocator bypass.

## Entries not fixed

- None. All Priority-1 entries listed in the audit were remediated.

## Mandatory verification run (in required order)

1. YAML parse: PASS (`OK dict len= 14`)
2. `bin\oc-py scripts/l1b_verify_wiring.py --process DNADamage`: PASS
3. `bin\oc-py scripts/build_wiring_db.py --validate-only`: PASS (`[CROSS] 0 reciprocal mismatches, 0 cyclic ordering, 0 missing rows`)
