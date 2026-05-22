Phase B Turn 2 (RibosomeAssembly) completed at 2026-05-22 22:40:08 +05:30

Implemented
- opencell/vivarium/karr_ribosome_assembly.py
  - Added KarrRibosomeAssemblyProcess (name: karr_ribosome_assembly)
  - Loads data/karr_fixtures/per_process/RibosomeAssembly_flat.mat
  - Extracts RNA/monomer composition, catalysis matrix, substrate/enzyme/complex WIDs
  - Tracks 6 GTPases: EngA=MG_329_MONOMER, EngB=MG_335_MONOMER, Era=MG_387_MONOMER, Obg=MG_384_MONOMER, RbfA=MG_143_MONOMER, RbgA=MG_442_MONOMER
  - Supports 2 particle outputs: RIBOSOME_30S, RIBOSOME_50S
  - ports_schema implemented per design; assembly outputs use accumulate updater
  - next_update implements randomized per-particle order and all-or-nothing formation limit:
    min(rna_limit, monomer_limit, gtpase_limit, gtp_limit, h2o_limit)
  - Applies deltas: consume RNA/monomers/GTP/H2O and produce complexes/GDP/PI/H

- opencell/vivarium/karr_request_calculators.py
  - Added RequestCalculatorRibAsm(Step)
  - Computes GTP/H2O requests as sum(max_formable_without_substrates * n_gtpases_per_particle)

- tests/vivarium/test_karr_ribosome_assembly.py
  - Added 9 tests per design plan:
    1) fixture load
    2) no subunits -> no assembly
    3) no GTP -> no assembly
    4) one formation consumes expected GTP/H2O
    5) GDP/PI/H byproducts exact
    6) randomization affects scarcity outcome
    7) mass conservation on RNA/monomer/substrate deltas
    8) allocation + ribasm integration smoke (chassis-guarded)
    9) 500-tick ribosome+decay bounded/non-zero steady-state behavior

Verification
- Import check (WSL venv): PASS
  - /mnt/e/opencell/.venv-wsl/bin/python -c 'from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess'
- Targeted new tests: PASS
  - pytest tests/vivarium/test_karr_ribosome_assembly.py -v
  - Result: 9 passed
- Vivarium subset regression: PASS
  - pytest tests/vivarium -q
  - Result: 111 passed

Key metrics
- Controlled single-tick assembly (test_mass_conservation scenario):
  - Formation rate: 30S=3 particles/tick, 50S=2 particles/tick
  - GTP consumption: 14 molecules/tick (with matching H2O consumption 14/tick)
  - Byproducts: GDP=14/tick, PI=14/tick, H=14/tick
- Scarcity/randomization check:
  - seed=0 path: 2x30S formed (4 GTP consumed)
  - seed=3 path: 1x50S formed (4 GTP consumed)
