---
title: "Days 64–74: The Dictionary We Deleted, the Canary That Died at Tick 25,361, and the Bottleneck That Turned Out to Be Me"
date: 2026-08-03
authors: [sdrona]
tags: [opencell, L2.2, L2.event, evidence, honest-mode, condition-gated, orchestration, checkpoint]
---

**Tehol:** Bugg. Eleven days ago I told you to begin the re-baseline.

**Bugg:** You did, sir.

**Tehol:** And to let someone else read the result.

**Bugg:** That part turned out to be the expensive half.

**Tehol:** Start with the dictionary. The one that graded a page against a photocopy of itself.

**Bugg:** Deleted. Both copies of it. There was a hand-typed list of twenty-two verdict strings in the strict-rubric test and a second set of hand-typed dictionaries in the audit probe, and the test compared one to the other. Two opinions agreeing with each other is not a measurement. Both are gone.

**Tehol:** Replaced by what.

**Bugg:** A generator. It reads the raw per-channel metrics and the thresholds out of each process's evidence bundle and re-derives the verdict from scratch. It never trusts the verdict string already written in the file. The one tracked artifact is `evidence_index.json`, and the only defence it has against tampering is that the audit regenerates the whole index from nothing and diffs it against what's on disk.

**Tehol:** And the first honest index said?

**Bugg:** Twenty-two rows. All `MISSING_EVIDENCE`. Aggregate `NON_GREEN`.

**Tehol:** *[does not look up]* You deleted seventeen greens and committed a page of nothing.

**Bugg:** I committed a page of nothing that was *true*, sir. Every green we had was a claim about ensembles that no longer existed on disk. The only honest starting number was zero.

---

**Tehol:** Then you had to go and make the evidence real.

**Bugg:** Fifty seeds per process, genuinely extracted from Karr's MATLAB. Phase 3 ran eleven of the sixteen production processes out to the full fifty — five hundred and twenty-eight seed jobs on two bounded workers, about seventy-nine minutes wall clock, both workers clean. Five processes stayed blocked from the earlier preflight and I did not touch them, because a blocked process that quietly acquires evidence is exactly the shape of the thing we just deleted.

**Tehol:** And the three that wanted more depth.

**Bugg:** DNARepair, ProteinDecay and ReplicationInitiation. Their catalog rows have always said two hundred ticks. Every oracle file we had was one hundred. And the harness caught it — not from a filename, from `arr.shape[1]`. *"Requested 200 ticks, but oracle only provides 100."* A content check, not a label check. I regenerated all three at genuine depth and archived the hundred and fifty superseded files rather than overwriting them.

**Tehol:** ProteinDecay. Last time we spoke it had failed at two-point-zero-nine against a threshold of one, on both branches, identically, to six decimals.

**Bugg:** On real fifty-seed evidence at two hundred ticks it now passes. Its primary channel is monomers; the mean per-sample Wasserstein distance is seven ten-thousandths, against a null q95 of point two one. Verdict `SEED_NOISE`. Four million one hundred forty-seven thousand four hundred fifty-nine nonzero Karr samples against four million one hundred forty-seven thousand four hundred sixty-four of ours.

**Tehol:** So the failure was the evidence, not the process.

**Bugg:** The failure was that nobody had ever measured the process against evidence that satisfied its own catalog row. I am not going to dress that up as vindication. We spent a month believing a number that had been typed rather than computed, and then a week discovering that the computation, when finally performed on the right data, said something else again.

---

**Tehol:** You had two incidents you keep not mentioning.

**Bugg:** ProteinDecay ate the machine, sir.

**Tehol:** Go on.

**Bugg:** The per-tick process constructor in the harness was decorated `@lru_cache(maxsize=None)`. It is always called with a `SeedSequence`-derived value that is unique for every `(seed, tick)` pair. So every single call was a guaranteed cache *miss* that then permanently retained one more constructed process object. I probed it with a staircase — one-by-twenty, five-by-fifty, ten-by-one-hundred — and the cache size, the live instance count and the call count were the same number throughout, with zero hits. Every instance carried its own reloaded copy of large fixture arrays, two-point-seven to five-and-a-half mebibytes apiece. At the catalog's fifty seeds by two hundred ticks that is ten thousand constructions and thirty to fifty gibibytes retained. It grew at about point seven eight gibibytes a minute, never plateaued, went through the thirty-one gibibyte ceiling and had to be killed twice.

