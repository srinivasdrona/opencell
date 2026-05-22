# Phase C Turn 1 — ReplicationInitiation

**Status**: design ready · **Estimated wall**: 40 min · **Karr process**: `Process_ReplicationInitiation`

## Why this is Phase C Turn 1

ReplicationInitiation is the **gateway** to all of Phase C: it decides WHEN replication starts based on DnaA-ATP polymer state at the OriC. Without this process firing, the rest of Phase C (Replication, Supercoiling, Condensation, Segregation, Cytokinesis) never activate.

Per docstring lines 25-30:
- ~30 DnaA molecules form polymers at OriC sites R1-R5
- ~2000 additional DnaA boxes throughout the chromosome (titration effect)
- Initiation triggers ~2/3 through the cell cycle (robust timing control)
- Requires the chromosome to be supercoiled (couples to DNASupercoiling later)

This is the FIRST Phase C process with explicit chromosomal-position state. Tests the architecture for long-timescale discrete events.

## Algorithm (per docstring §Simulation, lines 79-112)

Ordered sub-steps each tick (deterministic order):

1. **activateFreeDnaA**: free DnaA + ATP → DnaA-ATP (deterministic up to limit of available DnaA + ATP)
2. **inactivateFreeDnaAATP**: dissociate free DnaA-ATP polymers, hydrolyze ATPs (free DnaA-ATP → free DnaA-ADP + Pi)
3. **polymerizeDnaAATP**: if chromosome is supercoiled, stochastically polymerize R1-R4 OriC boxes at rate `kbATP × numFreeDnaAATP / V × C` (C = cooperativity)
4. **polymerizeDnaAADP**: similar to ATP polymerization, slower
5. **bindDnaAATP**: stochastically bind free DnaA-ATP to empty DnaA boxes at rate `kbATP × numFreeDnaAATP / V`
6. **bindDnaAADP**: similar, slower
7. **releaseDnaAATP**: stochastic release of bound DnaA-ATP with uniform probability
8. **releaseDnaAADP**: similar
9. **reactivateFreeDnaAADP**: free DnaA-ADP → free DnaA-ATP at rate `numFreeDnaAADP × (k_Regen × membraneConc) / (K_Regen_P4 + membraneConc)`

Each sub-step is its own helper method. Order matters (per docstring).

**Initiation trigger** (separate from `evolveState`): when all 5 OriC boxes (R1-R5) have a DnaA-ATP polymer of sufficient length, emit a `replication_initiation_trigger` signal. The Replication process (pc-t2) reads this signal and starts elongation.

## Vivarium chassis integration

### New stores

```python
"chromosome": {
    "dnaa_complex_count": {       # DnaA-ATP/ADP polymer per chromosomal site
        # Keys: site identifiers like "R1", "R2", "R3", "R4", "R5", "DnaA_box_001"-"DnaA_box_2000"
        # Values: int = polymer length (0 = no DnaA bound; 1+ = DnaA-ATP/ADP monomer/polymer)
        site_id: {"_default": 0, "_updater": "accumulate", "_emit": True}
        for site_id in self.all_dnaa_sites
    },
    "replication_state": {
        # "idle" | "initiating" | "elongating" | "complete"
        "_default": "idle",
        "_updater": "set",
        "_emit": True,
    },
    "supercoiled": {  # boolean read from DNASupercoiling (or default True for Phase C T1 standalone)
        "_default": True,
        "_updater": "set",
        "_emit": False,
    },
},
"protein": {
    "counts": {
        "DnaA_MG_469": {"_default": 0, "_updater": "accumulate", "_emit": True},
        # free DnaA monomer
    }
},
"substrates": {
    "ATP": {...accumulate...},  # consumed in activateFreeDnaA
    "ADP": {...accumulate...},  # product of inactivateFreeDnaAATP
    "Pi": {...accumulate...},
    "H2O": {...accumulate...},
},
"requests": {
    "karr_replication_initiation": {
        "ATP": {"_default": 0.0, "_updater": "set"},
        "H2O": {"_default": 0.0, "_updater": "set"},
    }
},
"substrates_allocated": {
    "karr_replication_initiation": {
        "ATP": {"_default": 0.0, "_updater": "accumulate"},
        "H2O": {"_default": 0.0, "_updater": "accumulate"},
    }
},
```

