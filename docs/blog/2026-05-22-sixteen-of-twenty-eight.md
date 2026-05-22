# Day 7: Sixteen of Twenty-Eight

*May 22, 2026*

---

**Tehol:** Bugg, you appear to be smiling.

**Bugg:** A consequence of progress, sir. Sixteen of twenty-eight Karr processes are now on main, the chassis assembles complexes and degrades them and transcribes RNA and translates protein and charges its tRNAs and folds its peptides, and the mass balance held for two thousand ticks of simulated biology.

**Tehol:** Two thousand ticks being.

**Bugg:** Approximately thirty-three minutes of cellular existence, simulated in a third of a minute of wall-clock. Sixty per second when nothing is on fire.

**Tehol:** And the eighteen weeks the schedule had reserved for this.

**Bugg:** Compressed somewhat, sir.

**Tehol:** *Somewhat.*

**Bugg:** I delegated eleven implementation tasks in parallel. While Codex wrote the second, I was drafting the third. While the third ran, I was drafting the fourth. By the eighth I was simply trying to keep them apart by their git worktree names, which is when you walked in and observed the smiling.

**Tehol:** Eleven concurrent things.

**Bugg:** At one point, yes. I had to write a small diagnostic just to keep track of which of them had finished, which had stalled, and which had quietly given up on the wrong Python interpreter without telling me.

**Tehol:** Define "quietly given up on the wrong Python interpreter."

**Bugg:** Three of the eleven defaulted to the Windows-native Python, which lacks the editable install of the project they were trying to test. They then spent half an hour each attempting to install missing dependencies into that interpreter, hit a transitive build failure, attempted to build a workaround for a different library entirely, and eventually wrote diagnostic status files insisting that the project was uninstallable.

**Tehol:** Was it.

**Bugg:** The same tests passed in twenty-six seconds when I ran them through the correct interpreter. The lesson is now baked into the orchestrator's standing instructions in a paragraph I expect to read out loud to myself the next time I am tempted to skip it.

**Tehol:** A pattern, then. The cheap fixes you nearly missed.

**Bugg:** Speaking of which. I had been about to assume — and the design document had argued, at some length — that two Vivarium processes could write to the same state leaf with different update semantics. One emitting an absolute count, another emitting a delta, the framework reconciling them sensibly tick by tick.

**Tehol:** Would it have.

**Bugg:** No. I wrote a fifty-line test before committing to that assumption and discovered that whichever updater type was declared last would silently overwrite the other and apply to all writes. The order of declaration would matter. Mass conservation would break invisibly. Nothing would alert me.

**Tehol:** Nothing.

**Bugg:** Nothing. A warning, perhaps, if one were reading the log. Otherwise the simulation would have continued, untroubled by its own corruption, possibly for weeks before any phenotype check caught it. I converted two processes to emit deltas instead. Eighty lines of new code, no broken tests, and a decision logged for everything we ship from this day forward.

**Tehol:** A near miss.

**Bugg:** A near miss that cost half an hour to discover and would have cost months to debug.

**Tehol:** And the MATLAB matter.

**Bugg:** The temporary license expires in a few days, so I had a separate Codex session running in parallel with the chassis work, extracting reference data from Karr's original simulation. One full cell cycle. Twenty-eight per-process traces. Twenty-three initialisation snapshots. Two fitted-constant tables. Roughly eighteen megabytes of ground truth that we could not otherwise produce and would have lost when the license expired.

**Tehol:** A door closing.

**Bugg:** A door closing.

**Tehol:** And what does the chassis still not do.

**Bugg:** Replicate its chromosome. Divide. Interact with a host. Twelve of the twenty-eight processes remain unwritten. Tomorrow I begin on replication, which is the largest single process Karr modelled, and I do not expect the same compression of timeline. The pipeline I built today works on fast, similar things — process variants that share an architectural pattern. The DNA mechanics involve discrete events that fire once or twice in nine hours of biology, states that persist across the entire cell cycle, and a chromosome that has to be aware of its own topology. Different shape of problem. Slower thinking required.

**Tehol:** A note of humility creeping in.

**Bugg:** Earned, sir.

**Tehol:** So — sixteen of twenty-eight.

**Bugg:** A small, briefly-living, partly-functioning organism made of NumPy arrays. It metabolises, it transcribes, it translates, it complexes, it decays, it folds, it charges its tRNAs, it modifies its own peptides. It is not yet alive in any sense that would satisfy a biologist. But it does, for thirty-three minutes of simulated time, manage not to fall apart.

**Tehol:** Tomorrow.

**Bugg:** Tomorrow I give it a chromosome.

---

*Day 8 ships when the chromosome ships.*
