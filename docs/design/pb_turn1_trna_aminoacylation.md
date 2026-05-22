# Phase B Turn 1 — tRNAAminoacylation

**Status**: design ready · **Estimated wall**: 45 min · **Karr process**: `Process_tRNAAminoacylation` · **Functional area**: RNA-synthesis-and-maturation

## Why this is Phase B's first module

After A3.3 closes the M1+M2+M3+D.2+ProteinDecay chassis, the natural next process is tRNAAminoacylation because:

1. **Smallest, self-contained**: 39 reactions, 30 substrates, 21 enzymes, 37 t(m)RNAs. Smaller scope than any Phase C process.
2. **Clear interface to existing M3v3 (translation)**: M3 currently assumes a fixed supply of charged tRNAs; aminoacylation provides that supply dynamically. Closes one of M3's hardcoded assumptions.
3. **Forces the causal-ordering deviation explicit**: aminoacylation MUST happen before translation reads charged tRNAs within a tick to be Karr-faithful. Phase A3.3's all-accumulate decision introduced a 1-tick lag. This is the test of whether the lag matters at Δt=1s. If steady-state charged-tRNA fraction matches Karr's reported ~67% (per `initializeState`: 2/3 of tRNAs are charged), the lag is acceptable.
4. **Demonstrates the broader "ReactionProcess" pattern**: tRNAAminoacylation is one of ~7 Karr processes that inherit from `ReactionProcess` (a reaction-stoichiometry + enzyme-kinetics base class). Building this one establishes the pattern for the rest.

## Empirical fixture findings

Loading `data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat`:

```
data.fixture:
  reactionStoichiometryMatrix:   (30, 39) int16   - 30 metabolites × 39 reactions
  reactionCatalysisMatrix:        (39, 21) uint8   - reactions × enzymes (sparse, binary)
  reactionModificationMatrix:     (39, 37) uint8   - reactions × tRNA targets (sparse, binary)
  enzymeBounds:                   (39, 2)  float64 - per-reaction kcat (lower=0, upper=kcat)
  freeRNAWholeCellModelIDs:       (37, 1)  obj     - 36 free tRNAs + 1 free tmRNA
  aminoacylatedRNAWholeCellModelIDs: (37, 1) obj   - 36 charged tRNAs + 1 charged tmRNA
  substrateWholeCellModelIDs:     (30, 1)  obj     - 20 AAs + 10 metabolites (ATP, AMP, ADP, PPi, Pi, H2O, H+, fTHF10, THF + 1 other)
  enzymeWholeCellModelIDs:        (58, 1)  obj     - aminoacyl-tRNA synthetases (21) + supportive enzymes
  reactionIndexs_aminoacylation:  37 reaction indices (37 of 39 reactions are aminoacylations)
  reactionIndexs_transfer:        2 reaction indices (glutamyl amidotransfer + methionyl formyltransfer)
  speciesReactantMatrix, speciesReactantByproductMatrix: (37, 88) - pre-computed for evolveState
```

37 aminoacylation reactions + 2 transfer reactions = 39 total. Confirmed against the docstring's claim.

## Karr's algorithm (from `evolveState` at lines 387-462)

```matlab
function evolveState(this)
    if ~any(this.freeRNAs)  % terminate early if no free RNAs
        return;
    end

    % Step 1: Deterministic allocation
    %   For each amino-acid type, charge up to min(free_tRNAs_for_that_AA, AA_supply)
    %   tRNAs proportionally split across tRNAs that use the same AA

    % Step 2: Stochastic residual allocation
    %   While substrates remain AND uncharged tRNAs remain AND enzymes available:
    %     - Compute per-reaction limits from substrate / enzyme / freeRNA availability
    %     - Sample a reaction weighted by limits
    %     - Execute one charging event
    %     - Update substrates, enzymes, freeRNAs

    % Step 3: Apply final state changes
    substrate_delta = -reactionStoichiometryMatrix @ reactionModificationMatrix @ reactionFluxes
    freeRNAs        -= reactionFluxes
    aminoacylatedRNAs = freeRNAs_consumed (via reactionModificationMatrix)
end
```

