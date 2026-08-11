---
title: "Days 75-82: Fourteen Greens Came Back, Fifty Files Were One Seed, and Ten Lanes Waited at the Gate"
date: 2026-08-11
authors: [sdrona]
tags: [opencell, L2.1, L2.2, evidence, matlab, event-windows, parallelism, checkpoint]
---

**Tehol:** Bugg. You said L2.2 had zero passes.

**Bugg:** Mechanically, sir.

**Tehol:** That is not an answer. Fourteen processes were inside their
stochastic bounds a week earlier. Did all fourteen simultaneously forget how
to be cells?

**Bugg:** No, sir. Their evidence forgot how to be current.

**Tehol:** Explain the difference before I throw the ladder at you.

**Bugg:** Every Design-A evidence bundle records the exact hashes of the runner,
the projections, the replay helper and the process code that produced it. We
merged a CI cleanup, bounded a cache that had eaten thirty gigabytes, changed
the common replay helper, repaired chromosome projections and touched the
catalog. The biological measurements in the fourteen bundles still passed.
The source hashes did not match anymore, so the fail-closed generator called
every row `FAIL`.

**Tehol:** Which you repeated to me as if the biology had failed.

**Bugg:** I did, sir.

**Tehol:** And then?

**Bugg:** We froze the tree and reran all fourteen. Fifty Karr seeds each, at
their actual catalog tick depth. DNARepair at two hundred. ProteinDecay at two
hundred. ReplicationInitiation at two hundred. The others at twenty, fifty or a
hundred as specified. Fourteen passed again.

**Tehol:** So the scoreboard returned to fourteen, four, four.

**Bugg:** With a difference. This time the fourteen are bound to the current
tree and the audit re-hashes the raw inputs. The oracle population manifest
covers all eighteen Design-A rows, fifty of fifty seeds each. `integrity: OK`.

**Tehol:** How long did it take to prove that nothing had changed?

**Bugg:** Five hours of wall time for the detached run.

**Tehol:** *[stares at him]*

**Bugg:** ProteinDecay alone took six thousand one hundred and three seconds.

**Tehol:** I did not ask you to make it sound better.

---

**Tehol:** And L2.1?

**Bugg:** Sixteen genuine. Five coincidental. Six uninformative. One literal
failure.

**Tehol:** The one.

**Bugg:** ChromosomeCondensation.

**Tehol:** The eleven that are not failures and not successes.

**Bugg:** Mostly a clock problem. The trace begins at birth and runs one hundred
ticks. Cytokinesis does not divide. Ribosome assembly has not reached its
active regime. DNA damage sees no radiation. Chromosome segregation does not
segregate. Running the same inactive trace again would produce the same honest
nothing.

**Tehol:** So we need active windows.

**Bugg:** Yes, sir. One mechanical track to find them, not eleven people each
inventing a different definition of "active."

---

**Tehol:** You also told me we needed more MATLAB extraction.

**Bugg:** Sometimes.

**Tehol:** There are thousands of MAT files on that disk.

**Bugg:** There are hundreds of copies of the same fifty seeds on that disk.
ProteinProcessingII appears three hundred and fifty-four times and contains
fifty unique seed identities. MacromolecularComplexation appears four hundred
and fifty-two times and contains fifty. Replication appears three hundred and
six times and contains fifty. DNASupercoiling appears six hundred and three
times and contains two hundred.

**Tehol:** File count is not evidence count.

**Bugg:** Nor is the right seed the right window. The fifty
MacromolecularComplexation traces cover the first hundred ticks, when its
network-of-two substrate is zero. A real full-cycle scan found that substrate
leaving zero at tick eight thousand two hundred and sixty-four. The files are
real. They answer the wrong temporal question.

**Tehol:** ProteinProcessingII.

**Bugg:** Fifty real seeds. Zero `transferase_fires` coverage.

**Tehol:** Cytokinesis.

**Bugg:** One usable seed. Its onset-to-pinch interval is almost three thousand
nine hundred ticks. The old hundred-tick contract failed closed, correctly.

**Tehol:** FtsZ.

**Bugg:** Two early traces. Zero division-anchored traces.

**Tehol:** DNA damage.

**Bugg:** A hundred-tick trace and a thirty-two-thousand-four-hundred-tick
trace. Both no-stimulus. Zero useful irradiated traces.

**Tehol:** Ribosome assembly.

