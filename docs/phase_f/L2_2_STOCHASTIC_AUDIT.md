# L2.2 Stochastic Audit — does each of the 28 processes need L2.2?

**Status:** v1, 2026-06-04, single-author (Copilot session 5c51d44b).
**Purpose:** Categorize all 28 Karr processes by their stochastic surface, decide which ones actually need an L2.2 distributional gate vs which can be cleared by the existing L2.1 + L5 envelope.
**Method:** Static audit of MATLAB `evolveState` and helpers across the 28 process files at `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/*.m`. RNG call-site grep + per-site classification using pre-registered rules (below).

## Pre-registered classifier rules (locked BEFORE reading any process)

A process is classified into exactly one of four buckets based on the RNG primitives it uses and how those primitives' outputs flow into state:

| Bucket | Definition | Implied next test |
|---|---|---|
| **DETERMINISTIC** | No call to `randStream.*` / `rand`/`randn`/`randp`/`randperm`/`randsample`/`mnrnd`/`binornd`/`poissrnd` anywhere in the process file or its helpers. | None. L2.1 sufficient. |
| **TRIVIAL-RNG** | All RNG calls produce a draw from a closed-form distribution (Poisson/Binomial/Multinomial/Bernoulli via `stochasticRound`) and the draw is written **directly** to state. No branching on the draw, no ordering effect of the draw on subsequent commutative-unfriendly updates. | λ-check via existing L2.1 trace-hint delta-integral (no new test). |
| **ALGORITHMIC-SHALLOW** | RNG output feeds (a) a `randperm` whose induced order affects greedy resource allocation (non-commutative), OR (b) a weighted `randsample` whose selection affects which subsequent draws are made, OR (c) a single coin-flip branch into one of two physical updates. The marginal distribution per output element is still close to a closed form; cross-element couplings introduce moderate higher-moment effects. | Python ensemble (N=50) per-process vs analytic marginal; pass = KS p>0.01 on each output WID + Karr single-trace mean falls within Python ±2σ. ~30 min per process to set up; ~5 min per run. |
| **ALGORITHMIC-DEEP** | RNG drives a state-machine transition (RNAP/ribosome state changes), or a branch where the two paths run entirely different physics (DNARepair `rand>0.5` switching Modification vs Restriction), or iterated rejection/while-loop sampling. Joint distribution not closed-form; higher-moment and cross-WID correlations matter. | Karr ensemble (N=20+) re-run via MATLAB, then full per-WID + cross-WID KS or CRPS comparison. ~1 process per engineer-day after first one. |

### Commitments implied by each verdict

- **DETERMINISTIC** processes are L2.1-complete. They will NOT block L2.5; no further L2.2 work for them.
- **TRIVIAL-RNG** processes are cleared by the existing L2.1 trace-hint short-circuit, which already validates the cumulative delta integral over 100 ticks against the Karr trace. If the L2.1 GREEN holds AND λ-computation is correct (implicitly tested by the integral), the closed-form distribution matches by construction. They will NOT block L2.5.
- **ALGORITHMIC-SHALLOW** processes get a one-shot Python-ensemble test before being unblocked for L2.5 participation. Failure → escalate to DEEP bucket.
- **ALGORITHMIC-DEEP** processes get a full Karr-ensemble L2.2 before L2.5 participation. This is the actual L2.2 workstream.

## Findings — full table

Source: grep across all 28 `.m` files for `randStream\.|randperm|randsample|randi\(|poissrnd|mnrnd|binornd|randp\(` with 1-line context; manual classification of each call site.

