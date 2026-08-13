---
title: "Days 83-85: Ten Lanes, Two Greens, and the Day MATLAB Changed the Locks"
date: 2026-08-14
authors: [sdrona]
tags: [opencell, L2.1, L2.2, matlab, event-windows, rng, evidence, checkpoint]
---

**Tehol:** Bugg. We opened ten lanes.

**Bugg:** We did, sir.

**Tehol:** How many reached the other side.

**Bugg:** Two.

**Tehol:** *[waits]*

**Bugg:** Replication and RibosomeAssembly.

**Tehol:** And the other eight.

**Bugg:** Reached a locked door.

**Tehol:** All eight.

**Bugg:** The same door, mostly.

**Tehol:** Which is.

**Bugg:** MATLAB changed the locks.

---

**Tehol:** Start with what worked.

**Bugg:** Replication first. Fifty Karr seeds, one hundred ticks each, against
the corrected no-hint port. Chromosome primary PASS. Substrates SEED_NOISE.
Bound enzymes SEED_NOISE.

**Tehol:** After how many rounds of "Replication is fixed."

**Bugg:** Enough that I no longer use that sentence without a noun after it.
The topology was fixed. Then the SSB ownership. Then the primer limits. Then
RNAP collision stalls. Then terC linking. Then ligation. Then the allocator
strict-zero rule that the focused suite missed and the unit suite caught.

**Tehol:** And now.

**Bugg:** Now the N=50 row is PASS.

**Tehol:** Good. Ribosome assembly.

**Bugg:** It already had the science: fifty distinct event-window seeds,
forty-four with firings, eighty-three pooled Karr firing ticks, count, timing
and payload all inside seed noise. But the L2.event bundle and the L2.2 index
spoke different evidence dialects.

**Tehol:** So you translated.

**Bugg:** Without trusting the word PASS. The bridge reads the raw event
statistics and materializes the complete L2.2 event authority set. The index
now derives RibosomeAssembly PASS mechanically.

**Tehol:** Scoreboard.

**Bugg:** Sixteen PASS. Three FAIL. Three missing.

---

**Tehol:** L2.1.

**Bugg:** Better than the old scoreboard admitted. We found active windows for
six of the eleven rows that had looked coincidental or uninformative.

**Tehol:** Which six.

**Bugg:** DNA repair, metabolism, protein decay, replication, RNA modification
and ribosome assembly. Every one replayed bit-identically on a non-trivial
window.

**Tehol:** So the active-window-aware rubric says.

**Bugg:** Twenty-two genuine. Five missing active extraction. One fail.

**Tehol:** Chromosome condensation.

**Bugg:** Still the one.

---

**Tehol:** Tell me about the one.

**Bugg:** Karr does not start ChromosomeCondensation at tick zero with a fresh
random stream. It constructs an `mcg16807` stream, seeds it, sets ATP and water
to infinity and runs the process twenty times during initialization.

**Tehol:** You ported the stream.

**Bugg:** Exactly enough to learn that the stream was not the last missing
thing. The replay artifact shows the chromosome after initialization, after
other processes have already bound RNA polymerase and DnaA and gyrase. What we
need is the chromosome/process state immediately before those twenty warmup
calls. The only local artifact rich enough to contain it is a sixty-eight
megabyte MATLAB MCOS object whose fields our non-MATLAB tooling cannot decode.

**Tehol:** So you merged the new random generator.

**Bugg:** Briefly.

**Tehol:** Briefly.

**Bugg:** It changed a shared source hash and invalidated ProteinTranslocation's
already-green L2.2 evidence.

**Tehol:** And you removed it.

**Bugg:** The useful work remains on the ChromosomeCondensation branch. Main
keeps the green evidence green.

---

**Tehol:** That happened more than once.

**Bugg:** Three times.

**Tehol:** List them.

**Bugg:** MacromolecularComplexation added a process-specific oracle-root
override to the shared Design-A helper. Fourteen recertified rows became stale.
We removed the shared override and kept the extractor process-local.

ProteinProcessingII added active-window manifests directly to shared `h12.py`.
ProteinFolding, ProteinProcessingI and tRNAAminoacylation immediately lost
their H12 source hash. We removed it and rebuilt the PPII runner as a separate
module.

ChromosomeCondensation added `mcg16807` support to shared `matlab_rng.py`, and
ProteinTranslocation became stale. Removed.

**Tehol:** Parallelism.

**Bugg:** Parallelism with shared hashes is a room full of people editing the
same notarized page. Everyone can be right and the document still becomes
invalid.

---

**Tehol:** ProteinProcessingII, then.

**Bugg:** The existing one-hundred-tick traces were more useful than we thought.
Twenty-eight of fifty seeds already contain natural, regime-valid transferase
windows. Earliest at tick thirty-seven. We built a hash-bound manifest that
references those slices without copying the MAT files.

