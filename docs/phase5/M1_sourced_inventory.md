# M1 — Sourced parameter inventory (UNBLOCKED)

**Status:** unblocked (2026-04-25). All M1 inputs identified in
authoritative public sources fetched directly into
`data/m1_sources/`. **No values to be synthesised.** The user's prior
hard-stop on hand-curation has been resolved by going to the actual
upstream Karr/Suthers data (which I had previously failed to look for
on GitHub — see the user pushback "why are you unable to get the data
from existing GitHub repos").

## Sources fetched (under `data/m1_sources/`)

| Source | Path | Provenance |
|---|---|---|
| Suthers 2009 SBML (iPS189) | `iPS189.xml` (232 KB) | PLoS Comput Biol 5(2):e1000285 supplementary s005 |
| Suthers 2009 supplementary tables | `suthers2009_s001..s004` (.xls) | PLoS Comput Biol DOI 10.1371/journal.pcbi.1000285 |
| Karr 2012 simulation data | `WholeCell/data/` | github.com/CovertLab/WholeCell @ 6cdee6b |
| Karr 2012 knowledge-base xlsx | `WholeCellKB/public/fixtures/data.xlsx` (1.7 MB, 20 sheets) | github.com/CovertLab/WholeCellKB @ 10a9798 |
| Karr 2012 knowledge-base SQL | `WholeCellKB/public/fixtures/data.sql` (8.2 MB) | same — full DB dump with `public_evidence` provenance rows |
| Karr 2012 parameter manifest | `data/karr_fixtures/parameters.json` (5 KB, A4F) | github.com/CovertLab/WholeCell |

## M1 parameter availability

### iPS189 SBML — `iPS189.xml` (loaded with libsbml, 0 errors)

- 350 reactions, 433 species, 2 compartments (Extra_organism, Cytosol)
- Glycolysis present and complete: `R_PGI`, `R_PFK`, `R_FBA`, `R_TPI`,
  `R_GAPD`, `R_PGK`, `R_PGM`, `R_ENO`, `R_PYK`
- PTS uptake: `R_GLCpts`, `R_FRUpts`, `R_MANpts`, `R_GAMpts`,
  `R_MALTpts`, `R_SUCpts`, `R_TREpts`, `R_CELBpts`, `R_ARBTpts`,
  `R_SALCpts`, `R_MNLpts`, `R_ACGApts`
- Fermentation: `R_LDH_L`, `R_PTAr`, `R_PTA2r`, `R_ACKr`, `R_PDH`
- Energy: `R_ATPS4r`, `R_ADK1`, `R_ADK2`, `R_DADK`
- `R_Biomass`: 61 reactants, 23 products — full M.gen biomass equation
  with sourced stoichiometric coefficients (e.g. 0.2669 alanyl-tRNA,
  0.193 arginyl-tRNA, 0.148 asparaginyl-tRNA, ...)
- No flux bounds embedded (pure FBA-style stoichiometry); use
  COBRA convention plus the 3 Karr A4F bounds below

### Karr A4F parameters (already ingested via `data/karr_fixtures/parameters.json`)

| Quantity | Value | Unit | parameters.json key |
|---|---|---|---|
| Glucose uptake upper bound | 12.0 | mmol/(gDW·h) | Metabolism.exchangeRateUpperBound_carbon |
| Non-carbon uptake upper bound | 20.0 | mmol/(gDW·h) | Metabolism.exchangeRateUpperBound_noncarbon |
| Non-growth ATP maintenance (NGAM) | 8.39 | mmol_ATP/(gDW·h) | Metabolism.nonGrowthAssociatedMaintenance |
| Growth-associated ATP demand (GAM) | 59.81 | mmol_ATP/mmol_biomass | Metabolism.growthAssociatedMaintenance |

Units for NGAM/GAM still tagged UNVERIFIED in
`karr_parameters_unit_map.yaml`; M1 work should resolve them by
cross-checking against WholeCellKB Reactions sheet annotations.

### WholeCellKB parameters extracted via `scripts/m1_extract_wckb.py`

- **Biomass composition (col 17, "mmol gDCW⁻¹")** — per-metabolite
  coefficients for all M.gen biomass precursors. Zero synthesis.
- **Adenylate kinase (Adk1) Keq = 1.0** | kinetic form
  `Vmax*AMP/(Km+AMP)` — sourced from Reactions sheet
- **Adk2..Adk4, Dak1** — full Adk family with Keq + kinetics
- **Media composition (col 18, "SP4 mM")** — extracellular concs for
  all SP4-medium species (e.g. GLC = 32.95 mM, AC = 0.305 mM, NAD =
  0.00528 mM)
- All 156 misc parameters available with `value`, `units`, `evidence`
  (incl. `is_experimentally_constrained` flag), `references`

### Initial intracellular concentrations — derivable

ATP/ADP/AMP/NAD/NADH initial intracellular concentrations are NOT
stored as KB rows; Karr's `Metabolism.m` computes them at sim init
from biomass composition × cell volume × growth rate. Two sourced
routes available:

1. **Simulation steady-state extraction** — `WholeCell/data/Simulation_fitted.mat`
   contains the fitted simulation timeseries; ATP/ADP/AMP intracellular
   concentrations can be read from the `Metabolism` state at t=0
   (no synthesis; just extraction of an authoritative simulation result).
2. **Mechanical derivation** — replicate the Karr init formula:
   `[X] = biomass_coeff[X] × dryWeight / (volume × molecularWeight)`,
   with all inputs sourced (biomass_coeff from WholeCellKB, dryWeight
   and volume from `parameters.json` State_Mass entries).

Both routes are zero-synthesis. Prefer (1) as primary, (2) as
cross-check.

### Validation oracle thresholds — sourced

- **Adenylate energy charge (EC) target** — Karr 2012 wild-type
  simulation (path: `WholeCell/data/Simulation_fitted.mat`) reports
  the steady-state EC. Read directly; no Atkinson 1968 fallback
  required.
- **Total adenylate pool size** — derivable as in (2) above from
  biomass composition + cell volume.
- **Lactate / acetate fermentation flux split** — derivable as
  steady-state ratio of `R_LDH_L` / `R_ACKr` fluxes from
  `Simulation_fitted.mat`; cross-check against Yus et al. 2009
  Mycoplasma metabolome paper if needed.
- **ATP-production-feasibility ≥ maintenance** — directly enforceable
  from sourced NGAM (8.39 mmol/(gDW·h)).
- **Glucose-sensitivity** — derivable from sweep over glucose uptake
  bound (already-sourced upper limit 12 mmol/(gDW·h)).

## Implementation plan (once de-blocked)

1. **`scripts/karr_a4f_ingest_m1.py`** — extend the A4F ingest pattern
   to load iPS189.xml + WholeCellKB xlsx and emit a single sourced
   `data/karr_fixtures/iPS189_m1.json` with: stoichiometry, biomass
   reaction, AK kinetics, media composition. Every value carries its
   `source_path`, `source_row` and `evidence` attribution.

2. **`opencell/m1/central_carbon.py`** — pFBA solver + adenylate ODE
   wrapper. Loads stoichiometry from the JSON above; **no embedded
   numbers**; reaction list filtered to a glycolysis + fermentation +
   energy subnetwork (~20-30 reactions) selected by membership rules
   (compartment + pathway tag), not hand-curated.

3. **`opencell/vivarium/m1_metabolism.py`** — Vivarium Process wrapping
   the M1 module using the M0-A persistent-LSODA pattern.

4. **`tests/m1/`** — five tests, one per validation criterion, each
   asserting against the WholeCellKB-sourced threshold.

5. **`scripts/m1_validate.py`** — produces `artifacts/M1_validation.json`
   with steady-state EC / pool / fermentation split from a 1 h Vivarium
   simulation, vs the corresponding extracted-from-Simulation_fitted
   reference values.

6. **Provenance** — every parameter flows through
   `opencell/provenance/store.py::record_measured()` with the source
   citation (PMC ID, GitHub commit SHA, sheet/row, or PUB_xxxx evidence
   row). Output: `artifacts/M1_provenance.jsonl`.

7. **`docs/phase5/M1_central_carbon.md`** — the findings doc, citing
   every value and showing each validation criterion's
   pass/fail.

## What remains genuinely uncertain (NO synthesis required)

The plan has zero residual synthesis. The two design choices that
still need to be MADE (not synthesised) are:

- Subnetwork scope: pure central carbon (~20 reactions) vs central
  carbon + nucleotide salvage (~40 reactions) — pick by ATP-balance
  closure, not by guess.
- Whether to use Karr Vmax/Km values directly in pFBA cost
  function (legitimate sourced data) or just use stoichiometry +
  bounds (simpler, fewer moving parts).

Both are decidable empirically once the data is loaded; no values
are invented.

## Files to delete from this session

- `scripts/m1_inspect_kb.py` — exploratory inspection of
  knowledgeBase.mat, can be removed once the .mat path is permanently
  abandoned (it is opaque without MATLAB).
- `scripts/m1_inspect_wckb.py`, `scripts/m1_extract_wckb.py` — keep
  as reproducible extraction scripts; will be evolved into
  `scripts/karr_a4f_ingest_m1.py`.

## Source URLs

- iPS189 SBML: https://journals.plos.org/ploscompbiol/article/file?type=supplementary&id=info:doi/10.1371/journal.pcbi.1000285.s005
- Suthers 2009 paper: https://doi.org/10.1371/journal.pcbi.1000285 (PMC2633051, open access)
- WholeCell repo: https://github.com/CovertLab/WholeCell (commit `6cdee6b`)
- WholeCellKB repo: https://github.com/CovertLab/WholeCellKB (commit `10a9798`)
- Karr 2012 paper: https://doi.org/10.1016/j.cell.2012.05.044 (PMC3413483, open access)