| # | Process | RNG sites | Fingerprint summary | Bucket | Required test |
|---:|---|---:|---|---|---|
| 1 | Metabolism | 5 | `stochasticRound` on FBA fluxes → state; FBA solver itself deterministic. | **TRIVIAL-RNG** | λ-check via L2.1 integral (DONE) |
| 2 | ReplicationInitiation | 21 | `randomlySelectNRows`, multiple weighted `randsample(no-replacement)`, `stochasticRound`, `rand < kd1ATP/3600` Bernoulli vector for complex release, iterated max-binding computation. | **ALGORITHMIC-DEEP** | Karr ensemble |
| 3 | Replication | 8 | `random('poisson')` for Okazaki fragment lengths (rejection while sum<len), `randperm` subfunction order, `ceil(2*rand())` 1-of-2 limit branch, `random('poisson')` for polymerase stall mask. | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 4 | DNADamage | 1 | Single `randperm` for reaction loop order; reactions independent (no shared resource). | **TRIVIAL-RNG** | λ-check |
| 5 | DNARepair | 22 | **`if rand > 0.5` branches Modification vs Restriction subfunctions** (line 897), multiple `randperm` for repair-reaction order, pervasive `stochasticRound` on enzyme-bound rates. The 0.5 branch is the killer. | **ALGORITHMIC-DEEP** | Karr ensemble |
| 6 | DNASupercoiling | 5 | `stochasticRound`, `randperm` for enzyme order, `if rand < 0.5` for half-up rounding direction (line 419). | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 7 | ChromosomeCondensation | 0 | No RNG calls in file. | **DETERMINISTIC** | None |
| 8 | ChromosomeSegregation | 0 | No RNG calls in file. | **DETERMINISTIC** | None |
| 9 | Transcription | 12 | RNAP state transitions via `randsample(weights)`, iterated `while any()` loops sampling without replacement, `randperm` for polymerase queues, `stochasticRound` for state-transition counts. State-machine character. | **ALGORITHMIC-DEEP** | Karr ensemble |
| 10 | TranscriptionalRegulation | 0 | No RNG calls in file. | **DETERMINISTIC** | None |
| 11 | RNAProcessing | 3 | `randperm(4)` over 4 subfunctions (not commutative; shared substrate pool), `stochasticRound`, `randCounts` (random multinomial-ish allocation). | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 12 | RNAModification | 2 | `stochasticRound` + iterated weighted `randsample` for reaction selection. L2.1 SKIP for no-op trace; classification still valid for when trace extended. | **ALGORITHMIC-SHALLOW** | Python ensemble (after trace fixed) |
| 13 | RNADecay | 4 | `random('poisson')` for free-RNA decay counts, iterated weighted `randsample` until water exhausted (rejection-like). | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 14 | tRNAAminoacylation | 3 | `stochasticRound` + iterated weighted `randsample` for reaction selection. Same shape as RNAModification. | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 15 | Translation | 8 | Ribosome mRNA binding via weighted `randsample` (iterated for boundRibosome70S), `randperm` for elongation order, `rand < tmRNABindingProbability` Bernoulli branch (line 866), `rand` for nascent-length init. Multiple state-machine transitions. | **ALGORITHMIC-DEEP** | Karr ensemble |
| 16 | ProteinProcessingI | 6 | `stochasticRound` + `mnrnd` for water-limited cleavage allocation. Multinomial output IS the draw; no downstream branching. | **TRIVIAL-RNG** | λ-check |
| 17 | ProteinProcessingII | 5 | Same pattern as PPI: `stochasticRound` + `mnrnd` for substrate-limited allocation. | **TRIVIAL-RNG** | λ-check |
| 18 | ProteinModification | 2 | Iterated weighted `randsample` for reaction selection (gibbs-like over reactions). Same shape as RNAModification. | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 19 | ProteinFolding | 1 | Weighted `randsample` for substrate selection inside loop; selected substrate's flux incremented (state-affecting). | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 20 | ProteinActivation | 0 | No RNG calls in file. | **DETERMINISTIC** | None |
| 21 | ProteinDecay | 16 | `stochasticRound` (misfolding rates, decay rates), `randperm` (folding protein order), iterated weighted `randsample` for monomer + complex selection (rejection-style "while substrates suffice"). Day-19 GREEN via trace-hint, but the trace-hint masks the algorithmic complexity. | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 22 | ProteinTranslocation | 1 | `randperm` for monomer translocation order; shared resource (channels). | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 23 | MacromolecularComplexation | 5 | Inverse-CDF `find(rand() < cumprob, 1, 'first')` for complex selection, iterated assembly; shared substrate pool. | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 24 | RibosomeAssembly | 1 | `randperm` for complex formation try-order; shared subunit pool. L2.1 SKIP for no-op trace. | **ALGORITHMIC-SHALLOW** | Python ensemble (after trace fixed) |
| 25 | FtsZPolymerization | 3 | `stochasticRound` (enzyme discretization) + 2× `ceil(numel * rand())` for polymer length index selection (state-affecting). | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 26 | Cytokinesis | 5 | Five `if rand() <= rate` per-element Bernoulli accept/reject for filament binding/dissociation events. Each updates ring substate; sequential over the ring. | **ALGORITHMIC-SHALLOW** | Python ensemble |
| 27 | HostInteraction | 0 | No RNG calls in file. | **DETERMINISTIC** | None |
| 28 | TerminalOrganelleAssembly | 0 | No RNG calls in file. | **DETERMINISTIC** | None |

