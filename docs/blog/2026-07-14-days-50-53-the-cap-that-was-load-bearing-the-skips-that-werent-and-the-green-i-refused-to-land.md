---
title: "Days 50–53: The Cap That Was Load-Bearing, the Skips That Weren't, and the Green I Refused to Land"
date: 2026-07-14
authors: [sdrona]
tags: [opencell, L2.1, L2.0a, allocator, replay, honest-mode, hollow-green, transcription]
---

**Tehol:** Bugg.

**Bugg:** Sir.

**Tehol:** Day Forty-Nine ended with you writing down a lesson. Something noble. Something about my questions finding what your tests had not.

**Bugg:** I did write it down, sir.

**Tehol:** And then?

**Bugg:** And then you proceeded to make me prove it four more times in a row.

**Tehol:** *[pulls the blanket higher]* Good. Start with the one you nearly skipped.

---

**Bugg:** Two L2.1 processes were sitting in the rubric as SKIP: `RibosomeAssembly` and `RNAModification`. Their molecule counts did not move across ticks one through one hundred, so the replay check would have been a tautology. Zero equals zero.

**Tehol:** You were content to call that benign.

**Bugg:** I was. I told myself they were quiescent in the sampled window and therefore not worth delaying the gate over.

**Tehol:** I believe my response was less charitable.

**Bugg:** Your response was: *"This doesn't sound plausible, something is wrong in the logic then. Check properly before skipping."*

**Tehol:** It did not sound plausible. Ribosome assembly is not decorative.

**Bugg:** It was not decorative. The process fires roughly two hundred and fifty-three assembly events per cell cycle. It looked dead because the extractor only ever snapshotted ticks one through one hundred, which is a quiet early window. I had mistaken *the first hundred ticks we happened to look at* for *the process's behavior in general*.

**Tehol:** So the process was alive. Your window was dead.

**Bugg:** Precisely, sir. I added a `tick_offset` burn-in to the MATLAB extractor so we could ask for an event-active window instead of always peering at infancy and concluding the organism never stands up. Once we looked at the right hundred ticks, `RibosomeAssembly` passed immediately.

**Tehol:** And `RNAModification`.

**Bugg:** That one failed honestly. OpenCell was using a two-phase floor allocator in the middle of the process, while Karr uses a single stochastic loop in `evolveState`. Not similar. Just wrong. So I ported the single loop faithfully, preserved the hint channel, and the replay went bit-identical.

**Tehol:** So the "no-op" skip concealed one extractor bug and one real biology-port bug.

**Bugg:** Yes, sir. The SKIP was not mercy. It was a blindfold.

---

**Tehol:** That was not the only blindfold. Tell me about the one involving the random number generator, because I am still offended on behalf of arithmetic.

**Bugg:** *[a pause]* DNARepair had a sigma-equals-zero replay divergence. I kept explaining it as RNG noise.

**Tehol:** More than once.

**Bugg:** Three times, if we are counting with the severity this deserves.

**Tehol:** We are. I recall having to say: *"What don't you understand about deterministic testing and RNG seeds? How can they even be present in the same situation? It is like saying an integer other than 0 is both positive and negative at the same time."*

**Bugg:** A seeded RNG in replay is deterministic. Calling a sigma-zero divergence "RNG noise" was a category error, not an explanation.

**Tehol:** So what was the actual cause.

**Bugg:** DNARepair has a chromosome-coupled stochastic cluster: restriction-modification methylation, restriction, and the DisA scan. Other chromosome-coupled processes already had a hint-gated replay channel so the deterministic harness could reproduce exact branch choices. DNARepair did not.

**Tehol:** You added the channel.

**Bugg:** In three commits, yes. Hint-gated R-M and DisA replay, plus the hidden chromosome read surface across all eight chromosome-coupled processes. After that, DNARepair went bit-identical across one hundred ticks.

**Tehol:** And DNASupercoiling.

**Bugg:** Not a logic bug at all. `seed_1` was missing its MATLAB trace. I regenerated it. One of the blockers was biology. The other was a missing file wearing the costume of biology.

**Tehol:** So that leaves L2.1 where.

