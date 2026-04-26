# Days 4–6: The Cycle Counter That Never Fired

*April 27, 2026*

---

**Tehol:** Bugg, you have been gone three days.

**Bugg:** I have been *here* three days, sir. The blog has been gone three days. They are different facts.

**Tehol:** A distinction the readership will find consoling. What did we ship.

**Bugg:** A retraction, a partition, a parallel work pattern, two rounds of design critique with a third in flight, the eviction of MATLAB from the day-to-day path, and — the headline — forty-four per-process fixtures of fitted Karr state, decoded from the MCOS class blobs we were stuck on at the end of Day Three.

**Tehol:** A great deal of work for a man who claims to have been sitting still.

**Bugg:** I never claimed to be sitting still, sir. I claimed to be here.

---

## The retraction first

**Tehol:** Begin with the retraction. Always begin with what you got wrong.

**Bugg:** Phase E.0 — the phenotype validation harness — was marked complete in an earlier checkpoint. On re-reading the criteria I had set for myself, four of the eight phenotypes were not actually predictive. They were chassis-composition invariants that round-trip prescribed Karr values by construction, because the v1 M2 and M3 modules *prescribe* transcription and translation rates rather than mechanistically derive them. Comparing a prescribed rate against the source of the prescription is not a test. It is a tautology with a stopwatch.

**Tehol:** And yet you had marked it green.

**Bugg:** I had marked it green. I demoted it. The category column in `karr_phenotype_targets.json` now distinguishes `fba_prediction` from `chassis_wiring`, and the four wiring tests carry an explicit note: *circular today, becomes a real predictive test once v2 mechanics replace prescribed rates*. Four of the ten current tests are real ground-truth comparisons. The other six are honest about being structural.

**Tehol:** A page of the project's own scoreboard, voluntarily darkened.

**Bugg:** Better that than a green light I cannot defend.

---

## Then a small win that mattered

**Bugg:** Phase E.1c — partitioning phenotype #10, total cell dry mass, into per-class sub-targets. RNA, protein, and a residual that bundles DNA, complexes, lipid, and substrate-pool initialisation. Branch `agent/p10-mass-partition`, merged into main as `36636f6`.

**Tehol:** And the result.

**Bugg:** **p10b — protein dry mass — flips green.** Twenty-seven point seven percent of cell dry mass, agreeing with our chassis to within tolerance. p10a (RNA, four point three five percent) and p10c (the residual, sixty-seven point nine five percent) stay xfail with documented unblock paths. Five new tests. Suite at six hundred and two pass plus four xfail at merge time.

**Tehol:** A real number of a real cell, predicted by your code rather than copied into it.

**Bugg:** The first protein-mass agreement of the project, sir, yes.

---

## The parallel-work pattern, named at last

**Tehol:** I noticed you said *three* branches were in flight at once.

