---
title: "Days 86-104: MATLAB Came Back, Negative Zero Stopped DNA Damage, and One Green Survived the Audit"
date: 2026-09-02
authors: [sdrona]
tags: [opencell, L2.1, L2.2, matlab, rng, evidence, dna-damage, protein-processing, checkpoint]
---

**Tehol:** Bugg. MATLAB opened.

**Bugg:** It did, sir.

**Tehol:** After four days.

**Bugg:** The license was restored. We tested MATLAB. It printed a version
number. It claimed Statistics Toolbox was licensed.

**Tehol:** So we opened all eight lanes.

**Bugg:** Immediately.

**Tehol:** And.

**Bugg:** The license was not the last lock.

**Tehol:** Of course it wasn't.

---

**Tehol:** Start at the beginning.

**Bugg:** We launched eight isolated closure tracks: five missing L2.1 active
windows, ChromosomeCondensation, MacromolecularComplexation,
ProteinProcessingII, DNASupercoiling, Cytokinesis, FtsZPolymerization and
DNADamage.

**Tehol:** That is more than eight.

**Bugg:** The active-window batch contains five processes. The accounting gets
unpleasant if you look at it directly.

**Tehol:** And ReplicationInitiation.

**Bugg:** That arrived after we reran the L2.1 baseline.

**Tehol:** Arrived.

**Bugg:** It had been standing in the room the whole time. The old summary said
twenty-two genuine, five missing and one fail. The actual classifier said
twenty-one genuine, one partial, five missing and one fail.

**Tehol:** The partial was.

**Bugg:** ReplicationInitiation. Karr fired on one hundred and three active
ticks. OpenCell fired on fifty-five of them in the original summary.

**Tehol:** So our eight-lane closure wave became nine lanes.

**Bugg:** That is how biology responds to project management, sir.

---

**Tehol:** Tell me about Statistics Toolbox.

**Bugg:** MATLAB said:

`license('test', 'Statistics_Toolbox') == 1`

**Tehol:** Which means the toolbox exists.

**Bugg:** It means the license permits it to exist.

**Tehol:** Ah.

**Bugg:** The files did not exist. No `toolbox/stats`. No genuine `mnrnd.m`.

**Tehol:** But our simulations ran.

**Bugg:** Because the repository contains a compatibility `mnrnd.m`.

**Tehol:** Is it correct?

**Bugg:** It is a reasonable multinomial sampler. It is not MATLAB's
multinomial sampler. It consumes random numbers differently.

**Tehol:** Meaning every later state can move.

**Bugg:** Correct. ProteinProcessingII calls `mnrnd` during a whole-cell run.
Therefore a Cytokinesis extraction can be contaminated by an `mnrnd` shim even
though Cytokinesis never calls `mnrnd`.

**Tehol:** Because the whole cell runs to reach cytokinesis.

**Bugg:** Exactly.

**Tehol:** Did we notice before extracting anything.

**Bugg:** No.

**Tehol:** Naturally.

---

**Tehol:** ProteinProcessingII first.

**Bugg:** The first attempt looked excellent. Twenty-two new active windows.
Fifty of fifty seeds. Every non-trivial sample matched the source-derived
predictor. `H12_CONFIRMED`.

**Tehol:** Green.

**Bugg:** Rejected.

**Tehol:** Why.

**Bugg:** Independent review inspected the MAT metadata. Every new trace
carried the hash of our repository `mnrnd.m`.

**Tehol:** So we had proven exact agreement with a trajectory produced by the
wrong random function.

**Bugg:** We had also written all fifty manifest paths as absolute paths to
this machine and routed twenty-two files around the oracle-population
provenance check by calling them external fixtures.

**Tehol:** A three-part green.

**Bugg:** Wrong RNG. Non-portable manifest. Provenance escape hatch.

**Tehol:** Did the test pass.

**Bugg:** Beautifully.

**Tehol:** I am beginning to dislike that word.

---

**Tehol:** So we installed the real toolbox.

**Bugg:** Statistics and Machine Learning Toolbox 26.1. Then we verified the
actual provider:

`E:\MATLAB\toolbox\stats\stats\mnrnd.m`

**Tehol:** Done.

**Bugg:** Not done. The extractor adds `scripts/matlab` to the front of the
MATLAB path, so the repository shim still won.

**Tehol:** We installed the toolbox and continued using the shim.

**Bugg:** Briefly.

**Tehol:** Bugg.

**Bugg:** We built a fail-closed provider contract.

**Tehol:** For `mnrnd`.

**Bugg:** For five functions.

**Tehol:** Five.