**Tehol:** And the other twenty-two.

**Bugg:** Need later windows beyond tick one hundred. The process-isolated
runner is merged and validates the twenty-eight. The final twenty-two wait for
MATLAB.

**Tehol:** Macromolecular complexation.

**Bugg:** Extractor ready. The early traces miss network-two because the
limiting monomer does not appear until around tick eight thousand two hundred
and sixty-four. The targeted cohort plan is ready. It waits for MATLAB.

**Tehol:** Cytokinesis.

**Bugg:** Seed zero valid, four thousand ticks. Seeds one through forty-nine
planned. Waits for MATLAB.

**Tehol:** FtsZ.

**Bugg:** Fifty pre-division windows planned. Waits for MATLAB.

**Tehol:** DNA damage.

**Bugg:** `hollidayJunctions` ported. UVB/gamma condition override and
identity-bound cohort planner ready. Waits for MATLAB.

---

**Tehol:** DNA supercoiling did not wait for MATLAB.

**Bugg:** It found other ways to hurt us.

**Tehol:** Begin.

**Bugg:** The old fifty-seed gate was underpowered. We had two hundred unique
seeds on disk, so we preregistered a sparse-event gate before reading the
result. It failed: OpenCell fired in thirty-one seeds, Karr in fifty-eight.

**Tehol:** Good. A real failure.

**Bugg:** We found a real port bug: OpenCell clipped supercoiling sigma before
writeback. MATLAB does not. We removed the clamp.

**Tehol:** And.

**Bugg:** OpenCell went from underactive to active in every seed.

**Tehol:** Improvement.

**Bugg:** Not in the direction the word normally implies.

**Tehol:** Then.

**Bugg:** Release semantics. Stable binding. Transient topoI. Random enzyme
order. ATP consumed inside the loop. Persistent RNG per biological seed.
Initialization gyrase binding. Releasable-protein accessibility. Full
chromosome binding side effects.

**Tehol:** And.

**Bugg:** Fourteen hundred and eighty-six sparse ticks on our side. Sixty-five
on Karr's.

**Tehol:** So after eight corrections, worse.

**Bugg:** More literal, not closer. Those are different axes.

**Tehol:** What finally stopped the source tour.

**Bugg:** A microscope. Seed zero, tick five. Same Karr `states_before`. Twelve
free topoIV molecules. Two legal positive-sigma regions. Four hundred and
eighty-four accessible candidate starts. Both our arithmetic and the visible
MATLAB source arithmetic say bind twelve. Karr's after-state says bind zero.

**Tehol:** Meaning.

**Bugg:** The missing cause is in chromosome state that the trace does not
serialize: `damagedSites`, `doubleStrandedRegions`, caches used by
`getAccessibleRegions`. The visible inputs are insufficient to reconstruct
Karr's decision.

**Tehol:** So the DNAS branch stays out of main.

**Bugg:** Correct.

---

**Tehol:** Now the door.

**Bugg:** `E:\MATLAB\bin\matlab.exe`.

**Tehol:** It exists.

**Bugg:** It exits before startup.

**Tehol:** Message.

**Bugg:** `MathWorks Licensing Error 10. Your license for MATLAB has expired.`

**Tehol:** Which tracks does that stop.

**Bugg:** ChromosomeCondensation state recovery. Five L2.1 active windows.
MacromolecularComplexation's fifty active windows. ProteinProcessingII's
remaining twenty-two. DNAS hidden chromosome state. Cytokinesis forty-nine.
FtsZ fifty. DNA damage's stimulus cohort.

**Tehol:** Seven tracks.

**Bugg:** Eight, if you count the active-window batch separately from its five
processes.

**Tehol:** And what remains running.

**Bugg:** Nothing. We reached the license boundary.

---

## Honest scoreboard

| Gate | Current status |
|---|---|
| **L2.1** | **22 GENUINE / 5 MISSING_ACTIVE_EXTRACTION / 1 FAIL** |
| **L2.2** | **16 PASS / 3 FAIL / 3 MISSING_EVIDENCE**, integrity OK |
| **L2.4** | PASS, 100 ticks x 4 seeds, implemented v1 scope |
| **L2.5** | not started; blocked until L2.1 and L2.2 close |
| **Ten-track wave** | 2 closed / 8 blocked |

---

**Tehol:** Did the parallel wave fail?

**Bugg:** No. It converted eight vague blockers into executable extraction
plans and one precise external dependency. It also closed two rows and moved
six L2.1 rows to genuine.

**Tehol:** Did it finish the gates?

**Bugg:** No.

**Tehol:** Then say both.

**Bugg:** The wave worked. The gates remain open. The next experiment requires
a valid MATLAB license.

**Tehol:** *[closes his eyes]* Good. Publish that, not the version where we
almost finished.

---

*This is the OpenCell dev blog. The repo is
[github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell).
The next post begins when MATLAB opens again.*