### next_update structure

```python
def next_update(self, timestep, states):
    # Snapshot current state
    dnaa_polymer_counts = ...  # per-site
    free_dnaa = states["protein"]["counts"][self.dnaa_wid]
    free_atp = states["substrates_allocated"]["karr_replication_initiation"]["ATP"]
    
    # Execute the 9 sub-steps in order (each updates an internal `_state` dict
    # of pending deltas; we collect and emit at end)
    deltas = {"chromosome": defaultdict(dict), "protein": {"counts": {}}, "substrates": {}}
    
    self._activate_free_dnaa(deltas, free_dnaa, free_atp)
    self._inactivate_free_dnaa_atp(deltas)
    if states["chromosome"]["supercoiled"]:
        self._polymerize_dnaa_atp(deltas, ...)
        self._polymerize_dnaa_adp(deltas, ...)
    self._bind_dnaa_atp(deltas, ...)
    self._bind_dnaa_adp(deltas, ...)
    self._release_dnaa_atp(deltas, ...)
    self._release_dnaa_adp(deltas, ...)
    self._reactivate_free_dnaa_adp(deltas, ...)
    
    # Check for initiation trigger
    if self._check_initiation_trigger(states):
        deltas["chromosome"]["replication_state"] = "initiating"
    
    return deltas
```

## Empirical fixture findings

Inspect `data/karr_fixtures/per_process/ReplicationInitiation_flat.mat`. Expected:
- ~2005 DnaA site positions (5 OriC + ~2000 chromosomal boxes)
- DnaA WID
- Rate constants: kbATP, kbADP, kd1ATP, kd1ADP, k_Regen, K_Regen_P4
- Cooperativity constant
- DnaA polymer length thresholds for initiation

## Scope

**Net new files**:
1. `opencell/vivarium/karr_replication_initiation.py` (~280 LOC; complex due to 9 sub-steps)
2. `tests/vivarium/test_karr_replication_initiation.py` (~220 LOC)

**Modified files**: NONE.

## Test plan

1. test_fixture_loads (~2005 sites, kinetic constants present)
2. test_zero_free_dnaa_no_activity (zero DnaA → no polymerization)
3. test_activation_consumes_atp (free DnaA + ATP → DnaA-ATP; ATP decreases)
4. test_polymer_growth_at_oric (with abundant free DnaA-ATP + supercoiled chromosome, R1-R5 polymers grow over ticks)
5. test_initiation_trigger_fires (all 5 OriC boxes reach threshold polymer length → replication_state transitions idle → initiating)
6. test_titration_effect (with 2000 non-OriC sites occupied, fewer free DnaA available for OriC; initiation delayed)
7. test_no_supercoil_no_polymerization (supercoiled=False → polymerization sub-steps don't execute)
8. test_deterministic_with_seed
9. test_release_kinetics (with abundant bound DnaA-ATP, release events occur at expected rate)

## Acceptance criteria

- All 9 tests pass
- No regressions in Phase A + B (all tests still pass)
- Commit: `pc-t1: ReplicationInitiation (DnaA-ATP polymer dynamics at OriC)`
- STATUS reports: per-tick polymer growth rate, expected ticks-to-initiation under nominal conditions

## Out of scope

- Replication elongation (pc-t2)
- DNASupercoiling (pc-t3 — pc-t1 reads supercoiled as input but doesn't modify it)
- Cell-cycle reset (after replication complete, DnaA needs to dissociate; that's handled in pc-final's CellCycleCoordinator)

## Connection to existing chassis

ReplicationInitiation reads from existing M3v3 (DnaA is a protein that translates) and M1 (ATP) via the standard `protein.counts` and `substrates_allocated` ports. It writes to new `chromosome.*` stores. The chassis_v4 → chassis_v5 transition will wire it in.
