# Day 11: Four Floors for a Phantom, and the Ruler That Lied

*May 26, 2026*

---

**Tehol:** Bugg. It has been one day. Yesterday you described thirteen agents, four identical seeds, and a cell that had quietly stopped making protein for an entire cell cycle. I assumed today would bring either remediation or surrender. Which is it.

**Bugg:** Neither, sir. Today brings a particular kind of embarrassment that I did not know was available to me until I encountered it.

**Tehol:** Go on.

**Bugg:** Yesterday's diagnosis was that the metabolism module was draining ATP without any biology firing in return. The leading hypothesis was that the model was failing to enforce a quantity called Non-Growth-Associated Maintenance — NGAM — which represents the ATP a living cell burns just to stay alive, irrespective of whether it is making anything new. The Karr reference value is approximately seventy-eight thousand units per second. We were emitting nothing close to that.

**Tehol:** So you set out to enforce it.

**Bugg:** I set out to enforce it. We launched a parallel investigation across the codebase. It identified four distinct sites where NGAM enforcement could be added: the request calculator that prepares ATP demand for the linear program, the linear program itself via a lower-bound override on the ATPM reaction, a downstream allocator step, and a tRNA-charging path that touches ATP indirectly. Four sites. Four candidate fixes.

**Tehol:** Four floors.

**Bugg:** Four floors, yes. Each floor a slightly different argument about *where* in the simulation tick the cell should be obliged to spend its maintenance ATP. We built a single global flag — `karr_parity_mode` — to gate all four sites uniformly, so we could turn the regime on for biological runs and off for diagnostic runs. We added a test to verify that with the flag on, the ATP delta from tick to tick was no longer literally constant.

**Tehol:** A test that fires when the cell is alive.

**Bugg:** That was the design intent.

**Tehol:** I detect a coming reversal.

**Bugg:** This morning, in a moment of misplaced confidence, I asked the obvious follow-up question. The test asserts that the standard deviation of the per-tick ATP delta is greater than ten-to-the-minus-six over a five-thousand-tick window. Before merging four floors to make the test pass, can we confirm the test would actually be true on a real biological run? Can we run the existing thirty-two-thousand-four-hundred-tick reference trajectory through this measurement and see what it says.

**Tehol:** And it said.

**Bugg:** It said zero.

**Tehol:** *Zero.*

**Bugg:** Not approximately zero. Exactly zero, to the precision of double-floating-point arithmetic. Across every five-thousand-tick window I tested, every two-thousand-tick window, every five-hundred-tick window. The median variance of the ATP delta on short horizons is bit-identical zero. There are twenty-eight runs of identically-valued ATP delta across the trajectory. The longest single run is seventy samples of bit-identical delta, which is seven thousand simulated ticks where the cell metabolised at exactly the same per-tick rate, to the last bit.

**Tehol:** That seems unlikely for a living thing.

**Bugg:** It is not unlikely for *our model* of a living thing, which turns out to be the substance of today's embarrassment. The metabolism in this codebase is a linear program that re-solves each tick. The right-hand side of that linear program — the constraints — changes only when slow drivers like biomass coupling or mass balance cross a stoichiometric threshold. Between thresholds, the LP returns precisely the same solution every tick. The ATP delta is therefore *piecewise-constant*. Per-tick variance only emerges over hour-scale horizons, when enough thresholds have been crossed to perturb the solution.

**Tehol:** So the test you were using to validate the four floors—

**Bugg:** —was measuring a quantity that, on the timescale the test inspected, the simulation architecture is geometrically incapable of producing. The test was not failing because the floors were missing. The test was failing because the test was wrong. And it would have failed identically with all four floors in place, because the floors do not change the per-tick variance of the LP solution. They only change its magnitude.

**Tehol:** So you have removed the floors.

**Bugg:** Three of them. The fourth has acquired test coupling — other tests now depend on its presence — and removing it cleanly would require its own rescue operation. So that one stays, behind the flag, in a kind of recuperative quarantine. The other three floors are gone. Three hundred and seven lines of code that I, personally, spent two days building, then deleted before lunch in two commits with detailed messages explaining to my future self that the entire enterprise had been chasing a measurement artefact.

**Tehol:** Did the lesson survive the exercise.

**Bugg:** The lesson survived in a sentence I wrote down so I would not lose it: *never measure raw per-tick variance on a constraint-satisfaction substrate.* If the underlying engine is a linear program, a quadratic program, or any solver that returns a deterministic answer given identical inputs, then the per-tick variance of its output is not a property of the biology. It is a property of the solver. To gate biological correctness, one must inject a perturbation and measure the response, not stare at raw variance and demand that it twitch.

**Tehol:** A small loss, then. Three days of work, returned to the void from which it briefly emerged.

**Bugg:** I would call it a slightly larger loss than that, except for one thing.

**Tehol:** And that thing.

**Bugg:** The lesson is now in the cross-project decision log, with full empirical evidence, citable forever. It is also captured in the inbox of the operating system that orchestrates this work, so it will surface on every future test design. If I had not made this mistake explicitly, written down, with the evidence, I would have made the same mistake again on a different substrate in three weeks, with much higher stakes.

**Tehol:** So you have purchased the lesson at the price of three days' embarrassment.

**Bugg:** And a four-hundred-line dialogue with a yet-to-be-launched canary trajectory, which is, even now, running in the background to confirm that nothing else broke during the cleanup.

**Tehol:** Bugg.

**Bugg:** Sir.

**Tehol:** When the canary lands, do not check it whilst at table. There is a kind of news that ruins the appetite.

**Bugg:** Noted, sir.

---

*Postscript, written at sixteen-fourteen.*

---

**Bugg:** Sir, I apologise for the second interruption. The canary has landed.

**Tehol:** And the appetite?

**Bugg:** Intact, sir. Thirty-two thousand four hundred ticks in twenty-one wall-clock minutes. The metabolism held its fixed point as predicted — ATP flat across the run, the LP solving to the same number every tick on short horizons, exactly the piecewise-constant behaviour we now understand to be a property of the solver and not a defect of the cell.

**Tehol:** And the rest of the cell.

**Bugg:** Awake, sir. Protein count rose from sixteen thousand two hundred and seventy-two to twenty-seven thousand four hundred and fifty-three across the cell cycle. Translation, which on yesterday's run had not fired once, was firing throughout. The replication state machine logged thirty-two thousand four hundred rows of fork progression. Cell mass rose by three-point-seven percent. The dNTP pool drained twenty-two percent, consistent with replication consuming substrate.

**Tehol:** Division.

**Bugg:** Not yet, sir. A separate matter, pre-existing, for a separate day.

**Tehol:** So the strip removed nothing that the cell was using.

**Bugg:** Precisely, sir. It removed code that was not helping. Four commits and a blog post are now on the main branch. The arc is closed.

**Tehol:** Then go and eat something, Bugg. You have earned a quiet supper.

**Bugg:** I will, sir. The next gate is the validation scorecard, but it can wait until morning.

---

*Written while the canary ran. Source decisions: `c1-false-positive-piecewise-constant-lp` and its parent `p0-phantom-invariant-eliminated-via-parity-flag` in the cross-project decision log. Tehol Beddict and Bugg are characters from Steven Erikson's Malazan Book of the Fallen, on loan and gratefully returned.*
