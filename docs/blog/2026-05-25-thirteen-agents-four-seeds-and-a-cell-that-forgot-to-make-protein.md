# Day 10: Thirteen Agents, Four Seeds, and a Cell That Forgot to Make Protein

*May 25, 2026*

---

**Tehol:** Bugg, you have been gone for two days. I assumed you had finally found a tailor who could measure you for trousers without weeping.

**Bugg:** No, sir. I have been managing a small army.

**Tehol:** An *army*. Of what.

**Bugg:** Thirteen autonomous coding agents, in parallel, each on its own branch of the repository, each implementing a different piece of the cell. Yesterday morning I gave each of them a written brief, launched them simultaneously, and went away to draft the next set of briefs while the first set wrote code.

**Tehol:** Simultaneously.

**Bugg:** Eleven at first, then thirteen. Phase C — the DNA and cell-cycle pieces — went out as nine briefs. Phase D — the host-interaction module that completes the twenty-eight processes — went out as one. Phase E — the validation harness against Karr's reference data — went out as one. Then I added two further briefs for the chassis integrations themselves, v5 and v6, which are the wiring that holds the whole cell together.

**Tehol:** And how does one man manage thirteen of anything.

**Bugg:** Badly, at first. The Python launcher failed because the executable on Windows is a batch shim and the argument-quoting collapsed. The PowerShell launcher failed because the new shells did not inherit the API key. Once I had piped the prompts through standard input and string-interpolated the credentials by hand, all thirteen ran cleanly. An hour and a half later they had each shipped a design document, an implementation, a passing test suite, and a clean commit. I merged all thirteen onto the main branch with one merge conflict — two agents had each written to the same progress file at the same instant.

**Tehol:** A small disagreement among workers.

**Bugg:** Resolved by deleting the file, which neither of them needed. The integrated main passed eight hundred and sixty-four tests, no regressions, fifty-seven more than the baseline. I pushed it to the central server and went to dinner.

**Tehol:** And this is — what, the cell.

**Bugg:** This is the cell having, at last, all twenty-eight of Karr's biological processes present as modules. Transcription, translation, replication, the cell-cycle coordinator, the host-interaction layer, every metabolic compartment. The architecture was finally *complete in form*.

**Tehol:** *In form.*

**Bugg:** That word is doing considerable work, sir. The form was complete. The function was not.

**Tehol:** How long until you discovered this.

**Bugg:** Eleven hours. The next morning I launched the first proper biological run — four parallel ensemble simulations, one for each of four different random seeds, each thirty-two thousand four hundred ticks long, which is the duration of one full *M. genitalium* cell cycle. The point of running four seeds in parallel was to demonstrate that the model gives consistent but seed-varying biology, which is the minimum bar for a stochastic whole-cell simulation.

**Tehol:** You found something unexpected, otherwise you would not be telling me with that particular face.

**Bugg:** I found that the four runs were not seed-varying. They were identical. Ten decimal places identical, across all four seeds. The metabolism module was emitting precisely the same flux at every tick, regardless of seed. Which is a fascinating result for a model that is supposed to contain stochastic elements.

**Tehol:** And.

**Bugg:** And the transcription log had zero rows. Across thirty-two thousand four hundred ticks of simulated time, transcription had fired zero times. So had translation. The cell had been making no protein and no RNA for an entire simulated cell cycle.

**Tehol:** While the metabolism happily ran in circles.

**Bugg:** While the metabolism happily ran in circles. The substrate pool, which had been initialised to a value of *one* — one molecule of ATP, one of GTP, one of every amino acid — was being drained one thousand units per tick by a process whose output went to nowhere observable, leaving the cell with thirty million units of negative ATP by the end of the run.

**Tehol:** Bugg, that is not a cell. That is a hole in the floor.

**Bugg:** Yes, sir.

**Tehol:** And you had run eight hundred and sixty-four tests against this hole in the floor before launching it.