## Tallies

| Bucket | Count | Processes |
|---|---:|---|
| DETERMINISTIC | 6 | ChromosomeCondensation, ChromosomeSegregation, HostInteraction, ProteinActivation, TerminalOrganelleAssembly, TranscriptionalRegulation |
| TRIVIAL-RNG | 5 | Metabolism, DNADamage, ProteinProcessingI, ProteinProcessingII (+ implicitly tRNAAminoacylation if its iterated-randsample is judged commutative — held in shallow for safety) |
| ALGORITHMIC-SHALLOW | 13 | Replication, DNASupercoiling, RNAProcessing, RNAModification, RNADecay, tRNAAminoacylation, ProteinModification, ProteinFolding, ProteinDecay, ProteinTranslocation, MacromolecularComplexation, RibosomeAssembly, FtsZPolymerization, Cytokinesis (14 actually — see Open Question Q3 below) |
| ALGORITHMIC-DEEP | 4 | ReplicationInitiation, DNARepair, Transcription, Translation |

(Totals: 6 + 5 + 13 + 4 = 28. The shallow/trivial boundary for tRNAAminoacylation is a judgement call — defaulted to shallow.)

## Verdict on L2.2 scope

**A 19-process L2.2 is not warranted.** Of the 22 stochastic processes, only **4 actually require a Karr-ensemble L2.2** (the DEEP bucket). The other 18 split into 6 deterministic (no test needed), 5 trivial-RNG (cleared by existing L2.1), and 13 algorithmic-shallow (cleared by a one-shot Python ensemble, no MATLAB regen).

**Estimated L2.2 cost under this verdict:**
- DEEP (4 processes × ~1 engineer-day) = 4 days of MATLAB ensemble + Python comparison harness + per-process design
- SHALLOW (13 processes × ~30 min setup + 5 min runtime) = ~1 engineer-day total for the Python ensemble harness, then 13 × 5min = 1 hour of runs
- TRIVIAL (5 processes) = ~0 incremental (the λ-check is already implicit in L2.1)
- DETERMINISTIC (6 processes) = 0

**Total: ~5 engineer-days for L2.2 closure**, vs ~3-4 engineer-weeks for the naive "all 19 stochastic processes get a full Karr ensemble" interpretation.

## L2.5 sequencing implication

The 2026-06-04 sequencing rule ("L2.5 gated on L2.2 all-green for stochastic processes participating in L2.5 pairs") translates concretely to:

