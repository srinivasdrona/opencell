# Day 7: Sixteen of Twenty-Eight

*May 22, 2026*

---

**Tehol:** Bugg, you appear to be smiling.

**Bugg:** A consequence of progress, sir, and possibly low blood sugar.

**Tehol:** Quantify the progress.

**Bugg:** Sixteen of twenty-eight Karr processes, with mass balance holding over two thousand ticks. The chassis assembles complexes, degrades them, transcribes RNA, translates protein, charges tRNAs, folds peptides, modifies their N-termini, translocates the membrane ones, activates the regulated ones, and decays the lot. In approximately the proportions one would expect.

**Tehol:** And the original schedule estimated this in?

**Bugg:** Eighteen weeks.

**Tehol:** Bugg.

**Bugg:** Yes sir.

**Tehol:** I am not certain whether to congratulate you or to inquire about the schedule's relationship to reality.

**Bugg:** A line of inquiry I have so far declined to pursue.

---

## What changed

**Bugg:** The pattern.

**Tehol:** Elaborate.

**Bugg:** Yesterday I delegated to Codex one task at a time. Today I delegated eleven Phase B turns concurrently. While Codex implemented turn two, I designed turn three. While turn three ran, I designed turn four. By turn ten, I was four turns ahead and the bottleneck had become my willingness to stay awake.

**Tehol:** You ran ten of these — what was the word — sessions in parallel.

**Bugg:** At one point, eleven. Each in its own git worktree, with its own Vivarium chassis fragment, its own scratchpad, and its own quietly fatal misunderstanding of which Python interpreter it was meant to use.

**Tehol:** Ah.

**Bugg:** Three of them spent half an hour on a Windows interpreter that lacked the editable install of the project they were trying to test. I had not told them which interpreter to use. They had inferred. Incorrectly.

**Tehol:** And the lesson, encoded somewhere.

**Bugg:** Encoded in the orchestrator's standing instructions, sir. Every future delegation now begins with a paragraph informing the executor that WSL is not optional.

---

## The probe that mattered

**Tehol:** What did you nearly get wrong.

**Bugg:** I had been about to assume that two Vivarium processes could write to the same state leaf with different update semantics — one absolute, one relative — and that the framework would reconcile them sensibly.

**Tehol:** Would it?

**Bugg:** No. It would silently elect whichever updater type was declared last and apply it to all updates. The order of declaration would matter. Mass conservation would break invisibly. The simulation would continue, untroubled by its own corruption.

**Tehol:** And the discovery was made by?

**Bugg:** A fifty-line test that took half an hour to write. The findings persuaded me to convert two existing processes to emit deltas rather than absolutes. Tedious, but not invasive — eighty lines of new code, no broken tests.

**Tehol:** A small probe averting a large catastrophe.

**Bugg:** A pattern I shall be repeating.

---

## The MATLAB Hour

**Tehol:** And the license.

**Bugg:** The temporary MATLAB license expires in days. So I asked Codex, in parallel with the chassis work, to extract everything I might plausibly want. One full Karr cell cycle, twenty-eight per-process traces, twenty-three initialisation snapshots, two fitted-constant tables. Roughly eighteen megabytes of ground truth that we could not otherwise produce.

**Tehol:** Before the door closed.

**Bugg:** Before the door closed.

---

## What the chassis cannot yet do

**Tehol:** Be specific about the gaps.

**Bugg:** It cannot replicate its chromosome. It cannot divide. It cannot interact with a host. Twelve of the twenty-eight processes remain unwritten. The first of them, replication initiation, is now in main; the largest, replication itself, awaits design tomorrow. I will not promise the same compression of timeline again — DNA mechanics involve states that persist across the cell cycle and discrete events that fire once or twice in nine hours. The Codex pipeline was made for fast, similar things. Slow, dissimilar things are next.

**Tehol:** A note of humility creeping in.

**Bugg:** Earned, sir.

---

## Bottom line

**Tehol:** The summary, then.

**Bugg:** Sixteen of twenty-eight. The chassis does not yet live, but it metabolises, transcribes, translates, complexes, decays. It charges its tRNAs and folds its peptides. It runs at sixty ticks per second and stays in steady state for thirty-three minutes of biological time.

**Tehol:** Which is to say.

**Bugg:** Which is to say I have a small, briefly-living, partly-functioning organism made of NumPy arrays. Tomorrow I give it a chromosome.

---

*Day 8 ships when the chromosome ships.*