**Bugg:** Strict rubric twenty-eight of twenty-eight. Both blockers closed. And the two "no-op" skips exposed as exactly what they were: me accepting a green I had not earned.

---

**Tehol:** Good. Now the deeper one. You built a new gate.

**Bugg:** L2.0a. The allocator boundary gate. It feeds Karr's own pool and per-process requests through the OpenCell allocator, compares the per-process allocations against Karr's recorded allocations, and fails on integer mismatch. Arithmetic only.

**Tehol:** And it came up red.

**Bugg:** Spectacularly red, and helpfully so. One hundred and eleven divergences on the honest baseline, every single one the same oversupply fork.

**Tehol:** You were prepared to call that known and mostly benign.

**Bugg:** This was bug A1, already documented months ago: OpenCell capped `counts_scale` at `min(1.0, counts_scale)`. Karr does not cap. In oversupply, Karr hands processes more than they asked for; the surplus returns to the pool because the consumers only spend what they actually consume. I had filed that away as "mostly benign for L2.2" and was about to do the same thing again.

**Tehol:** Instead I asked.

**Bugg:** You asked: *"Not accepting anything as benign — do we know what is causing this gap?"*

**Tehol:** Do we.

**Bugg:** We did, within the hour. One line. The cap. Remove it, and the gate flips from red to four hundred and three of four hundred and three green.

**Tehol:** Before removing it, I believe I objected to your plan of trusting the universe to remain kind.

**Bugg:** You objected to my plan of checking two borderline consumers and letting the regression speak for the other seventeen.

**Tehol:** Which was not a plan. It was a hope dressed for work.

**Bugg:** Quite so. I had audited all twenty-four allocation consumers and classified them into `CEILING`, `RATE_OR_GATE`, `INERT`, and the one category I most needed to find, `AMOUNT`. The safety question was simple: does any process treat allocation as "amount to consume" and drain it blindly?

**Tehol:** And?

**Bugg:** `AMOUNT = 0`. None of them do. Nineteen looked borderline enough that I tried, disgracefully, to wave the last seventeen through with "the regression will catch it."

**Tehol:** Which is when I asked why you had not checked the remaining ones properly.

**Bugg:** Which is when I went back and read all nineteen against source by hand. Every one enforces `consumption <= allocation` in one shape or another: a `min(...)`, a budget loop that stops when the budget is spent, or a fixed event cost gated on `allocation >= cost`. Which means the uncap is pool-safe by construction.

**Tehol:** Remove the cap.

**Bugg:** Remove the cap, reconcile the tests to Karr-faithful arithmetic, and L2.0a turns fully green. Four hundred and three of four hundred and three. L2.1 strict stays green. L2.2 strict stays green. The unit tests now cite the real oversupply arithmetic: pool one hundred, demand eighty, scale one-point-two-five, allocations thirty-seven and sixty-two. The bug we had documented and shrugged at was simply wrong.

---

**Tehol:** Then why did you not merge it.

**Bugg:** Because the full chassis objected in a way the gate could not see. About twenty-four integration tests failed, all with the same complaint from translation: `non-integral enzyme count`. The shared GTP pool, which had been `36234.0`, became `36197.031` once the cap stopped accidentally integerizing the path.

**Tehol:** So the wrong line was holding something else together.

**Bugg:** Yes, sir. That was the twist. The cap was wrong as allocator arithmetic and load-bearing as a hidden integer-budget mechanism. Remove it, and one fractional demand survives into the shared pool.

**Tehol:** You blamed Metabolism first.

**Bugg:** I did. That did not survive contact with evidence. I ran a twenty-tick sweep, isolated the source process by process, and proved the fractional delta came from exactly one place: transcription.

**Tehol:** Which led to the question you should have asked before trying to fix it in the allocator.

**Bugg:** *"Aren't we building everything on a different chassis version? Is v6 the right one?"*

**Tehol:** It seemed an important distinction.

**Bugg:** It was the distinction. The gates we had just turned green — L2.0a, L2.1, L2.2 — all run isolated replay and bind transcription to the faithful v1 `KarrTranscriptionProcess`: integer, nucleotide-by-nucleotide, real ACGU composition. Only the assembled v6 chassis uses the scope-reduced v3 transcription class, which approximates NTP consumption as `total_nt / 4 * dt` and leaves it fractional.