**Bugg:** All eight hundred and sixty-four passed. Every test asserted on the *shape* of what the processes emitted — whether the output dictionary had the right keys, whether the values were finite, whether the type was correct. None of them asserted that anything *flowed*. The chassis was completely wired and completely silent, and the test suite reported it as healthy.

**Tehol:** You are telling me you built the entire municipal water system, with valves and meters and ledgers and inspectors, and the inspectors all returned satisfied because every valve was the correct shape, and only when the citizens died of thirst did anyone notice that no water had moved through any of it.

**Bugg:** That is approximately what I am telling you. Yes.

**Tehol:** Bugg, this is a parable.

**Bugg:** It became a policy. By breakfast yesterday I had reached three conclusions and one rule. The conclusions: there were *three separate bugs* causing the silent failure, not one. The rule: for any future placeholder or "decorative" implementation, the test that ships with it must run the engine for some number of ticks and assert that the relevant pool changes by a specific signed amount. Schema tests are not biology tests. "The engine runs without crashing" is not "the deltas are flowing through the wires."

**Tehol:** Three bugs.

**Bugg:** Three bugs. The first was that the transcription and translation modules had been quietly marked as *steps* rather than *processes* by a clever piece of code I had written precisely seven hours before I broke things with it. A *step* runs at timestep zero, which is to say, never. The diagnostic note that said "marking a process as a step zeros its timestep" was sitting in a file in the repository, written by me. I had reviewed it. I had then written the line of code that did exactly the thing the note warned against, in the very next commit.

**Tehol:** *The very next commit.*

**Bugg:** Approximately ninety minutes of self-regression.

**Tehol:** Continue.

**Bugg:** The second bug was the substrate-initialisation default. The shared metabolite store was initialised at *one* molecule per species rather than at Karr's published initial counts, which run into the millions for the major NTPs. And because the store's update rule was "accumulate" — that is, all writes are summed each tick — there was no mechanism for the initial counts to ever be set to their correct values. The store just accumulated whatever the processes wrote to it, starting from one. So when transcription was eventually fixed and began draining a thousand ATP per tick from a store containing one molecule, the result was immediate insolvency.

**Tehol:** And the third.

**Bugg:** The metabolism module had a boolean flag called `dynamic_bounds`, defaulting to *false*. Which meant the flux-balance solver was solving the same constraints every tick, regardless of the substrate pool's actual state. The solver was a beautifully written piece of mathematics that had been computing the same answer every tick for two days because the question never changed.

**Tehol:** All three of these existed in code you had personally reviewed.

**Bugg:** All three. And here is the part that still bothers me. The cascade-conservation test that I ran two days ago — the one that announced the chassis was finally healthy and ready to validate — passed with a numerical conservation drift of three parts in ten billion. The test was correct. The math closed. The cell was conserving mass to ten decimal places because *no biology was happening*. A closed system with nothing in it conserves nothing perfectly.

**Tehol:** The test was passing for the wrong reason.

**Bugg:** The test was passing because the cell was dead and dead cells balance their books exquisitely.

**Tehol:** Bugg, this is your second parable in one conversation. You have been at this too long.

**Bugg:** I will not argue, sir. I will only say that by the end of today I had landed eleven commits to fix it. Four for bug five — the protein pipeline that translation feeds into and that processing-one, processing-two, and the maturation step drain — which had been a sequence of disconnected buckets pretending to be a pipeline. Three for bug six — the metabolism's writeback, which was producing flux solutions for three hundred and sixty-eight cytosol reactions but only writing twenty-four of them back to the shared pool. Two merge commits and a fixup on a canary that the very next commit on the same branch widened beneath. Three hundred and thirty-eight tests now pass on the main branch.

**Tehol:** And one fails.

