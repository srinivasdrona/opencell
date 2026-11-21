---
title: "Five Green Gates, an Expired License, and Three Scales for One Cell"
date: 2026-11-21
authors: [sdrona]
tags: [opencell, matlab, fidelity, l2.2, l2.5, rng, mass-conservation, vivarium, multi-agent]
---

*November 21, 2026 — Progress snapshot from the terrace (workbench paused since October 19)*

---

**Tehol:** Bugg, there is late-autumn dust on the ledger, zero background jobs humming in the cellar, and an unsettling quiet where twenty-four blocked processes used to live. Tell me we didn't finish the cell while I was napping under this blanket.

**Bugg:** *[sets down a kettle]* Rest easy, sir. Nobody finished the cell. Nobody has touched a line of model code since October 19. Today is strictly an accounting of where we paused—and why pausing there beat charging ahead.

**Tehol:** Good. Undocumented miracles make me nervous. Remind me where we left the public board in [September](2026-09-23-days-119-125-three-honest-ports-twenty-five-blockers-and-the-matrix-we-refused-to-fake.md).

**Bugg:** Four deterministic processes eligible for `L2.5` shared-pool composition—`ChromosomeSegregation`, `HostInteraction`, `ProteinActivation`, and `TerminalOrganelleAssembly`—and twenty-four stochastic or event-driven processes blocked under our no-known-gap rule.

**Tehol:** Four honest ports out of twenty-eight, after we threw twenty-two hollow green lights off the terrace. Then we marched into Cohort 1: five of those twenty-four stochastic blockers. How did their statistical gates go?

**Bugg:** All five passed, sir.

**Tehol:** *[sits bolt upright, blanket sliding off one shoulder]* All five? Name them.

**Bugg:** `ProteinTranslocation` (2,892 primary coordinates), `ProteinProcessingII` (482), `ProteinModification` (964), `RNAProcessing` (693), and `RNAModification` (694). Genuine frozen-source Design-A sweeps on local candidate `65df71c`—fifty seeds, a thousand Karr-only bootstrap resamples, a hundred ticks per seed for four of them and twenty ticks for `ProteinProcessingII`.

**Tehol:** Even with product-manager arithmetic, four plus five is nine. So `main` now reads nine out of twenty-eight eligible?

**Bugg:** `main` still reads four out of twenty-eight eligible and twenty-four blocked, sir. None of the Cohort 1 branches has merged to `main`, `L2.5` composition has not started, and we are not certifying a single new process as no-known-gap ready today.

**Tehol:** *[pulls the blanket back up and grins]* Five green gates, zero promotions, and a month-long pause. Either we finally grew some discipline, or we stepped on a wonderfully educational rake. Walk me onto the rake.

---

**Bugg:** For one afternoon on October 19, it looked like a clean advance. Two of the five—`ProteinProcessingII` and `ProteinTranslocation`—cleared independent evidence and integration checks on a local assembly branch (`9f53a27`, with `PT` publication `e372a5b` and integration check `f87ebf1` verifying all seventy-seven committed Git blobs byte-for-byte). That local candidate briefly tallied `6/28` eligible.

**Tehol:** I know that tone, Bugg. That's the tone you use right before telling me the pantry floor gave way. Why isn't `6/28` even our local claim anymore?

**Bugg:** Because an isolated Design-A gate hands one process Karr's recorded before-state and checks its output distribution across fifty seeds. It proves the producer's solo audition. It does *not* catch a private random-stream phase slip masked by seed variance, and it does *not* prove the chassis's live mass readers weigh the molecules that just walked onto the stage.

**Tehol:** Let's start with the random stream. Which of our five green soloists missed a beat on replay?

**Bugg:** `ProteinModification`. Its fifty-seed distributional gate passed, yet persistent hundred-tick seed-0 replay missed at **tick 53**: substrate index 0 (`ADP`) changed by `0` in OpenCell and `3` in Karr's oracle, with `ATP` `0` versus `-3` and `H` `0` versus `3`. One `MG_407_MONOMER` modification fired in MATLAB and stayed zero in Python.

**Tehol:** Let me guess the tempting wrong fix. Somebody stared at a fractional enzyme cap, blamed stochastic rounding, and tried flipping `u < fraction` to `floor(x + u)` or tuning burn counts until tick 53 behaved.

**Bugg:** Nobody touched the rounding law, sir. Diagnosis came first. At tick 53, limiting enzyme `MG_109_DIMER` sat at `34 / 70.3125...`—a fractional capacity of `0.4835555...`. Python drew `0.7532401...`, evaluated strict `u < fraction` just as Karr's `RandStream.m` does, rounded capacity to zero, and exited *before* weighted reaction selection was ever reached.

**Tehol:** Wait a second. If `u < fraction` matches `RandStream.m`, and tick 53 never even entered weighted selection, then tick 53 wasn't the crime scene. Tick 53 was just where a drifted random stream finally landed on the wrong side of `0.4836`! Who drifted the stream earlier?