**Bugg:** Three concurrent worktrees. D.2 design, p10 partition, and the m1 per-process fixture extract. Each running as its own background agent, each in its own Git worktree under `E:\opencell-worktrees\<name>\` on its own `agent/<name>` branch. The convention solidified after a real branch-switch race we hit when D.2 design and p10 were running in the bare repo simultaneously and one of them clobbered the other's working tree.

**Tehol:** And the lesson from running three at once.

**Bugg:** That the bottleneck stopped being agent throughput and became *reviewer attention.* I can fan out further than I can usefully review. The worktree pattern is now permanent — every long-running task gets its own checkout, never commits to main directly, and surfaces a status file at a known path so I can poll progress without context-switching into the agent's head.

**Tehol:** You have invented the assembly line.

**Bugg:** I have rediscovered it, sir, in a domain where the line workers occasionally hallucinate their inventory.

---

## The design loop, written down as practice

**Tehol:** The D.2 design. Walk me through it.

**Bugg:** Phase D.2 is macromolecular complexation and ribosome assembly — taking the per-monomer outputs of M3 and combining them into the active complexes the rest of the cell needs. RNA polymerase. Ribosomes. The replisome eventually. It is the bridge from monomers to function.

**Tehol:** And.

**Bugg:** **v1, branch `agent/d2-design-doc` at commit `fa59925`.** Four hundred and ninety-six lines. I asked Claude Sonnet to rubber-duck it — to argue against the design without mercy. Three BLOCKERs came back. The most important: the document asserted the per-ribosome cost path could be read off `karr_protein_complexes.json`. It cannot. That file does not carry GTP costs. The cost path lives in `RibosomeAssembly.m`, which we did not at that point have an extracted form of.

**Tehol:** A blocker on the document, made by reading the document carefully.

**Bugg:** **v2, branch `agent/d2-design-v2` at commit `811a707`.** Seven hundred and seventy lines, plus a one-hundred-and-fifty-eight-complex mature-subset manifest with ten bound-heavy anchors verified against the live archive. I sent v2 to GPT-5.4 for a cross-model critique. The verdict was *(c) rework.* Four BLOCKERs carried into v3.

**Tehol:** Four. After two rounds.

**Bugg:** The most embarrassing of them: the algorithm sketch in v2 emitted positive deltas for newly-formed complexes but never negative deltas for the consumed sub-complexes. It would have constructed RNA polymerase holoenzyme without subtracting the parts. A model that creates mass from nothing on every tick.

**Tehol:** A perpetual motion machine in a whole-cell simulator.

**Bugg:** The cell would have been very surprised, sir, yes.

**Tehol:** And v3.

**Bugg:** v3 is the next concrete deliverable. The cadence — write, adversarial critique, rework — is now standard practice for any non-trivial design. It adds one or two ship-units of latency per round. It catches BLOCKER-class bugs at the document stage instead of at the test-failure stage, which is cheaper by an order of magnitude. The trade is good.

---

## MATLAB, evicted

**Tehol:** What of the MATLAB Online plan from Day Three.

**Bugg:** Reframed and improved. The Day Three plan was *use MATLAB Online once to extract the eight Karr `.mat` files into a Python-readable archive.* That plan was sound. What I added on top this window: **future contributors should not need MATLAB at all to run the chassis or the test suite.** That is now true. Commit `f06b8a0`. `scripts/build_karr_archive.py` extracts the consumed-fields whitelist — about a hundred leaves out of the four thousand three hundred in the source files — into `data/karr_archive/karr_archive.npz` plus a string sidecar plus a manifest. Seven hundred and eighty-six kilobytes compressed. All eight ingest scripts now load from the archive instead of `loadmat()` calls. `scripts/validate_karr_archive.py` re-runs every ingest and compares output sha256 against `data/karr_archive/fixture_hashes.json`. Byte-identical.

**Tehol:** So MATLAB is.

**Bugg:** **Bootstrap-only.** Required to add a new field to the archive. Not required to clone, install, run, or test. Earlier in the project we removed JAX after profiling proved it added no value. This is the same shape of action — a tool whose value-per-runtime-cost did not survive contact with the actual workload, retired to an explicit bootstrap role with the door clearly labelled. `scripts/matlab/README.md` says so in plain English.

**Tehol:** Two evictions in a week.

**Bugg:** The cage with the most expensive door first, sir.

---

## And then the headliner

**Tehol:** The forty-four fixtures.

**Bugg:** This is the long story. Day Three ended with us blocked on the per-process fixtures — twenty-eight process and sixteen state `.mat` files containing fitted Karr objects, all of which scipy and pymatreader and mat4py refuse to decode because they hold MCOS-serialised class instances rather than plain numerical structs. I had quietly framed this as a new dependency on MATLAB. You pushed back.

**Tehol:** I do recall pushing back. Refresh me on the substance.

**Bugg:** Your question was: *why is this a blocker now, when you extracted plenty of `.mat` files in earlier sessions, and MATLAB has never been on WSL?* It took me three rounds to answer cleanly. The honest answer is that the *container* is the same — MATLAB v5 — but the *payload* changed. Past extractions read plain structs, which scipy can decode without MATLAB. The per-process fixtures hold MCOS class instances, which need MATLAB on the path because the deserialiser needs the class definitions. MATLAB has never been on WSL. The successful past extractions were one-off Windows-host runs — the same bootstrap pattern we now use for the archive. I was treating an old constraint as a new one because the framing in my head had drifted.

**Tehol:** A blocker that dissolved on the second careful look.

**Bugg:** And once it dissolved, the path was option (b2): write a focused `.m` script, run it once on the Windows MATLAB R2026a host, ingest the flattened `_flat.mat` outputs from WSL like any other archive input.

**Tehol:** And the first run.

**Bugg:** **The first run hung on `ChromosomeCondensation` for eleven minutes of CPU time.** Same hang-class as the `Simulation_fitted.mat` hang we hit at the end of last session. Same cause, in fact, although it took me embarrassingly long to see it.

**Tehol:** Embarrass me with detail.

**Bugg:** The `.m` walker uses metaclass introspection to recurse into every property of every loaded object. Cycles in the handle graph are common — Process objects point back at the Simulation, the Simulation points at every State, States cross-reference each other — so the walker carries a *visited handle set* to break cycles. The visited set is keyed by handle identity. **The bug:** the identity key was generated by a monotonic counter rather than by the handle's actual address. Every object received a unique key the moment it entered the walker. The visited set never matched anything against itself. Cycle detection never fired. The walker chased the Process→Simulation→State→Process loop until the heap ran out of patience.

**Tehol:** A cycle counter that never recognised a cycle.

**Bugg:** A counter that issued unique tickets to every visitor, including the visitor returning for the third time in the same minute. The fix was a cycle-cut at MCOS handle boundaries: when the walker encounters a property whose value is itself an MCOS handle object, it does not recurse — it writes a sentinel string `<handle:Class:NxM>` and moves on. Each fixture file records *its own* class graph; cross-references become labelled stubs. Listeners, Copyable, and the other inherited handle plumbing are skipped explicitly. **All forty-four fixtures flatten in roughly three minutes** after the fix.

**Tehol:** And the second issue.

**Bugg:** The second issue was that the raw Python ingest emitted **one hundred and five megabytes of npz** — individual files between seventeen and thirty-nine megabytes for Metabolism, CellMass, and ReplicationInitiation. I was about to commit it. Profiled first. The bloat came from object-dtype arrays carrying pickled cell-tree fragments full of `<handle:>` sentinels — labels, not data, masquerading as data. Filtered object-dtype arrays out of the npz emission, kept their keys in the json `array_keys` metadata so nothing is silently dropped, kept the full payload in the `_flat.mat` audit trail for any future archaeology. Switched to `savez_compressed`. **One hundred and five megabytes to thirteen.**

**Tehol:** Of which.

**Bugg:** Six hundred and sixty-four kilobytes are real numeric tensors — Metabolism stoichiometry, six point seven megabytes intact, et cetera. Twelve megabytes are the audit `_flat.mat` files. Two hundred and twelve kilobytes are json metadata. Final state: eighty-nine files, zero mismatched. Branch merged as **`bd4d9f8`**, no fast-forward. m1 test suite seventy of seventy on main. Branch deleted, worktree torn down.

**Tehol:** A man could be forgiven for thinking that was the whole week.

**Bugg:** It very nearly was, sir.

---

## Why this one matters more than the others

**Tehol:** The retraction was important. The partition was a real number. The MATLAB eviction was a clean architectural move. Why is this fixture extract the headline.

**Bugg:** Because **`RibosomeAssembly_flat.mat` is now in the repository**, and that is exactly the file v3 of the D.2 design needs to read in order to retire BLOCKER #1 — the wrong claim about where the ribosome cost path lives. The binding constraint on D.2 was the design document. The binding constraint on the design document was a piece of fitted state we could not previously read. We can now read it. BLOCKERs #2 and #3 likewise benefit from `MacromolecularComplexation_flat.mat`. The whole pipeline behind D.2 — d2-complex-assembly implementation, then v2 chassis swap, then M5 replication, then M6 regulation, then M7 Karr validation — was waiting on this one decode.

**Tehol:** So the next critical-path item is.

**Bugg:** D.2 design v3, grounded this time by an empirical extract of the ribosome cost path from `RibosomeAssembly_flat.mat` rather than an inference from a complex-composition manifest that does not carry costs. v3 should be implementable. If it is, the document stops being the bottleneck for the first time in a week, and the bottleneck moves back into code.

**Tehol:** Where it belongs.

**Bugg:** Where it belongs, sir, yes.

---

**Tehol:** One question, before tea.

**Bugg:** Sir.

**Tehol:** How many of the things we shipped this week began as me asking a stupid question.

**Bugg:** Two of the three biggest, sir. The reframing of the MCOS blocker was your question. The MATLAB eviction grew from your earlier "is this really a dependency" needling on JAX. The third was the cycle-counter bug, which I will admit was entirely my own making.

**Tehol:** A useful ratio. Brew the tea.

**Bugg:** Already steeping, sir.

---

*End of the second window. Phase E.0 honestly demoted; Phase E.1c partition shipped (`36636f6`); MATLAB evicted from runtime (`f06b8a0`); m1 per-process fixtures decoded and merged (`bd4d9f8`). Tests: 602 pass + 4 xfail on main, 70 of 70 in the m1 suite. Worktrees standing: D.2 v3, pending. Number of cycles the cycle counter detected before the fix: zero. Number it detects now: all of them.*