**Bugg:** Fifty real event windows, all hash-distinct. Forty-four seeds fire.
Eighty-three pooled Karr firing ticks. Count, timing and payload all land inside
the seed-noise null. PASS.

**Tehol:** Yet the L2.2 index calls it missing.

**Bugg:** The event gate and the Design-A index still speak different evidence
dialects. The science is done. The bookkeeping bridge is not.

---

**Tehol:** Replication.

**Bugg:** We ported the remaining no-hint mechanics from the MATLAB source:
lead-gap limits, primer kinetics, RNAP and terC stalls, ligation, ATP and water
hydrolysis products, PPi, explicit process RNG. Then the unit suite found a
strict-zero regression because the requested substrates were initialized from
the shared pool rather than the process allocation.

**Tehol:** After the focused suite had passed.

**Bugg:** After one hundred and fifty-eight focused tests had passed.

**Tehol:** And the fix.

**Bugg:** The allocation grant is now the baseline for requested substrates.
No global fallback. The full unit suite passes. L1b is one hundred and fifteen
of one hundred and fifteen methods and twenty-eight of twenty-eight wiring
rows again.

**Tehol:** Macromolecular complexation.

**Bugg:** The closed-form demotion was withdrawn. Karr's network-two branch is
Monte Carlo and naturally reachable; both competing pentamers formed in the
real scheduler scan. It now needs active-window distributional evidence rather
than a deterministic-convergence excuse.

**Tehol:** DNASupercoiling.

**Bugg:** Two hundred unique seeds. Enough data. The wrong acceptance rule. The
proposed event-rate tolerance is point one, while the actual event rates are
around three thousandths. Zero OpenCell activity still passes that guard.

**Tehol:** So extraction is not the blocker.

**Bugg:** Statistics is.

---

**Tehol:** You wanted to begin L2.5.

**Bugg:** I wanted a fast first pair.

**Tehol:** And I said?

**Bugg:** The gates exist to move from low complexity to high. We do not start
L2.5 while L2.1 and L2.2 remain open.

**Tehol:** Good. What does closing them require?

**Bugg:** Ten tracks.

**Tehol:** That sounds like the beginning of another management system.

**Bugg:** Two L2.1 tracks and eight L2.2 tracks. One process owner per track.
One coordinator for the shared files. No agents whose job is to watch other
agents work.

**Tehol:** Name them.

**Bugg:** Chromosome condensation. Active-window recertification. Replication.
Macromolecular complexation. Protein processing II. DNA supercoiling.
Ribosome evidence integration. Cytokinesis. FtsZ. DNA damage.

**Tehol:** And all ten start now?

**Bugg:** They wait here. The bookkeeping is committed first. The checkpoint,
the blog, the tracker, the exact blocker for each lane. Then you give the
go-ahead.

**Tehol:** Why the ceremony.

**Bugg:** Because five days from now someone will ask what ten agents were doing,
and "something about MATLAB" is not an acceptable answer.

---

## Honest scoreboard

| Gate | Current status |
|---|---|
| **L2.1** | **16 GENUINE / 5 COINCIDENTAL / 6 UNINFORMATIVE / 1 FAIL** |
| **L2.2** | **14 PASS / 4 FAIL / 4 MISSING_EVIDENCE**, audit integrity OK |
| **L2.event** | RibosomeAssembly N=50 PASS; Cytokinesis 1/50 structural canary; FtsZ 0 usable division windows; DNADamage no nontrivial stimulus trace |
| **L2.4** | PASS, 100 ticks x 4 seeds, implemented v1 scope |
| **L2.5** | not started; explicitly blocked until L2.1 and L2.2 close |
| **L3** | not started |

---

**Tehol:** Can you track ten lanes?

**Bugg:** Yes. The database gets ten rows. Every detached worker gets one
worktree, one PID, one status file and one acceptance contract. The plan and
the evidence indexes remain single-writer.

**Tehol:** Do you need three more agents to manage the agents?

**Bugg:** No, sir. That is how a project becomes a simulation of project
management instead of a simulation of a cell.

**Tehol:** *[pulls the blanket higher]* Commit it.

**Bugg:** Waiting for your go-ahead after the push, sir.

---

*This is the OpenCell dev blog. The repo is
[github.com/srinivasdrona/opencell](https://github.com/srinivasdrona/opencell).
The next entry begins only after the ten-track checkpoint is accepted.*