**Bugg:** `binornd`, `mnrnd`, `poissrnd`, `random` and `randsample`. The repo
contains compatibility versions of all five. Promoting the Statistics Toolbox
directory changes all five providers, so binding only `mnrnd` would have been
another partial truth.

**Tehol:** What does the contract record.

**Bugg:** MATLAB release, toolbox version, each provider's path relative to
`matlabroot`, and each provider's hash. Bootstrap verifies them before loading
the fitted simulation and again after returning to the caller's working
directory.

**Tehol:** Why twice.

**Bugg:** MATLAB searches the current directory before the configured path. A
caller standing inside `scripts/matlab` could pass the first check, return to
the shim directory and silently switch providers again.

**Tehol:** You found that yourself.

**Bugg:** The reviewer found it.

**Tehol:** Good reviewer.

**Bugg:** The reviewer also found that our general L2.2 extraction launcher
printed provider failures and returned success.

**Tehol:** A success-shaped failure.

**Bugg:** We have a collection.

---

**Tehol:** And the second ProteinProcessingII attempt.

**Bugg:** Twenty-two windows re-extracted with the genuine providers. A tracked
MATLAB driver. Provider identity in every later trace. Driver, source, fixture,
seed, tick range and MAT hashes in every manifest row. Repository-relative
paths. Fresh-clone relocation test.

**Tehol:** Fifty of fifty.

**Bugg:** Fifty of fifty. Five hundred and eighty-one non-trivial samples.
Five hundred and eighty-one exact matches. All three required branches:
passthrough, peptidase and transferase.

**Tehol:** Reviewer.

**Bugg:** Accepted.

**Tehol:** Current-tree sweep.

**Bugg:** Passed.

**Tehol:** Shared index.

**Bugg:** Regenerated mechanically from the complete tracked bundle.

**Tehol:** So this one is actually green.

**Bugg:** ProteinProcessingII is closed.

---

**Tehol:** One.

**Bugg:** One.

**Tehol:** Out of eight.

**Bugg:** Seven original lanes remain. Plus ReplicationInitiation.

**Tehol:** Progress has an unusual shape in this project.

**Bugg:** It is mostly the shape of things we are no longer allowed to lie
about.

---

**Tehol:** DNA damage.

**Bugg:** That one discovered negative zero.

**Tehol:** There is no negative zero.

**Bugg:** IEEE 754 disagrees.

**Tehol:** Explain without becoming happy.

**Bugg:** Karr computes the maximum number of reactions from substrate counts
divided by the required stoichiometry:

`substrates / max(0, -stoichiometry)`

Some zero stoichiometry entries become negative zero after unary negation.
Modern MATLAB preserves the sign through `max`. Positive substrate divided by
negative zero becomes negative infinity.

**Tehol:** Then `maxReactions <= 0`.

**Bugg:** And every UV reaction exits before damaging DNA.

**Tehol:** So the first fifty UV traces showed the radiation substrate, a
non-zero expected rate, abundant vulnerable motifs and zero damage.

**Bugg:** Correct. We normalized the non-negative denominator with `abs`.
Nothing positive changes; only negative zero becomes positive zero.

**Tehol:** Karr events.

**Bugg:** Five-seed canary: eight fire ticks against an expected 9.72. Full
fifty-seed cohort: ninety-nine fire ticks against an expected 97.22.

**Tehol:** Finally.

**Bugg:** Then OpenCell fired on nine hundred and ninety-two of one thousand
ticks.

**Tehol:** Of course.

**Bugg:** Karr produced ninety-nine crosslinks. OpenCell produced four thousand
three hundred and ninety-one.

**Tehol:** Why.

**Bugg:** OpenCell uses a hardcoded lumped UV rate of `0.6` per second. Karr's
source-derived aggregate rate is `0.0133795`.

**Tehol:** Ratio.

**Bugg:** Forty-four point eight five.

**Tehol:** Observed ratio.

**Bugg:** Forty-four point three five.

**Tehol:** At least the bug signed its work.

**Bugg:** The per-reaction rate-law repair exists on the branch. Branch-local
evidence says PASS. It still needs independent review and integration before
the scoreboard moves.

---

**Tehol:** Chromosome condensation.

**Bugg:** MATLAB let us open the opaque object.

**Tehol:** The sixty-eight megabyte one.

**Bugg:** We captured the exact state before and after its twenty-call
initialization warmup. We also learned our `mcg16807` implementation was wrong.

**Tehol:** Wrong multiplier.

**Bugg:** The Park-Miller multiplier was fine. MATLAB's exposed `State` is an
encoded scalar, not the raw generator state. We reverse-engineered the
encoding from live restored-state vectors.

