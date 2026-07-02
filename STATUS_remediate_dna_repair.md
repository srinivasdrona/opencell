# STATUS: DNARepair wiring-row remediation

## Scope
- Target row: `data/schemas/per_process_wiring/DNARepair.yaml`
- Audit source: `docs/phase_f/audits/DNARepair_semantic_audit.md`
- Remediation class: mechanical row edits only (no schema/code changes)
- Status: COMPLETE

## Priority-1 entries fixed
1. `DNARepair-S1-01` (`MISSING`) - **Pattern M1**
- Added missing MATLAB-consumed metabolites to `consume_stoichiometry`: `NAD`, `AMET`, `H2O`.
- Kept OC truth explicit per-entry (`NAD`/`H2O` not decremented in OC; `AMET` conditionally decremented in OC bypass path).
- Added/expanded `deviations.known_deviations` strings for MATLAB-vs-OC consume divergence.

2. `DNARepair-S3-01` (`MISSING`) - **Pattern M1 + M2**
- Expanded `produce_stoichiometry` beyond `AMP/PPI/AHCYS/H` with canonical MATLAB exemplars:
  `ADP`, `PI`, `NMN`, `DAMP`, `DCMP`, `DGMP`, `DTMP`, `DR5P`.
- Documented that OC does not emit this broader MATLAB product set (entry notes + known deviation).
- Declared exemplar scope in `process.notes` ("canonical exemplars listed, not exhaustive enumeration").

3. `DNARepair-S4-01` (`ROW_WRONG`) - **Pattern R1**
- Replaced `allocator.request_formula.matlab` with executable-shape statement:
  `max(0, -S) * min(ceil(C * E * dt), rates)`.
- Updated request-formula note to explicitly distinguish MATLAB formulation from OC pathway-level approximation.
- Added known-deviation line capturing formula divergence.

4. `DNARepair-S4-02` (`ROW_WRONG`) - **Pattern R1**
- Updated dNTP consume formulas (`DATP/DCTP/DGTP/DTTP`) to stop presenting fixed split as MATLAB truth.
- Each entry now states MATLAB sequence/reaction-driven usage vs OC fixed `dntp_split` approximation.
- Added known-deviation line for dNTP formula asymmetry.

5. `DNARepair-S5-02` (`ROW_WRONG`) - **Pattern R2**
- Set `compartment_routing` mismatch truthfully for `AMP` and `PPI` (`mismatch: true`).
- Updated routing notes to explicitly state OC tuple absence.

## Unfixed entries
- None from Priority-1 list.

## Mandatory verification results
1. YAML parse: PASS (`OK dict len= 14`)
2. `bin\oc-py scripts/l1b_verify_wiring.py --process DNARepair`: PASS
3. `bin\oc-py scripts/build_wiring_db.py --validate-only`: PASS (no new row-level/cross-row failures)
