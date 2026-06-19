# H3_REPORT

## Scope
- Harness-only change in `tests/vivarium/l2_replay_common.py` (`_set_enzyme_vector`).
- Added process-aware shadow-write of enzyme overlays into `protein.enzyme_counts` when that store exists in the process state schema, while preserving existing writes to `protein.counts` / `complex.counts`.

## Verify-before-commit Results

### (a) No-regression on 8 current GREENs
- Command: `python -m pytest tests/vivarium/test_karr_cytokinesis_l2_replay.py tests/vivarium/test_karr_macromolecular_complexation_l2_replay.py tests/vivarium/test_karr_chromosome_segregation_l2_replay.py tests/vivarium/test_karr_host_interaction_l2_replay.py tests/vivarium/test_karr_dna_damage_l2_replay.py tests/vivarium/test_karr_protein_translocation_l2_replay.py tests/vivarium/test_karr_protein_processing_i_l2_replay.py tests/vivarium/test_karr_dna_repair_l2_replay.py --tb=line -rs -q`
- Result: `8 passed` (no regression).

### (b) H3 candidate fingerprints (before vs after)
- Command: `python -m pytest tests/vivarium/test_karr_protein_folding_l2_replay.py tests/vivarium/test_karr_protein_processing_ii_l2_replay.py tests/vivarium/test_karr_rna_modification_l2_replay.py --tb=line -rs -q`

| Process | Before | After | Delta |
|---|---|---|---|
| ProteinFolding | `tick=2, observable=foldedMonomers, index=429, oc_val=0.0, karr_val=1.0, diff=-1.0` | same | no shift |
| ProteinProcessingII | `tick=2, observable=processedMonomers, index=429, oc_val=0.0, karr_val=1.0, diff=-1.0` | same | no shift |
| RNAModification | `tick=6, observable=substrates, index=2, oc_val=2.0, karr_val=1.0, diff=+1.0` | same | no shift |

## Additional fingerprint changes
- None observed in executed verification set.
- The 8 previously GREEN processes stayed GREEN; no new first-fail signatures were introduced in those tests.

## MATLAB context for `protein.enzyme_counts`
- In MATLAB, process enzyme vectors are assembled from simulation state (`monomer.counts` and `complex.counts`) via `Process.copyFromState -> copyEnzymesFromState`:
  - `/mnt/e/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m:476-483`
  - `/mnt/e/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m:666-676`
- Enzyme vectors are written back to monomer/complex count state in `copyToState`:
  - `/mnt/e/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m:739-749`
- ProteinProcessingI/II consume enzyme activity from `this.enzymes(...)` directly:
  - `/mnt/e/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingI.m:237-240`
  - `/mnt/e/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingII.m:365-375`

Interpretation: harness `protein.enzyme_counts` is a process-side projection corresponding to the monomer-backed enzyme portion of MATLAB process enzyme state (with complex-backed enzymes remaining in `complex.counts`).

## Verdict
- **H3 refuted for the three target residues in this branch state.**
- The shadow-write change is safe (no regressions in the 8 GREEN gate), but it did not close or shift the candidate first-fail fingerprints.
- Newly GREEN among the 3 H3 candidates: **none**.
