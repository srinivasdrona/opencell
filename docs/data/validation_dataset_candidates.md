# Empirical validation candidates for the coupled Chassagnole + Vilar model

## STRATEGIC PIVOT (2026-04-24, user input)

The user proposed a sharper architectural direction that supersedes the
"keep adding hand-coded sub-models" thread (Phase 5 in the plan):

> Don't write a 100-gene model from scratch — extract a 100-gene functional
> core from a highly trusted, validated genome-scale model. Target organism:
> *Mycoplasma genitalium* (or *M. pneumoniae*). Filter for genes that are
> (a) essential for metabolic flux (e.g. central glycolysis), and
> (b) essential for transcription/translation (the absolute minimum machinery).

### Why this beats the current "build" path

* M. genitalium / pneumoniae are already minimal; no thousands of redundant
  housekeeping genes to trim. M. genitalium has 482 genes total of which
  ~382 are individually essential; JCVI-syn3.0 (the synthetic minimal) has
  473; JCVI-syn3A has ~493.
* Extracting ~100 genes from a curated GPR matrix is *finite work*; writing
  100 genes by hand is *unbounded debugging*. Errors in hand-built kinetics
  make solver bugs unfindable.
* Modular framework: if our chassis is right, plugging in the full syn3A
  model later is the same shape of task as plugging in the Core 100.

### North Star: JCVI-syn3A 4D simulation (Luthey-Schulten group)
* Modern industry benchmark for "minimal whole cell" — full spatial
  (Lattice Microbes, GPU) + temporal simulation. Cell 2022 paper:
  Thornburg et al., "Fundamental behaviors emerge from simulations of
  a living minimal cell" (DOI: 10.1016/j.cell.2021.12.025).
* We don't compete with this. We aim to be the *open, pythonic,
  architecturally-modular* framework on which the Core 100 →
  full-syn3A path is reproducible end-to-end.

### Validation invariant (per user)
**Stable, predictable growth curve** (biomass accumulation over the
cell-cycle horizon). If the Core 100 doesn't produce a sensible growth
curve, the gene set is wrong (or the kinetics are).

### Resolution (2026-04-24, end of strategic-pivot session)

After three rounds of adversarial critique the project committed to:
* **Chassis**: vivarium-core (Apache 2.0). Solvers become Vivarium Processes.
* **Target**: Karr-equivalent M. genitalium WCM in Python, subsystem-by-subsystem
  via the new Phase A/M/L/E/Z ladder in plan.md.
* **Source mix**: iPS189 (BiGG, SBML) for structure + Karr 2012 .mat files
  for kinetics (extracted via scipy.io). WholeCellKB if accessible.
* **Validation invariant**: replicate ≥10 of Karr's 28 published phenotypes
  within his error bars (M7 milestone). Growth rate is necessary but not
  sufficient.
* **Methodology contribution**: LLM-assisted MATLAB→Python translation +
  parameter curation, productised as Phase L (l1-l4 todos).
* **De-scoped**: differentiable JAX engine, GPU drug screens, autonomous
  agent curation, drug discovery, eukaryote completeness. All overpromise.
* **Frozen artefact**: Chassagnole+Vilar coupled model retained as
  architectural regression test, not extended.

See plan.md "Strategic Direction (2026-04-24)" section and
files/source_inventory_2026-04-24.md for the full survey + critique chain.

### Concrete starting actions (next session)

1. **Pick the source GPR.** Two solid options:
   - Suthers et al. 2009 *iPS189* — published M. genitalium GSM in COBRA
     format, ~189 reactions / 274 metabolites. Smaller, easier to prune.
   - Karr et al. 2012 WCM repository — has the M. genitalium GPR plus
     curated kinetics for transcription/translation/replication. Larger
     but already includes the central-dogma machinery we'd otherwise
     have to add by hand. (DOI: 10.1016/j.cell.2012.05.044)
   - JCVI-syn3A model files from the Luthey-Schulten group's GitHub
     (`Lattice-Microbes/MinCell` or similar) — already 473-gene
     curated, would need only down-selection not augmentation.
2. **Define the Core 100 selection criteria** as a single SQL/CSV filter:
   - essential = TRUE in single-gene KO experiments (482→382 set)
   - belongs to one of: glycolysis, PPP, nucleotide biosynthesis,
     amino-acid biosynthesis (only if essential), tRNA synthetases,
     ribosomal proteins (subset), RNAP subunits, σ-factor, key
     replication initiation/elongation
3. **Anchor with a growth-curve invariant**: even before the model is
   complete, decide what "growth" means in our framework
   (biomass = sum-of-essential-monomers? Karr-style? Just total protein?).
4. **Map to existing chassis**: our `SbmlOdeModel` + `TranscriptionModel`
   + `MetabolismModel` + `CoupledMetabolismTranscription` already cover
   the metabolism + transcription primitives. The gap is translation
   + replication + biomass aggregation. Build these on the same chassis,
   not as bespoke modules.

### Open questions to resolve before building

* Which GSM source? (decision feeds everything else)
* Continuous growth model (chemostat-style) or discrete cell cycle
  (one division event)? Affects how we measure "growth curve".
