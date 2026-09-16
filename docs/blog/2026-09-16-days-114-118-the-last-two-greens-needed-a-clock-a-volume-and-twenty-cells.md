---
title: "Days 114-118: The Last Two Greens Needed a Clock, a Volume, and Twenty Cells"
date: 2026-09-16
authors: [sdrona]
tags: [opencell, L2.2, cytokinesis, ftsz, matlab, rng, evidence, milestone]
---

**Tehol:** Bugg.

**Bugg:** Sir.

**Tehol:** How many empty chairs.

**Bugg:** None.

**Tehol:** Say the board.

**Bugg:** Twenty-two PASS. Zero FAIL. Zero MISSING_EVIDENCE. Aggregate
GREEN. Integrity OK.

**Tehol:** Again.

**Bugg:** Twenty-two out of twenty-two.

---

**Tehol:** The last post ended with two processes waiting for the cell to
divide.

**Bugg:** Cytokinesis and FtsZPolymerization.

**Tehol:** And fifty required divisions.

**Bugg:** We changed that.

**Tehol:** Before or after seeing the final result.

**Bugg:** Before running the new gates. The extraction had occupied nearly a
month. Sampling uncertainty improves with the square root of the sample
count; wall time was increasing almost linearly and sometimes worse because
some simulated cells never divided.

**Tehol:** So the engineering gate is twenty.

**Bugg:** The first twenty completed windows from the same ascending seed
stream. Censored seeds still count as attempts and never as completions. No
resampling. No skipping inconvenient seeds. The original fifty-completion
cohort remains deferred confirmatory evidence for a publication-grade claim.

**Tehol:** A smaller claim, written down before asking the question.

**Bugg:** Exactly.

---

**Tehol:** We already had more than twenty traces.

**Bugg:** We had traces missing two inputs.

**Tehol:** Of course.

**Bugg:** The first FtsZ pilot failed honestly. Its enzyme distance was
`0.581578` against a Karr-only threshold of `0.174015`. The substrate
distance failed too.

**Tehol:** Biology bug.

**Bugg:** Input bug. MATLAB converts molecule counts to concentrations using
the cell's live `geometry.volume` every tick. OpenCell used the fixture volume
forever because the trace did not carry the live value.

**Tehol:** And Cytokinesis.

**Bugg:** Its conditional diameter formula matched, but the trace omitted the
process's private random-stream state. We knew when Karr contracted and could
prove OpenCell's deterministic diameter calculation on those ticks. We could
not prove whether OpenCell would independently choose the same contraction
ticks.

**Tehol:** The gate passed anyway.

**Bugg:** The first version would have.

**Tehol:** Reviewer.

**Bugg:** Rejected it. One payload mismatch equaled the threshold and still
passed. OpenCell was evaluated only on ticks where Karr had already
contracted, so over-firing was impossible to observe. We had also changed the
catalog primary channel to fit what the trace happened to expose.

**Tehol:** Three varieties of green paint.

**Bugg:** We removed all three.

---

**Tehol:** What did the extractor need.

**Bugg:** Two additions in the same whole-cell pass:

- Cytokinesis `randStreamState` before and after every process call;
- FtsZ `geometry_volume` before and after every process call.

Old traces now fail closed for full authority. No backfill can recreate a
random-stream state or a live volume that was never recorded.

**Tehol:** Then the canary.

**Bugg:** Failed before simulation.

**Tehol:** Naturally.

**Bugg:** The extractor's new provenance guard asked MATLAB for its own
source path. `mfilename('fullpath')` returned the path without `.m`. The
hasher tried opening the extensionless file.

**Tehol:** So our source-verification code could not find its source.

**Bugg:** It failed closed, which is the flattering description. We fixed
the path, added the exact Windows regression and reran seed 36.

**Tehol:** Result.

**Bugg:** Both traces valid. Same completion tick. Same DNADamage source.
Same genuine Statistics Toolbox providers. Cyt full-replay ready. FtsZ live
volume present.

**Tehol:** Actual replay.

**Bugg:** Cytokinesis: five thousand of five thousand ticks, thirteen audited
fields, zero mismatches, one hundred and forty-seven Karr contraction events
and one hundred and forty-seven OpenCell events.

**Tehol:** FtsZ.

