# Phase B Turn 9 — ProteinFolding

**Status**: design ready · **Estimated wall**: 30 min · **Karr process**: `Process_ProteinFolding`

## Why this is Phase B Turn 9

Per Karr's docstring (read the actual extract at `docs/karr_extracts/process/19_ProteinFolding.md`), this is a more complex process than the others because:

1. **85 proteins bind inorganic ions** (Zn, Mg, Fe, etc.) at specific sites — co-factor binding
2. **64 proteins fold with chaperone assistance** (DnaJ, DnaK, GroEL, GroES, GrpE)
3. **All proteins require trigger factor** for proper folding
4. **Chaperone-mediated folding consumes ATP** (each cycle through GroEL/GroES)

This is the FIRST Phase B process that requires multiple state variables across multiple sub-mechanisms (ion binding + chaperone folding). The complexity warrants slightly more design care than T6-T8.

## Algorithm sketch

Per docstring (verify at implementation):

```
Phase 1: ion binding
  For each "ion-binding-required" protein P:
    if all required ions available AND P is unbound:
      bind ions to P (decrement ion counts, mark P as ion-bound)

Phase 2: chaperone folding
  For each "chaperone-required" protein P (subset of ion-bound where needed):
    Compute max foldings = min(
      free trigger factor,
      free DnaJ, free DnaK, free GroEL, free GroES,
      ATP allocation,
      unmodified count for P
    )
    Stochastically select proteins to fold
    Consume ATP per folding cycle (typically 4-8 ATP per GroEL cycle)
    Emit: -unfolded, +folded
```

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/ProteinFolding_flat.mat`. Expected fields:
- `ionBindingMatrix`: which proteins need which ions
- `chaperoneRequirements`: per-protein chaperone needs (binary or weighted)
- ~85 proteins with ion needs; ~64 chaperone-dependent; ~482 total monomers
- 5 chaperone enzyme WIDs + trigger factor WID

## Scope

**Net new files**:
1. `opencell/vivarium/karr_protein_folding.py` (~250 LOC)
2. `tests/vivarium/test_karr_protein_folding.py` (~180 LOC)

**Modified files**: NONE.

## Test plan

1. test_fixture_loads
2. test_no_unfolded_no_action
3. test_ion_binding_first_then_chaperone (two-phase ordering verified)
4. test_no_chaperones_no_folding_of_chaperone_dependent (ATP available but no DnaK → those 64 stuck)
5. test_no_ions_no_binding (Zn missing → 85 proteins stuck at ion-binding phase)
6. test_atp_consumption_per_chaperone_cycle (~4 ATP per protein per GroEL cycle)
7. test_trigger_factor_required_for_all (zero trigger factor → no folding)
8. test_deterministic_with_seed

## Acceptance criteria

- All 8 tests pass
- No regressions in prior phases
- Commit: `pb-t9: ProteinFolding (ion binding + chaperone-mediated folding)`

## Out of scope

- Misfolding kinetics (Karr models it as 0 — proteins fold deterministically given resources)
- Reverse folding / unfolding (deferred to ProteinDecay)
- Wiring into chassis_v4

## Remaining Phase B turns after T9

| Turn | Process | Complexity |
|---|---|---|
| pb-t10 | ProteinTranslocation | SecA + SecYEGDF-YidC pore; 117 membrane/extracellular proteins; ATP-dependent |
| pb-t11 | ProteinActivation | Activation reactions for selected enzymes (small scope) |
| pb-final | build_karr_chassis_v4 | Full Phase B integration + extended ratchet validation |
