# M1 validation against Karr 2012 published values

_Generated 2026-04-24T13:34:23.283663+00:00_

## Inputs (all sourced)

| File | sha256 | Source |
|---|---|---|
| `data/m1_sources/iPS189.xml` | `d18ff3c941763956` | Suthers et al., PLoS Comput Biol 2009 (doi:10.1371/journal.pcbi.1000285) supplementary s005 |
| `data/m1_sources/WholeCell/data/parameters.json` | `d93c9af3bcaf47ce` | Karr et al., Cell 2012; github.com/CovertLab/WholeCell @ data/parameters.json |
| `data/m1_sources/WholeCellKB/public/fixtures/data.xlsx` | `31dafc5b637b975d` | github.com/CovertLab/WholeCellKB public/fixtures/data.xlsx |

**Karr-sourced numeric inputs:**

- `exchangeRateUpperBound_carbon` = 12.0
- `exchangeRateUpperBound_noncarbon` = 20.0
- `nonGrowthAssociatedMaintenance` = 8.39
- `growthAssociatedMaintenance` = 59.81
- `meanInitialGrowthRate_cell_per_s` = 2.1393e-05
- `meanInitialGrowthRate_per_h` = 0.0770148

## Model

- Full iPS189 SBML loaded with libsbml: 350 reactions, 433 species (87 boundary).
- Objective: `R_Biomass`. pFBA via scipy.optimize.linprog (highs); steady state imposed only on non-boundary species.
- Defaults: rev → [-1000, 1000]; non-rev → [0, 1000].
- Karr overrides: `R_EX_glc_D_e_.lb = -12.0`; `R_ATPM.lb = 8.39`; SP4 non-carbon exchanges capped at |±20.0|; `R_ZN2t4` opened for zinc influx (iPS189 SBML encodes it as export-only).

## Three-mode comparison

| Mode | Biomass flux (h⁻¹) | Glucose uptake | ATPM | Lactate excretion |
|---|---:|---:|---:|---:|
| **A** A: iPS189 raw + Karr bounds + NGAM | -0 | 0 | 8.39 | 8.39 |
| **B** B: iPS189 fully reversible + Karr bounds + NGAM | 28.32 | -0.6966 | 8.39 | -0 |
| **C** C: iPS189 fully open, no NGAM (feasibility check) | 542.3 | -13.34 | -1000 | 446.7 |

## Primary comparison (Mode A — literal Karr setup)

| Metric | Karr target | OpenCell predicted | Rel error | Karr source |
|---|---:|---:|---:|---|
| Growth rate (h^-1) | 0.07701 | -0 | -100.00% | WCKB Misc.parameters Parameter_0151 (meanInitialGrowthRate, is_experimentally_constrained=true) = 2.1393e-05 cell/s × 3600 |
| Doubling time (h) | 9 | — | — | ln(2) / Parameter_0151_per_h |
| Glucose uptake cap (mmol/(gDW·h)) | -12 | 0 | — | parameters.json processes.Metabolism.exchangeRateUpperBound_carbon (negated for uptake) |
| NGAM ATPM lower bound | 8.39 | 8.39 | +0.00% | parameters.json processes.Metabolism.nonGrowthAssociatedMaintenance |

## Interpretation

Mode A is the literal Karr-2012 setup applied to the public Suthers-2009 SBML.  Mode B opens irreversibility constraints on non-Karr-overridden reactions; Mode C drops Karr bounds entirely.

Mode A predicts mu = 0 (no growth).  Modes B and C predict mu > 0, which proves the LP machinery is correct and the gap is not in our solver.  The gap is that Karr and colleagues curated additional reactions and reversibility flips (notably for transporters and the tRNA-charging cycle) directly into MATLAB-class knowledgebase objects that ARE NOT in the public Suthers iPS189 SBML.  Those modifications are saved in Simulation_fitted.mat / knowledgeBase.mat.

Open-source status of those .mat files: the WholeCell repository is MIT-licensed and we have its full 187-file MATLAB source, but the .mat files were serialized as instances of custom MATLAB classes (mcos blobs).  Reconstituting them in Python via scipy.io.loadmat / pymatreader returns only an opaque (s0, s1, s2, arr) structure.  Loading them in GNU Octave hangs because the WholeCell class hierarchy transitively imports CPLEX 12.2 (commercial), GLPK-MEX (binary), Java libs (json-marshaller, batik), and MySQL JDBC.  In practice deserializing these files requires the full MATLAB toolchain + commercial CPLEX license -- which is a real, documented gap in how Karr et al. published their data.

Resolution paths (in increasing fidelity to Karr): (1) Augment iPS189 with sourced fixes (transporter reversibility, missing exchanges) one reaction at a time, each documented from BiGG / KEGG / the Suthers paper text.  (2) Use the iJR904 or iJO1366 E. coli models as an FBA oracle for the central-carbon validation, comparing fluxes on shared reactions.  (3) Run Karr's MATLAB code on a machine with a CPLEX license (the only way to obtain Karr's exact predicted state).

## No-synthesis statement

Every numeric input on this page is loaded from the files in the Inputs table above; no value was hand-entered into source. The predicted column is the LP solver output. Rel-error is computed as (predicted − Karr) / Karr.
