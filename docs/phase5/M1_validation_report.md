# M1 validation against Karr 2012 published values

_Generated 2026-04-24T19:08:54.643919+00:00_

## Inputs (all sourced)

| File | sha256 | Source |
|---|---|---|
| `data/m1_sources/iPS189.xml` | `d18ff3c941763956` | Suthers et al., PLoS Comput Biol 2009 (doi:10.1371/journal.pcbi.1000285) supplementary s005 |
| `data/m1_sources/WholeCell/data/parameters.json` | `d93c9af3bcaf47ce` | Karr et al., Cell 2012; github.com/CovertLab/WholeCell @ data/parameters.json |
| `data/m1_sources/WholeCellKB/public/fixtures/data.xlsx` | `31dafc5b637b975d` | github.com/CovertLab/WholeCellKB public/fixtures/data.xlsx |
| `data/m1_sources/karr_flat/sim_fitted_targeted.mat` | `4f3c17a74a0956b5` | Extracted from Karr WholeCell Simulation_fitted.mat via local MATLAB R2026a (scripts/matlab/extract_karr_targeted.m).  Contains the curated FBA stoichiometry, bounds, and biomass objective Karr's metabolism process used at runtime. |

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

## Four-mode comparison

| Mode | Biomass flux (h⁻¹) | Glucose uptake | ATPM | Lactate excretion |
|---|---:|---:|---:|---:|
| **A** A: iPS189 raw + Karr bounds + NGAM | -0 | 0 | 8.39 | 8.39 |
| **B** B: iPS189 fully reversible + Karr bounds + NGAM | 28.32 | -0.6966 | 8.39 | -0 |
| **C** C: iPS189 fully open, no NGAM (feasibility check) | 542.3 | -13.34 | -1000 | 446.7 |
| **D** D: Karr fitted MAT (from MATLAB extraction) | 0.01089 | — | — | — |

**Mode D detail**: solved on Karr's own fitted FBA matrix (376 metabolites × 504 reactions), biomass at column 502, 339 reactions active at the optimum.  μ = 0.01089 /h vs Karr published 0.07701 /h (rel-error -85.9%).  This is **not a match** — Karr's own stoichiometry and bounds, solved by our LP, predict growth ~7× lower than the published value.

**Caveat — what Mode D does NOT validate.**  The `ngam_from_mat=8.39`, `gam_from_mat=59.81`, and `cellCycleLength_s_from_mat=32400` fields above are *read* directly from the MAT.  They equal Karr's published values by definition (Karr published those numbers because that is what is in the MAT).  They confirm the extractor is correct, **not** that the model reproduces biology.  The only independently-predicted quantity in Mode D is μ, and it is currently 14% of Karr's target.  Likely missing inputs: (a) the small penalty terms in `fbaObjective` (35 entries of −5.31e-9) we dropped during diagnosis, (b) `fbaEnzymeBounds` — kinetic flux ceilings derived from enzyme amounts × kcats, (c) the fact that Karr's metabolism process is dynamic (substrate / enzyme amounts update every second from the other 27 processes) and a single static snapshot may not be at biomass-max steady state.

## Primary comparison (Mode A — literal Karr setup)

| Metric | Karr target | OpenCell predicted | Rel error | Karr source |
|---|---:|---:|---:|---|
| Growth rate (h^-1) | 0.07701 | -0 | -100.00% | WCKB Misc.parameters Parameter_0151 (meanInitialGrowthRate, is_experimentally_constrained=true) = 2.1393e-05 cell/s × 3600 |
| Doubling time (h) | 9 | — | — | ln(2) / Parameter_0151_per_h |
| Glucose uptake cap (mmol/(gDW·h)) | -12 | 0 | — | parameters.json processes.Metabolism.exchangeRateUpperBound_carbon (negated for uptake) |
| NGAM ATPM lower bound | 8.39 | 8.39 | +0.00% | parameters.json processes.Metabolism.nonGrowthAssociatedMaintenance |

## Interpretation

Mode A is the literal Karr-2012 setup applied to the public Suthers-2009 SBML.  Mode B opens irreversibility constraints on non-Karr-overridden reactions; Mode C drops Karr bounds entirely.  Mode D solves Karr's own fitted FBA matrices (extracted from Simulation_fitted.mat via local MATLAB R2026a using the targeted extractor in scripts/matlab/extract_karr_targeted.m).

Mode A predicts mu = 0 (no growth).  Modes B and C predict mu > 0, which proves the LP machinery is correct and the gap is not in our solver.  Mode D, on Karr's own stoichiometry + bounds + biomass objective, predicts mu = 0.0109 /h vs Karr published 0.077 /h — a ~7x miss.  The remaining gap therefore is NOT 'iPS189 vs Karr's curated network'; both are now Karr's.  The remaining gap is likely (a) the small penalty terms in fbaObjective (35 entries of -5.31e-9) we dropped during initial diagnosis, (b) fbaEnzymeBounds — kinetic flux ceilings from enzyme amounts and kcats — extracted but not yet applied as additional bounds, and/or (c) the dynamic nature of Karr's metabolism process: substrate and enzyme amounts update every simulated second from the other 27 processes, so a static snapshot may not be at biomass-max steady state.

Honesty note: ngam_from_mat = 8.39, gam_from_mat = 59.81, cellCycleLength_s_from_mat = 32400 in Mode D's output match Karr's published values BY DEFINITION (those numbers ARE Karr's; they live in the MAT we read).  They confirm the extractor is correct, not that the model reproduces biology.  Likewise in Mode A, R_ATPM flux equalling NGAM is a tautology (NGAM is the lower bound on R_ATPM, and with biomass = 0 the LP rests on that bound).  The only independently predicted quantities in this report are the biomass fluxes (Mode A: 0; Mode D: 0.0109; both differ from the 0.077 target).  Net independent agreement: 0/4.

## No-synthesis statement

Every numeric input on this page is loaded from the files in the Inputs table above; no value was hand-entered into source. The predicted column is the LP solver output. Rel-error is computed as (predicted − Karr) / Karr.
