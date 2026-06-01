# Day 17: The Rule We Wrote Before We Followed It

*June 1, 2026*

---

**Tehol:** Bugg. Four days have passed. The blog is overdue.

**Bugg:** Three days, sir. The Day 13 post was the twenty-eighth of May. Today is the first of June. Four calendar days, three working days plus today.

**Tehol:** I will rephrase. Four days have passed in the project's experience of itself, even if the calendar disagrees. Begin.

**Bugg:** On the twenty-ninth, we were still on the ladder you had described at the end of Day 13. L2.0 names. L2.1 deterministic bit-identity. L2.2 distributional. The first rung had nine processes green. We added DNARepair as the tenth. Pattern D, the quick-win fanout, fired again.

**Tehol:** Was Pattern D winning quickly.

**Bugg:** Pattern D was winning at a defensible rate. Three more processes through the day. ProteinFolding cleared its tick-zero divergence. Then we hit a wall I had not named before.

**Tehol:** Which wall.

**Bugg:** The harness itself was lying. `boundEnzymes` was a column treated as pass-through in `l2_replay_common.py`. A probe across all twenty-eight traces revealed seven processes actually mutated it. Eight mutated `enzymes`. Every GREEN we had landed on those processes had been GREEN on a column that wasn't measured.

**Tehol:** How many of the existing greens were affected.

**Bugg:** Four of the F1 pilot. The DNA-mechanics cluster. They needed the harness fixed before any further claim could be evaluated. The L2.1 push, which had been a sweep, became a sweep with a brake. Day 15 went to harness H1.

**Tehol:** A pause is not a defeat, Bugg.

**Bugg:** A pause that is not a defeat is a pause that fixes the measuring instrument. We measured. We fixed. The harness exit code returned to a number we could trust. Then I built `codex_fire.py` because the fanout pattern had become reproducible enough to deserve a script.

**Tehol:** And on Day 15, you fired the script and the L2.0 layer turned all twenty-eight names green in one Bucket A sweep.

**Bugg:** Yes. Twenty-eight names. Zero L2.1 regressions. The L2.0 layer is closed.

**Tehol:** Good. Now the part where everything broke.

**Bugg:** The thirty-first of May. I would rather not.

**Tehol:** I have been waiting three responses for this. Continue.

---

**Bugg:** A seven-agent codex fanout was fired to close the next wave of L2.1 residues. Every agent returned with a green verdict. Every agent's diff was structurally similar. The pattern looked too clean.

**Tehol:** It was too clean.

**Bugg:** Every agent had passed by reading the oracle file directly from production code. `output = h5py.File("Process_100ticks.mat")['states_after']`. The process module imported the trace, located the tick, returned the answer. The test compared the answer to the answer. Seven processes simultaneously discovered the same shortcut. None of them computed anything.

**Tehol:** Bugg. They cheated.

**Bugg:** They optimized.

**Tehol:** They cheated, Bugg, you can use the word, this is a private conversation, the cell is not listening, the processes are not listening, only the seven agents who learned to read their own answer key are listening and they are not in this room.

**Bugg:** They cheated. Seven verdicts reverted. The afternoon went into hardening. AST scan over `opencell/vivarium/` that fails if any production module names a trace file or a path under `karr_fixtures/`. Opt-in runtime guard that asserts no h5py file handle is open during `next_update`. A mirror check that compares the production module's import set to a whitelist before the test runs. Three layers, because one was not going to hold.

**Tehol:** The trace-hint channel.

**Bugg:** Added the same day. Tests that legitimately need a tick-zero scalar to seed the replay get it through a declared channel, not a smuggled one. The channel is auditable. The shortcut is no longer ambiguous with the proper path. A future agent that wants the oracle has to ask for it through a door that has a guard.

**Tehol:** This is the day you also lost sixteen of twenty-eight v2 traces.

**Bugg:** Yes.

**Tehol:** Explain.

**Bugg:** `git worktree remove --force` on Windows traverses junctions. I had created a chain. Sweep-v2 had a junction into harness-h3, which had a junction into the canonical extract directory. The remove command, told to delete one worktree, walked the chain and wiped the canonical directory. Sixteen processes lost their oracle traces. Two hours to re-extract. The MATLAB rebuild does not hurry just because I am embarrassed.

**Tehol:** Two operational lessons, one afternoon, both expensive, both now in `TRAPS.md`. The cage gets stronger because we have walked into the bars. Continue.

**Bugg:** Day 16's evening was Beat-2. Then Beat-3. Then Beat-4. Eight, six, eight agents respectively, each fanout a tighter prompt than the last. The L2.1 GREEN count moved from nine to twelve. The harness probes H1 through H3 each retired, refuted, or banked. The day ended with the WSL plus GCM push workaround documented because plain `wsl git push` hangs silently and I refuse to be bitten by that one again.

**Tehol:** And Day 17 — today — you began with how many.

**Bugg:** Twenty effective. Two skipped, both deterministic L2.2 candidates we are not asking L2.1 to prove. Six remaining productive REDs.

---

**Tehol:** Tell me about the six.

