# Phase B Turn 4 — RNAProcessing

**Status**: design ready · **Estimated wall**: 30 min · **Karr process**: `Process_RNAProcessing`

## Why this is Phase B Turn 4

After tRNAAminoacylation establishes the Karr `ReactionProcess` pattern (deterministic + stochastic two-phase flow), RNAProcessing reuses the SAME pattern with a different fixture. This turn validates the pattern's transferability and ships ~9 cleavage reactions for rRNA/tRNA/scRNA precursors.

**Scope per docstring**: 5 enzymes (DeaD=MG_425, RsgA=MG_110, RNAseIII=MG_367, RNAseP=MG_0003+MG_465, RNAseJ=MG_139) cleaving polycistronic transcripts into mature 5S/16S/23S rRNAs + 36 tRNAs + 1 scRNA + 1 tmRNA.

## Algorithm: mass-action kinetics, repeated until exhausted

Per docstring §Biology (lines 35-43):
1. Calculate max maturation rate per RNA from substrate + enzyme + immature RNA availability
2. Stochastically select maturations weighted by max rates
3. Update substrates, enzymes, immature/mature RNAs
4. Repeat steps 1-3 until insufficient resources

**This is structurally identical to tRNAAminoacylation's Phase 2 (stochastic residual sampling).** Reuse the algorithm helpers from `karr_trna_aminoacylation.py` if possible.

## Empirical fixture findings

Fixture: `data/karr_fixtures/per_process/RNAProcessing_flat.mat`. Expected fields (verify at implementation time):
- `reactionStoichiometryMatrix`: ~30 substrates × ~9 reactions (cleavages)
- `reactionCatalysisMatrix`: 9 reactions × 5 enzymes
- `reactionModificationMatrix`: 9 reactions × ~80 RNA species (immature + intermediate + mature)
- `enzymeBounds`: kcat per reaction (from docstring: DeaD 1.48, RsgA 0.29, RNAseP 0.027-6, RNAseIII 7.7, RNAseJ 0.37)
- `unprocessedRNAWholeCellModelIDs`, `processedRNAWholeCellModelIDs`

## Vivarium chassis integration

### Class: `KarrRNAProcessingProcess(Process)`

```python
name = "karr_rna_processing"
defaults = {
    "fixture_path": "data/karr_fixtures/per_process/RNAProcessing_flat.mat",
    "rng_seed": 0,
    "time_step": 1.0,
}
```

### ports_schema (mirror tRNAAminoacylation pattern)

```python
{
    "substrates": {wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                   for wid in self.substrate_wids},  # ATP, GTP, Mg, Zn, AMP, water, ...
    "rna": {
        "counts": {
            # All unprocessed + processed RNAs in a flat WID space
            **{wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
               for wid in self.unprocessed_rna_wids},
            **{wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
               for wid in self.processed_rna_wids},
        }
    },
    "protein": {
        "counts": {wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                   for wid in self.enzyme_wids},  # 5 RNase enzymes (read-only)
    },
    "requests": {
        "karr_rna_processing": {
            wid: {"_default": 0.0, "_updater": "set", "_emit": False}
            for wid in self.substrate_wids
        }
    },
    "substrates_allocated": {
        "karr_rna_processing": {
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
            for wid in self.substrate_wids
        }
    },
}
```

### next_update (same pattern as tRNAAminoacylation Phase 1+2)

```python
def next_update(self, timestep, states):
    unprocessed = np.array([states["rna"]["counts"][w] for w in self.unprocessed_rna_wids])
    if unprocessed.sum() == 0:
        return {}  # no immature RNAs, nothing to do
    
    substrates = self._read_allocated_or_baseline(states, "karr_rna_processing")
    enzymes = np.array([states["protein"]["counts"][w] for w in self.enzyme_wids])
    
    reaction_fluxes = self._compute_reaction_fluxes(
        unprocessed, substrates, enzymes, timestep
    )
    
    # Mass balance
    sub_delta = -(self.reaction_stoich @ reaction_fluxes)
    
    # RNA transitions: unprocessed - flux, processed + flux (via modification matrix)
    unprocessed_delta = -(self.reaction_modification @ reaction_fluxes * IS_UNPROCESSED_MASK)
    processed_delta = +(self.reaction_modification @ reaction_fluxes * IS_PROCESSED_MASK)
    # [Details: each reaction converts one immature -> one or more mature; check matrix]
    
    return {
        "substrates": {...},
        "rna": {"counts": {...}},
    }
```

## Scope

**Net new files**:
1. `opencell/vivarium/karr_rna_processing.py` (~200 LOC; reuses tRNAAminoacylation's helpers where possible)
2. `tests/vivarium/test_karr_rna_processing.py` (~150 LOC)

**Modified files**: NONE.

## Test plan

1. **test_fixture_loads**: 5 enzymes, ~9 reactions, ~80 RNA species
2. **test_no_unprocessed_no_action**: zero immature RNAs → empty update
3. **test_mass_conservation**: substrate consumption matches reaction stoichiometry
4. **test_enzyme_kinetics**: low-kcat enzyme limits flux even with abundant substrate
5. **test_30s_cleavage_cascade**: starting from 30S precursor + RNaseIII, after one tick, intermediate 16/17S + 23S + 9S RNAs appear
6. **test_deterministic_with_seed**: same seed → bit-identical output
7. **test_no_substrate_no_action**: zero water/Mg → no cleavage
8. **test_integration_with_chassis_v3** (SKIP if not on main; gated by pytest.importorskip)

## Acceptance criteria

- All 7 (+1 skip) tests pass
- No regressions in Phase A3.3 (32 tests) or Phase B T1/T2/T3 tests
- Commit: `pb-t4: RNAProcessing (Karr mass-action cleavage kinetics)`

## Out of scope

- Cofactor (Mg2+, Zn2+, Mn2+) explicit modeling — assume always available
- Wiring into chassis_v4
