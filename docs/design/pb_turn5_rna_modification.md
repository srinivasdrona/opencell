# Phase B Turn 5 — RNAModification

**Status**: design ready · **Estimated wall**: 30 min · **Karr process**: `Process_RNAModification`

## Why this is Phase B Turn 5

Completes the RNA maturation pathway after Processing. Adds the 13 modification enzymes (methylation, pseudouridylation, lysidine, sulfur transfer) that mature rRNA + tRNA bases before they're catalytically active.

Per docstring lines 38-43:
- **91 modification reactions** across 38 RNAs (each RNA: 1-7 reactions)
- **13 enzymes**: methyltransferases, pseudouridine synthases, lysidine synthetase, sulfur transferases, uridine 5-carboxymethylaminomethyl modifier
- For an RNA to be "fully modified", ALL its required reactions must complete (rule from docstring lines 71-72)

## Algorithm: ReactionProcess pattern (identical to T1 + T4)

Same deterministic + stochastic two-phase flow as tRNAAminoacylation and RNAProcessing. Reuse helpers.

**Key constraint** (per docstring lines 71-72): an RNA only transitions from "unmodified" to "modified" state when ALL required modifications have happened. This adds a per-RNA reaction-completion check. Either:
- (a) Track per-RNA per-reaction completion state (heavyweight)
- (b) Compute reactions in bulk; an RNA stays unmodified until its full reaction count is reached (Karr's actual approach)

Pick (b): a counter `n_completed_modifications[rna]` tracks how many of its required reactions have happened. When it reaches the count from `reactionModificationMatrix.sum(axis=0)[rna]`, the RNA transitions to modified.

## Empirical fixture findings

Fixture: `data/karr_fixtures/per_process/RNAModification_flat.mat`. Expected:
- `reactionStoichiometryMatrix`: ~50 substrates × 91 reactions (methyl donors, ATP, sulfur, etc.)
- `reactionCatalysisMatrix`: 91 reactions × 13 enzymes
- `reactionModificationMatrix`: 91 reactions × 38 RNAs (sparse; sum per column = required reactions for that RNA)
- `enzymeBounds`: kcat per reaction
- `unmodifiedRNAWholeCellModelIDs` (38), `modifiedRNAWholeCellModelIDs` (38)

## Vivarium chassis integration

Same pattern as T4. Ports schema mirrors RNAProcessing with the difference that the modification process tracks a per-RNA "reactions completed" counter as internal state (NOT exposed as a Vivarium store — purely process-local since no other process reads it).

```python
class KarrRNAModificationProcess(Process):
    name = "karr_rna_modification"
    
    def __init__(self, params):
        super().__init__(params)
        # Internal state: number of completed reactions per unmodified RNA
        # Reset between unmodified -> modified transitions
        self._n_completed = np.zeros(len(self.unmodified_rna_wids), dtype=np.int64)
        self._required_reactions_per_rna = self.reaction_modification.sum(axis=0)  # per RNA
    
    def next_update(self, timestep, states):
        # 1. Compute reactions executable from substrates + enzymes + unmodified RNAs available
        # 2. Stochastically sample reactions
        # 3. Increment _n_completed[rna] by reactions affecting that RNA
        # 4. For RNAs where _n_completed[rna] >= required_reactions[rna]:
        #    - Emit -1 to unmodified, +1 to modified
        #    - Reset _n_completed[rna] = 0
        # 5. Emit substrate deltas
        ...
```

**Note on internal state**: stored as process attribute, NOT in the Vivarium store. This means:
- It's not visible to other processes (acceptable — no other process reads it)
- It's not persisted across Engine restart (acceptable — restart = reset to all-unmodified state, equivalent to Karr's initialization)
- It's not deterministic across parallel runs of the same chassis (acceptable — both runs start with `_n_completed = 0`)

## Scope

**Net new files**:
1. `opencell/vivarium/karr_rna_modification.py` (~220 LOC)
2. `tests/vivarium/test_karr_rna_modification.py` (~160 LOC)

**Modified files**: NONE.

## Test plan

1. **test_fixture_loads**: 13 enzymes, 91 reactions, 38 RNAs
2. **test_no_unmodified_no_action**: zero unmodified RNAs → empty update
3. **test_required_reactions_per_rna**: per-RNA reaction count from fixture matches 1-7 range
4. **test_mass_conservation**: substrate consumption matches reaction stoichiometry
5. **test_full_modification_transitions_state**: with enough substrates+enzymes, after N ticks an unmodified RNA's `_n_completed` reaches `required_reactions[rna]` and unmod -> mod transition happens
6. **test_partial_modification_no_transition**: with substrate scarcity (only some reactions can complete), no unmod -> mod transition, `_n_completed` stays partial
7. **test_deterministic_with_seed**: same seed + same state → bit-identical output
8. **test_integration_with_chassis_v3** (SKIP unless chassis available): can the chassis_v4 builder wire this in alongside processing? Test the wiring path.

## Acceptance criteria

- All 7 (+1 skip) tests pass
- No regressions
- Commit: `pb-t5: RNAModification (per-RNA completion-counter scheme)`

## Out of scope

- Cofactor explicit modeling (assume always available; per Karr's simplification)
- Wiring into chassis_v4 builder (separate turn)
- Modeling reverse reactions (modification is irreversible per Karr)

## Pattern locked in after T5

After Phases B T1 + T4 + T5, the `ReactionProcess` pattern is fully established:
- tRNAAminoacylation: aminoacylation reactions
- RNAProcessing: cleavage reactions
- RNAModification: modification reactions (with per-RNA completion counter)

Subsequent Phase B processes (ProteinProcessingI/II, ProteinModification, etc.) will follow the same template. This will accelerate T6-T11 wall-time substantially.