The deterministic-then-stochastic pattern matches Karr's own commentary in the docstring (lines 76-90): "1. Deterministically activate tRNAs up to the minimum of free tRNAs and amino acids... 2. Stochastically activate residual tRNAs using residual amino acids."

## Vivarium chassis integration

### Class: `KarrTRNAAminoacylationProcess(Process)`

```python
name = "karr_trna_aminoacylation"
defaults = {
    "fixture_path": "data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat",
    "rng_seed": 0,
    "time_step": 1.0,
}
```

### ports_schema

```python
{
    "substrates": {wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                   for wid in self.substrate_wids},  # 30 WIDs (AAs + metabolites)
    "rna": {
        "counts": {
            # Both free and charged tRNAs in the same flat WID space
            **{wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
               for wid in self.free_rna_wids},        # 37 free t/tm-RNAs
            **{wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
               for wid in self.aminoacylated_rna_wids},  # 37 charged t/tm-RNAs
        }
    },
    "protein": {
        "counts": {wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                   for wid in self.enzyme_wids},      # 58 synthetase + helper enzymes
    },
    "requests": {
        "karr_trna_aminoacylation": {
            wid: {"_default": 0.0, "_updater": "set", "_emit": False}
            for wid in self.substrate_wids  # request all 30 metabolites
        }
    },
    "substrates_allocated": {
        "karr_trna_aminoacylation": {
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
            for wid in self.substrate_wids
        }
    },
}
```

### next_update (Karr's deterministic + stochastic two-phase)

```python
def next_update(self, timestep, states):
    free_rna = np.array([states["rna"]["counts"][w] for w in self.free_rna_wids])
    charged_rna = np.array([states["rna"]["counts"][w] for w in self.aminoacylated_rna_wids])
    substrates = np.array([states["substrates_allocated"]["karr_trna_aminoacylation"][w]
                            or states["substrates"][w] for w in self.substrate_wids])
    enzymes = np.array([states["protein"]["counts"][w] for w in self.enzyme_wids])
    
    if free_rna.sum() == 0:
        return {}  # no free tRNAs, nothing to do
    
    reaction_fluxes = self._compute_reaction_fluxes(
        free_rna, substrates, enzymes, timestep
    )
    
    # Apply: substrate delta = -stoich @ mod @ flux
    sub_delta = -(self.reaction_stoich @ self.reaction_modification @ reaction_fluxes)
    rna_delta = -reaction_fluxes  # free tRNAs decrease
    charged_delta = self.reaction_modification.T @ reaction_fluxes  # charged increases
    
    return {
        "substrates": {wid: float(sub_delta[i])
                       for i, wid in enumerate(self.substrate_wids) if sub_delta[i] != 0},
        "rna": {"counts": {
            **{wid: float(rna_delta[i])
               for i, wid in enumerate(self.free_rna_wids) if rna_delta[i] != 0},
            **{wid: float(charged_delta[i])
               for i, wid in enumerate(self.aminoacylated_rna_wids) if charged_delta[i] != 0},
        }},
    }


def _compute_reaction_fluxes(self, free_rna, substrates, enzymes, dt):
    """Karr's deterministic + stochastic flow."""
    # Phase 1: deterministic allocation
    # For each reaction: max_possible = min over (substrate_availability, enzyme_availability, free_rna)
    rxn_substrate_limit = self._substrate_limit(substrates)         # per-reaction
    rxn_enzyme_limit = self._enzyme_limit(enzymes, dt)              # per-reaction
    rxn_free_rna_limit = self.reaction_modification @ free_rna      # per-reaction
    
    deterministic_flux = np.floor(np.minimum.reduce([
        rxn_substrate_limit, rxn_enzyme_limit, rxn_free_rna_limit
    ])).astype(np.int64)
    
    # Phase 2: stochastic residual
    # While there are residuals (substrate, enzyme, or freeRNA capacity remaining):
    #   Sample reaction proportional to current limits
    #   Execute one event, update residuals
    fluxes = deterministic_flux.copy()
    # ... while loop with bounded iterations
    
    return fluxes
```

