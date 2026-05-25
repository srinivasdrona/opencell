# Allocator Completeness Audit (L3 + L4 + L6)

## Top-line counts
- Processes audited: 28 (Class A roster).
- L3 HIGH: 2 (`DNASupercoiling`, `ProteinTranslocation`).
- L4 HIGH: 0 (MEDIUM mismatches: 2).
- L6 HIGH: 1 (`MacromolecularComplexation`).

## L3 hot list (resource-vector completeness)

1. `DNASupercoiling` — `H2O` is missing from the Python allocator/request vector.
   - Python process requests only `ATP` (`requests[self.name][self.atp_wid]`) and allocator enrollment is ATP-only for this process. `H2O` is absent from both request and consumer vectors.  
     Evidence: `opencell/vivarium/karr_dna_supercoiling.py:190-193`, `opencell/vivarium/karr_composite.py:1397`.
   - The reducer catalog already identifies this as ATP-only enrollment vs MATLAB ATP+H2O usage.  
     Cross-reference: `E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:45-50`.

2. `ProteinTranslocation` — Python allocator/request vector is ATP-only, while Karr extract explicitly includes ATP+GTP requirement and H2O update.
   - Karr extract simulation algorithm states to calculate ATP and GTP requirement, then update ATP/GTP/ADP/GDP/Pi/H2O/H+.  
     Evidence: `docs/karr_extracts/process/22_ProteinTranslocation.md:122-125`.
   - Python consumer enrollment and request calculator expose only `ATP` for `karr_protein_translocation`.  
     Evidence: `opencell/vivarium/karr_composite.py:1394`, `opencell/vivarium/karr_request_calculators.py:507-513`.
   - Reducer cross-reference: no matching `blocks_b1` entry found in `bugs_to_fix.md` (new L3 candidate).

## L4 hot list (key-identity consistency)

1. `MacromolecularComplexation` default-key drift (`d2_real` vs `karr_macromolecular_complexation`).
   - Allocator defaults still define D2 consumer key as `d2_real`.  
     Evidence: `opencell/vivarium/karr_allocation_step.py:67`.
   - Process and request-calculator both use `karr_macromolecular_complexation`.  
     Evidence: `opencell/vivarium/karr_macromolecular_complexation.py:152,185-189`; `opencell/vivarium/karr_request_calculators.py:54-57,63`.
   - Result: mismatch confirmed in default-key path (MEDIUM).
   - Reducer cross-reference: no direct `bugs_to_fix.md` entry for this key-identity seam.

2. `ProteinDecay` default-key drift (`protein_decay_light` vs `karr_protein_decay_light`).
   - Allocator defaults use `protein_decay_light`.  
     Evidence: `opencell/vivarium/karr_allocation_step.py:68`.
   - Process and request-calculator use `karr_protein_decay_light`.  
     Evidence: `opencell/vivarium/karr_protein_decay_light.py:54,171-173`; `opencell/vivarium/karr_request_calculators.py:88-90,127-129`.
   - Result: mismatch confirmed (MEDIUM).
   - Reducer cross-reference: `E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:149-154`.

## L6 hot list (request-calculator correctness)

1. `MacromolecularComplexation` consumes substrates but request calculator is hard-zero.
   - RequestCalculatorD2 is explicitly zero-demand by design and returns zero vector each tick.  
     Evidence: `opencell/vivarium/karr_request_calculators.py:30-32,61-63`.
   - Process performs direct substrate consumption (`delta_substrates`) from shared substrate counts.  
     Evidence: `opencell/vivarium/karr_macromolecular_complexation.py:205-209,236-242`.
   - Result: consume-without-demand mismatch confirmed (HIGH).
   - Reducer cross-reference: `E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:53-58`.

## Critique verification report (seeded predictions)

1. **DNASupercoiling H2O omission**: **confirmed**.
   - Seed was stated in critique (`allocator enrollment ATP-only, omitting H2O`).  
     Evidence: `E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/gpt55_critique.md:16`.
   - Code evidence aligns with seed: ATP-only request/enrollment path.  
     Evidence: `opencell/vivarium/karr_dna_supercoiling.py:190-193`; `opencell/vivarium/karr_composite.py:1397`.

2. **ProteinDecay key mismatch**: **confirmed**.
   - Seeded mismatch in critique.  
     Evidence: `E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/gpt55_critique.md:18`.
   - Code evidence confirms default mismatch (`protein_decay_light` vs `karr_protein_decay_light`).  
     Evidence: `opencell/vivarium/karr_allocation_step.py:68`; `opencell/vivarium/karr_protein_decay_light.py:54`.

3. **MacromolecularComplexation zero-demand despite consumption**: **confirmed**.
   - Seeded in critique.  
     Evidence: `E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/gpt55_critique.md:18`.
   - Code evidence confirms hard-zero calculator + direct substrate deltas in process.  
     Evidence: `opencell/vivarium/karr_request_calculators.py:30-32,61-63`; `opencell/vivarium/karr_macromolecular_complexation.py:236-242`.

## Vocabulary status
- `mismatch_confirmed`: `DNASupercoiling` (L3), `ProteinTranslocation` (L3), `MacromolecularComplexation` (L4/L6), `ProteinDecay` (L4).
- `mismatch_absent`: no additional HIGH findings beyond the hot lists above in enrolled consumers.
- `evidence_missing`: MATLAB-side exact substrate universes remain underspecified for several non-enrolled processes (`DNADamage`, `Metabolism`, `Transcription`, `Translation`) because those paths are primarily L2 topology defects, not allocator-vector defects.

## Open questions
1. Should L4 be evaluated against allocator **defaults** only, or against the effective chassis `consumer_processes` override? Current matrix records both behaviorally (v5/v6 override mostly consistent) and default-contract drift.
2. For L3 scoring in non-enrolled direct-writer processes (`Transcription`, `Translation`, `Metabolism`, `DNADamage`), should those rows remain `N/A` under this layer by policy, or be force-classified as `HIGH` despite being owned by L2?
