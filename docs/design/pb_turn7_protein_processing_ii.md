# Phase B Turn 7 — ProteinProcessingII

**Status**: design ready · **Estimated wall**: 25 min · **Karr process**: `Process_ProteinProcessingII`

## Why this is Phase B Turn 7

ProteinProcessingII handles **lipoprotein-specific modifications**: diacylglyceryl transfer + signal peptide cleavage. Smaller scope than ProteinProcessingI (only lipoproteins affected, ~30 of 482 monomers).

Per docstring (verify at implementation):
- **2 enzymes**: diacylglyceryl transferase, signal peptidase II
- Substrate: diacylglycerol (a lipid; from membrane biosynthesis, but here just a counted pool)
- Mechanism: bind, transfer DAG to C-terminal Cys of signal sequence, then cleave signal sequence
- All-or-nothing per protein per tick

## Algorithm

Same ReactionProcess pattern as T6.

Per-protein two-step: (a) DAG transfer (consumes diacylglycerol, adds DAG modification mark), (b) signal cleavage (consumes water, releases signal peptide fragment). Since both must happen for "mature lipoprotein" state, model as a single combined reaction per lipoprotein. The unmodified→modified state transition fires when both enzymes process the protein within the same tick (or accumulate across ticks via an internal counter, similar to RNAModification's pattern).

**Pick**: internal-counter approach (matching T5's RNAModification pattern) for the partial-modification case where DAG transfer happens this tick but cleavage doesn't.

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/ProteinProcessingII_flat.mat`. Expected:
- ~30 lipoprotein monomers
- 2 enzymes (diacylglyceryl transferase, signal peptidase II)
- ~2 reactions per lipoprotein (DAG transfer + cleavage)

## Scope

**Net new files**:
1. `opencell/vivarium/karr_protein_processing_ii.py` (~190 LOC; reuse helpers from T5 for the counter pattern)
2. `tests/vivarium/test_karr_protein_processing_ii.py` (~140 LOC)

**Modified files**: NONE.

## Test plan

1. test_fixture_loads
2. test_non_lipoprotein_unaffected
3. test_dag_transfer_then_cleave (in 1-2 ticks with both enzymes abundant, lipoprotein becomes mature)
4. test_partial_progress_no_transition (DAG transfer happens but cleavage doesn't → counter advances, no transition)
5. test_mass_conservation (DAG consumed, water consumed, signal peptide fragment released)
6. test_no_dag_no_action (zero diacylglycerol → no progress)
7. test_deterministic_with_seed

## Acceptance criteria

- All 7 tests pass
- No regressions in prior phases
- Commit: `pb-t7: ProteinProcessingII (lipoprotein DAG transfer + signal cleavage)`

## Out of scope

- Modeling diacylglycerol synthesis (assume pool exists; future Phase will wire to lipid biosynthesis)
- Signal peptide fate beyond release (deferred to degradation pathways)