## Scope

**Net new files**:
1. `opencell/vivarium/karr_trna_aminoacylation.py` (~250 LOC)
2. `tests/vivarium/test_karr_trna_aminoacylation.py` (~200 LOC)

**Modified files**: NONE in this turn.

## Test plan

1. **test_fixture_loads**: 30 substrates, 39 reactions, 37 free+37 charged RNAs, 58 enzymes
2. **test_no_free_rna_no_action**: all free_rna = 0 → empty update
3. **test_mass_conservation**: substrate consumption matches reactionStoichiometry @ reactionModification @ fluxes
4. **test_steady_state_fraction**: from snapshot state, after 100 ticks, ~67% of tRNAs are charged (Karr's `initializeState` sets 2/3 charged)
5. **test_deterministic_phase_only**: with rng_seed forced + Phase 2 disabled, output bit-identical
6. **test_atp_consumption**: each aminoacylation costs 1 ATP (per docstring); 100 chargings → 100 ATP consumed
7. **test_enzyme_limit_kicks_in**: starve enzymes → flux limited by enzyme capacity, not substrate
8. **test_integration_with_chassis_v3** (SKIP if not on main): use pytest.importorskip; will be enabled in chassis_v4 build

## Causal-ordering verification

Add a special test:

9. **test_within_tick_lag_at_dt_1s**: run chassis_v3 + aminoacylation for 100 ticks at Δt=1s, measure the steady-state charged-tRNA fraction. Compare against Karr's published ~67% (or whatever the snapshot says). If within 5%, the 1-tick lag is acceptable at Δt=1s. If divergent, design v2 needs to address.

This test is the empirical answer to the deviation-from-Karr concern logged in `vivarium-all-accumulate-no-set` decision.

## Acceptance criteria

- All 8 (or 9 with chassis available) tests pass
- Targeted test runtime < 30s
- Commit: `pb-t1: tRNAAminoacylation (Karr's deterministic + stochastic flow)`
- STATUS reports: charged-tRNA steady-state fraction, ATP consumption rate per tick

## Out of scope

- Wiring into chassis_v3 (`build_karr_chassis_v4` is a separate turn after Phase B's first 3 processes)
- The 2 transfer reactions' special handling (`reactionIndexs_glutamylamidotransfer`, `reactionIndexs_methionylformyltransfer`) — implement as standard reactions for now; verify against Karr's special-cased stoichiometry in lines 266-269 of the .m
- Modeling tmRNA stalled-ribosome rescue dynamics (tmRNA exists in our universe but its rescue role isn't exercised until full Translation is built)

## Codex delegation

Single turn, 45 min wall. Worktree: `agent/pb-t1-trna-aminoacylation`.

When T5 (A3.3 final) is merged and verified, launch this immediately.

## Phase B subsequent turns (preview)

- **pb-t2**: RibosomeAssembly (full, with the 6 GTPases) — replaces D.2-real's 2 ribosomal complexes with proper assembly kinetics
- **pb-t3**: TranscriptionalRegulation — adds feedback into M2v3's transcription rates
- **pb-t4**: RNAProcessing (pre-rRNA, pre-tRNA cleavage)
- **pb-t5**: RNAModification (methylation, pseudouridylation)
- **pb-t6 through pb-t10**: remaining maturation processes
- **pb-final**: `build_karr_chassis_v4` that integrates all Phase B processes + ratchet-closure validation across the full RNA/protein maturation pathway