* Do we keep Vilar in the picture as a "decorative" regulatory motif on
  top of the Core 100, or drop it once we have real M. genitalium genes?

---

## Original empirical-comparison candidates (still useful for the
## Chassagnole+Vilar artifact even if Core 100 is the new main thread)

Triaged into "ideal", "plausible", and "fallback". Decision criterion:
does the dataset measure something the **coupled** model produces? The
sub-models individually have anchors; the composite does not.

## Top candidates (read order)

### 1. Chassagnole 2002 — Figs 5 & 6 (the model's own calibration data)
- **What:** Glucose-pulse time courses for ~15 intracellular metabolites
  in batch *E. coli* W3110, measured at sub-second to second resolution
  via in-vivo NMR / rapid sampling. Already used by the authors to
  fit the model parameters.
- **Fits what:** Metabolism-only validation. Confirms our `MetabolismModel`
  reproduces published behaviour (we already pass libroadrunner oracle;
  this would add an *experimental* anchor on top).
- **Effort:** Low. Data are in the paper supplement (Tables/figures);
  digitise once.
- **Catch:** Doesn't validate the coupling, only the metabolism leg.
- **DOI:** 10.1002/bit.10288

### 2. Bettenbrock et al. 2006 — PTS dynamics under glucose pulse
- **What:** Time-resolved measurement of PTS-system phosphorylation
  state, glucose uptake flux, and intracellular glucose-6-P after a
  glucose pulse to glucose-starved *E. coli*. Measured EIIA~P, glucose,
  G6P over 30 min.
- **Fits what:** Validates our PTS-flux→f_met coupling pathway directly.
  This is the closest published dataset to what our model claims.
- **Effort:** Medium. Two figures to digitise; need to align units
  (their per-cell vs Chassagnole's per-volume) — pint-validatable.
- **Catch:** No transcription readout. Validates the metabolism→signal
  arm but leaves the signal→synthesis arm unvalidated.
- **DOI:** 10.1074/jbc.M512868200

### 3. Taniguchi et al. 2010 — single-cell mRNA + protein distributions
- **What:** mRNA and protein copy-number distributions for 1018 *E. coli*
  genes across 4 growth conditions, single-cell. Reports CV vs mean
  (Fano factor), which is the canonical observable for stochastic
  gene-expression models.
- **Fits what:** Validates the *noise structure* of the Vilar tau-leap
  output (do our hybrid runs reproduce realistic CV-vs-mean scaling?).
- **Effort:** Medium-low. Supplement has the full table.
- **Catch:** Steady-state, not dynamics. Closest if we want to test
  whether tau-leap statistics are biologically reasonable.
- **DOI:** 10.1126/science.1188308

### 4. Schmidt et al. 2016 — *E. coli* proteome under 22 conditions
- **What:** Quantitative proteome (counts per cell) of all detectable
  *E. coli* proteins across glucose/acetate/glycerol/etc.
- **Fits what:** Anchors our R/A/C absolute counts to a sanity range
  for a real bacterial regulator. Bulk, not dynamics.
- **DOI:** 10.1038/nbt.3418

## Fallback: Karr 2012 *M. genitalium* subset

If none of the above can be matched within a one-day spike, fall back
to using a slice of the Karr WCM dataset:

- **What's available:** Karr et al. published full single-cell time
  courses (~100 observable species, 50,000+ time points per cell, ~100
  replicate cells) at <https://www.wholecell.org/> (mirrored on figshare).
- **Best subset for our coupled model:**
  - `metabolicReaction` fluxes (analogue of PTS flux)
  - `Rna` counts for any one constitutively-expressed gene
  - `ProteinMonomer` counts for the same gene
- **Fits what:** Directly comparable observables to our coupled output
  (metabolic flux + mRNA + protein time series in a single cell).
- **Effort:** Medium-high. Karr's dataset uses HDF5; we'd need a small
  loader and a unit-mapping table to align with our (mM, molecules/cell)
  conventions.
- **Catch:** *M. genitalium* not *E. coli*; volumes, growth rates, and
  proteome composition all differ. Use as relative-shape comparison,
  not absolute calibration.
- **DOI:** 10.1016/j.cell.2012.05.044

## Recommended order for next session

1. **Quick sanity (1-2 h):** Digitise Chassagnole Fig 5 (glucose,
   G6P, PEP, PYR time traces), overlay our metabolism-only run.
   Even if it just confirms what libroadrunner already tells us,
   it gives us a publishable-quality experimental comparison figure.
2. **The real prize (4-6 h):** Bettenbrock 2006 PTS data. Validates
   the f_met signal directly. If our PTS flux time course matches,
   the coupling architecture has empirical legs even if Vilar doesn't.
3. **If both above stall:** Pivot to Karr subset. Build a loader for
   one species pair (metabolic flux + one mRNA + one protein) from
   the Karr HDF5, compare against our coupled hybrid output.

## Decision rule

If after one full day's work **no single experimental anchor** can be
found for the coupling itself, then either:
- swap Vilar for a *real* E. coli regulator (e.g., the lac operon,
  which has decades of glucose-shift data), or
- accept that this is an architectural demo and move on to scaling
  (more sub-models / more species), documenting the limitation
  explicitly in the README.

We do not fabricate validation data.
