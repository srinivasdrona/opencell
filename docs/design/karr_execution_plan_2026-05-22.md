# Karr 2012 Whole-Cell Model — End-to-End Execution Plan for OpenCell

**Source:** Karr et al., 2012, *Cell* 150(2):389–401, DOI 10.1016/j.cell.2012.05.044 — read end-to-end via PMC3413483 on 2026-05-22.
**Author of this plan:** Copilot CLI (orchestrator), after reading the paper main text in full (not the supplementary methods Data S1 — see §9 below).
**Purpose:** Map OpenCell's current implementation against Karr's complete architecture, and produce a realistic phased plan to v1.0.

---

## 1. The Karr architecture (verbatim from the paper)

Karr divides *M. genitalium* (525 genes) into **16 cell state variables** integrated by **28 process sub-models**. Each tick is 1 second.

### 1.1 The simulation algorithm (paper § "Simulation Algorithm")

```
initialize cell state                                   # 16 state variables
loop until cell divides OR t > t_max:
    allocate shared resources among sub-models          # variable allocation step
    for each of the 28 sub-models:                      # PARALLEL ON 1s TICK
        sub-model reads its inputs (previous tick values)
        sub-model computes its updates
    update cell state                                   # commit all updates
    t += 1s
```

**Key assumption (paper):** "sub-models are approximately independent on short time scales (less than one second)... sub-models are run independently at each time step, but depend on the values of variables determined by the other sub-models at the previous time step."

This is the **one-tick-lag** property — confirmed by Probe 3 of our decision spike. Karr's architecture is fundamentally lag-coupled, not same-tick-coupled.

### 1.2 The 16 state variables (paper § "Sub-model Integration")

Confirmed by inspection of `data/karr_fixtures/per_process/` — Karr's fixture directory contains exactly 16 state structures:

| # | State variable | Karr description |
|---|---|---|
| 1 | `CellGeometry` | shape, volume, septum |
| 2 | `CellMass` | total mass, mass fractions |
| 3 | `Chromosome` | nascent DNA, replication state |
| 4 | `FtsZRing` | molecular machine |
| 5 | `Host` | host urogenital epithelium |
| 6 | `MetabolicReaction` | metabolic reaction fluxes |
| 7 | `Metabolite` | metabolite copy numbers |
| 8 | `Polypeptide` | nascent protein polymers |
| 9 | `ProteinComplex` | complex copy numbers |
| 10 | `ProteinMonomer` | mature protein copy numbers |
| 11 | `Ribosome` | molecular machine |
| 12 | `Rna` | RNA copy numbers |
| 13 | `RNAPolymerase` | molecular machine |
| 14 | `Stimulus` | environmental signals |
| 15 | `Time` | wall-clock + cell cycle stage |
| 16 | `Transcript` | nascent RNA polymers |

### 1.3 The 28 sub-models (paper § "Cellular Process Sub-models")

Karr describes them as spanning **6 functional areas**. Per the paper:

> "The sub-models spanned six areas of cell biology: (1) transport and metabolism, (2) DNA replication and maintenance, (3) RNA synthesis and maturation, (4) protein synthesis and maturation, (5) cytokinesis, and (6) host interaction."

Confirmed by fixture inspection — exactly 28 process fixtures exist:

| Area | Sub-models (Karr's process names) | Count |
|---|---|---|
| **1. Transport and metabolism** | `Metabolism` | 1 |
| **2. DNA replication and maintenance** | `ReplicationInitiation`, `Replication`, `DNADamage`, `DNARepair`, `DNASupercoiling`, `ChromosomeCondensation`, `ChromosomeSegregation` | 7 |
| **3. RNA synthesis and maturation** | `Transcription`, `TranscriptionalRegulation`, `RNAProcessing`, `RNAModification`, `RNADecay`, `tRNAAminoacylation` | 6 |
| **4. Protein synthesis and maturation** | `Translation`, `ProteinProcessingI`, `ProteinProcessingII`, `ProteinModification`, `ProteinFolding`, `ProteinActivation`, `ProteinDecay`, `ProteinTranslocation`, `MacromolecularComplexation`, `RibosomeAssembly` | 10 |
| **5. Cytokinesis** | `FtsZPolymerization`, `Cytokinesis` | 2 |
| **6. Host interaction** | `HostInteraction`, `TerminalOrganelleAssembly` | 2 |

**Total: 28** ✓

---

## 2. OpenCell current state — honest map against Karr's 28

| # | Karr process | OpenCell status | Where |
|---|---|---|---|
| 1 | `Metabolism` | ✅ **DONE (v1)** — Karr-native FBA, 645 reactions, per-reaction oracle PASSED | `opencell/m1/karr_metabolism.py` + `opencell/vivarium/karr_m1.py` |
| 2 | `Transcription` | ✅ **v1 DONE; v2 MECHANISM SHIPPED BUT NOT WIRED** — A3 step 2 in flight | `opencell/m2/transcription.py`, `transcription_v2.py`, `opencell/vivarium/karr_m2.py`, `karr_m2_v2.py` (in progress on `agent/v2-chassis-swap-...`) |
| 3 | `Translation` | ✅ **v1 DONE; v2 MECHANISM SHIPPED BUT NOT WIRED** — A3 step 2 in flight | Same pattern as Transcription |
| 4 | `MacromolecularComplexation` | 🟡 **STUB SHIPPED (snapshot loader); REAL IN A3 STEP 3** | `opencell/vivarium/karr_d2_stub.py` (on `agent/d2-stub`) → D.2-real coming |
| 5 | `RibosomeAssembly` | 🟡 **PARTIAL (30S/50S only, in d2-stub); 70S+30S_IF3 deferred to Translation v2** | Same as above |
| 6 | `ProteinDecay` | 🟡 **QUEUED as ProteinDecay-light in A3 step 3** | Joint design with D.2-real |
| 7 | `RNADecay` | ❌ **NOT STARTED** | — |
| 8 | `RNAProcessing` | ❌ **NOT STARTED** | — |
| 9 | `RNAModification` | ❌ **NOT STARTED** | — |
| 10 | `tRNAAminoacylation` | ❌ **NOT STARTED** | — |
| 11 | `TranscriptionalRegulation` | ❌ **NOT STARTED** (todo `m6-regulation` covers this) | — |
| 12 | `ProteinProcessingI` | ❌ **NOT STARTED** | — |
| 13 | `ProteinProcessingII` | ❌ **NOT STARTED** | — |
| 14 | `ProteinModification` | ❌ **NOT STARTED** | — |
| 15 | `ProteinFolding` | ❌ **NOT STARTED** (D.3 placeholder in plan) | — |
| 16 | `ProteinActivation` | ❌ **NOT STARTED** (D.4 placeholder) | — |
| 17 | `ProteinTranslocation` | ❌ **NOT STARTED** | — |
| 18 | `ReplicationInitiation` | ❌ **NOT STARTED** (todo `m5-replication-cellcycle` covers this) | — |
| 19 | `Replication` | ❌ **NOT STARTED** | — |
| 20 | `DNADamage` | ❌ **NOT STARTED** | — |
| 21 | `DNARepair` | ❌ **NOT STARTED** | — |
| 22 | `DNASupercoiling` | ❌ **NOT STARTED** | — |
| 23 | `ChromosomeCondensation` | ❌ **NOT STARTED** | — |
| 24 | `ChromosomeSegregation` | ❌ **NOT STARTED** | — |
| 25 | `FtsZPolymerization` | ❌ **NOT STARTED** | — |
| 26 | `Cytokinesis` | ❌ **NOT STARTED** | — |
| 27 | `HostInteraction` | ❌ **NOT STARTED** | — |
| 28 | `TerminalOrganelleAssembly` | ❌ **NOT STARTED** | — |

### Headline numbers

- **Fully implemented (v1):** 1 (Metabolism)
- **Implemented but not chassis-wired (v2):** 2 (Transcription, Translation — wiring in flight as A3 step 2)
- **Stubbed (snapshot-loaded, no dynamics):** 2 (MacromolecularComplexation, RibosomeAssembly via d2-stub)
- **Queued (joint A3 step 3):** 2 (D.2-real, ProteinDecay-light)
- **Not started:** 21 of 28 processes

### Honest assessment

After A3 ships completely (~6 weeks projected), OpenCell will have ~6 of 28 sub-models with real dynamics. That's **21%** of Karr's architecture. The current plan's "v1.0 release after M7 / Karr-equivalent validation" framing was always undershooting Karr-equivalent — it would not pass Karr's validation phenotypes which depend on cell cycle, DNA replication, RNA maturation, and the long tail of protein processing.

---

## 3. Karr validation phenotypes — coverage analysis

The paper validates against these phenotype categories (from §"Model validation against independent experimental data" and §"Identification of metabolism as an emergent cell cycle regulator"):

| Phenotype | Karr's result | What it requires | Reachable with current trajectory? |
|---|---|---|---|
| Doubling time | 9.36 ± 1.9 h | Full cell cycle: ReplicationInitiation → Replication → Cytokinesis | ❌ requires ~5 new processes |
| Cellular chemical composition | ✓ matches Morowitz 1962 | All biomass-contributing processes including DNA | ❌ DNA mass fraction needs Replication |
| Mass fractions over time | ✓ each fraction doubles over cycle | Full cell cycle + all biomass producers | ❌ requires cell cycle |
| Gene expression (R² = 0.68) | ✓ matches training data | Transcription + RNADecay + RNAProcessing + TranscriptionalRegulation | 🟡 partial (Transcription v2 only) |
| Metabolic fluxes | ✓ glycolysis >100× PPP/lipid | Metabolism | ✅ already passes |
| Metabolite concentrations | ✓ within 1 OOM of *E. coli* (100% / 70%) | Metabolism + closed loop with all consumers | 🟡 partial |
| Burst-like protein synthesis | ✓ matches Yu 2006, So 2011 | Translation v2 + ProteinDecay + RNADecay | 🟡 partial after A3 |
| mRNA/protein distributions | ✓ matches Taniguchi 2010 | Transcription v2 + Translation v2 + decays + degradation | 🟡 partial |
| DNA-binding protein dynamics | ✓ 50% chromosome bound in 6 min | Replication + Transcription + DNASupercoiling + ChromosomeCondensation | ❌ |
| Cell cycle phase durations | ✓ initiation 64.3%, replication 38.5%, cytokinesis 4.4% variability | ReplicationInitiation + Replication + Cytokinesis | ❌ |
| dNTP-replication coupling | ✓ inverse-correlated phase durations | Replication + Metabolism (for dNTP pool) | ❌ |
| ATP/GTP synthesis & usage | ✓ ATP/GTP 1000× FAD(H₂)/NAD(H) | Metabolism + Transcription + Translation closed loop | ✅ partially after A3 |
| Gene essentiality (79% acc.) | ✓ 525 single-gene disruptions | **ALL 28 sub-models** (every gene affects at least one) | ❌ requires full architecture |
| Single-gene disruption phenotypes | ✓ 5 classes | All 28 sub-models | ❌ |
| `lpdA`/`thyA`/`deoD` discoveries | ✓ Nox substrate promiscuity, Tdk/Pdp kcats | All 28 sub-models | ❌ |

### Reachable subset

Even if A3 ships perfectly, we cover Karr phenotypes in 3 categories (metabolic fluxes, partial composition, ATP/GTP usage) and partially-cover 4 more. The other 8 categories — including the headline ones (doubling time, cell cycle, gene essentiality) — require new processes.

---

## 4. The realistic phased plan

OpenCell's current todo set has placeholders for M5 (replication+cellcycle), M6 (regulation), M7 (validation). The map above shows these are aggregating multiple Karr processes — they're not 3 small modules, they're **~22 modules grouped into 3 buckets**. Let me decompose properly.

### Phase A3 (current, in flight) — Producer-degrader-consumer closed loop

| Step | Karr process(es) | Status |
|---|---|---|
| A3.1 `d2-stub` | MacromolecularComplexation (placeholder) | ✅ done |
| A3.2 `v2-chassis-swap-dynamic-pool-discipline` | Transcription v2, Translation v2 wired | 🟡 in flight (Codex) |
| A3.3 `d2-real-plus-protein-decay-light` | MacromolecularComplexation (real), ProteinDecay | ⏳ queued |

**End of A3:** 6/28 processes real (21%). Phenotypes p5-p10 graduate from circular to real. Metabolic + RNA + protein closed loop runs in steady-state.

### Phase B — RNA and Protein maturation (the "stable-cell" closure)

The chassis after A3 will compute steady-state protein/RNA correctly, but cannot accumulate cellular components over a cycle (no decay-balance for stable RNAs, no folding/processing for nascent proteins). To get a *stable cell at steady state with real dynamics*, we need:

| Order | Karr process | Why now |
|---|---|---|
| B.1 | `RNADecay` | Without it, RNAs accumulate forever. Closes the RNA loop already started in Transcription v2. Simple Poisson process per Karr (paper §"Cellular Process Sub-models"). |
| B.2 | `tRNAAminoacylation` | Translation v2 will need *charged* tRNAs (not just raw). Without this, AA availability is wrong. |
| B.3 | `RNAProcessing` | Many tRNAs and rRNAs are processed post-transcription. Mature counts in Translation depend on this. |
| B.4 | `RNAModification` | Some tRNAs need methylation/etc. before being functional. Coupling with B.2. |
| B.5 | `ProteinProcessingI` | Signal peptide cleavage and N-terminal modification — required for many proteins to be functional. |
| B.6 | `ProteinProcessingII` | Disulfide formation, folding into final tertiary structure. |
| B.7 | `ProteinFolding` | Chaperone-assisted folding for ~30% of proteins. Karr paper § "ProteinFolding" implements this with chaperone-capacity kinetics. |
| B.8 | `ProteinModification` | Post-translational modifications (phosphorylation, glycosylation). |
| B.9 | `ProteinTranslocation` | Membrane vs cytosolic destination. Most proteins live in one compartment. |
| B.10 | `ProteinActivation` | Many enzymes need a cofactor / metal / prosthetic group activation step beyond MacromolecularComplexation. |

**Phase B total: 10 new processes.** Brings coverage to 16/28 (57%).

After Phase B: a steady-state cell with realistic RNA + protein dynamics. Still no cell cycle.

### Phase C — DNA replication and cell cycle (the "growth and division" loop)

| Order | Karr process | Why now |
|---|---|---|
| C.1 | `ChromosomeCondensation` | SMC-based; required as a state-baseline for replication |
| C.2 | `DNASupercoiling` | Required for replication geometry |
| C.3 | `ReplicationInitiation` | DnaA polymerization at oriC — Karr paper § Fig 4B; this is the cell cycle starting gate |
| C.4 | `Replication` | DNA polymerase elongation; dNTP-bounded per Karr §"emergent cell cycle regulator" |
| C.5 | `ChromosomeSegregation` | Daughter chromosome separation |
| C.6 | `FtsZPolymerization` | Division ring assembly |
| C.7 | `Cytokinesis` | Final division step |
| C.8 | `DNADamage` | Constant background damage rate (often spontaneous) |
| C.9 | `DNARepair` | Repair processes; needed for cell viability simulations |
| C.10 | `TranscriptionalRegulation` | TFs that respond to cell-cycle / environmental cues |

**Phase C total: 10 new processes.** Brings coverage to 26/28 (93%).

After Phase C: a cell that can grow, replicate, divide. This is the **earliest point Karr's doubling-time phenotype is reachable**.

### Phase D — Host interaction and terminal-organelle (the *M. genitalium*-specific bits)

| Order | Karr process | Why now |
|---|---|---|
| D.1 | `HostInteraction` | *M. genitalium* attaches to urogenital epithelium — cell biology specific to this pathogen |
| D.2 | `TerminalOrganelleAssembly` | Specialized cell-pole structure for host attachment and motility |

**Phase D total: 2 new processes.** Brings coverage to 28/28 (100%).

After Phase D: full Karr architecture. v1.0 release. Karr-equivalent validation can begin.

### Phase E — Validation against Karr's 28 phenotypes (the L4 paper proper)

After Phase D, we can attempt Karr's full validation suite: gene essentiality screening (525 disruptions × ≥5 runs each = ~3,000 simulations), cell cycle phenotypes, energy distribution, single-gene-disruption pathology classification, and the `lpdA`/`thyA`/`deoD` model-discovery loop.

---

## 5. Realistic effort estimates per phase

Honest assessment based on:
- The historical record: M1 took ~6 weeks; M2v2 + M3v2 mechanism modules took ~3 weeks each; D.2 design alone has consumed 4 rework cycles over 2 weeks
- Karr complexity heuristic: process complexity scales roughly with number of substrate WIDs + number of catalysis-bound enzyme WIDs in its fixture
- LLM-assisted development with the established methodology (Codex executor + Copilot architect)

| Phase | Processes | Est. wall-clock effort | Cumulative |
|---|---|---|---|
| A3 (now) | 3 substeps | 6 weeks total (~4 weeks remaining after A3.2 ships) | week 4 |
| B (RNA + protein maturation) | 10 processes | ~12 weeks (mix of simple and complex; e.g. RNADecay ~1 week, ProteinFolding ~2 weeks) | week 16 |
| C (DNA + cell cycle) | 10 processes | ~14 weeks (Replication itself is ~3 weeks; ReplicationInitiation ~2 weeks; cell cycle integration is non-trivial) | week 30 |
| D (host + organelle) | 2 processes | ~3 weeks | week 33 |
| E (Karr validation) | 0 new processes; ~28 phenotype tests | ~4 weeks | week 37 |

**Honest range for v1.0: 37 ± 6 weeks from today.** ~9 months.

Previous plan's "v1.0 by end August 2026" estimate (~14 weeks from today) was undershooting by ~6 months because it didn't account for the 22 unimplemented sub-models. The earlier plan assumed M5/M6/M7 were small modules; they're actually large buckets each containing multiple Karr processes.

---

## 6. Critical dependencies surfaced by paper-reading

The Karr paper makes several architectural decisions we should adopt explicitly:

### 6.1 Variable allocation step (the "resource ledger")

> "the common inputs to the sub-models were computationally allocated at the beginning of each time step" (paper § Sub-model Integration)

OpenCell has a partial `resource_ledger.py` (per `p1-ledger` in plan.md). I haven't deeply audited it against Karr's allocation strategy. **This is a piece that may need rework as we add processes that compete for the same substrates** (e.g., RNA polymerase competing for NTPs across Transcription + replication).

### 6.2 Parameter reconciliation as a final integration step

> "we refined the values of the sub-model parameters to make the sub-models mutually consistent" (paper § Sub-model Integration)

This is a global tuning step Karr did *after* every sub-model worked in isolation. OpenCell currently does no such global reconciliation. Our `bounded-tuning policy` (per `copilot-instructions.md`) implies parameter changes happen per-module with biological-range justification — Karr's approach was different (parameters were reconciled across processes to match data, not pulled from primary measurements alone). This is a **methodology question** the L4 paper will need to address: did we follow Karr's reconciliation, or stay strict per-module?

### 6.3 Sub-model independence is bounded by 1-second timestep

> "we began with the assumption that the sub-models are approximately independent on short time scales (less than one second)" (paper § Whole-cell model construction)

This justifies the 1-second tick architecture but also explains why all processes must be computationally cheap (must complete in << 1s of simulator wall time × 30000s of cell life = 8 cell-hours). OpenCell needs **performance budgets per process** before Phase B (per todo `a8-performance-budget` which is done — verify it still applies post-D.2).

### 6.4 192 wild-type + 3011 single-gene disruption simulations

> "We used the whole-cell model to simulate 192 wild type cells and 3,011 single-gene deletants. All simulations were performed with MATLAB R2010b on a 128 core Linux cluster."

Karr ran ~3,200 simulations × ~9h each = ~28,800 CPU-hours on a 128-core cluster (~9 wall-days). OpenCell needs an analogous ensemble runner. The `p3-morris` and `p6-sensitivity` todos cover some of this. **A scaling test against Karr's runtime per cell** belongs in our `p5-perf` work — current single-cell runtime is the proxy.

### 6.5 The 44% energy discrepancy is in Karr — not a bug to fix

> "we also found a large (44%) discrepancy between total energy usage and production... and the model's prediction estimates the total energy cost of such uncoupling."

OpenCell may reproduce this discrepancy (or fail to). It's not a model bug; it's a *prediction*. The L4 paper should highlight whether we reproduce this Karr finding.

---

## 7. Methodology learnings for the L4 paper

Reading the paper end-to-end clarified what L4 should claim:

1. **"LLM-assisted port of Karr 2012 to Python":** the LLM's role is most useful for: (a) translation of MATLAB algorithms to Python, (b) cross-model design critique (catches what one model misses), (c) execution loops that don't need architectural reasoning. The paper-reading step itself was Copilot's job, not Codex's.

2. **The methodology fault we keep hitting:** designing from summaries instead of primary sources. v1→v2 (paper summaries), v2→v3 (JSON fixture summaries), v3→v4 (MATLAB source). And this very plan was almost written without reading the paper. Each level of indirection introduces a Bayesian-prior error that compounds. **Primary source reading is non-negotiable** — and it should happen *before* designing, not as critique-driven correction.

3. **Cross-model critique catches what single-model design misses:** documented 4× now (Sonnet on v1, GPT-5.4 on v2, Opus 4.6+GPT-5.5 on v3, Opus 4.6+GPT-5.5+Sonnet 4.6 on v4). Without this gate, we ship designs with architectural BLOCKERs.

4. **Karr-fidelity is the project's purpose, not a tradeoff variable:** L4 paper's experimental claim hinges on faithful reproduction. Optionality on this (target-clamp controllers, decay-absorbed-into-D.2) was incorrectly framed earlier as "options" — they're abandonments of the project's purpose.

5. **The 28-process architecture forces process-level discipline.** Each process has its own MATLAB source, its own fixture, its own algorithm. The pattern that works: read the .m source via `_flat.mat` extraction (the d2-spike-validated pattern) → cross-model critique a 1-page design → Codex implements → orchestrator validates → commit.

---

## 8. Immediate next steps (what changes today)

### 8.1 Acknowledge the scope gap

Update `plan.md` Current Status to reflect that we're at 6/28 sub-models after A3, with 22 more to go for full Karr fidelity. v1.0 is ~9 months, not ~3 months.

### 8.2 Decompose M5/M6/M7 into Karr processes

Current todos `m5-replication-cellcycle`, `m6-regulation`, `m7-karr-validation` are aggregate placeholders. They should be decomposed into the 20 processes of Phases B+C (Karr's actual architecture) plus the final validation step.

### 8.3 Re-prioritize against Phase B order

After A3 ships, the next-actionable should be **RNADecay** (Phase B.1) — simplest, immediately closes the RNA loop already started by Transcription v2. Not ReplicationInitiation (which would be Phase C; significantly more complex; no payoff without other Phase B processes for steady-state).

### 8.4 Build a per-process complexity gauge

The 22 remaining processes are not equal effort. Audit each `_flat.mat` fixture's complexity (key counts, substrate WIDs, enzyme WIDs) and use that to estimate effort. This sharpens the Phase B/C/D estimates.

### 8.5 Read Data S1 (the supplementary methods)

This plan was written from the **paper main text** + fixture inspection. The detailed per-process algorithmic descriptions live in Data S1 (Supplementary Information). For Phase B onwards, the architect (Copilot) should read Data S1 in full *before* designing each Karr process. **This is the same lesson as the D.2 methodology shift, applied prospectively.**

---

## 9. What this plan does NOT cover yet

Be honest about gaps:

1. **Data S1 (Supplementary Methods).** The 28-process algorithmic details live here. I haven't read it. Must be done before designing Phase B.1 (RNADecay).
2. **Per-process fixture-complexity audit.** Will sharpen Phase B/C/D estimates.
3. **Cross-process dependency graph.** Karr describes integration via 16 state variables, but the specific producer→consumer relationships for each variable need a table. Phase B order assumes I've got this roughly right.
4. **Performance budget revalidation.** With 22 more processes, the 1-second tick has 22× more work. Need to check whether OpenCell's current per-process timing (mostly sub-millisecond) scales.
5. **Variable-allocation strategy details.** §6.1 — Karr's specific allocation algorithm for substrates competing across processes.
6. **Parameter reconciliation methodology.** §6.2 — Karr's iterative tuning approach. Does our bounded-tuning policy align with what Karr actually did, or is it a more conservative subset?

These six follow-ups should be captured as concrete todos.

---

## 10. The headline takeaway

**OpenCell is currently ~21% of Karr's architecture by sub-model count.** The remaining 79% is 22 processes grouped into Phases B (RNA/protein maturation, 10 processes), C (DNA/cell cycle, 10 processes), and D (host interaction, 2 processes). Estimated wall-clock to full Karr-equivalent v1.0: **~9 months from today**, not the previously-implied ~3 months.

This was knowable from reading the paper at the start of the project — the indication is in Figure 1A's count of 28 colored sub-model names. Reading the paper end-to-end now means future design rounds can be planned against the full architecture rather than discovered piecemeal.