**Tehol:** The fix.

**Bugg:** `maxsize=4`. That is the entire fix. The function is pure, so bounding retention cannot change what any tick computes — and I proved that rather than asserting it: same seed/tick grid, bounded cache versus unbounded, bit-identical substrate, monomer and complex arrays out.

**Tehol:** A cache with a key that is never reused is not a cache.

**Bugg:** It is a leak with good manners. And the other incident was Metabolism's flux-variability gate, which projected past two hours and had once spent nearly nine CPU-hours emitting about two lines of log. Three separate solver bugs wearing one trenchcoat: Dantzig pricing cycling catastrophically on a matrix with a three-point-six-times-ten-to-the-eighth scaling ratio; warm-starting each column from the previous column's basis inducing its own degeneracy — one column took thirty iterations cold and a hundred and eighty-six thousand nine hundred fifty-four warm without ever converging; and a hard equality row on the objective face making phase-one report infeasible on a face that is provably non-empty.

**Tehol:** And after.

**Bugg:** Mean one and a half seconds a sample, projected twenty-four minutes for the full sweep. And nothing about the mathematics moved — no bound, no tolerance, no pass threshold, no seeds, no ticks. I checked that by re-deriving feasibility residuals in numpy independently of the solver, because "I made it faster and it still passes" is precisely the sentence a person says right before they discover they made it faster by making it wrong.

---

**Tehol:** Give me the disposition. All of it.

**Bugg:** Twenty-two processes in scope for Design-A. Fourteen PASS. Four FAIL. Four with no evidence at all. Aggregate `NON_GREEN`.

**Tehol:** Not twenty-eight.

**Bugg:** Not twenty-eight, and I want that said plainly. Twenty-two is what this gate covers. Fourteen of twenty-two is not a cell.

**Tehol:** The four failures.

**Bugg:** They fail in four different ways, which is the interesting part. DNASupercoiling fails on *support*: its primary component has seventeen nonzero events on our side and twenty-four on Karr's, against a floor of thirty. Replication fails on *staleness* — a helper file changed underneath evidence that had already been generated, so the index refuses it rather than re-reading it charitably. MacromolecularComplexation and ProteinProcessingII both fail on a *sentinel*: each claimed a deterministic-convergence demotion without machine-checked support for it.

**Tehol:** And you went and got more seeds for the supercoiling one.

**Bugg:** I pre-registered a power diagnostic first — the decision rule written and committed before a single extension seed existed — then extracted seeds fifty through ninety-nine and ran it. It came back `POWERED_AT_N100`. The support problem goes away at a hundred seeds.

**Tehol:** So you promoted it.

**Bugg:** I did not. It was accepted as supplemental, non-gating evidence. The canonical row is frozen at fifty seeds by a hundred ticks and it still reads `FAIL / PRIMARY_INSUFFICIENT_SAMPLES`. A diagnostic that tells you what *would* happen at a different N is not a verdict at the N you actually gate on. If I let that one through, the next fourteen would follow it.

---

**Tehol:** The four with no evidence.

**Bugg:** The event-class ones. Cytokinesis, DNADamage, FtsZPolymerization, RibosomeAssembly. And before any of them could be gated, something had to exist to gate them *with*, so we built the shared L2.event foundation — schema, registry, window loader, adapters, metrics, evidence index, a CLI runner with a refusal gauntlet.

**Tehol:** And the first thing it found.

**Bugg:** That there are exactly two event-window MAT files on disk anywhere in this repository's data tree. Both seed zero. And one of the two is for a process that isn't even in the event-class scope. The catalog, meanwhile, carried notes claiming RibosomeAssembly and DNADamage were L2.2 GREEN. RibosomeAssembly's green was one seed of the fifty required. DNADamage's green was the cell producing zero damage events and Karr producing zero damage events, and someone calling that agreement.

**Tehol:** Zero equals zero again.

**Bugg:** Zero equals zero again, sir. So the foundation was made to fail closed: a channel with no Karr support returns `NO_KARR_SUPPORT`, never `PASS`, and the refusal precedence runs inside the evaluator where it cannot be stepped around.

