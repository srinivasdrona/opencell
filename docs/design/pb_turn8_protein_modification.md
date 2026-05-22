# Phase B Turn 8 — ProteinModification

**Status**: design ready · **Estimated wall**: 25 min · **Karr process**: `Process_ProteinModification`

## Why this is Phase B Turn 8

Per docstring lines 35-37: 20 protein species modified at 63 sites by **3 enzymes**:
- Serine/threonine protein kinase (MG_109)
- Lipoate ligase
- Alpha-glutamate ligase

Mechanism: covalent modification (phosphorylation, lipoate attachment, glutamate attachment) at specific sites. Multiple sites per protein → reuse the per-protein completion-counter pattern from T5/T7.

## Algorithm

Same ReactionProcess pattern + internal completion counter (T5/T7 pattern):
1. Compute max executable reactions from substrate (ATP for kinase, lipoate, glutamate) + enzyme + unmodified protein availability
2. Stochastically select reactions weighted by per-reaction limits
3. Increment per-protein `_n_completed_modifications` counter
4. When `_n_completed[protein] >= required_modifications[protein]`: emit -1 unmodified, +1 modified, reset counter

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/ProteinModification_flat.mat`. Expected:
- ~63 modification reactions × ~20 protein species
- 3 enzymes
- Per-protein required modifications count (from reactionModificationMatrix.sum(axis=0))

## Scope

**Net new files**:
1. `opencell/vivarium/karr_protein_modification.py` (~200 LOC; reuse helpers from T5)
2. `tests/vivarium/test_karr_protein_modification.py` (~140 LOC)

**Modified files**: NONE.

## Test plan

1. test_fixture_loads (3 enzymes, ~63 reactions, ~20 proteins)
2. test_no_unmodified_no_action
3. test_required_modifications_per_protein (1-7 per protein expected)
4. test_full_modification_transitions (with enzyme + substrate excess, eventually unmod → mod)
5. test_partial_modification_no_transition (substrate scarcity → counter advances, no transition)
6. test_mass_conservation (ATP/lipoate/glutamate consumption matches stoichiometry)
7. test_deterministic_with_seed

## Acceptance criteria

- All 7 tests pass
- No regressions in prior phases
- Commit: `pb-t8: ProteinModification (3-enzyme covalent modification + counter)`

## Out of scope

- Reverse reactions (modification is irreversible per Karr)
- Wiring into chassis_v4
