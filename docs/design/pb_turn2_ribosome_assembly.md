# Phase B Turn 2 — RibosomeAssembly (full GTP-dependent)

**Status**: design ready · **Estimated wall**: 40 min · **Karr process**: `Process_RibosomeAssembly` · **Functional area**: protein-synthesis-and-maturation

## Why this is Phase B Turn 2

A3.3 left two ribosomal complexes (`RIBOSOME_30S`, `RIBOSOME_50S`) in `D.2-real` as MC-sampled complexes without their actual biological constraints. Karr's `RibosomeAssembly` is a separate process that:

1. **Consumes 6 GTPases as catalytic enzymes** (Era=MG_387, RbfA=MG_143 for 30S; EngA=MG_329, EngB=MG_335, Obg=MG_384, RbgA=MG_442 for 50S)
2. **Consumes 1 GTP + 1 H2O per particle assembled**
3. **Has an all-or-nothing per-tick assembly model** (either a full particle forms within Δt=1s, or no progress)
4. **Routes through KarrAllocationStep for GTP/H2O** — first real test of our allocation step with non-zero requests (D.2-real always requests zero, recall Opus critique)

Once Turn 2 lands, the 2 ribosomal complexes move from D.2-real's MC pool to RibosomeAssembly's deterministic kinetic process.

## Empirical fixture findings

Fixture: `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`. Inspect at implementation time. Expected fields (per docstring):
- `proteinComplexRNAComposition`: rRNA composition of 30S and 50S
- `proteinComplexMonomerComposition`: r-protein composition of 30S and 50S
- `complexationCatalysisMatrix`: which GTPases catalyze which particle
- 2 complexes: RIBOSOME_30S, RIBOSOME_50S
- Substrates: GTP, GDP, Pi, H2O, H+ at minimum

## Karr's algorithm (per docstring lines 64-74)

```
In randomized order over particles (RIBOSOME_30S, RIBOSOME_50S):
  for each ribosomal particle:
    1. Calculate max number of particles formable, limited by:
       - free RNA subunits (16S for 30S, 5S+23S for 50S)
       - free protein monomers (~20 for 30S, ~30 for 50S)
       - 6 GTPase enzyme counts
       - GTP supply (from allocation step)
       - H2O supply (from allocation step)
    2. Form n_form particles:
       - complex.counts[particle] += n_form
       - rna.counts[subunit] -= n_form * stoich (per composition matrix)
       - protein.counts[monomer] -= n_form * stoich
       - substrates[GTP] -= n_form * n_gtpases (6 for the catalysts)
       - substrates[H2O] -= n_form * n_gtpases
       - substrates[GDP] += n_form * n_gtpases
       - substrates[Pi] += n_form * n_gtpases
       - substrates[H] += n_form * n_gtpases
```

The randomization is over which particle forms first within a tick (matters when GTP is scarce — first-come-first-served).

## Vivarium chassis integration

### Class: `KarrRibosomeAssemblyProcess(Process)`

```python
name = "karr_ribosome_assembly"
defaults = {
    "fixture_path": "data/karr_fixtures/per_process/RibosomeAssembly_flat.mat",
    "rng_seed": 0,
    "time_step": 1.0,
}
```

### ports_schema

```python
{
    "substrates": {
        # GTP, GDP, Pi, H2O, H+ — at minimum
        wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
        for wid in self.substrate_wids
    },
    "rna": {
        "counts": {
            # 16S, 5S, 23S rRNAs (and any others in the composition)
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
            for wid in self.rna_subunit_wids
        }
    },
    "protein": {
        "counts": {
            # All r-protein subunits + the 6 GTPase enzymes (read-only)
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
            for wid in self.monomer_subunit_wids + self.gtpase_wids
        }
    },
    "complex": {
        "counts": {
            "RIBOSOME_30S": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
            "RIBOSOME_50S": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        }
    },
    "requests": {
        "karr_ribosome_assembly": {
            "GTP": {"_default": 0.0, "_updater": "set", "_emit": False},
            "H2O": {"_default": 0.0, "_updater": "set", "_emit": False},
        }
    },
    "substrates_allocated": {
        "karr_ribosome_assembly": {
            "GTP": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
            "H2O": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
        }
    },
}
```

### Algorithm

