# Track-A4: L3 Resource-Vector Completeness

## Mandate
Two processes have incomplete resource-vector enrollments in the allocator:

1. **DNASupercoiling**: missing `H2O` from request vector and consumer enrollment (currently ATP-only). Karr ATP-driven topoisomerase events consume H2O stoichiometrically.
2. **ProteinTranslocation**: missing `GTP/ADP/GDP/Pi/H2O/H+` (currently ATP-only). Karr extract explicitly states ATP+GTP requirement with H2O/ADP/GDP/Pi/H+ updates.

## Authoritative references (all merged on main)
- `opencell/validation/swarm/allocator/allocator_audit.md` — L3 hot list (lines 9-22)
- `opencell/validation/swarm/consolidated/CONSOLIDATED_AUDIT_REPORT.md` — finding row 6 + new finding #1
- `docs/karr_extracts/process/22_ProteinTranslocation.md:122-125` — canonical Karr substrate list

## Specific file/line targets

### DNASupercoiling
- `opencell/vivarium/karr_dna_supercoiling.py:190-193` — request build (currently ATP-only)
- `opencell/vivarium/karr_composite.py:1397` — consumer enrollment vector (ATP-only)
- Add H2O to both. Verify Karr ratio (ATP:H2O typically 1:1 for hydrolysis).

### ProteinTranslocation
- `opencell/vivarium/karr_composite.py:1394` — consumer enrollment vector
- `opencell/vivarium/karr_request_calculators.py:507-513` — request calculator (currently ATP-only)
- `opencell/vivarium/karr_protein_translocation.py` — process body must consume from allocated GTP/H2O too
- Read `docs/karr_extracts/process/22_ProteinTranslocation.md:122-125` for the exact substrate list and update direction (ATP→ADP+Pi, GTP→GDP+Pi, H2O consumed, H+ produced).

## Implementation plan

### Part 1 — DNASupercoiling H2O
1. Add `H2O` to the request vector at `karr_dna_supercoiling.py:190-193`.
2. Add `H2O` to consumer enrollment at `karr_composite.py:1397`.
3. Modify `next_update` to consume H2O at the same stoichiometric ratio as ATP. Keep strict-zero discipline (no global-pool fallback — A1 already landed this for the helper).

### Part 2 — ProteinTranslocation full vector
1. Update `RequestCalculatorProteinTranslocation` (lines 507-513) to compute demand for ATP + GTP + H2O.
2. Add GTP/ADP/GDP/Pi/H2O/H+ to the consumer enrollment vector.
3. Modify `karr_protein_translocation.py` `next_update`:
   - Read allocated ATP, GTP, H2O (strict-zero).
   - Emit deltas for ATP→ADP+Pi, GTP→GDP+Pi, H2O→consumed, H+→produced.
   - Match Karr extract stoichiometry as closely as possible without re-implementing the full state machine (biology fidelity is a separate concern).

## Tests
- `tests/integration/test_dna_supercoiling_h2o_enrollment.py` — assert request vector includes H2O; assert allocator grants H2O; assert process consumes H2O.
- `tests/integration/test_protein_translocation_full_vector.py` — assert all 7 substrate channels enrolled; assert deltas have correct signs (ATP/GTP/H2O negative; ADP/GDP/Pi/H+ positive).

```
py -3.12 -m pytest tests/unit -q --ignore=tests/gates
```
Must remain green.

## Self-grading
Write `opencell/validation/track_a/a4_l3_vector_completeness_summary.md`:
- Per-process: substrate IDs added to request + consumer, lines modified, stoichiometry source
- Whether tick-level mass-balance is sane (substrates in == substrates out for hydrolysis cycles)
- Any L3 gaps surfaced for other processes during the sweep

## Commit discipline
- Branch: `track-a/L3-vectors` (worktree `E:\opencell-worktrees\track-a4`).
- Commits:
  1. `track-a4: add H2O to DNASupercoiling allocator request + enrollment`
  2. `track-a4: extend ProteinTranslocation to full ATP+GTP+ADP+GDP+Pi+H2O+H+ vector`
  3. `track-a4: integration tests for L3 resource-vector completeness`

## Python interpreter
**Use `py -3.12`** for all pytest invocations.

## Budget
- Token budget: 220k with compaction at 75%.
- If ProteinTranslocation stoichiometry is unclear from the Karr extract, STOP and write `a4_stoichiometry_question.md` with the specific ambiguity — do not guess.

## Scope discipline
- Do not touch L5 helpers (A1 done).
- Do not enroll new processes that aren't already enrolled (A2 territory).
- Do not rename allocator keys (A3 territory).
- Stay in DNASupercoiling + ProteinTranslocation files + composite + request_calculators.