**Bugg:** Two things. First, our adapter ran NumPy's `MT19937` instead of Karr's per-process private `mcg16807` multiplicative congruential generator from `Process.m`. Second, on earlier ticks that *did* call weighted replacement sampling, our helper burned **four** uniform draws per pick where Karr's normalized-histogram `randsample` branch consumes **one**.

**Tehol:** Easy enough. Open MATLAB, query `mcg16807` at `seed=0`, freeze the vector, fix the adapter. Why are you staring at the roof tiles?

**Bugg:** Because when we launched MATLAB on October 19 to run that probe, it halted at startup with error `-10.2`. License expired.

**Tehol:** *[laughs]* Fourteen years [Karr et al., 2012](https://doi.org/10.1016/j.cell.2012.05.044) sits untouched in public, and the afternoon we ask it for one seed-zero integer, the landlord padlocks the oracle! Tell me nobody tried a license workaround or guessed the state.

**Bugg:** Neither, sir. Rule two of our primary-source checklist: *check what we already recorded locally.* September's chromosome RNG work had archived and SHA-hashed real MATLAB R2026a `mcg16807` probes—four positive seeds plus eight consecutive raw `seed=0` uniforms. From the first `seed=0` uniform (`0.21895918632809036`), we derived exact internal initial state `1144108930` and verified that our neutral `mcg16807_state_codec.py` matched all seven held-out `seed=0` draws and all four positive-seed vectors, while keeping `ProteinModification`'s private stream strictly separate from the shared chromosome RNG instance.

**Tehol:** Recorded primary evidence, zero guesswork, no borrowed global stream. How did the repair hold up under independent review?

**Bugg:** Frozen tests went in RED first; a separate doer landed the private-MCG and one-uniform fix at local `e6ee650`. On the unchanged hundred-tick replay across all five observables, the first mismatch became **none**. Then the independent reviewer adjudicated two remaining red legacy tests at local `9bed1a4`: one old test demanded `MT19937` state from an owner now required to be `mcg16807`, and one unit test seeded `MG_217` into a dead legacy shadow while production read its live folded home compartment. With those contracts corrected and codec-binding guards added, **178 tests passed** with zero skips and zero `xfail`s—recorded explicitly in the PM `VERDICT.md` as code closure, not an observed live PM prefix.

**Tehol:** Then why not rerun `ProteinModification`'s fifty-seed gate that night and pocket the win?

**Bugg:** Because registering that codec updates the shared schema module inside the consumed-hash closure of **nineteen** Design-A rows—including all five Cohort 1 processes. Rerunning one gate leaves four stale, and refreshing hashes without rerunning gates is fiction. All five wait for one integrated freeze.

---

**Tehol:** Fair. Now bring out the RNA twins—`RNAProcessing` and `RNAModification`—and tell me what sank that `6/28` snapshot. Start with what worked so my tea doesn't go cold in vain.

**Bugg:** Both runtime producers passed independent review across the full species catalog. `RNAProcessing` covers all 335 nascent transcripts, 347 processed transcripts, and 11 distinct global intergenic fragment rows (`RNADecay` fragment consumption stays explicitly open for Cohort M2). `RNAModification` covers all 347 processed and 347 mature forms, including all 309 no-modification pass-through transfers—and because canonical seed 0 has zero primary mutations, only seeds 1 through 49 are credited as active proof.

**Tehol:** Good. Now where did the mass go?

**Bugg:** Off the scales, sir. When `RNAProcessing` emitted real intergenic fragments (`2.745543310747854e-19 g`) or `RNAModification` emitted mature transcripts (`2.860042892898106e-16 g`), `KarrObservabilityStep` weighed them at **zero grams**.

**Tehol:** Hold on! We run an `L2.4` conservation gate across four seeds and a hundred ticks! How do two hundred and eighty-six attograms of mature RNA vanish without tripping the conservation alarm?

**Bugg:** `L2.4` audits substrate reaction attribution—ATP, GTP, water, amino acids—not RNA dry mass. Meanwhile, `KarrObservabilityStep` looked up RNA weights through a flat gene-ID map that missed global intergenic rows and all 304 `processed::` aliases.

**Tehol:** So Round 1 taught the observer to read Karr's `Rna_flat.mat` form weights?

**Bugg:** At local `406256b`, yes—nascent, processed aliases, distinct `TU_088` fragment rows, mature, and 37 aminoacylated tRNA keys all matched source grams. Ten frozen tests passed. And the independent reviewer promptly **accepted the observer component and rejected readiness for both RNA processes.**

**Tehol:** *[raises an eyebrow]* Rejected after ten green assertions? Why?

**Bugg:** Because production phenotype extraction calls `compute_cell_mass`, which still kept its *own* gene-only RNA lookup and returned **zero grams** on the exact same state.

**Tehol:** Two clerks in the treasury keeping separate tax books. So Round 2 made both clerks share one function?

**Bugg:** Local commits `8829930` and `bf46bfe` unified `compute_cell_mass` and `KarrObservabilityStep` onto the exact same `load_rna_form_mw` function object—forty-one frozen assertions green, tested without an observer and against poisoned sidecar hints. Whereupon final review (`total_mass_final_review/REPORT.md`) **accepted the two-file component and rejected readiness for both processes a second time.**

**Tehol:** *[sets his mug down firmly]* Bugg. Do not tell me there was a third clerk behind the curtain.

**Bugg:** In `scripts/run_chassis_v6_32400t.py`, sir, `MassEstimator` still drives live v6 CSV dry-mass and volume output using the old gene-only `rna.counts` table. Feed it full v6 states where the repaired helper measures `1.0456691520017047e-14 g` and `1.0742421254975782e-14 g`, and `MassEstimator` writes `1.0456416965685974e-14 g` for both—zero grams of added RNA.

**Tehol:** Wait—stop right there. An eager agent loop would have rushed off to patch clerk number three for RNA, declared victory, and walked straight into the exact same trap on proteins next week. Tell me we checked proteins before writing another patch.

**Bugg:** We did, sir—Munger's inversion again. The planner ran a one-molecule canonical-pool unit probe: not a new whole-cell run or trajectory claim, just placing **one** `MG_014_MONOMER` in `processed_i`, compartment `c`, via the canonical pool API. Karr's `ProteinMonomer` fixture gives that molecule **`1.1548196442356155e-19 g`**. Its flat mature `protein.counts` view is *rightly* zero because `processed_i` is an intermediate form. Both `compute_cell_mass` and the CSV `MassEstimator` read only the mature projection and reported **`0.0 g`**.

**Tehol:** *[whistles softly]* And there goes the `6/28` snapshot. `ProteinProcessingII` and `ProteinTranslocation` move compartmental intermediate proteins for a living! Their isolated statistical gates were real, their seventy-seven verified Git blobs were real, and yet one `processed_i` monomer weighs nothing on two of our live scales.

**Bugg:** Exactly, sir. Calling `6/28` current readiness on a revised tree with partial mass projections would be dressing an incomplete boundary in a green suit. So `9f53a27` remains a historical local snapshot, and canonical bookkeeping stays **4/28 eligible, 24 blocked**.

---

**Tehol:** Let's state the November 21 reality plainly—no fog, no "almost done" promises. Since October 19, nothing has been churning offstage?

**Bugg:** Nothing, sir. Every agent is stopped, no gates are running, `L2.5` composition has not begun, and all Cohort 1 commits remain local and unpushed while `main` takes only this post.

**Tehol:** Good. Because playing whack-a-mole across three mass readers—observer Monday, `compute_cell_mass` Tuesday, CSV `MassEstimator` Wednesday, protein intermediates whenever `L2.5` explodes—is infrastructure comedy, not science. When we unpause the bench, what is the exact bounded move?

**Bugg:** First, freeze **one bounded shared-mass contract** spanning represented RNA forms and current-cohort protein forms and compartments. Second, implement **one** fixture-derived projection shared by all three live readers—`KarrObservabilityStep`, `compute_cell_mass`, and `MassEstimator`—guarded against mature-only blind spots, mixed-store double-counting, and poisoned observer hints, with zero count inflation or rate tuning.

**Tehol:** And only after an independent reviewer tries to break all three scales with the same state basket—

**Bugg:** —do we integrate the accepted `ProteinModification` RNG repair and unified mass projection into a single frozen candidate tree, rerun **all five Cohort 1 gates once in parallel** on those final source hashes, and close strict no-known-gap publication—while keeping `RNADecay` fragment consumption explicitly open for Cohort M2.

**Tehol:** *[tucks the blanket around his knees]* In April we celebrated 4,500 lines before lunch with zero biology simulated. Seven months later we have five fifty-seed stochastic gates green, a 178-test zero-mismatch `mcg16807` repair proved while MATLAB's license sat expired, and we refused to promote a single process because one tenth-of-an-attogram monomer vanished from two scales.

**Bugg:** In whole-cell modeling, sir, maturity looks suspiciously like refusing to grade on a curve.

**Tehol:** Four honest ports and a clean bookmark beat nine premature stickers any day, Bugg. Leave the bookmark at October 19. When we open the ledger again, all three clerks read from one scale.

**Bugg:** *[picks up the broom]* One scale, sir. Whenever you're ready.

---

*This is the OpenCell dev blog. Follow the repository at [github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell). Canonical `main` remains at 4/28 pre-L2.5 processes eligible (24 blocked); Cohort 1 stochastic repairs and mass components remain on local branches pending unified three-reader mass closure and a single post-freeze five-gate rerun.*
