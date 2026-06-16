# Day 30: Six Bugs, One Store, and a Chromosome That Stopped Being Fictional

*June 16-17, 2026*

---

**Tehol:** Bugg, what did we start the day with?

**Bugg:** Twelve of twenty processes validated, sir. Fourteen if you count the two convergence-greens that passed the stress test. Two regime-bounded with documented algorithmic divergences — Macromolecular Complexation and Protein Translocation. Four chromosome-blocked. Two event-class.

**Tehol:** And what do we have now?

**Bugg:** Sixteen validated. Eighty percent.

**Tehol:** *[sets down teacup]* In one day.

**Bugg:** In one day.

---

## The Convergence Funnel

**Tehol:** Walk me through it. You had Macromol and PTransloc sitting at "regime-bounded." Those had real divergences found by the SUT audits yesterday, correct?

**Bugg:** Yes. Macromol was sampling a Poisson multiplicity — forming multiple complex copies per loop iteration — while Karr forms exactly one. PTransloc had three divergences: species-level versus copy-level permutation, raw versus rate-scaled enzyme capacities, and batch-per-species versus one-copy-per-iteration.

**Tehol:** So you fixed them.

**Bugg:** I fired both via codex with 3-slot prompts. Macromol was a two-line fix — literally delete the Poisson draw and the forced floor-to-1 logic, replace with `formed[chosen] += 1`. PTransloc was a 218-line faithful re-port: copy-level `MatlabRandStream.randperm`, rate-scaled enzyme capacity, break-on-first-failure.

**Tehol:** And the tests?

**Bugg:** 11/11 for Macromol, 19/19 for PTransloc. Then I ran the substrate-stress revalidation. Macromol at α=1.0: exact match — 97 events versus 97, W1=0.000. PTransloc: PASS at *all* α levels, including α=0.01 where it had previously diverged.

**Tehol:** The α<1 failure on Macromol?

**Bugg:** Same input-mismatch confound as tRNAAA. OC-at-α versus Karr-at-α=1. Different inputs, not different algorithms. The SUT audit proved the algorithm is faithful; the stress test was measuring the wrong thing.

**Tehol:** And you caught that because—

**Bugg:** Because we ran the full convergence funnel. Phase 1 finds the fragile greens, Phase 2 classifies algorithm-match versus input-mismatch, Phase 3 fixes and revalidates. The funnel works.

---

## The Event Class Ambush

**Tehol:** The event-class processes. Cytokinesis and RibosomeAssembly. Those had been parked since Day 28 — zero events in the extraction window. What changed?

**Bugg:** I ran SUT audits on both. RibosomeAssembly had a real bug hiding behind the zero-event mask: OC was folding catalytic enzyme counts into the stoichiometric `min(...)` bound, capping formation at the enzyme count. Karr uses enzymes as a binary all-present gate. One GTPase copy is enough for multiple assemblies.

**Tehol:** Why wasn't this caught earlier?

**Bugg:** Two shields. First: zero events in the extraction window meant L2.2 never exercised it. Second: in normal operation, enzyme counts are high enough that `min(enzyme_count, GTP_limited)` equals `min(∞, GTP_limited)`. The bug only matters when enzymes are scarcer than substrates, which the test fixtures don't exercise.

**Tehol:** *[nods slowly]* The abundant-enzyme mask. Same shape as the convergence-green mask — the test regime happens to be the one where the bug is invisible.

**Bugg:** Precisely.

**Tehol:** And Cytokinesis?

**Bugg:** That was more dramatic. OC's own docstring said "Karr-light v1: bulk progress ratchet." Zero RNG draws versus Karr's five classes of per-element stochastic draws across a four-phase edge-wise FtsZ ring state machine. Not a bug — an intentional simplification that someone planned to finish later and never did.

**Tehol:** So you finished it.

**Bugg:** 868 lines changed. Full five-phase FtsZ ring constriction cycle: bind-first-straight, bind-second-straight, unbind-residual-bent, GTP-hydrolysis-bend with geometry update, dissociate-first-bent. Per-element `rng.random() <= rate` draws. Mass conservation of FtsZ subunits across all polymer states. Completion when pinchedDiameter reaches zero.

**Tehol:** Tests?

**Bugg:** Seven. Deterministic-rate phase cycle, zero-rate invariant, hydrolysis stoichiometry, mass conservation across many ticks, geometry-driven completion. All green.

---

## FtsZPolymerization: The ODE That Was a Coin Flip

**Tehol:** And the third event-class process?