```python
def next_update(self, timestep, states):
    # Read GTP+H2O allocations (the Karr allocation step set these upstream)
    gtp_alloc = float(states["substrates_allocated"]["karr_ribosome_assembly"]["GTP"])
    h2o_alloc = float(states["substrates_allocated"]["karr_ribosome_assembly"]["H2O"])
    
    n_formed = {"RIBOSOME_30S": 0, "RIBOSOME_50S": 0}
    
    # Randomize particle order each tick
    particle_order = self._rng.permutation(["RIBOSOME_30S", "RIBOSOME_50S"])
    
    for particle in particle_order:
        # Limit by RNA subunits
        rna_limit = self._compute_rna_limit(particle, states)
        # Limit by protein monomers
        monomer_limit = self._compute_monomer_limit(particle, states)
        # Limit by GTPase enzymes (all 6 must be present; min count rules)
        gtpase_limit = self._compute_gtpase_limit(particle, states)
        # Limit by GTP, H2O (allocations)
        gtp_per_particle = self.n_gtpases_per_particle[particle]  # e.g., 2 for 30S, 4 for 50S
        gtp_limit = math.floor(gtp_alloc / gtp_per_particle)
        h2o_limit = math.floor(h2o_alloc / gtp_per_particle)
        
        n_form = min(rna_limit, monomer_limit, gtpase_limit, gtp_limit, h2o_limit)
        if n_form <= 0:
            continue
        
        n_formed[particle] = n_form
        # Decrement allocations
        gtp_alloc -= n_form * gtp_per_particle
        h2o_alloc -= n_form * gtp_per_particle
    
    # Compute and emit deltas
    update = self._build_update(n_formed)
    return update
```

### RequestCalculator for GTP/H2O

```python
class RequestCalculatorRibAsm(Step):
    """Compute RibosomeAssembly's GTP+H2O request from current rna/protein/enzyme state."""
    defaults = {"ribasm_proc": None}
    
    def ports_schema(self):
        return {
            "substrates": {...read-only baseline...},
            "rna": {"counts": {...read subunits...}},
            "protein": {"counts": {...read subunits + 6 GTPases...}},
            "requests": {
                "karr_ribosome_assembly": {
                    "GTP": {"_default": 0.0, "_updater": "set", "_emit": False},
                    "H2O": {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
        }
    
    def next_update(self, timestep, states):
        # Estimate max formable per particle from current state (excl. GTP/H2O)
        # Request GTP/H2O = sum of (estimate * n_gtpases_per_particle)
        ...
```

## Scope

**Net new files**:
1. `opencell/vivarium/karr_ribosome_assembly.py` (~240 LOC)
2. `tests/vivarium/test_karr_ribosome_assembly.py` (~200 LOC)

**Net additions to existing files**:
- `opencell/vivarium/karr_request_calculators.py` (+~50 LOC for `RequestCalculatorRibAsm`)

**Modified files**: NONE (D.2-real keeps its current treatment of ribosomal complexes; the chassis_v4 builder will route to RibosomeAssembly in Turn 5 of Phase B).

## Test plan

1. **test_fixture_loads**: 2 complexes, correct subunit/enzyme WID counts
2. **test_no_subunits_no_assembly**: zero rna+monomer → zero formed
3. **test_no_gtp_no_assembly**: zero GTP allocation → zero formed
4. **test_one_formation_consumes_gtp**: form 1 particle → exactly `n_gtpases × n_gtp_per_gtpase` GTP consumed
5. **test_gdp_pi_h_byproducts**: form N particles → produce exactly N×n_gtpases of GDP/Pi/H
6. **test_randomization_changes_outcome**: under GTP scarcity, the particle formed first changes with seed
7. **test_mass_conservation**: rna/monomer/substrate delta accounts exactly
8. **test_integration_with_chassis_v3**: composite with allocation + ribasm runs without error (skip if chassis_v4 not yet built)
9. **test_steady_state_ribosome_count** (extended): in a 500-tick chassis run with ProteinDecay-light decaying ribosomes, steady-state count is bounded and non-zero

## Acceptance criteria

- All 9 tests pass (or 8 + 1 chassis-skip)
- No regressions in A3.3 tests (32 tests) or M1/M2/M3 tests
- Commit: `pb-t2: RibosomeAssembly (GTP-dependent all-or-nothing assembly)`

## Out of scope

- Wiring into a new chassis builder (chassis_v4 = Phase B Turn N once enough Phase B processes land)
- Modeling assembly intermediates (Karr's all-or-nothing simplification is preserved)
- Modeling GTPase catalytic kinetics individually (each GTPase consumes 1 GTP + 1 H2O; no Michaelis-Menten)

## Phase B subsequent turns (preview)

| Turn | Process | Key new mechanism |
|---|---|---|
| pb-t3 | TranscriptionalRegulation | Feedback into M2v3 transcription rates from current gene-product counts |
| pb-t4 | RNAProcessing | Pre-rRNA cleavage from 16S/23S/5S precursors; pre-tRNA processing |
| pb-t5 | RNAModification | Methylation, pseudouridylation of t/rRNAs |
| pb-t6 | ProteinProcessingI | N-terminal Met cleavage, signal peptide cleavage |
| pb-t7 | ProteinProcessingII | Diacylation, isoprenylation |
| pb-t8 | ProteinModification | Phosphorylation, acetylation |
| pb-t9 | ProteinFolding | Chaperone-mediated folding (groEL, dnaK) |
| pb-t10 | ProteinTranslocation | Sec-system membrane insertion |
| pb-t11 | ProteinActivation | Activation reactions for selected enzymes |
| pb-final | build_karr_chassis_v4 | Full Phase B integration + extended ratchet validation |