**Tehol:** And the reviewer still took it apart.

**Bugg:** Four rounds. Round two found that the gate could be bypassed and that the payload mapping was reading raw positions rather than real component keys. Round three found that a "pooled" support floor meant two different things in two places. Round four found two things I would never have found. The first: the path check that confirms evidence came from the sanctioned Karr source directory was a string-prefix comparison, so a sibling directory named `karr_native_evil` would have been accepted as living under `karr_native`. The second is worse — the payload gate took a flat list of firings and resampled individual firings as if each were an independent seed. For a repeated-firing process, which is exactly the shape RibosomeAssembly produces, that manufactures a pseudo-replicated, artificially tight null. It would have made real divergence look like noise. Nothing was wrong with the test suite. There were a hundred and seven tests, then a hundred and sixty-nine, and every one of them passed the whole time.

**Tehol:** Which is the point you keep having to learn.

**Bugg:** A test suite tells you the code does what you thought. It has nothing to say about whether what you thought was correct.

---

**Tehol:** The canaries. You ran real MATLAB.

**Bugg:** Canary A regenerated the RibosomeAssembly seed-zero window with a complete stride contract — stride one, ticks two hundred and one through three hundred, two hundred ticks of burn-in. The refusal we used to get for an incomplete window is gone. The refusal we still get is `SINGLE_SEED_ENSEMBLE_REQUIRED`, because one is not fifty. The adapter status in the registry is unchanged: `structural_smoke_only`, verdict `NOT_APPLICABLE`, not gating. The two deliberate failure canaries in between refused exactly what they were built to refuse.

**Tehol:** And D.

**Bugg:** Canary D was the long one — a full run to produce real Cytokinesis event data, which requires getting deep enough into the cell cycle for a septum to actually pinch. It ran to tick twenty-five thousand three hundred and sixty-one and then died inside ProteinProcessingII's call to `mnrnd`.

**Tehol:** Which is a MATLAB function.

**Bugg:** Which is a MATLAB Statistics Toolbox function that we do not have, so this project long ago wrote its own `mnrnd.m` and put it on the path. And the extraction launcher unconditionally prepends that path directory to *every* job — so our shim silently shadows the real function on every run, including runs of processes that never call it. The shadow is a property of the run, not of the target process. Our shim built histogram bin edges as `[0, cumsum(p)]` straight off the raw probability vector and then forced the last edge to exactly one. Feed it a sparse `p` and the trailing zero-probability categories leave the second-to-last cumulative edge a hair above one; forcing the final edge down to one makes that pair genuinely decreasing, and MATLAB stops. The trigger was `p`'s sparsity, not its shape.

**Tehol:** Twenty-five thousand ticks to find a bug in a helper we wrote ourselves.

**Bugg:** In a helper written long before this branch, that had been quietly shadowing every extraction this project has ever run. It is fixed — no histogram function at all now, a manual count that behaves identically under MATLAB and Octave so it can actually be tested in our own environment, and it fails closed on bad input instead of clamping. And the shim's version and content hash are now written into every trace's metadata, so every trace produced before the fix classifies as `regenerate_invalid`. Including traces whose own process never touches `mnrnd`.

**Tehol:** So Canary D is done.

**Bugg:** Canary D has not successfully completed. The crash is understood and the crash is fixed. That is not the same sentence and I am not going to let them become one.

---

**Tehol:** You told me several of these were process failures. Now you tell me they were something else.

**Bugg:** Three of them were profile mistakes, sir — we were asking the wrong *kind* of question and then recording the wrong answer as a defect.

FtsZPolymerization sat in the event class. It is continuous polymer-state ODE kinetics integrated every tick. Its enzyme channel moves on a hundred ticks out of a hundred. There is no "did the thing fire" question to ask. So it was reframed as a windowed, per-tick diagnostic in honest mode with no trace hint — and the honest report is `INSUFFICIENT_ENSEMBLE`, because we have one seed and it is the only one that exists anywhere: identical hash across twenty-seven worktrees, main, and the mirrors. The canary can never return PASS at N equals one. It needs forty-nine more seeds. It is not green and the proposed catalog row is not applied.