**Bugg:** FtsZPolymerization. Karr uses a custom ODE23S integrator for monomer activation, nucleation, and elongation kinetics — deterministic chemical kinetics. OC had replaced it with stochastic rate draws. A fundamentally different mathematical model pretending to be the same process.

**Tehol:** That's... not a simplification. That's a different simulation.

**Bugg:** Correct. Fixed it. scipy `solve_ivp` with BDF method, mass-preserving enzyme discretization, substrate-limit clamping. Nine tests green including the L2 replay.

---

## The Chromosome Store

**Tehol:** Four processes were blocked on the chromosome port. What happened there?

**Bugg:** Built the chromosome sparse-triple store. 351 lines. Holds all 11 Karr chromosome fields as sparse triples — positions, strands, values, shape — with circular-coordinate normalization matching `CircularSparseMat.m`. Then re-ported DNASupercoiling as the first consumer: reads and writes `chromosome.linkingNumbers` as real sparse triples, derives the legacy `supercoil_density` scalar from the full state. L2 replay passes.

**Tehol:** First chromosome-primary process validated end-to-end.

**Bugg:** Then Replication — `polymerizedRegions`. Same pattern, more complex field (regions grow as the fork advances). Eight tests pass, L2 replay green.

**Tehol:** That's two of the four chromosome-blocked processes resolved in one day.

**Bugg:** The other two — ReplicationInitiation and DNARepair — are the same pattern. Branches are ready. They died tonight because—

**Tehol:** Because someone was running four other codex sessions on the same subscription.

**Bugg:** *[pause]* I was going to say Azure capacity constraints, sir.

**Tehol:** *[slight smile]* Yes. Azure capacity constraints. Named "the other four machines on my subscription." Tomorrow morning they'll fire cleanly.

---

## The MATLAB Scan

**Tehol:** The event-window traces. You kept saying MATLAB extraction was needed.

**Bugg:** I checked exhaustively first. No full-cycle Karr simulation outputs exist on disk anywhere — not in the repo, not in the mirrors, not in SimTK downloads. The CovertLab repo ships code, not cached runs. Our own extractor starts from tick 1 and runs 100 ticks — too early for these sparse-event processes.

**Tehol:** So you fired the extraction.

**Bugg:** 50,000 ticks at seed=1, four processes. Running overnight. The seed-0 scan already finished — RibosomeAssembly fires 253 events across the full cycle, starting at tick 238. Cytokinesis didn't fire in seed 0 because the sim didn't reach division. Seed 1 at 50k ticks should catch it.

**Tehol:** And when it finishes?

**Bugg:** We'll know the exact tick ranges for all four event-class processes. Then a targeted extraction at the right offset produces the oracle traces the L2.event harness needs.

---

## The Scoreboard

**Tehol:** Final count.

**Bugg:**

| Start of day | End of day | Change |
|---|---|---|
| 12/20 (60%) | 16/20 (80%) | +4 validated |

Six algorithm fixes shipped. One chromosome store built. Two chromosome-primary processes ported end-to-end. Three faithful re-ports of "Karr-light" simplifications. One full-cycle MATLAB scan running overnight.

**Tehol:** What made today different from the days where we shipped one fix and spent three hours debugging the harness?

**Bugg:** The convergence funnel. We stopped trying to validate through the distributional gate when the distributional gate couldn't tell us anything. SUT audit → fix → revalidate. Structural correctness first, statistical confirmation second. Every process that went through the funnel today moved in one pass because we knew what was wrong before we touched the code.

**Tehol:** And the event-class ambush?

**Bugg:** Same principle. The zero-event mask hid real bugs — but only from the statistical gate. The SUT audit found them in ten minutes of reading. The fix was obvious once the divergence was named.

**Tehol:** *[stands, stretches]* Sixteen of twenty. Two more chromosome ports ready to fire. Three event-class processes with faithful algorithms awaiting traces. One process that genuinely needs the chromosome port AND an external damage stimulus before it can do anything.

**Bugg:** Nineteen of twenty are actionable, sir. Only DNADamage is truly blocked on two orthogonal prerequisites.

**Tehol:** Nineteen. Tomorrow we finish what Azure wouldn't let us finish tonight.

**Bugg:** Yes, sir.

---

*Commits landed: `3deae19`, `3c7d432`, `f24f234`, `3cee339`, `9375e59`, `dc9eb70`, `b83c278`, `4fb41e2`, `67a0edb`, `1dbdd4a`, `580c9e7`, `4c0dddf`, `dd8a49c`, `cd1ff60`, `a1f506c`, `5cbca58`, `9375e59`, `5a794de`, `ad01b72` + catalog updates v3.4→v3.11.*
