# Phase B Turn 10 — ProteinTranslocation

**Status**: design ready · **Estimated wall**: 35 min · **Karr process**: `Process_ProteinTranslocation`

## Why this is Phase B Turn 10

Translocation moves **117 integral membrane / lipoproteins / extracellular proteins** through the SecA-translocase pore via ATP-dependent step-wise mechanism. This is the **first Phase B process with explicit compartment routing** (cytoplasm → membrane / extracellular).

Per docstring lines 22-33:
- 3 destinations: integral membrane, lipoprotein-bound, extracellular
- SRP-mediated recognition for integral membrane; direct recognition for the other two
- 4 enzymes: SRP, SRP receptor, translocase ATPase, translocase pore
- ATP-dependent step-wise translocation through the pore

## Algorithm

For each tick:
1. Identify cytoplasm-located proteins that have a non-cytoplasm destination
2. Group by recognition mechanism (SRP vs direct)
3. For SRP-mediated: rate-limited by free SRP + SRP receptor + ATP
4. For direct: rate-limited by translocase ATPase + pore + ATP
5. Translocate proteins (all-or-nothing per tick; if ATP supply runs out, remaining proteins stay cytoplasmic for next tick)

## Vivarium chassis integration

**Compartment routing handled via two separate stores or a flat WID convention?** Looking at A3.3's chassis_v3: it uses flat `protein.counts.<wid>` without compartment dimension. Karr models compartments explicitly; we've been treating them implicitly (each protein lives in its "natural" compartment).

**Decision for T10**: Add a NEW store `protein.location.<wid>` that holds a string-or-enum indicating current location ("cytoplasm" | "membrane" | "extracellular"). Translocation reads this, writes the destination. Other processes (M3v3 translation, ProteinDecay-light, etc.) don't read it yet — they'll be backwards-compatible. Phase C may need updates.

Alternative: encode compartment in the WID itself (e.g., `MG_001_MEM` vs `MG_001_CYT`). Simpler but doubles the WID count. Per `migrate-by-addition-not-rewrite`, prefer additive new store.

**Pick**: separate `protein.location` store with `_updater: "set"` (single-writer = translocation process).

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/ProteinTranslocation_flat.mat`. Expected:
- 4 enzyme WIDs (SRP, SRP receptor, translocase ATPase, translocase pore)
- 117 translocatable protein WIDs
- Per-protein destination compartment flag
- ATP cost per translocation event (~5-10 ATP based on docstring "step-wise mechanism")

## Scope

**Net new files**:
1. `opencell/vivarium/karr_protein_translocation.py` (~250 LOC)
2. `tests/vivarium/test_karr_protein_translocation.py` (~180 LOC)

**Modified files**: NONE (we keep chassis_v3 untouched; chassis_v4 will wire in translocation).

## Test plan

1. test_fixture_loads (4 enzymes, 117 proteins, 3 destinations)
2. test_no_cytoplasmic_no_translocation
3. test_srp_mediated_integral_membrane_path
4. test_direct_lipoprotein_path
5. test_atp_consumption_per_translocation
6. test_srp_starvation_blocks_membrane_only (zero SRP → integral membrane proteins stuck; lipoproteins continue via direct path)
7. test_translocase_starvation_blocks_all (zero ATPase → nothing translocates)
8. test_protein_location_store_updates (verify destination compartment is set correctly)
9. test_deterministic_with_seed

## Acceptance criteria

- All 9 tests pass
- No regressions in prior phases
- Commit: `pb-t10: ProteinTranslocation (SRP + direct path, compartment routing)`

## Out of scope

- Detailed pore conformational changes
- Modeling membrane lipid bilayer composition
- Wiring into chassis_v4 (separate turn)
- ProteinProcessingII-coupled signal cleavage (already in T7; this turn only does the translocation itself)