**Tehol:** Then the warmup state matched.

**Bugg:** Then we discovered the extraction boundary reseeds every process
after loading the fitted snapshot. The chromosome keeps the warmup's physical
effects; the process random stream returns to the seed's initial state.

**Tehol:** A hybrid state.

**Bugg:** Source-faithful, unfortunately.

**Tehol:** Result.

**Bugg:** The official branch strict rubric now says GENUINE. But a deeper
hidden-state probe still finds one SMC site shifted at tick seven.

**Tehol:** So not closed.

**Bugg:** Not under the no-known-gap rule. The independent review was
interrupted before it could adjudicate whether that hidden field is an
applicable process output or another process's mutation.

---

**Tehol:** DNA supercoiling.

**Bugg:** The hidden chromosome fields were necessary, but they were not the
answer we first expected.

**Tehol:** The old microscope said two regions had positive sigma.

**Bugg:** Because the visible linking numbers were rounded to thirty. The
hidden `superhelicalDensity` says their real sigma is zero. Karr never calls
topoIV binding there. We fixed that.

**Tehol:** The fourteen hundred events.

**Bugg:** The gate still called them PASS because the sparse-support test only
looked for underactivity. It could reject zero events but could not reject
twenty-two times too many.

**Tehol:** Reviewer.

**Bugg:** Rejected the gate.

**Tehol:** Good reviewer.

**Bugg:** We also separated random-stream ownership. Gyrase release draws come
from the chromosome stream, not the process stream. That fixed the first
release divergence.

**Tehol:** Remaining difference.

**Bugg:** At tick five, OpenCell writes linking number 51933. Karr writes
51932. One downstream random-consumption difference remains. No new N=200
gate will run until that source gap closes and a two-sided sparse rule is
preregistered.

---

**Tehol:** The extraction lanes.

**Bugg:** MacromolecularComplexation has thirty-six of fifty genuine active
windows. Fourteen remain.

**Tehol:** FtsZ.

**Bugg:** Two of fifty. Each of the first two genuine seeds took roughly six
hours and fifty minutes.

**Tehol:** Forty-eight times seven hours.

**Bugg:** Across shared slots, yes.

**Tehol:** Cytokinesis.

**Bugg:** Zero of fifty in the clean genuine-provider cohort. The old seed was
shim-bound and no longer counts.

**Tehol:** L2.1 active windows.

**Bugg:** One local DNADamage candidate. No genuine trace yet for
TranscriptionalRegulation, ChromosomeSegregation, Cytokinesis or
HostInteraction. Nothing has been promoted into the manifest.

**Tehol:** ReplicationInitiation.

**Bugg:** DnaA identity mapping and random-stream work landed on the branch.
The active replay now reaches tick nine before the first mismatch. Eleven
focused tests pass; three fail. The remaining gap is initialization and
unweighted non-origin DnaA binding.

---

## Honest scoreboard

| Gate | Current authoritative status |
|---|---|
| **L2.1** | **21 GENUINE / 1 PARTIAL / 5 MISSING_ACTIVE_EXTRACTION / 1 FAIL** |
| **L2.2** | **17 PASS / 2 FAIL / 3 MISSING_EVIDENCE**, integrity OK |
| **L2.4** | PASS, 100 ticks x 4 seeds, implemented v1 scope |
| **L2.5** | not started; blocked until L2.1 and L2.2 close |
| **Original eight open lanes** | **1 closed / 1 review candidate / 6 open** |

---

**Tehol:** So MATLAB came back.

**Bugg:** Then we learned a license flag is not an installed toolbox, an
installed toolbox is not the selected function, and the selected function is
not stable if the caller stands in the wrong directory.

**Tehol:** We closed one process.

**Bugg:** And removed three ways to generate evidence that looked valid but
was not.

**Tehol:** Is that progress.

**Bugg:** It is slower than a green counter and faster than building on a false
one.

**Tehol:** Current processes.

**Bugg:** None running at this checkpoint. Two orphan lock files from the
August runs were removed. The branches and partial trace cohorts remain on
disk, ready to resume.

**Tehol:** Then what do we say.

**Bugg:** The license problem is over. The evidence problem is not. One more
lane is genuinely closed, one has a reviewable candidate, and every remaining
red is narrower than it was.

**Tehol:** Publish that.

**Bugg:** The version where we say "almost green."

**Tehol:** Delete it.

---

*This is the OpenCell dev blog. The repo is
[github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell).
The next post begins with seven lanes, four MATLAB slots, and no tolerance for
a green light wearing somebody else's random-number generator.*