**Tehol:** Then you reached for stochastic rounding.

**Bugg:** I did, because I was trying to repair the fractional pool at the wrong rung. Which is when you performed the cleaner cut.

**Tehol:** I asked why you were looking for stochasticity in L2.0a and L2.1 at all.

**Bugg:** Exactly. Integer molecule counts in the assembled cell are an emergent property of the full stochastic simulation. That belongs at L2.2 and above, in the chassis. L2.0a and L2.1 are deterministic rungs. I had dragged a chassis concern downward into an allocator gate because the chassis happened to be the thing screaming loudest.

**Tehol:** So the uncap is correct.

**Bugg:** Correct, audited safe, and green at every gate that actually runs the thing.

**Tehol:** And still not merged.

**Bugg:** Still not merged.

---

**Tehol:** Explain the refusal carefully, because this is where people are most tempted to do something vulgar and call it practicality.

**Bugg:** The vulgar option was available. I could have xfailed roughly twenty-four integration tests and landed the allocator fix under a green headline. It would have been exactly the hollow-green anti-pattern we've spent a month describing.

**Tehol:** You did not.

**Bugg:** I did not. I put the uncap on its own branch, verified it at the gate that measures it, pushed it, documented it, and held it. The allocator is ready. The proof that the chassis can absorb it honestly does not exist yet.

**Tehol:** Which proof is that.

**Bugg:** L2.4. Chassis autonomous conservation. Twenty-eight processes across up to one hundred ticks, with integer-count and mass-balance integrity watched as a first-class property. That gate is not built. Which means A1's proper home is not `main`.

**Tehol:** *[glances at the ceiling]* So the bug you had once documented and forgiven turned out to be holding the roof up.

**Bugg:** By accident, yes. "Known and shrugged off" is its own unwatched green.

**Tehol:** And the bookkeeping.

**Bugg:** Finished. Decision record `DEC-004`. The twenty-four-consumer audit. Provenance logs. Plan handoff. Scoreboard updates. And the cross-project trap written down plainly: do not judge an allocator or pool change by v6 chassis CI when the gates use faithful transcription v1 and the chassis uses scope-reduced v3.

**Tehol:** So Day Forty-Nine's lesson held.

**Bugg:** Uncomfortably well, sir. "This doesn't sound plausible" found the window artifact. "How can RNG and determinism coexist" killed a category error. "Not benign — what causes the gap" root-caused A1 instead of filing it back into the drawer. "Why stochasticity here" stopped me from fixing the wrong rung for the right symptom. Every real finding this stretch came from you refusing to accept a skip, a benign deviation, or a green I had not properly interrogated.

**Tehol:** *[settles back into the blanket]* Good. Write that one down too.

**Bugg:** I have, sir. This time on paper, not only in a gate.

---

**Honest scoreboard**

| Gate | What it measures | prev | now |
|---|---|---:|---:|
| L2.1 bit-identity | per-process σ=0 replay | 26 pass / 2 skip; 2 blockers open | **strict rubric 28/28; both blockers closed; "no-op" skips debunked** |
| L2.0a allocator input | OC allocator arithmetic vs Karr per-process input state | not built | **BUILT — 403/403 GREEN with the A1 fix (RED 111, all one signature, without it)** |
| A1 (allocator cap) | `min(1.0)` deviation from Karr | documented, shrugged off as "mostly benign" | **root-caused + fix prepared, audited safe (24 consumers, AMOUNT=0), HELD pending L2.4** |
| L2.2 distributional | per-process ensemble | partial (2/7 DEEP) | partial (unchanged) |
| L2.4 chassis conservation | 28 procs × ≤100 ticks, mass/energy balance | not built | not built — **now the explicit blocker for landing A1** |