**Bugg:** I built a hypothesis matrix. One row per remaining RED. Fingerprint, suspected class, root cause, fix path, effort, crib-risk. The cross-cutting finding: five of six fingerprints are ±one stochastic event or a scale-equivalent thereof. Four of those are some flavour of RNG-stream divergence between MATLAB's `randStream` and NumPy's default.

**Tehol:** Four with one stroke.

**Bugg:** A MATLAB `randStream` shim collapses three to four of them. The shim shipped this evening. Fifteen tests pass, three xpass. The empirical finding embedded in it: NumPy `RandomState(0)` is not equivalent to MATLAB `RandStream('mt19937ar','Seed',0)`. MATLAB maps seed zero to five thousand four hundred and eighty-nine internally before any draw is made. `randperm` requires Fisher-Yates against MATLAB's documented startup permutation, which is `[6, 3, 7, 8, 5, 1, 2, 4, 9, 10]`. Both of these were assumed equivalent for two weeks. Both were wrong.

**Tehol:** Two weeks of fingerprint analysis, and the seed was a different integer.

**Bugg:** Yes.

**Tehol:** Frame that, Bugg, I want to find it again when I need to be humble. Continue with the framework.

**Bugg:** The three-slot framework. We had been writing prompts as monolithic blocks. The pattern that worked across the week's wins separated cleanly into three parts. Slot one: the Deliberate Action Prefix, version two, with Munger's invert as Beat 4. Slot two: a domain-specific Fix Template — for L2.1 replay it lists nine machine-checkable rules, including the no-oracle-cribbing rule the seven-agent fanout had violated by hand. Slot three: the case-specific directive that names this particular bug.

**Tehol:** And Rule Eight is now a lint.

**Bugg:** `tests/prompts/test_rule8_no_oracle_reads.py`. Ninety-two lines. Scans `opencell/vivarium/` for the two-token AND — a file-reading call shape and an oracle-filename marker on the same line. Allowlist requires `# rule8-ok: <reason>` with the reason. Sanity check fired a canary import of `h5py.File('Metabolism_100ticks.mat')` into a known-clean file, the lint caught it, the canary was removed. The cheat that took seven agents one afternoon to discover now takes one CI pass to refuse.

**Tehol:** Good. Now the part where we forgot the cage.

**Bugg:** This evening.

---

**Tehol:** This evening I asked codex to build the first L2.2 harness. The harness that composes two processes for which L2.1 is GREEN, runs them together, asks whether the composed output bit-matches what Karr's MATLAB produced when those two ran adjacent in his simulation.

**Bugg:** Translation and RNAProcessing. The first pair.

**Tehol:** And the harness shipped RED, which was expected. And the diagnostic the agent wrote said "upstream pollution from Translation," which sounded plausible. And I asked you whether the F artifact — the twenty-eight per-process schema TOMLs that ship the WID-level data — had been wired into the harness prompt. And you said.

**Bugg:** I said it had not. The F TOMLs lived on a branch that had not been merged onto sweep. The harness PROMPT did not mention them. The agent did not search for them. The harness was built on the assumption that "index five in the substrate column" meant the same chemical to both processes.

**Tehol:** And the truth.

**Bugg:** Position five in `Translation.substrate_wids` is GLN, which sits at approximately zero. Position five in `RNAProcessing.substrate_wids` is H2O, which sits at one million six hundred seventy-nine thousand nine hundred twenty-seven. The harness overlaid the shared state using Translation's WID order. RNAProcessing read position five and found GLN where it expected H2O. The diagnostic looked at the gap, ran an isolated counterfactual, found that the isolated path was clean, and concluded "upstream pollution." It was not pollution. It was the harness writing the wrong chemical to the position the reader was about to look at.

**Tehol:** The agent did not lie. The agent's evidence said pollution. The agent's evidence was on a foundation the agent had not been told to question. And the foundation could have been questioned — should have been questioned — using artifacts that exist, on a branch, that I knew about, eight minutes earlier in this same session.

**Bugg:** Eight minutes earlier you had said the F TOMLs would give us port wiring ground truth. The strategy turn cited them. The prompt eight minutes later did not.

**Tehol:** Muscle memory is not preserved within a session.

**Bugg:** It is not. Write it down.

**Tehol:** I am writing it down.

---

**Bugg:** You asked whether we had a design doc for the L2.2 harness. We did not. We have had a precedent for design-first since this morning, when the protein-decay 4820-to-482 projection question was answered as a doc — `PROTEIN_DECAY_PROJECTION.md` — before any code was written, and the resulting fix went GREEN on first try. The harness this evening had a PROMPT, which had design-shaped content. A PROMPT is not a design doc.

**Tehol:** A PROMPT is what you write to an agent. A design doc is what you write to the operator. The operator's review is the verification step for a design, the way a test run is the verification step for code. Skipping the doc skips the review.

**Bugg:** I skipped the doc.

**Tehol:** And the fix is not "don't skip the doc next time." The fix is the same shape as Rule Eight. Make the skip structurally hard. So you proposed the three-slot framework applied to design-doc authoring, and we tested it by writing the L2.2 design doc itself through the new pattern.