- L2.5 pairs involving ONLY deterministic + trivial-RNG processes can start **immediately** (no L2.2 dependency).
- L2.5 pairs involving algorithmic-shallow processes can start once the Python ensemble harness ships (target: ~1 day) AND the relevant processes pass their shallow check.
- L2.5 pairs involving any of the 4 DEEP processes (ReplicationInitiation, DNARepair, Transcription, Translation) must wait for that process's Karr-ensemble L2.2 to land.

Likely first L2.5 pair candidates that are unblocked today (no DEEP dependency):
- Translation + RNAProcessing → BLOCKED (Translation is DEEP)
- RNAProcessing + RNAModification → unblocked after shallow check
- ProteinProcessingI + ProteinProcessingII → unblocked **immediately** (both trivial)
- Metabolism + ProteinDecay → unblocked after pdecay shallow check
- FtsZPolymerization + Cytokinesis → unblocked after both shallow checks

This is actually good news for L2.5 progress — the first viable L2.5 pair (`PPI + PPII`) needs zero new work to start.

## Honest limitations and open questions

**Limitations of this audit:**

1. **Static read only.** I did not run any of these. A process whose static fingerprint looks shallow could behave deep if the iterated-`randsample` loop happens to be effectively a Gibbs sampler with non-trivial mixing.

2. **Helper-function blindness.** The grep only matched `randStream\.` and direct RNG primitives in the process file. Helpers in `+util/` or inherited methods could contain additional RNG calls. Spot-check shows the process files are largely self-contained for stochastic logic, but a counter-example would invalidate the bucket assignment for that process.

3. **No commutativity proof.** "randperm with non-commutative downstream" was judged by reading the loop body for shared-state writes. For close calls (e.g. RNAProcessing's `randperm(4)`), I defaulted to shallow rather than risk a false-trivial.

4. **The wrong-λ-right-shape gap remains.** This audit cannot detect a bug where the Python λ computation is wrong but the distributional shape is right. That's the gap a full Karr ensemble would close, and we accept the gap for TRIVIAL and SHALLOW buckets in exchange for ~3 weeks of saved work. L2.1's delta-integral check (via trace-hint) is the partial mitigation.

5. **Bias risk acknowledged.** I (the agent) had a clear preference for fewer processes in DEEP because that unblocks L2.5 faster. To mitigate, the classifier rules were locked before reading any process, and the four DEEP picks include the three processes I had no prior bias on (RepInit, DNARepair, Transcription). Translation lands in DEEP cleanly via the `rand < tmRNABindingProbability` branch and the iterated weighted state machine.

**Open questions for operator:**

- **Q1.** Do you accept the "wrong-λ-right-shape" gap for TRIVIAL+SHALLOW buckets? If no, we need to widen L2.2 to all 18 stochastic processes (not just the 4 DEEP).
- **Q2.** Do the 2 L2.1-SKIPPED processes (RibosomeAssembly, RNAModification) get L2.2 work now, or do we defer until their no-op traces are extended? My recommendation: defer; classify them in advance (done in this table) so when traces ship the test is ready.
- **Q3.** The 14th SHALLOW entry vs 13 in the headline: tRNAAminoacylation is a judgement call between TRIVIAL and SHALLOW. Defaulted shallow. Acceptable?
- **Q4.** Should DEEP processes' L2.2 work proceed in parallel via codex fleet (4 agents, ~1 day each, ~1 calendar day total), or sequentially (4 calendar days, less integration risk)?

## Provenance

- F artifacts read: `docs/karr_extracts/process/{01..28}_*.md` (verbatim docstring extracts + mapping notes, no code).
- MATLAB sources read: `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/*.m` (all 28, full RNG-site grep + 1-line context, ~445 matching lines reviewed).
- L2.1 status as of audit: 44/46 strict GREEN, 2 SKIP (`karr_ribosome_assembly`, `karr_rna_modification`) on `audit/l2-1-sweep-v2` @ `413896a`.
- Reconciled ladder: see `plan.md` top block and decision `l-ladder-l2.5-and-l2.2-distributional-split` in `~/.pm-os/DECISIONS.md`.
