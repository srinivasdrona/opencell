# Phase B Turn 6 — ProteinProcessingI

**Status**: design ready · **Estimated wall**: 25 min · **Karr process**: `Process_ProteinProcessingI`

## Why this is Phase B Turn 6

After Phase B T1-T5 establish the ReactionProcess pattern and the protein synthesis pathway through translation + complex assembly, ProteinProcessingI runs the **N-terminal deformylation + methionine cleavage** maturation on freshly-translated proteins.

Per docstring lines 22-26 + lines 75-83:
- **2 enzymes**: peptide deformylase (MG_106), methionine aminopeptidase (MG_172)
- **All-or-nothing per protein per tick** (matches Karr's "complete within a single time step" simplification)
- ~7% of proteins require methionine cleavage; 100% require deformylation
- Algorithm: max-rate computation + stochastic selection (same template as T1, T4, T5)

## Algorithm

Per docstring §Simulation (lines 75-83):
1. Compute max processable peptides from enzyme availability
2. Stochastically select peptides to process, weighted by per-species counts
3. Update enzymes (consumption per cleavage), substrates (water for cleavage, formate released), unprocessedMonomers (-1), processedMonomers (+1)

This is mechanically identical to RNAProcessing's algorithm with peptides instead of RNAs. The only special bit is the `nascentMonomerNTerminalMethionineCleavages` boolean mask determining which proteins need methionine cleavage (the rest only need deformylation).

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/ProteinProcessingI_flat.mat`. Expected:
- `unprocessedMonomerWholeCellModelIDs` + `processedMonomerWholeCellModelIDs` (~482 each)
- `nascentMonomerNTerminalMethionineCleavages` (boolean mask, ~7% True)
- `enzymeWholeCellModelIDs` (2: MG_106 deformylase + MG_172 methionine aminopeptidase)
- `reactionStoichiometryMatrix`, `reactionCatalysisMatrix`, `enzymeBounds`

## Scope

**Net new files**:
1. `opencell/vivarium/karr_protein_processing_i.py` (~180 LOC; copy-adapt from `karr_rna_processing.py`)
2. `tests/vivarium/test_karr_protein_processing_i.py` (~140 LOC)

**Modified files**: NONE.

## Test plan

1. test_fixture_loads (2 enzymes, ~482 monomers, ~34 with met-cleavage flag)
2. test_no_unprocessed_no_action
3. test_deformylase_always_required (100% of nascent peptides need deformylation)
4. test_met_cleavage_subset (~7% need additional methionine cleavage per boolean mask)
5. test_mass_conservation (water consumption, formate release, methionine release for cleaved subset)
6. test_enzyme_kinetics_limit (low enzyme → limited flux)
7. test_deterministic_with_seed

## Acceptance criteria

- All 7 tests pass
- No regressions in Phase A3.3 (32 tests), Phase B T1-T5
- Commit: `pb-t6: ProteinProcessingI (deformylation + N-Met cleavage)`

## Out of scope

- Multi-enzyme cofactors (assume always available per Karr)
- Wiring into chassis_v4 (separate turn)