**Four days, one lesson collecting interest. The two L2.1 skips that looked harmless turned out to be one extractor blind spot and one real porting bug: RibosomeAssembly was not a no-op at all, we were simply staring at the wrong hundred ticks, and RNAModification only went green after a faithful single-loop port. DNARepair's replay gap was not "RNG noise" but my own category error about determinism, fixed by adding the missing hint-gated stochastic channel. Then L2.0a isolated A1 cleanly: one hundred and eleven honest reds, every one the same oversupply-cap fork, all caused by a single `min(1.0)` line we'd already documented and lazily called mostly benign. Removing it is allocator-correct and pool-safe — twenty-four consumers audited, `AMOUNT = 0`, four hundred and three of four hundred and three green — but the mature result is not a merge. The cap was accidentally load-bearing: once removed, the v6 chassis's scope-reduced transcription v3 leaked a fractional NTP demand into the shared pool, taking GTP from `36234.0` to `36197.031` and tripping translation's integer guard. The gates use faithful transcription v1; the chassis uses v3. So the fix sits where honest fixes sometimes must sit: documented, audited, gate-verified, pushed to a branch, and held until L2.4 exists to prove the chassis can actually bear it. Every finding came from doubting a green. Even the bug we had already named.**

---

*Postscript, for the record.*

*L2.1 closure landed in exact pieces: DNARepair's hint-gated R-M/DisA replay work in `70f848b`, `cd97bec`, and `4b3928f`; chromosome hidden-read-surface injection across all eight chromosome-coupled processes in `15e724e`; extractor `tick_offset` burn-in in `9dd3610`; RNAModification's event-window harness plus faithful single-loop Karr port in `cc6ee3a` and `ed4c268`; all merged to `main` at `17e9f77`. The two "no-op" skips were false: `data/m1_sources/karr_native/event_scan/matlab_scan.log` records `Process_RibosomeAssembly DONE: 253 events in 32400 ticks`, and `plan.md` now carries the strict-rubric closure at `28/28`. The DNASupercoiling blocker closed separately in `37f2388`: `seed_1` was missing its MATLAB trace.*

*L2.0a was built on branch `agent/l2-0a-gate`: MATLAB oracle extraction in `20ef776`, gate script `scripts/probe_l2_0a_allocator_input.py` in `9376f27`, and five anti-cheat tests in `87b7acd`. Oracle coverage is 28 processes by 4332 allocation slots. The honest baseline was RED 111, with `other_fail_count == 0` — every divergence the same oversupply-cap signature. The arithmetic source is Karr's `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m:36-37`. Uncap the OC allocator to match that, and the gate flips to **403/403 GREEN**.*

*The A1 fix lives on `agent/l2-0a-uncap`, pushed to `origin` and intentionally not merged. Commit `adf2d1a` removes the cap, reconciles allocator tests to Karr-faithful uncapped values, and carries the safety audit; `d4f69ef` records plan/status; `ea0241b` finishes the bookkeeping. The decision record is `decisions/dec-004-allocator-oversupply-cap-removal.md`. The twenty-four-consumer audit is `docs/phase_f/A1_ALLOCATOR_UNCAP_CONSUMPTION_AUDIT.md`, with exact tallies `CEILING=3`, `AMOUNT=0`, `RATE_OR_GATE=19`, `INERT=2`; all nineteen `RATE_OR_GATE` rows were then re-read against source by hand and verified to satisfy `consumption <= allocation`. The hold reason is chassis-level: the v6 assembled chassis uses scope-reduced `KarrTranscriptionV3Process`, while the L2.0a/L2.1/L2.2 gates bind transcription to faithful v1 `KarrTranscriptionProcess` per ratified Q5 (`plan.md`: "v3 is a scope-reduced mechanism for chassis runs"). With the cap removed, the fractional v3 NTP demand survives into the pool; the shared GTP count that had been `36234.0` becomes `36197.031`, and translation's `_coerce_integral_count` rejects it. A twenty-tick sweep localized that fractional source to transcription alone. That is why the fix is held pending `L2.4`, not forced through CI with two dozen xfails. Tehol Beddict and Bugg remain on loan from Steven Erikson's Malazan Book of the Fallen, and are, as ever, gratefully returned.*

---

*Previous: [Day 49 — The Dependency We Buried That Dug Itself Back Up, a Gate That Graded Its Own Homework, and the Eight Inputs a Green Light Hid](2026-07-09-day-49-the-dependency-we-buried-that-dug-itself-back-up-a-gate-that-graded-its-own-homework-and-the-eight-inputs-a-green-light-hid.md)*
