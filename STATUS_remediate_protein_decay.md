# STATUS: ProteinDecay ROW_WRONG/MISSING Remediation

## Scope
- Target row: `data/schemas/per_process_wiring/ProteinDecay.yaml`
- Audit source: `docs/phase_f/audits/ProteinDecay_semantic_audit.md`
- Applied only Priority-1 `ROW_WRONG` / `MISSING` items; no schema/code edits.
- Run date: `2026-07-02`

## Fixed Audit Entries
- `PD-S1-01` (`MISSING`) - **Pattern M2**
  - Added explicit row scope declaration in `process.notes`: "This row is exemplar-scoped; canonical exemplars listed, not exhaustive enumeration."
- `PD-S2-02` (`ROW_WRONG`) - **Pattern R1**
  - Updated `consume_stoichiometry` H claim to explicitly separate MATLAB vs OC semantics and added clipping-gate asymmetry note.
  - Added matching one-line `known_deviations` entry.
- `PD-S3-01` (`MISSING`) - **Pattern M2**
  - Covered by the same explicit exemplar-scope declaration in `process.notes`.
- `PD-S3-02` (`ROW_WRONG`) - **Pattern R1**
  - Corrected ALA/GLY/MET OC anchors/notes to reflect latent-path, disabled-by-default behavior; removed active-fabrication implication.
  - Added matching one-line `known_deviations` entry.
- `PD-S4-02` (`ROW_WRONG`) - **Pattern R1**
  - Rewrote H consume formula/note language to remove formula-equivalence claim and document Poisson/clipping vs MATLAB stochasticRound/while-loop behavior.
  - Added matching one-line `known_deviations` entry.
- `PD-S5-01` (`ROW_WRONG`) - **Pattern R1**
  - Reconciled `compartment_routing` with merge deviation by setting `mismatch: true` on listed entries and clarifying merge behavior in notes.
- `PD-S6-02` (`MISSING`) - **Pattern M1**
  - Added explicit allocator-coupled step-order claim in `ordering_constraints.note` (`request_calculator_pd` before `karr_allocation_step`) and captured it in `known_deviations`.

## Unfixed / Partial
- None.
