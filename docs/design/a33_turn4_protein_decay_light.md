# A3.3 Turn 4 — ProteinDecay-light (complex decay only)

**Status**: design ready · **Codex worktree**: `agent/a33-decay-light` (to be created) · **Estimated wall**: 30 min · **Depends on**: nothing in this turn (D.2-real is needed for the eventual integration test in Turn 5; Turn 4's own tests use synthetic states).

## Why this module exists

Probe 4 + reviewer critiques established the architecture: D.2-real assembles complexes from free subunits (producer), ProteinDecay-light degrades complexes back to free subunits (consumer). Together they close the ratchet so complex counts reach steady state instead of growing unboundedly.

This turn implements **only sub-process #3** of Karr's full ProteinDecay (per `docs/karr_extracts/process/21_ProteinDecay.md` §1.3 "Decay macromolecular complexes"). The other 4 sub-processes (misfold, refold, monomer decay, polypeptide-tag decay) are deferred to Phase B.

## Algorithm

### Karr's full ProteinDecay sub-process #3 (per docstring lines 44-49)

> Decay macromolecular complexes
> - Model decay is poisson process with rate parameter given by the inverse weighted average half life of the complex's subunits
> - Salvage bound prosthetic groups
> - Mark subunits as damaged to be degraded by either the protease/peptidase or ribonuclease machinery

### ProteinDecay-light simplifications (explicit in v1 design §1.2)

| Karr full | A3.3 light |
|---|---|
| Poisson per-complex decay rate (computed from subunit half-lives) | Configurable single-rate parameter `complex_decay_rate_per_s` (default `ln(2)/(8*3600)` = 8h half-life). Per-complex override via optional `complex_half_lives` dict. |
| Salvage prosthetic groups (heme, FeS clusters, etc.) | Deferred — prosthetic groups not modeled in A3.3 universe |
| Mark subunits as damaged → second-pass cleavage by protease/peptidase | Light: return subunits DIRECTLY to free protein/RNA pools (skipping the damaged→cleaved step). GPT-5.5 flagged this as a Karr-deviation; we accept it as the cost of "light". |
| Lon protease + 7 peptidase enzyme capacity check | Deferred — assume always-available enzymes. **Documented explicitly in §1.2 of v1 design and reaffirmed here.** |
| ATP + H₂O consumption for hydrolysis | Kept. The `complexDecayReactions` matrix provides per-complex stoichiometry. |
| Compartment restriction (cytosol + TM-cytosol only) | Deferred — A3.3 uses flat WID space, no compartment routing |

### ProteinDecay-light pseudocode

```python
class ProteinDecayLightProcess(Process):
    name = "karr_protein_decay_light"
    defaults = {
        "fixture_path": "data/karr_fixtures/per_process/ProteinDecay_flat.mat",
        "rng_seed": 0,
        "time_step": 1.0,
        "complex_decay_rate_per_s": math.log(2) / (8 * 3600),  # 8-hour default half-life
        "complex_half_lives": None,  # optional: dict[wid -> seconds]; overrides default
        "consume_atp_h2o": True,  # set False to skip metabolite accounting
    }
    
    def __init__(self, parameters):
        super().__init__(parameters)
        fx = _load_fixture(self.parameters["fixture_path"])
        self.complex_wids: list[str] = fx["complex_wids"]    # subset of 1206 — see filter below
        self.substrate_wids: list[str] = fx["substrate_wids"]  # the ProteinDecay substrate universe
        self.protein_wids: list[str] = fx["protein_monomer_wids"]
        self.rna_wids: list[str] = fx["rna_wids"]
        self.complex_decay_reactions: np.ndarray = fx["complex_decay_reactions"]  # (53, n_complexes)
        self._rng = np.random.default_rng(self.parameters["rng_seed"])
        
        # Filter to D.2-real's 147 complexes (intersection with D.2's complex_wids).
        # Rationale: ProteinDecay-light only operates on what D.2-real can recreate,
        # so the ratchet closure is exact. Other complexes (ribosomal modified
        # variants, etc.) are deferred to Phase B.
        # If filter list is given via parameter, use it; otherwise filter to first 147.
        # CODEX: read karr_d2_real.py to get the canonical list, OR have the caller
        # pass it via parameter. Pick the cleaner approach.
        # See "Implementation note: complex-set filtering" below.
        
    def ports_schema(self):
        return {
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_wids
                }
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.protein_wids
                }
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.rna_wids
                }
            },
            "requests": {
                "karr_protein_decay_light": {
                    "ATP": {"_default": 0.0, "_updater": "set", "_emit": False},
                    "H2O": {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                "karr_protein_decay_light": {
                    "ATP": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                    "H2O": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                }
            },
        }
    
    def next_update(self, timestep, states):
        # Step 1: sample how many of each complex decay this tick
        complex_counts = np.array(
            [float(states["complex"]["counts"][wid]) for wid in self.complex_wids],
            dtype=np.int64,
        )
        
        # Compute per-complex decay rate
        rates = np.full(len(self.complex_wids), self.parameters["complex_decay_rate_per_s"])
        if self.parameters["complex_half_lives"]:
            for i, wid in enumerate(self.complex_wids):
                hl = self.parameters["complex_half_lives"].get(wid)
                if hl:
                    rates[i] = math.log(2) / hl
        
        # Poisson sample: expected decays per complex = rate * count * dt
        expected = rates * complex_counts * timestep
        n_decay = self._rng.poisson(expected).astype(np.int64)
        # Cap at available counts (can't decay more than we have)
        n_decay = np.minimum(n_decay, complex_counts)
        
        # Step 2: compute stoichiometric updates from decay
        # complex_decay_reactions: shape (53, n_complexes), int16
        # Each column c gives the net stoichiometric change for substrate row r
        # when one of complex c decays.
        # Positive entries = products (subunits released, water consumed (?))
        # Negative entries = reactants (ATP consumed, H2O consumed)
        sub_deltas = self.complex_decay_reactions @ n_decay  # shape (53,)
        
        # Step 3: split sub_deltas into substrates / protein.counts / rna.counts
        # based on which subset of the 53 rows is metabolite vs monomer vs RNA.
        # CODEX: inspect the fixture's substrate_wid list and partition by WID prefix
        # or by lookup against opencell's M1/M2/M3 WID universes. See implementation note.
        
        # Step 4: build update
        update = {
            "complex": {
                "counts": {
                    wid: float(-n_decay[i])
                    for i, wid in enumerate(self.complex_wids)
                    if n_decay[i] > 0
                }
            },
            "substrates": {...},
            "protein": {"counts": {...}},
            "rna": {"counts": {...}},
            "requests": {
                "karr_protein_decay_light": {
                    "ATP": float(abs(sub_deltas[atp_index])),  # request what we'll consume
                    "H2O": float(abs(sub_deltas[h2o_index])),
                }
            },
        }
        return update
```

### Implementation note: complex-set filtering

The ProteinDecay fixture's `complexs` array has 1206 entries — far more than D.2-real's 147. This is because Karr's full ProteinDecay also handles ribosomal-modified variants, FtsZ compartmentalized variants, etc., that A3.3 doesn't model.

**Filter rule**: ProteinDecay-light's `self.complex_wids` is the intersection of:
- The 1206 complexes in `ProteinDecay_flat.mat::fixture.complexs` (with WIDs extracted from a separate field — likely `complexWholeCellModelIDs` or similar; verify by inspection)
- D.2-real's 147 D.2-formed complexes (from `MacromolecularComplexation_flat.mat`)

**Codex implementation**: load both fixtures' complex WID lists, compute the intersection, store as `self.complex_wids`. Also subset the `complex_decay_reactions` matrix to those columns.

**Verification**: assert `len(self.complex_wids) <= 147` (probably exactly 147 if every D.2 complex has a decay reaction defined).

### Implementation note: substrate partitioning

The 53 rows of `complex_decay_reactions` cover all of:
- ATP, ADP, phosphate, hydrogen, water (5 metabolites)
- 20 amino acids
- Modified amino acids (methionine, fmethionine, glutamate, glutamine, formate, ammonia — 6)
- Possibly some others (count: 5 + 20 + 6 = 31, room for 22 more)

When we apply `complex_decay_reactions @ n_decay`, the resulting 53-vector contains deltas for each of these. We need to route:
- ATP, H2O, ADP, Pi, H deltas → `substrates.<wid>` port (negative = consumption)
- Amino-acid deltas → `substrates.<wid>` port (positive = subunits released)
- Released *protein monomer subunits* — these are NOT in the 53-row substrate space; they come from `proteinComplexMonomerComposition` field. **Recompute monomer release from complex composition, not from decay reactions.**

Two-step substrate routing:
1. `sub_deltas = complex_decay_reactions @ n_decay` → metabolite + AA deltas (goes to `substrates`)
2. `monomer_deltas = proteinComplexMonomerComposition @ n_decay` → protein monomer deltas (goes to `protein.counts`)
3. `rna_deltas = proteinComplexRNAComposition @ n_decay` → RNA deltas (goes to `rna.counts`)

The `proteinComplexMonomerComposition` and `proteinComplexRNAComposition` fields exist in the fixture (verified at the field-listing step).

This is the cleaner architecture: complex decay reactions handle metabolite stoichiometry (ATP, H2O, AAs); composition matrices handle subunit return.

## Scope (this turn)

**Net new files**:
1. `opencell/vivarium/karr_protein_decay_light.py` (~220 LOC; revised up from 180 due to substrate partitioning logic)
2. `tests/vivarium/test_karr_protein_decay_light.py` (~200 LOC)

**Modified files**: NONE.

## Test plan

### Test 1: fixture loads
Asserts `complex_wids` is non-empty (≤ 147), `complex_decay_reactions` has expected shape.

### Test 2: zero complexes → zero decay
All `complex.counts.<wid>` = 0. Update returns empty (no decay, no subunit release).

### Test 3: deterministic Poisson
Same seed + same state → same number of decays. Confirms reproducibility.

### Test 4: mass conservation per complex
For one complex `c` with stoichiometry `composition[:, c]` and count `N`, force decay of all `N` (set rate to inf). Verify:
- `update["complex"]["counts"][wid_c] == -N`
- `update["protein"]["counts"]` deltas sum (weighted by `composition`) match Karr's prediction
- `update["rna"]["counts"]` deltas similarly

### Test 5: ATP+H2O accounting
Decay one complex, check `update["substrates"]["ATP"]` and `update["substrates"]["H2O"]` are negative and match the `complex_decay_reactions[atp_idx, c]` × n_decay value.

### Test 6: requests are state-derived
Confirm `update["requests"]["karr_protein_decay_light"]["ATP"]` equals the absolute ATP need for the decays that will happen this tick.

### Test 7: bounded by counts
Set rate to very high. Verify decays are capped at the current count (can't decay more than exists).

### Test 8: integration with D.2-real (SKIP if unavailable)
```python
pytest.importorskip("opencell.vivarium.karr_d2_real")
```
If D.2-real is on the branch but `karr_d2_real.py` isn't yet, skip cleanly. Re-enabled in Turn 5.

The integration scenario: D.2-real builds a complex from subunits → ProteinDecay-light decays it back. Mass should be conserved over one full cycle (subunits in == subunits out for the formed-then-decayed complexes, modulo ATP/H2O consumed for the decay step).

## Acceptance criteria

- All 7 non-skipped tests pass (8th is SKIP if D.2-real not present)
- `pytest tests/ -x --ignore=tests/probes -q` — no regressions
- Commit: `a33-t4: ProteinDecay-light (complex decay only)`
- STATUS reports counts + full pytest output

## Out of scope (Turn 4)

- Protein monomer decay (sub-process 4) — Phase B
- Misfolding/refolding (sub-processes 1, 2) — Phase B
- Polypeptide-tag decay — Phase B
- Lon protease + peptidase capacity check — Phase B
- Prosthetic group salvage — Phase B
- Compartment routing — Phase B
- Chassis integration — Turn 5
