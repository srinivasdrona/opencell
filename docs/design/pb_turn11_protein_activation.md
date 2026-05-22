# Phase B Turn 11 — ProteinActivation

**Status**: design ready · **Estimated wall**: 20 min · **Karr process**: `Process_ProteinActivation`

## Why this is Phase B Turn 11

Smallest Phase B process. Per docstring lines 39-47: **6 proteins** with boolean activation rules tied to metabolite/stimulus levels. Activates/deactivates proteins based on environmental signals. Mostly bookkeeping — no kinetics, no Monte Carlo.

The 6 proteins:
- MG_085_HEXAMER (HPr kinase/phosphatase)
- MG_101_MONOMER (HTH-type TF)
- MG_127_MONOMER (Spx subfamily)
- MG_205_DIMER (HrcA heat-shock repressor)
- MG_236_MONOMER (ferric uptake repressor)
- MG_409_DIMER (PhoU phosphate transport regulator)

Each has a boolean rule like "active if [HMP-Ser] > threshold AND [ATP/ADP] < threshold". When the rule evaluates True, the protein is in `matureMonomers` state; False puts it in `inactiveMonomers`. State transitions are tick-by-tick based on current metabolite/stimulus state.

## Algorithm

```
For each regulated protein P:
  Read current substrate/stimulus concentrations
  Evaluate boolean rule R(P) (compiled at __init__ from fixture)
  If R(P) and P is currently inactive: transition inactive -> active
  If !R(P) and P is currently active: transition active -> inactive
```

No randomness, no kinetics, no ATP cost. Just rule evaluation + state transition.

## Vivarium chassis integration

**New store**: `protein.activity.<wid>` (boolean 0/1) for the 6 regulated proteins. Single-writer = ProteinActivation. Other processes that need "active enzyme count" can read this.

**Updater**: `_updater: "set"` (single writer, full overwrite each tick).

For the boolean rules: store as Python callables at __init__ time, parsed from the fixture's rule strings. Each rule maps a dict of substrate/stimulus counts → bool.

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/ProteinActivation_flat.mat`. Expected:
- 6 regulated protein WIDs
- 6 boolean rules as text strings (or pre-compiled expression trees)
- List of substrates/stimuli referenced by rules

## Scope

**Net new files**:
1. `opencell/vivarium/karr_protein_activation.py` (~150 LOC; smaller because no kinetics)
2. `tests/vivarium/test_karr_protein_activation.py` (~120 LOC)

**Modified files**: NONE.

## Test plan

1. test_fixture_loads (6 rules)
2. test_unregulated_proteins_unaffected
3. test_high_metabolite_activates (e.g., HrcA active when heat-shock stimulus high)
4. test_low_metabolite_deactivates
5. test_rule_evaluation_per_tick (state transitions only when rule output changes)
6. test_no_random_no_seed_dependence (rules are deterministic)
7. test_activation_state_emitted (the new store emits correctly)

## Acceptance criteria

- All 7 tests pass
- No regressions in prior phases
- Commit: `pb-t11: ProteinActivation (boolean-rule activation/deactivation)`

## Out of scope

- Rule learning / rule-from-data (Karr hardcodes them from literature)
- Multi-tick rule history (rules use current-tick state only)
- Wiring into chassis_v4 (separate turn)

## Phase B nearly complete

After T11, only the final chassis_v4 integration remains. All 11 Phase B processes will be shipped:
- T1 tRNAAminoacylation ✅ MERGED
- T2 RibosomeAssembly 🟡 in flight
- T3 TranscriptionalRegulation 🟡 in flight
- T4 RNAProcessing 🟡 in flight
- T5 RNAModification 🟡 in flight
- T6 ProteinProcessingI ⏳ designed
- T7 ProteinProcessingII ⏳ designed
- T8 ProteinModification ⏳ designed
- T9 ProteinFolding ⏳ designed
- T10 ProteinTranslocation ⏳ designed
- T11 ProteinActivation ⏳ designed
- pb-final: chassis_v4 integration ⏳ next