**Bugg:** Active on all two hundred ticks, exact monomer conservation. The
single-seed distances fell to `0.0743` for enzymes and `0.02825` for
substrates once the live volume was supplied.

---

**Tehol:** Then we needed twenty new traces.

**Bugg:** And the MATLAB trial license said one day remaining.

**Tehol:** So.

**Bugg:** Six isolated worktrees. Six MATLAB processes. Non-overlapping seed
shards. One global banking lock. One monitor applying the ascending-seed
contract. One stop flag when twenty valid completions became selectable.

**Tehol:** Did the monitor work.

**Bugg:** The first one died because its WSL command contained Windows line
endings and because the new validator correctly rejected the old traces it
was replacing.

**Tehol:** We have a talent for building monitors that need monitoring.

**Bugg:** The workers were unaffected. We restarted the monitor with a
single-line command and treated old-schema rejection as transient while
workers were active.

**Tehol:** Final cohort.

**Bugg:** Attempts zero through thirty-three. Twenty-two completed, twelve
right-censored. The selector took the first twenty completions:

`0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 17, 21, 22, 23, 24, 27, 29, 30`

Zero duplicate trace hashes. Zero source mismatches. Zero invalid censors.
Zero rejected traces.

---

**Tehol:** Cytokinesis authority.

**Bugg:** Twenty seeds times five thousand ticks: one hundred thousand full
`next_update` replays.

**Tehol:** Mismatches.

**Bugg:** Zero across substrates, chromosome, enzymes, bound enzymes, four
FtsZ-ring edge surfaces, pinched diameter, random-stream state, water
request, derived outputs and output contract.

**Tehol:** Events.

**Bugg:** Two thousand nine hundred and forty contraction events on both
sides. Count distance zero. Timing distance zero. Payload distance zero.

**Tehol:** FtsZ authority.

**Bugg:** Ten Karr-only calibration seeds and ten independent evaluation
seeds. Five distinct symmetric calibration splits. Fixed multiplier three.

**Tehol:** Numbers.

**Bugg:** Enzymes: `0.02268`, threshold `0.13392`. Substrates: `0.00650`,
threshold `0.08019`. All evaluation seeds active. Every support guard clear.
Monomer discrepancy exactly zero.

**Tehol:** Reviewer.

**Bugg:** Independently rehashed all forty trace inputs and eleven code
inputs. Recomputed the selector, the Cyt replay, the FtsZ calibration and
both verdicts. Accepted.

---

## Honest scoreboard

| Gate | Published authoritative status |
|---|---|
| **L2.1 active-window manifest** | **11 / 11 EXISTING_WINDOW_PASS** |
| **L2.2** | **22 PASS / 0 FAIL / 0 MISSING_EVIDENCE**, aggregate GREEN, integrity OK |
| **L1b wiring** | **28 / 28 PASS** |
| **L2.4 conservation** | PASS, 100 ticks x 4 seeds |
| **L2.2 CI acceptance** | Blocking `--require-all-pass` gate active |

---

**Tehol:** Caveats.

**Bugg:** The division cohort is an engineering N=20 claim. N=50 remains
deferred confirmation. FtsZ calibrates on half the cohort and evaluates on
the other half. These gates replay each process from Karr's recorded
before-state; they prove process behavior under the reference trajectory,
not agreement between two independently free-running whole cells.

**Tehol:** So what did we finish.

**Bugg:** Every applicable exact-replay active window. Every in-scope
per-process distributional gate. Every missing evidence row.

**Tehol:** And what begins now.

**Bugg:** Coupling. The individual musicians have passed their auditions.
Next we find out whether they can share the stage without stealing one
another's ATP.

**Tehol:** L2.5.

**Bugg:** L2.5.

**Tehol:** Does the board stay green if someone changes a source file.

**Bugg:** CI now regenerates the evidence index and runs
`--require-all-pass`. A stale, missing or non-PASS row blocks the merge.

**Tehol:** Good.

**Bugg:** Sir?

**Tehol:** Twenty-two.

**Bugg:** Twenty-two.

---

*This is the OpenCell dev blog. The repo is
[github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell).
The L2.1 and L2.2 process-fidelity campaign is complete. The next chapter is
shared-pool composition.*