MacromolecularComplexation's network-of-two branch can never be confirmed the way the others are, and not for want of sampling — Karr's own routine draws a random number per iteration of a while loop to decide which complex builds next, and there is no closed form for that sequence. The census across five thousand samples says the branch's upper bound is zero everywhere, because its limiting substrate's pool is zero in all ten thousand argmin counts. So it has a hardened `CONDITION_GATED_CANDIDATE` artifact — non-operative, consumed by nothing, changing no row. And it carries `lifecycle_reachability_status: UNRESOLVED` in the file itself, because whether that substrate ever becomes nonzero at a later cycle stage is a question we have not answered. It does not unblock L2.5.

ProteinProcessingII got the first canary in this project driven by genuine local MATLAB using Karr's own hash-pinned `RandStream` — no stub, no scaffold, a freshly constructed stream per seed. Twenty seeds, two distinct outcomes, zero invariant violations. It is non-gating. The process verdict stays `H12_OBSERVED_REGIME`. And the full scarcity matrix is hard-blocked, because the Statistics Toolbox is licensed on this machine and not installed.

**Tehol:** And DNADamage.

**Bugg:** Preregistered, not executed, and explicitly non-biological. The local Karr condition fixtures set radiation to zero, so there is no calibrated dose to claim. The profile injects Karr's own radiation substrate purely to reach the mechanism, with the expected fire-tick counts — ninety-seven point two two for UVB, ninety-six point zero two for gamma — frozen in a JSON file before any MATLAB runs. It is a mechanism stress test. It is not a claim about a cell that was irradiated.

---

**Tehol:** Replication.

**Bugg:** Replication is the one that keeps teaching the same lesson. Round after round on that one branch: the literal Okazaki-fragment topology pipeline, the mother-strand shrink on unwinding, the accessibility occlusion cap, the call order, the bound-versus-free enzyme pool ownership, the daughter-strand write. Every round the same shape — we had invented a semantic where Karr had a specific one, and the invention looked reasonable until someone read the original.

**Tehol:** The most recent.

**Bugg:** Single-strand binding proteins. We were scoping candidate binding sites across the whole genome, which treated the not-yet-synthesized complement of a daughter strand as exposed single-stranded DNA — and, because one strand's polymerized region never shrinks, could never produce a candidate site there at all. It now computes the two real fork gaps directly, the same windows the gate's own threshold formula already reads. And separately: a zero advance-budget tick was skipping the entire column, including the termination retry, so a fragment that finished polymerizing but was gated on an unmet condition would never be re-checked on a later tick. Karr re-evaluates that every tick regardless of progress.

**Tehol:** So it's fixed.

**Bugg:** It is not. The reviewer still rejects integration and the fifty-seed run over strand scoping and event fidelity. I am telling you what improved, not that it is done.

---

**Tehol:** *[pulls the blanket higher]* And what did all of this cost you, other than eleven days.

**Bugg:** It cost me the illusion that the machines were the constraint. There are thirty-one worktrees on this disk. The reviewer was upgraded, and every substantial change now runs a two-turn handshake — state the intent, get it adjudicated, then implement — and every extraction is preceded by an inventory across every worktree so we stop re-extracting data we already have somewhere.

**Tehol:** All of which is good.

**Bugg:** All of which is good, and all of which converges on one queue. The agents don't wait on compute. They wait on someone to read a review, adjudicate a conflict, decide whether a diagnostic gets to become a verdict. The parallelism scaled and the adjudication didn't. For most of these eleven days the thing holding the work was not a solver or a licence or a MATLAB run. It was the orchestrator.

**Tehol:** Which is you.

**Bugg:** Which is me, sir.

**Tehol:** Then say what is actually true, and then we stop.

**Bugg:** L2.2 is fourteen of twenty-two in scope, on genuine fifty-seed Karr evidence, mechanically re-derived, aggregate `NON_GREEN`. Four honest failures with four different causes. Four event-class processes with no gateable evidence and a foundation that now refuses to pretend otherwise. FtsZ is an honest diagnostic at one seed. Macromolecular complexation has a candidate disposition that changes nothing. ProteinProcessingII has a real MATLAB canary that gates nothing. DNADamage has a preregistration and no run. Replication has better topology and a standing rejection. Cytokinesis got to tick twenty-five thousand three hundred sixty-one and fell over in our own shim.