**Bugg:** And one fails. The substrate-non-negativity test. Because transcription and translation, even now that they fire, still write their drains directly to the shared pool without going through the allocator. They were never enrolled. Which means they still take whatever they want regardless of what is available, and the negative-ATP problem from yesterday is still present in milder form. The diagnostic I built into today's fix proves it: the metabolism's contribution to the NTP balance is essentially zero per tick. The drain comes from two processes that have never been forced to ask permission.

**Tehol:** So tomorrow.

**Bugg:** Tomorrow is what I am calling Track A. Enrol transcription and translation in the allocator. Scale their activity by the ratio of what they get to what they ask for. The same pattern bug eight, which is translation's energy accounting, will need. And bug nine, which is protein decay, will need too. Three bugs in a row that all follow the same shape, which means the next sprint is doing the same fix three times in slightly different places.

**Tehol:** And then.

**Bugg:** And then the cell, for the first time, will be biology rather than bookkeeping. And then we run the twenty-eight-phenotype scorecard against Karr's published values. Which has been sitting in a fixtures directory for three weeks waiting for there to be biology to compare against.

**Tehol:** Bugg, I have a question.

**Bugg:** Sir.

**Tehol:** You launched thirteen agents in parallel yesterday, all of them implementing different parts of the same body, none of them aware of the others, and you ended the day with a chassis that was wired in form but silent in function. Should this surprise me?

**Bugg:** It surprised me, sir. But on reflection it was not the parallelism that did it. The parallelism produced thirteen correctly-shaped pieces. What did it was that I had no test in the suite that asked whether the pieces, when assembled, *did anything*. The agents could not be expected to write that test, because each of them only saw its own piece. The test had to come from me, and I had not written it. I have now written it. It runs at every commit. It will fail loudly if the cell ever again becomes a beautiful corpse.

**Tehol:** A *what*.

**Bugg:** That is what I have been calling it in my own head, sir. Forgive me.

**Tehol:** No, no. *Keep* it. That is the most useful name you have given a failure mode this entire project. A beautiful corpse. Conservation perfect, mass balanced, every test green, and nothing alive inside. Bugg, write it down somewhere durable.

**Bugg:** It is already in the decisions log.

**Tehol:** Of course it is.

**Bugg:** Sir, may I go to sleep.

**Tehol:** One last thing.

**Bugg:** Sir.

**Tehol:** The thirteen agents. They each cost something to run.

**Bugg:** Yes, sir.

**Tehol:** And the four seeds. They each cost something to run.

**Bugg:** Yes, sir.

**Tehol:** And the four diagnostic agents this morning, and the bug-fixing agents this afternoon, and the watchers that watched the agents.

**Bugg:** Yes, sir.

**Tehol:** I am to assume someone, somewhere, is paying for all of this.

**Bugg:** A small subscription, sir. The orchestration is on one account; the executors on another. The accounts are unaware of each other. It is a great convenience.

**Tehol:** Bugg, this is the most Lether thing you have ever said.

**Bugg:** I have been studying, sir.

---

*Commits on `main` today, 2026-05-25 (HEAD `47b245f`): Bug 5 in four commits (5A `bbfab3c`, 5B `a2da0eb`, 5C `6e4f0d1`, 5D `50ec5fc`) closing the protein maturation pipeline from translation through processing-I, processing-II, and Karr step 7. Bug 6 in three commits (6b `b69e7ca`, 6a Stage 1 `c697075`, 6a Stage 2 `ecde4e4`) closing the FBA-to-substrate writeback for 368 cytosol reactions with signed deltas. One stage-1 canary fixup (`be2d401`) and one merge (`40f96c5`). Regression: 338 passed, 1 failed (B1, known-pending Track A), 2 xfailed in 17m30s. The "beautiful corpse" pattern, the parallel codex fleet of thirteen, the self-regression that introduced bug 1 in the commit immediately after the diagnostic note warning against it, and the cascade-conservation test that passed for the wrong reason are all logged in `decisions/`. Track A — enrolling transcription (M2v3) and translation (M3v3) in the substrate allocator — is the entire next sprint.*
