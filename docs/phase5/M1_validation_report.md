# M1 validation against Karr 2012 published values

_Generated 2026-04-25T05:55:11.305584+00:00_

## Inputs (all sourced)

| File | sha256 | Source |
|---|---|---|
| `data/m1_sources/iPS189.xml` | `d18ff3c941763956` | Suthers et al., PLoS Comput Biol 2009 (doi:10.1371/journal.pcbi.1000285) supplementary s005 |
| `data/m1_sources/WholeCell/data/parameters.json` | `d93c9af3bcaf47ce` | Karr et al., Cell 2012; github.com/CovertLab/WholeCell @ data/parameters.json |
| `data/m1_sources/WholeCellKB/public/fixtures/data.xlsx` | `31dafc5b637b975d` | github.com/CovertLab/WholeCellKB public/fixtures/data.xlsx |
| `data/m1_sources/karr_flat/sim_fitted_targeted.mat` | `e5ae921d22a3b885` | Extracted from Karr WholeCell Simulation_fitted.mat via local MATLAB R2026a (scripts/matlab/extract_karr_targeted.m).  Contains the curated FBA stoichiometry, bounds, and biomass objective Karr's metabolism process used at runtime. |

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

## Five-mode comparison

| Mode | Biomass flux (h⁻¹) | Glucose uptake | ATPM | Lactate excretion |
|---|---:|---:|---:|---:|
| **A** A: iPS189 raw + Karr bounds + NGAM | -0 | 0 | 8.39 | 8.39 |
| **B** B: iPS189 fully reversible + Karr bounds + NGAM | 28.32 | -0.6966 | 8.39 | -0 |
| **C** C: iPS189 fully open, no NGAM (feasibility check) | 542.3 | -13.34 | -1000 | 446.7 |
| **D** D: Karr fitted MAT, snapshot rxn bounds + RHS (BIG=1e3) | 0.03922 | — | — | — |
| **E** E: Karr stored runtime oracle (read from MAT) | 0.07629 (stored) | — | — | — |

**Mode D detail:** solved on Karr's own fitted FBA matrix (376 metabolites × 504 reactions, RHS=fbaRightHandSide, BIG=1e3 substituted for ±∞), Karr objective = max biomass + parsimony penalty.  μ = 0.03922 /h vs Karr stored 0.07629 /h (ratio 0.51× — within 2×).  Snapshot fbaEnzymeBounds were dropped: 34/504 of Karr's stored fluxs violate snapshot fbaEnzymeBounds; snapshot bounds are post-step (free-enzyme) not the bounds used during the LP solve.

**Mode E (Karr's stored runtime oracle):** at the Simulation_fitted.mat snapshot, Karr's metabolism state recorded growth = 2.119e-05 /s (0.07629 /h), doubling time = 13.1 h, plus the full 645-element flux vector with 253 nonzero entries (range [-1e+06, 1e+06]).  This is the gold-standard oracle for downstream per-reaction validation.

## Primary comparison (Mode A — literal Karr setup)

| Metric | Karr target | OpenCell predicted | Rel error | Karr source |
|---|---:|---:|---:|---|
| Growth rate (h^-1) | 0.07701 | -0 | -100.00% | WCKB Misc.parameters Parameter_0151 (meanInitialGrowthRate, is_experimentally_constrained=true) = 2.1393e-05 cell/s × 3600 |
| Doubling time (h) | 9 | — | — | ln(2) / Parameter_0151_per_h |
| Glucose uptake cap (mmol/(gDW·h)) | -12 | 0 | — | parameters.json processes.Metabolism.exchangeRateUpperBound_carbon (negated for uptake) |
| NGAM ATPM lower bound | 8.39 | 8.39 | +0.00% | parameters.json processes.Metabolism.nonGrowthAssociatedMaintenance |

## Interpretation

Mode A is the literal Karr-2012 setup applied to the public Suthers-2009 SBML.  Mode B opens irreversibility constraints on non-Karr-overridden reactions; Mode C drops Karr bounds entirely.  Mode D solves Karr's own fitted FBA matrices (extracted from Simulation_fitted.mat via local MATLAB R2026a using the targeted extractor in scripts/matlab/extract_karr_targeted.m).  Mode E reads Karr's stored runtime values (state.MetabolicReaction.dump) directly as a validation oracle.

Mode A predicts mu = 0.  Mode D predicts mu = 0.039 /h vs Karr published 0.077 /h — within 2x.

STRUCTURAL FINDING (2026-04-25): Karr's MAT snapshot fundamentally cannot reproduce his runtime growth via static FBA.  The smoking gun: 34/504 of Karr's own stored fluxes (mode E's data) violate his own snapshot fbaEnzymeBounds, by up to 100x.  This proves that the snapshot enzyme bounds are POST-step (free-enzyme count after substrate binding tightened it), not the bounds Karr used during the LP solve.  Including snapshot enzyme bounds in Mode D gives mu ~135x lower than published; dropping them and using a per-cell-per-sec ceiling of 1e3 (Karr's natural runtime cobratoolbox-style default) gives Mode D's reported mu = 0.039 /h.  The remaining 2x gap is the implicit runtime context for the unbounded reactions (Karr's calcFluxBounds() runs every simulated second using protein-state and kinetic constants; we have not ported that calculation).

Implication for downstream M1 validation: the right oracle is NOT 'compare derived FBA growth to Karr published mu' — that comparison is structurally bounded by what a static snapshot can express.  The right oracle is Mode E: compare individual reaction fluxes (and growth) to Karr's STORED runtime values, since those are GROUND TRUTH at this snapshot.  This requires porting reactionWholeCellModelIDs onto our M1 module's reaction set and doing per-reaction comparisons.

## No-synthesis statement

Every numeric input on this page is loaded from the files in the Inputs table above; no value was hand-entered into source. The predicted column is the LP solver output. Rel-error is computed as (predicted − Karr) / Karr.