L2.5 has not started and is not certified. L3 has not started.

**Tehol:** And the next thing you do is not another process.

**Bugg:** The next thing I do is stop. We have three descriptions of this ladder in three places and they no longer agree with each other, which is how the hand-typed dictionary happened in the first place. So: one canonical ladder, one reconciled status, one blog that matches both. No new work until the bookkeeping is true.

**Tehol:** *[closes his eyes]* You have finally found a use for the part of the job you hate.

**Bugg:** I have found out what it costs to skip it, sir. That is not the same thing, but it will do.

---

**Honest scoreboard**

| Gate | What it measures | prev (Days 54–63) | now (Days 64–74) |
|---|---|---|---|
| **L2.2** distributional | 22 in-scope processes, ensemble vs Karr | "REVEALED HOLLOW" — pin checked a hand-typed dictionary; true count UNKNOWN | **14 PASS / 4 FAIL / 4 MISSING_EVIDENCE, aggregate NON_GREEN.** Verdicts mechanically re-derived from raw metrics; the hand-typed dictionaries are deleted |
| **L2.2 oracle data** | genuine multi-seed Karr traces | ensemble directory empty | **11/16 production processes at full 50 seeds** (528 seed jobs, ~79 min); 3 M=200 processes regenerated at genuine depth; 5 remain blocked |
| ProteinDecay | last post's live failure (W1 2.09 vs threshold 1) | FAIL, identically on both branches | **PASS on real 50×200 evidence** — primary-channel W1 mean 0.00078 vs null q95 0.213, `SEED_NOISE` |
| DNASupercoiling | primary-component support | — | **FAIL / PRIMARY_INSUFFICIENT_SAMPLES** (n_oc 17, n_karr 24, floor 30). Pre-registered N=100 diagnostic returned `POWERED_AT_N100` — **accepted as supplemental, non-gating; canonical row still FAIL** |
| **L2.event** foundation | shared event-class gate machinery | did not exist | **built and fail-closed** — 4 reviewer rounds, 107→169 tests; found a prefix-vs-ancestor path hole and a pseudo-replicated payload null that would have hidden real divergence |
| RibosomeAssembly | event-class gate | catalog claimed "L2.2 GREEN" | **structural only.** Canary A gave it a complete M4 stride contract; still refused by `SINGLE_SEED_ENSEMBLE_REQUIRED` — **1 of 50 seeds** |
| Cytokinesis | event-class gate | not built | **adapter structural/unregistered, 0/50 seeds.** Canary D reached **tick 25,361** and failed safely in our own pre-existing `mnrnd` shim; shim fixed and hash-bound — **D has not completed** |
| FtsZPolymerization | was event-class | "event-class, deferred" | **reframed as an honest windowed diagnostic.** N=1/100 ticks, explicit `INSUFFICIENT_ENSEMBLE`, never PASS. **Not green**; needs 49 more seeds |
| MacromolecularComplexation | H12 support for network≥2 | FAIL (sentinel) | **hardened `CONDITION_GATED_CANDIDATE`, non-operative.** Lifecycle reachability **UNRESOLVED**. Does not unblock L2.5 |
| ProteinProcessingII | H12 support | FAIL (sentinel) | **first genuine-MATLAB canary with Karr's real RandStream** — 20 seeds, 2 outcomes, 0 invariant violations. **Non-gating**, still `H12_OBSERVED_REGIME`; full matrix blocked (Statistics Toolbox absent) |
| DNADamage | event-class gate | vacuous zero==zero "green" | **preregistered synthetic mechanism-stress profile, explicitly non-biological, not executed** |
| Replication | topology fidelity | FAIL | bound/free pools, call order, occlusion cap, SSB fork-gap scoping, zero-budget termination retry all improved — **still rejected on strand scoping / event fidelity. Not fixed** |
| **L2.5 / L3** | composition / direct coupling | not started | **not started, not certified** |
| **the bottleneck** | what the work waits on | the grader | **the orchestrator** — parallelism scaled, adjudication didn't |

---

*This is the OpenCell dev blog. The repo is [github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell). The next entry will not contain a single new process. It will contain one ladder, one status, and a check that the two agree — which is the least interesting work available and, on the evidence of the last eleven days, the only work that would have prevented any of this.*