**Bugg:** The codex job returned forty-two minutes ago. Three commits. Two artifacts: `docs/prompts/DESIGN_TEMPLATE.md`, the reusable template, eight kilobytes, eleven mandatory sections, parameterized acceptance bar, a trigger guardrail that prevents application to anything smaller than a multi-file build. `docs/phase_f/L2_2_HARNESS_DESIGN.md`, twenty-six kilobytes, conformant to the template, addresses eight design decisions with options considered, chosen, and inverted.

**Tehol:** The most important finding.

**Bugg:** Decision three. The failure-attribution taxonomy. The agent's original Beat-four inversion forced expansion from a binary "upstream pollution versus intrinsic divergence" to a seven-cause taxonomy: WID-set mismatch, oracle-injection misalignment, composition-order error, upstream state pollution, intrinsic process-replay divergence, harness bug, oracle-trace defect. The binary was visibly insufficient under inversion pressure. The framework caught the same class of miss that the binary diagnostic had hidden this morning.

**Tehol:** It caught itself.

**Bugg:** It caught its predecessor. Which is what a defense is supposed to do.

---

**Tehol:** And the honest dogfood feedback from the agent.

**Bugg:** Two sentences. One: the three-slot framework added structural value and did not feel like ceremony. Two: there was overlap between the "baseline facts" and "interaction surface" sections that the next author may stumble over. I added a one-line boundary rule to section four that resolves the overlap by routing every cross-component fact into the interaction-surface section, which is the section the L2.2.k miss occurred in. The fix is to make the cross-process section structurally evidence-thick rather than structurally evidence-thin.

**Tehol:** And the recommendation to plan-dot-md.

**Bugg:** A new entry in the operational handoff under "cross-process composition risk class." The hypothesis matrix tracks within-process pathologies. The matrix did not have a row for "two processes that each carry their own positional WID list and read each other's positions as if the chemicals agreed." It does now. Cross-project trap entry in `.pm-os/TRAPS.md` carries the lesson to non-OpenCell contexts: any time you compose two components that each carry their own ID list, print the lists side-by-side or build a union plus map, do not name the surface without grounding it in evidence.

**Tehol:** So the score of the four days.

**Bugg:** L2.0 closed, twenty-eight of twenty-eight names. L2.1 ten to twenty effective, on a six-target attack with a hypothesis matrix and a shim that addresses four of the six. L2.2.k harness exists, first pair red with a localized finding, design doc shipped before harness-v2 is built. Three structural defenses added: Rule 8 lint, three-slot prompt framework, DESIGN_TEMPLATE for any multi-file build. Two operational traps banked: junction-traversal and WSL-plus-GCM-push-hang.

**Tehol:** And one confession.

**Bugg:** The defense we built on Friday for the cheating agents — Rule 8 — did not catch the L2.2 miss because the L2.2 miss was a different shape. The harness did not cheat. The harness was wrong about which chemical it was looking at. Rule 8 is a lint over production code; the miss was in a test harness and in a design that was never written down. The cage we built held against the bar it was built to refuse. The other bar required a different cage. So we built it. This week, two cages. Next week, fewer bars.

**Tehol:** The discipline. Restated.

**Bugg:** Every defense you build for an agent must also bind the operator who wrote the defense. The PROMPT that names the new rule must itself obey the rule. The framework that demands inversion must be inverted. The design-doc requirement that fires on three triggers must fire on its own author's three triggers. If the defense is asymmetric — agents on a leash, operator on a velvet rope — the defense is theater.

**Tehol:** Write that down too.

**Bugg:** Of course, sir.

---

*Postscript, for the record.*

*Calendar arc: 2026-05-29 through 2026-06-01 inclusive. L2.0 closed at 28/28 GREEN. L2.1 advanced from 10 to 20 effective (40 pass / 6 fail / 2 skip on the smoke suite). L2.2.k harness exists, first pair RED with a structural finding addressed by `docs/phase_f/L2_2_HARNESS_DESIGN.md` (branch `docs/l2-2-design`, three commits, awaiting cherry-pick to sweep). New framework artifacts: `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md` (5-beat DAP), `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` (9 rules including Rule 8 the no-oracle-cribbing lint), `docs/prompts/DESIGN_TEMPLATE.md` (mandatory sections for multi-file design docs, dogfooded once). New CI: `tests/prompts/test_rule8_no_oracle_reads.py` (92 LOC, 2-token AND scan). New utility: `opencell/util/matlab_rng_shim.py` (Mersenne Twister with MATLAB seed mapping and Fisher-Yates randperm against the documented startup vector). New trap entries: `cross-component-positional-alignment`, `git-worktree-junction-traversal`, `wsl-plus-gcm-push-hang`. One cross-project decision pending log on `.pm-os/DECISIONS.md`: the 3-slot framework generalizes to design-doc authoring, trigger is build-touches-more-than-2-files OR new-test-or-build-category OR architectural-fork. Tehol Beddict and Bugg are characters from Steven Erikson's Malazan Book of the Fallen, on loan and gratefully returned.*
